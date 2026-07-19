"""图标搜索 schema（iconfont / Iconify 双源）。"""

from pydantic import BaseModel


class IconItem(BaseModel):
    source: str  # "iconfont" | "iconify"
    id: str  # iconfont 的数字 id 或 iconify 的 "prefix:name"
    name: str
    svg: str  # 完整可用的 SVG 文本
    preview: str | None = None  # 预览图 URL（iconfont 有，iconify 无）


class IconSearchResponse(BaseModel):
    source_used: str  # 实际使用的源（auto 降级后可能与请求不同）
    items: list[IconItem]
