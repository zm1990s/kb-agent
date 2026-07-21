"""系统设置路由（管理员）。当前含引擎（LLM 后端）选择和平台品牌配置。"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user, require_admin
from app.models.auth import User
from app.services.settings_service import (
    ENGINE_CATALOG,
    MODEL_CHAT_KEY,
    MODEL_CLASSIFY_KEY,
    MODEL_CODEX_CHAT_KEY,
    MODEL_CODEX_CLASSIFY_KEY,
    MODEL_CODEX_TITLE_KEY,
    MODEL_CODEX_WHATSNEW_KEY,
    MODEL_TITLE_KEY,
    MODEL_WHATSNEW_KEY,
    PROMPT_CATALOG,
    TASK_HEADERS_CHAT_KEY,
    TASK_HEADERS_CLASSIFY_KEY,
    TASK_HEADERS_TITLE_KEY,
    TASK_HEADERS_WHATSNEW_KEY,
    WHATSNEW_FREQ_DAYS,
    EngineNotAvailableError,
    InvalidPromptError,
    get_case_default_workspace_id,
    get_chat_engine_backend,
    get_chat_file_retention_days,
    get_download_url_ttl_sec,
    get_engine_backend,
    get_engine_idle_timeout_sec,
    get_jwt_expire_min,
    get_max_upload_mb,
    get_openai_api_key,
    get_openai_base_url,
    get_openai_model,
    get_prompt,
    get_require_email_verification,
    get_setting,
    get_smtp_from,
    get_smtp_host,
    get_smtp_password,
    get_smtp_port,
    get_smtp_tls,
    get_smtp_user,
    get_suggested_questions,
    get_task_headers,
    get_task_model,
    get_whatsnew_freq,
    get_whatsnew_hour,
    get_workspace_suggested_questions,
    list_prompt_history,
    rollback_prompt,
    set_case_default_workspace_id,
    set_chat_engine_backend,
    set_chat_file_retention_days,
    set_download_url_ttl_sec,
    set_engine_backend,
    set_engine_idle_timeout_sec,
    set_jwt_expire_min,
    set_max_upload_mb,
    set_openai_api_key,
    set_openai_base_url,
    set_openai_model,
    set_prompt,
    set_require_email_verification,
    set_setting,
    set_smtp_from,
    set_smtp_host,
    set_smtp_password,
    set_smtp_port,
    set_smtp_tls,
    set_smtp_user,
    set_suggested_questions,
    set_task_headers,
    set_task_model,
    set_whatsnew_freq,
    set_whatsnew_hour,
    set_workspace_suggested_questions,
)
from app.services.usage_service import record_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


class EngineOptionOut(BaseModel):
    id: str
    label: str
    available: bool


class EngineConfigOut(BaseModel):
    current: str
    options: list[EngineOptionOut]


class EngineConfigIn(BaseModel):
    backend: str


@router.get("/engine", response_model=EngineConfigOut)
async def get_engine_config(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> EngineConfigOut:
    current = await get_engine_backend(session)
    return EngineConfigOut(
        current=current,
        options=[
            EngineOptionOut(id=e.id, label=e.label, available=e.available)
            for e in ENGINE_CATALOG
        ],
    )


@router.put("/engine", response_model=EngineConfigOut)
async def update_engine_config(
    body: EngineConfigIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> EngineConfigOut:
    try:
        await set_engine_backend(session, body.backend)
    except EngineNotAvailableError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "该引擎不可用或未实现"
        ) from exc
    current = await get_engine_backend(session)
    logger.info("audit admin set_engine admin=%s backend=%s", admin.id, body.backend)
    await record_event(session, action="admin_set_engine", user_id=admin.id,
                       meta={"backend": body.backend})
    return EngineConfigOut(
        current=current,
        options=[
            EngineOptionOut(id=e.id, label=e.label, available=e.available)
            for e in ENGINE_CATALOG
        ],
    )


# ── 平台品牌配置 ────────────────────────────────────────────


class BrandingOut(BaseModel):
    name: str
    logo_url: str


class BrandingIn(BaseModel):
    name: str | None = None
    logo_url: str | None = None

    @field_validator("logo_url")
    @classmethod
    def validate_logo_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("/")):
            raise ValueError("logo_url 须以 http://、https:// 或 / 开头")
        return v


BRANDING_NAME_KEY = "branding_name"
BRANDING_LOGO_KEY = "branding_logo_url"
DEFAULT_NAME = "KB-Agent"
DEFAULT_LOGO = ""


@router.get("/branding", response_model=BrandingOut)
async def get_branding(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BrandingOut:
    """任意登录用户可读（NavBar 用）。"""
    name = await get_setting(session, BRANDING_NAME_KEY) or DEFAULT_NAME
    logo_url = await get_setting(session, BRANDING_LOGO_KEY) or DEFAULT_LOGO
    return BrandingOut(name=name, logo_url=logo_url)


# ── 提示词管理 ────────────────────────────────────────────────


class PromptOut(BaseModel):
    key: str
    label: str
    description: str
    value: str
    required_placeholders: list[str]


class PromptIn(BaseModel):
    value: str


class PromptHistoryOut(BaseModel):
    id: int
    prompt_key: str
    version: int
    value: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/prompts", response_model=list[PromptOut])
async def get_prompts(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[PromptOut]:
    result = []
    for tpl in PROMPT_CATALOG:
        value = await get_prompt(session, tpl.key)
        result.append(
            PromptOut(
                key=tpl.key,
                label=tpl.label,
                description=tpl.description,
                value=value,
                required_placeholders=tpl.required_placeholders,
            )
        )
    return result


@router.put("/prompts/{key}", response_model=PromptOut)
async def update_prompt(
    key: str,
    body: PromptIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PromptOut:
    tpl = next((p for p in PROMPT_CATALOG if p.key == key), None)
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "未知提示词 key")
    try:
        await set_prompt(session, key, body.value)
    except InvalidPromptError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    value = await get_prompt(session, key)
    logger.info("audit admin update_prompt admin=%s key=%s", admin.id, key)
    await record_event(session, action="admin_update_prompt", user_id=admin.id,
                       meta={"key": key})
    return PromptOut(
        key=tpl.key,
        label=tpl.label,
        description=tpl.description,
        value=value,
        required_placeholders=tpl.required_placeholders,
    )


@router.put("/prompts/{key}/reset", response_model=PromptOut)
async def reset_prompt(
    key: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PromptOut:
    """恢复默认提示词（删除 DB 中的覆盖值）。"""
    tpl = next((p for p in PROMPT_CATALOG if p.key == key), None)
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "未知提示词 key")
    from app.models.settings import AppSetting
    row = await session.get(AppSetting, key)
    if row is not None:
        await session.delete(row)
        await session.commit()
    logger.info("audit admin reset_prompt admin=%s key=%s", admin.id, key)
    await record_event(session, action="admin_reset_prompt", user_id=admin.id,
                       meta={"key": key})
    return PromptOut(
        key=tpl.key,
        label=tpl.label,
        description=tpl.description,
        value=tpl.default,
        required_placeholders=tpl.required_placeholders,
    )


@router.get("/prompts/{key}/history", response_model=list[PromptHistoryOut])
async def get_prompt_history(
    key: str,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[PromptHistoryOut]:
    if not any(p.key == key for p in PROMPT_CATALOG):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "未知提示词 key")
    rows = await list_prompt_history(session, key)
    return [PromptHistoryOut.model_validate(r) for r in rows]


class RollbackIn(BaseModel):
    version: int


@router.post("/prompts/{key}/rollback", response_model=PromptOut)
async def rollback_prompt_version(
    key: str,
    body: RollbackIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PromptOut:
    tpl = next((p for p in PROMPT_CATALOG if p.key == key), None)
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "未知提示词 key")
    try:
        value = await rollback_prompt(session, key, body.version)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    logger.info("audit admin rollback_prompt admin=%s key=%s version=%d",
                admin.id, key, body.version)
    await record_event(session, action="admin_rollback_prompt", user_id=admin.id,
                       meta={"key": key, "version": body.version})
    return PromptOut(
        key=tpl.key,
        label=tpl.label,
        description=tpl.description,
        value=value,
        required_placeholders=tpl.required_placeholders,
    )


# ── 新动态定时配置 ────────────────────────────────────────────


class WhatsnewScheduleOut(BaseModel):
    hour: int
    frequency: str
    frequency_options: list[str]


class WhatsnewScheduleIn(BaseModel):
    hour: int | None = None
    frequency: str | None = None


async def _get_schedule_out(session: AsyncSession) -> WhatsnewScheduleOut:
    return WhatsnewScheduleOut(
        hour=await get_whatsnew_hour(session),
        frequency=await get_whatsnew_freq(session),
        frequency_options=list(WHATSNEW_FREQ_DAYS.keys()),
    )


@router.get("/whatsnew-schedule", response_model=WhatsnewScheduleOut)
async def get_whatsnew_schedule(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WhatsnewScheduleOut:
    return await _get_schedule_out(session)


@router.put("/whatsnew-schedule", response_model=WhatsnewScheduleOut)
async def update_whatsnew_schedule(
    body: WhatsnewScheduleIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WhatsnewScheduleOut:
    if body.hour is not None:
        try:
            await set_whatsnew_hour(session, body.hour)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if body.frequency is not None:
        try:
            await set_whatsnew_freq(session, body.frequency)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    logger.info(
        "audit admin set_whatsnew_schedule admin=%s hour=%s freq=%s",
        admin.id, body.hour, body.frequency,
    )
    await record_event(
        session,
        action="admin_set_whatsnew_schedule",
        user_id=admin.id,
        meta={"hour": body.hour, "frequency": body.frequency},
    )
    return await _get_schedule_out(session)


# ── 聊天+ 文件保留期 ──────────────────────────────────────────


class ChatFileRetentionOut(BaseModel):
    days: int


class ChatFileRetentionIn(BaseModel):
    days: int


@router.get("/chat-file-retention", response_model=ChatFileRetentionOut)
async def get_chat_file_retention(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ChatFileRetentionOut:
    return ChatFileRetentionOut(days=await get_chat_file_retention_days(session))


@router.put("/chat-file-retention", response_model=ChatFileRetentionOut)
async def update_chat_file_retention(
    body: ChatFileRetentionIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ChatFileRetentionOut:
    try:
        await set_chat_file_retention_days(session, body.days)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    logger.info("audit admin set_chat_file_retention admin=%s days=%d", admin.id, body.days)
    await record_event(
        session,
        action="admin_set_chat_file_retention",
        user_id=admin.id,
        meta={"days": body.days},
    )
    return ChatFileRetentionOut(days=await get_chat_file_retention_days(session))


# ── 引导问题 ─────────────────────────────────────────────────


class SuggestedQuestionsOut(BaseModel):
    questions: list[str]


class SuggestedQuestionsIn(BaseModel):
    questions: list[str]


@router.get("/suggested-questions", response_model=SuggestedQuestionsOut)
async def get_suggested_questions_endpoint(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SuggestedQuestionsOut:
    """任意登录用户可读（chat 页用）。"""
    return SuggestedQuestionsOut(questions=await get_suggested_questions(session))


@router.put("/suggested-questions", response_model=SuggestedQuestionsOut)
async def update_suggested_questions(
    body: SuggestedQuestionsIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SuggestedQuestionsOut:
    questions = await set_suggested_questions(session, body.questions)
    logger.info("audit admin update_suggested_questions admin=%s count=%d", admin.id, len(questions))
    await record_event(session, action="admin_update_suggested_questions", user_id=admin.id,
                       meta={"count": len(questions)})
    return SuggestedQuestionsOut(questions=questions)


@router.get("/workspaces/{workspace_id}/suggested-questions", response_model=SuggestedQuestionsOut)
async def get_ws_suggested_questions(
    workspace_id: str,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SuggestedQuestionsOut:
    """登录用户均可读；空间未配置时回退全局默认。"""
    qs = await get_workspace_suggested_questions(session, workspace_id)
    if qs is None:
        qs = await get_suggested_questions(session)
    return SuggestedQuestionsOut(questions=qs)


@router.put("/workspaces/{workspace_id}/suggested-questions", response_model=SuggestedQuestionsOut)
async def update_ws_suggested_questions(
    workspace_id: str,
    body: SuggestedQuestionsIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SuggestedQuestionsOut:
    """仅管理员可写。"""
    questions = await set_workspace_suggested_questions(session, workspace_id, body.questions)
    logger.info("audit admin update_ws_suggested_questions ws=%s count=%d", workspace_id, len(questions))
    await record_event(session, action="admin_update_ws_suggested_questions", user_id=admin.id,
                       meta={"workspace_id": workspace_id, "count": len(questions)})
    return SuggestedQuestionsOut(questions=questions)


# ── 任务级模型配置 ─────────────────────────────────────────────

_TASK_MODEL_LABELS: dict[str, str] = {
    MODEL_CLASSIFY_KEY: "文档归类模型",
    MODEL_CHAT_KEY: "对话问答模型",
    MODEL_WHATSNEW_KEY: "新动态摘要模型",
    MODEL_TITLE_KEY: "会话标题模型",
    MODEL_CODEX_CLASSIFY_KEY: "文档归类模型",
    MODEL_CODEX_CHAT_KEY: "对话问答模型",
    MODEL_CODEX_WHATSNEW_KEY: "新动态摘要模型",
    MODEL_CODEX_TITLE_KEY: "会话标题模型",
}

# 每个 key 归属的引擎（前端按此过滤）
_TASK_MODEL_ENGINE: dict[str, str] = {
    MODEL_CLASSIFY_KEY: "claude_cli",
    MODEL_CHAT_KEY: "claude_cli",
    MODEL_WHATSNEW_KEY: "claude_cli",
    MODEL_TITLE_KEY: "claude_cli",
    MODEL_CODEX_CLASSIFY_KEY: "codex",
    MODEL_CODEX_CHAT_KEY: "codex",
    MODEL_CODEX_WHATSNEW_KEY: "codex",
    MODEL_CODEX_TITLE_KEY: "codex",
}


class TaskModelOut(BaseModel):
    key: str
    label: str
    model: str | None
    engine: str = "claude_cli"


class TaskModelsOut(BaseModel):
    default_model: str
    tasks: list[TaskModelOut]


class TaskModelIn(BaseModel):
    model: str | None = None


@router.get("/models", response_model=TaskModelsOut)
async def get_task_models(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> TaskModelsOut:
    from app.core.config import get_settings
    default = get_settings().claude_model
    tasks = []
    for key, label in _TASK_MODEL_LABELS.items():
        tasks.append(TaskModelOut(
            key=key,
            label=label,
            model=await get_task_model(session, key),
            engine=_TASK_MODEL_ENGINE.get(key, "claude_cli"),
        ))
    return TaskModelsOut(default_model=default, tasks=tasks)


@router.put("/models/{key}", response_model=TaskModelOut)
async def update_task_model(
    key: str,
    body: TaskModelIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> TaskModelOut:
    if key not in _TASK_MODEL_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "未知任务模型 key")
    try:
        await set_task_model(session, key, body.model or "")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    logger.info("audit admin update_task_model admin=%s key=%s model=%s",
                admin.id, key, body.model)
    await record_event(session, action="admin_update_task_model", user_id=admin.id,
                       meta={"key": key, "model": body.model})
    return TaskModelOut(
        key=key,
        label=_TASK_MODEL_LABELS[key],
        model=await get_task_model(session, key),
    )


@router.put("/branding", response_model=BrandingOut)
async def update_branding(
    body: BrandingIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BrandingOut:
    if body.name is not None:
        await set_setting(session, BRANDING_NAME_KEY, body.name.strip() or DEFAULT_NAME)
    if body.logo_url is not None:
        await set_setting(session, BRANDING_LOGO_KEY, body.logo_url.strip())
    name = await get_setting(session, BRANDING_NAME_KEY) or DEFAULT_NAME
    logo_url = await get_setting(session, BRANDING_LOGO_KEY) or DEFAULT_LOGO
    logger.info("audit admin update_branding admin=%s name=%s", admin.id, body.name)
    await record_event(session, action="admin_update_branding", user_id=admin.id,
                       meta={"name": body.name, "logo_url": body.logo_url})
    return BrandingOut(name=name, logo_url=logo_url)


# ── 邮箱验证配置 ──────────────────────────────────────────────────────────────

class EmailVerificationOut(BaseModel):
    require_email_verification: bool


class EmailVerificationIn(BaseModel):
    require_email_verification: bool | None = None


@router.get("/email-verification", response_model=EmailVerificationOut)
async def get_email_verification_config(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> EmailVerificationOut:
    return EmailVerificationOut(
        require_email_verification=await get_require_email_verification(session),
    )


@router.put("/email-verification", response_model=EmailVerificationOut)
async def update_email_verification_config(
    body: EmailVerificationIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> EmailVerificationOut:
    if body.require_email_verification is not None:
        await set_require_email_verification(session, body.require_email_verification)
        logger.info(
            "audit admin set_require_email_verification admin=%s enabled=%s",
            admin.id, body.require_email_verification,
        )
        if body.require_email_verification:
            # 开启验证时，将历史存量未验证用户全部标记为已验证（豁免），
            # 避免他们在重新开启后被拦住登录
            from sqlalchemy import update as sa_update  # noqa: I001
            from app.models.auth import User as UserModel
            await session.execute(
                sa_update(UserModel)
                .where(UserModel.email_verified == False)  # noqa: E712
                .values(email_verified=True)
            )
            await session.commit()
            logger.info("audit admin email_verification_grandfathered admin=%s", admin.id)
    return EmailVerificationOut(
        require_email_verification=await get_require_email_verification(session),
    )


# ── 对话引擎配置 ──────────────────────────────────────────────────────────────


class ChatEngineConfigOut(BaseModel):
    chat_engine_backend: str
    openai_base_url: str
    openai_api_key: str  # 非空时脱敏返回 "***"
    openai_model: str


class ChatEngineConfigIn(BaseModel):
    chat_engine_backend: str
    openai_base_url: str = ""
    openai_api_key: str = ""  # 空字符串表示不更新已有 key
    openai_model: str = ""


@router.get("/chat-engine", response_model=ChatEngineConfigOut)
async def get_chat_engine_config(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ChatEngineConfigOut:
    raw_key = await get_openai_api_key(session)
    return ChatEngineConfigOut(
        chat_engine_backend=await get_chat_engine_backend(session),
        openai_base_url=await get_openai_base_url(session),
        openai_api_key="***" if raw_key else "",
        openai_model=await get_openai_model(session),
    )


@router.put("/chat-engine", response_model=ChatEngineConfigOut)
async def update_chat_engine_config(
    body: ChatEngineConfigIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ChatEngineConfigOut:
    try:
        await set_chat_engine_backend(session, body.chat_engine_backend)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if body.openai_base_url:
        await set_openai_base_url(session, body.openai_base_url)
    # 空字符串不覆盖已有 key（允许只改 model 而不动 key）
    if body.openai_api_key:
        await set_openai_api_key(session, body.openai_api_key)
    if body.openai_model:
        await set_openai_model(session, body.openai_model)
    logger.info(
        "audit admin update_chat_engine admin=%s backend=%s",
        admin.id, body.chat_engine_backend,
    )
    await record_event(
        session, action="admin_update_chat_engine", user_id=admin.id,
        meta={"backend": body.chat_engine_backend},
    )
    raw_key = await get_openai_api_key(session)
    return ChatEngineConfigOut(
        chat_engine_backend=await get_chat_engine_backend(session),
        openai_base_url=await get_openai_base_url(session),
        openai_api_key="***" if raw_key else "",
        openai_model=await get_openai_model(session),
    )


# ── 任务级请求 Headers ────────────────────────────────────────────────────────

_TASK_KEY_MAP = {
    "classify": TASK_HEADERS_CLASSIFY_KEY,
    "title":    TASK_HEADERS_TITLE_KEY,
    "chat":     TASK_HEADERS_CHAT_KEY,
    "whatsnew": TASK_HEADERS_WHATSNEW_KEY,
}


class TaskHeadersOut(BaseModel):
    classify: dict[str, str]
    title:    dict[str, str]
    chat:     dict[str, str]
    whatsnew: dict[str, str]


class TaskHeadersUpdateIn(BaseModel):
    headers: dict[str, str]


@router.get("/task-headers", response_model=TaskHeadersOut)
async def get_task_headers_config(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> TaskHeadersOut:
    return TaskHeadersOut(
        classify=await get_task_headers(session, TASK_HEADERS_CLASSIFY_KEY),
        title=await get_task_headers(session, TASK_HEADERS_TITLE_KEY),
        chat=await get_task_headers(session, TASK_HEADERS_CHAT_KEY),
        whatsnew=await get_task_headers(session, TASK_HEADERS_WHATSNEW_KEY),
    )


@router.put("/task-headers/{task}", response_model=TaskHeadersOut)
async def update_task_headers(
    task: str,
    body: TaskHeadersUpdateIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> TaskHeadersOut:
    if task not in _TASK_KEY_MAP:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"未知任务类型: {task!r}，有效值: {list(_TASK_KEY_MAP)}"
        )
    await set_task_headers(session, _TASK_KEY_MAP[task], body.headers)
    logger.info("audit admin update_task_headers admin=%s task=%s", admin.id, task)
    await record_event(
        session, action="admin_update_task_headers", user_id=admin.id, meta={"task": task}
    )
    return TaskHeadersOut(
        classify=await get_task_headers(session, TASK_HEADERS_CLASSIFY_KEY),
        title=await get_task_headers(session, TASK_HEADERS_TITLE_KEY),
        chat=await get_task_headers(session, TASK_HEADERS_CHAT_KEY),
        whatsnew=await get_task_headers(session, TASK_HEADERS_WHATSNEW_KEY),
    )


# ── 运行时可调配置（安全 + 存储 + 引擎超时） ─────────────────────────────────


class RuntimeConfigOut(BaseModel):
    jwt_expire_min: int
    max_upload_mb: int
    download_url_ttl_sec: int
    engine_idle_timeout_sec: int


class RuntimeConfigIn(BaseModel):
    jwt_expire_min: int | None = None
    max_upload_mb: int | None = None
    download_url_ttl_sec: int | None = None
    engine_idle_timeout_sec: int | None = None


async def _get_runtime_config_out(session: AsyncSession) -> RuntimeConfigOut:
    return RuntimeConfigOut(
        jwt_expire_min=await get_jwt_expire_min(session),
        max_upload_mb=await get_max_upload_mb(session),
        download_url_ttl_sec=await get_download_url_ttl_sec(session),
        engine_idle_timeout_sec=await get_engine_idle_timeout_sec(session),
    )


@router.get("/runtime-config", response_model=RuntimeConfigOut)
async def get_runtime_config(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RuntimeConfigOut:
    return await _get_runtime_config_out(session)


@router.put("/runtime-config", response_model=RuntimeConfigOut)
async def update_runtime_config(
    body: RuntimeConfigIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RuntimeConfigOut:
    try:
        if body.jwt_expire_min is not None:
            await set_jwt_expire_min(session, body.jwt_expire_min)
        if body.max_upload_mb is not None:
            await set_max_upload_mb(session, body.max_upload_mb)
        if body.download_url_ttl_sec is not None:
            await set_download_url_ttl_sec(session, body.download_url_ttl_sec)
        if body.engine_idle_timeout_sec is not None:
            await set_engine_idle_timeout_sec(session, body.engine_idle_timeout_sec)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    logger.info("audit admin update_runtime_config admin=%s", admin.id)
    await record_event(
        session, action="admin_update_runtime_config", user_id=admin.id,
        meta={
            "jwt_expire_min": body.jwt_expire_min,
            "max_upload_mb": body.max_upload_mb,
            "download_url_ttl_sec": body.download_url_ttl_sec,
            "engine_idle_timeout_sec": body.engine_idle_timeout_sec,
        },
    )
    return await _get_runtime_config_out(session)


# ── SMTP 配置 ────────────────────────────────────────────────────────────────

_SMTP_MASKED = "***"


class SmtpConfigOut(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str  # 已设置时返回 "***"，未设置时返回 ""
    smtp_from: str
    smtp_tls: bool


class SmtpConfigIn(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None  # 传 "" 表示清空，传 "***" 表示不改变
    smtp_from: str | None = None
    smtp_tls: bool | None = None


async def _get_smtp_config_out(session: AsyncSession) -> SmtpConfigOut:
    password = await get_smtp_password(session)
    return SmtpConfigOut(
        smtp_host=await get_smtp_host(session),
        smtp_port=await get_smtp_port(session),
        smtp_user=await get_smtp_user(session),
        smtp_password=_SMTP_MASKED if password else "",
        smtp_from=await get_smtp_from(session),
        smtp_tls=await get_smtp_tls(session),
    )


@router.get("/smtp", response_model=SmtpConfigOut)
async def get_smtp_config(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SmtpConfigOut:
    return await _get_smtp_config_out(session)


@router.put("/smtp", response_model=SmtpConfigOut)
async def update_smtp_config(
    body: SmtpConfigIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SmtpConfigOut:
    try:
        if body.smtp_host is not None:
            await set_smtp_host(session, body.smtp_host)
        if body.smtp_port is not None:
            await set_smtp_port(session, body.smtp_port)
        if body.smtp_user is not None:
            await set_smtp_user(session, body.smtp_user)
        if body.smtp_password is not None and body.smtp_password != _SMTP_MASKED:
            await set_smtp_password(session, body.smtp_password)
        if body.smtp_from is not None:
            await set_smtp_from(session, body.smtp_from)
        if body.smtp_tls is not None:
            await set_smtp_tls(session, body.smtp_tls)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    logger.info("audit admin update_smtp_config admin=%s", admin.id)
    await record_event(
        session, action="admin_update_smtp_config", user_id=admin.id,
        meta={"smtp_host": body.smtp_host, "smtp_port": body.smtp_port},
    )
    return await _get_smtp_config_out(session)


# ── Case 录入默认保存空间（管理员） ─────────────────────────────────────────


class CaseWorkspaceOut(BaseModel):
    workspace_id: str | None
    workspace_name: str | None


class CaseWorkspaceIn(BaseModel):
    workspace_id: str


@router.get("/case-default-workspace", response_model=CaseWorkspaceOut)
async def get_case_default_workspace(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CaseWorkspaceOut:
    """返回 Case 录入的默认保存空间；未配置返回 null。"""
    import uuid as _uuid

    from app.models.auth import Workspace

    ws_id = await get_case_default_workspace_id(session)
    if not ws_id:
        return CaseWorkspaceOut(workspace_id=None, workspace_name=None)
    name: str | None = None
    try:
        ws = await session.get(Workspace, _uuid.UUID(ws_id))
        name = ws.name if ws is not None else None
    except (ValueError, TypeError):
        name = None
    return CaseWorkspaceOut(workspace_id=ws_id, workspace_name=name)


@router.put("/case-default-workspace", response_model=CaseWorkspaceOut)
async def update_case_default_workspace(
    body: CaseWorkspaceIn,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CaseWorkspaceOut:
    """管理员设置 Case 录入的默认保存空间；校验空间存在。"""
    import uuid as _uuid

    from app.models.auth import Workspace

    try:
        ws = await session.get(Workspace, _uuid.UUID(body.workspace_id))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法空间 ID") from exc
    if ws is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "空间不存在")
    await set_case_default_workspace_id(session, body.workspace_id)
    logger.info("audit admin set_case_default_workspace admin=%s ws=%s", admin.id, body.workspace_id)
    await record_event(
        session, action="admin_set_case_default_workspace", user_id=admin.id,
        meta={"workspace_id": body.workspace_id},
    )
    return CaseWorkspaceOut(workspace_id=body.workspace_id, workspace_name=ws.name)
