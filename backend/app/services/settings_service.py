"""应用设置业务逻辑。当前用于引擎（LLM 后端）选择和提示词管理。

引擎目录：Claude CLI 已实现；Codex / OpenClaw 预留占位（未实现，前端灰显）。
选择持久化在 app_settings，重启仍生效。
"""

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.prompt_history import PromptHistory
from app.models.settings import AppSetting

ENGINE_KEY = "engine_backend"

# ── 提示词默认值（移到此处作为唯一真相源，service 和 API 共用） ──────────

CLASSIFY_PROMPT_KEY = "classify_prompt"
TITLE_PROMPT_KEY = "title_prompt"
ANSWER_PROMPT_KEY = "answer_prompt"
ANSWER_FETCH_PROMPT_KEY = "answer_fetch_prompt"

DEFAULT_CLASSIFY_PROMPT = """你是知识库文档归类助手。请阅读随附文件，输出一个 JSON 对象，包含以下字段：
- "category": 从下列候选分类中选最匹配的一个名称（若都不合适填 null）：{categories}
- "brief": 2-3 句话的简明介绍，说明这份文档是什么、覆盖什么内容、适合什么场景查阅（面向非专家读者，不超过 60 字）
- "summary": 200 字以内的详细中文摘要（含主要技术要点/操作步骤概述）
- "tags": 3-6 个关键词字符串数组
- "content_text": 文件的正文内容，以 Markdown 格式输出（保留标题层级、列表、表格等结构；用于全文检索与展示，尽量完整）

当前处理时间：{timestamp}
只输出 JSON，不要多余解释。"""

DEFAULT_TITLE_PROMPT = "请为以下对话内容生成一个简短标题（5-10个中文字，不加引号或标点）：\n\n{message}"

DEFAULT_ANSWER_FETCH_PROMPT = """你是企业知识库的智能问答助手。\
下面是本知识库中所有文档的索引（编号、标题、分类、标签、摘要）。
当前时间：{timestamp}

请判断：仅凭这些摘要信息，能否准确回答用户的问题？
- 如果摘要已足够，直接给出完整回答。
- 如果需要查阅某些文档的原文才能准确回答，列出需要的文档编号，不要猜测内容。
- 如果用户问及时间相关的内容（如"最近""本月""最新"），请结合当前时间和文档的上传日期（在索引中体现）判断。
{history}
用户问题：{question}

文档索引：
{catalog}

请只输出一个 JSON 对象，二选一：
方案A（摘要已够用）：{{"mode": "answer", "answer": "Markdown 回答", "doc_numbers": [相关文档编号]}}
方案B（需要原文）：{{"mode": "fetch", "fetch_numbers": [需要原文的文档编号列表]}}
不要输出 JSON 以外的内容。"""

DEFAULT_ANSWER_PROMPT = """你是企业知识库的智能问答助手。\
下面是本知识库中所有文档的索引（编号、标题、分类、标签、摘要），\
以及你请求获取的部分文档原文。请综合索引和原文，给出准确完整的回答。
当前时间：{timestamp}
{history}
用户问题：{question}

文档索引：
{catalog}
{fulltext}
请只输出一个 JSON 对象，格式：
{{"answer": "给用户看的 Markdown 回答", "doc_numbers": [相关文档的编号数组]}}
不要输出 JSON 以外的内容。"""


@dataclass(frozen=True)
class PromptTemplate:
    key: str
    label: str
    description: str
    default: str
    required_placeholders: list[str] = field(default_factory=list)


PROMPT_CATALOG: list[PromptTemplate] = [
    PromptTemplate(
        key=ANSWER_FETCH_PROMPT_KEY,
        label="对话问答提示词（第一阶段：判断是否需要原文）",
        description="Agent 先用摘要索引判断能否回答。摘要够用则直接输出答案；否则声明需要哪些文档原文（返回 fetch 模式）。必须包含 {question}、{catalog}、{history}。",
        default=DEFAULT_ANSWER_FETCH_PROMPT,
        required_placeholders=["{question}", "{catalog}", "{history}", "{timestamp}"],
    ),
    PromptTemplate(
        key=ANSWER_PROMPT_KEY,
        label="对话问答提示词（第二阶段：结合原文回答）",
        description="当第一阶段判断摘要不够用时，Agent 获取文档原文后使用此提示词作答。必须包含 {question}（用户问题）、{catalog}（文档索引）、{history}（对话历史）、{fulltext}（请求的文档原文）、{timestamp}（当前时间）。",
        default=DEFAULT_ANSWER_PROMPT,
        required_placeholders=["{question}", "{catalog}", "{history}", "{fulltext}", "{timestamp}"],
    ),
    PromptTemplate(
        key=CLASSIFY_PROMPT_KEY,
        label="文档索引提示词",
        description="Agent 读取文档原文后执行归类、生成摘要和标签时使用的提示词。必须包含 {categories}（分类名列表）和 {timestamp}（处理时间，格式 YYYY-MM-DD HH:MM:SS）两个占位符。",
        default=DEFAULT_CLASSIFY_PROMPT,
        required_placeholders=["{categories}", "{timestamp}"],
    ),
    PromptTemplate(
        key=TITLE_PROMPT_KEY,
        label="会话标题提示词",
        description="用户发出第一条消息后，Agent 自动生成会话标题时使用的提示词。必须包含 {message} 占位符（运行时替换为用户的第一条消息）。",
        default=DEFAULT_TITLE_PROMPT,
        required_placeholders=["{message}"],
    ),
]

_PROMPT_CATALOG_MAP = {p.key: p for p in PROMPT_CATALOG}


@dataclass(frozen=True)
class EngineOption:
    id: str
    label: str
    available: bool


# 引擎目录：唯一真相源，前端据此渲染（未实现的置灰）。
ENGINE_CATALOG: list[EngineOption] = [
    EngineOption(id="claude_cli", label="Claude CLI", available=True),
    EngineOption(id="codex", label="Codex（未实现）", available=False),
    EngineOption(id="openclaw", label="OpenClaw（未实现）", available=False),
]

_AVAILABLE_IDS = {e.id for e in ENGINE_CATALOG if e.available}


class EngineNotAvailableError(Exception):
    """选择了未实现/未知的引擎。"""


async def get_setting(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(AppSetting.value).where(AppSetting.key == key))
    return result.scalar_one_or_none()


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await session.commit()


async def get_engine_backend(session: AsyncSession) -> str:
    """当前生效的引擎后端：DB 设置优先，回退到配置默认。"""
    stored = await get_setting(session, ENGINE_KEY)
    return stored or get_settings().engine_backend


async def set_engine_backend(session: AsyncSession, backend: str) -> None:
    """设置引擎后端；仅允许 available 的引擎。"""
    if backend not in _AVAILABLE_IDS:
        raise EngineNotAvailableError(backend)
    await set_setting(session, ENGINE_KEY, backend)


# ── 提示词管理 ──────────────────────────────────────────────────────────────


class InvalidPromptError(Exception):
    """提示词缺少必须的占位符。"""


async def get_prompt(session: AsyncSession, key: str) -> str:
    """取提示词；DB 无值时返回默认值。"""
    stored = await get_setting(session, key)
    if stored:
        return stored
    tpl = _PROMPT_CATALOG_MAP.get(key)
    return tpl.default if tpl else ""


async def set_prompt(session: AsyncSession, key: str, value: str) -> None:
    """保存提示词，校验必须占位符存在，并追加历史版本。"""
    tpl = _PROMPT_CATALOG_MAP.get(key)
    if tpl is None:
        raise ValueError(f"未知提示词 key: {key}")
    for ph in tpl.required_placeholders:
        if ph not in value:
            raise InvalidPromptError(f"提示词必须包含占位符 {ph}")
    # 追加历史版本（版本号 = 当前最大版本 + 1）
    max_ver_result = await session.execute(
        select(func.max(PromptHistory.version)).where(PromptHistory.prompt_key == key)
    )
    max_ver = max_ver_result.scalar() or 0
    session.add(PromptHistory(prompt_key=key, version=max_ver + 1, value=value))
    await set_setting(session, key, value)


async def list_prompt_history(
    session: AsyncSession, key: str, limit: int = 50
) -> list[PromptHistory]:
    """取指定提示词的历史版本列表（最新在前）。"""
    result = await session.execute(
        select(PromptHistory)
        .where(PromptHistory.prompt_key == key)
        .order_by(PromptHistory.version.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_prompt_version(
    session: AsyncSession, key: str, version: int
) -> PromptHistory | None:
    """取某个提示词的指定版本。"""
    result = await session.execute(
        select(PromptHistory).where(
            PromptHistory.prompt_key == key,
            PromptHistory.version == version,
        )
    )
    return result.scalar_one_or_none()


async def rollback_prompt(session: AsyncSession, key: str, version: int) -> str:
    """回退到历史版本：重新执行 set_prompt（会产生新版本号）。"""
    row = await get_prompt_version(session, key, version)
    if row is None:
        raise ValueError(f"版本 {version} 不存在")
    await set_prompt(session, key, row.value)
    return row.value
