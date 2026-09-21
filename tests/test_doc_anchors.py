"""`<文件>:<行号>` **锚点守卫**：文档里引用的行号必须与源码实况一致。

**为什么要有它（2026-09-20 实测事故）**：我在 `ui.py` / `document.py` 里加了几行（`selected_spans`
形参与校验块），**忘了重取锚点**，结果 8 份文档里几十处 `file:line` 全部失真 —— 当时我还**误报**
"锚点未动"（只核了 `document.py` 的三个，没核 `ui.py`）。零行漂移纪律靠人眼显然不可靠 ⇒ 用本
测试机械守住**最常被引用的那些符号**。

**规则**：源码一动、锚点没跟着重取，本测试先红。此时只有两条正路 ——
① 把改动压成**等量替换**（若行数没变，锚点自然仍对）；② 按纪律**重取全部受影响锚点**并在文档
里更新（顺带在变更记录里报告 old→new）。**不许**把本测试的期望值改成"实际值"了事。
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

#: (源码文件, 该行应含的符号前缀, 引用了它的文档们)
ANCHORS: list[tuple[str, str, list[str]]] = [
    ("src/memoria/presentation/api/ui.py", "def _agent_kb", ["docs/design/agent-capabilities.md"]),
    (
        "src/memoria/presentation/api/ui.py",
        "def agent_session_delete",
        [
            "docs/design/agent-capabilities.md",
            "docs/design/agent-plugin-design.md",
            "docs/reference/agent-guide/10-data-layout-and-host-embedding.md",
        ],
    ),
    (
        "src/memoria/presentation/api/ui.py",
        "def agent_session_rename",
        ["docs/reference/agent-guide/10-data-layout-and-host-embedding.md"],
    ),
    (
        "src/memoria/presentation/api/ui.py",
        "def agent_ask_cancel",
        ["docs/reference/agent-guide/10-data-layout-and-host-embedding.md"],
    ),
    (
        "src/memoria/presentation/api/ui.py",
        "def agent_usage_stats",
        ["docs/reference/agent-guide/10-data-layout-and-host-embedding.md"],
    ),
    (
        "src/memoria/services/document.py",
        "def save_document",
        [
            "docs/conventions/docs-management.md",
            "docs/design/agent-capabilities.md",
            "docs/design/agent-plugin-design.md",
            "docs/reference/hard-constraints.md",
            "docs/reference/agent-guide/README.md",
            "docs/reference/agent-guide/10-data-layout-and-host-embedding.md",
        ],
    ),
    (
        "src/memoria/services/document.py",
        "def confirm_kp_range",
        ["docs/design/agent-capabilities.md", "docs/design/agent-plugin-design.md"],
    ),
    ("src/memoria/services/document.py", "def update_kp", ["docs/design/agent-plugin-design.md"]),
    ("src/memoria/services/document.py", "def rename_kp_id", ["docs/design/agent-plugin-design.md"]),
    (
        "src/memoria/services/document.py",
        "def detach_link_instance",
        ["docs/design/agent-capabilities.md", "docs/design/agent-plugin-design.md"],
    ),
    (
        "src/memoria/services/document.py",
        "def apply_link_instances",
        ["docs/design/agent-capabilities.md", "docs/design/agent-plugin-design.md"],
    ),
    (
        "src/memoria/services/document.py",
        "def wrap_text_as_link",
        ["docs/design/agent-plugin-design.md"],
    ),
    ("src/memoria/services/document.py", "def validate_kb", ["docs/design/agent-capabilities.md"]),
    (
        "src/memoria/services/link_text_search.py",
        "def scan_link_text_matches",
        ["docs/design/agent-capabilities.md"],
    ),
]


def _symbol_line(rel_source: str, symbol: str) -> int:
    lines = (_ROOT / rel_source).read_text(encoding="utf-8").split("\n")
    for idx, line in enumerate(lines, start=1):
        if line.strip().startswith(symbol):
            return idx
    raise AssertionError(f"{rel_source} 里找不到符号：{symbol}")


@pytest.mark.parametrize(("rel_source", "symbol", "docs"), ANCHORS, ids=[a[1] for a in ANCHORS])
def test_documented_anchor_matches_source(rel_source: str, symbol: str, docs: list[str]) -> None:
    """文档里的 `<文件>:<行号>` 必须等于该符号**当前**所在行。"""
    real = _symbol_line(rel_source, symbol)
    basename = Path(rel_source).name
    anchor = f"{basename}:{real}"
    for doc in docs:
        text = (_ROOT / doc).read_text(encoding="utf-8")
        assert anchor in text, (
            f"{doc} 里找不到锚点 {anchor}（{symbol} 现在在第 {real} 行）—— "
            "源码改动打破了既有的 `<文件>:<行号>` 引用：请压成等量替换，或按纪律重取锚点并更新文档"
        )
