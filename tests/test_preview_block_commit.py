"""预览区编辑的**块级提交**（2026-09-25）—— 人定的口径：

    「预览区域编辑你尝试改源码区重新渲染预览区。这个是错的，我们原有的基础设施就是做的**双向同步**，
      这也是导致编辑卡顿、上下闪动的原因」

**病根**（两段代码都在 `app.js` 的 `MemoriaEditSync` 里，只有一条路是对的）：

| 路 | 入口 | 原来怎么做 | 真机表现 |
|---|---|---|---|
| 普通输入 | `commit()` / `commitSelection()` | `spliceBlockSource()` + `reRenderBlock()` ⇒ **块级** | 便宜、不闪 ✔ |
| 结构性编辑 | `commitRange()` / `splitParagraph()` / 边界插空行 / 图片块 / 撤销重做 | 改完源码调 `renderPreview(state.doc)` ⇒ **整篇**重解析 + 重建 30 万节点 DOM + 整篇 MathJax/mermaid，且 `renderPreview` 会先插一句"渲染中"把高度塌掉 | **卡顿 + 上下闪动 + 光标乱跳** ✘ |

**修法**：结构性编辑也走块级 —— `paintPreviewAfterSourceEdit()` 用"**全量解析 + 公共前后缀差分**"找出真正
变化的块区间，只重建那几块（`R.renderBlock` + **重编块下标** + `stampBlockLines` + 只对新块排公式/补链接/渲图），
任一不变量不成立就由 `repaintPreview()` 退回整篇 `renderPreview()`。

本文件钉的是**契约**（不是 DOM 行为）：① 5 个编辑提交点全部改走 `repaintPreview()` 且**再没有**"编辑后整篇重渲"；
② 差分口径必须与 `renderPreview()` **同一份准备好的源**（数学标准化 + 图片路径重写），否则 AST 会不一致；
③ 不变量与兜底必须都在（块数对不上 / 找不到落点 / 抛异常 ⇒ 整篇重渲）；④ 好的那条路（普通输入）不许被改动。
"""

from __future__ import annotations

from pathlib import Path

_APPJS = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app" / "js" / "app.js"


def _js() -> str:
    return _APPJS.read_text(encoding="utf-8")


def test_every_preview_edit_commit_goes_through_the_block_level_entry() -> None:
    """5 个"预览区编辑提交"点全部改走 `repaintPreview()`；**全仓不再有"编辑后整篇重渲"这种写法**。"""
    js = _js()
    assert js.count("repaintPreview()") >= 6, "1 个定义 + 5 个调用点（定义处那句注释里还会再提一次）"
    for why in (
        "撤销/重做也走**块级提交**",           # applySnapshot
        "**结构性编辑的块级提交**",             # commitRange（回车拆段 / 退格合并 / 跨块删除）
        "边界插空行也走块级提交",               # insertAtNonEditableDock
        "图片块结构编辑也走块级提交",           # 图片块结构编辑
    ):
        assert f"repaintPreview().then(function () {{   // 2026-09-25：{why}" in js, f"漏了：{why}"
    # 第 5 处 = `splitParagraph()`（**回车**，人最常触发的那条）：理由写在上一行
    assert "// 2026-09-25：**回车拆段（最常走的那条）改为块级提交** —— 原来这里整篇重渲" in js
    assert "      repaintPreview().then(function () {" in js
    assert "renderPreview(state.doc).then" not in js, (
        "预览区编辑提交后**不许**再整篇重渲 —— 那正是「回车卡顿 + 上下闪动」的来源"
    )


def test_the_diff_uses_exactly_the_same_prepared_source_as_the_full_render() -> None:
    """差分解析必须与 `renderPreview()` 同一份**准备好的源**（否则 AST 不一致 ⇒ 误判成整篇、光标下标可能对不上）。"""
    js = _js()
    prep = 'body = MP0 && typeof MP0.normalizeBody === "function" ? MP0.normalizeBody(body) : body;'
    assert js.count(prep) == 2, "`renderPreview()` 与新块级提交各一份，必须逐字相同（改一处要改两处）"
    assert js.count("body = rewriteMdImagePaths(body);") == 2
    assert "// ⚠️ **必须与 `renderPreview()` 用同一份\"准备好的源\"**" in js


def test_the_block_level_patch_reindexes_rebuilds_and_falls_back() -> None:
    """四条纪律都在：① 换 AST + `M.setDoc`；② 只重渲变化区间；③ **重编块下标**；④ 不成立就退回整篇。"""
    js = _js()
    assert "function paintPreviewAfterSourceEdit() {" in js
    assert "function _paintBlockSpan(container, preview, i, oldSpan, newSpan) {" in js
    assert "function repaintPreview() {" in js
    # ① 差分的产物必须是"与整篇解析同源"的 AST：整体换引用 + 让 mapper 跟着换（`restoreCursor` 靠它换回 DOM）
    assert "_doc = fresh; if (M && typeof M.setDoc === \"function\") M.setDoc(_doc);" in js
    # ② 差分：**基准必须是"DOM 现在渲染的是什么"**（`_domBlockSig`），不能是 `_doc.blocks`（见下一个用例）
    assert "while (i < lim && same(_domBlockSig[i], newB[i])) i++;" in js
    assert "while (k < lim2 && same(_domBlockSig[oldB.length - 1 - k], newB[newB.length - 1 - k])) k++;" in js
    assert "var oldSpan = oldB.length - i - k, newSpan = newB.length - i - k;" in js
    assert "var k = 0, lim2 = Math.min(oldB.length - i, newB.length - i);" in js, "后缀差分的上界要先扣掉前缀"
    # ③ 重编块下标（`stampBlockLines()` 是按 `data--block-index` 反查元素的）
    assert 'for (var j = 0; j < all.length; j++) all[j].setAttribute("data--block-index", String(j));' in js
    assert "if (all.length !== _doc.blocks.length) return false;" in js, "不变量：`.-src-block` 与 `doc.blocks` 一一对应"
    assert "stampBlockLines(preview, _doc);" in js
    # ③b `stampBlockLines()` 是**重新绑定** `_blockLineMap` 的 ⇒ 外部那份（编辑模块 / keys-debug）必须同步换掉
    assert js.count("window.__blockLineMap = _blockLineMap;") >= 4, "整篇渲 / 缓存恢复 / 块级补（两条出口）各一处"
    # ③c 新出现的代码块/表格等仍要"禁编辑"（与 `renderPreview()` 第 4 步同一份选择器）
    assert "var NEC = 'mjx-container, pre, code, table, svg, .-mermaid-container, .-mermaid-error, .-lightbox-overlay';" in js
    assert "与 `renderPreview()` 第 4 步同一份选择器" in js
    # ④ 兜底：找不到落点 / 块数对不上 / 抛异常 ⇒ 整篇重渲（老路径）
    assert "if (!first && oldSpan > 0) return false;" in js
    assert "return renderPreview(state.doc);" in js
    assert 'log("render", "块级提交失败 ⇒ 退回整篇重渲: "' in js
    # 只处理**新块**（不碰整篇）：公式 / wikilink / mermaid
    assert "window.MathJax.typesetPromise(made)" in js
    assert 'if (!made[t].querySelector("code.language-mermaid")) continue;' in js
    assert "try { postProcessWikilinks(); bindPreviewLinks(); }" in js


def test_the_diff_baseline_is_the_dom_not_the_mutated_ast() -> None:
    """**真机 bug（2026-09-25，AG100，我引入的）**：`ada⏎啊SD阿松大D啊S` 在第二行行首退格 ⇒ 预览**只剩 `ada`**；
    再退一次才露出合并结果 `ad啊SD阿松大D啊S`。

    **机制**：「行首退格合并」这条分支会**先就地改 AST**（`prevBlock.children = mergeAdjacentInline(...)`），
    然后才写源码、再调块级提交。而块级提交的差分原来拿 `_doc.blocks`（**已被就地改过**）当基准 ⇒ 那个块被判成
    "没变" ⇒ **跳过重渲** ⇒ DOM 停在旧文本、AST/源码已是新文本（AST↔DOM 错位）。
    ⇒ 修法：差分基准改为 `_domBlockSig`（"这个 DOM 现在逐块渲染的是什么"），并在四处维护它：
    整篇渲染、缓存搬回、`reRenderBlock()`（单块）、块级提交（区间 splice）。"""
    js = _js()
    assert "var _domBlockSig = null;" in js and "function _previewBlockSig(b) {" in js
    assert "same(oldB[i], newB[i])" not in js, "不许再拿 `_doc.blocks` 当差分基准（那正是这个 bug）"
    assert "if (!_domBlockSig || _domBlockSig.length !== oldB.length) return false;" in js, (
        "没登记 / 与块数不符 ⇒ 老实整篇重渲（不许冒险）"
    )
    # 四处维护点
    assert js.count("_domBlockSig = _doc.blocks.map(_previewBlockSig);") == 2, "整篇渲染 + 缓存搬回"
    assert "_domBlockSig[blockIndex] = _previewBlockSig(_doc.blocks[blockIndex]);" in js, "`reRenderBlock()` 单块"
    assert "Array.prototype.splice.apply(_domBlockSig, [i, oldSpan].concat(sigs));" in js, "块级提交区间 splice"


def test_the_hot_path_only_touches_the_edited_lines_and_block() -> None:
    """人（2026-09-25）：「**预览区域编辑体感很差，因为输入进去没有反应，是等渲染之后才显示编辑内容，
    为什么不是先显示编辑内容然后再同步呢**」。

    病根不在"没先显示"，而在**同步本身太重**（重到把这一帧占满，字符只能等它做完才画出来）：
      · `renderEditor()` 是**整篇重建**（每行一个 `.-line` 元素）⇒ 5888 行的文档**每敲一键**重建 5888 个元素；
      · `reRenderBlock()` 原来把**整篇预览**再排一遍 MathJax（`typesetPromise([container])`），
        并用 `postProcessWikilinks()` / `bindPreviewLinks()` 扫**全部**链接。
    两处都改成"只动改动的那几行 / 那一块" ⇒ 主线程敲完就空出来，字符当帧画出 ✔（AST/源码仍**同步**更新，
    所以不存在"先显示、后同步"的时序风险 —— 只是把 O(文档) 降成 O(改动)）。"""
    js = _js()
    # ① 源码面板增量更新：函数 + 三个热路径调用点 + 兜底
    assert "function patchEditorLines(startLine, oldCount, newCount) {" in js
    assert "if (!_sp || !patchEditorLines(_sp.start, _sp.oldCount, _sp.newCount)) renderEditor(state.doc);" in js
    assert "if (!_sp2 || !patchEditorLines(_sp2.start, _sp2.oldCount, _sp2.newCount)) renderEditor(state.doc);" in js
    assert "if (!patchEditorLines(startLine, endLine - startLine + 1, newLines.length)) renderEditor(state.doc);" in js
    assert "return { start: start, oldCount: oldCount, newCount: newLines.length };" in js, (
        "`spliceBlockSource()` 要把「改了哪几行」回报给调用方（源码面板才谈得上增量）"
    )
    assert 'for (var d = startLine + newCount; d < all.length; d++) {' in js, "行数变化时必须重编后续 `data-line`"
    # ② 后处理只对"这一块"（否则每次按键都付整篇的钱）
    assert "window.MathJax.typesetPromise(_madeBlock ? [_madeBlock] : [container])" in js
    assert "postProcessWikilinks(_madeBlock || undefined);" in js and "bindPreviewLinks(_madeBlock || undefined);" in js
    assert "function postProcessWikilinks(root) {" in js and '(root || preview).querySelectorAll(".-wikilink")' in js
    assert "function bindPreviewLinks(root) {" in js and '(root || preview).querySelectorAll(".memoria-link:not([data--bound])")' in js


def test_preview_typing_is_native_first_and_the_jump_re_anchors() -> None:
    """人两条真机反馈（2026-09-25）：

      A「**看到预览区域输入的时候，是先在源码区域输入的，这个是不对的，因为我们基础设施是双向映射，可以双向同步，
        你这个南辕北辙会导致输入卡顿，而且现在仍然是输入等一会才有反应**」
        ⇒ **原生优先**（AG103）：在预览里敲字，DOM 里的字是浏览器原生敲进去的、**那一刻就已经对了** ⇒ 只把**另一侧
        （AST + 源码面板）**同步过去；那一块的"渲染态归一"推迟到**停手 ~180 ms** 再渲一次。
        护栏：IME 组合中不渲 / 停手期间又敲则计时重来 / 渲完若光标还在该块就放回去 / 结构性提交先**取消**挂起的重渲 /
        暂存进缓存前先 **flush**（别把没归一的 DOM 存进池）。
      B「**现在预览区域知识点跳转定位位置又不准了**」
        ⇒ **跳转落点二次校准**（AG104）：`scrollIntoView` 那一刻异步排版还没落（MathJax 排队跑、懒加载图片 0 高）⇒
        落点会漂；在 ~350 ms / ~1.4 s 各再对准一次，且**用户一自己滚动/点击/触摸/按键就放弃**（不抢滚动条）。"""
    js = _js()
    # A · 原生优先
    assert "function _scheduleBlockRepaint(blockIndex) {" in js and "function _flushBlockRepaint() {" in js
    assert "if (EH && EH._composing) return;" in js, "IME 组合中不重渲（等 compositionend 之后那次停手）"
    assert "}, 180);   // ② 停手才渲" in js
    assert "if (keepCaret) restoreCursor(cur.blockIndex, cur.nodePath, cur.offset);" in js, "重渲后把光标放回去"
    assert "function _cancelBlockRepaint() {" in js
    assert js.count("_cancelBlockRepaint();") >= 2, "结构性提交两处（commitRange / splitParagraph）要取消挂起的重渲"
    assert "flushRepaint: _flushBlockRepaint," in js
    assert 'window.MemoriaEditSync.flushRepaint();' in js, "暂存进缓存前先 flush（否则池里存的是没归一的 DOM）"
    # B · 跳转落点二次校准
    assert "function _reanchorJumpScroll(startLine, endLine) {" in js
    assert "_reanchorJumpScroll(startLine, endLine);" in js, "必须由 `highlightPreviewRange` 那次滚动触发"
    assert '["wheel", "mousedown", "touchstart", "keydown"].forEach(function (ev) {' in js, "用户一动就放弃校正"
    assert 'first.scrollIntoView({ block: "start", behavior: "auto" });' in js
    assert "tick(350); tick(1400);" in js


def test_the_typing_path_stays_block_level_and_is_not_touched() -> None:
    """**好的那条路不许被改动**：普通输入仍是 `spliceBlockSource()` + `reRenderBlock()`（本来就便宜不闪）。
    （AG102 起 `reRenderBlock` 多带一个 `keepLineMap` 实参：行数没变时不重算块→行映射。）"""
    js = _js()
    assert "function commit(block, cursor, nativeDone) {" in js and "function commitSelection(block, blockIndex, selStart, selEnd) {" in js
    assert js.count("spliceBlockSource(cursor.blockIndex, G.generateBlock(block));") == 1
    assert js.count("spliceBlockSource(blockIndex, G.generateBlock(block));") == 1
    assert "reRenderBlock(cursor.blockIndex, _sameLines);" not in js, "打字路径已改为**原生优先**（AG103：不在按键当刻重渲，见下一个用例）"
    assert "_scheduleBlockRepaint(cursor.blockIndex);" in js
    assert "reRenderBlock(blockIndex, !!_sp2 && _sp2.oldCount === _sp2.newCount);" in js, "格式/样式这类**离散操作**仍是立刻重渲"


def test_the_keystroke_path_skips_the_o_document_restamp() -> None:
    """人（2026-09-25）：「**输入内容的操作，仍然是等好一会才加载输入的内容**」。两处真凶：

    ① **每次按键都白付一趟 O(文档) 的 `stampBlockLines()`** —— 打字/行内格式化**不改"块→行"映射**（行数没变 ⇒
       映射逐字不动），但原来每键都重算（5888 行逐行走正则 + 4000 块写 `data--src-line`）⇒ 跳过。
    ② **`keys-debug.js` 是常驻的诊断埋点**：它猴补 `console.log`（全应用日志都要过它），并在每次输入后做
       **300 ms / 1000 ms 两趟整篇正文 diff** ⇒ 平时开着会实打实拖慢编辑 ⇒ 改成**按需开启**（默认关）。
    另：`commit()` 里加了"按键 → 预览更新"整条链的计时（> 20 ms 才打 `[EDIT]` 一行），下次手感有疑可以看数。"""
    js = _js()
    # ① `keepLineMap` 旁路
    assert "function reRenderBlock(blockIndex, keepLineMap) {" in js
    assert "if (!keepLineMap) stampBlockLines(preview, _doc);" in js
    # ③ 按键链路计时（只打慢的）
    assert 'log("EDIT", "按键提交 " + Math.round(_ms) + "ms · 行 "' in js
    # ② keys-debug 默认关 + 两种开启方式；关闭时**不猴补 console、不装监听**
    kd = _APPJS.parent / "keys-debug.js"
    assert kd.exists(), "诊断埋点文件还在（默认关即可，不必删）"
    text = kd.read_text(encoding="utf-8")
    assert 'var __kdbgOn = false;' in text and "if (!__kdbgOn) return;" in text
    assert 'localStorage.getItem("-keys-debug") === "1"' in text
    assert "/[?&]kdbg=1(?:&|$)/.test(location.search)" in text
    assert text.index("if (!__kdbgOn) return;") < text.index("console.log = function ()"), (
        "必须在**猴补 console.log 之前**判掉，否则关闭状态仍然拖慢全应用日志"
    )


def test_the_view_anchor_is_taken_before_the_rerender_and_only_native_typing_defers() -> None:
    """人（2026-09-25）两条真机反馈：

      A「**从预览区域切换分栏等其他模式仍有位置漂移**」
        ⇒ `setViewMode()` 切模式会 `renderEditor()` + `await renderPreview()`，**两个视图都被刷回顶部**；
          而锚点原来是在**之后**才量的（`_getViewTopSrcLine(prevMode)`）⇒ 量到的永远是"第一行"。
          （AG82 用 `keepPosition()` 修过同一条，但它随 K4a 窗口化一起被 AG97 删掉 ⇒ 漂移回归。AG105 用
          "**重渲染之前先把锚点与滚动位置采下来**"复原，不依赖任何窗口化设施。）
      B「**是先在源码区域输入的…现在仍然是输入等一会才有反应**」
        ⇒ `commit()` 原来对**所有**入口都推迟 180 ms 才重渲预览那一块；而 `beforeinput` 那条路我们
          `preventDefault()` 了（DOM 由**我们**负责更新）⇒ 那 180 ms 里源码面板已经变了、预览却没动，
          正是人看到的"先源码、后预览"。修法：`nativeDone`（只有 IME 的 `compositionend` 才有）⇒ 只推迟
          "渲染态归一"；其余入口**先画预览、再同步源码面板**。"""
    js = _js()
    # A · 锚点/滚动位置先采、后重渲（顺序是本用例的核心）
    cap = "const body = collectEditorBody();   var _viewAnchorBeforeRerender = _getViewTopSrcLine(prevMode); _saveCurrentViewScroll(prevMode);"
    assert cap in js, "重渲染**之前**就要采锚点与滚动位置"
    assert js.index(cap) < js.index("renderEditor(state.doc);\n      await renderPreview(state.doc);"), (
        "锚点必须在 `renderEditor()`/`renderPreview()` **之前**采 —— 否则量到的是被刷回顶部后的第一行"
    )
    assert "anchorLine = _viewAnchorBeforeRerender;" in js
    assert "anchorLine = _getViewTopSrcLine(prevMode);" not in js, "不许再在重渲染之后现量锚点（那正是漂移的来源）"
    assert "// 2026-09-25 AG105：`_saveCurrentViewScroll(prevMode)` 已**上移到重渲染之前**" in js, (
        "滚动位置同理：重渲染之后再存，存到的是 0"
    )
    # B · "原生优先"只对"浏览器已经画好"的那条路生效
    assert "if (nativeDone) _scheduleBlockRepaint(cursor.blockIndex);" in js
    assert "else reRenderBlock(cursor.blockIndex, !!_sp && _sp.oldCount === _sp.newCount);" in js, (
        "非原生路（`beforeinput` 里我们 `preventDefault()` 了）**必须当刻把预览画出来**，否则就是「先源码、后预览」"
    )
    assert "var ok = commit(block, cursor, nativeDone);" in js, "`insertText()` 要把 `nativeDone` 透给 `commit()`"
    eh = (_APPJS.parent / "edit-handler.js").read_text(encoding="utf-8")
    assert "EditSync.insertText(committed, true, true);" in eh, "只有 IME 的 `compositionend` 那条路能标 `nativeDone`"
    # 定时器到点时若又开始了新一次组合 ⇒ 把重渲再往后推（否则会换掉正在组合的 DOM 节点、浏览器中断组合）
    assert "if (EH && EH._composing) { _repaintBlock = bi;" in js

