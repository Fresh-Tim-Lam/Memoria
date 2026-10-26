# contentMinPx.def 双源收口 报告

> Lead 背景：改「文档区保底宽度」默认值时改了 4 处才生效，其中两处是同义双源：
> `display-settings.js CONTENT_MIN_RANGE = { ..., def: 360 }` 与 `agent-panel.js const CONTENT_MIN_PX = 360`。

## 0. 结论速览
- ✅ `contentMinPx` 默认值现在**只有一处事实源**：`display-settings.js` 的 `CONTENT_MIN_RANGE.def`；
  新增对外接口 `MemoriaDisplaySettings.getContentMinDef()`。
- ✅ `agent-panel.js` 不再独立写死默认值：改为 `contentMinDefPx()` 优先读上述接口；
  只保留 `CONTENT_MIN_PX_LAST_RESORT = 360` 作为“设置模块缺席/异常时的**最后兜底**”（注释明确它不是第二事实源）。
- ✅ 同文件内 `DEFAULTS.contentMinPx` 也改为引用 `CONTENT_MIN_RANGE.def`（原来 360 也写了两遍）。
- ✅ 实测「改一处即生效」：**只改 display-settings.js 的 def** ⇒ agent-panel 生效值随之变化；
  **只改 agent-panel 兜底** ⇒ 不生效（display-settings 在场时）。
- ✅ 顺带排查其它 `def/默认值` 双写并登记（本任务只改 contentMinPx）。

---

## 1. 代码改动（本任务独立 patch）
```
display-settings.js  +14/−7
agent-panel.js       +30/−12
patch: artifacts/agent/verify/todo/contentmin-def-single-source.patch（12,808B；校验不含 task-164/task-169 字样）
```

### display-settings.js
- `CONTENT_MIN_RANGE` 上移到 `DEFAULTS` 之前；
- `DEFAULTS.contentMinPx: CONTENT_MIN_RANGE.def`（同文件也不再写第二份 360）；
- 导出新增：
```js
getContentMinDef() { return CONTENT_MIN_RANGE.def; }
```
- 注释改写：`def` = 唯一事实源；agent-panel 只保留最后兜底。

### agent-panel.js
```js
// 唯一事实源 = display-settings.CONTENT_MIN_RANGE.def（经 getContentMinDef 读取）
const CONTENT_MIN_PX_LAST_RESORT = 360; // 仅模块缺席/异常时的最后兜底，不是第二事实源
function contentMinDefPx() { ...读 getContentMinDef()，异常才回退 LAST_RESORT... }
function currentContentMinPx() {
  ...读 ds.getContentMinPx()；夹紧范围也取自 ds.CONTENT_MIN_RANGE...
  return contentMinDefPx(); // 最后兜底
}
```
- `getDockState().contentMinPx` 由 `CONTENT_MIN_PX` 改为 `contentMinDefPx()`；
- 相关注释（`CONTENT_MIN_PX=360` 三处）改为“默认值来自 display-settings 的 def”。

---

## 2. 验证（真机 WebView2 + 真实三文件；隔离干净树）
> ⚠️ 共享工作区当时 `agent-panel.js`（render-perf task-169）与 `app.css` 为「他人未提交改动」，
> 按 Lead 要求**未动共享 dirty 文件**；本任务在隔离 worktree（HEAD `f21307ac` + 本 patch）完成验证。
> 探针 `contentmin-def-probe.mjs` / runner `contentmin-def-run.ps1`，端口 9597，用户 Memoria PID 48812 前后一致。

### Run A —— **只改 display-settings 的 def（文件级）**，agent 兜底仍 360
| 检查 | 结果 |
|---|---|
| `MemoriaDisplaySettings.getContentMinDef()` | **420** |
| `MemoriaDisplaySettings.getContentMinPx()` | **420** |
| `MemoriaAgentPanel.getContentMinPx()`（agent 侧实际生效值） | **420** |
| `getDockState().contentMinPx`（dock 计算口径） | **420** |
| `availablePx` | **844**（窗口 1264 − 420；若默认仍 360 则为 904，差 60） |
| 隐藏 display-settings（模拟模块缺席） | agent 生效值 → **360**（最后兜底） |
| 用户存了 contentMinPx=300 | agent 生效值 → **300**（用户设置优先于 def，符合既有语义） |

⇒ **只改 display-settings.py 的一个 def，agent 生效值从 360 → 420（dock 可用宽度同步 −60）** ✅

### Run B —— **只改 agent-panel 的兜底（临时 999）**，display def=420 不变
| 检查 | 结果 |
|---|---|
| agent 生效值 | **420**（不是 999 ⇒ 兜底不是第二事实源） |
| `getDockState().contentMinPx` | **420** |
| 隐藏 display-settings 后 | **999**（只有模块缺席时才回退到兜底） |

⇒ **改兜底不生效；只有设置模块缺席才回退兜底** ✅（正是任务要求证明的“不再是第二事实源”）

> 说明：`DEFAULTS.contentMinPx` 在模块加载时引用 def；因此“改 def 生效”的验证是**文件级（重启/重载 app）**，
> 不承诺“运行中改 def 对象后立即变”。用户存的 contentMinPx 始终优先于 def（既有语义不变）。

---

## 3. 顺带排查：其它 def/默认值是否双写（本任务只收口 contentMinPx）
| 位置 | 内容 | 判定 |
|---|---|---|
| `app.js:19394-19397` | `PREVIEW_CACHE_MAX=8` / `PREVIEW_CACHE_MAX_LINES=4000` / `PRELOAD_MAX_LINES=1200` / `PRELOAD_MAX_TABS=4`（注释称“兜底”，生效值来自设置） | **疑似同类风险**：与 `display-settings.js:514-529 PERF_DEFAULTS`（8 / 8000 / 4000 / 8）**3 项数值不一致**；设置模块缺席时才用这些常量 ⇒ 改设置默认值不会改兜底。**登记，不本任务改** |
| `preview-cache-policy.js:46-55 DEFAULTS` | previewCacheMax / previewCacheMaxLines / preloadMaxLines / preloadMaxTabs… | **有意双写 + 已有跨文件钉子测试**（注释 `必须逐字相等`，测试逐键核对）⇒ 不是静默第二事实源；登记 |
| `display-settings.js PERF_RANGES` vs `preview-cache-policy.js:67-70 RANGES` | 区间 | 同上，有意双写 + 测试核对；登记 |
| `previewFontSize / uiScale / fonts / fontBrand / backgroundPreload` | 仅 `display-settings.js DEFAULTS` 出现；app.js/agent-panel 未发现第二份字面默认值 | 暂未发现双写 |
| `agent-panel.js DOCK_*` | dock 尺寸默认（16/22/120rem） | 不属于显示设置域，未登记为同类 |

---

## 4. 门禁（⚠️ 与共享工作区隔离说明）
- **本任务隔离树**（HEAD `f21307ac` + 本 patch；不含他人未提交改动）：
  - `pytest -q tests` → **1516 passed**（tracked 测试；共享仓另有 2 个他人的 untracked 测试文件，故共享收集数为 1524）
  - `node --check` 66 文件 0 失败；`i18n_selftest` PASS
  - worktree 的 team_audit / prompt_drift 因**缺失他人 untracked artifacts**而报 `artifact_refs`/prompt 漂移（如 task-1/2/10/11 交付物不存在）⇒ 这两项在 worktree 无意义，以共享仓结果为准
- **共享仓当前**（HEAD `f21307ac`，尚不含本 patch；含 render-perf 未提交 agent-panel/css）：
  - `pytest -q tests` → **1524 passed**
  - `team_audit` → **FAIL=0**；`prompt_drift` → FAIL=0 exit 0；12 剧本 **12/12**
  - 本 patch 应用后再跑应保持（纯前端默认值读取方式改动，无后端/契约变化）。

---

## 4.5 追加：已落地共享工作区（HEAD 前进到 5a919691）
等待期间 render-perf 的 task-169 已提交（HEAD `f21307ac` → `5a919691`），共享写域变 clean；本 patch 已
`git apply` 成功落地到共享工作区（当前 `git diff` = agent-panel.js +30/−12、display-settings.js +14/−7）。
在共享工作区（**含本 patch**）重跑门禁：
- `pytest -q tests` → **1524 passed**
- `node --check` 66 文件 0 失败；`i18n_selftest` PASS
- `prompt_drift` → FAIL=0（exit 0）；12 剧本 **12/12**
- `team_audit` → **FAIL=2（外部，并非本 patch）**：
  - `deliberation_quality: dq5 冻结收据不完整/不匹配 — docs/guides/lead-dispatch-rules.md 标准 sha 不匹配`
  - `steward_self_audit: 标准已变而收据未更新 — docs/guides/lead-dispatch-rules.md 磁盘 vs 收据 sha 不一致`
  - 原因：task-169 提交同时更新了 `docs/guides/lead-dispatch-rules.md`（`git diff f21307ac..HEAD` 可见），
    收据未重写；本 patch 只改 `agent-panel.js`/`display-settings.js`，不涉及该文档 ⇒ 需 Lead/registrar 重读标准并更新收据。

## 5. 产物
```
artifacts/agent/verify/todo/
  contentmin-def-single-source.md      （本报告）
  contentmin-def-single-source.patch   （仅 display-settings.js + agent-panel.js 的改动）
  contentmin-def-probe.mjs             （真机探针：A/B 默认值单源验证）
  contentmin-def-run.ps1               （launcher，端口 9597）
  contentmin-def-A.json / .log         （Run A：只改 def=420）
  contentmin-def-B.json / .log         （Run B：只改兜底=999）
```

## 6. 限制
1. 默认值在模块加载时快照（`DEFAULTS.contentMinPx = def`），因此改 def 后需**重启/重载 app** 生效（与所有显示设置一致）。
2. 用户已保存的 `contentMinPx` 优先于 def（既有语义；本任务未改优先级）。
3. 本任务在隔离 worktree 开发（因共享 `agent-panel.js` 正被 render-perf task-169 修改），交付物是**可单独 apply 的 patch**；等 task-169 提交后应用并跑共享门禁即可。
