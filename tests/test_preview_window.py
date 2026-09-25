"""预览**窗口化渲染**（K4a，2026-09-24）的契约钉子 —— 只读预览里"先渲染看得到的、再补其余的"。

人（2026-09-24）：「能不能做成先渲染看的到的部分，然后再渲染看不到的部分，这样切换文件不就快了……
  ① 在显示区域有页签的文件可以暂存上次位置渲染双向做；② 新打开加入的文件从头开始，渲染就是往下做；
  ③ 跳转方式进入文件，和 ① 一样双向渲染，定位过程可以在已经渲染的包含定位点的"窗口"里"播放"」。
滚条口径由人拍板：**按屏数**（上下各 2 屏）、**拖动时松手才渲**、本期先接受「原生 Ctrl+F 只搜得到已渲染窗口」。

**为什么它是治本的那一刀**（真机读数）：脚本只花 335 ms 而 `paint` 等到 1788 ms —— 那 ~1.45 s 是浏览器对
**整篇 30 万节点**做样式/布局/绘制；`content-visibility` 只让浏览器"跳过"，节点仍在文档里（1833 → 1788 ms
＝没搬动）⇒ 必须把窗口外的块**换出 DOM**。

本文件钉的是**契约**（模块在哪、常数是人的决定、三个入口都接上了、切走时全量物化、异常与编辑模式都退回
全量渲染）；算法细节是 DOM 行为，靠真机读数验收（`paint` 应大幅下降）。
"""

from __future__ import annotations

import re
from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
_APPJS = _APP / "js" / "app.js"


def _js() -> str:
    return _APPJS.read_text(encoding="utf-8")


def test_window_engine_is_appended_at_the_very_end_and_exported() -> None:
    """整块**追加在 app.js 末尾**（既有 `app.js:<行号>` 锚点零漂移），并对外只暴露一个小门面。"""
    js = _js()
    assert "(function memoriaPreviewWindow() {" in js
    assert "window.MemoriaPreviewWindow = {" in js
    assert js.index("memoriaPreviewWindow") > js.index("(function memoriaWriteGuard() {"), "必须追加在末尾（零漂移）"
    for name in ("attach", "detach", "ensureLine", "setAnchorLine", "claimScroll", "captureAnchor", "stats"):
        assert f"    {name}: {name}," in js, f"对外要导出 {name}"


def test_the_human_s_decisions_are_written_into_constants() -> None:
    """三个拍板都落到常数上：**按屏数** / **松手才渲** / 跳变阈值。"""
    js = _js()
    assert "const SCREENS = 2;" in js, "窗口 = 上下各 2 屏（人是「按屏数」口径，不是块数）"
    assert "const MARGIN_SCREENS = 1;" in js, "距窗口边缘还剩 1 屏就开始补"
    assert "const JUMP_SCREENS = 1;" in js, "一次滚过一屏以上 ⇒ 视为跳变（拖滚条 / PageDown）"
    assert "const DRAG_SILENCE_MS = 150;" in js, "没有 scrollend 时「松手」的判定兜底"
    assert "const MIN_SLOTS = 120;" in js, "小文档不窗口化（不值得多一层间接）"
    assert 'p.addEventListener("scrollend", function () { if (st) _settle(st); }, { passive: true });' in js, (
        "有 scrollend 就用它 —— 这正是「松手才渲」的原生信号（现在绑在**模块级**探针上）"
    )
    assert "const EST_PX = 96;" in js and "const BLANK_EST_PX = 18;" in js, (
        "未测量块的估值要按块类型分档（空行块矮得多，跟着正文估会把总高吹成好几倍）"
    )


def test_edit_mode_is_taken_over_but_with_caret_safeguards() -> None:
    """**编辑模式也接管**（人 2026-09-24 实测：他的工作方式就是编辑模式，而原先这里早退 ⇒ 窗口化在他那儿
    一次都没生效）。风险由两条安全阀兜住：① 占位块**不可编辑、不可选中**（否则点一下就能把内容写进一个
    随时被丢掉的盒子）；② **光标/选区所在块永不摘走**（`_caretSlots`，摘了就是丢光标 / 丢 IME 组合）。"""
    js = _js()
    assert "const editing = _editing(preview);" in js and '_skip("edit-mode")' not in js
    assert "st = { preview: preview, pane: pane, slots: slots, from: 0, to: slots.length - 1, lastTop: -1, raf: 0, timer: null, editing: editing };" in js
    assert "const span = _screenSlots(slots, SCREENS + (editing ? 1 : 0));" in js, "编辑模式多留一屏（少搬窗 ⇒ 少打扰光标）"
    assert "const keepSet = s.editing ? _caretSlots(s) : null;" in js
    assert "if (keepSet && keepSet.has(i)) continue;" in js, "光标/选区所在块必须跳过（不摘走）"
    assert 'd.contentEditable = "false";' in js, "占位块不可编辑"
    assert "} catch (e) {\n      _skip(\"throw\", (e && e.message) || String(e));" in js, "异常一律退回全量"


def test_the_three_entries_from_the_human_are_wired() -> None:
    """入口 ①（有页签 ⇒ 上次位置、双向）/ ②（新打开 ⇒ 文档头）/ ③（跳转 ⇒ 先物化目标块）。"""
    js = _js()
    # ① 缓存命中：带上锚点（槽下标 + 块内偏移）
    assert "window.MemoriaPreviewWindow.attach(preview, { anchor: entry.anchor, scrollTop: entry.scrollTop });" in js
    assert "window.MemoriaPreviewWindow.captureAnchor($(\"#preview-pane\"), preview)" in js, (
        "切走时要把锚点（槽下标 + 块内偏移）记进缓存条目 —— 裸 `scrollTop` 像素在高度估值下会飘"
    )
    # ② 冷渲染收尾
    assert "window.MemoriaPreviewWindow.attach(preview, {});" in js
    # ③ 跳转：**目标行先定锚再渲染**（人 2026-09-24：「直接渲染对应位置的窗口，从该窗口的开头播放定位」），
    #    另有两条定位路径把目标块**先物化**（源码行定位 / 预览区间高亮：KP、wikilink、搜索、检查面板都走它们）
    assert "window.MemoriaPreviewWindow.setAnchorLine(_jLine);" in js
    assert "const _jumpIdx = pendingLine ? _slotOfLine(slots, pendingLine) : -1; pendingLine = 0;" in js, (
        "`attach` 必须**优先**用跳转目标行定锚（且用完即清）—— 否则会先渲旧位置/文档头、卡一会、再跳过去"
    )
    assert "window.MemoriaPreviewWindow.ensureLine(lineNum);" in js
    assert "window.MemoriaPreviewWindow.ensureLine(startLine);" in js


def test_stash_still_sees_the_whole_tree_and_pixel_writes_step_aside() -> None:
    """切走前**全量物化** ⇒ `_previewCacheStash()` 一行未改（池的条目格式、`_estimatePreviewBytes`、
    既有考古工具全不受影响）；恢复时那两处裸像素写要让路（锚点已经定过位置）。"""
    js = _js()
    assert 'var _pvAnchor = window.MemoriaPreviewWindow ? window.MemoriaPreviewWindow.captureAnchor($("#preview-pane"), preview) : null; if (window.MemoriaPreviewWindow) { window.MemoriaPreviewWindow.detach(preview); window.MemoriaPreviewWindow.markLoad(); }' in js, (
        "锚点必须**在窗口态下先量**（占位块的位置 = 恢复时那套估值的口径 ⇒ 前后自洽、且不读整棵树），"
        "然后才全量物化；顺序反过来会让那一次几何读变成**整棵树的强制布局**（等于把窗口化省下的又付回去）"
    )
    assert "scrollTop: pane ? pane.scrollTop : 0, anchor: _pvAnchor," in js, "条目里存的必须是那个先量好的锚点"
    assert js.count("!(window.MemoriaPreviewWindow && window.MemoriaPreviewWindow.claimScroll())") == 3, (
        "三处裸像素写（恢复路径 / `_restoreTabScroll` / `_restoreCurrentViewScroll`）都要先问一句 claimScroll()"
        "（第三处是 AG83 补的：与第一处同款写法，原来漏了）"
    )
    # 新块进窗时就地补链接：本块拿不到主 IIFE 的闭包 ⇒ 只经 facade 上那两个**幂等函数引用**
    assert "window.MemoriaApp.pvPostWikilinks = postProcessWikilinks; window.MemoriaApp.pvBindLinks = bindPreviewLinks;" in js
    assert "A.pvPostWikilinks()" in js and "A.pvBindLinks()" in js


def test_spacers_carry_the_lookup_attributes_and_a_measured_height() -> None:
    """占位块两条硬要求：① 带上 `data--block-index` / `data--src-line*`（否则行号定位会"找不到"）；
    ② 离开窗口时先**量真高**再写死在占位块上（滚动条越用越准，且只有一趟读 ⇒ 一次布局）。"""
    js = _js()
    assert 'd.setAttribute("data--block-index", slot.bi);' in js
    assert 'd.setAttribute("data--src-line", slot.line); d.setAttribute("data--src-line-end", slot.lineEnd);' in js
    assert 'slot.spacer.style.height = _h(slot) + "px";' in js
    assert "const h = leaving[k].node.offsetHeight; if (h > 0) leaving[k].h = h;" in js


def test_cold_render_is_not_blind_in_the_readout() -> None:
    """**冷渲染**（未命中）原来没有 `frame1` / `paint`（它们只打在那条"命中恢复"里）⇒ 一旦未命中，读数就成了瞎的
    （真机：`画面 — ms`，而 `render 1837 ms` 无从归因）。这例钉住：冷渲染收尾也打同款双 rAF，并加 `postRender`
    阶段把"整条渲染流水线"与"attach + `setViewMode` 收尾"切开。"""
    js = _js()
    assert '_markPhase("postRender"); if (window.MemoriaPreviewWindow) window.MemoriaPreviewWindow.attach(preview, {});' in js
    assert '_markAsync("frame1", _o); window.requestAnimationFrame(function () { _markAsync("paint", _o); });' in js
    assert "if (window.requestAnimationFrame) { const _o = _switchAbs;" in js, "起点注册时捕获（旧一轮才能被丢掉）"


def test_debug_readout_and_wheel_fallback_are_wired() -> None:
    """人（2026-09-24）：「仍然无法滚动，要调试日志」⇒ 读数必须能一眼回答四个判据：

    `wheel` 不涨 = 滚轮事件**没到预览区**；`wheel` 涨而 `scrolls` 不涨 = 事件到了**窗格没滚**（`fallback` 会 >0）；
    两者都涨而画面不动 = **窗口没跟随**（看 `log` 里的 `move` 轨迹）；`max` 为 0 = **窗格根本不可滚**。
    另：跳转取证靠 `anchorLine`（交给窗口的目标行）与 `jumpIdx`（它在槽位表命中的下标，-1 = 没找到）。"""
    js = _js()
    # **模块级探针**：不依赖"是否接管" —— 人实测过"窗口 -1–-1/0 而日志只有 anchorLine"，那时监听没绑，
    # 于是"没接管"和"事件没到"在读数里长得一模一样 ⇒ 探针改为模块加载即绑（`_boot()`）。
    assert "_boot();   // **模块加载即绑好探针**" in js
    assert 'p.addEventListener("wheel", function (e) {' in js
    assert 'p.addEventListener("scroll", function () {' in js
    assert '_log("wheel(未接管) dy="' not in js, (
        "滚轮**不进日志**（只计数）—— 人实测：149 次滚轮把 8 条环形缓冲全占满，把 `attach?`/`attach✗` 挤掉了"
    )
    assert 'dbg.wheel++;   // 只计数' in js
    assert 'var dbg = { wheel: 0, scrolls: 0, fallback: 0, attach: 0, skip: "", anchorLine: 0, jumpIdx: -1, top: 0, max: 0, log: [],' in js
    assert "edit: { n: 0, in: 0, t0: 0, a0: 0, m0: 0, wait: 0, render: 0, attach: 0, links: 0, math: 0 } };" in js
    assert "dbg.attach++; dbg.skip = \"\";" in js, "接管次数与「上次跳过原因」要能在读数上直接看到（`skip` 不会被环形缓冲挤掉）"
    for key in ("attach", "skip", "wheel", "scrolls", "fallback", "anchorLine", "jumpIdx", "top", "max", "smooth", "log"):
        assert re.search(rf"^\s+{key}: ", js, re.M), f"`stats()` 要出 {key}（读数据此判因）"
    assert 'rows: rows, win: (window.MemoriaPreviewWindow && typeof window.MemoriaPreviewWindow.stats === "function")' in js
    assert "perfLiveWin" in (_APP / "js" / "display-settings.js").read_text(encoding="utf-8")


def test_attach_never_fails_silently() -> None:
    """人（2026-09-24）实测读数：`窗口 -1–-1/0（真身 0）` + 日志只有 `anchorLine=4163` ⇒ **窗口化一路没接管**，
    而日志里**看不出是哪一步退的** ⇒ 每个早退分支都必须留一行原因（含异常）。"""
    js = _js()
    assert '_skip("no-preview")' in js and '_skip("no-pane")' in js
    assert '_skip("slots<" + MIN_SLOTS, slots.length)' in js
    assert '_skip("throw", (e && e.message) || String(e));' in js, "异常也要留证（原来静默退回）"
    assert 'dbg.skip = s; _con("attach✗ " + s, true); _log("attach✗ " + s);' in js, "跳过原因要写进 `dbg.skip`（环形缓冲会被滚轮挤掉，这个字段不会）**且同时进控制台**"
    assert '_log("attach? edit=" + (preview ? String(preview.contentEditable) : "-") + " children="' in js, (
        "进来就记一行（编辑模式与子节点数一眼看出）"
    )


def test_jump_target_beats_the_saved_anchor() -> None:
    """跳转**优先于**「恢复上次位置」：文件看过一次时，缓存锚点曾把目标行顶掉 ⇒ 于是"先渲旧位置、再跳过去"（人实测）。"""
    js = _js()
    assert "const _jumpIdx = pendingLine ? _slotOfLine(slots, pendingLine) : -1; pendingLine = 0;" in js
    assert "const anchorIdx = (_jumpIdx >= 0) ? _jumpIdx : ((a && typeof a.i === \"number\")" in js, (
        "命中缓存（有 `a`）时也必须让目标行优先"
    )
    assert "const off = (_jumpIdx >= 0) ? pendingOff :" in js, "跳转落到目标块**块首**（人：「从该窗口的开头播放定位」）"
    assert "pendingOff = off;" in js, (
        "而**位置携带**（编辑/切模式重渲）要把**块内偏移一起带** —— 否则每次重渲都把块顶对齐到视口顶，"
        "真机表现就是「每次回车画面都往上跑」"
    )
    assert "pendingOff = 0;   // **跳转一律落块首**" in js, "跳转入口把偏移清 0（`keepPosition()` 之后再把真实偏移覆盖回来）"


def test_slots_come_from_blocks_not_from_preview_children() -> None:
    """**实测踩到的真根因**（2026-09-24）：渲染器把整篇包在**一个** `<div class="-preview-content">` 里
    （`renderer.js:52`）⇒ `#preview` **只有 1 个子节点** ⇒ 若按"直接子节点"摊槽位表就只摊出 1 个槽、
    被 `MIN_SLOTS` 挡下（真机日志：`attach✗ slots<120 1`）⇒ 窗口化**一次都没生效**。
    ⇒ 槽位表必须按**块元素**摊，而且换窗要**走每个槽自己的父节点**。"""
    js = _js()
    assert 'const nodes = preview.querySelectorAll(".-src-block[data--block-index]");' in js
    assert "host.replaceChild(_spacer(leaving[k]), leaving[k].node);" in js, "离窗走各自父节点"
    assert "host.replaceChild(slot.node, _spacer(slot));" in js, "进窗同理"
    assert "if (!slot.node.parentNode) continue;" in js, "「是否已物化」的判据是 `node.parentNode`（与容器无关）"
    assert "renderer.js" in js, "注释里要留下这个坑的来处（免得以后有人又按子节点摊）"


def test_every_full_render_carries_the_position_over() -> None:
    """人（2026-09-24）：「**跳转之后编辑行为会导致回到文件开头**，顺便检查一下其他有没有这种编辑回到开头」。
    真因：`renderPreview()` 用 `preview.innerHTML = '<p class="-preview-loading">…'` **先把预览清成一行** ⇒ 滚动位置
    被夹到 0；而**每次编辑**都会走全量重渲染（`scheduleRenderSync → syncSourceToPreview → renderPreview`）⇒ 回开头。
    ⇒ 在**清 DOM 之前**（`const token = ++state.previewToken;` 那一行）就要 `keepPosition()`。

    同一轮把"其它会回开头的口子"逐个查了：
      · `_restoreCurrentViewScroll()` 写裸像素 `previewPane.scrollTop = tab.previewScroll` —— 第 1317 行有 `claimScroll()` 守卫，**这里漏了** ⇒ 补上；
      · `renderPreviewAST()`（`preview.innerHTML = ""`）**无任何调用点**（死代码）⇒ 不改；
      · 第 541 / 634 / 1343 行的 `preview.innerHTML = ""` 都是**清空/关文件**类路径（旁边还有 `editor.innerHTML = ""` 与 `fileMeta`），不是编辑触发、文档本身也换了 ⇒ 无需保位置。
    """
    js = _js()
    assert "window.MemoriaPreviewWindow.keepPosition();   // 2026-09-24 窗口化（K4a）：**下面那行 `preview.innerHTML`" in js
    i_hook = js.index("window.MemoriaPreviewWindow.keepPosition();   // 2026-09-24 窗口化（K4a）：**下面那行")
    i_clear = js.index("preview.innerHTML = '<p class=\"-preview-loading\">' + T(\"preview.rendering\") + '</p>';")
    assert i_hook < i_clear, "必须在清 DOM **之前**量（清完就只剩一行、量不到顶部块了）"
    assert (js.count("!(window.MemoriaPreviewWindow && window.MemoriaPreviewWindow.claimScroll())") >= 2), (
        "两处裸像素恢复（页签恢复与 `_restoreCurrentViewScroll`）都要有 `claimScroll()` 守卫"
    )
    assert "function renderPreviewAST(body) {" in js, "已查：定义存在但无调用点（死代码）⇒ 不必改"


def test_mode_switch_carries_the_position_over() -> None:
    """人（2026-09-24）：「从预览切换到其它模式比如分栏、源码，**位置就会漂移或者回到文件开头**」。
    真因：`setViewMode()` 切模式会**重渲染预览**，那次收尾走的是冷渲染那条 `attach(preview, {})` —— 锚点是
    **文档头** ⇒ 预览先回开头，之后才量"顶部对应哪一行" ⇒ 量到的已是第一行。⇒ 重渲染**之前**用
    `keepPosition()` 把"顶部那一块的源码行"交给窗口（`pendingLine` 用完即清 ⇒ 不污染换文件）。"""
    js = _js()
    assert "keepPosition: keepPosition," in js, "要导出（接线在 `setViewMode` 里）"
    assert "function keepPosition() {" in js
    assert "if (!pv) return 0;" in js, "窗口态/纯 DOM 态都要能取锚点（「过渡」结束后窗口已交还 ⇒ 走纯 DOM 分支）"
    assert "② **纯 DOM 态**" in js and 'const els = pv.querySelectorAll("[data--src-line]");' in js, (
        "纯 DOM 态：直接扫 `[data--src-line]` 取「行 + 块内偏移」（**零估值**，之后由 `_restorePlainPosition()` 按真几何还原）"
    )
    assert "carry = true;   // 告诉渲染侧" in js, "同文档重渲染 ⇒ 让渲染侧别再插「渲染中」占位行（那是「上下闪动」的源头）"
    assert "const caret = _caretSlots(st);" in js, "兜底：量不到顶部块时用光标/选区所在块"
    assert "if (line > 0) { setAnchorLine(line); _log(\"anchorLine=\" + line + \" (caret)\"); return line; }" not in js
    assert "function carrying() { return carry; }" in js and "carrying: carrying," in js, "要导出（渲染侧据此决定清不清屏）"
    assert "if (!incremental && !(window.MemoriaPreviewWindow && window.MemoriaPreviewWindow.carrying())) {" in js
    assert "window.MemoriaPreviewWindow.keepPosition();   // 2026-09-24 窗口化（K4a）：**重渲染前**" in js
    # 关键：必须在 `renderEditor` / `renderPreview` **之前**量（之后预览已经回到开头）
    i_hook = js.index("window.MemoriaPreviewWindow.keepPosition();   // 2026-09-24 窗口化（K4a）")
    i_ed = js.index('syncLog("setViewMode: 重新渲染编辑器和预览");')
    i_render = js.index("await renderPreview(state.doc);", i_ed)
    assert i_ed < i_hook < i_render


def test_edit_path_has_its_own_readout() -> None:
    """人（2026-09-24）：「**还是有略微闪动，特别是按回车，会卡顿一下，现在添加日志我们集中精力优化这个**」
    ⇒ 编辑路径要有**自己的**读数（`lastSwitch*` 那套只在换文件时更新，编辑触发的重渲染根本不进读数）。
    五段：**等待**（`input` → 开始重渲染 = 去抖 + 事件循环被占）/ **全量重渲染**（清屏前量锚点 → `attach` 进来，
    同步 parse+render+stamp）/ **接管** / **补链接** / **排版**（异步）。"""
    js = _js()
    assert "edit: { n: 0, in: 0, t0: 0, a0: 0, m0: 0, wait: 0, render: 0, attach: 0, links: 0, math: 0 }" in js
    assert 'p.addEventListener("input", function () { dbg.edit.in = now(); }, { passive: true });' in js
    assert "if (e.in) { e.n++; e.wait = Math.round(now() - e.in); e.in = 0; }" in js
    assert "if (dbg.edit.t0) { dbg.edit.render = Math.round(now() - dbg.edit.t0); dbg.edit.t0 = 0; }" in js, (
        "`attach` 进来那一刻结算「全量重渲染」—— 这一段最可能是回车卡顿的本体"
    )
    assert "if (dbg.edit.a0) { dbg.edit.attach = Math.round(now() - dbg.edit.a0); dbg.edit.a0 = 0; }" in js
    assert "dbg.edit.links = Math.round(now() - tLinks);" in js
    assert "dbg.edit.math = Math.round(now() - dbg.edit.m0); dbg.edit.m0 = 0;" in js
    assert "edit: dbg.edit," in js, "要经 `stats()` 出去"
    ds = (_APP / "js" / "display-settings.js").read_text(encoding="utf-8")
    assert 'T("settings.display.perfLiveEdit"' in ds
    for name in ("zh-CN", "en"):
        loc = (_APP / "i18n" / f"{name}.js").read_text(encoding="utf-8")
        assert "perfLiveEdit:" in loc, f"{name} 缺 `perfLiveEdit`"
        assert "perfLiveWinLog:" in loc, f"{name} 的 `perfLiveWinLog` 不能被顶掉"


def test_render_pipeline_is_split_into_segments() -> None:
    """人（2026-09-24）读数：**画面 26975 ms**、阶段 `postRender 26679`、`rpEnd -25897` ⇒ 26.7 s 全在
    `renderPreview()` 里面，但**里面哪一步**看不出来。⇒ 把渲染切成 `parse` → `dom` → `stamp` → `mermaid` → `mjStart`
    五段（`markRender()` 由 app 侧那几行同行追加打点，**第一个打点即起点**，读数按"距起点 ms"显示）。
    同一轮还修掉日志抓到的真 bug：`attach✗ throw … 'replaceChild' … not a child of this node` ——
    编辑重渲染把整篇 DOM 换掉后，`detach()` 仍握着**旧槽位表** ⇒ 旧占位块早已不在文档里 ⇒ 那次整篇没接管。"""
    js = _js()
    assert "markRender: markRender," in js and "function markRender(name) {" in js
    assert "function resetRender() { dbg.rp.t0 = 0; dbg.rp.parts = {}; }" in js
    assert "rp: { t0: 0, parts: {} }," in js and "rp: dbg.rp," in js, "要经 `stats()` 出去"
    for name in ("parse", "dom", "stamp", "mermaid", "mjStart"):
        assert f'window.MemoriaPreviewWindow.markRender("{name}")' in js, f"`renderPreview()` 里缺 `{name}` 打点"
    assert "resetRender();  // 新一次渲染 = 新的一轮分段计时" in js
    assert "if (name === \"entry\" || name === \"parse\" || !dbg.rp.t0) { dbg.rp.parts = {}; dbg.rp.t0 = t; }" in js, (
        "**`parse` 自己开新一轮** —— 不能在 `detach()` 里清：`attach()` 内部就会调 `detach()`，一清就把刚采集的分段抹掉"
        "（真机读数里「渲染分段」整行消失就是这条）"
    )
    # 真 bug：旧槽位表的占位块不能再拿去 `replaceChild`
    assert "if (!sp || !sp.parentNode || !pv.contains(sp)) continue;" in js, (
        "只处理仍连着当前 DOM 的占位块（否则 `replaceChild` 抛 not a child of this node —— 真机日志实证）"
    )
    ds = (_APP / "js" / "display-settings.js").read_text(encoding="utf-8")
    assert 'var PERF_RENDER_ORDER = ["entry", "parse", "dom", "stamp", "mermaid", "mjStart", "audit"];' in ds
    assert 'T("settings.display.perfLiveRender"' in ds
    assert "const useWorst = !!(rpWorst && rpWorst.parts && (rpWorst.total || 0) > " in ds, (
        "优先显示**最慢那次**的分段（编辑会把最近一次覆盖掉，而要看的是那个几十秒的冷渲染）"
    )
    assert "rpWorst: { total: 0, parts: {} }," in js and "rpWorst: dbg.rpWorst," in js
    for name in ("zh-CN", "en"):
        loc = (_APP / "i18n" / f"{name}.js").read_text(encoding="utf-8")
        assert "perfLiveRender:" in loc
        assert "perfRenderPart: { entry:" in loc, (
            f"{name}：`perfRenderPart` 必须是**嵌套对象** —— 写成带点的字面键（`\"perfRenderPart.parse\"`）时 "
            f"`T()` 按 `.` 走层级查找会找不到 ⇒ 读数里直接印出键名（真机读数实证）"
        )


def test_scroll_drift_is_measured() -> None:
    """人（2026-09-24）：「**我每次回车画面都往上跑**」并圈定要补"漂移读数" ⇒ 记三样：
    ① 渲染**前/后**的 `scrollTop`（差 = `delta`）；② 会话**累计**（`sum`，直接量化"往上飘多远"）；
    ③ 这一轮 `_move` 里 **补偿的合计**（`comp`，补偿本身也是漂移嫌疑源）。
    采集口径：`keepPosition()` 记"前"（此刻 DOM 还是上次的、位置还没动），`attach()` 末尾用**双 rAF** 记"后"
    （补偿与浏览器对 `scrollTop` 的夹取都在那之前落定）。"""
    js = _js()
    assert "drift: { n: 0, open: false, line: 0, off: 0, before: 0, after: 0, delta: 0, comp: 0, sum: 0 }," in js
    assert "var drift = null;" in js, "别名先声明为空，**赋值必须在 `dbg` 之后**（AG91）"
    assert js.index("var dbg = {") < js.index("drift = dbg.drift;"), (
        "`drift = dbg.drift;` 必须在 `var dbg = {…}` **之后** —— 写在前面就是加载期 TypeError、"
        "整块 IIFE 挂不上（真机：窗口化全失效、不能跳转/不能滚动）"
    )
    assert "function _con(msg, isErr) {" in js and "_log(s) { _con(String(s));" in js, "日志要同时进控制台（人 2026-09-24 明确要求）"
    assert "drift.before = pane ? Math.round(pane.scrollTop) : 0;" in js, "「前」在 `keepPosition()` 里记"
    assert "drift.comp += Math.round(after - before);" in js, "补偿量按轮累计（补偿也在 `_move` 里）"
    assert "drift.delta = drift.after - drift.before;" in js and "drift.sum += drift.delta;" in js
    assert "drift: dbg.drift," in js, "要经 `stats()` 出去"
    ds = (_APP / "js" / "display-settings.js").read_text(encoding="utf-8")
    assert 'T("settings.display.perfLiveDrift"' in ds
    for name in ("zh-CN", "en"):
        assert "perfLiveDrift:" in (_APP / "i18n" / f"{name}.js").read_text(encoding="utf-8")


_LOAD_PROBE = r"""
const fs = require("fs");
const errs = [];
const realLog = console.log.bind(console);
// 最小桩：够模块在"加载期"跑完 `_boot()`（`document.getElementById` / `addEventListener` / `window.performance`）
const el = { addEventListener() {}, clientHeight: 800, scrollTop: 0, scrollHeight: 0, contains() { return true; } };
globalThis.document = { getElementById() { return el; }, querySelector() { return el; }, createElement() { return { style: {}, setAttribute() {}, classList: { contains() { return false; } } }; }, querySelectorAll() { return []; } };
globalThis.window = globalThis;
globalThis.window.performance = { now: () => Date.now() };
globalThis.window.requestAnimationFrame = (f) => setTimeout(f, 0);
globalThis.window.cancelAnimationFrame = () => {};
globalThis.window.addEventListener = () => {};
globalThis.window.console = { log: (...a) => realLog(...a), error(...a) { errs.push(a.join(" ")); } };
globalThis.window.MemoriaApp = {};
try {
  // **只加载"窗口化那一块"**（`app.js` 末尾的 IIFE）—— 加载期异常都发生在这里，而整份 app.js 需要 DOM/localStorage 等一堆桩。
  // 用 `lastIndexOf("(function () {")` 定位：本块是文件里**最后**一个 IIFE（文件是 CRLF，按整行匹配会落空）
  const src = fs.readFileSync(process.argv[1], "utf-8");
  // 找**最后一个**「IIFE 紧跟着 "use strict"」的那一处 = 本块（单纯 lastIndexOf 会命中块内的嵌套 IIFE / 注释里提到的写法）
  let at = -1;
  for (let i = src.lastIndexOf("(function () {"); i >= 0; i = src.lastIndexOf("(function () {", i - 1)) {
    if (src.slice(i, i + 80).indexOf('"use strict"') >= 0) { at = i; break; }
  }
  new Function("window", "globalThis", at >= 0 ? src.slice(at) : src)(globalThis, globalThis);
} catch (e) { console.log(JSON.stringify({ loaded: false, error: String(e && e.message || e) })); process.exit(0); }
const W = globalThis.MemoriaPreviewWindow;
realLog(JSON.stringify({
  loaded: !!W,
  exports: W ? Object.keys(W).sort() : [],
  stats: W && typeof W.stats === "function" ? !!W.stats() : false,
  errs: errs,
}));
"""


def test_load_time_errors_cannot_hide() -> None:
    """**加载期异常 = 窗口化全失效**（AG91 的教训，真机代价很大）：我把 `var drift = dbg.drift;` 写在 `var dbg = {…}`
    **之前** ⇒ 加载时 `dbg` 还是 undefined ⇒ 整块 IIFE 抛错、`window.MemoriaPreviewWindow` **根本没挂上** ⇒
    真机表现是"**不能正确跳转、跳转后不能滚动**"，而面板上只表现为"少了几行读数"，肉眼极难发现。
    ⇒ 两道防线：① **顺序断言**（别名赋值必须在声明之后 —— 直接钉住这次的写法）；② **控制台凭证**
    （模块加载成功必须打一行 `🪟 pvwin module loaded …`，人按要求看控制台；少了它就该警觉）。
    ③ 所有日志/跳过都同时进控制台（`_log` → `console.log`；`_skip` → `console.error`）。"""
    js = _js()
    assert js.index("var dbg = {") < js.index("drift = dbg.drift;"), (
        "`drift = dbg.drift;` 必须在 `var dbg = {…}` 之后（写在前面就是加载期 TypeError：整块挂不上、窗口化全失效）"
    )
    assert 'var drift = null;' in js
    assert '_con("module loaded · attach/keepPosition/markRender/drift ready");' in js, "加载成功要留一行控制台凭证"
    assert "function _con(msg, isErr) {" in js and "_log(s) { _con(String(s));" in js
    assert '_con("attach✗ " + s, true);' in js, "跳过原因也要进控制台（error 级）"


def test_reentrancy_and_hysteresis_guard_the_window() -> None:
    """人（2026-09-24）实测：「**滚到边界就卡住**，而且**等待下一次滚动时间比全量渲染还要长**」，日志里
    `move 2872-2911` 与 `move 2872-2912` **交替**。真因：`_move()` 收尾调 `_afterMaterialize()`，后者收尾又调
    `_cover()` ⇒ 同一次调用栈里接着算下一趟；差一个槽就再换一趟，而每趟都要"一次布局 + 补链接 + 排版"⇒ 自转。
    ⇒ 两道护栏：**防重入**（`s.moving`）+ **迟滞**（`HYST_SLOTS`）。"""
    js = _js()
    assert "if (s.moving) return false;" in js, "换窗期间抑制再入（`_afterMaterialize()` 会再调 `_cover()`）"
    assert "s.moving = true;   // ← 本趟换窗期间**抑制再入**" in js
    assert "_afterMaterialize(entering.length > 0);\n    s.moving = false;" in js, "标志位要在收尾清掉（否则窗口从此再不更新）"
    assert "const HYST_SLOTS = 6;" in js
    assert "if (Math.abs(i0 - s.from) < HYST_SLOTS && Math.abs(i1 - s.to) < HYST_SLOTS) return false;" in js, (
        "窗口只差一两个槽就不动它（真机日志正是两个窗口交替）"
    )


def test_window_placement_is_self_consistent_with_the_estimate_table() -> None:
    """落点必须与**同一张高度表**自洽：锚点块回到「视口顶部 ± 块内偏移」（否则内容对不上）。"""
    js = _js()
    assert "const i0 = _indexAt(s.slots, Math.max(0, top - vh * MARGIN_SCREENS));" in js
    assert "const i1 = _indexAt(s.slots, top + vh * (1 + MARGIN_SCREENS));" in js
    assert "pane.scrollTop = Math.max(0, (box ? box.offsetTop : 0) + off);" in js, (
        "锚点块回到「视口顶部 + 块内偏移」—— 与上面排位置用的是同一张高度表"
    )
    assert "if (after !== before) { s.pane.scrollTop += after - before; if (drift.open) drift.comp += Math.round(after - before); }" in js, (
        "④ 高度回填补偿：补齐时基准块的视觉位置不动（手工版 scroll anchoring）"
    )
