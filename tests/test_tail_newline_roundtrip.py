"""task-147（R0 数据损坏）行为守卫：`collectEditorBody()` 的尾换行保真。

跑 `scripts/benchmark/maintenance/tail_newline_roundtrip_test.js`（白盒单测：
从 app.js 按花括号配平抽取**真实源码** + node:vm + 最小 DOM 桩），
判据是**逐字节**（不是长度/计数）—— 见 task-147 与
`artifacts/agent/verify/todo/doc-body-staleness-analysis.md` §10：
任何"长度/聚合标量"判据都可能被相互抵消的变化骗过（本次 bug 就是 +1 与 −1 抵消）。

改前该单测矩阵应为 **6 FAIL / 6 PASS**（尾 `\\n\\n`、`\\n\\n\\n` 各 3 种编辑全红），
改后应为 **12 PASS**；本测试断言后者，因此它能对回归判红。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark" / "maintenance" / "tail_newline_roundtrip_test.js"


def test_collect_editor_body_restores_document_tail_newlines() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不在 PATH —— 前端尾换行单测跳过")
    proc = subprocess.run(
        [node, str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    detail = (proc.stdout or "")[-6000:] + "\n[stderr]\n" + (proc.stderr or "")[-3000:]
    assert proc.returncode == 0, "尾换行白盒单测失败：\n" + detail
    # 防止"空跑/被吞"：矩阵必须真的跑了 12 组合且无 FAIL
    assert "总组合: 12" in (proc.stdout or ""), "矩阵未跑满 12 组合：\n" + detail
    assert "FAIL: 0" in (proc.stdout or ""), "矩阵存在 FAIL：\n" + detail
