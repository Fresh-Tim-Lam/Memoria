"""E35 钉子：Markdown 预览里的字面 `$` / `\\$` 不得被误吞成行内公式。

来源 = 人（2026-11-07）：「markdown 原文没法直接写$或者转义?」。

**根因（Node 实跑复现，非推断）**：`markdown-preview.js` 的 `protectMath()` 用一个
行内正则配对 `$...$`：
  - `价格 $5 元 到 $10 元`（两个孤立 `$`）被配成行内公式，渲染成 `\\(5 元 到 \\)`；
  - 正则不认识 `\\$`，转义的 `$` 还能和后面的真公式开符配对，把真公式拆坏。

修法（`markdown-preview.js`）：`protectInlineMath()` 扫描器 + `looksLikeInlineMath()`：
  - `\\$` 与代码内的 `$` 不是定界符（`\\$` 渲染成字面 `$`，不显示反斜杠）；
  - 行内公式不跨行；
  - 闭符紧跟数字 ⇒ 货币（`$5 ... $10`）；
  - 内容以数字开头、闭前有空格（或含中文）且无 TeX 记号 ⇒ 货币/散文；
  - **带空格的真公式（`$ n $`）保留**（仓库 KB 大量使用，不能用 Pandoc 的
    「开符后不得有空格」规则——那会打掉几百条既有公式，见 `git show 872148c8` 的回归）；
  - 判定为字面 `$` 的字符输出为 `<span class="-md-literal-dollar">$</span>`：MathJax 的
    `HTMLDomStrings` 会把同一元素内相邻文本节点拼成一个字符串再找定界符，只有元素边界
    才能阻止它把两个裸 `$` 再配成公式。

本文件钉四件事（全部用 node 实跑真实 `markdown-preview.js` + `vendor/marked.min.js`）：
1. 货币 `$5` / 两个孤立 `$` / 价格区间保持文本，不生成 `\\(...\\)`；
2. `\\$` 渲染成字面 `$`（无可见反斜杠、不当公式）；
3. 正常 `$x$` / `$$x$$` / `$ n $`（带空格）/ `$3 \\times 4$` 仍排版；
4. 代码（行内 code 与围栏）里的 `\\$` / `$x$` 保持原文。
"""

from __future__ import annotations

import html as _html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "src" / "memoria" / "ui" / "static" / "app"

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
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
const out = {};
for (const [name, body] of Object.entries(cases)) {
  out[name] = window.MemoriaMarkdownPreview.renderHtml(body, {
    knownTargets: new Set(),
    linkOverrides: {},
  });
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def probe() -> dict[str, str]:
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过 markdown-preview 回归")
    done = subprocess.run(
        [node, "-e", _NODE_PROBE, str(_APP)],
        input=json.dumps(_CASES, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert done.returncode == 0, f"markdown-preview 跑不起来：{done.stderr}"
    return json.loads(done.stdout)


#: 输入 → 预览 HTML（全部经真实 marked + markdown-preview）。
_CASES = {
    # ── ① 字面 $ / 货币 ──────────────────────────────────────────────────────
    "one_currency": "价格 $5 元",
    "two_currency": "价格 $5 元 到 $10 元",
    "ascii_currency": "a $5 b $10 c",
    "price_range": "$95-$180",
    "currency_then_math": "价格 $5 元，公式 $x$ 成立",
    "currency_no_space": "价格 $5元和$x$ 成立",
    "table_currency_formula": "| 价格 | $5 | $x$ |",
    # ── ② 转义 \$ ────────────────────────────────────────────────────────────
    "escaped_one": "价格 \\$5 元",
    "escaped_two": "价格 \\$5 元 到 \\$10 元",
    "escaped_math_pair": "\\$x\\$",
    "escaped_then_math": "价格 \\$5 和 $x$ 元",
    # ── ③ 正常公式（含仓库大量使用的带空格写法）───────────────────────────────
    "inline": "价格 $x$ 元",
    "padded": "有 $ n $ 个样本",
    "padded_two": "矩阵 $ X $（$ n \\times d $）",
    "tex_operator": "$3 \\times 4$",
    "digit_padded": "$1 + x $",
    "numeric_math": "$5.5$ 与 $2^n$",
    "abs_math": "范数 $|x|$",
    "display": "$$x^2$$",
    "display_block": "$$\nx^2\n$$",
    "strong_math": "**$x$**",
    # ── ④ 代码里的 $ 保持原文 ────────────────────────────────────────────────
    "inline_code_escaped": "`\\$5`",
    "inline_code_math": "`$x$`",
    "fence": "```\n\\$5\n$x$\n```",
}


def _visible(html: str) -> str:
    """预览 HTML 的可见文本（去掉标签、还原实体；去掉尚未由 MathJax 消费的 TeX 定界符）。"""
    text = _html.unescape(re.sub(r"<[^>]+>", "", html)).strip()
    return re.sub(r"\\[()\[\]]", "", text)


def _inline_math(html: str) -> list[str]:
    return re.findall(r"\\\((.+?)\\\)", html, flags=re.S)


# ── ① 字面 $ / 货币不得变成公式 ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "case,expected_text",
    [
        ("one_currency", "价格 $5 元"),
        ("two_currency", "价格 $5 元 到 $10 元"),
        ("ascii_currency", "a $5 b $10 c"),
        ("price_range", "$95-$180"),
    ],
)
def test_literal_dollars_stay_text(probe: dict, case: str, expected_text: str) -> None:
    html = probe[case]
    assert _visible(html) == expected_text, f"{case} 的字面 $ 被吞/改写了"
    assert _inline_math(html) == [], f"{case} 不应生成行内公式：{_inline_math(html)}"
    assert "\\[" not in html, f"{case} 不应生成块级公式"
    # 机制：字面 $ 必须落在独立元素里，MathJax 才无法把相邻文本节点里的两个 $ 配对
    assert 'class="-md-literal-dollar"' in html, f"{case} 缺少字面 $ 隔离元素"


def test_currency_does_not_swallow_following_formula(probe: dict) -> None:
    """`$5 元，公式 $x$`：货币 $ 不能抢走真公式的开符（旧实现在这里把整句吞成公式）。"""
    html = probe["currency_then_math"]
    assert _inline_math(html) == ["x"], f"应只剩真公式 x，实际 {_inline_math(html)}"
    assert _visible(html) == "价格 $5 元，公式 x 成立"


def test_currency_without_space_before_formula(probe: dict) -> None:
    html = probe["currency_no_space"]
    assert _inline_math(html) == ["x"], f"应只剩真公式 x，实际 {_inline_math(html)}"
    assert _visible(html).startswith("价格 $5元和"), _visible(html)


def test_table_row_keeps_currency_and_formula(probe: dict) -> None:
    """表格同一行：货币 `$5` 不能把后面的 `$x$` 开符抢走（`|` 按单元格分隔符处理）。"""
    html = probe["table_currency_formula"]
    assert _inline_math(html) == ["x"], f"应只剩真公式 x，实际 {_inline_math(html)}"
    visible = _visible(html)
    assert "价格" in visible and "$5" in visible and visible.endswith("|"), visible


# ── ② 转义 \$ 渲染成字面 $ ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case,expected_text",
    [
        ("escaped_one", "价格 $5 元"),
        ("escaped_two", "价格 $5 元 到 $10 元"),
        ("escaped_math_pair", "$x$"),
        ("escaped_then_math", "价格 $5 和 x 元"),
    ],
)
def test_escaped_dollar_is_literal_dollar(probe: dict, case: str, expected_text: str) -> None:
    html = probe[case]
    assert _visible(html) == expected_text, f"{case} 的 \\$ 没有渲染成字面 $"
    assert "\\$" not in _visible(html), f"{case} 预览仍显示反斜杠"
    assert "\\[" not in html, f"{case} 不应生成块级公式"
    if case != "escaped_then_math":
        assert _inline_math(html) == [], f"{case} 被误判成公式：{_inline_math(html)}"
    else:
        assert _inline_math(html) == ["x"]


# ── ③ 正常公式仍工作（含带空格写法——HEAD `872148c8` 的回归点）──────────────


def test_normal_inline_math(probe: dict) -> None:
    assert _inline_math(probe["inline"]) == ["x"]
    assert _visible(probe["inline"]) == "价格 x 元"


def test_space_padded_math_still_renders(probe: dict) -> None:
    """`$ n $` 是仓库 KB 的主流写法（示例库约 500 处），不能被 E35 修掉。"""
    assert _inline_math(probe["padded"]) == [" n "], _inline_math(probe["padded"])
    assert _inline_math(probe["padded_two"]) == [" X ", " n \\times d "], _inline_math(
        probe["padded_two"]
    )
    assert _inline_math(probe["digit_padded"]) == ["1 + x "]


def test_tex_operators_are_not_treated_as_currency(probe: dict) -> None:
    assert _inline_math(probe["tex_operator"]) == ["3 \\times 4"]


def test_numeric_and_absolute_value_math_still_render(probe: dict) -> None:
    assert _inline_math(probe["numeric_math"]) == ["5.5", "2^n"]
    assert _inline_math(probe["abs_math"]) == ["|x|"]


def test_display_math_still_renders(probe: dict) -> None:
    assert "\\[x^2\\]" in probe["display"]
    assert "\\[x^2\\]" in probe["display_block"]


def test_strong_wrapped_math_still_renders(probe: dict) -> None:
    html = probe["strong_math"]
    assert "<strong>" in html and _inline_math(html) == ["x"]


# ── ④ 代码里的 $ 不被改写 ───────────────────────────────────────────────────


def test_inline_code_keeps_backslash_dollar(probe: dict) -> None:
    assert "<code>\\$5</code>" in probe["inline_code_escaped"]
    assert "<code>$x$</code>" in probe["inline_code_math"]
    assert "-md-literal-dollar" not in probe["inline_code_math"]


def test_fenced_code_is_raw(probe: dict) -> None:
    html = probe["fence"]
    assert "\\$5" in html, "围栏代码里的 \\$ 必须逐字节保留"
    assert "$x$" in html, "围栏代码里的 $x$ 不得被改写"
    assert _inline_math(html) == []
