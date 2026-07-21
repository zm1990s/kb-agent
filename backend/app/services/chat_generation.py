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
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.db import SessionLocal
from app.models.auth import User
from app.services.answer_service import (
    AnswerResult,
    Stage,
    ThinkingChunk,
    TokenChunk,
    answer_question_streamed,
)
from app.services.answer_service_plus import (
    OutputFilesResult,
    answer_question_plus_streamed,
)
from app.services.chat_service import add_message, generate_conversation_title
from app.services.usage_service import record_event

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# 生成器工厂：绑好各自参数，产出 Thinking/Token/AnswerResult/OutputFiles/Stage 项
StreamFactory = Callable[["AsyncSession", "GenerationState"], AsyncIterator]

logger = logging.getLogger(__name__)

# 终态保留窗口（秒）：让刚返回的客户端还能读到 done / 补发，之后清出注册表。
# 设为 300s：用户切换菜单再返回常超过 30s，延长窗口让 catchup 兜底更可靠。
_GRACE_SEC = 300

# 队列哨兵：推给订阅者表示流结束
_END = object()


class GenerationInProgress(Exception):
    """该会话已有生成任务在跑。"""


@dataclass
class GenerationState:
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    is_new_conv: bool
    # 来源：区分普通对话（chat）与聊天+（chatplus）。驱动 record_event 的 action，
    # 并让 /chat/active 与 /chat/plus/active 各自只列自己来源的会话。
    source: str = "chatplus"
    # 为 true 时把 Stage 广播为 stage 事件（普通对话需要）；false 时忽略（聊天+ 现状）。
    forward_stage: bool = False
    # 审计元信息：workspace_id 记单个（首个）空间；extra_meta 合并进 record_event 的 meta。
    event_workspace_id: uuid.UUID | None = None
    extra_meta: dict = field(default_factory=dict)
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
    started_at_epoch: float = field(default_factory=time.time)


_registry: dict[uuid.UUID, GenerationState] = {}
_bg_tasks: set[asyncio.Task] = set()  # 持有任务引用，防被 GC


# ── 查询 ────────────────────────────────────────────────────────────────


def is_active(conversation_id: uuid.UUID) -> bool:
    """该会话是否有生成任务【正在 running】。

    注意：终态（done/error/cancelled）保留窗口内的任务不算 active——否则上一轮
    刚结束的窗口期内发新消息会被误判为「生成中」。
    """
    st = _registry.get(conversation_id)
    return st is not None and st.status == "running"


def list_active(user_id: uuid.UUID, source: str = "chatplus") -> list[uuid.UUID]:
    """该用户当前仍在 running 的会话 id 列表（侧边栏指示器用），按来源过滤。"""
    return [
        cid
        for cid, st in _registry.items()
        if st.user_id == user_id and st.status == "running" and st.source == source
    ]


def list_active_details(user_id: uuid.UUID, source: str = "chatplus") -> list[dict]:
    """该用户当前 running 会话详情（按来源过滤），用于前端重连后恢复真实运行时长。

    elapsed_seconds 用服务器单调时钟算出「已运行秒数」，供前端以本机时钟
    反推锚点（Date.now() - elapsed*1000），避免客户端/服务端墙钟偏移导致
    显示时长失真。started_at 绝对值一并保留（无害，供调试/回退）。
    """
    now = time.monotonic()
    return [
        {
            "conversation_id": str(cid),
            "started_at": st.started_at_epoch,
            "elapsed_seconds": max(0.0, now - st.started_at),
        }
        for cid, st in _registry.items()
        if st.user_id == user_id and st.status == "running" and st.source == source
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
    """终态保留窗口结束后，把该会话清出注册表。

    只删「仍是当前这个 state」的条目：若窗口内已有新一轮生成覆盖了同一
    conversation_id，则新 state 不应被这个旧定时器误删。
    """
    state = _registry.get(conversation_id)

    def _remove() -> None:
        if _registry.get(conversation_id) is state:
            _registry.pop(conversation_id, None)

    loop = asyncio.get_running_loop()
    loop.call_later(_GRACE_SEC, _remove)


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
    stream_factory: "StreamFactory",
) -> None:
    """detached 任务主体：跑生成、广播事件、完成落库。

    与来源无关：stream_factory 是一个绑好各自参数的异步生成器工厂，产出
    ThinkingChunk / TokenChunk / AnswerResult / OutputFilesResult / Stage。
    普通对话（forward_stage=True）会把 Stage 实时广播为 stage 事件；Stage 不
    进 stream_blocks，故晚到的重连不会补发过期 stage（终态 done 已取代）。
    """
    final: AnswerResult | None = None
    output_files: list[dict] = []
    async with SessionLocal() as session:
        try:
            async for item in stream_factory(session, state):
                if isinstance(item, ThinkingChunk):
                    _broadcast(state, "thinking", {"text": item.text})
                elif isinstance(item, TokenChunk):
                    _broadcast(state, "token", {"text": item.text})
                elif isinstance(item, AnswerResult):
                    final = item
                elif isinstance(item, OutputFilesResult):
                    output_files = item.files
                elif isinstance(item, Stage):
                    if state.forward_stage:
                        # 仅实时广播、不进 stream_blocks（不参与 catchup 补发）
                        _broadcast(state, "stage", {
                            "stage": item.stage,
                            "message_key": item.message_key,
                            "message_params": item.message_params,
                        })
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
            logger.exception("%s 生成失败 conv=%s", state.source, state.conversation_id)
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

            # 用量统计：action 取自来源（chat / chatplus）；extra_meta 合并（如空间归因）
            await record_event(
                session,
                action=state.source,
                user_id=state.user_id,
                workspace_id=state.event_workspace_id,
                meta={
                    "conversation_id": str(state.conversation_id),
                    "question": question,
                    "answer": final.answer,
                    **state.extra_meta,
                },
            )

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


def _spawn(state: GenerationState, question: str, stream_factory: "StreamFactory") -> GenerationState:
    """登记 state 并起 detached 任务；调用方已确保 conversation 未在跑。"""
    _registry[state.conversation_id] = state
    task = asyncio.create_task(
        _run_generation(state, question=question, stream_factory=stream_factory)
    )
    state.task = task
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return state


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
    attachment_names: dict[str, str] | None = None,
    interactive: bool = False,
    use_original_docs: bool = False,
    engine_override: str = "",
) -> GenerationState:
    """启动一个聊天+ detached 生成任务；该会话已在跑则抛 GenerationInProgress。

    检查 + 登记之间无 await，单线程 asyncio 下原子。
    """
    # 仅当确有任务在 running 时才拒绝；终态（done/error/cancelled）保留窗口内的
    # 旧任务不应阻挡新一轮——否则上一轮刚结束的 _GRACE_SEC 秒内点选项/发消息会被
    # 误判为「生成中」而 409，前端退化成订阅旧的已结束流，表现为「点了没反应」。
    if is_active(conversation_id):
        raise GenerationInProgress()

    state = GenerationState(
        conversation_id=conversation_id,
        user_id=user_id,
        is_new_conv=is_new_conv,
        source="chatplus",
        forward_stage=False,
        event_workspace_id=workspace_id,
    )

    async def _factory(session, st):
        # 在本任务会话重取 User，避免跨会话 lazy-load（check_skill_access 加载组关系）
        user = await session.get(User, st.user_id)
        if user is None:
            raise RuntimeError(f"生成任务找不到用户 user={st.user_id}")
        async for item in answer_question_plus_streamed(
            session,
            workspace_id=workspace_id,
            conversation_id=st.conversation_id,
            user=user,
            question=question,
            history=history,
            doc_ids=doc_ids,
            all_docs=all_docs,
            skill_ids=skill_ids,
            attachment_keys=attachment_keys,
            attachment_names=attachment_names,
            interactive=interactive,
            use_original_docs=use_original_docs,
            engine_override=engine_override,
        ):
            yield item

    return _spawn(state, question, _factory)


def start_chat_generation(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    is_new_conv: bool,
    question: str,
    history: list[tuple[str, str]] | None,
    workspace_id: uuid.UUID | list[uuid.UUID] | None,
    conv_ws: uuid.UUID | None,
    ws_all: list[str],
) -> GenerationState:
    """启动一个普通对话 detached 生成任务；该会话已在跑则抛 GenerationInProgress。

    workspace_id 可为单空间 / 空间列表（自动定位）/ None；conv_ws 为审计记录用
    的单一空间；ws_all 为完整空间归因（写入 meta.workspaces）。
    """
    if is_active(conversation_id):
        raise GenerationInProgress()

    state = GenerationState(
        conversation_id=conversation_id,
        user_id=user_id,
        is_new_conv=is_new_conv,
        source="chat",
        forward_stage=True,
        event_workspace_id=conv_ws,
        extra_meta={"workspaces": ws_all},
    )

    async def _factory(session, st):
        # 空列表按 None 处理，复用 answer_question_streamed 的 no_docs 分支
        async for item in answer_question_streamed(
            session,
            workspace_id=workspace_id or None,
            question=question,
            history=history,
        ):
            yield item

    return _spawn(state, question, _factory)
