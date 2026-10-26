"""task-156 Step3 真机夹具：有序列表（未从 1 起）+ 引用内有序列列表。

docs/q.md（CRLF）：
```
# 有序列表保号 step3 探针

> 前言
> 10. ten
> 11. eleven
> 12. twelve

10. flat ten
11. flat eleven
```
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "artifacts" / "agent" / "verify" / "todo" / "quote-list-step3-fixture"
KB = OUT / "kb"

LINES = [
    "# 有序列表保号 step3 探针",
    "",
    "> 前言",
    "> 10. ten",
    "> 11. eleven",
    "> 12. twelve",
    "",
    "10. flat ten",
    "11. flat eleven",
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
