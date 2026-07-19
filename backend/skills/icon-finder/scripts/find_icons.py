#!/usr/bin/env python3
"""搜索图标（iconfont 优先，自动降级 Iconify），打印候选供选择。

用法：
    python find_icons.py "<关键词>" [--limit N] [--source auto|iconfont|iconify]

输出每个候选的 index / source / id / name（不打印完整 SVG，避免刷屏）。
选中后用 save_icon.py 保存并转 PNG。
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request

# 本平台内网代理接口（容器内直连后端，无需鉴权）
API = "http://localhost:8000/icons/search"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--source", default="auto", choices=["auto", "iconfont", "iconify"])
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

    items = data.get("items", [])
    print(f"来源: {data.get('source_used')}  结果数: {len(items)}\n")
    for i, it in enumerate(items):
        print(f"[{i}] {it['source']:8} id={it['id']:<24} name={it['name']}")
    if not items:
        print("（无结果，换个关键词试试，或用英文）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
