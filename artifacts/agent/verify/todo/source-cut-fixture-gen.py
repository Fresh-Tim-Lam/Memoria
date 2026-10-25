"""task-150 夹具：**自建 KB**（不碰 docs/example、不碰用户库），供"源码区剪切"真机取证。

产出 `artifacts/agent/verify/todo/source-cut-fixture/kb/`：
  docs/cut.md —— 8 行固定文本（单行/跨行选区都能稳定构造），LF + 单个尾换行
  docs/second.md —— 第二篇（用于"切文件不回魂"的对照，可选）
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root
OUT = ROOT / "artifacts" / "agent" / "verify" / "todo" / "source-cut-fixture"
KB = OUT / "kb"

CUT_LINES = [
    "# cut 用例（task-150）",
    "",
    "第2行：AAA-001 这一段有足够长的文字用于单行选区测试。",
    "第3行：BBB-002 这一段也有足够长的文字。",
    "第4行：CCC-003 第四行内容。",
    "第5行：DDD-004 第五行内容。",
    "第6行：EEE-005 第六行内容。",
    "第7行：FFF-006 第七行内容（末行，带尾换行）。",
]

SECOND_LINES = [
    "# 第二篇（对照）",
    "",
    "第二篇正文：SECOND-001，用于验证切文件后内容不回魂。",
    "第二篇第4行。",
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

    # **CRLF**（Windows 用户文件常态）：保存走文本模式写，LF 会被统一成 CRLF；
    # 用 CRLF 夹具才能让"保存后磁盘逐字节"有稳定期望（LF→CRLF 是 task-147 登记的相邻风险，不属本任务）。
    (KB / "docs" / "cut.md").write_bytes(("\n".join(CUT_LINES) + "\n").replace("\n", "\r\n").encode("utf-8"))
    (KB / "docs" / "second.md").write_bytes(("\n".join(SECOND_LINES) + "\n").replace("\n", "\r\n").encode("utf-8"))
    print("fixture:", OUT)
    print("cut.md lines:", len(CUT_LINES), "| second.md lines:", len(SECOND_LINES))
    for i, line in enumerate(CUT_LINES):
        print("  L%d: %r" % (i + 1, line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
