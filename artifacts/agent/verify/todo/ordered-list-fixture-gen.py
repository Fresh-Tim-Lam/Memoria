"""task-157 真机夹具：有序列表非 1 起编号（含引用块内列表）。

docs/ord.md（CRLF）：
```
# ordered start probe

10. ten
11. eleven

3. three
4. four

> 前言段落（同一引用块内的普通段落）
> 10. qten
> 11. qeleven
```
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "artifacts" / "agent" / "verify" / "todo" / "ordered-list-fixture"
KB = OUT / "kb"

LINES = [
    "# ordered start probe",
    "",
    "10. ten",
    "11. eleven",
    "",
    "3. three",
    "4. four",
    "",
    "> 前言段落（同一引用块内的普通段落）",
    "> 10. qten",
    "> 11. qeleven",
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
    (KB / "docs" / "ord.md").write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
    print("fixture:", OUT)
    for i, line in enumerate(LINES):
        print("  L%d: %r" % (i + 1, line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
