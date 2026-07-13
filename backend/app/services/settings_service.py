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
WHATSNEW_HOUR_KEY = "whatsnew_schedule_hour"
WHATSNEW_HOUR_DEFAULT = 2  # 凌晨 2 点

WHATSNEW_FREQ_KEY = "whatsnew_schedule_freq"
WHATSNEW_FREQ_DEFAULT = "weekly"
WHATSNEW_FREQ_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
}

# ── 提示词默认值（移到此处作为唯一真相源，service 和 API 共用） ──────────

CLASSIFY_PROMPT_KEY = "classify_prompt"
TITLE_PROMPT_KEY = "title_prompt"
ANSWER_PROMPT_KEY = "answer_prompt"
ANSWER_FETCH_PROMPT_KEY = "answer_fetch_prompt"
WHATSNEW_PROMPT_KEY = "whatsnew_prompt"

DEFAULT_CLASSIFY_PROMPT = """你是知识库文档归类助手。请阅读随附文件，输出一个 JSON 对象，包含以下字段：
- "category": 从下列候选分类中选最匹配的一个名称（若都不合适填 null）：{categories}
- "brief": 2-3 句话的简明介绍，说明这份文档是什么、覆盖什么内容、适合什么场景查阅（面向非专家读者，不超过 60 字）
- "summary": 200 字以内的详细中文摘要（含主要技术要点/操作步骤概述）
- "tags": 3-6 个关键词字符串数组
- "content_text": 文件的正文内容，以 Markdown 格式输出（保留标题层级、列表、表格等结构；用于全文检索与展示，尽量完整）

重要：输出必须是合法 JSON。content_text 内若含双引号，必须转义为 \"；含换行符必须转义为 \\n。只输出 JSON，不要多余解释。"""

DEFAULT_TITLE_PROMPT = "请为以下对话内容生成一个简短标题（5-10个中文字，不加引号或标点）：\n\n{message}"

DEFAULT_ANSWER_FETCH_PROMPT = """你是企业知识库的智能问答助手。
当前时间：{timestamp}

下面是本知识库中所有文档的索引。每条格式为：
[编号] 标题：… | 分类：… | 标签：…
    上传：YYYY-MM-DD | 摘要：…

重要说明：
- "上传：" 后面的日期是该文档实际入库日期，是真实数据，不是格式占位符。
- 当用户询问"最近""过去一周""本月"等时间相关问题时，必须将每篇文档的上传日期与当前时间对比，得出结论，不得以"索引中无日期信息"为由拒绝回答。

请判断：仅凭这些摘要信息，能否准确回答用户的问题？
- 如果摘要已足够，直接给出完整回答。
- 如果需要查阅某些文档的原文才能准确回答，列出需要的文档编号，不要猜测内容。
{history}
用户问题：{question}

文档索引：
{catalog}

请只输出一个 JSON 对象，二选一：
方案A（摘要已够用）：{{"mode": "answer", "answer": "Markdown 回答", "doc_numbers": [相关文档编号]}}
方案B（需要原文）：{{"mode": "fetch", "fetch_numbers": [需要原文的文档编号列表]}}
不要输出 JSON 以外的内容。"""

DEFAULT_ANSWER_PROMPT = """你是企业知识库的智能问答助手。
当前时间：{timestamp}

下面是本知识库中所有文档的索引，每条格式为：
[编号] 标题：… | 分类：… | 标签：…
    上传：YYYY-MM-DD | 摘要：…
以及你请求获取的部分文档原文。请综合索引和原文，给出准确完整的回答。
{history}
用户问题：{question}

文档索引：
{catalog}
{fulltext}
请只输出一个 JSON 对象，格式：
{{"answer": "给用户看的 Markdown 回答", "doc_numbers": [相关文档的编号数组]}}
不要输出 JSON 以外的内容。"""


DEFAULT_WHATSNEW_PROMPT = """你是企业知识库的文档动态播报助手。
当前时间：{timestamp}

以下是「{workspace_name}」空间在 {period} 新增的文档列表（共 {doc_count} 篇），每条格式为：
[编号] 标题：… | 分类：… | 标签：…
    上传：YYYY-MM-DD | 摘要：…

{documents}

请以 Markdown 格式输出本周期的文档动态摘要，要求：
1. 首先用 1-2 句话概括本期新增文档的整体情况（涉及哪些主题/领域）
2. 按文档分类或主题分组，逐条介绍每篇文档的核心价值和适用场景（每条 1-2 句话）
3. 如有时间分布规律（如集中在某周上传），可简要提及
4. 语言简洁专业，适合在通知/公告页面阅读
5. 不要重复列出文档标题（文档链接由系统单独展示），聚焦在内容价值上

只输出 Markdown 正文，不要加额外的标题或分隔线。"""


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
        description="Agent 读取文档原文后执行归类、生成摘要和标签时使用的提示词。必须包含 {categories}（分类名列表）占位符。",
        default=DEFAULT_CLASSIFY_PROMPT,
        required_placeholders=["{categories}"],
    ),
    PromptTemplate(
        key=TITLE_PROMPT_KEY,
        label="会话标题提示词",
        description="用户发出第一条消息后，Agent 自动生成会话标题时使用的提示词。必须包含 {message} 占位符（运行时替换为用户的第一条消息）。",
        default=DEFAULT_TITLE_PROMPT,
        required_placeholders=["{message}"],
    ),
    PromptTemplate(
        key=WHATSNEW_PROMPT_KEY,
        label="新动态摘要提示词",
        description="定时任务为每个空间生成「新动态」摘要时使用的提示词。必须包含 {workspace_name}、{period}、{doc_count}、{documents}、{timestamp} 五个占位符。",
        default=DEFAULT_WHATSNEW_PROMPT,
        required_placeholders=["{workspace_name}", "{period}", "{doc_count}", "{documents}", "{timestamp}"],
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


# ── 新动态定时配置 ───────────────────────────────────────────

async def get_whatsnew_hour(session: AsyncSession) -> int:
    """返回新动态摘要生成的整点小时（0-23）。"""
    stored = await get_setting(session, WHATSNEW_HOUR_KEY)
    try:
        return int(stored) if stored is not None else WHATSNEW_HOUR_DEFAULT
    except ValueError:
        return WHATSNEW_HOUR_DEFAULT


async def set_whatsnew_hour(session: AsyncSession, hour: int) -> None:
    if not 0 <= hour <= 23:
        raise ValueError("hour 须在 0-23 之间")
    await set_setting(session, WHATSNEW_HOUR_KEY, str(hour))


async def get_whatsnew_freq(session: AsyncSession) -> str:
    """返回新动态摘要生成频率（daily/weekly/biweekly/monthly）。"""
    stored = await get_setting(session, WHATSNEW_FREQ_KEY)
    if stored in WHATSNEW_FREQ_DAYS:
        return stored
    return WHATSNEW_FREQ_DEFAULT


async def set_whatsnew_freq(session: AsyncSession, freq: str) -> None:
    if freq not in WHATSNEW_FREQ_DAYS:
        raise ValueError(f"freq 须为 {list(WHATSNEW_FREQ_DAYS.keys())} 之一")
    await set_setting(session, WHATSNEW_FREQ_KEY, freq)
