# task-187 — 补齐 KG 设计未落地项：毛球态判定（D-KGV-09）+ T-double（D-KGV-15）

> **开工基线**：HEAD `0337954e`（开工时；`docs/example` dirty=true，241 项）。
> **重要说明（提交归属）**：本任务代码/测试/首版 JSON 在 **2026-10-27 00:40:09 被提交 `313a9802`（作者 FreshTim）**，不是我 commit 的（任务要求不 commit）；我继续完成了修正后的验证脚本、最终 `verify_hairball_tdouble.json` 与本报告。本报告与最新 JSON 仍在工作区（未 commit），请 Lead 复核归属。
> **设计依据（只读）**：`docs/design/kg-visualization-v0.md §6`（D-KGV-09）、`§8`（T-double / D-KGV-15）；`PHASE4-RULINGS.md`。
> **纪律**：未改 `docs/**`、`docs/example/**`、`Package/**`、`src/memoria/services/**`；未 commit。

---

## 0. 一句话结论

- **§6 毛球态判定已实现**：前端 Union-Find（复用 `graph-groups.js` 既有能力，零新增字段），**单条件** `maxGroupShare >= 0.80`；阈值用真实语料实测校准（134/404 ⇒ **89.55%**；HEAD archive 61/154 ⇒ **81.97%**；良好/稀疏语料 ⇒ 2.74%–16.67%）。
- **判定结果流向**：`engine.loadPayload()` 内计算 → 挂 `engine.hairball` + 发 `hairball` 事件 + `engine.hairballReport()` 读取；**当前无 UI 消费方**（诚实状态，见 §4）。
- **§8 T-double 已实现**：7 个视觉通道声明 + `checkVisualEncoding()` 机检；当前 galaxy 的 2D 半径/颜色/halo 亮度与 3D 颜色/emissive/halo 全部 **同变量(degree)同方向(+)** ⇒ PASS；红 fixture（不同变量 / 方向相反）均报冲突。
- **双向证红**：旧三条件组合对"良好语料"也命中（无判别力，已用测试固定）；新判定在已知毛球态命中、已知良好语料不命中。

---

## 1. 缺口一：毛球态判定

### 1.1 实现位置

`src/memoria/ui/static/app/js/graph-groups.js`（末尾追加，不移动既有行号）：

```
HAIRBALL_MAX_GROUP_SHARE_THRESHOLD = 0.80
HAIRBALL_CALIBRATION              // 实测值与推导（见 §2）
computeHairball(nodes, links, groupsMeta, opts?)
  → { isHairball, rule:"max_group_share >= threshold", threshold,
      metrics:{nodeCount, edgeCount, componentCount, maxGroupSize, maxGroupShare,
               labels, edgesPerNode, avgDegree, zeroDegreeCount}, calibration }
```

`src/memoria/ui/static/app/js/graph-engine.js`：

```
loadPayload() 末尾：
  this.hairball = MemoriaGraphHairball.computeHairball(this.nodes, this.links, this.groups);
  this._emit("hairball", this.hairball);
hairballReport()  // 只读
```

### 1.2 判定规则（可复现）

```
isHairball := nodeCount > 0 AND maxGroupShare >= 0.80
maxGroupShare := max(连通分量节点数) / nodeCount
连通分量 = 前端 Union-Find（graph-groups.js#UnionFind；与分组同源，零新增字段）
```
- **单条件**（按 D-KGV-09 裁决）：旧 `labels>60 OR edges/nodes<4 OR avgdeg<8` 已废弃；
- 其余指标仅作为 `metrics` 诊断字段输出，**不参与判定**。

---

## 2. 阈值校准（T-hairball-1 / T-hairball-2）

### 2.1 测量条件（可复现）

| 项 | 值 |
|---|---|
| 测量日期 | 2026-10-27 |
| HEAD | `0337954e`（dirty=true） |
| 语料（hairball 实测） | 工作区 `docs/example/AAA_Vocab`，manifest_sha256 = `236a48932bdb0c8a5aabe2644d97390e72526973b59919a547a13e9c7be6fc7f`，post_build=true |
| 语料（HEAD archive 对照） | `git archive HEAD docs/example/AAA_Vocab`，manifest_sha256 = `931a57f7a1a362ef57500ee01a543dd8eb44d4454ff7627d096c2d3682f4c746` |
| 采集 | `memoria.graph.collector.collect_graph_data` + 同源并查集 |

### 2.2 实测值（T-hairball-1）

| 语料 | 节点/边 | 连通分量 | 最大分量 | **maxGroupShare** | 判定（阈值 0.80） |
|---|---|---|---|---|---|
| **真实语料（工作区，134/404）** | 134 / 404 | 15 | 120 | **0.8955（89.55%）** | **命中**（毛球态） |
| 同 KB HEAD archive | 61 / 154 | 11 | 50 | **0.8197（81.97%）** | **命中** |
| 真实稀疏 KB `artifacts/baseline-kb/数字通信原理` | 329 / 36 | 293 | 9 | **0.0274（2.74%）** | 不命中 |
| 合成良好语料（12 群 × 10 节点） | 120 / 120 | 12 | 10 | **0.0833（8.33%）** | 不命中 |
| 合成毛球语料（60 节点单群+弦） | 60 / 62 | 1 | 60 | **1.0000（100%）** | 命中 |

> 补充诊断（真实语料，非判定条件）：labels=134，edges/nodes=3.015，avgDegree=6.03，zeroDegree=14。
> 这与设计 §6 表一致（原三条件中 labels 命中、另两条不命中 ⇒ 旧"任一命中"永远命中）。

### 2.3 阈值推导（T-hairball-2）

```
已实测毛球态下界 = min(0.8955, 0.8197) = 0.8197
已实测良好/稀疏上界 = max(0.0833, 0.0274) = 0.0833
取 2pp 容差（同一语料 build/布局差异的保守余量）：
threshold = 0.8197 - 0.0197 = 0.80
```
- 0.80 低于两个已实测毛球态值（分别留 9.55pp / 1.97pp 余量），远高于良好/稀疏上界（0.0833）；
- **不是"永远命中/永远不命中"**：T-hairball-3 双向红/绿测试固定了这一点。

---

## 3. 缺口二：T-double 检查（D-KGV-15）

### 3.1 实现位置

`src/memoria/ui/static/app/js/graph-engine.js`（末尾追加）：

```
VISUAL_CHANNELS  // 7 条通道声明（id/surface/channel/variable/direction/source）
checkVisualEncoding(channels) → {pass, conflicts, bySurface, encodedVariables, channels}
MemoriaGraphVisualChannels = { CHANNELS, check }
```

判定口径（冻结）：**同 surface 内**，同一变量 + 同方向 = 冗余强化（PASS）；不同变量、或同变量方向相反 = 冲突。

### 3.2 当前通道声明（与生产渲染公式逐条对应）

| 通道 | 变量 | 方向 | 生产代码依据 |
|---|---|---|---|
| 2D 节点半径 | degree | +1 | `graph-view-2d.js#_radiusForNode` / `engine.radiusForNode`（连续分位） |
| 2D galaxy 颜色 | degree | +1 | `graph-view-2d.js#galaxyNodeColor2D(ratio)`（ratio 越大越亮） |
| 2D galaxy halo 亮度 | degree | +1 | `galaxy 分支 halo = 0.14 + ratio * 0.3` |
| 3D 节点半径 | **null（等大）** | 0 | `_rebuildGraph` 节点 `scale=1`（D-KGV-04） |
| 3D galaxy 颜色 | degree | +1 | `graph-view-3d.js#galaxyColor3D(ratio)` |
| 3D galaxy emissive | degree | +1 | `emissiveIntensity = 0.25 + ratio * 0.45` |
| 3D galaxy halo 亮度 | degree | +1 | halo `baseOpacity`（半径等大，D-KGV-16；亮度编码 degree） |

### 3.3 机检（T-double-1 / T-double-2）

`tests/test_kgviz_hairball_tdouble.py`：

| 测试 | 结果 |
|---|---|
| T-double-1：当前 channels ⇒ `pass=true`，conflicts=[]，encodedVariables=["degree"] | ✅ |
| T-double-2 红 fixture ①：`2d.galaxyColor` 改为变量 `alphabetical`（不同变量） | ✅ `pass=false`，reason=`different_variables` |
| T-double-2 红 fixture ②：`2d.galaxyColor` 方向改 -1（同变量反向） | ✅ `pass=false`，reason=`opposite_direction` |
| 声明↔生产代码静态一致性（半径/颜色/halo 公式、3D `scale=1`） | ✅ |

真机侧（`verify_hairball_tdouble.json`）：
- galaxy 模式下生产函数 **degree ↔ radius 相关系数 = 0.993**（134 节点全量）；
- `MemoriaGraphVisualChannels.check(CHANNELS)` 在真机返回 `pass=true`；
- 像素亮度采样未取得可靠读数（视图从隐藏切到显示时 `simNodes` 屏幕坐标未同步，取不到有效采样点）⇒ 颜色/halo 的**方向**由静态公式断言 + 声明检查覆盖，见 §7 局限。

---

## 4. 毛球态判定的 UI 表现（任务要求说明）

**当前：判定已实现，但暂无 UI 消费方。** 数据流：

```
engine.loadPayload()
  → engine.hairball = {isHairball, rule, threshold, metrics, calibration}
  → engine._emit("hairball", report)     // 事件已发出，目前无监听者
  → engine.hairballReport()              // 只读读取
```
- 本任务写域只有 `graph-*.js` / `tests/` / `artifacts/`，**不含 `app.js`、i18n、CSS**，因此没有新增提示条/徽标；
- 下一步（建议由 Lead 安排小任务）：在 `app.js` 监听 `engine.on("hairball")`，当 `isHairball=true` 时在图上显示非阻断提示（如"图较密，可放大或按群筛选"），并接入 i18n；判定本身**不是**"图不可用"的硬门禁（D-KGV-09 原意是粗粒度提示）。

---

## 5. 验收对照

| 验收 | 结果 |
|---|---|
| **T-hairball-1** 真实语料最大分组占比 | ✅ **0.8955（120/134）**，测量条件见 §2.1 |
| **T-hairball-2** 实测校准阈值 + 可复现判据 | ✅ 阈值 **0.80**（= min(hairball 0.8197) − 0.02 容差），判据 `maxGroupShare >= 0.80` |
| **T-hairball-3** 双向证红 | ✅ 毛球态（100%/89.55%/81.97%）命中；良好语料（8.33%）不命中；旧三条件在良好语料上仍命中 ⇒ 无判别力（测试固定） |
| **T-double-1** galaxy 三通道同变量同方向 PASS | ✅ 声明检查 PASS + 真机 radius 相关 0.993 + 静态公式断言 |
| **T-double-2** 红 fixture 必须报冲突 | ✅ 不同变量 / 方向相反 两种红 fixture 均 `pass=false` |
| **T-all-1** 门禁 | ✅ pytest **1655 passed / 0 failed**；node 0 fail；i18n PASS；team_audit **FAIL=0**；12 剧本 **12/12**（`raw-interaction-t187-final_0337954e.json`） |
| §8 真人判读（U-KGV-5） | ⏸ **T-size-1 / T-label / T-depth 仍未做**（需真人；本任务按任务书确认不代做） |

---

## 6. 改动文件 / 产物

```
src/memoria/ui/static/app/js/graph-groups.js   +86 行（毛球态判定 + 校准常量 + T-double 声明？否：仅毛球）
src/memoria/ui/static/app/js/graph-engine.js   +143 行（hairball 接入 + 视觉通道声明/T-double 检查）
tests/test_kgviz_hairball_tdouble.py           新增 217 行（6 条机检，含双向红/绿 fixture）
artifacts/agent/verify/todo/kgviz-hairball-tdouble/
  verify_hairball_tdouble.py / verify_hairball_tdouble.json / shots/01_graph2d_galaxy_tdouble.png
```
> 注：上述 `src` 与测试文件已被人提前提交 `313a9802`（见文首说明）；最新 JSON/报告仍在工作区。

## 7. 诚实局限（登记）

| # | 项 | 说明 |
|---|---|---|
| L1 | **maxGroupShare 是粗粒度代理** | 一个"连通但可读"的图也可能因单一大分量命中；判定应作为提示，不是硬门禁。 |
| L2 | **UI 消费方缺位** | 判定/事件/读取接口已就绪，但无提示条（写域不含 app.js/i18n）；需要后续小任务接线。 |
| L3 | **T-double 真机像素采样失败** | 颜色/halo 方向未用真实像素相关性验证；已用"公式静态断言 + 声明机检 + 真实 radius 相关 0.993"覆盖，像素级留作增强。 |
| L4 | **阈值基于当前设计语料 + 一个稀疏真实 KB** | 未来若出现"中等连通（60–80%）但可读"的真实 KB，需按新实测复核阈值（校准常量集中在一个文件，改动成本低）。 |
| L5 | **U-KGV-5 真人三项仍未做** | T-size-1 / T-label / T-depth 需真人参与，需 Lead 安排。 |
