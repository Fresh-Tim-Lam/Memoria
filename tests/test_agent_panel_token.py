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


def test_session_reference_is_a_short_alias_and_expands_before_send():
    """会话引用在输入框里只写**别名**（不出现 34 字符会话 id），发送前展开成可解析的完整 URI。

    口径来源：用户「会话引用不需要渲染会话id，太占地方，**实际要传入**」。
    断言 ① 别名比完整 URI 短；② 同一会话复用同一别名；③ 已登记别名 / 完整 URI 都算合法、
    未登记别名不认；④ `expandSessionAliases()` 把别名换回完整 URI；⑤ 非引用文本原样不动。
    """
    src = panel_source()
    decl = re.search(r"const sessionAliasById = new Map\(\);[^\n]*\n\s*let sessionAliasSeq = 0;", src)
    assert decl is not None, "未在 agent-panel.js 找到别名登记表声明"
    prelude = (
        'const SESSION_URI_PREFIX = "dsh-session:";\n'
        "function sessionUri(id) { return SESSION_URI_PREFIX + "
        'Buffer.from(JSON.stringify(String(id)), "utf8").toString("base64url"); }\n'
        'function decodeSessionUri(uri) { const raw = String(uri || "");'
        " if (raw.indexOf(SESSION_URI_PREFIX) !== 0) return null;"
        " const p = raw.slice(SESSION_URI_PREFIX.length);"
        ' if (!/^[A-Za-z0-9_-]+$/.test(p)) return null;'
        ' try { return JSON.parse(Buffer.from(p, "base64url").toString("utf8")); } catch (e) { return null; } }\n'
        + decl.group(0)
        + "\n"
    )
    fns = "\n".join(
        extract_function(name)
        for name in (
            "sessionAliasFor",
            "sessionAliasUri",
            "sessionAliasOrUriOk",
            "expandSessionAliases",
        )
    )
    script = (
        prelude
        + fns
        + """
const id = "session-20260918T163014Z-8ac06ed5";
const full = Buffer.from(JSON.stringify(id), "utf8").toString("base64url");
const uri = sessionAliasUri(id);
const text = "@[" + "上一轮会话" + "](" + uri + "#seq:3-7) 总结";
console.log(JSON.stringify({
  uri: uri,
  again: sessionAliasUri(id),
  shorter: uri.length < ("dsh-session:" + full).length,
  aliasOk: sessionAliasOrUriOk("s1"),
  unknownOk: sessionAliasOrUriOk("s9"),
  fullOk: sessionAliasOrUriOk(full),
  expanded: expandSessionAliases(text),
  expandedHasId: expandSessionAliases(text).indexOf(full) >= 0,
  expandedStillShortAlias: expandSessionAliases(text).indexOf("dsh-session:s1") >= 0,
  plain: expandSessionAliases("没有引用的纯文本"),
}));
"""
    )
    out = node_eval(script)
    assert out["uri"] == "dsh-session:s1"
    assert out["again"] == out["uri"]  # 同一会话复用同一别名
    assert out["shorter"] is True
    assert out["aliasOk"] is True
    assert out["unknownOk"] is False  # 未登记别名不认（不猜）
    assert out["fullOk"] is True  # 完整 URI 仍认（历史文本 / 旧 token）
    assert out["expandedHasId"] is True and out["expandedStillShortAlias"] is False
    assert out["plain"] == "没有引用的纯文本"
    # 接线（静态断言，防"函数写了但没接上"）：① 两处会话 token 拼写都走别名 URI；
    # ② 发送路径先把别名展开成完整 URI（发后端 / 落盘 / 气泡渲染都用展开后的文本）
    assert "sessionAliasUri(id)" in extract_function("formatSessionMentionToken")
    assert "sessionAliasUri(id)" in extract_function("sessionFragmentToken")
    assert 'const text = expandSessionAliases(((input && input.value) || "").trim());' in src


def test_session_fragment_token_carries_message_char_range():
    """对话栏里拖拽选取「某次回复内的一段」⇒ token 带**消息内字符区间**（`#seq:3c12-3c48`）。

    口径来源：用户「一次回复内信息不是结构化的吗，拖拽选取的时候选不到某次回复内的内容起止么」
    ⇒ 选 C（渲染也做可寻址结构）。字符位 = **1 起闭区间**，与文件引用 `#L3C2-L5C7` 同一套；
    只在两端都拿得到时才写（缺一端 / 倒置 ⇒ 退回整条，不半猜）。
    """
    src = panel_source()
    fns = "\n".join(extract_function(name) for name in ("fragmentSuffix", "fragmentSpanText"))
    script = (
        fns
        + """
const suffixCases = [
  [3, null, 3, null],
  [3, null, 7, null],
  [3, 11, 3, 48],
  [3, 11, 7, 48],
  [3, null, 7, 48],
  [3, 11, 7, null],
  [3, 47, 3, 12],
  [0, 1, 0, 5],
];
const spanCases = [
  [3, null, null, null],
  [3, null, 7, null],
  [3, 12, 3, 48],
  [3, 12, 7, 48],
  [3, null, 7, 48],
];
console.log(JSON.stringify({
  suffix: suffixCases.map(c => fragmentSuffix(c[0], c[1], c[2], c[3])),
  span: spanCases.map(c => fragmentSpanText(c[0], c[1], c[2], c[3])),
}));
"""
    )
    out = node_eval(script)
    # `fragmentSuffix` 收 **0 基**偏移（`messageOffsetAt` 的产物），内部 +1 成 1 基字符位；
    # 事件 seq 本身是 **0 起**（末条正是 `#seq:0c2-0c5`）；缺一端 / 倒置 ⇒ 退回整条（不半猜）。
    assert out["suffix"] == [
        "#seq:3",
        "#seq:3-7",
        "#seq:3c12-3c48",
        "#seq:3c12-7c48",
        "#seq:3-7",
        "#seq:3-7",
        "#seq:3",
        "#seq:0c2-0c5",
    ]
    # `fragmentSpanText` 收 **1 基**字符位（token 里的原值），只负责显示成 `3:12–3:48` 这类串
    assert out["span"] == ["3", "3–7", "3:12–3:48", "3:12–7:48", "3–7:48"]
    # 接线（静态断言）：气泡渲染后**反标**消息原文偏移；选区落点把两端偏移一起传给 token 拼写
    assert "annotateMessageOffsets(el, text);" in extract_function("renderBody")
    assert "messageOffsetAt(range.startContainer, range.startOffset)" in src
    assert "sessionFragmentToken(loc.seqFrom, loc.seqTo, loc.offFrom, loc.offTo)" in src


def test_preview_annotation_wiring_is_intact() -> None:
    """预览区「源坐标」映射的接线与**不写 DOM** 不变量 —— 本轮唯一没能在 harness 里端到端驱动到的部分。

    为什么只做静态断言：该路径需要真实预览 DOM + 真实选区，而自动化上下文里 `Selection.toString()` 恒为空
    （`isCollapsed=false` 但 `String(sel).length == 0`），选区悬浮入口的前置（`selAddHit()` 读它）永远不满足
    ⇒ 预览分支驱动不到（真机可用，只是自动化测不到）。守住四条：
    ① 三支函数都在；② `selectionLocation` 的**两处**预览分支都走 `previewRangeEndpoints`（"按名调用"的副本，
       漏改一处就会出现"有时精确、有时块级"的漂移）；③ 列号一路传到 token 拼写；④ **映射过程绝不写 DOM**
       —— 首版给文本节点套 `span.-src-seg` 预打标，为此不得不加"编辑态直接返回"的守卫，而真机默认常是编辑态
       ⇒ 功能整体失效（用户报障"预览现在不能映射回去精确的字符号"）。改为按需现算后，`previewSourcePoint`
       里出现任何 `createElement` / `replaceChild` / `setAttribute` 都属回退，必须让测试挡下来。
    """
    src = panel_source()
    for name in ("edgeTextNode", "previewSourcePoint", "previewRangeEndpoints"):
        assert name in extract_function(name), f"缺少 {name}()"
    assert src.count("...previewRangeEndpoints(range, a, b)") == 2, "两处预览分支必须都走 previewRangeEndpoints"
    assert "startCol: ps ? ps.col : null" in extract_function("previewRangeEndpoints")
    point = extract_function("previewSourcePoint")
    for forbidden in ("createElement", "replaceChild", "setAttribute", "appendChild", "insertBefore"):
        assert forbidden not in point, f"预览源坐标映射不得写 DOM（发现 {forbidden}）"
    assert "data--src-line" in point and "data--src-line-end" in point, "块行区间必须取自单一事实源属性"


def test_history_row_context_menu_wiring_is_intact() -> None:
    """历史行右键菜单（重命名 / 删除）+ 悬浮提示的接线 —— 实现全在 `agent-panel.js` 的末尾追加块。

    守住四条：
    ① 五个函数都在（菜单 / 删除 / 重命名 / 行装饰 / 输入弹窗）；
    ② 菜单项**同时**有重命名与删除，且删除带 `danger`（误点保护）；两个 RPC 名必须复用既有的
       `agent_session_rename` / `agent_session_delete`（不新造并行的写入口）；
    ③ 行内 `-hist-del` 在追加块里被摘除、提示挂到**整行与标题**上 —— 菜单只能右键唤出，
       悬浮提示是唯一的发现入口（用户原话："鼠标悬浮在这些对话栏上悬浮提示右键更多操作"）；
    ④ 右键委托挂在**页签视图**上并 `stopPropagation()`：挂 `document` 的话，app.js 那条全局
       contextmenu（"目标不在菜单里就 hide"）会立刻关掉刚打开的菜单。
    """
    src = panel_source()
    for name in (
        "openHistRowMenu",
        "histDeleteWithConfirm",
        "histRename",
        "decorateHistoryRowMenu",
        "promptHistInput",
    ):
        assert name in extract_function(name), f"缺少 {name}()"

    menu = extract_function("openHistRowMenu")
    assert 'T("agent.history.rename")' in menu and 'T("agent.history.delete")' in menu
    assert "danger: true" in menu
    assert 'call("agent_session_rename", id, val, kb || null)' in extract_function("histRename")
    assert 'call("agent_session_delete", id, kb || null)' in extract_function("histDeleteWithConfirm")

    decor = extract_function("decorateHistoryRowMenu")
    assert 'row.querySelector("[data-hist-del]")' in decor and "del.remove()" in decor, "行内删除按钮须被摘除"
    assert "row.title = hint" in decor, "整行悬浮提示（菜单发现入口）"
    assert 'row.querySelector(".-hist-title")' in decor, "标题自带 title，提示须并进去才看得见"

    bind = src.split("(function bindHistRowMenu()")[1].split("})();")[0]
    assert 'view.addEventListener("contextmenu"' in bind, "右键委托必须挂在页签视图上（不是 document）"
    assert "ev.stopPropagation()" in bind, "须拦住 app.js 的全局 contextmenu，否则菜单刚开就被关掉"
    assert 'closest("[data-hist-id]")' in bind


def test_history_row_menu_i18n_keys_exist_in_both_packages() -> None:
    """新增键必须 `zh-CN` / `en` 成对（`docs/conventions/i18n.md` 规则 2），且追加在**文件末尾**。"""
    app_dir = PANEL.parents[1]  # …/ui/static/app
    for lang in ("zh-CN", "en"):
        text = (app_dir / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
        assert 'agent.historyList, {\n    rightClickMore:' in text, f"{lang}.js：rightClickMore 位置/键名不对"
        assert 'agent.history, {\n    rename:' in text, f"{lang}.js：agent.history.rename 位置/键名不对"
        for key in ("renameTitle", "renamePh", "renameFail", "deleteTitle", "deleteBody", "busyLock"):
            assert f"{key}:" in text, f"{lang}.js 缺键 {key}"
