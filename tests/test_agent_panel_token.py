"""选区 → 引用 token 的前端拼写离线单测（**跑真源码**，不是复制一份实现）。

口径来源：`docs/design/dsh-agent-port.md §6.21`（`@路径#L3C2-L5C7`，列 1 起、可只写一端）。

为什么用 `node` 实跑：token 拼写的**唯一事实源**是 `agent-panel.js::rangeTokenText()`（后端只解析），
在 Python 侧再写一遍就成了并行事实源。这里把该函数**从文件里抽出来**交给 `node` eval，断言：
① 各形态的拼写逐字正确；② 后端 `_at_range_parts()` 能逐字解回（前后端同一语法）；
③ 选区落点（`addSelectionToChat`）确实把行 **和列** 交给该函数（静态断言，防止将来漏传列号）。
`node` 不在 PATH 时整文件 skip（与 `scripts/i18n_selftest.js` 一样，前端自测依赖 node）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PANEL = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "memoria"
    / "ui"
    / "static"
    / "app"
    / "js"
    / "agent-panel.js"
)


def panel_source() -> str:
    return PANEL.read_text(encoding="utf-8")


def extract_function(name: str) -> str:
    """从 `agent-panel.js` 原文里按**花括号配平**抽出一个顶层函数声明（含 `function` 关键字）。"""
    src = panel_source()
    match = re.search(r"\n  function " + re.escape(name) + r"\(", src)
    assert match is not None, f"未在 agent-panel.js 找到函数 {name}"
    start = src.index("{", match.end() - 1)
    depth = 0
    for index in range(start, len(src)):
        if src[index] == "{":
            depth += 1
        elif src[index] == "}":
            depth -= 1
            if depth == 0:
                return src[match.start() + 1 : index + 1]
    raise AssertionError(f"函数 {name} 花括号不平衡")


def node_eval(script: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不在 PATH —— 前端 token 拼写单测跳过")
    proc = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


#: `[path, sLine, sCol, eLine, eCol] -> 期望 token`（与 §6.21 的语法表逐条对应）。
CASES = [
    ["docs/a.md", 3, 2, 5, 7, "@docs/a.md#L3C2-L5C7"],  # 行+列区间
    ["docs/a.md", 3, 2, 5, None, "@docs/a.md#L3C2-L5"],  # 混写：止端缺列（行末）
    ["docs/a.md", 3, None, 5, None, "@docs/a.md#L3-L5"],  # 无列（向后兼容）
    ["docs/a.md", 3, 5, 3, 5, "@docs/a.md#L3C5"],  # 单点（列）
    ["docs/a.md", 3, 2, 3, 7, "@docs/a.md#L3C2-L3C7"],  # 同行区间
    ["docs/a.md", 12, None, None, None, "@docs/a.md#L12"],  # 单行
    ['docs/A B.md', 3, 2, 5, 7, '@"docs/A B.md"#L3C2-L5C7'],  # 含空格路径（引号只包路径）
    ["docs/a.md", 0, None, 0, None, "@docs/a.md"],  # 取不到行号 ⇒ 退回 `@路径`（不编造）
    ["", 1, 1, 1, 1, ""],  # 无路径 ⇒ 空串
]


def test_range_token_text_emits_line_and_column():
    fn = extract_function("rangeTokenText")
    script = fn + "\nconsole.log(JSON.stringify(" + json.dumps(CASES) + ".map(a => rangeTokenText(a[0], a[1], a[2], a[3], a[4]))));"
    assert node_eval(script) == [case[5] for case in CASES]


def test_frontend_token_round_trips_through_backend_parser():
    from memoria.services.agent.tools.kb import _at_range_parts

    fn = extract_function("rangeTokenText")
    sample = [case[:5] for case in CASES[:6]]
    script = fn + "\nconsole.log(JSON.stringify(" + json.dumps(sample) + ".map(a => rangeTokenText(a[0], a[1], a[2], a[3], a[4]))));"
    tokens = node_eval(script)
    assert [_at_range_parts(token) for token in tokens] == [
        ("docs/a.md", 3, 2, 5, 7),
        ("docs/a.md", 3, 2, 5, None),
        ("docs/a.md", 3, None, 5, None),
        ("docs/a.md", 3, 5, None, None),
        ("docs/a.md", 3, 2, 3, 7),
        ("docs/a.md", 12, None, None, None),
    ]


def test_selection_path_passes_columns_into_the_formatter():
    src = panel_source()
    # 纯函数被「选区 → token」这条路径调用（且落点用 `insertSessionToken`，与 §6.20 同一条）
    assert "formatRangeMention = function (path, sLine, sCol, eLine, eCol)" in src
    assert "insertSessionToken(formatRangeMention(path, loc.startLine, loc.startCol, loc.endLine, loc.endCol))" in src
    # 列号来自源码区端点的**行内字符偏移**（只数 `.-line-content`，不数行号列）
    assert "el.closest(\".-line-content\")" in src
    assert "return { line: line, col: off + 1, lineStart: off === 0 };" in src
