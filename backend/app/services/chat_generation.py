"""聊天+ 后台生成注册表：把「生成」与「SSE 传输」解耦。

问题：原本生成跑在请求生成器里，客户端断连 → Starlette 抛 CancelledError →
Claude 子进程被杀、助手消息从未落库。

方案：生成跑在 detached asyncio 任务里（自己的 DB 会话 + 子进程），完成时落库；
SSE 请求退化成「订阅者」，只从内存队列读事件转发。断连只退订，任务继续。

前提：单 uvicorn 进程（entrypoint.sh，无 --workers），故按 conversation_id
建内存注册表安全。重启会丢在途任务（与 tasks/worker.py 取舍一致）。
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from app.core.db import SessionLocal
from app.models.auth import User
from app.services.answer_service import AnswerResult, ThinkingChunk, TokenChunk
from app.services.answer_service_plus import (
    OutputFilesResult,
    answer_question_plus_streamed,
)
from app.services.chat_service import add_message, generate_conversation_title

logger = logging.getLogger(__name__)

# 终态保留窗口（秒）：让刚返回的客户端还能读到 done / 补发，之后清出注册表
_GRACE_SEC = 30

# 队列哨兵：推给订阅者表示流结束
_END = object()


class GenerationInProgress(Exception):
    """该会话已有生成任务在跑。"""


@dataclass
class GenerationState:
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    is_new_conv: bool
    status: str = "running"  # running | done | error | cancelled
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    # 按序累积的流式块（thinking / token 交替，同类合并）；供重连补发。
    # 仅内存、不落库——thinking 不进 DB。每项 (kind, text)，kind ∈ {"thinking","token"}。
    stream_blocks: list[list] = field(default_factory=list)
    # 终态事件（done / output_files / title），供晚到的重连按序补发
    terminal_events: list[tuple[str, dict]] = field(default_factory=list)
    task: asyncio.Task | None = None
    cancel_requested: bool = False
    started_at: float = field(default_factory=time.monotonic)


_registry: dict[uuid.UUID, GenerationState] = {}
_bg_tasks: set[asyncio.Task] = set()  # 持有任务引用，防被 GC


# ── 查询 ────────────────────────────────────────────────────────────────


def is_active(conversation_id: uuid.UUID) -> bool:
    """该会话是否有生成任务在注册表内（running 或处于终态保留窗口）。"""
    return conversation_id in _registry


def list_active(user_id: uuid.UUID) -> list[uuid.UUID]:
    """该用户当前仍在 running 的会话 id 列表（侧边栏指示器用）。"""
    return [
        cid
        for cid, st in _registry.items()
        if st.user_id == user_id and st.status == "running"
    ]


# ── 广播 / 订阅 ──────────────────────────────────────────────────────────


def _broadcast(state: GenerationState, event: str, data: dict) -> None:
    """把事件推给所有订阅者（无界队列 + put_nowait，慢订阅者不拖垮生成）。"""
    # 累积 thinking / token 为有序块（同类合并），供重连按序补发
    if event in ("thinking", "token"):
        text = data["text"]
        blocks = state.stream_blocks
        if blocks and blocks[-1][0] == event:
            blocks[-1][1] += text
        else:
            blocks.append([event, text])
    for q in state.subscribers:
        q.put_nowait((event, data))


def subscribe(
    conversation_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[GenerationState, asyncio.Queue, list[tuple[str, dict]]] | None:
    """订阅某会话的生成流。

    返回 (state, queue, catchup)；不存在或非 owner 返回 None（不泄漏存在性）。
    catchup = 已累积的 thinking/token 块（按序）+ 终态事件。
    若已终态，队列预置 _END，补发完即结束。
    本函数同步、无 await，读 status/stream_blocks/terminal_events 原子（单线程 asyncio）。
    """
    state = _registry.get(conversation_id)
    if state is None or state.user_id != user_id:
        return None

    queue: asyncio.Queue = asyncio.Queue()
    catchup: list[tuple[str, dict]] = []
    for kind, text in state.stream_blocks:
        catchup.append((kind, {"text": text}))
    catchup.extend(state.terminal_events)

    if state.status == "running":
        state.subscribers.add(queue)
    else:
        # 已终态：补发完直接结束，不加入 subscribers（不会再有新事件）
        queue.put_nowait(_END)
    return state, queue, catchup


def unsubscribe(state: GenerationState, queue: asyncio.Queue) -> None:
    """退订（客户端断连时调用）；只移除队列，绝不动生成任务。"""
    state.subscribers.discard(queue)


def request_cancel(conversation_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """请求取消生成（停止按钮）；校验 owner。不在跑/非 owner 返回 False。"""
    state = _registry.get(conversation_id)
    if state is None or state.user_id != user_id or state.status != "running":
        return False
    state.cancel_requested = True
    if state.task is not None:
        state.task.cancel()
    return True


# ── 生成任务 ────────────────────────────────────────────────────────────


def _schedule_removal(conversation_id: uuid.UUID) -> None:
    """终态保留窗口结束后，把该会话清出注册表。"""
    loop = asyncio.get_running_loop()
    loop.call_later(_GRACE_SEC, _registry.pop, conversation_id, None)


async def _persist_and_finalize(
    session,
    state: GenerationState,
    answer: str,
    sources: list[dict],
    output_files: list[dict],
) -> None:
    """用任务自己的会话落库助手消息。"""
    await add_message(
        session,
        conversation_id=state.conversation_id,
        role="assistant",
        content=answer,
        sources=sources,
        output_files=output_files,
    )


async def _run_generation(
    state: GenerationState,
    *,
    question: str,
    history: list[tuple[str, str]] | None,
    workspace_id: uuid.UUID | None,
    doc_ids: list[uuid.UUID] | None,
    all_docs: bool,
    skill_ids: list[uuid.UUID] | None,
    attachment_keys: list[str] | None,
    interactive: bool = False,
) -> None:
    """detached 任务主体：跑生成、广播事件、完成落库。"""
    final: AnswerResult | None = None
    output_files: list[dict] = []
    async with SessionLocal() as session:
        # 在本会话重取 User，避免跨会话 lazy-load（check_skill_access 会加载组关系）
        user = await session.get(User, state.user_id)
        if user is None:
            logger.error("生成任务找不到用户 user=%s", state.user_id)
            state.status = "error"
            for q in list(state.subscribers):
                q.put_nowait(_END)
            _schedule_removal(state.conversation_id)
            return
        try:
            async for item in answer_question_plus_streamed(
                session,
                workspace_id=workspace_id,
                conversation_id=state.conversation_id,
                user=user,
                question=question,
                history=history,
                doc_ids=doc_ids,
                all_docs=all_docs,
                skill_ids=skill_ids,
                attachment_keys=attachment_keys,
                interactive=interactive,
            ):
                if isinstance(item, ThinkingChunk):
                    _broadcast(state, "thinking", {"text": item.text})
                elif isinstance(item, TokenChunk):
                    _broadcast(state, "token", {"text": item.text})
                elif isinstance(item, AnswerResult):
                    final = item
                elif isinstance(item, OutputFilesResult):
                    output_files = item.files
                # Stage 不广播（前端本就忽略）
        except asyncio.CancelledError:
            # 客户端点了停止：子进程已由生成器 finally 杀掉；落库已累积的部分答案
            # （只取 token 块，thinking 不落库）
            state.status = "cancelled"
            answer = "".join(
                t for k, t in state.stream_blocks if k == "token"
            ).strip()
            try:
                await _persist_and_finalize(session, state, answer, [], [])
            except Exception:
                logger.exception(
                    "cancelled 后落库失败 conv=%s", state.conversation_id
                )
            for q in list(state.subscribers):
                q.put_nowait(_END)
            _schedule_removal(state.conversation_id)
            raise  # re-raise，让任务真正结束
        except Exception:
            logger.exception("chat+ 生成失败 conv=%s", state.conversation_id)
            state.status = "error"
            evt = {
                "answer": "",
                "sources": [],
                "conversation_id": str(state.conversation_id),
                "error_key": "engine_unavailable",
            }
            state.terminal_events.append(("done", evt))
            _broadcast(state, "done", evt)
        else:
            if final is None:
                final = AnswerResult(answer="", sources=[], error_key="no_answer")
            state.status = "done"
            done_payload: dict = {
                "answer": final.answer,
                "sources": final.sources,
                "conversation_id": str(state.conversation_id),
            }
            if final.error_key:
                done_payload["error_key"] = final.error_key
            state.terminal_events.append(("done", done_payload))
            _broadcast(state, "done", done_payload)

            if output_files:
                files_evt = {"files": output_files}
                state.terminal_events.append(("output_files", files_evt))
                _broadcast(state, "output_files", files_evt)

            try:
                await _persist_and_finalize(
                    session, state, final.answer, final.sources, output_files
                )
            except Exception:
                logger.exception("助手消息落库失败 conv=%s", state.conversation_id)

            if state.is_new_conv:
                title = await generate_conversation_title(
                    session,
                    conversation_id=state.conversation_id,
                    first_message=question,
                )
                if title:
                    title_evt = {
                        "conversation_id": str(state.conversation_id),
                        "title": title,
                    }
                    state.terminal_events.append(("title", title_evt))
                    _broadcast(state, "title", title_evt)
        finally:
            # 正常/错误路径：结束所有订阅流并安排清理（cancel 路径已在上面处理）
            if state.status != "cancelled":
                for q in list(state.subscribers):
                    q.put_nowait(_END)
                _schedule_removal(state.conversation_id)


def start_generation(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    is_new_conv: bool,
    question: str,
    history: list[tuple[str, str]] | None,
    workspace_id: uuid.UUID | None,
    doc_ids: list[uuid.UUID] | None,
    all_docs: bool,
    skill_ids: list[uuid.UUID] | None,
    attachment_keys: list[str] | None,
    interactive: bool = False,
) -> GenerationState:
    """启动一个 detached 生成任务；该会话已在跑则抛 GenerationInProgress。

    检查 + 登记之间无 await，单线程 asyncio 下原子。
    """
    if is_active(conversation_id):
        raise GenerationInProgress()

    state = GenerationState(
        conversation_id=conversation_id,
        user_id=user_id,
        is_new_conv=is_new_conv,
    )
    _registry[conversation_id] = state

    task = asyncio.create_task(
        _run_generation(
            state,
            question=question,
            history=history,
            workspace_id=workspace_id,
            doc_ids=doc_ids,
            all_docs=all_docs,
            skill_ids=skill_ids,
            attachment_keys=attachment_keys,
            interactive=interactive,
        )
    )
    state.task = task
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return state
