# task-198 报告：图片编辑滚动 / 小窗 mermaid / 关闭小窗定位

> 人的三句原话：预览区图片编辑后闪到文件开头；跳转小窗里 mermaid 没渲染；关闭小窗后闪到跳转入口，要求给小窗加按钮定位入口，「别再关闭小窗触发」。
> **未 commit**。真机验证为本地 app（WebView2/CDP）+ 最小夹具；未动 `docs/design/**`、`Package/**`、`docs/example/**`。

## 0. 结论
| 验收 | 结果 | 关键读数 |
|---|---|---|
| T-ui-1 B1 图片编辑后不跳开头 | ✅ | RED：previewTop **8369→0**；GREEN：可视锚点行 **235→235**，图片视口 top **408.58→408.77**（不再回 0） |
| T-ui-2 小窗 mermaid 真渲染 | ✅ | RED：`svgCount=0, mermaidCode=1`；GREEN：**`svgCount=1, mermaidCode=0`** |
| T-ui-3 关闭不滚、按钮定位准 | ✅ | RED：关闭 delta **preview +3412 / editor +2982**；GREEN：关闭 **0 / 0**；定位按钮 delta **+3412 / +2982** |
| T-ui-4 主预览 mermaid / 编辑同步回归 | ✅ | 主预览 `svg=1, mermaid-error=0`；12 剧本 **12/12** |
| T-ui-5 pytest / node | ✅ | pytest **1661 passed**（基线 1655 + 本任务 6 例）；改动 JS 文件 `node --check` 全 0 |

---

## 1. B1：图片编辑后预览跳到文件开头
### 复现（先红）
夹具 `t198-fixture-gen.py` 生成 `docs/long-image.md`（图前 60 节 + 图片 + 图后 60 节，图片源码行 243）。真机：打开文件 → 分栏 → 滚到图片（约 8301px）→ 触发真实 UI 的图片属性写回事件（`memoria:image-attr`, width=360）。
- RED：`previewTop 8369 → 0`、`editorTop 8421 → 0`；`__memoriaEditScrollStats = 0`（说明根本没走 keep-scroll 恢复）。
- 证据：`t198-real-red-b1.json`、`t198-red-b1.log`。

### 根因（三类中的哪一类）
**滚动恢复逻辑被绕过**，不是图片加载本身、也不是锚点映射错误：
`image-tools.js::applyImageEditLines()` 是图片属性/名称写回的唯一入口，但它直接
`renderEditor()` + `await renderPreview(state.doc)`；而源码编辑/撤销走的是
`app.js::_renderPreviewKeepScroll()`（task-141：采锚点→重渲→恢复→漂移收敛）。
图片路径没有复用该入口 ⇒ 整篇重渲把预览和编辑器都刷回 0。
另：图片属性提交后会 `reenterImageEdit()`，`enterBlockEditMode()` 里的 `blockEl.focus()` 默认会把块滚进视口，叠加二次偏移。

### 修法
1. `app.js` 门面暴露 `renderPreviewKeepScroll: _renderPreviewKeepScroll`。
2. `image-tools.js::applyImageEditLines()`：
   - 先记 `editor-pane.scrollTop`，`renderEditor()` 后 rAF 恢复；
   - 预览走 `A().renderPreviewKeepScroll()`（能力缺失才 fallback 裸 `renderPreview`）。
3. `edit-handler.js` 块编辑聚焦改 `focus({preventScroll:true})`，且不退回会滚动的 `focus()`。

### GREEN
`t198-real.json`：`b1TopBefore=235 / b1TopAfter=235`，图片视口 top 408.58→408.77（图片高度 74.6→210 是预期拉大）；`__memoriaEditScrollStats`：`restores:1, restoredByAnchor:1`。
> **诚实边界**：`previewTop` 数值仍会变动（本例 +609），因为图片本身变高、惰性预览在重渲中物化高度；但**可视锚点行和图片在视口中的位置不变**，不再跳到文件开头。这是 task-141 的锚点语义（只补差值，不重设落点），不是回退。

---

## 2. B2：跳转小窗 mermaid 未渲染
### 复现（先红）
夹具 `docs/link-source.md` 有 `[[link-target]]`；`docs/link-target.md` 顶部是 mermaid fence。真机点 wikilink 出小窗。
- RED：小窗 `svgCount=0`，`code.language-mermaid=1`（显示原始代码块）。
- 证据：`t198-real-red-b2b3.json`、`t198-red-b2b3.log`。

### 根因
小窗走的是**独立简化渲染路径** `_linkPanelRenderPreview()`：它只调
`MemoriaMarkdownPreview.renderHtml()`（HTML），**漏了主预览渲染后的 mermaid 后处理**；
主预览在 `renderHtml` 后还会 `await renderMermaidBlocks(container)`。
小窗内容异步注入，时机上也不在主预览容器内。

### 修法
小窗复用**同一个**主渲染后处理器：
```js
docEl.innerHTML = MP.renderHtml(...);
if (typeof MP.renderMermaidBlocks === "function") await MP.renderMermaidBlocks(docEl);
```
不自己 `mermaid.init`（重复初始化有已知风险）；`_linkPanelRenderPreview` 改 async，两处调用点 `await`，避免关闭/切换候选后异步替换继续。

### GREEN
`svgCount=1 / mermaidCode=0`；截图 `shots/b2-panel-mermaid.png` 可见节点与连线；主预览回归 `mainMermaid={svg:1,error:0}`。

---

## 3. B3：关闭小窗不再滚动；新增「定位入口」按钮
### 先说明解耦方式（按要求）
- **关闭 = 只关闭**：`closeLinkPanel()` 函数体内**没有任何** `scrollTop/scrollTo/scrollIntoView`；
- **定位 = 只由按钮 click 触发**：新增 `data-panel-locate`（文案「↩ 定位入口」）→ `_linkPanelLocateAnchor(pop)` 内才 `scrollIntoView({block:"center"})`；
- 不在 close 里加"要不要滚"的条件判断。唯一的耦合源是浏览器 `focus()` 的隐式滚动：关闭时焦点回位改为 `focus({preventScroll:true})`，且**不退回会滚动的 `focus()`**。旧代码 `pop.anchorEl.focus()` / `pop.opener.focus()` 正是「关闭后闪到入口」的真因。

### 复现（先红，只临时回退 App 的 B2/B3 改动，B1 保持修复以隔离）
- RED：打开小窗 → 滚到顶 → 点关闭：`previewTop 0→3412`、`editorTop 0→2982`。
- 证据：`t198-real-red-b2b3.json`。
### GREEN
- 关闭：`delta preview=0, editor=0`，panel 消失；
- 定位按钮：点击后 `preview +3412 / editor +2982`，panel 消失；
- 截图 `shots/b3-after-close.png` 停在顶部（未跳入口），按钮文字见 `b2-panel-mermaid.png` 右下「↩ 定位入口」。
- i18n：`cfg.linkPanel.locate / locateTitle` 中英各 +2 行。

---

## 4. 改动与证据
```
改 src/memoria/ui/static/app/js/app.js             +43/−9
改 src/memoria/ui/static/app/js/image-tools.js     +13/−1
改 src/memoria/ui/static/app/js/edit-handler.js     +4/−2
改 src/memoria/ui/static/app/i18n/zh-CN.js          +2
改 src/memoria/ui/static/app/i18n/en.js             +2
新增 tests/test_preview_panel_images_mermaid.py     6 例（静态契约）
新增 artifacts/agent/verify/todo/preview-panel-images-mermaid/
     t198-fixture-gen.py / 198-probe.mjs / 198-run.ps1
     t198-real.json（GREEN）
     t198-real-red-b1.json / t198-real-red-b2b3.json（RED）
     t198-{red-b1,red-b2b3,green}.log
     shots/b1-before-edit.png、b1-after-edit.png、b2-panel-mermaid.png、b3-after-close.png、main-mermaid-regression.png
```
复现命令：
```powershell
python artifacts\agent\verify\todo\preview-panel-images-mermaid\t198-fixture-gen.py
powershell -ExecutionPolicy Bypass -File artifacts\agent\verify\todo\preview-panel-images-mermaid\198-run.ps1
```

## 5. 门禁
- `python -m pytest -q tests` → **1661 passed, 0 failed**（基线 1655 + 6 新例）
- 改动 JS：`node --check app.js / image-tools.js / edit-handler.js` → 全 0
- `node scripts/i18n_selftest.js` → exit 0
- 12 剧本 → **12/12，failed 0**
- 未 commit；未动禁止路径

## 6. 限制
1. B1 的 scrollTop 数值因图片高度/惰性物化会变化（本例 +609），但可视锚点与图片视口位置保持；若产品要求"像素级不动"，需改为钉住编辑图片的 rect 并反向补偿，会牺牲"内容锚点不变"语义 —— 当前按 task-141 既有锚点语义实现。
2. 真机验证用本地 WebView2；小窗 mermaid 的样式/尺寸沿用主渲染器，未额外改小窗 CSS。
3. `node --check` 全 `src` 时仓库自带的 `vendor/mathjax/.../boldsymbol.js` 是既有不可解析 vendor 文件（非本任务改动）；本任务改动文件全过。
