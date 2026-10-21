# P6「鸠占鹊巢」施工计划

> **状态**：设计稿（2026-10-21）
> **前置**：`S_render_frozen` 13/13 已冻结；`p5_perf_frozen` 已冻结；**task-47（L1/L3 补齐）必须完成**
> **风险等级**：**最高** —— 本片删除 legacy，之后无法回退到双跑对照

---

## 0. 核心策略：换实现，不换签名

**勘察结果（决定性）**：

| 项 | 数量 | 含义 |
|---|---|---|
| `app.js` 里 `renderPreview(` 调用 | **29 处** | ❌ **不能逐个改**（29 处 × 每处都可能遗漏） |
| `app.js` 里 `R.render(` 调用 | 3 处 | 可直接改 |
| 三个临时开窗 | 3 处（L14321 / 14346 / 14413） | 需迁入 render-core 后删除 |
| `renderer.js` | 18KB / 514 行 | 待删（确认无其他消费者后） |
| `surface/legacy-surface.js` | 15KB / 298 行 | 待删 |
| `markdown-preview.js` | 104KB / 2409 行 | **保留**（代码高亮/mermaid/math 仍被复用） |

**⇒ P6 的做法不是"把 29 处调用改成新 API"，而是「把 `renderPreview` 的内部实现换成 render-core」，让 29 个调用点一字不动。**

这是"鸠占鹊巢"的字面含义：**占其巢（同一个门面），换其主（实现）**。

---

## 1. 为什么必须这样切

| 做法 | 后果 |
|---|---|
| 改 29 个调用点 | 每处都要验证；漏一处 = 静默走 legacy（**并行事实源重新出现**） |
| **换 `renderPreview` 内部实现** | **单点改动**；29 个调用点行为不变（签名不变）；legacy 自然失去入口 |

**判据**：改完后 `renderer.js` 的 `R.render` 在 app.js 主链**不应再被调用**（可用调用计数证明）。

---

## 2. 分段施工（每段独立可验收、可回滚）

### P6a：`renderPreview` 内部切到 render-core

**前置勘察已完成（2026-10-21）**：29 处调用点的 `opts` 用法极度简单 ——
**27 处无 opts**（`renderPreview(doc)` / `renderPreview(state.doc)` / `renderPreview(res)`），
**仅 2 处传 `{incremental: true}`**（`app.js` 内两处 `setBlockSource` / `syncSourceToPreview` 路径）。
而 `incremental` 已被证明**只影响 loading 提示，不影响实际渲染**（`app.js:1985-1987` 无条件全量 `preview.innerHTML=""` + `R.render`）。
⇒ **P6a 的兼容面极小：签名 `renderPreview(doc, opts?)`、忽略 `opts` 即可。**

**做什么**
- `renderPreview(doc, opts)` 内部改为：
  ```
  parse（同一 parse）
    → MemoriaRenderCore.renderDocument / render(doc)
    → preview.innerHTML = "" + append
    → stampBlockLines / BlockIndex
    → 后处理（链接层 + 公式编排）
  ```
- **签名与返回值不变**（仍有 Promise、仍接受 `{incremental}` 兼容参数，内部可忽略）
- `R.render`（renderer.js）不再被调用

**验收（硬）**
1. `S_render_frozen` 同会话 dual **13/13 `diff=0`** —— ⚠️ 注意：此时 legacy 已不参与主链，**dual 对照的意义变了**；改为与**冻结基线**对比（`-newlegacy` 归档 vs 当前 new）
2. **11 交互剧本 11/11**
3. **调用计数**：`renderer.js` 的 `R.render` 调用次数 = **0**
4. 门禁 PASS 0

**回滚点**：`renderPreview` 内部一行开关（`USE_RENDER_CORE`）可切回

### P6b：三个临时开窗迁入 render-core

**要迁的三处**（`app.js`）：
| 开窗 | 现状 | 迁入目标 |
|---|---|---|
| `applyPreviewLinkLayer`（L14321） | `postProcessWikilinks` + `bindPreviewLinks` | render-core 渲染后自动执行（**块级作用域**） |
| `applyPreviewMathTypeset`（L14346） | token 自增 + `queuePreviewMathTypeset` + 打标 | render-core 内持公式编排入口 |
| `paintPreviewBlockPatch`（L14413） | 块级重绘门面 | render-core 的块级重绘方法 |

**验收**
1. 3 个开窗**全部删除**（`grep "MemoriaApp.surface.applyPreview"` = 0）
2. `new-surface.js` 里**不再引用**这三个 window 属性
3. 13/13 + 11 剧本 + 门禁

### P6c：删除 legacy 插头

**做什么**
- 删除 `surface/legacy-surface.js`
- `registry.js`：只保留 `new`；`switchTo('legacy')` 返回明确错误或降级到 new（**不得静默**）
- `index.html`：移除 legacy-surface 的 script 引入
- `new-surface.js`：`setMode`/`collectText` 等 legacy 兼容面自行实现或删除

**验收**
1. `switchTo('legacy')` ⇒ **明确失败**（`onDegraded` 或抛错），不静默
2. 13/13 + 11 剧本 + 门禁
3. `grep legacy-surface` = 0

### P6d：删除 renderer.js + 清理死代码

**做什么**
- 删除 `renderer.js`（514 行）——**前提：`grep "MemoriaRenderer"` 只剩注释或已删除**
- 清理 `app.js` 里 legacy 渲染相关的死代码（`R.render`、`R.renderRange` 等）
- 清理 `markdown-preview.js` 中**确认无人调用**的旧渲染路径（**谨慎**：该文件 2409 行，大部分仍被复用）

**验收**
1. `grep "MemoriaRenderer"` = 0（除文档）
2. 13/13 + 11 剧本 + 门禁
3. **`markdown-preview.js` 不得大改** —— 只删已证明无消费者的函数

---

## 3. 全域验收（P6 收口）

| # | 判据 | 来源 |
|---|---|---|
| 1 | `S_render_frozen` 13/13 `diff=0` | 已冻结基线 |
| 2 | 11 交互剧本 11/11 | `run_interaction.py` |
| 3 | 门禁 PASS 0 | `check_line_attr_gate.js` |
| 4 | **`R.render` 调用 = 0** | 调用计数 |
| 5 | **3 个开窗全部删除** | grep |
| 6 | **`legacy-surface.js` / `renderer.js` 已删** | 文件不存在 |
| 7 | `switchTo('legacy')` **明确失败** | 手动/剧本 |
| 8 | **性能不退化**：工作量计数与 P6a 前**逐项相同** | `p5perf_workload.mjs` |
| 9 | 编辑不丢字（随机序列 3 组 × 100 步） | `p4d_*` 复用 |

---

## 4. 风险与缓解

> 风险分级、单向门判定与回滚计划要求见 [`docs/guides/risk-management.md`](../guides/risk-management.md)。

**本片对应的风险登记册条目**：
- **R-04**（单向门）：删除 legacy 后永久失去 A/B 对照 —— **前置：task-47 必须先完成**
- **R-06**：`markdown-preview.js` 104KB 仍承担高亮/mermaid/math，P6d 禁止大改
- **R-07**：`renderPreview` 29 个调用点 —— 已用"换实现不换签名"缓解

**执行前必须通过**：`python scripts/benchmark/maintenance/risk_preflight.py --operation "P6a" --require-baseline artifacts/baseline/s_render_frozen --require-baseline artifacts/baseline/p5_perf_frozen --allow-dirty-src src/memoria/services/agent/ask_stream.py`



| 风险 | 概率 | 缓解 |
|---|---|---|
| **29 个调用点里有特殊 opts 依赖** | 中 | P6a 前先枚举 29 处的 `opts` 用法（`incremental` / `keepScroll` 等），逐项确认 new 实现兼容 |
| `markdown-preview.js` 里还有旧渲染链被 assist/复习卡使用 | **高** | **P6d 前必须 grep 全部消费者**；若有，保留该文件不删 |
| 公式/mermaid 异步时序改变 | 中 | P6b 迁移后立即跑含公式的文档（scale-5k） |
| 删除 legacy 后发现回归 | 低 | **git 可回滚**；但双跑对照永久失去 —— 这正是 task-47 必须先做的原因 |
| 窗口化渲染路径（K4a 已回退） | 低 | 确认不需要 |

---

## 5. 与既有文档的关系

| 文档 | 关系 |
|---|---|
| `display-refactor-charter.md` | 总纲；S13/S14 待修项 |
| `stage2-plan.md` | P6 定义 |
| `render-fidelity-contract.md` | P6 的判等工具与冻结基线 |
| `view-surface-contract.md` §4.5 | 插头方法语义（P6c 后 §4.5 需标注"legacy 已删除"） |
| `org.md` §12 | 测量密封性协议（P6 后无 A/B，须改用冻结基线对照） |
