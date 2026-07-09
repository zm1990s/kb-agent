"""归类 service：经 engine 让 Claude CLI 读原文，一趟产出

{category, summary, tags, content_text}，写回 documents 并维护全文检索向量。

设计要点：
- LLM 只经 app/engine/（唯一出口）。
- 后台任务，处理任务记录状态/日志/重试（processing_tasks）。
- 失败不静默：落 error + status=failed，可经 reprocess 重试。
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.base import get_engine
from app.models.document import Category, Document, ProcessingTask


def _parse_engine_json(text: str) -> dict:
    """从引擎输出中提取 JSON 对象（容忍前后包裹的代码块/文字）。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("引擎输出中未找到 JSON 对象")
    return json.loads(text[start : end + 1])


async def _resolve_category_id(
    session: AsyncSession, workspace_id: uuid.UUID, name: str | None
) -> uuid.UUID | None:
    """把分类名解析为该 workspace 内的 category_id；找不到返回 None。"""
    if not name:
        return None
    stmt = select(Category.id).where(
        Category.workspace_id == workspace_id, Category.name == name
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _append_log(task: ProcessingTask, stage: str, message: str) -> None:
    entry = {"stage": stage, "message": message, "at": datetime.now(UTC).isoformat()}
    # JSONB list，重新赋值以触发 ORM 脏标记
    task.logs = [*(task.logs or []), entry]


async def run_classification(session: AsyncSession, task_id: uuid.UUID) -> None:
    """执行一次归类任务。捕获异常并落库为 failed（可重试），不向外抛。"""
    task = await session.get(ProcessingTask, task_id)
    if task is None:
        return
    doc = await session.get(Document, task.document_id)
    if doc is None:
        return

    task.status = "running"
    task.attempts += 1
    _append_log(task, "start", f"第 {task.attempts} 次尝试")
    await session.commit()

    try:
        # 候选分类
        cats_result = await session.execute(
            select(Category.name).where(Category.workspace_id == doc.workspace_id)
        )
        cat_names = [n for (n,) in cats_result.all()]

        from app.services.settings_service import CLASSIFY_PROMPT_KEY, get_prompt
        prompt_tpl = await get_prompt(session, CLASSIFY_PROMPT_KEY)
        prompt = prompt_tpl.format(
            categories=", ".join(cat_names) if cat_names else "（无预定义分类）",
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

        # 经 engine 让 CLI 读原文（唯一 LLM 出口）；引擎后端取管理员在应用内的选择
        from app.services.settings_service import get_engine_backend

        engine = get_engine(await get_engine_backend(session))
        from app.storage.base import get_storage

        path = await get_storage().open_path(doc.storage_key)
        result = await engine.complete(prompt, files=[path])
        _append_log(task, "engine", "引擎返回，开始解析")

        parsed = _parse_engine_json(result.text)
        category_id = await _resolve_category_id(
            session, doc.workspace_id, parsed.get("category")
        )

        doc.category_id = category_id
        doc.brief = parsed.get("brief")
        doc.summary = parsed.get("summary")
        doc.tags = list(parsed.get("tags") or [])
        doc.content_text = parsed.get("content_text")
        doc.status = "ready"

        # 维护全文检索向量（title + summary + content_text）
        await session.execute(
            update(Document)
            .where(Document.id == doc.id)
            .values(
                search_tsv=func.to_tsvector(
                    "simple",
                    func.concat_ws(
                        " ",
                        doc.title,
                        doc.summary or "",
                        doc.content_text or "",
                    ),
                )
            )
        )

        task.status = "succeeded"
        task.error = None
        _append_log(task, "done", "归类成功")
        await session.commit()

    except Exception as exc:  # noqa: BLE001  # 后台任务须兜底，不能让异常逃逸
        await session.rollback()
        task = await session.get(ProcessingTask, task_id)
        doc = await session.get(Document, task.document_id) if task else None
        if task is not None:
            err = f"{type(exc).__name__}: {exc}"
            task.status = "failed"
            task.error = err
            _append_log(task, "error", err)
        if doc is not None:
            doc.status = "failed"
        await session.commit()
