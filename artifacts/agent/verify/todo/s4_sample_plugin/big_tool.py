#!/usr/bin/env python
"""样例扩展工具：输出 512 KiB —— 用来验证**输出上限被真强制**（截断 + 标记，不是只写进 schema）。"""

from __future__ import annotations

import json
import sys


def main() -> int:
    sys.stdin.readline()
    payload = "x" * (512 * 1024)
    print(json.dumps({"text": payload, "error": False, "code": None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
