# task-175 — KG 节点大小「连续变化」落地（v0 冻结设计 A/B/C）

> **基线**：HEAD `3bdcb64f`（开工时）；本任务只改下面列出的前端文件 + 测试 + artifacts，未 commit。
> **设计依据（只读）**：`docs/design/kg-visualization-v0.md` §1（D-KGV-13 / 人裁决②：连续、不设挡位）、§8（T-size-2/3/4）；`USER-RULING-continuous-size.md`；`USER-RULING-node-size-range.md`（75%–165%）。
> **纪律**：未改 `docs/design/**`、`docs/example/**`、`Package/**`、`src/memoria/services/**`；未 revert 他人改动。

---

## 0. 一句话结论

**产品行为已变化**：2D 图谱节点半径不再是常量 6px，而是按度数在 **4.50–9.90px 之间连续映射**（21 个 distinct degree → 21 个 distinct 半径，平台段 0%）；3D 节点 **等大**（134 个 mesh 全部 scale=1）；节点 tooltip 显示 **degree 绝对原值**（中英双语）。

| 关闭条件 | 结果 |
|---|---|
| 1. 2D 连续变化（≥5 个不同 degree 半径两两不同且单调） | ✅ 实测 21 个 distinct 半径 == 21 distinct degree，单调无反转 |
| 2. 3D 仍等大（实测） | ✅ 134 meshes `allScaleOne=true`，`distinctGeometries=1` |
| 3. tooltip 显示 degree 原值（中英双语，截图） | ✅ zh「连接数 25」/ en「Connections: 25」，截图 02/02b |
| 4. T-size-2/3/4 机检 + T-size-3 必红 fixture | ✅ 见 §3；必红 fixture：3 个 distinct 半径 vs 25 distinct degree、平台段 **91.67%** ⇒ 被检出 |
| 5. 真机截图 | ✅ 见 §4（5 张） |
| 6. 门禁 | ✅ pytest **1534 passed**（基线 1526 + 8 新测）/ node 0 fail / i18n PASS / team_audit FAIL=0 / 12 剧本 12/12 |
| 7. 报告 + 截图 + 机检 JSON | ✅ 本文件 + `shots/` + `t-size-machine-check.json` + `verify.json` |

---

## 1. 实现（对照设计 §1，不自行发挥）

### A. 连续尺寸映射

```
radius(d) = R_MIN + (R_MAX - R_MIN) · t(d)
R_MIN = 4.50px, R_MAX = 9.90px（= 用户 nodeRadius 基准 × 0.75 / × 1.65；U-KGV-2：v0 按随基准缩放实现）
t(d) = (#distinct degree 值 < d) / (K-1)，K = 当前语料 distinct degree 数
```

- **纯函数**在 `src/memoria/ui/static/app/js/graph-engine.js` 新增并导出 `MemoriaGraphSizing`：
  `sizingRangeForBase / computeUndirectedDegrees / distinctSortedDegrees / percentileRankT / radiusForDegree`；
- `MemoriaGraphEngine.loadPayload` 一次 O(N+E) 建 `_degreeMap + _degreeDistinct`；实例方法 `degreeOf / degreeDistinct / radiusForNode / sizingRange`；
- `graph-view-2d.js`：
  - 节点半径 = `_radiusForNode(n.id, opts.nodeRadius)`（**不再** `opts.nodeRadius` 常量；**删除** galaxy 旧的比例再乘 `r*(1+ratio*0.5)`，避免双重缩放）；
  - 连线端点让位改用两端半径最大值（`_radiusForNode(link.source/target)`），避免大节点被箭头戳穿；
  - 命中半径改为 `max(opts.nodeRadius+6, radiusForNode+2)`（大节点边缘可点中，不回归交互）；
- `graph-view-3d.js`：`_rebuildGraph` 中节点 `scale` 恒为 **1**（设计 D-KGV-04：3D 等大）；**颜色/光晕仍按 galaxy 规则编码**（重要性用颜色，不用大小）。

**t(d) 的实现口径（必须披露）**：设计写「t = percentile-rank」，但纯 ECDF（`#(d'≤d)/N`）在并列多时会**永远达不到 1**（max 节点 t<1 ⇒ 达不到 R_MAX），且并列质量会形成平台。因此实现取 **distinct degree 的归一化 rank**：同 degree 同半径（设计 §1.4 正确行为）、min→4.5 / max→9.9、distinct 半径 == distinct degree。若 Phase 4 要改为纯 ECDF，只需改 `percentileRankT` 一个函数——但 **T-size-4 会因 max<9.9 失败**，故当前口径与设计 §1.2/§1.3 的目标（最厚节点可达 R_MAX、无平台）自洽。

**U-KGV-2 实际行为（记录）**：`nodeRadius` 设置 4–12 时按比例缩放：
```
base 6  → [4.50, 9.90]（设计值）
base 4  → [3.00, 6.60]
base 12 → [9.00, 19.80]
```

### B. tooltip 显示 degree 绝对原值（硬要求）

- `graph-label.js#resolveNodeHoverHtml(node, opts)` 新增 `opts.degreeText`；有值时插入 `.-graph-hint-degree` 行（比其它 meta 更醒目，tabular-nums）；
- `app.js#updateGraphNodeHint` 用 `state.graphEngine.degreeOf(node.id)`（与映射同口径）→ `T("graph.hover.degree", { n })`；
- i18n：zh `连接数 {n}` / en `Connections: {n}`（`graph.hover.degree`）；CSS `. -graph-hint-degree` 增样式；
- 兼容：未传 degreeText 时 HTML 与旧版完全一致（其它调用方零影响）。

### C. 三项机检（T-size-2/3/4）

- 落地点：`tests/test_kgviz_size_continuous.py`（8 条 pytest，机检直接跑生产纯函数）；
- 另产出可复跑脚本 `artifacts/agent/verify/todo/kgviz-size-continuous/verify_size.py`，把机检结果写成 `t-size-machine-check.json`，并做真机验证写 `verify.json`。

---

## 2. 改动文件（`git diff --stat`）

```
src/memoria/ui/static/app/js/graph-engine.js   +114
src/memoria/ui/static/app/js/graph-view-2d.js  +28/-?  (连续半径 / 连线让位 / 命中半径)
src/memoria/ui/static/app/js/graph-view-3d.js  +5/-?   (scale 恒 1)
src/memoria/ui/static/app/js/graph-label.js    +11/-?  (degreeText)
src/memoria/ui/static/app/js/app.js            +7/-?   (tooltip 接线)
src/memoria/ui/static/app/css/app.css          +8      (.-graph-hint-degree)
src/memoria/ui/static/app/i18n/{zh-CN,en}.js   +4 each (graph.hover.degree)
tests/test_kgviz_size_continuous.py            新增（8 条）
artifacts/agent/verify/todo/kgviz-size-continuous/  报告 + 脚本 + JSON + 5 图
```

无 `docs/**`、无 `src/memoria/services/**`、无 `Package/**`、无 `docs/example/**` 改动；未 revert 他人改动。

---

## 3. 机检结果（`t-size-machine-check.json`）

### T-size-2 单调性 ✅
25 个 distinct degree（0/1/2/…/22/24/25）→ 半径逐对非递减，**0 反转**。

### T-size-3 连续性 ✅（含必红 fixture）

代码实现（绿）：
```
distinctDegrees = 25
distinctRadii   = 25      ← 一一对应
plateau         = {ratio: 0, flat: 0, total: 24}   ← 无平台（相邻 rank 半径差 <0.01px 的段占比 0%）
```

**必红 fixture（先证红）**：故意把映射改成「3 档」（t→0/0.5/1）：
```
bucketed distinctRadii = 3  vs distinctDegrees = 25   ⇒ pass_distinct=false
plateau.ratio = 91.67%（22/24 段 <0.01px）             ⇒ pass_plateau=false
detectedAsBucketed = true
```
⇒ 该检查**确实能识别"偷偷分桶"**，不是恒绿装饰。

### T-size-4 范围 ✅
```
base 6 : min=4.50  max=9.90（±0.5 内；反锯齿 +1.0px 为渲染层常量偏移，差分判据抵消）
base 4 : [3.00, 6.60]；base 12 : [9.00, 19.80]（随用户设置缩放，U-KGV-2）
```

---

## 4. 真机验证（`verify.json` + `shots/`）

**环境/语料**：pywebview/WebView2 真机，HEAD `3bdcb64f`，语料 = 工作区 `docs/example/AAA_Vocab` 现场副本（`ev:corpus:p3-live-134`：**134 节点 / 404 边**，manifest sha `583ed4ed…`；与冻结设计 §7 一致）。

### 4.1 2D 实际绘制半径（拦截 `CanvasRenderingContext2D.prototype.arc` 采集一次 draw）
```
nodes=134  links=404
drawRadiiCount=134
distinctDrawn=21   distinctDegrees=21   distinctEngineRadii=21
minDrawn=4.5       maxDrawn=9.9
plateauRatio=0
drawnEqualsEngine=true   ← 画布实际半径 == engine.radiusForNode（不是只测映射函数）
5 个样本：perilous degree25 → r9.9 / 其余见 verify.json sample
```
⇒ 节点大小**真的画出来了**，且**连续**（21 distinct degree ↔ 21 distinct 半径，无平台）。

### 4.2 3D 等大
```
active=true  meshes=134  allScaleOne=true  distinctGeometries=1
camera fov=50, z=1791.2
```
⇒ 3D 节点 mesh 全部等大；透视造成的近大远小是深度线索（设计明确 3D 不用大小编码）。

### 4.3 tooltip 中英双语（截图 02 / 02b）
```
zh: "perilous\n连接数 25\nID · perilous\nvocab/perilous.md…"
en: "perilous\nConnections: 25\n…"
       degree line class = .-graph-hint-degree
```
最高 degree 节点（perilous, degree=25）与最低（media-crime-details, degree=0）。

### 4.4 截图
```
shots/01_graph2d_continuous_size.png          全图（连续大小已生效）
shots/01b_graph2d_zoomed_size_visible.png     放大后：不同节点大小肉眼可见（k≈3.2）
shots/02_tooltip_degree_zh.png                中文 tooltip「连接数 25」
shots/02b_tooltip_degree_en.png               英文 tooltip「Connections: 25」
shots/03_graph3d_equal_size.png               3D 等大
```

---

## 5. 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q`（基线 1526） | **1534 passed / 0 failed**（113.7s；1526 + 新增 8 条） |
| `node --check` 全部前端 js | **0 fail** |
| `i18n_selftest.js` | **PASS，exit 0** |
| `scripts/agent/team_audit.py` | **FAIL=0**（86 条：WARN 56 / INFO 30，均既有） |
| 12 交互剧本 | **12/12，failed=0**（29.3s，`scripts/benchmark/surface/results/raw-interaction-t175-final_3bdcb64f.json`） |

---

## 6. 未做 / 已知风险（诚实登记）

| # | 项 | 说明 |
|---|---|---|
| R1 | **galaxy 风格仍是「颜色 + 大小」双编码** | 本任务按设计「2D 用大小、3D 等大」实现，未改 galaxy 颜色；T-double 检查项会报告这个冲突。是否二选一需要 Phase 4 后续裁决（设计文档写了 T-double，但本轮任务只到 A/B/C） |
| R2 | **3D galaxy 光晕仍随 degree 变化** | 节点 mesh 已等大（scale=1）；光晕 `_syncHaloGlow` 的 opacity/尺寸仍由 ratio 驱动（装饰性发光，不是节点大小）。若要求绝对等大含光晕，可另派一行改动 |
| R3 | **标签 LOD/避让 / 布局种子 / 埋点** | 明确不在本任务（Lead 已另派）；本任务没有顺手改 |
| R4 | **t(d) 口径** | 见 §1：用 distinct-degree 归一化 rank（非纯 ECDF）。理由与失败后果已写；若 Phase 4 要纯 ECDF，需重算 T-size-4 预期 |
| R5 | **语料身份** | 真机验证用工作区现场语料（134/404，manifest `583ed4ed…`）；该语料**不可从 git 复现**（设计 §7 已声明），本次已记录，不改变结论 |
| R6 | **用户设置 4–12 缩放** | 按「随基准缩放」实现；若人希望固定 4.5–9.9 不随设置变，需改 `sizingRangeForBase` 一处（U-KGV-2） |

---

## 7. 复跑

```powershell
# 机检 + 真机（需要 WebView2 环境；会启动/结束自己的 app 实例，不动用户进程）
.venv\Scripts\python.exe artifacts/agent/verify/todo/kgviz-size-continuous/verify_size.py

# 只跑 pytest 机检
.venv\Scripts\python.exe -m pytest tests/test_kgviz_size_continuous.py -q
```
产物：`t-size-machine-check.json` / `verify.json` / `shots/`。
