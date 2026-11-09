"""E35 主预览钉子：lexer/parser 不得把货币 `$` 配对成行内公式。

`markdown-preview.js` 只服务链接小窗/助手预览；主预览走 `P.parse` +
`surface/render-core.js` 的 MATH_INLINE。若 lexer 把 `价格 $5 元 到 $10 元`
配对成公式，主预览仍会排版成数学。本文件用真实前端模块跑 AST 断言。

同时保留带空格公式 `$ n $`（仓库 KB 大量使用），不能因为修货币而误伤。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_JS = _ROOT / "src" / "memoria" / "ui" / "static" / "app" / "js"

_NODE_PROBE = r"""
globalThis.window = globalThis;
const path = require("path");
const base = process.argv[1];
require(path.join(base, "ast.js"));
require(path.join(base, "lexer.js"));
require(path.join(base, "parser.js"));
require(path.join(base, "source-gen.js"));
const P = window.MemoriaParser;
function walk(n, out) {
  if (!n) return;
  if (n.type === "math_inline") out.push(n.formula);
  (n.children || []).forEach((c) => walk(c, out));
}
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = {};
for (const [name, body] of Object.entries(cases)) {
  const doc = P.parseDocument ? P.parseDocument(body) : P.parseBlocks([body]);
  const formulas = [];
  (doc.blocks || doc).forEach((b) => walk(b, formulas));
  out[name] = formulas;
}
process.stdout.write(JSON.stringify(out));
"""


_CASES = {
    "currency_range": "价格 $5 元 到 $10 元",
    "currency_then_formula": "价格 $5 元，公式 $x$ 成立",
    "padded_formula": "有 $ n $ 个样本",
    "padded_formula_two": "矩阵 $ X $（$ n \\times d $）",
    "normal_inline": "$x$",
    "escaped_currency": "价格 \\$5 元",
}


@pytest.fixture(scope="module")
def probe() -> dict[str, list[str]]:
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过 lexer AST 断言")
    done = subprocess.run(
        [node, "-e", _NODE_PROBE, str(_JS)],
        input=json.dumps(_CASES, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert done.returncode == 0, f"lexer/parser 跑不起来：{done.stderr}"
    return json.loads(done.stdout)


def test_currency_pair_is_not_math(probe: dict[str, list[str]]) -> None:
    assert probe["currency_range"] == [], "两个货币 $ 不得配对成行内公式"


def test_currency_does_not_steal_later_formula(probe: dict[str, list[str]]) -> None:
    assert probe["currency_then_formula"] == ["x"], "货币 $ 之后的真公式必须保留"


def test_padded_formula_still_parses(probe: dict[str, list[str]]) -> None:
    assert probe["padded_formula"] == [" n "]
    assert probe["padded_formula_two"] == [" X ", " n \\times d "]


def test_normal_and_escaped(probe: dict[str, list[str]]) -> None:
    assert probe["normal_inline"] == ["x"]
    assert probe["escaped_currency"] == [], "\\$ 不得被当成公式"
