"""图标搜索代理路由（iconfont / Iconify 双源）。

- 统一出网、超时、降级与日志：skill 脚本在容器内直连本接口，不裸连外网被风控。
- iconfont 优先，报错/超时/无结果时降级 Iconify（`logger.warning` 记录切换）。
- 内网免鉴权：本 router 仅供容器内 skill 脚本调用，不经 Next.js /api 对外暴露。
  （图标搜索非敏感数据，安全边界＝能进容器才能调。）
"""

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.icon import IconItem, IconSearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/icons", tags=["icons"])

_ICONFONT_SEARCH = "https://www.iconfont.cn/api/icon/search.json"
_ICONIFY_SEARCH = "https://api.iconify.design/search"
_ICONIFY_SVG = "https://api.iconify.design/{name}.svg"
_TIMEOUT = 3.0

_ICONFONT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://www.iconfont.cn/",
    "x-requested-with": "XMLHttpRequest",
}


async def _search_iconfont(client: httpx.AsyncClient, q: str, limit: int) -> list[IconItem]:
    """调 iconfont 内部 search.json；每个图标内嵌 show_svg，直接可用。"""
    resp = await client.post(
        _ICONFONT_SEARCH,
        data={
            "q": q,
            "sortType": "updated_at",
            "page": 1,
            "pageSize": limit,
            "fromCollection": -1,
            "ctoken": "",
        },
        headers=_ICONFONT_HEADERS,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise ValueError(f"iconfont code={data.get('code')}")
    items: list[IconItem] = []
    for ic in data.get("data", {}).get("icons", []):
        svg = ic.get("show_svg") or ""
        if not svg:
            continue
        items.append(
            IconItem(
                source="iconfont",
                id=str(ic.get("id")),
                name=ic.get("name") or ic.get("font_class") or "icon",
                svg=svg,
                preview=ic.get("preview_image"),
            )
        )
    return items


async def _search_iconify(client: httpx.AsyncClient, q: str, limit: int) -> list[IconItem]:
    """调 Iconify 开放 API：先搜名字，再逐个取 SVG。"""
    resp = await client.get(_ICONIFY_SEARCH, params={"query": q, "limit": limit})
    resp.raise_for_status()
    names: list[str] = resp.json().get("icons", [])
    items: list[IconItem] = []
    for full in names[:limit]:
        try:
            svg_resp = await client.get(_ICONIFY_SVG.format(name=full))
            svg_resp.raise_for_status()
            svg = svg_resp.text
        except httpx.HTTPError as exc:
            logger.warning("iconify svg 取失败 %s: %s", full, exc)
            continue
        items.append(
            IconItem(
                source="iconify",
                id=full,
                name=full.split(":", 1)[-1],
                svg=svg,
                preview=None,
            )
        )
    return items


@router.get("/search", response_model=IconSearchResponse)
async def search_icons(
    q: str = Query(min_length=1, max_length=100),
    source: str = Query("auto", pattern="^(auto|iconfont|iconify)$"),
    limit: int = Query(20, ge=1, le=50),
) -> IconSearchResponse:
    """搜索图标。auto：iconfont 优先，报错/超时/无结果降级 Iconify（含日志）。"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        if source == "iconfont":
            try:
                items = await _search_iconfont(client, q, limit)
                return IconSearchResponse(source_used="iconfont", items=items)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("iconfont 搜索失败 q=%r: %s", q, exc)
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "iconfont 搜索失败") from exc

        if source == "iconify":
            try:
                items = await _search_iconify(client, q, limit)
                return IconSearchResponse(source_used="iconify", items=items)
            except httpx.HTTPError as exc:
                logger.warning("iconify 搜索失败 q=%r: %s", q, exc)
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "iconify 搜索失败") from exc

        # auto：iconfont 优先，失败或空结果降级 iconify
        try:
            items = await _search_iconfont(client, q, limit)
            if items:
                return IconSearchResponse(source_used="iconfont", items=items)
            logger.warning("icon search fallback iconfont→iconify: iconfont 无结果 q=%r", q)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("icon search fallback iconfont→iconify: %s q=%r", exc, q)

        try:
            items = await _search_iconify(client, q, limit)
            return IconSearchResponse(source_used="iconify", items=items)
        except httpx.HTTPError as exc:
            logger.warning("iconify 兜底也失败 q=%r: %s", q, exc)
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "图标搜索失败（两源均不可用）"
            ) from exc
