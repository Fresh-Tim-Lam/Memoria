#!/usr/bin/env python
"""样例第三方扩展工具（**属于插件自己，不在 Memoria 核心**）。

协议（v1 `kind: "stdio"`）：
    stdin  ← 一行 JSON：{"v":1,"tool":"ext.kb_stats","arguments":{...},"kb_path":"<abs>"}
    stdout → 一行 JSON：{"text":"...", "error": false, "code": null}

本工具演示：第三方**不改 `registry.py` 本体**也能新增工具 —— 它只读库、算几个统计数字。
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    request = json.loads(sys.stdin.readline() or "{}")
    kb_path = str(request.get("kb_path") or "")
    arguments = request.get("arguments") or {}
    pattern = str(arguments.get("glob") or "**/*.md")

    docs = 0
    lines = 0
    headings = 0
    for root, dirs, files in os.walk(kb_path):
        dirs[:] = [d for d in dirs if d not in (".git", ".memoria", "node_modules")]
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            docs += 1
            with open(os.path.join(root, name), encoding="utf-8", errors="replace") as fh:
                for row in fh:
                    lines += 1
                    if row.lstrip().startswith("#"):
                        headings += 1

    text = f"扩展工具 ext.kb_stats（插件自带实现）：{docs} 篇 md / {lines} 行 / {headings} 个标题行（pattern={pattern}）"
    print(json.dumps({"text": text, "error": False, "code": None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
