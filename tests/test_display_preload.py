"""「后台预加载」开关（设置 →「显示」→「性能」）与 app.js 侧「预览 DOM 缓存 + 后台预渲染」的契约钉子。

人（2026-09-23）：「出现在页签的文件能不能内存预加载减小切换速度？或者后台提供 后台预加载开关，
并且说明更大的硬件开销和更流畅的体验（推荐大型知识库）」。落地口径：

1. **只缓存渲染好的预览 DOM**（不新增第二份文档数据缓存：后端 `load_document` 已按
   `(路径, mtime, size)` 缓存，前端再来一份只是多一处过期风险）。
2. **缓存的键 = 路径，值里带后端版本号（`version` = 文件内容 sha256）与正文指纹** —— 两者任一
   不符立即丢弃重渲；宁可慢一次，也绝不显示过期内容。
3. **搬移节点而不是克隆**（切走时把 `#preview` 的子节点整体搬进 `DocumentFragment`，切回时搬回）
   ⇒ 已挂的事件监听与已排版好的 MathJax/Mermaid 产物一并保留。
4. **失效必须是事件驱动的显式清单**：本地编辑 / 写盘成功 / 视图模式变更 / 关闭页签 / 换库 /
   文件集合变化（重命名、删除、新建、导入）/ 界面语言变更 / 主题变更。
5. **后台预渲染**：渲染收尾后用 `requestIdleCallback`（无该 API 时 `setTimeout` 兜底）一次一个页签，
   跳过当前页签与已缓存者，超行数上限与单会话次数上限即停，任何中止信号立刻停手；
   预渲染在**脱离文档**的容器里完成，不动 `#preview` / 编辑器 / 撤销栈 / 滚动位置。
6. **开关落点**：`DEFAULTS.backgroundPreload`（默认关）→ `pickKnown` → 既有 `save_ui_settings` 通道
   （localStorage `-display-settings` + 磁盘 `ui-settings.json` 的 `display` 段），与字号/字体同一条路径。
"""

from __future__ import annotations

from pathlib import Path

_APP = Path(__file__).resolve().parents[1] / "src" / "memoria" / "ui" / "static" / "app"
_APPJS = _APP / "js" / "app.js"
_DISPLAY = _APP / "js" / "display-settings.js"
_LOCALES = {"zh-CN": _APP / "i18n" / "zh-CN.js", "en": _APP / "i18n" / "en.js"}


def _display() -> str:
    return _DISPLAY.read_text(encoding="utf-8")


def _app() -> str:
    return _APPJS.read_text(encoding="utf-8")


def test_default_is_off_and_flows_through_the_shared_save_path() -> None:
    """默认关（不改变现有行为）；键走 `pickKnown` ⇒ 与字号/字体同一条 `save_ui_settings` 通道。"""
    src = _display()
    assert "backgroundPreload: false," in src, "缺默认值（必须默认关：预加载是可选开销）"
    assert (
        "if (data && data.backgroundPreload !== undefined) out.backgroundPreload = !!data.backgroundPreload;"
        in src
    ), "缺 pickKnown 白名单条目 ⇒ save() 会把它当脏键丢掉，开关点不动"
    assert "function save(partial)" in src and "a.save_ui_settings({ display: load() })" in src, "未复用既有落盘通道"


def test_checkbox_reads_checked_not_value() -> None:
    """勾选框必须取 `el.checked`：`el.value` 恒为 `"on"`，会把开关永远存成真。"""
    src = _display()
    assert 'let val = el.type === "checkbox" ? !!el.checked : el.value;' in src


def test_section_reuses_the_house_markup_and_the_shared_fold_path() -> None:
    """版块用既有骨架 ⇒ 自动被 `graph-settings.js::foldSettingsSections()` 折成可展缩的 `<details>`。"""
    src = _display()
    assert "function preloadSection(T, s)" in src
    assert '<section class="-settings-section">' in src, "缺版块骨架（折叠机制只认 section.-settings-section）"
    assert '<h3 class="-settings-heading">${T("settings.display.perfGroup")}</h3>' in src
    assert 'class="-settings-field -settings-field--inline"' in src, "勾选框要复用既有行内字段样式"
    assert 'data-display-setting="backgroundPreload"' in src, "未接既有 data-display-setting 绑定通道"
    assert (
        '<p class="-muted -settings-note">${T("settings.display.preloadNote")}${preloadFootprintNote(T)}</p>' in src
    ), "缺字段下方的说明（并附一句现场占用读数）"
    assert "function preloadFootprintNote(T)" in src and 'stats.bytes / 1048576' in src, "现场读数走缓存自身的估算口径"
    assert "${preloadSection(T, s)}</div></div>`;" in src, "版块要挂在显示页模板末尾（与其它版块同一条渲染路径）"


def test_apply_all_announces_the_toggle_to_app_js() -> None:
    """开关只在 `applyAll()` 里通告一次（设置变更 → save/applyAll），app.js 侧开关未变时空操作。"""
    src = _display()
    assert "applyFonts(s); announcePreload(s.backgroundPreload);" in src
    assert "if (app && typeof app.setBackgroundPreload === \"function\") app.setBackgroundPreload(!!on);" in src
    assert "window.MemoriaApp.setBackgroundPreload = setBackgroundPreload;" in _app(), "app.js 未暴露开关入口"


def test_cache_is_keyed_by_path_version_and_body_fingerprint() -> None:
    """键 = 路径；值带版本号（后端 sha256）与正文指纹 ⇒ 盘上内容/正文一变就对不上。"""
    js = _app()
    assert "var _previewDomCache = new Map();" in js
    assert "function _docVersionOf(doc)" in js and "typeof doc.version === \"string\"" in js
    assert "function _bodyFingerprint(body)" in js, "缺正文指纹（RPC 版本号之外的兜底判据）"
    assert (
        "if (entry.version !== _docVersionOf(doc) || entry.fp !== _bodyFingerprint(_previewSourceBody(doc)))"
        in js
    ), "恢复前必须同时校验版本与指纹，不符即丢弃"


def test_cache_moves_nodes_instead_of_cloning() -> None:
    """切走搬出 / 切回搬回（移动节点 ⇒ 监听与已排版产物随节点保留，这也是"零解析"的前提）。"""
    js = _app()
    assert "function _previewCacheStash(path)" in js
    assert "while (preview.firstChild) frag.appendChild(preview.firstChild);" in js, "必须是移动（appendChild），不能 clone"
    assert "function _previewCacheRestore(doc)" in js and "preview.appendChild(entry.frag);" in js
    # 命中即接管本轮渲染：不重跑 parse / render / MathJax
    assert "if (!incremental && _previewCacheRestore(doc)) { _renderingPreview = false; return; }" in js
    # 渲染成功后才登记"这份 DOM 对应哪份文档的哪个版本"（没有这一步就永远存不进缓存）
    assert "function _markPreviewDomCurrent(doc)" in js
    assert "_notifyRenderSettled(); _preloadSchedule(); _markPreviewDomCurrent(doc);" in js
    assert 'if (!first || first.classList.contains("-preview-loading")) { _previewDomKey = null; return; }' in js, (
        "失败/占位（.-preview-loading）不算有效渲染，绝不能把错误页缓存起来"
    )
    # 缓存条目只对"本会话未编辑过"且已写盘干净的文档建立
    assert "if (_dirty) return;" in js and "if (!state.doc.preview_body) return;" in js
    # 整段渲染被跳过 ⇒ 要自己补上 renderPreview 里那段"当前文件目录"（否则后续编辑的图片路径会按上一篇算）
    assert "if (MP0 && MP0.setCurrentFileDir) MP0.setCurrentFileDir(_relDirOf(doc.path));" in js


def test_every_invalidation_trigger_is_wired() -> None:
    """失效清单逐条钉住：编辑 / 写盘 / 视图模式 / 关闭页签 / 换库 / 文件集合 / 语言 / 主题。"""
    js = _app()
    # ① 本地编辑
    assert "_dirty = true; _previewCacheDrop(state.currentPath); _previewDomKey = null;" in js
    # ② 写盘成功（syncToDisk）
    assert 'syncLog("syncToDisk: 保存成功"); _previewCacheDrop(state.currentPath);' in js
    # ③ 视图模式变更
    assert "if (prevMode !== mode) { _previewCacheDrop(state.currentPath); _previewDomKey = null;" in js
    # ④ 关闭页签
    assert "_previewCacheDrop(tab.path);" in js
    # ⑤ 换库（打开/关闭）
    assert "function resetOpenDocumentUi() { _previewCacheClear();" in js
    assert "state.openTabs = []; _previewCacheClear(); _preloadResetForNewKb();" in js
    # ⑥ 文件集合变化（重命名 / 删除 / 新建 / 导入 / 刷新）
    assert "state.dirs = res.dirs || []; _previewCacheClear();" in js
    # ⑦⑧ 语言 / 主题（已缓存条目的本地化文案与 mermaid 主题色会过期）
    assert 'window.addEventListener("memoria:langchange", function () { _previewCachePurge(); });' in js
    assert 'window.addEventListener("memoria:themechange", function () { _previewCachePurge(); });' in js
    # 容量上限（LRU）与关闭页签即丢，避免泄漏 DocumentFragment
    assert "while (_previewDomCache.size > PREVIEW_CACHE_MAX) _previewCacheDrop(_previewDomCache.keys().next().value);" in js


def test_preload_is_idle_bounded_and_abortable() -> None:
    """预渲染：空闲回调驱动、一次一个页签、有行数/次数上限、任何中止信号立即停手。"""
    js = _app()
    assert "window.requestIdleCallback(fire, { timeout: 1200 })" in js
    assert "_preloadIdle = setTimeout(fire, 300);" in js, "缺 requestIdleCallback 时的兜底"
    assert "var PRELOAD_MAX_TABS = 4;" in js and "if (_preloadDone >= PRELOAD_MAX_TABS) return;" in js
    assert "var PRELOAD_MAX_LINES = 1200;" in js
    assert "if ((res.lines || []).length > PRELOAD_MAX_LINES) return false;" in js
    # 跳过当前页签与已缓存页签
    assert "if (!path || path === state.currentPath) continue;" in js
    assert "if (_previewDomCache.has(path) || _preloadTried.has(path)) continue;" in js
    # 中止信号：切页签 / 开始编辑 / 关开关；await 之后再确认一次
    assert '_preloadStop("switch")' in js and '_preloadStop("edit")' in js and '_preloadStop("toggle-off")' in js
    assert "if (_preloadAbort !== token || !_preloadEnabled) return;" in js
    assert "if (!_preloadEnabled || path === state.currentPath || _dirty) return false;" in js


def test_preload_renders_off_screen_without_touching_the_visible_ui() -> None:
    """在脱离文档的 holder 里渲染，并保存/还原 `state.doc`、`_blockLineMap`、mapper 的当前文档。"""
    js = _app()
    assert 'const holder = document.createElement("div");' in js
    assert "holder.appendChild(R.render(ast));" in js
    assert "const savedDoc = state.doc;" in js and "const savedMap = _blockLineMap;" in js
    assert "state.doc = savedDoc;" in js and "_blockLineMap = savedMap;" in js
    assert "M.setDoc(savedMapperDoc);" in js, "mapper 的当前文档也要还原，否则编辑映射会错到预渲染那篇上"
    # 预渲染跳过的异步部分（mermaid / MathJax / 图片灯箱）在恢复时补做
    assert "if (entry.prerendered) _applyPreviewStaticPass(preview, _doc);" in js
    assert "if (MP && MP.attachImageLightbox) { try { MP.attachImageLightbox(preview); } catch (_)" in js
    assert "if (window.MathJax?.typesetPromise) queuePreviewMathTypeset(preview, token);" in js


def test_toggle_keys_exist_in_both_locales_and_state_the_trade_off() -> None:
    """文案中英成对；说明必须写清"以硬件换流畅"与"推荐大型知识库"。"""
    keys = ("perfGroup", "preloadLabel", "preloadNote", "preloadFootprint")
    for locale, path in _LOCALES.items():
        text = path.read_text(encoding="utf-8")
        missing = [key for key in keys if f"{key}:" not in text]
        assert not missing, f"{locale} 缺 settings.display 性能键：{missing}"
        assert 'Object.assign(g.MEMORIA_LOCALES["' + locale + '"].settings.display, {' in text
    zh = _LOCALES["zh-CN"].read_text(encoding="utf-8")
    en = _LOCALES["en"].read_text(encoding="utf-8")
    assert "推荐大型知识库" in zh and "内存" in zh and "CPU" in zh
    assert "Recommended for large knowledge bases" in en and "memory" in en and "CPU" in en
