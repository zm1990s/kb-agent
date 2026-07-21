#!/usr/bin/env python3
"""保存选中图标：取 SVG → 存工作目录 → 转 PNG（供 pptx 插图）。

用法：
    python save_icon.py "<关键词>" --id <图标id> [--source auto|iconfont|iconify]
                         [--out-name <文件名，不含扩展名>] [--size 512]
                         [--color "#RRGGBB"]

- 用与搜索相同的关键词 + id 精确定位候选（find_icons.py 打印的 id）。
- SVG 存 icons/<name>.svg，PNG 存 icons/<name>.png（512×512 透明底）。
- 打印生成的 PNG 相对路径，Agent 生成 pptx 时用它 add_picture。
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import cairosvg

API = "http://localhost:8000/icons/search"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")
    return s or "icon"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--id", required=True, help="find_icons.py 打印的图标 id")
    ap.add_argument("--source", default="auto", choices=["auto", "iconfont", "iconify"])
    ap.add_argument("--out-name", default=None)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--color", default=None, help="替换 currentColor 的填充色，如 #2563eb")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    qs = urllib.parse.urlencode(
        {"q": args.query, "limit": args.limit, "source": args.source}
    )
    try:
        with urllib.request.urlopen(f"{API}?{qs}", timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print(f"搜索失败: {e}", file=sys.stderr)
        return 1

    match = next((it for it in data.get("items", []) if str(it["id"]) == str(args.id)), None)
    if match is None:
        print(f"未找到 id={args.id} 的图标（请先用 find_icons.py 确认 id）", file=sys.stderr)
        return 1

    svg = match["svg"]
    # SVG 常用 currentColor 表示随文字色；转 PNG 前替换成指定色，否则默认黑
    fill = args.color or "#000000"
    svg = svg.replace("currentColor", fill)

    out_dir = Path("icons")
    out_dir.mkdir(exist_ok=True)
    base = _slug(args.out_name or match["name"])
    svg_path = out_dir / f"{base}.svg"
    png_path = out_dir / f"{base}.png"

    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(png_path),
        output_width=args.size,
        output_height=args.size,
    )

    print(f"已保存:\n  SVG: {svg_path}\n  PNG: {png_path}  ({args.size}x{args.size})")
    print(f"\n在 pptx 中插入: slide.shapes.add_picture('{png_path}', left, top, ...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
