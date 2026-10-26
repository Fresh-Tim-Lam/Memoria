"""task-156 Step1 真机夹具：引用块内既有段落又有列表（跨行 child）。

docs/q.md（CRLF）：
```
# 引用内列表 step1 探针

> 前言段落一
> - q1 ten
> - q2 eleven
> 后记段落二
> - q3 twelve

> 纯段落引用（对照组）
```
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "artifacts" / "agent" / "verify" / "todo" / "quote-list-step1-fixture"
KB = OUT / "kb"

LINES = [
    "# 引用内列表 step1 探针",
    "",
    "> 前言段落一",
    "> - q1 ten",
    "> - q2 eleven",
    "> 后记段落二",
    "> - q3 twelve",
    "> 尾段段落三",
    "",
    "> 纯段落引用（对照组）",
]


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    (KB / ".memoria").mkdir(parents=True)
    (KB / "docs").mkdir()
    now = datetime.now(timezone.utc).isoformat()
    (KB / ".memoria" / "manifest.yaml").write_text(
        "schema_version: 1\nupdated_at: '%s'\nfiles: []\n" % now, encoding="utf-8")
    (KB / ".memoria" / "pending.yaml").write_text(
        "schema_version: 1\nupdated_at: '%s'\nitems: []\n" % now, encoding="utf-8")
    body = "\n".join(LINES) + "\n"
    (KB / "docs" / "q.md").write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    print("fixture:", OUT)
    for i, line in enumerate(LINES):
        print("  L%d: %r" % (i + 1, line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
