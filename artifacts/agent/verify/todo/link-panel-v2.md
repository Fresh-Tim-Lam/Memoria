# task-161 链路小窗 v2（可拖动浮动面板 + 候选列表 + 钉住）报告

> 人要求：小窗太小、要能移动；默认预览可调模式；多链接在小窗内部选；不要占地方；只能有一个文档显示区。
> Lead 追加：① 钉住（内联 SVG 图钉）② 候选链接列表（知识点名称/description/tags/类型徽标）。
> 更正（已遵守）：是 **knowledge（知识点名称）**，不是 KB 名称 ⇒ **不显示库名、不做跨库设计**；上一轮"跨库"分析已撤回、未写入本报告。

---

## 0. 结论速览
- ✅ 可拖动浮动面板：默认 520×420（min 360×260 / max 720×640），标题栏拖动、双击复位、方向键微调；位置/尺寸/模式/钉住态**持久化到 ui-settings**。
- ✅ 默认【预览】，可切【源码】；不提供编辑模式。
- ✅ 多候选 = **左候选列表 + 右单一文档区**；候选=1 无列表、文档区占满；严禁并列两个文档区。
- ✅ 列表每行：**类型徽标**（知识点/纯文件引用/区域缺失）+ **知识点名称** + description(2 行) + tags(chips ≤3 + "+N")。
- ✅ 钉住：点外部/焦点离开/主界面交互都不关；Esc/× 仍可关；钉住时点另一个链接 ⇒ **同一面板换内容**（不新开不重定位）；pinned 持久化。
- ✅ 全部打开(n) 保留；Ctrl/Cmd+点击直跳保留；拉到编辑区语义不变；断链仍走原编辑模态；无 backdrop。

---

## 1. ui-settings 持久化（先确认，不新写路径）
- 前端统一入口：`call("get_ui_settings")` / `call("save_ui_settings", partial)`（app.js 既有函数，浅合并；与 boot/layout/customColors 同一套）。
- 新增键：`linkPanel: { x, y, w, h, mode, pinned }`（仅此键，不碰其它配置；未改 `src/memoria/storage/ui_settings.py`）。
- 用户态目录由既有实现决定：`ui_settings._settings_dir()` = `MEMORIA_CONFIG_DIR` > `%LOCALAPPDATA%\Memoria\config`（task-160 迁移后）> 旧安装目录只读兼容。**没有新增"自己找路径"的 JSON 写入点。**
- 真机磁盘证据（临时 config 目录）：`...\config\ui-settings.json` 内含
  `"linkPanel": {"x":707,"y":263,"w":580,"h":464,"mode":"source","pinned":true}`；前端 reload（模拟重启）后几何/模式仍读回（P5）。

---

## 2. 面板 v2 实现（app.js 链接面板部分重写）
```
标题栏（拖动把手）：[📌] [单候选: 名称 | 多候选: N 个链接] [预览|源码] [全部打开(n)] [−] [×]
单一文档区（多候选时左侧 210px 候选列表；右侧同一文档区）
底部状态栏：文件路径 · 整文件/L1–7        [拉到编辑区]
```
- 拖动：标题栏 pointerdown → window pointermove/up；拖动夹回视口；双击标题栏复位到默认位置（贴近链接、不遮挡）；标题栏 focus 时方向键 16px（Shift 48px）微调。
- 尺寸：`resize: both` 右下角把手；CSS min/max 约束；pointerup 后读取 rect 持久化。
- 折叠：`[−]` → 只留标题栏（height:auto、隐藏 body/status，P6 高度 37px）；`[+]` 恢复原尺寸。
- 模式：preview = `MemoriaMarkdownPreview.renderHtml`（沿用既有预览能力；只读）；source = 原始 markdown `<pre>`（等宽只读）；模式写 `linkPanel.mode` 并被记住。
- 单文档区：`data-panel-doc` 全局面板内仅 1 个；切换候选只替换其内容（domCount 恒为 1，P1/P3 验证）。
- 键盘：Esc 关闭（焦点回链接）；Tab 在面板内循环（focus trap）；列表内 ↑↓ 移动、Enter=拉到编辑区；标题栏方向键移动。
- aria：面板 `role="dialog" aria-modal="false"`（可驻留面板语义，替代 v1 的 menu）；模式按钮 `aria-pressed`；列表 `role="listbox"/option`、`aria-selected`；钉住按钮 `aria-pressed`；链接 `aria-expanded` true/false。
  > 说明：v1 的 `role=menu/menuitem` 在 v2 改为 `dialog/listbox`（拖动面板 + 焦点陷阱的语义正确性）；`aria-expanded`、焦点管理、Esc 均保留。

---

## 3. 钉住（Pin）
- 图标：**内联 SVG 手绘**（viewBox 0 0 16 16、宽高 13、`stroke="currentColor"`、stroke-width 1.4、未钉住 fill=none）。三条理由（按 Lead）：
  ① 零前端依赖硬约束；② 风格一致（app 既有图标均内联 SVG + currentColor + stroke）；③ 许可风险：外找素材要跟许可证，收益不抵风险。
- 钉住态：钉座 path `fill="currentColor"` + 按钮 `color: var(--theme-color)` ⇒ 实心蓝钉；截图 `P9-pin-icon-unpinned-2x.png` / `P9-pin-icon-pinned-2x.png`（2× 放大，便于判 13px 可辨性）。
- 语义：未钉住=点外部/焦点离开关闭；已钉住=两者都不关；**Esc 与 × 永远可关**；已钉住时点另一链接复用同一面板换内容（不新开、不重定位，P10 验证 rect 不变、列表 5 条、钉住仍在）。
- 持久化：`linkPanel.pinned` 写 ui-settings；关掉再开保持（P10/P11）。
- 键盘：按钮在 Tab 序列内，Enter/Space 切换；`title`/`aria-label` 中英双语。

---

## 4. 候选列表（仅候选 > 1）
- 行字段：
  ① **类型徽标**（文字+颜色，不靠图标形状）：
     `知识点`（绿）/`纯文件引用`（蓝，kp_id==None）/`区域缺失`（橙，kp_id 存在但 range_ok=false）/`未解析`（橙，文件都拿不到）
  ② **知识点名称** = candidate.name（纯文件引用时 = 文件 stem，如 `plain-note`）
  ③ description 两行 clamp；无则「无描述」
  ④ tags chips ≤3 + `+N`；无 tags 则不占行
- **纯文件引用**特殊处理：右侧显示**该文件头内容**（预览/源码两模式均可读）；底栏显示「整文件」而非 L 区间；「拉到编辑区」可用（打开文件，不定位 KP）。
- 数据与性能：
  - description/tags 来自 `load_document(file)` 的 `knowledge_points`（已有通道，按文件缓存）；
  - 多候选**按文件去重批量**请求（`Promise.all`，非串行）：本夹具 **5 个候选 / 4 个唯一文件**（target.md 内 2 个 KP 复用一次请求）⇒ 实测 `rpcFiles = [target.md, other.md, plain-note.md, broken-range.md]`；列表首屏 loading 态后填充。
- **不显示库名**（按更正）；未实现任何跨库解析/设计。

---

## 5. 真机矩阵（临时 KB + 真机按键/鼠标；截图见 §6）
夹具：`link-popover-fixture/kb`（单链接 target-kp；多链接 5 候选 = 3 知识点 + 纯文件引用 plain-note + 区域缺失 norang-kp；断链 ghost-kp；target.md 含两个 KP 验证去重）。

| 场景 | 操作 | 结果 |
|---|---|---|
| **P1** | 点击单链接 | 面板出现（默认 preview，`listCount=0`、名称/路径·L1–7、按钮全在）；**不跳转**（仍 a.md）；无 backdrop ✅ |
| **P2** | 切源码 | `<pre>` 原始 markdown；关闭再开 ⇒ 模式仍 source ✅ |
| **P3** | 点击多链接 | 面板：`5 个链接`、左列表 5 行（3 类徽标 + name/desc/tags）；右单文档区；点击列表项切换右侧、底栏随之变 ✅ |
| | 点第 4 行（纯文件引用） | 右侧显示 plain-note.md 文件头；底栏 `docs/plain-note.md · 整文件`；按钮可用 ✅ |
| | 点第 5 行（区域缺失） | 底栏 `docs/broken-range.md · 整文件`；面板不关闭 ✅ |
| **P4** | 拖动标题栏 | 面板从 (607,183) → (707,263)；关掉再开仍在该位置 ✅ |
| **P5** | 前端 reload（模拟重启） | 位置/尺寸/模式从磁盘读回（settings 文件 linkPanel 键）✅ |
| **P6** | 折叠/展开 | 高度 420→37（只剩标题栏），展开恢复 ✅ |
| **P7** | 拖右下角缩放 | 520×420 → 580×464 并持久化 ✅ |
| **P8** | 不回归 | Esc 关、点外部关、Ctrl+点击直跳（currentPath→target.md 且无面板）、拉到编辑区后关+定位、断链开原模态、Tab focus trap 全过 ✅ |
| **P9** | 钉住 | 点钉后 aria-pressed=true（实心蓝）；点外部/点编辑区 ⇒ 面板仍在；Esc ⇒ 关闭 ✅ |
| **P10** | 钉住持久化 + 换链接 | 重开仍钉住；钉住时点另一个链接 ⇒ 同面板（panelCount=1、rect 不变、列表换 5 条、钉住仍 true）✅ |
| **P11** | 钉住下逃生口 | × 关闭；重开仍钉住；Esc 关闭 ✅ |

---

## 6. 截图（`artifacts/agent/verify/todo/link-panel-v2-screens/`）
- `P1-single-preview.png`（单候选预览，无列表）
- `P3-candidate-list.png`（5 候选列表：三态徽标/name/desc/tags）
- `P3-pure-reference-selected.png`（纯文件引用选中：文件头 + 整文件底栏）
- `P2-source-mode.png`（源码模式）
- `P4-dragged.png`（拖动后位置）
- `P6-collapsed.png`（折叠窄条）
- `P9-pin-icon-unpinned-2x.png` / `P9-pin-icon-pinned-2x.png`（图钉 2× 放大：空心 / 实心蓝）
- `P9-pinned-after-outside.png`（钉住后点外部仍显示）
- `P10-pinned-switch-link.png`（钉住时换链接：同一面板换内容）

---

## 7. 已知限制（如实）
1. 折叠态本身不持久化（持久化的是位置/尺寸/模式/钉住；折叠是临时减占地）。
2. 面板内预览是只读：其中的 wikilink/图片不响应点击（"看一眼"面板；交互编辑走「拉到编辑区」）。
3. 候选列表列宽固定 210px（未做可拖分隔条；spec 允许"若成本高就固定"）。
4. 区域缺失/纯文件引用统一显示文件头（最多 400 行，超出标注截断）；不额外做"整文件全文分页"。
5. 标题栏拖动使用 PointerEvent；WebView2 下 CDP 合成鼠标需带 `buttons` 掩码（真机鼠标无此问题，探针已按真实 pointer 语义验证）。
6. 未提供跨库链接（按更正：不存在此需求）。

---

## 8. 门禁（本轮）
- `pytest -q tests`：**1516 passed**（曾因面板 CSS 的 `!important` 触发 `test_checkbox_dot_style` 契约，已改为无 `!important` 后全绿）。
- `node --check`：66 个非 vendor JS 全过。
- `i18n_selftest`：PASS（exit 0）。
- `team_audit`：**FAIL=0**；`prompt_drift`：FAIL=0 / NOT_RUN=0，exit 0；12 剧本 12/12。
- 真机：`link-panel-v2-run.ps1` exit=0；用户 `Memoria.exe` PID 48812 前后一致；端口 9594 已释放；临时 KB/config 副本，未写 `docs/example/AAA_Vocab/**`。

---

## 9. 变更文件（未 commit）
```
app.js        +…/−…   （链接面板 v2：拖动/缩放/折叠/模式/单文档区/候选列表/徽标/tags/钉住/复用/批量去重）
app.css       +…/−…   （.-link-panel* / 列表 / 徽标 / tags / 钉住态；无 !important）
i18n/zh-CN.js +…      （cfg.linkPanel.*：pin/linkCount/类型徽标/listAria/meta/noDesc/wholeFile…）
i18n/en.js    +…
```
新增产物：`artifacts/agent/verify/todo/link-popover-fixture-gen.py`（v2 夹具）、`link-panel-v2-probe.mjs`、`link-panel-v2-run.ps1`、`link-panel-v2-realapp.{json,log}`、`link-panel-v2-screens/*.png`。
