#!/usr/bin/env python
"""样例扩展工具：故意睡很久 —— 用来验证**超时被真强制**（子进程被终止，不是只写进 schema）。"""

from __future__ import annotations

import json
import sys
import time


def main() -> int:
    sys.stdin.readline()
    time.sleep(30)
    print(json.dumps({"text": "不该走到这里（超时应该已经终止我）"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
