"""行内公式里的 Markdown 活跃字符不得被当成语法：`$[a]_\\times$` + 行内链接的回归钉子。

来源 = 人（2026-11-02，带截图）：
「其中 $[a]_\\times$ 为叉积反对称矩阵。绕"过 $c$、方向 $a$"的直线旋转为
 $p\\mapsto R(p-c)+c$，其齐次矩阵平移列为 $c-Rc$（[transform.hpp](…#L185-L208)）。」
在预览里被渲染成一整段坏文本（`$a]_\\times…` / `[transform.hpp）`）。

根因（在词法器实测，可复现）：行内公式体内没有"公式模式"。公式里的 `[a]` 会走
**链接分支** `matchBracketLink()`，而它按 `](` 向后找配对 ⇒ 从公式里的 `[a]`
一路吞到本行**真正的链接** `[transform.hpp](…)`，把整句公式 + 后文变成一个
`link_open`（link 文本 = 中间所有源码）⇒ AST 里公式节点消失、链接文本错位。

修法（`lexer.js`）：`_hasUnmatched(tokens, "math_inline_open")` 为真时进入"公式
内部"分支——只有 `$`（关闭）与反斜杠转义有语法意义，其余 `[ ] _ * ~ \\` !`
一律按原文产出 token，parser 用 `token.value` 拼回 formula（escape 令牌会被
parser 还原为 `"\\"+char`，所以 `\\times` / `\\mapsto` 逐字节回写不丢反斜杠）。

本文件钉三件事：
1. **报障原句**：AST 得到 5 个 math_inline（公式原文逐一断言）+ 1 个 link（url 正确）；
2. **公式体内 Markdown 字符不外溢**：`[ ] _ * ~ \\` !` 出现在 `$…$` 内时仍是同一个公式；
3. **不误伤正常语法**：公式外的链接/强调照常解析；SourceGen 逐字节回写一致。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "src" / "memoria" / "ui" / "static" / "app"
_JS = _APP / "js"

#: 报障原句（照抄人给的 markdown，含直引号与行内链接锚点）。
_REPORTED_LINE = (
    '其中 $[a]_\\times$ 为叉积反对称矩阵。绕"过 $c$、方向 $a$"的直线旋转为 '
    '$p\\mapsto R(p-c)+c$，其齐次矩阵平移列为 $c-Rc$'
    '（[transform.hpp](../../../src/include/gfx/math/transform.hpp#L185-L208)）。'
)

#: 公式内含 Markdown 活跃字符的用例：每一句都必须只产出一个 math_inline，公式原文原样。
_MATH_CASES = {
    "bracket": "$[a]_\\times$",
    "matrix": "$[a]_{ij}$",
    "underscore_star": "$a_b * c_d$",
    "brackets_and_parens": "$x [y] (z)$",
    "set_braces": "$\\{a,b\\}$",
    "looks_like_link": "$[x](y)$",
    "tilde": "$a~b$",
    "backtick": "$`a`$",
    "bang": "$!x$",
    "pipe": "$\\left| x \\right|$",
}

#: 真实语法对照（不能被"公式模式"误伤）。
_CONTROL_CASES = {
    "plain_link": "见 [transform.hpp](path/to.hpp#L1-L2) 的定义",
    "emphasis": "这是 **粗体** 与 *斜体* 与 `code`",
    "math_then_link": "$c-Rc$（[transform.hpp](a/b.hpp#L3-L4)）",
    "two_math": "$c$ 与 $a$ 两点",
}

_NODE_PROBE = r"""
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const repo = process.argv[1];
const JS = path.join(repo, "src/memoria/ui/static/app/js");
const sandbox = { console };
sandbox.window = sandbox;
vm.createContext(sandbox);
for (const file of ["ast.js", "lexer.js", "parser.js", "source-gen.js"]) {
  vm.runInContext(fs.readFileSync(path.join(JS, file), "utf8"), sandbox, { filename: file });
}
const P = sandbox.MemoriaParser;
const G = sandbox.MemoriaSourceGen;
const cases = JSON.parse(fs.readFileSync(0, "utf8"));

function walk(nodes, out) {
  for (const node of nodes || []) {
    if (node.type === "text") { out.texts.push(node.content == null ? "" : node.content); continue; }
    if (node.type === "math_inline") { out.math.push(node.formula); continue; }
    if (node.type === "link") { out.links.push({ text: node.text, url: node.url }); continue; }
    if (node.type === "bold" || node.type === "italic" || node.type === "bold_italic") { out.emphasis.push(node.type); walk(node.children, out); continue; }
    if (node.type === "code") { out.code.push(node.code == null ? "" : node.code); continue; }
    if (node.type === "math_block") { out.mathBlock.push(node.formula); continue; }
    if (node.type === "escape") { out.texts.push("\\" + node.char); continue; }
    if (node.children) { walk(node.children, out); continue; }
  }
  return out;
}

const result = {};
for (const [name, line] of Object.entries(cases)) {
  const doc = P.parse(line);
  const collected = walk(doc.blocks, { texts: [], math: [], links: [], emphasis: [], code: [], mathBlock: [] });
  const blocks = [];
  for (const block of doc.blocks) {
    blocks.push({ type: block.type, children: walk(block.children, { texts: [], math: [], links: [], emphasis: [], code: [], mathBlock: [] }) });
  }
  const regenerated = doc.blocks.map((block) => G.generateBlock(block)).join("\n");
  result[name] = { collected, blocks, roundtrip: regenerated === line, regenerated };
}
process.stdout.write(JSON.stringify(result));
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("本机没有 node，跳过词法器数值断言")
    cases = {"reported": _REPORTED_LINE, **_MATH_CASES, **_CONTROL_CASES}
    done = subprocess.run(
        [node, "-e", _NODE_PROBE, str(_ROOT)],
        input=json.dumps(cases, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    assert done.returncode == 0, f"lexer/parser/source-gen 跑不起来：{done.stderr}"
    return json.loads(done.stdout)


def _math_of(probe: dict, case: str) -> list[str]:
    return [formula for formula in probe[case]["collected"]["math"]]


# ── ① 报障原句 ────────────────────────────────────────────────────────────────


def test_reported_line_parses_math_and_link(probe: dict) -> None:
    """一整个段落：5 个行内公式 + 1 个链接，公式原文与链接 url 逐一正确。"""
    collected = probe["reported"]["collected"]
    assert _math_of(probe, "reported") == [
        "[a]_\\times",
        "c",
        "a",
        "p\\mapsto R(p-c)+c",
        "c-Rc",
    ], "公式被吞掉或与链接互相污染"
    assert collected["links"] == [
        {"text": "transform.hpp", "url": "../../../src/include/gfx/math/transform.hpp#L185-L208"},
    ], "行内链接必须单独成为 link 节点，且 url 不被公式吞掉"
    assert probe["reported"]["roundtrip"] is True, "编辑回写必须逐字节一致"


def test_reported_line_has_no_link_swallowing_math(probe: dict) -> None:
    """反证：坏实现里整句只有一个 link_open，公式节点为 0 ⇒ 这里钉住链接数量与文本长度。"""
    links = probe["reported"]["collected"]["links"]
    assert len(links) == 1
    assert links[0]["text"] == "transform.hpp", f"链接文本被公式污染：{links[0]['text']!r}"
    # 链接文本里不允许出现公式定界符或汉字（那正是"吞掉整句"的形态）。
    assert "$" not in links[0]["text"]
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in links[0]["text"])


# ── ② 公式体内 Markdown 活跃字符不外溢 ───────────────────────────────────────


@pytest.mark.parametrize("case", sorted(_MATH_CASES))
def test_markdown_active_chars_stay_inside_inline_math(probe: dict, case: str) -> None:
    """`$[a]_\\times$` 这类公式必须仍是**一个** math_inline，且原文逐字节保留。"""
    math = _math_of(probe, case)
    assert len(math) == 1, f"{case} 应只产出一个行内公式，实际 {math}"
    assert math[0] == _MATH_CASES[case][1:-1], f"{case} 公式原文被改写"
    assert probe[case]["collected"]["links"] == [], f"{case} 公式内的 [..](..) 不应变成链接"
    assert probe[case]["roundtrip"] is True, f"{case} 回写必须逐字节一致"


# ── ③ 不误伤正常语法 ────────────────────────────────────────────────────────


def test_plain_link_still_parses(probe: dict) -> None:
    links = probe["plain_link"]["collected"]["links"]
    assert links == [{"text": "transform.hpp", "url": "path/to.hpp#L1-L2"}]
    assert probe["plain_link"]["roundtrip"] is True


def test_emphasis_and_code_still_parse(probe: dict) -> None:
    collected = probe["emphasis"]["collected"]
    assert len(collected["emphasis"]) >= 1
    assert collected["code"] == ["code"]
    assert probe["emphasis"]["roundtrip"] is True


def test_math_then_link_on_same_line(probe: dict) -> None:
    collected = probe["math_then_link"]["collected"]
    assert _math_of(probe, "math_then_link") == ["c-Rc"]
    assert collected["links"] == [{"text": "transform.hpp", "url": "a/b.hpp#L3-L4"}]
    assert probe["math_then_link"]["roundtrip"] is True


def test_two_inline_formulas_with_chinese_between(probe: dict) -> None:
    collected = probe["two_math"]["collected"]
    assert _math_of(probe, "two_math") == ["c", "a"]
    assert "".join(collected["texts"]).count("与") >= 1
    assert probe["two_math"]["roundtrip"] is True
