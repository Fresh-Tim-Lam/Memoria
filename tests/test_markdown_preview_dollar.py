"""E35 钉子：Markdown 预览里的字面 `$` / `\\$` 不得被误吞成行内公式。

来源 = 人（2026-11-07）：「markdown 原文没法直接写$或者转义?」。
Lead 实测 lexer/parser/source-gen 对两类输入都能逐字节往返，问题在
`markdown-preview.js` 的 `protectMath()`：它会把同一行里两个孤立 `$`
（例如 `a $5 b $10 c`）配对成 `$...$`，导致货币符号被当成公式。

修复必须同时满足：
1. 字面 `$5` / `价格 $5 元` 保持文本；
2. `\\$` 渲染成字面 `$`（不显示反斜杠、不当公式）；
3. 正常 `$x$` / `$$x$$` 仍排版。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "src" / "memoria" / "ui" / "static" / "app"
_MARKED = _APP.parent / "vendor" / "marked.min.js"

_NODE_PROBE = r"""
globalThis.window = globalThis;
globalThis.document = {
  createElement: () => ({ style: {}, setAttribute() {}, appendChild() {}, addEventListener() {} }),
  addEventListener() {},
  querySelector() { return null; },
};
const fs = require("fs");
const path = require("path");
const app = process.argv[1];
const marked = require(path.join(app, "..", "vendor", "marked.min.js"));
globalThis.marked = marked;
eval(fs.readFileSync(path.join(app, "js", "markdown-preview.js"), "utf8"));
const cases = [
  "\u4ef7\u683c $5 \u5143",
  "a $5 b $10 c",
  "\u4ef7\u683c \\$5 \u5143",
  "$x$",
  "$$x$$",
  "**$x$**",
];
const out = {};
for (const s of cases) {
  out[s] = window.MemoriaMarkdownPreview.renderHtml(s, {
    knownTargets: new Set(),
    linkOverrides: {},
  });
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过 markdown-preview 回归")
    done = subprocess.run(
        [node, "-e", _NODE_PROBE, str(_APP)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert done.returncode == 0, f"markdown-preview 跑不起来：{done.stderr}"
    return json.loads(done.stdout)


def test_currency_dollars_are_not_paired_into_math(probe: dict) -> None:
    one = probe["价格 $5 元"]
    assert "价格 $5 元" in one, "单个货币 $ 必须保持原文"
    assert "\\(" not in one and "\\[" not in one, "不得把单个 $ 变成公式"


def test_two_loose_dollars_stay_text(probe: dict) -> None:
    html = probe["a $5 b $10 c"]
    assert "a $5 b $10 c" in html, "两个孤立 $ 不得被配对成 $...$"
    assert "\\(" not in html and "\\[" not in html


def test_escaped_dollar_renders_as_literal_dollar(probe: dict) -> None:
    html = probe["价格 \\$5 元"]
    assert "价格 $5 元" in html, "\\$ 应渲染成字面 $"
    assert "\\$" not in html, "预览不得显示反斜杠"
    assert "\\(" not in html and "\\[" not in html


def test_normal_inline_and_block_math_still_render(probe: dict) -> None:
    assert "\\(x\\)" in probe["$x$"]
    assert "\\[x\\]" in probe["$$x$$"]
    assert "<strong>" in probe["**$x$**"] and "\\(x\\)" in probe["**$x$**"]
