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


def test_message_actions_and_write_bar_wiring_is_intact() -> None:
    """消息**下方**的操作行 + 写入状态条（2026-09-21 第二版，人定稿）。

    人：「撤销按钮和复制按钮都放在每个对话气泡的下方，不是气泡内，或者说 agent 回复甚至不需要气泡框住」
        「用户只能在最后一次对话下方撤销」「文件修改状态可以效仿 trae 的做法，给一个状态栏可以展开」

    守五条：
    ① `pushMessage` / `renderMessages` / `finalizeMessage` 一律**包装**（重新赋值），不是改内部
       ⇒ `agent-panel.js` 上方所有 `<行号>` 锚点零漂移；
    ② 每条消息外面包一层 `.-agent-turn`，操作行 `.-agent-msg-actions` 在**气泡外面**；
    ③ 操作行里是「复制」（只给助手消息）：clipboard 优先、失焦 / 无权限时回退 `execCommand`；
    ④ 写入状态条 `.-agent-write`（可展开）**只挂最新一条助手消息**下方，撤销按钮在其中，
       且**只有撤销、没有 redo**；
    ⑤ 中英键成对，且都追加在 `i18n/*.js` 文件末尾的 `agent` 块里。
    """
    src = panel_source()
    for name in ("pushMessage", "renderMessages", "finalizeMessage"):
        assert f"const {name}Base = {name};" in src, f"{name} 必须包装（而非改内部，否则行号锚点漂移）"
        assert f"{name} = function" in src
    assert "function wrapTurn(rec, msgEl)" in src and '"-agent-turn "' in src
    assert "function actionsEl(rec)" in src and '"-agent-msg-actions"' in src
    assert 'rec.role === "user"' in src, "用户消息不加复制按钮"
    assert (
        'copy.className = "-agent-act -agent-act--icon -agent-act--copy"' in src
    ), "复制改用**图标**按钮（构造已收口到 copyButtonEl；--copy 供 syncTurnActions 识别与补齐）"
    assert "const COPY_ICON_SVG" in src and "copy.innerHTML = COPY_ICON_SVG" in src
    assert 'copy.title = T("agent.copy")' in src, "悬停提示就一个字：复制"

    assert "await navigator.clipboard.writeText(text)" in src, "优先 clipboard API"
    assert 'document.execCommand("copy")' in src, "失焦 / 无权限时必须回退 execCommand"
    assert 'T("agent.copyDone")' in src and 'T("agent.copyFail")' in src, "要给一次成败反馈"

    # 写入状态栏（**第四版**，人定稿）：从"消息下方"**搬进顶部副标题行** `.-agent-subhead`
    # （= 原 `.-agent-history` 那一行；会话名与「历史」按钮搬到 `.-agent-head`，模型名不再显示）。
    # 两态（bar / 展开）+ **文案两态**（无改动不渲染 / 已修改 N / 写入失败）；栈式 undo/redo 只在这里
    # 出现一次。**「已撤销」短显态已删除**（人 2026-09-21：「撤销之后栈状态栏就没了，我无法重做」——
    # 它把整条状态栏连同**重做入口**一起收掉；栈里只要有步骤就该显示，可用性交给 `can_undo/can_redo`）。
    assert "function renderWriteState()" in src
    assert '".-agent-write-bar"' in src, "状态栏 bar 态"
    assert "function subheadEl()" in src and 'classList.add("-agent-subhead")' in src, "history 行改名 subhead"
    assert "function restructureHeader()" in src and "head.appendChild(current)" in src, "会话名搬到 head"
    assert "model.hidden = true" in src, "不再显示模型名"
    assert "restructureHeader();" in src, "页面加载即重排顶栏（放在 IIFE 末尾 ⇒ index.html 零改动）"
    assert 'T("agent.writeIdle")' in src and 'T("agent.writeSummary"' in src, "文案（无改动 / 已修改 N）"
    assert "markWriteUndone" not in src and "writeUndone" not in src, "「已撤销」短显态不许复活（会吃掉重做入口）"
    assert "if (!writeState) return;" in src, "状态栏只由 writeState 决定去留"
    assert 'T(isRedo ? "agent.redo" : "agent.undo")' in src, "撤销 / 重做按钮文案（栈语义：一步一退 / 一进）"
    assert "function stepButton(direction, st, stack)" in src, "两个按钮共用一份实现，可用性由栈指针决定"
    assert '"-agent-write-redo"' in src and '"-agent-write-undo"' in src
    assert 'T("agent.stackPos"' in src and 'T("agent.stackStep"' in src, "bar 态显示栈位置、展开态显示轨迹"
    # 展开态**必须撑开宿主那一行**：`.-agent-history`（= subhead）被 `--bar-h-b` 钉成一行高，
    # 展开出来的 body 是静态流 ⇒ 不撑开会溢出盖住 `.-agent-head` 与消息区顶部（L4 实测过 45px）。
    assert '"-agent-write-host--open"' in src, "展开时给宿主打类 ⇒ CSS 让它 height:auto"
    assert 'classList.remove("-agent-write-host--open")' in src, "每次重绘回到折叠态（不留坏类）"
    assert ".-agent-write-host--open { height: auto; align-items: flex-start; }" in (
        PANEL.parents[1] / "css" / "app.css"
    ).read_text(encoding="utf-8"), "配套 CSS 规则（同特异度、在本文件更靠后 ⇒ 覆盖 `.-agent-history` 的固定高度）"
    assert 'data-act="redo"' not in src, "不复用旧的手写 redo 标记（重做走栈）"
    # 接口必须在 IIFE 的 `return {...}` 里暴露；**不能**在 IIFE 内部 `Object.assign` 到那个全局名
    # —— 那时全局名还没被赋值，`Object.assign` 只会创建临时对象、随后被 `return` 覆盖 ⇒ 方法丢失（真机踩过：
    # 表现是"agent 回话下面只有复制、没有撤销"，且控制台一片干净）
    assert "setWriteState: setWriteState" in src, "状态栏接口要在 return 里暴露给 plan-confirm.js"
    assert "Object.assign(window.MemoriaAgentPanel" not in src, "不要在 IIFE 内部 assign 到那个全局名"

    app_dir = PANEL.parents[1]  # …/ui/static/app
    for lang in ("zh-CN", "en"):
        text = (app_dir / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
        assert f'g.MEMORIA_LOCALES["{lang}"].agent, {{' in text, f"{lang}.js：新键须追加在文件末尾的 agent 块里"
        for key in (
            "copy",
            "copyDone",
            "copyFail",
            "undo",
            "undoTitle",
            "undoing",
            "undoDone",
            "undoFail",
            "redo",
            "redoTitle",
            "redoing",
            "redoDone",
            "redoFail",
            "stackPos",
            "stackStep",
            "stackHere",
            "writeIdle",
            "writeSummary",
            "writeLines",
            "writeFailed",
            "maxIterations",
            "maxTokens",
            "filtered",
            "emptyAnswer",
            "process",
            "tools",
            "messages",
            "failed",
            "thought",
            "toggleTitle",
            "running",
            "output",
            "inspectTitle",
            "transcriptLabel",
        ):
            assert f"{key}:" in text, f"{lang}.js 缺键 agent.{key}"


def test_last_reply_carries_usage_and_hit_rate_at_a_stable_anchor() -> None:
    """人 2026-09-21：「agent 最后一次回话下方没有显示 token 使用情况以及命中率」。

    用量行**一直有实现**（`renderTurnUsage()`），坏在**定位**：它按"assistant 序位 +
    `querySelectorAll('.-agent-msg--assistant')`"取元素，而计划 / 写入回执卡也带这个类
    （`plan-confirm.js`）却**不在** `messages` 里 ⇒ 只要出现过写入卡，序位就整体偏一格，
    用量行挂到那张卡上、最后那条回话下方反而空白。

    钉住三点：① 定位改走 `assistantWrapFor()`（`data-msg-index` 稳定索引）；② 每个消息元素都打上该
    索引（包装 `messageEl()`，不改本体 ⇒ 行号锚点不动）；③ 旧的序位法**删除且不许复活**；④ 用量行
    补上命中率（`agent.usage.rate`，口径 `hit / prompt`，与底部状态栏同源）。
    """
    src = panel_source()
    assert "function assistantWrapFor(rec)" in src
    assert 'data-msg-index="' in src and "el.dataset.msgIndex" in src
    assert "const baseMessageElForIndex = messageEl;" in src, "靠包装 messageEl() 打索引（不改本体）"
    assert "assistantOrdinal" not in src, "序位法已删除（错位根因），不要留作后备"
    assert "const wraps = box.querySelectorAll" not in src, "序位法不许复活"
    assert 'T("agent.usage.rate"' in src
    for lang in ("zh-CN", "en"):
        text = (PANEL.parents[1] / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
        assert 'rate: "' in text, f"{lang}.js 缺 agent.usage.rate"


def test_stop_note_maps_every_non_final_stop_reason_to_a_visible_note() -> None:
    """人 2026-09-21：「agent 有时候思考就卡在思考了，然后没有后文」（例：AAA_Vocab）。

    真机取证（`docs/example/AAA_Vocab/.memoria/agent/sessions/session-20260921T111525Z-ab1ac72c.jsonl`）：
    `loop/end {stop_reason:"max-iterations", iterations:8}`，最后一轮 `assistant/message` 的 `content`
    是**空串**（只有 tool_calls）⇒ 后端 `answer=""`，而前端过去完全不读 `stop_reason` ⇒ 气泡全空。

    这里**实跑** `stopNote()`（从源码抽出、`T` 用桩），钉住"每一类非正常收尾都有一句话"，并且
    **正常收尾但没有正文**（`final-answer` + `answer==""`，`test_agent_thinking_stream.py` 明确允许）
    同样要说话 —— 否则人看到的仍是"卡在思考、没有后文"。
    """
    fn = extract_function("stopNote")
    script = (
        "function T(k, p) { return p ? k + JSON.stringify(p) : k; }\n"
        + fn
        + "\nconsole.log(JSON.stringify(["
        + 'stopNote({stop_reason: "max-iterations", iterations: 8}),'
        + 'stopNote({stop_reason: "max-tokens"}),'
        + 'stopNote({stop_reason: "content-filter"}),'
        + 'stopNote({stop_reason: "final-answer"}),'
        + "stopNote(null)]));"
    )
    assert node_eval(script) == [
        'agent.stop.maxIterations{"n":8}',
        "agent.stop.maxTokens",
        "agent.stop.filtered",
        "agent.stop.emptyAnswer",
        "agent.stop.emptyAnswer",
    ]


def test_status_line_is_retired_and_errors_go_to_the_floating_toast() -> None:
    """人 2026-09-21：「对话框下面这个（`#agent-status`）能不能去掉」⇒ 整行撤除，错误改走顶部 toast。

    四条不许回退：
    ① `index.html` 里**不再有**该元素（原行改成注释、**保留行数** ⇒ 文档里那些 `index.html:<行号>`
       锚点（如 :175 / :323 / :360）不动）；
    ② `app.css` 的两条规则同步作废（同样原地留注释、保留行数 ⇒ `app.css:5160` / `:5615-5641` 不动）；
    ③ `setStatusText()` 被**接管**：只记状态（状态点判红改读内部布尔）+ 把"只在这行显示过"的提示
       （未输问题 / 换库丢弃 / 超时 / 配置读取失败）改走 `showFlashError`；
    ④ 一次失败**只弹一个** toast（两个入口谁先谁后都要去重），且「断网」**不弹**（它是状态，不是出错）。
    """
    app = PANEL.parents[1]
    html = (app / "index.html").read_text(encoding="utf-8")
    assert 'id="agent-status"' not in html
    css = (app / "css" / "app.css").read_text(encoding="utf-8")
    assert ".-agent-status {" not in css, "撤除的样式不许剩规则体"
    assert ".-agent-status.-agent-error" not in css
    src = panel_source()
    assert "const baseSetStatusTextBeforeStatus = setStatusText;" in src, "状态行写入被接管"
    assert "const baseShowFlashErrorBeforeStatus = showFlashError;" in src
    assert "function flashOnce(fn, args)" in src, "两个入口共用一道去重闸门"
    assert 'text !== T("agent.err.net_disabled")' in src, "「断网」是状态、不弹 toast"
    assert 'if (lastStatusError) return "error";' in src, "状态点改读内部状态（不再读 DOM 类）"
    assert "function stopNote(result)" in src, "没有最终答复时必须说一句"


def test_turn_process_rows_render_so_a_failed_write_cannot_hide() -> None:
    """2026-09-22「一次回合的过程内容」：**过程行**取代旧的 `toolsStrip()` 摘要条，失败仍必须显形。

    真机取证（2026-09-21）：那一轮 iteration 8 里模型**说了话也调了工具** —— `propose_write` 要建
    `vocab/plummet.md`，但整批被拒（`capability/apply` 报 `backup_failed`：`[WinError 5] 拒绝访问`
    在批次目录 rename 上）⇒ 库内**一个字节没变**；而前端过去**完全不渲染** `tool_calls[]` ⇒ 人只
    看到"我按模板写入"这句承诺，结论必然是"agent 没有做出行动"。

    钉住（**新**不变量）：
    ① `finalizeMessage` 仍把工具结果收进消息记录（兜底合成的数据面）；
    ② 过程行由 `renderProcessInto()` 渲染（思考行之后、正文之前）：工具行 = 状态点 + `工具名 · 参数摘要`
       + 状态文案，`error` 行红字（`agent.tool.failed` + code）、`running` 文案、`ok` 不加字；
    ③ **实时通道**：包装门面 `call`，第 4 个位置参数回传 `process_cursor`、`process_delta` 喂给
       `applyProcessDelta()`（同 `id` 的结果行**就地**更新，不重建整块）；
    ④ **兜底**：没有实时过程通道（`rec.process` 空、`result.tool_calls` 有）时 `synthesizeRows()` 合成行
       （`message` 当 `detail`、`is_error` 定 `state`）⇒ 失败不可能隐形；
    ⑤ 旧实现（`toolsStrip()` / `.-agent-tools` / `agent.tools.*`）**不再存在**；
    ⑥ 中英键 + 配套 CSS 在场。
    """
    src = panel_source()
    assert "rec.tools = Array.isArray(result.tool_calls)" in src, "工具结果要进消息记录"
    for name in (
        "renderProcessInto",
        "applyProcessDelta",
        "processRowsEl",
        "toolRowEl",
        "updateToolRowEl",
        "processBox",
        "synthesizeRows",
        "procRows",
        "mergeToolRows",
    ):
        assert f"function {name}(" in src, f"缺少 {name}()"
    assert 'box.className = "-agent-process";' in src, "过程区容器"
    assert 'line.className = "-agent-tool";' in src and 'dot.className = "-agent-tool-dot";' in src
    assert 'line.setAttribute("data-tool-id", String((row && row.id) || ""));' in src
    assert 'line.setAttribute("data-state", state);' in src, "状态点按 data-state 着色"
    assert 'T("agent.tool.running")' in src and 'T("agent.tool.failed")' in src and 'T("agent.tool.output")' in src
    assert 'st.classList.toggle("-agent-tool-state--error", state === "error");' in src, "失败行红字"
    # 实时通道：门面 `call` 补第 4 个位置参数（过程游标）并消费 `process_delta`
    assert "args.push(reasoningCursor); args.push(processCursor);" in src, "第 4 个位置参数 = 过程游标"
    assert 'if (res && typeof res.process_cursor === "number") processCursor = res.process_cursor;' in src, "回传游标"
    assert "applyProcessDelta(res.process_delta)" in src, "过程增量先喂给 applyProcessDelta"
    assert "let processCursor = 0;" in src and "processCursor = 0;" in src, "每轮提问重置过程游标"
    assert 'if (line) updateToolRowEl(line, row);' in src and "else box.appendChild(toolRowEl(row));" in src, "同 id 就地更新"
    # 兜底：无实时过程通道时由 `result.tool_calls` 合成
    assert 'detail: String((call && call.message) || ""),' in src
    assert 'state: isError ? "error" : "ok",' in src
    # 旧实现不许复活
    assert "function toolsStrip" not in src and '"-agent-tools"' not in src
    assert 'T("agent.tools.' not in src
    css = (PANEL.parents[1] / "css" / "app.css").read_text(encoding="utf-8")
    assert ".-agent-tools {" not in css and ".-agent-tool-row {" not in css
    assert '.-agent-tool[data-state="error"] .-agent-tool-dot { background: var(--error); }' in css
    assert ".-agent-tool-state--error { color: var(--error); }" in css
    # 载荷侧：`tool_calls[]` 必须带**可读原因**（`message`），否则前端只能显示光秃秃的 code
    ask_src = (Path(__file__).resolve().parents[1] / "src" / "memoria" / "services" / "agent" / "ask.py").read_text(
        encoding="utf-8"
    )
    assert '"message": _tool_message(call.content)' in ask_src
    assert "def _tool_message(content: Any) -> str:" in ask_src


def test_should_skip_kb_refresh_window_is_one_and_a_half_seconds() -> None:
    """`shouldSkipKbRefresh()`：把"同一次收尾里两个刷新入口只能跑一遍"的窗口钉死（node 实跑）。"""
    fn = extract_function("shouldSkipKbRefresh")
    script = fn + (
        "\nconsole.log(JSON.stringify(["
        "shouldSkipKbRefresh(10000, 9000),"  # 1.0s 内 ⇒ 跳
        "shouldSkipKbRefresh(10000, 8000),"  # 2.0s 前 ⇒ 不跳
        "shouldSkipKbRefresh(10000, 0),"     # 从未刷过 ⇒ 不跳
        "shouldSkipKbRefresh(10000, undefined)]));"
    )
    assert node_eval(script) == [True, False, False, False]


def test_turn_end_refreshes_the_workspace_unconditionally() -> None:
    """人 2026-09-21：「每次对话结束 memoria 没有刷新，程序上先挂一个刷新」。

    原来只有"写入回执"那条路会刷（`plan-confirm.syncAfterWrite()`），而 agent 现在是**调用内直接
    落盘**的 ⇒ 只要回执链路没走到（本回合只是读+答、提议没被 drain…），文件树 / 待确认 / 图谱 /
    当前文档就停在本回合之前的样子。现在 `finalizeMessage()`（`done` 与 `error` 都走）收尾无条件刷。

    钉住：① 收尾钩子里真的调了 `refreshAfterTurn(result)`；② 三个 KB 视图**无条件**刷；③ 当前文件
    **只在"本回合写过库"且没有脏编辑时**重开（绝不覆盖人正在写的编辑）；④ 与 `syncAfterWrite()`
    共用 1.5s 去重窗口（`A().__kbRefreshAt`）—— 视图可跳，**精确**的"确知被写就重开"永远执行。
    """
    src = panel_source()
    assert "refreshAfterTurn(result); // 回合收尾**无条件刷工作区**" in src, "收尾必须挂上"
    assert "function refreshAfterTurn(result)" in src and "function turnWroteSomething(result)" in src
    assert 'row.name === "propose_write" && !row.is_error' in src, "判据 = 写工具成功过一次"
    assert "if (!turnWroteSomething(result)) return;" in src, "没写过库 ⇒ 不动编辑器"
    assert "window.__memoriaHasPendingEdits && window.__memoriaHasPendingEdits()" in src, "脏编辑 ⇒ 不重开"
    assert "shouldSkipKbRefresh(Date.now(), app.__kbRefreshAt)" in src and "app.__kbRefreshAt = Date.now();" in src
    for call in ("app.refreshFiles?.()", "app.refreshKbPendingSummary?.()", "app.loadGraphData?.()"):
        assert call in src, f"收尾刷新缺 {call}"
    plan = (PANEL.parents[1] / "js" / "plan-confirm.js").read_text(encoding="utf-8")
    assert "const fresh = Date.now() - (Number(app.__kbRefreshAt) || 0) < 1500;" in plan, "另一侧同窗口"
    assert plan.count("if (!fresh) {") == 2, "只跳过两组视图刷新（重开当前文件那条永远执行）"


def test_agent_reply_math_goes_through_the_preview_pipeline() -> None:
    """人 2026-09-21：「agent 回复的内容公式没有被渲染，它的渲染不是采用和 memoria 一样的吗」。

    事实是**不一样**：气泡只走 `marked.parse()`，没有预览那条"公式"管线 ⇒ `$…$` / `$$…$$` 原样留在
    文本里（而 MathJax 的全局配置本来就认这两个定界符：`index.html:24-33`）。

    钉住三条：① 交给 `marked` 之前走**同一份**归一化（`MemoriaMathNormalize.normalize()`，
    `markdown-preview.js::normalizeBody()` 用的也是它）；② 净化**之后**用**同一个** MathJax 实例排版
    （`MemoriaMathPreview.initMathJax()` + `MathJax.typesetPromise`）；③ 排版**防抖**且在节点已游离时
    跳过（流式每帧重渲染 ⇒ 不能每帧都排）。
    """
    src = panel_source()
    assert "tpl.innerHTML = agentRichHtml(src);" in src, "正文走完整管线（公式归一化 + 图片改写）"
    assert "window.marked.parse(agentMathSource(src), { gfm: true, breaks: true })" in src, "管线内先归一化再 marked"
    assert "attachAgentImages(el); typesetAgentMath(el); // 净化**之后**" in src, "排版挂在净化之后"
    assert src.index("sanitizeHtmlInto(el, tpl.content);") < src.index("typesetAgentMath(el);"), (
        "顺序：先净化再排版（否则 MathJax 产物会被剥掉）"
    )
    assert "function agentMathSource(text)" in src and "function typesetAgentMath(el)" in src
    assert "window.MemoriaMathNormalize" in src, "归一化取共享模块（不复制第二套规则）"
    assert "preview.initMathJax()" in src and "window.MathJax.typesetPromise([el])" in src
    assert "const AGENT_MATH_DEBOUNCE_MS = 300;" in src and "if (!el.isConnected) return;" in src, "防抖 + 游离守卫"


def test_agent_math_source_falls_back_and_never_swallows_text() -> None:
    """`agentMathSource()`：有归一化模块就走它；模块缺失 / 抛错一律**原样返回正文**（node 实跑）。"""
    fn = extract_function("agentMathSource")
    script = (
        "global.window = {MemoriaMathNormalize: {normalize: (s) => s.replace(/x/, 'NORMALIZED')}};\n"
        + fn
        + "\nconst ok = agentMathSource('x');"
        + "\nglobal.window = {};\nconst missing = agentMathSource('x');"
        + "\nglobal.window = {MemoriaMathNormalize: {normalize: () => { throw new Error('boom'); }}};\n"
        + "const boom = agentMathSource('x');"
        + "\nconsole.log(JSON.stringify([ok, missing, boom, agentMathSource(null)]));"
    )
    assert node_eval(script) == ["NORMALIZED", "x", "x", ""]


def test_local_images_are_rendered_but_only_from_the_library() -> None:
    """人 2026-09-21：「img 怎么会被丢，都是交给 memoria 渲染管线渲染的，只要有本地图片文件就会渲染出来」。

    会话记录里的图片引用（`.memoria/images/x.png`）经预览那条通路改写成 `/files/...` 后**应当渲染**；
    但气泡内容是**模型输出、不受信** ⇒ 只放行**库内**图片，远程 / `data:` / `javascript:` 一律丢，
    且只搬运 `src`/`alt`/`title` 三个属性（`on*` 不抄）。
    """
    src = panel_source()
    # ① 图片不再整棵丢弃；改写走预览同一份实现
    assert '"IMG", "PICTURE"' not in src and '"PICTURE", "VIDEO", "AUDIO", "SOURCE", "TRACK", "CANVAS", "SVG", "MATH"' in src
    assert "function agentRichHtml(src)" in src and "preview.rewriteLocalImagePaths(html)" in src, "库根改写取共享实现"
    # ② 净化期只放行库内图片，且只搬三个属性
    assert 'if (tag === "IMG") appendLocalImage(target, node); else sanitizeHtmlInto(target, node);' in src
    assert "function appendLocalImage(target, node)" in src and "if (!isLocalImageSrc(src)) return;" in src
    for forbidden in ('setAttribute("onerror"', 'setAttribute("onload"', 'setAttribute("href"'):
        assert forbidden not in src, "属性只搬 src/alt/title"
    # ③ 灯箱复用预览那一套
    assert "preview.attachImageLightbox(el)" in src and "attachAgentImages(el); typesetAgentMath(el);" in src


def test_local_image_src_predicate_is_the_security_boundary() -> None:
    """`isLocalImageSrc()`：只有改写后的 `/files/...` 算库内图片（node 实跑，安全边界只此一处）。"""
    fn = extract_function("isLocalImageSrc")
    script = fn + (
        "\nconsole.log(JSON.stringify(["
        "isLocalImageSrc('/files/.memoria/images/a.png'),"
        "isLocalImageSrc('/files/x.png'),"
        "isLocalImageSrc('http://evil/x.png'),"
        "isLocalImageSrc('https://evil/x.png'),"
        "isLocalImageSrc('data:image/png;base64,AAAA'),"
        "isLocalImageSrc('javascript:alert(1)'),"
        "isLocalImageSrc('files/x.png'),"
        "isLocalImageSrc(''),"
        "isLocalImageSrc(null)]));"
    )
    assert node_eval(script) == [True, True, False, False, False, False, False, False, False]


def test_thinking_and_process_text_use_the_same_markdown_pipeline() -> None:
    """人 2026-09-21：「思考可以渲染吧，不然公式这些用户都看不懂」。

    **上游是纯文本**（`dsh-src/.../ReasoningRow.tsx:60` 直接 `{text}`，第 30 行还把 `**` 去掉）——
    我们**有意超出上游**：思考行（`.-agent-think-body`）与过程行里的「更早助手正文」（`.-agent-step`）
    都走助手正文那条管线（归一化 + marked + 净化 + 公式排版），否则思考里的公式没人看得懂。
    """
    src = panel_source()
    assert "if (String(text || \"\").trim()) { renderAssistantBody(body, text);" in src, "思考行渲染（空文本仍走快路径）"
    assert "renderAssistantBody(step, text); // 与助手正文同一条管线" in src, "过程行的更早正文同样渲染"
    css = (PANEL.parents[1] / "css" / "app.css").read_text(encoding="utf-8")
    assert ".-agent-think-body.markdown-body," in css and ".-agent-step.markdown-body {" in css, "撤掉 pre-wrap"
    assert ".-agent-think-body.markdown-body > :first-child," in css, "首尾间距收口"


def test_agent_bubble_images_fit_the_pane_width() -> None:
    """人 2026-09-21：「agent 对话的图片自动按照对话栏宽度对图片大小后处理自适应缩放」。

    真机症状（L4 实测）：1920×1080 的库内图在 ~350px 宽的对话栏里**按原始像素**渲染 ⇒ 横向溢出、
    被裁。钉住三处容器（正文 / 思考行 / 过程行里的更早正文）都 `max-width: 100%` + `height: auto`
    （撑满不越界、保比例），圆角取预览 `.-preview img` 同一档（`app.css:4255` 的 4px）。
    """
    css = (PANEL.parents[1] / "css" / "app.css").read_text(encoding="utf-8")
    assert ".-agent-msg-body.markdown-body img," in css
    assert ".-agent-think-body.markdown-body img," in css
    assert ".-agent-step.markdown-body img {" in css
    block = css.split(".-agent-step.markdown-body img {")[1].split("}")[0]
    assert "max-width: 100%;" in block, "按对话栏宽度撑满但不越界"
    assert "height: auto;" in block, "保比例"
    assert "border-radius: 4px;" in block, "与预览的图片圆角同档"


def test_composer_history_stepping_is_pure_and_bounded() -> None:
    """`composerHistNext()`：空框翻历史的**下标推进**规则（node 实跑）。

    口径（人 2026-09-21：「输入框空的时候按上下键要可以切换'发过的内容'」）：首次 ↑ = **最新**那条；
    继续 ↑ 往旧；**已到最旧停在最旧**（免得"再按一下框就空了"）；↓ 往新；**越过最新 ⇒ `null`**
    （退出历史模式、回到空框）；没有历史 ⇒ `null`。
    """
    fn = extract_function("composerHistNext")
    script = fn + (
        "\nconsole.log(JSON.stringify(["
        "composerHistNext(null, -1, 3),"   # 首次 ↑ ⇒ 最新（下标 2）
        "composerHistNext(2, -1, 3),"      # 再 ↑ ⇒ 1
        "composerHistNext(1, -1, 3),"      # 再 ↑ ⇒ 0
        "composerHistNext(0, -1, 3),"      # 已到最旧 ⇒ 停在 0
        "composerHistNext(0, 1, 3),"       # ↓ ⇒ 1
        "composerHistNext(2, 1, 3),"       # 越过最新 ⇒ null
        "composerHistNext(null, 1, 3),"    # 没进历史就 ↓ ⇒ null
        "composerHistNext(null, -1, 0),"   # 无历史 ⇒ null
        "composerHistNext(9, -1, 3)]));"   # 越界游标 ⇒ 当首次 ↑ 处理
    )
    assert node_eval(script) == [2, 1, 0, 0, 1, None, None, None, 2]


def test_composer_enter_ctrl_enter_and_history_wiring() -> None:
    """`#agent-input` 的三条键位口径：Enter 发送、Shift+Enter / **Ctrl（Cmd）+Enter 换行**、空框 ↑↓ 翻历史。

    人 2026-09-21：「输入框空的时候按上下键要可以切换"发过的内容"，crtl+enter输入框内换行」；
    2026-09-22 真机打回「ctrl+enter 没有换行」⇒ Ctrl/Cmd+Enter 改为**自己插**（不再指望浏览器默认）。
    实现要点：③ 有草稿时**一概不碰**（交给浏览器默认的上下移动）；④ 敲字 / `ask()` 之后游标复位。
    """
    src = panel_source()
    assert "if (composerEnterKey(e, input)) return;" in src, "Enter 语义收口到 composerEnterKey"
    assert (
        'if (e.ctrlKey || e.metaKey) {' in src and "composerInsertLineBreak(input);" in src
    ), "Ctrl/Cmd+Enter 必须**自己插**换行（Windows Chromium 没有默认动作）"
    assert "Windows Chromium 对 Ctrl+Enter 没有默认动作" in src, "文件头按键说明同步"
    assert 'if (String(input.value || "") !== "" && composerHistCursor === null) return false;' in src, (
        "判据是'人打的草稿'，不是'框空不空'（否则历史翻一次就卡死）"
    )
    assert "input.addEventListener(\"input\", function () {\n      composerHistCursor = null;" in src, "敲字即退出历史"
    assert "const askBase = ask;" in src and "composerHistCursor = null; // 发出去之后重新从最新那条开始" in src
    assert "input.setSelectionRange(end, end); // 光标落在末尾" in src
    assert "afterComposerEdit(input, end); // chip / 提及块与被替换的文本同步" in src


def test_ctrl_enter_really_inserts_a_line_break() -> None:
    """**真跑源码**：`composerEnterKey()` + `composerInsertLineBreak()` 在光标处插 `\\n`。

    这条是 2026-09-22 真机报障（「输入框内 ctrl+enter 没有换行」）的回归钉子 ——
    旧实现靠"不 preventDefault、交给浏览器默认"，而 Windows Chromium 的 textarea 对
    Ctrl+Enter **没有**默认动作 ⇒ 什么都不会发生。现在必须由我们自己插。
    """
    script = (
        extract_function("composerInsertLineBreak")
        + "\n"
        + extract_function("composerEnterKey")
        + """
function fakeInput(value, caret, end) {
  return {
    value: value, selectionStart: caret, selectionEnd: end === undefined ? caret : end,
    _caret: null, _events: 0,
    setSelectionRange: function (a, b) { this._caret = [a, b]; },
    dispatchEvent: function () { this._events += 1; return true; },
  };
}
function key(extra) {
  var e = { key: "Enter", ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, isComposing: false, _prevented: 0 };
  Object.keys(extra || {}).forEach(function (k) { e[k] = extra[k]; });
  e.preventDefault = function () { e._prevented += 1; };
  return e;
}
var out = {};
var a = fakeInput("abc", 3);
var ctrl = key({ ctrlKey: true });
out.ctrlHandled = composerEnterKey(ctrl, a);
out.ctrlValue = a.value;
out.ctrlCaret = a._caret;
out.ctrlEvents = a._events;
out.ctrlPrevented = ctrl._prevented;

var b = fakeInput("hello world", 5);
composerEnterKey(key({ metaKey: true }), b);
out.metaValue = b.value;
out.metaCaret = b._caret;

var c = fakeInput("abcdef", 2, 5);
composerEnterKey(key({ ctrlKey: true }), c);
out.selectionValue = c.value;

var d = fakeInput("send me", 7);
out.plainHandled = composerEnterKey(key({}), d);
out.plainValue = d.value;
out.plainEvents = d._events;

out.shiftHandled = composerEnterKey(key({ shiftKey: true }), fakeInput("x", 1));
out.altHandled = composerEnterKey(key({ altKey: true }), fakeInput("x", 1));
out.ctrlShiftHandled = composerEnterKey(key({ ctrlKey: true, shiftKey: true }), fakeInput("x", 1));
out.composingHandled = composerEnterKey(key({ isComposing: true }), fakeInput("x", 1));
out.nonEnterHandled = composerEnterKey(key({ key: "a" }), fakeInput("x", 1));
console.log(JSON.stringify(out));
"""
    )
    out = node_eval(script)
    assert out["ctrlHandled"] is True
    assert out["ctrlValue"] == "abc\n", "Ctrl+Enter 必须真的把 \\n 写进 value"
    assert out["ctrlCaret"] == [4, 4], "光标落在换行之后"
    assert out["ctrlEvents"] == 1, "要派发 input（镜像层 / 历史游标 / chip 高亮都挂在它上面）"
    assert out["ctrlPrevented"] == 1, "自己插就必须 preventDefault（否则浏览器可能再动一次）"
    assert out["metaValue"] == "hello\n world" and out["metaCaret"] == [6, 6], "Cmd+Enter 同口径、插在光标处"
    assert out["selectionValue"] == "ab\nf", "有选区时替换选区"
    assert out["plainHandled"] is False, "裸 Enter = 发送（由调用方 ask()）"
    assert out["plainValue"] == "send me" and out["plainEvents"] == 0, "发送路径不改 value"
    for flag in ("shiftHandled", "altHandled", "ctrlShiftHandled", "composingHandled", "nonEnterHandled"):
        assert out[flag] is True, f"{flag} 应放行（不改 value）"


def test_sticky_scroll_does_not_fight_the_user() -> None:
    """**真跑源码**：粘底判据 + 接线（2026-09-22 报障「生成的时候我无法往上滚动」）。

    旧行为：每个分片/过程行都无条件 `scrollTop = scrollHeight` ⇒ 用户上翻被每帧拽回。
    新行为：`stickToBottom` 由用户自己的滚动维护，非强制调用只在粘底时跟随。
    """
    src = panel_source()
    found = re.search(r"const STICK_SLOP_PX = (\d+);", src)
    assert found is not None, "STICK_SLOP_PX 常量缺失"
    slop = int(found.group(1))
    script = (
        "var STICK_SLOP_PX = " + str(slop) + ";\n"
        + extract_function("boxAtBottom")
        + """
var out = {};
out.atBottom = boxAtBottom(1000, 900, 100);
out.withinSlop = boxAtBottom(1000, 1000 - 100 - (STICK_SLOP_PX - 8), 100);
out.beyondSlop = boxAtBottom(1000, 1000 - 100 - (STICK_SLOP_PX + 8), 100);
out.scrolledUp = boxAtBottom(1000, 500, 100);
out.shortContent = boxAtBottom(50, 0, 100);
out.grownWhileAtBottom = boxAtBottom(1400, 900, 100);
console.log(JSON.stringify(out));
"""
    )
    out = node_eval(script)
    assert out["atBottom"] is True
    assert out["withinSlop"] is True, "容差内仍算「在看底部」"
    assert out["beyondSlop"] is False, "超出容差即停止跟随"
    assert out["scrolledUp"] is False, "往上翻 400px ⇒ 不再跟随"
    assert out["shortContent"] is True, "内容比容器短（没有滚动条）⇒ 算在底部"
    assert out["grownWhileAtBottom"] is False, (
        "内容一帧长出一大截时离底距离会瞬时变大 —— 故**不能**只看距离，"
        "必须由滚动事件维护 stickToBottom（这条钉住那条设计的理由）"
    )

    # `stickAfterScroll()`：状态机（L4 第二轮打回后改的判据 —— 只看**位置上移**）
    script = (
        "var STICK_SLOP_PX = " + str(slop) + ";\n"
        + extract_function("boxAtBottom")
        + "\n"
        + extract_function("stickAfterScroll")
        + """
var out = {};
// ① 用户上翻：位置变小 ⇒ 关掉跟随
out.userScrolledUp = stickAfterScroll(true, 5000, 4000, false);
// ② 程序化滚底 / 用户拖回底部：位置变大且近底 ⇒ 恢复跟随
out.backToBottom = stickAfterScroll(false, 0, 5000, true);
// ③ L4 事故：发问后强制滚底，事件到达时内容又长了一截（位置**变大**、距离 51 > 容差）
out.grownRightAfterSend = stickAfterScroll(true, 22569, 22630, false);
// ④ 位置没动（内容变长引起的同一位置）⇒ 保持原状态
out.samePosition = stickAfterScroll(false, 4000, 4000, false);
// ⑤ 上翻一像素以内算抖动，不关跟随
out.tinyJitter = stickAfterScroll(true, 5000, 4999.5, false);
console.log(JSON.stringify(out));
"""
    )
    out = node_eval(script)
    assert out["userScrolledUp"] == [False, 4000], "位置上移 ⇒ 停止跟随"
    assert out["backToBottom"] == [True, 5000], "回到底部 ⇒ 恢复跟随"
    assert out["grownRightAfterSend"] == [True, 22630], (
        "位置**变大**（哪怕还没到底）不许关掉跟随 —— 这正是 L4 抓到的"
        "『发问后整轮不再跟随』假阴性"
    )
    assert out["samePosition"] == [False, 4000], "同一位置保持原状态"
    assert out["tinyJitter"] == [True, 4999.5], "1px 内抖动不当作上翻"

    assert "if (box) messageBoxScrollTo(box, force === true);" in src
    assert "if (force) stickToBottom = true;" in src, "强制滚底要重挂粘底"
    assert "if (top < Number(lastTop) - 1) return [false, top];" in src, "只有位置上移才算用户上翻"
    assert 'box.addEventListener("scroll", function () {' in src, "滚动事件维护粘底状态"
    assert "streamingEl.textContent = rec.text;\n      scrollToBottom();" in src, "流式分片**不**强制滚底"
    assert src.count("scrollToBottom(true);") == 3, "强制滚底只留三处：整串重绘 / 用户发问 / 确认卡进场"


def test_composer_mirror_matches_the_textarea_content_box() -> None:
    """镜像层尺寸对齐 textarea 的**内容盒**（2026-09-22 报障「文字与光标错位几格」）。

    旧实现用 `offsetWidth/offsetHeight`：textarea 一旦出现滚动条（内容超过 `max-height`），
    可用文本宽度就窄一个滚动条（≈17px）⇒ 镜像换行点与 textarea 不一致 ⇒ 光标落在可见文字右侧几格。
    """
    src = panel_source()
    assert src.count('mirror.style.width = composerMirrorWidth(input) + "px";') == 2, (
        "两处 syncComposerChips（原始 + §6.20 重绑）都要走内容盒尺寸"
    )
    assert src.count('mirror.style.height = composerMirrorHeight(input) + "px";') == 2
    assert "return input.clientWidth + border;" in src, "clientWidth 已排除滚动条，再加两侧边框"
    assert "return input.clientHeight + border;" in src
    assert 'mirror.style.width = input.offsetWidth + "px"' not in src, "不许再用 offsetWidth 定镜像宽度"
    assert "parseFloat(cs.borderLeftWidth)" in src and "parseFloat(cs.borderRightWidth)" in src


def test_reply_bottom_row_is_usage_plus_a_visible_copy_button() -> None:
    """回复末尾那一行 =「用量 + 复制」同一行（人 2026-09-22：「对话底部除了显示用量信息还需要复制按钮」）。

    旧布局：用量文本挂在**气泡内**（`.-agent-msg` 末尾），复制是气泡外那一行里的**纯图标**
    （`opacity: .55`、文案只在悬停时给）⇒ 人没把它当成按钮。
    """
    src = panel_source()
    # ① 用量格改挂**操作行**（气泡外那一行）的**最前** ⇒ 与复制同一行
    assert "const line = usageRowEl(wrap);" in src
    assert "host.insertBefore(el, host.firstChild);" in src
    assert "wrap.appendChild(line);" not in src, "不许再挂回气泡内（那就成了两行）"
    assert "function usageRowHost(wrap) {" in src and 'turn.querySelector(".-agent-msg-actions")' in src
    # ② 复制按钮常显 + 带文字标签（图标 + 「复制」二字）
    assert 'class="-agent-act-label"' in src and 'esc(T("agent.copy"))' in src
    # ③ **实时那一轮必须真的长出按钮**（L4 抓到的真 bug）：助手消息是空文本建的，
    #    `actionsEl()` 那一刻返回空行；终答后要由 `syncTurnActions()` 补上（刷新页面才有的那条路不算）。
    assert "function copyButtonEl(rec) {" in src, "按钮构造收口（操作行与补齐共用）"
    assert "box.appendChild(copyButtonEl(rec));" in src
    assert "function syncTurnActions(rec) {" in src
    assert "syncTurnActions(currentAssistant());" in src, "终答落定后补齐底部操作行"
    assert "if (host === wrap) return; // 没有独立操作行（异常 DOM）：不往气泡里塞按钮" in src
    css = (PANEL.parents[1] / "css" / "app.css").read_text(encoding="utf-8")
    assert ".-agent-act-label {" in css, "标签样式（图标与文字的间距）"
    assert ".-agent-msg-actions .-agent-act {\n    opacity: 0.8;" in css, "复制按钮常显（原 .55 太隐形）"
    assert ".-agent-msg-actions .-agent-usage {" in css, "用量格在同一 flex 行里的布局"


def test_thinking_row_is_collapsed_and_has_no_text_beside_the_triangle() -> None:
    """① 思考行**始终默认折叠**（`<details>` 不带 `open`）；三角旁边**不放任何文字**；
    ② **摘要行在圆角气泡之外**（`.-agent-think` 自身透明、气泡是它下面的 `.-agent-think-bubble`），
       气泡内还能再「展开全部」（`agent.thinkMore`）；
    ③ 气泡未「展开全部」时，超出部分**不是裁掉**而是**在气泡内滚动**（滚轮即可翻看）；
    ④ **展开态有上限**（8rem → 20rem）：展开只是「变高一点」，按钮不会被顶到内容末尾。

    2026-09-22 人：「思考和三角符号应该不在圆角气泡内，而点击思考之后才展开在下方出现圆角气泡显示
    思考或者正在思考的内容，而且这个圆角气泡可以进一步展开直接显示全部」；「思考过程旁边不用展示文字」；
    「思考过程没展开鼠标在气泡内区域应该可以滚轮滚动内部信息」；「思考气泡要滑倒最底下才能收起很麻烦，
    不全部展示，改成展开后变高一点」。
    """
    src = panel_source()
    assert 'box = document.createElement("details");' in src, "思考行仍是原生 <details>"
    assert "box.open = true" not in src, "任何路径都不许默认展开"
    assert 'label.textContent = T("agent.think")' in src, "摘要行只剩这个固定标签"
    assert 'summary.appendChild(label);' in src, "摘要行只有标签一个子节点"
    assert "-agent-think-tip" not in src, "三角旁边的预览文字已撤除（含它的同步逻辑）"
    assert "thinkSummaryLine" not in src, "摘要取行纯函数随之失去调用点，一并删除"
    css = (PANEL.parents[1] / "css" / "app.css").read_text(encoding="utf-8")
    assert "background: transparent;" in css.rsplit(".-agent-think {", 1)[1].split("}", 1)[0], "摘要行不再自带气泡底色（取**最后**一条声明 = 末尾覆盖块）"
    assert ".-agent-think-bubble {" in css and "border-radius: 6px;" in css, "圆角气泡是它的子节点"
    # 真机 L4 复验（2026-09-22）：按钮排正文**之后**、又与正文同处裁区 ⇒
    # 长正文时 101 个按钮里 98 个落在可见带**外**（点不到"展开全部"）。判据 = 气泡是 flex 列、
    # 正文可收缩（`min-height: 0`）、按钮**不被压缩**（`flex: 0 0 auto`）⇒ 按钮恒在气泡底边。
    bubble = css.rsplit(".-agent-think-bubble {", 1)[1].split("}", 1)[0]
    assert "display: flex;" in bubble and "flex-direction: column;" in bubble, "气泡按列排、按钮才钉得住"
    body_rule = css.rsplit(".-agent-think-body {", 1)[1].split("}", 1)[0]
    assert "min-height: 0;" in body_rule and "overflow-y: auto;" in body_rule, "正文在气泡内滚动（不是裁掉）"
    more_rule = css.rsplit(".-agent-think-more {", 1)[1].split("}", 1)[0]
    assert "flex: 0 0 auto;" in more_rule, "「展开全部」不许被压缩/裁掉"
    # 展开态**必须留上限**（人：「思考气泡要滑倒最底下才能收起很麻烦，不全部展示，改成展开后变高一点」）
    # —— 旧值 `max-height: none` 让气泡长到几千 px，收起按钮被顶到内容末尾，得先滑到底才点得到。
    bubble_block = css.rsplit(".-agent-think-bubble {", 1)[1].split(".-agent-think-body {", 1)[0]
    assert "max-height: 8rem;" in bubble_block, "折叠态上限"
    assert ".-agent-think-bubble--full { max-height: 20rem; }" in bubble_block, "展开态 = 「变高一点」，不是放开高度"
    assert "max-height: none;" not in bubble_block, "两态都不许放开高度上限"
    zh = (PANEL.parents[1] / "i18n" / "zh-CN.js").read_text(encoding="utf-8")
    en = (PANEL.parents[1] / "i18n" / "en.js").read_text(encoding="utf-8")
    assert 'thinkMore: "展开",' in zh and 'thinkMore: "Expand",' in en, "按钮文案不许再声称「全部」"


def test_thinking_body_is_always_rendered_never_raw_text() -> None:
    """思考正文**一律走渲染**（人 2026-09-22：「而且思考过程里面要渲染，不是裸文本」）。

    与助手正文的流式**同口径**：每次增量都重渲染（`renderAssistantBody(streamingEl, parts.safe)`）；
    "流式期间先用 `textContent` 顶一下"那个分支已撤 ⇒ 公式 / 代码 / 列表在**生成中**就是渲染结果。
    """
    src = panel_source()
    assert 'if (row.state === "live") {' not in src, "流式的纯文本分支已撤"
    assert 'const shown = text || T("agent.thinkLive");' in src, "空正文时才用占位文案"
    assert "renderAssistantBody(body, shown);" in src, "流式增量也走同一条 markdown 管线"
    assert 'renderAssistantBody(body, text); body.__thinkText = String(text);' in src, "首屏（回放定稿）同样渲染"
    assert "body.__thinkText !== shown" in src, "同文去重，避免每个增量白重渲染"


def test_thinking_is_one_segment_per_step_interleaved_with_tool_rows() -> None:
    """**一段思考 = 一步**（人 2026-09-22：「agent 回话都是上面一个思考，然后产出总结并结束，但是我记得
    在 dsh 里面不是这样的，可能思考是多次开展多次结束的」）。

    `withThinkRows()` 给每个带 `reasoning` 的 `step` 行**前面**插一段思考；**最终答复那一步**的思考
    （回放记录上的 `rec.reasoning`）排在**最后**（它就是"最终答复之前的那次思考"）。
    """
    fn = extract_function("withThinkRows")
    rows = [
        {"kind": "step", "text": "先看看库。", "reasoning": "甲想", "iteration": 1, "tool_calls": 1},
        {"kind": "tool", "id": "c1", "name": "kb_overview", "state": "ok"},
        {"kind": "step", "text": "再改。", "reasoning": "乙想", "iteration": 2, "tool_calls": 1},
        {"kind": "tool", "id": "c2", "name": "propose_write", "state": "ok"},
    ]
    script = (
        fn
        + "\nconsole.log(JSON.stringify(withThinkRows("
        + json.dumps(rows, ensure_ascii=False)
        + ', {"reasoning": "丙想"}).map(function (r) { return r.kind + ":" + (r.text || r.name || ""); })));'
    )
    assert node_eval(script) == [
        "think:甲想", "step:先看看库。", "tool:kb_overview",
        "think:乙想", "step:再改。", "tool:propose_write",
        "think:丙想",
    ], "思考与工具行必须交替出现（一段一步），最终答复那一步的思考在末尾"
    src = panel_source()
    assert "function withThinkRows(rows, rec)" in src and "rows = withThinkRows(rows, rec);" in src, "实时/回放同一处插入"
    assert 'if (row.kind === "think") {' in src, "过程渲染要认得 think 行"


def test_the_expand_all_button_appears_only_when_the_bubble_needs_it() -> None:
    """「展开全部」按**行数 / 字符数**判定（不量 DOM 尺寸：渲染时可能还没进文档 ⇒ 纯函数、可单测）。"""
    fn = extract_function("thinkNeedsMore")
    script = (
        fn
        + "\nconsole.log(JSON.stringify([thinkNeedsMore('短'), thinkNeedsMore('行\\n'.repeat(6)),"
        + " thinkNeedsMore('x'.repeat(241)), thinkNeedsMore(null)]));"
    )
    assert node_eval(script) == [False, True, True, False]
    # 真机 L4 实测缺陷：`needed=true` 分支漏写文案 ⇒ **真正需要按钮的那些**（长正文）反而露出空白按钮
    # （101 个按钮文案为空、高度 3px，点了才出现「收起」）⇒ 两个分支都必须写初始文案。
    body = extract_function("refreshThinkMore")
    assert body.count('more.textContent = T("agent.thinkMore")') == 2, "两个分支都要有初始文案"
    assert "more.hidden = !needed;" in body, "按钮的显隐仍由截断判定驱动"


def test_process_summary_counts_tools_messages_and_failures() -> None:
    """③ 折叠摘要 = `N 次工具调用 · N 条过程消息`（为 0 的段省略）+ ` · N 次失败`；全 0 ⇒ 「思考了一会儿」。"""
    fn = extract_function("processSummaryText")
    prelude = 'function T(k, p) { return p ? k + JSON.stringify(p) : k; }\n'
    rows = [
        {"kind": "step", "text": "我查一下。", "tool_calls": 1},
        {"kind": "tool", "id": "c1", "name": "search_kb", "state": "running", "summary": "多层感知机"},
        {"kind": "tool", "id": "c1", "name": "search_kb", "state": "ok", "summary": "", "detail": "x"},
        {"kind": "tool", "id": "c2", "name": "propose_write", "state": "error", "code": "backup_failed", "summary": "新建 x"},
        {"kind": "tool", "id": "c2", "name": "propose_write", "state": "error", "code": "backup_failed", "summary": ""},
        {"kind": "step", "text": "   ", "tool_calls": 0},
    ]
    script = (
        prelude
        + fn
        + "\nconsole.log(JSON.stringify([processSummaryText("
        + json.dumps(rows, ensure_ascii=False)
        + "), processSummaryText([]), processSummaryText([{kind: 'step', text: '  '}])]));"
    )
    assert node_eval(script) == [
        'agent.process.tools{"n":2} · agent.process.messages{"n":1} · agent.process.failed{"n":1}',
        "agent.process.thought",
        "agent.process.thought",
    ]


def test_same_id_tool_rows_merge_keeping_the_call_summary() -> None:
    """同一次工具调用的 `call` / `result` 两行（同 `id`）合并成**一行**：摘要取调用行、状态取结果行。

    实测（L4，AAA_Vocab 回放）：不合并时一次调用显示成**两行**，其中结果行**没有参数摘要**
    （`tool/result` 事件不带 `arguments` ⇒ 后端 `summary` 是空串，见 `turn_process.tool_row()`）。
    """
    fn = extract_function("mergeToolRows")
    rows = [
        {
            "kind": "tool",
            "id": "c1",
            "name": "kb_overview",
            "summary": "知识库规模",
            "state": "running",
            "code": None,
            "detail": "",
        },
        {"kind": "step", "text": "我先看一下", "tool_calls": 1},
        {"kind": "tool", "id": "c1", "name": "kb_overview", "summary": "", "state": "ok", "code": "ok", "detail": "42 篇"},
        {
            "kind": "tool",
            "id": "c2",
            "name": "propose_write",
            "summary": "新建 plummet",
            "state": "error",
            "code": "backup_failed",
            "detail": "Error: 拒绝访问",
        },
    ]
    script = fn + "\nconsole.log(JSON.stringify(mergeToolRows(" + json.dumps(rows, ensure_ascii=False) + ")));"
    got = node_eval(script)
    assert [row["kind"] for row in got] == ["tool", "step", "tool"]
    assert got[0] == {
        "kind": "tool",
        "id": "c1",
        "name": "kb_overview",
        "summary": "知识库规模",
        "state": "ok",
        "code": "ok",
        "detail": "42 篇",
    }
    assert got[2]["summary"] == "新建 plummet" and got[2]["state"] == "error", "失败行同样保留摘要"
    assert "rows = mergeToolRows(rows);" in panel_source(), "渲染前必须合并（回放与定稿走同一条路）"


def test_folding_needs_a_final_answer_and_normal_mode_never_folds() -> None:
    """③ compact 档只在**末步构成最终答复**时折叠；不是最终答复 / normal 档 ⇒ 过程全部保留可见。"""
    final_fn = extract_function("finalAnswerFromRows")
    fold_fn = extract_function("processFoldable")
    script = (
        final_fn
        + "\n"
        + fold_fn
        + "\nconsole.log(JSON.stringify(["
        + "finalAnswerFromRows([{kind: 'step', text: '答案', tool_calls: 0}]),"
        + "finalAnswerFromRows([{kind: 'step', text: '查一下', tool_calls: 1}, {kind: 'tool', id: 'c1', state: 'ok'}]),"
        + "finalAnswerFromRows([{kind: 'step', text: '', tool_calls: 0}]),"
        + "finalAnswerFromRows([]),"
        + "processFoldable({processFinal: true}, [{kind: 'step', text: 'x'}]),"
        + "processFoldable({processFinal: false}, [{kind: 'tool', id: 'c', state: 'ok'}]),"
        + "processFoldable({}, [{kind: 'tool', id: 'c', state: 'ok'}]),"
        + "processFoldable({}, [{kind: 'tool', id: 'c', state: 'running'}]),"
        + "processFoldable({}, [{kind: 'step', text: 'x', tool_calls: 0}])]));"
    )
    assert node_eval(script) == [True, False, False, False, True, False, True, False, False]
    src = panel_source()
    # 折叠容器 + 真实 `<button>`（`aria-expanded`）⇒ 键盘可达、点击切换
    assert 'if (transcriptMode() !== "compact" || !processFoldable(rec, rows)) {' in src, "normal 档走不折叠分支"
    assert 'box.className = "-agent-process-fold";' in src
    assert 'btn.className = "-agent-act -agent-process-toggle";' in src
    assert 'btn.setAttribute("aria-expanded", open ? "true" : "false");' in src
    assert "rec.processOpen = next;" in src, "展开态按轮记忆（新回合默认折叠）"
    # 正文 / 锚点条 / 错误条 / 「（已停止）」标记由 `messageEl()` 在过程块**之后**追加 ⇒ 永远不折
    assert 'if (body) wrap.insertBefore(box, body); else wrap.appendChild(box);' in src, "过程块插在正文之前"
    assert 'if (body) wrap.insertBefore(frag, body); else wrap.appendChild(frag);' in src, "不折叠时同样插在正文之前"
    assert 'return cfg && cfg.transcript_mode === "normal" ? "normal" : "compact";' in src


def test_transcript_setting_is_wired_into_the_dialog_tab() -> None:
    """④ 设置弹窗「对话」页签的 `<select id="agent-transcript">`（normal / compact）：改动即保存并立即重绘。"""
    app = PANEL.parents[1]
    html = (app / "index.html").read_text(encoding="utf-8")
    assert html.count('id="agent-transcript"') == 1 and html.count('id="agent-refresh"') == 1
    # **零行漂移**：新控件追加在「刷新间隔」那一行里（不新增行 ⇒ `index.html:<行号>` 锚点不动）
    assert (
        '</label><label class="-agent-field"><span data-i18n="agent.settings.transcriptLabel">'
        '对话显示</span><select id="agent-transcript"></select></label>'
    ) in html
    src = panel_source()
    assert 'const TRANSCRIPT_CHOICES = ["normal", "compact"];' in src, "只允许这两个值（后端同白名单）"
    assert 'call("agent_save_config", { transcript_mode: mode })' in src
    assert 'sel.addEventListener("change", () => saveTranscriptMode(sel.value));' in src
    assert "function syncTranscriptSelect()" in src and "function saveTranscriptMode(value)" in src
    assert "syncTranscriptSelect();" in src, "`applyConfigToForm` 包装 / `init` 首帧都要对齐"
    assert "cfg = res;" in src and "renderMessages(); // 立即生效" in src, "改动即保存并立即重绘"
    for lang in ("zh-CN", "en"):
        text = (app / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
        assert "transcriptNormal:" in text and "transcriptCompact:" in text and "transcriptLabel:" in text


def test_replay_renders_process_rows_with_the_same_renderer() -> None:
    """⑤ 回放：`agent_session_load` 的记录带 `process` 时按**同一套**渲染；旧记录不动形状、不报错。"""
    src = panel_source()
    assert "process: msgProcess(rec), reasoning: msgReasoning(rec)," in src, "载入会话时把过程行与思考灌进 rec"
    assert "function msgProcess(rec)" in src and "function msgReasoning(rec)" in src
    assert 'if (row && row.kind === "step" && typeof row.reasoning === "string" && row.reasoning.trim()) parts.push(row.reasoning);' in src
    assert "return rec && Array.isArray(rec.process) ? rec.process : null;" in src, "没有 process 键 ⇒ null（旧会话保持现状）"
    assert src.count("renderProcessInto(") == 2, "定义 1 处 + `messageEl` 包装调用 1 处（回放/实时共用一个渲染器）"
    assert "renderProcessInto(el, rec);" in src

