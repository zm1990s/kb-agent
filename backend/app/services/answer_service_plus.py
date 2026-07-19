"""聊天+ 专用问答 service（与原始「聊天」逻辑物理隔离）。

设计要点（与 answer_service.py 的原始聊天不同）：
- 直连 Claude：不套两阶段 answer_fetch/answer_prompt 模板（Claude CLI 自带系统提示词）；
- Skill 内容经 --append-system-prompt 注入；
- 每会话持久工作目录 chatplus/conv_{conv}（与工作区解耦）：附件与 Agent 生成的
  文件跨轮次保留，Agent 可继续引用/修改；输出文件通过目录 diff 检测；
- 文档上下文：显式勾选 doc_ids 或 all_docs=True 时注入正文，均限量 MAX_PLUS_CONTEXT_DOCS
  篇（超出按最近优先截断并 log，不静默）；sources 恒为空。

共享的数据类与工具从 answer_service 复用，避免重复；原始聊天零改动。
"""

import logging
import shutil
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.base import EngineError, get_engine
from app.models.auth import User
from app.models.document import Document
from app.services.answer_service import (
    AnswerResult,
    Stage,
    ThinkingChunk,
    TokenChunk,
    _format_history,
)
from app.storage.base import get_storage

logger = logging.getLogger(__name__)

# 单次注入正文的文档上限（控制 token，防撑爆上下文）。超出按最近优先截断并 log。
MAX_PLUS_CONTEXT_DOCS = 20

# 单篇正文注入的字符上限
_DOC_CONTEXT_CHARS = 8000

# Skill bundle 解包上限（防 zip 炸弹）：总解压字节 + 文件数
_BUNDLE_MAX_TOTAL_BYTES = 50 * 1024 * 1024
_BUNDLE_MAX_FILES = 500

# 交互模式协议：仅当 interactive=True 时注入 system，让模型可弹选项向用户澄清。
# 模型输出 ```ask-user 围栏 JSON 块并结束本轮；前端解析成可点选项 + 「其他」自由输入框。
ASK_USER_PROTOCOL = """## 交互提问能力（已启用）

当你需要用户澄清关键信息（如目标、格式、语言、范围等）才能继续时，不要自行假设，\
而应向用户提问并给出候选选项。提问时输出一个如下格式的围栏代码块，然后**立即结束本轮回复**，\
等待用户选择后再继续：

```ask-user
{
  "question": "你的问题（简洁明确）",
  "options": [
    {"label": "选项一", "description": "可选的简短说明"},
    {"label": "选项二", "description": "可选的简短说明"}
  ],
  "multiSelect": false
}
```

规则：
- `question` 必填；`options` 给 2~4 个最可能的候选，每项 `label` 必填、`description` 可选。
- `multiSelect` 为 true 时表示用户可多选（默认 false 单选）。
- 前端会自动在选项之外附加一个「其他」自由输入框，你**无需**在 options 里加「其他/自定义」项。
- 仅在确有必要澄清时使用；信息已足够时正常作答，不要滥用。
- 输出该块后就停止，不要在同一轮里替用户假设答案继续往下做。
- **执行任何 Skill 后**，若结果存在歧义、需要用户确认下一步，或有多种合理后续方向，\
必须先 ask-user 再继续，不得自行假设。"""


def _slug(name: str) -> str:
    import re

    s = re.sub(r"[^\w\-]+", "-", name, flags=re.UNICODE).strip("-")
    return s or "skill"


# 注入的 Skill 附属文件放在此前缀下，检测输出时需排除
_SKILL_DIR = "skills"
# 注入的原始参考文档放在此前缀下（use_original_docs），检测输出时同样排除
_CONTEXT_DIR = "context"
# 顶层注入目录：仅当作为工作目录根下的一级前缀时排除
_INJECTED_PREFIXES = (_SKILL_DIR, _CONTEXT_DIR)

# 编程/依赖产生的临时目录：路径中任意一段命中即排除（node_modules 等）
_NOISE_DIRS = frozenset({
    "node_modules", "__pycache__", ".git", ".venv", "venv", "env",
    ".cache", ".npm", ".pnpm-store", ".yarn", ".next", ".nuxt",
    "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".ipynb_checkpoints", ".gradle", "target", ".tox", "site-packages",
})
# 依赖锁文件 / 编程杂项：按 basename 精确排除
_NOISE_FILES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "package.json",
    "requirements.txt", "poetry.lock", "Pipfile", "Pipfile.lock",
    ".gitignore", ".npmrc", ".DS_Store", "tsconfig.json",
})
# 临时/编译产物后缀
_NOISE_SUFFIXES = (".pyc", ".pyo", ".log", ".lock", ".tmp")


def _is_noise(rel: str) -> bool:
    """判断相对路径是否为编程/依赖产生的临时文件，应从输出中排除。"""
    parts = rel.split("/")
    # 顶层注入目录（skills/、context/）
    if parts[0] in _INJECTED_PREFIXES:
        return True
    # 路径任意一段命中噪声目录名（node_modules 可能嵌套在子目录里）
    if any(seg in _NOISE_DIRS for seg in parts[:-1]):
        return True
    name = parts[-1]
    if name in _NOISE_FILES:
        return True
    if name.startswith("."):  # 隐藏文件（.env 等杂项），非用户产物
        return True
    return name.endswith(_NOISE_SUFFIXES)


def _list_workdir_files(workdir) -> set[str]:
    """递归列出工作目录下的输出文件相对路径，排除注入目录与编程临时文件。"""
    from pathlib import Path

    root = Path(workdir)
    out: set[str] = set()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if _is_noise(rel):
            continue
        out.add(rel)
    return out


def _safe_doc_filename(title: str, fallback: str) -> str:
    """从文档 title 重建安全的落盘文件名（SECURITY #5 防路径穿越）。

    只取 basename，去除路径分隔符/父目录引用/控制字符，保留扩展名（Claude 靠
    扩展名/MIME 识别类型）。清洗后为空则用 fallback。
    """
    import re
    from pathlib import PurePosixPath, PureWindowsPath

    # 同时按 POSIX 与 Windows 分隔符取 basename，防 a/b 或 a\b
    name = PureWindowsPath(PurePosixPath(title).name).name
    name = name.replace("\x00", "").strip().strip(".")
    # 去掉除字母数字、点、下划线、连字符、空格、常见 CJK 外的字符
    name = re.sub(r"[^\w.\- ]+", "_", name, flags=re.UNICODE).strip()
    return name or fallback


def _extract_bundle(data: bytes, dest_dir) -> list[str]:
    """把 skill 整包安全解包到 dest_dir，返回解出的相对路径列表。

    防 zip-slip（拒绝 ../绝对路径/逃逸），并限总大小与文件数。失败/可疑条目跳过并 log。
    """
    import io
    import zipfile
    from pathlib import Path, PurePosixPath

    dest = Path(dest_dir)
    extracted: list[str] = []
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if len(extracted) >= _BUNDLE_MAX_FILES:
                    logger.warning("skill bundle 文件数超上限 %d，截断", _BUNDLE_MAX_FILES)
                    break
                name = info.filename
                parts = PurePosixPath(name).parts
                # 防穿越：拒绝绝对路径与含 .. 的条目
                if PurePosixPath(name).is_absolute() or ".." in parts:
                    logger.warning("skill bundle 跳过可疑路径条目: %s", name)
                    continue
                total += info.file_size
                if total > _BUNDLE_MAX_TOTAL_BYTES:
                    logger.warning("skill bundle 解压总大小超上限，停止解包")
                    break
                target = (dest / name).resolve()
                # 二次校验：解析后必须仍在 dest 内
                if dest.resolve() != target and dest.resolve() not in target.parents:
                    logger.warning("skill bundle 跳过逃逸条目: %s", name)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
                extracted.append(name)
    except zipfile.BadZipFile:
        logger.warning("skill bundle 无效 zip，跳过解包")
    return extracted


@dataclass
class OutputFilesResult:
    """Claude 在工作目录生成的输出文件列表（聊天+ 专用）。"""

    files: list[dict] = field(default_factory=list)
    # 每个 dict: {filename, storage_key, conversation_id}


async def _load_context_docs(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    doc_ids: list[uuid.UUID] | None,
    all_docs: bool,
) -> list[Document]:
    """加载要注入正文的文档（限量 MAX_PLUS_CONTEXT_DOCS，最近优先）。"""
    stmt = (
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.status == "ready",
            Document.deleted_at.is_(None),
        )
        .order_by(Document.created_at.desc())
    )
    if not all_docs:
        if not doc_ids:
            return []
        stmt = stmt.where(Document.id.in_(doc_ids))
    # 多取一条以判断是否超限
    stmt = stmt.limit(MAX_PLUS_CONTEXT_DOCS + 1)
    docs = list((await session.execute(stmt)).scalars().all())
    if len(docs) > MAX_PLUS_CONTEXT_DOCS:
        logger.warning(
            "plus 上下文文档超上限 %d（workspace=%s, all_docs=%s），按最近优先截断",
            MAX_PLUS_CONTEXT_DOCS,
            workspace_id,
            all_docs,
        )
        docs = docs[:MAX_PLUS_CONTEXT_DOCS]
    return docs


async def answer_question_plus_streamed(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID,
    user: User,
    question: str,
    history: list[tuple[str, str]] | None = None,
    doc_ids: list[uuid.UUID] | None = None,
    all_docs: bool = False,
    skill_ids: list[uuid.UUID] | None = None,
    attachment_keys: list[str] | None = None,
    interactive: bool = False,
    use_original_docs: bool = False,
):
    """聊天+ 流式问答生成器：复刻 Claude Desktop 直连体验。

    yield Stage / ThinkingChunk / TokenChunk / AnswerResult / OutputFilesResult。
    """
    # ── 构建 Skill 系统提示（逐个校验权限，防前端绕过）─────────────
    skill_system: str | None = None
    bundle_skills: list = []  # 带附属文件（bundle_key）的 skill，稍后解包到工作目录
    if skill_ids:
        from app.models.skill import Skill, SkillAuditLog
        from app.services.skill_service import check_skill_access

        skills_result = await session.execute(
            select(Skill).where(Skill.id.in_(skill_ids))
        )
        candidate_skills = skills_result.scalars().all()
        # 只保留当前用户有 read 权限的 Skill（admin 绕过；公开/创建者/被授权组）
        skill_objs = []
        for s in candidate_skills:
            if await check_skill_access(session, user=user, skill=s, level="read"):
                skill_objs.append(s)
                if s.bundle_key:
                    bundle_skills.append(s)
            else:
                logger.warning(
                    "plus 拒绝无权限 Skill user=%s skill=%s ws=%s",
                    user.id, s.id, workspace_id,
                )
        if skill_objs:
            skill_sections = [f"### {s.name}\n{s.content}" for s in skill_objs]
            skill_system = "## Active Skills\n" + "\n---\n".join(skill_sections)
            for s in skill_objs:
                session.add(
                    SkillAuditLog(
                        id=uuid.uuid4(),
                        workspace_id=workspace_id,
                        skill_id=s.id,
                        user_id=user.id,
                        action="used_in_chat",
                        detail={"question_len": len(question)},
                    )
                )
            await session.commit()

    # 注：「Skill 制作器」等内置能力改用 Claude CLI 原生 Skills 机制
    # （镜像内预置 ~/.claude/skills/skill-writer/SKILL.md），此处不再注入。

    # ── 交互模式：仅开关开时注入 ask-user 协议（Skill 在前，协议追加在最后）──
    # 协议放最后确保模型在完成 Skill 执行后仍能回到交互决策流程，不会被 Skill 内容覆盖。
    if interactive:
        skill_system = (
            ASK_USER_PROTOCOL
            if skill_system is None
            else f"{skill_system}\n\n---\n\n{ASK_USER_PROTOCOL}"
        )

    # ── 可选：引用工作区文档（需选定工作区 + 勾选文档/所有文件，均限量）──
    # 两种模式：
    #   use_original_docs=False（默认）：注入截断的 content_text 摘录到 prompt；
    #   use_original_docs=True：把原始文件拷进 workdir/context/ 供 Claude 直接读全文
    #     （见下方工作目录块，不再注入摘录）。
    context_block = ""
    original_docs: list = []  # use_original_docs 时待拷贝的文档
    if workspace_id is not None and (doc_ids or all_docs):
        docs = await _load_context_docs(
            session, workspace_id=workspace_id, doc_ids=doc_ids, all_docs=all_docs
        )
        if use_original_docs:
            original_docs = docs
        else:
            ctx_lines = []
            for doc in docs:
                if doc.content_text:
                    ctx_lines.append(f"\n## {doc.title}\n{doc.content_text[:_DOC_CONTEXT_CHARS]}")
            if ctx_lines:
                scope = "本空间最近的文档" if all_docs else "用户选定的参考文档"
                context_block = (
                    f"以下是{scope}（共 {len(ctx_lines)} 篇，请在需要时参考其内容）：\n"
                    + "\n".join(ctx_lines)
                    + "\n\n---\n\n"
                )

    # ── 准备每会话持久工作目录和附件（与工作区解耦）──────────────
    storage = get_storage()
    dir_prefix = f"chatplus/conv_{conversation_id}"
    workdir = await storage.resolve_dir(dir_prefix)

    attach_names: list[str] = []
    if attachment_keys:
        for key in attachment_keys:
            path = await storage.open_path(key)
            dest = workdir / path.name
            shutil.copy2(str(path), str(dest))
            attach_names.append(path.name)

    # ── use_original_docs：把选中文档的原始文件拷到 workdir/context/ ──────
    # 必须在 pre_files 快照之前；context/ 已在 _list_workdir_files 内排除（不算输出）。
    doc_names: list[str] = []
    if original_docs:
        ctx_dir = workdir / _CONTEXT_DIR
        ctx_dir.mkdir(parents=True, exist_ok=True)
        used_names: set[str] = set()
        for i, doc in enumerate(original_docs):
            try:
                src = await storage.open_path(doc.storage_key)
            except Exception:  # noqa: BLE001
                logger.warning("原始文档读取失败 doc=%s key=%s", doc.id, doc.storage_key)
                continue
            fname = _safe_doc_filename(doc.title, fallback=f"doc-{i + 1}")
            # 重名加序号，避免覆盖
            if fname in used_names:
                stem, dot, ext = fname.partition(".")
                fname = f"{stem}-{i + 1}{dot}{ext}"
            used_names.add(fname)
            try:
                shutil.copy2(str(src), str(ctx_dir / fname))
            except OSError:
                logger.warning("原始文档拷贝失败 doc=%s -> %s", doc.id, fname)
                continue
            doc_names.append(fname)

    # ── 解包带附属文件的 Skill bundle 到 workdir/skills/<slug>/ ──────
    # 必须在 pre_files 快照之前完成，否则会被误判为「本轮生成的输出文件」。
    bundle_notes: list[str] = []
    for s in bundle_skills:
        try:
            raw = await storage.read_bytes(s.bundle_key)
        except Exception:  # noqa: BLE001
            logger.warning("skill bundle 读取失败 skill=%s key=%s", s.id, s.bundle_key)
            continue
        sub = workdir / "skills" / _slug(s.name)
        sub.mkdir(parents=True, exist_ok=True)
        extracted = _extract_bundle(raw, sub)
        if extracted:
            rel = f"skills/{_slug(s.name)}"
            files_txt = "、".join(extracted[:20]) + ("…" if len(extracted) > 20 else "")
            bundle_notes.append(f"「{s.name}」附属文件在 {rel}/ 目录下：{files_txt}")

    # 工作目录提示：Agent 的 cwd 即会话目录，创建文件用相对路径即落在这里
    workdir_note = (
        "\n\n你当前的工作目录已设置好，可直接用相对路径创建/读取文件"
        "（生成的文件会自动提供给用户下载）。"
    )
    if attach_names:
        listing = "、".join(attach_names)
        workdir_note += f"\n工作目录中已有用户上传的附件：{listing}。"
    if doc_names:
        listing = "、".join(doc_names)
        workdir_note += (
            f"\n用户引用的原始文档已放入 {_CONTEXT_DIR}/ 目录，请直接读取分析其完整内容："
            f"{listing}。"
        )
    if bundle_notes:
        workdir_note += (
            "\n所选 Skill 随附了可用的脚本/资源文件，可直接读取或执行："
            + "；".join(bundle_notes)
            + "。"
        )

    hist_text = _format_history(history)
    prompt = f"{context_block}{hist_text}\n\n{question}{workdir_note}".strip()

    # 运行前快照（递归，含子目录；含历史轮次已生成的文件），diff 得出本轮新增。
    # skills/ 注入目录已在 _list_workdir_files 内排除。
    pre_files = _list_workdir_files(workdir)

    yield Stage("thinking", "stage_thinking_phase2")
    # 聊天+ 固定用 Claude CLI：需要文件读写/工作目录能力，
    # 不受「对话引擎」设置（openai_compat 无这些能力）影响。
    # 传入用户邮箱，供 CLI hook 在拦截 env 读取时写入安全审计。
    engine = get_engine("claude_cli", audit_user=user.email)

    try:
        if hasattr(engine, "complete_streaming"):
            from app.engine.base import TextChunk as EngineTextChunk
            from app.engine.base import ThinkingChunk as EngineThinkingChunk

            text_chunks: list[str] = []
            async for chunk in engine.complete_streaming(
                prompt,
                system=skill_system,
                cwd=workdir,
            ):
                if isinstance(chunk, EngineThinkingChunk):
                    yield ThinkingChunk(text=chunk.text)
                elif isinstance(chunk, EngineTextChunk):
                    text_chunks.append(chunk.text)
                    yield TokenChunk(text=chunk.text)
            answer = "".join(text_chunks).strip()
        else:
            r = await engine.complete(prompt, system=skill_system, cwd=workdir)
            answer = r.text.strip()
    except EngineError as exc:
        logger.error("plus engine 调用失败 workspace=%s: %s", workspace_id, exc)
        yield Stage("done", "stage_done")
        yield AnswerResult(
            answer="engine_unavailable", sources=[], error_key="engine_unavailable"
        )
        return

    # ── 检测本轮新增的输出文件（递归 diff，含子目录如 outputs/x.xlsx）────
    # 文件已持久落在会话目录；relpath 为相对工作目录的 POSIX 路径（可含 /）。
    post_files = _list_workdir_files(workdir)
    new_files = sorted(post_files - pre_files)
    output_files: list[dict] = []
    for relpath in new_files:
        output_files.append({
            # filename 展示用 basename；relpath 用于下载定位（可含子目录）
            "filename": relpath.rsplit("/", 1)[-1],
            "relpath": relpath,
            "storage_key": f"{dir_prefix}/{relpath}",
            "conversation_id": str(conversation_id),
        })

    error_key: str | None = None if answer else "no_answer"
    yield Stage("done", "stage_done")
    yield AnswerResult(answer=answer, sources=[], error_key=error_key)
    if output_files:
        yield OutputFilesResult(files=output_files)
