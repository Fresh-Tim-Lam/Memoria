# task-145 链接点击「小窗优先」重构报告（link popover redesign）

> 人要求（第二轮）：**所有链接点击（含单链接）都先出小窗**，小窗里看「那边是什么」，
> 再决定是否「拉到文本编辑区」；不再点了就离开当前位置。
> 本任务落地：单链接/多链接统一浮层（popover），无全屏遮罩；「拉到编辑区」= 原跳转语义（打开文件 + 定位 KP 区域），**不是插入引用**。

---

## 0. 结论速览
- ✅ 单候选不再直接跳转：点击 ⇒ 链接旁圆角浮层（单卡片）。
- ✅ 多候选同样浮层（候选列表 +「全部打开」），不再开整页模态。
- ✅ 每卡片：①名称 ②解释（无则区域首行摘要，再缺明确「无描述」）③区域正文内联预览（限高 12 行、可滚动）④「拉到编辑区」。
- ✅ Esc / 点外部关闭；↑↓ 移动、Enter 触发；`aria-expanded` 同步；`role=menu` / `role=menuitem`。
- ✅ 断链仍走原「编辑链接」模态；悬停高亮/右键菜单绑定未改；多目标「一次开多个标签」保留为「全部打开（n）」。
- ⚠️ 快速通道（Ctrl/Cmd+点击直跳）**已实现但标为「待确认」**（见 §5）。

---

## 1. 后端候选字段确认（先确认，不猜）

### 1.1 `resolve_links` / `resolve_link` 实际返回（HEAD）
`candidate = { file, kp_id, name, range_ok, start_line, end_line }`
（`link_resolver.entry_to_dict()`；前端另补 `requested_id`。**没有** `description`，**没有**区域正文。）

### 1.2 缺的字段从哪来（二次 RPC，不新增后端字段）
已有权威 RPC `load_document(rel_path)` 返回：
- `knowledge_points[]`：每个 KP 含 sidecar 原样字段（含 **`description`**）；
- `lines` / `body`：正文行数组；
- `sidecar`、`link_overrides` 等。

前端在浮层里按候选的 `file` 调一次 `load_document`（**同一浮层内按文件缓存**），再用 `start_line..end_line`
截取区域正文；描述用 `knowledge_points.find(k => k.id === candidate.kp_id).description`。
⇒ **未修改** `presentation/api/ui.py` 与 `services/*`（写域内本来允许，但无必要）。

### 1.3 取不到时的显式文案（不许空白/拼凑）
| 情况 | 卡片表现 |
|---|---|
| KP 有 description | 原样显示 |
| 无 description，有区域正文 | 区域**首行**摘要（≤120 字） |
| 都没有 | 明确显示「无描述」 |
| 候选无区域（range_ok=false） | 预览区「（无区域正文）」 |
| `load_document` 失败 | 「（预览不可用）」+ 描述走上述回退 |
| 候选未解析到文件（`unresolved`） | 名称保留、按钮 **disabled**、文件位「（未解析到文件）」 |

---

## 2. 交互与实现

### 2.1 统一入口（单/多同一套）
`app.js onMemoriaLinkClick(el, ev)`：
- 断链（`-link-broken`）→ `openLinkEditorFromElement`（不变）。
- 多目标（`data-link-targets`）/ `link_overrides` 路由 / `resolve_link` 单目标 ⇒ 统一拿 `candidates`：
  - **普通点击** ⇒ `showLinkPopover(el, title, candidates)`（**单候选也出浮层**）；
  - Ctrl/Cmd+点击且**仅 1 候选** ⇒ 直接 `jumpToTarget`（快速通道，待确认，见 §5）；
  - 解析失败 ⇒ 保持原 status 提示（无候选可展示）。
- 旧 `showLinkPicker`（整页模态）不再被链接点击调用；`link` 编辑/创建模态（`openLinkEditor`）仍然保留、行为不变。

### 2.2 浮层（无遮罩）
- `#link-popover` 追加到 `document.body`；`position:fixed; z-index:900`（模态 1000 之下、预览/工具栏之上），**无 backdrop**。
- 链接旁定位：优先下方左对齐，空间不足翻上方，四边夹在视口内（不挡触发点）。
- 单候选：**无标题头、无选择引导语**，只有一张卡片（轻）。
- 多候选：标题头 +「n 个目标」+ 候选卡片列表 + 底部「全部打开（n）」。
- 关闭：点外部（capture mousedown）、Esc（焦点回链接）、焦点离开浮层（focusout）、再次点同一链接切换关闭。
- 键盘：↑/↓ 移动（`-active` 高亮 + `scrollIntoView`）、Enter = 当前项「拉到编辑区」、Esc 关闭。
- 可访问性：浮层 `role="menu"` + `aria-label`（含链接标题），卡片 `role="menuitem"` + `aria-label`；链接 `aria-expanded` true/false。

### 2.3 「拉到编辑区」
= 既有 `jumpToTarget(candidate, {source:"link"})`：打开目标文件并定位该 KP 区域（`openFile(..., kpId)` + 状态提示）。
点击后**先关浮层**再跳转 ⇒ 浮层立即消失。**不插入引用/不写正文**（严格按 Lead 判定，无歧义上报点见 §6）。

### 2.4 数据与性能
- 每个候选卡片异步补齐：每文件最多 1 次 `load_document`（浮层内缓存），区域最多取 32 行、渲染最多 12 行（超出显示「已截断：显示前 12 行 / 共 N 行」）。
- 无第三方库；纯 DOM 拼接（沿用 `esc()`）。

### 2.5 多目标「一次开多个标签」处置
保留为浮层底部 **「全部打开（n）」**：逐个 `ensureOpenTab(candidate,{pending:i>0})` → `renderTabs()` → `jumpToTarget(第一个)`。
（旧 `confirmLinkPicker` 的 selectedOrder 路径不再被链接点击触发，函数保留以减小 diff；编辑/创建链接模态未受影响。）

---

## 3. 真机验证（Q=真实按键/真实鼠标；截图在 `link-popover-screens/`）

夹具：`link-popover-fixture/kb`（docs/a.md：单链接 `[[target-kp|单目标]]`、多目标 `[[multi-kp|多目标]]`→{target-kp,other-kp}、断链 `[[ghost-kp]]`；target/other 两个文档带 sidecar description + KP 区域）。

| 场景 | 操作 | 结果 |
|---|---|---|
| **S1** | 点击单链接 `单目标` | 浮层出现（cards=1，`role=menu/menuitem`），**currentPath 仍 docs/a.md（未直接跳转）**；卡片 name=目标知识点、desc=侧车 description、预览=区域正文、按钮=拉到编辑区；`aria-expanded=true`；无 backdrop、无模态 ✅ |
| **S2** | Esc | 浮层关闭（cards=0）、`aria-expanded=false`、仍停留 a.md ✅ |
| **S3** | 点击多目标 `多目标` | 浮层 cards=2 +「全部打开（2）」，两张卡片各自 name/desc/预览；未开模态 ✅ |
| **S4** | 点第 1 张「拉到编辑区」 | 浮层消失；`currentPath=docs/target.md`、`activeKpId=target-kp`（区域定位）✅ |
| **S5** | 多目标 →「全部打开（2）」 | 浮层消失、跳首个目标；`openTabs` 增至 3（多标签能力保留）✅ |
| **S6** | 点外部 | 浮层关闭、aria=false ✅ |
| **S7** | 单链接浮层内 Enter | 浮层关闭并跳到 target-kp ✅ |
| **S8** | Ctrl+点击单链接（快速通道） | **不出浮层**、直接跳 target-kp（待确认项，见 §5）✅ |
| **S9** | 断链点击 | 仍打开原「编辑链接」整页模态（不回归）✅ |

其它证据（同一 JSON）：
- `linksBound=3 / linksTotal=3`：链接点击绑定无遗漏；`window.MemoriaLinkContextMenu` 存在（右键菜单 API 未动）。
- 悬停高亮 `highlightGraphFromLink` / 鼠标进出绑定代码未改（仅点击回调签名加 `ev`）。
- 截图：
  - `link-popover-screens/S1-single-popover.png`（单链接浮层）
  - `link-popover-screens/S3-multi-popover.png`（多链接浮层 + 全部打开）
  - `link-popover-screens/S4-after-pull.png`（拉到编辑区后：浮层消失、target.md 定位）

机器可读：`link-popover-realapp.json`、运行日志 `link-popover-realapp.log`、探针 `link-popover-probe.mjs`、启动器 `link-popover-run.ps1`。

---

## 4. 改动清单（未 commit；写域内）
```
app.js   +301/−37   （浮层实现 + onMemoriaLinkClick 重写 + 点击接 event）
app.css  +116/−0    （.-link-popover 系列样式）
i18n/zh-CN.js +17   （cfg.linkPop.*）
i18n/en.js    +17   （cfg.linkPop.*）
```
未改：`presentation/api/ui.py`、`services/*`、`index.html`、旧 link modal 结构。
新增产物：`link-popover-fixture-gen.py`、`link-popover-fixture/`、`link-popover-probe.mjs`、`link-popover-run.ps1`、`link-popover-realapp.{json,log}`、`link-popover-screens/*.png`。

---

## 5. 快速通道（Ctrl/Cmd+点击直跳）——**待你裁决**
- 已实现：`Ctrl/Cmd + 点击` 且候选恰为 1 时直接 `jumpToTarget`，跳过浮层；**普通点击 100% 先出浮层**（核心变化未破）。
- 我的判断：显式修饰键 ≠ 普通点击，属于"高频连续跳转"逃生口，与"单链接也先小窗"不冲突。
- 若你判定冲突：删掉 `quickSkip &&` 两处分支即可（约 6 行），不影响其它逻辑；S8 断言届时翻转为"仍出浮层"。

---

## 6. 「拉到编辑区」语义核对（未扩大）
- 实际行为 = 原 `jumpToTarget`：打开目标文件 + 定位 KP 区域（真机 S4/S5/S7 均验证 currentPath/activeKpId）。
- **没有**任何"把文本插入当前文档/生成引用"的实现或后端调用；未新增 RPC 写路径。

---

## 7. 已知限制（如实）
1. 焦点陷阱（focus trap）未实现：Tab 可移出浮层，触发 `focusout` 自动关闭（有意，避免重负担；Esc/点外部为主动关闭）。
2. 源码模式链接仍是原始 `[[...]]` 文本（不渲染、不可点）——与改动前一致；浮层只作用于预览链接。
3. 预览内容是 KP **区域全文**（含该范围内标题行/空行，按 sidecar 范围原样）；超 12 行截止并标注截断。
4. `load_document` 是"整篇文档"级 RPC（后端已有缓存）；浮层内按文件去重，最多每候选一次，未新增缓存层。
5. 旧整页跳转模态代码保留（`showLinkPicker`/`confirmLinkPicker`），当前链接点击不可达；`link` 编辑/创建模态仍用同一 `#link-modal`，未受影响。

---

## 8. 门禁（本轮）
- `pytest -q tests`：**1516 passed**（基线 1516，不降）。
- `node --check`：全仓 66 个非 vendor JS，0 失败。
- `i18n_selftest`：PASS（exit 0，FAIL=0）。
- `12 剧本`：12/12（`run_interaction.py`，failed=0）。
- `team_audit`：**FAIL=0**；`prompt_drift`：FAIL=0 / NOT_RUN=0，exit 0。
- 真机：`link-popover-run.ps1` exit=0；用户 `Memoria.exe` PID 48812 前后一致；端口 9593 已释放；临时 KB 副本，未写 `docs/example/AAA_Vocab/**`。
