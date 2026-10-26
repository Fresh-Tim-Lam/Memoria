# task-176 — 布局确定性种子 + 会话内保位（D-KGV-07）

> **基线**：HEAD `f43c4478`（开工时）；本任务只改 3 个前端文件 + 1 个新测试 + artifacts，未 commit。
> **设计依据（只读）**：`docs/design/kg-visualization-v0.md §4`（D-KGV-07：①确定性种子 ②会话内保位 ③新节点锚点生长）、§8（T-stable）；`PHASE4-RULINGS.md`。
> **纪律**：未改 `docs/**`、`docs/example/**`、`Package/**`、`services/**`；**未改任何力导向参数**（alpha/decay/斥力/链接距离/迭代数原样）；未 revert 他人改动。

---

## 0. 一句话结论

**「每次打开图谱布局都大跳」已修复**：2D 与 3D 布局的**全部 13 处初始化/守卫随机源**改为可注入确定性 PRNG（默认固定种子 `0x9E3779B9`），
- 同一语料 + 同种子：连续初始化 2 次坐标**逐节点字节级一致**（2D/3D 都验证）；
- **换种子 ⇒ 134/134 节点坐标全变**（证明随机性还在，不是把随机删成规则圆环）；
- 同一库**独立启动 3 次**：节点位置哈希与**截图 PNG 字节完全一致**；
- hover / zoom / select / 切 graphStyle 后**布局坐标完全不变**（无 reheat）。

| 验收 | 结果 |
|---|---|
| **T-stable-1** 同语料+同种子连续初始化 2 次 ⇒ 字节级一致 | ✅ 2D/3D `firstEqualsSecond=true`；真机 3 次启动位置哈希全等 `1769879743` |
| **T-stable-2** 换种子 ⇒ 坐标必须不同 | ✅ alt seed（`0x12345678`）后 **134/134** 节点改变；恢复默认种子后与首次完全一致 |
| **T-stable-3** 同一库连续打开 3 次 ⇒ 屏幕坐标/截图一致 | ✅ 3 张 `stable3_run{1,2,3}.png` **sha256 完全相同** `96bc345c…` |
| **T-stable-4** hover/zoom/select/切样式后相对位置不变 | ✅ `hover=true, zoom=true, styleSwitch=true, select=true, allUnchanged=true` |
| **T-stable-5** 2D 与 3D 都要有种子 | ✅ 两个 layout 模块均有 `setSeed/getSeed`；3D 真机同种子一致、换种子 134/134 改变 |
| **先证红**（改前连续初始化 2 次应不同） | ✅ 机检必红 fixture：把 RNG 换回非确定性 `Math.random` ⇒ 两次初始化坐标**不同**（测试红）；改后同种子两次**相同**（绿） |

---

## 1. 实现（只替换随机源，不动力导向算法）

### 1.1 共享种子工具（`graph-engine.js`）

```js
const DEFAULT_LAYOUT_SEED = 0x9e3779b9;              // 固定默认种子（v0 不做 UI 暴露）
function createSeededRandom(seed)                    // mulberry32：确定性 [0,1) 序列
function hashStringToSeed(str)                       // FNV-1a（保留给将来"按语料派生种子"）
global.MemoriaGraphSeed = { DEFAULT_LAYOUT_SEED, createSeededRandom, hashStringToSeed };
// engine 实例：layoutSeed() / setLayoutSeed(seed)
```

### 1.2 两个布局模块（`graph-layout-2d.js` / `graph-layout-3d.js`）

- 构造参数支持 `layoutSeed`，默认 `0x9E3779B9`；`setSeed(seed, {relayout})` / `getSeed()`；
- **每次 `loadFromEngine()` 都把 RNG 重置到本种子**（`this._rng = makeLayoutRng(this._seed)`），
  所以第二次初始化不是"接着随机"，而是从完全相同的序列重新开始；
- 初始化函数（`initialPositions2D/3D`、`initialPositionsForGroups`、`initialPositionsScattered`）全部接受注入 `rand`；
- **近重合守卫**（`dist2 < 1` 的 ±0.005 抖动，2D 2 处 / 3D 3 处）也改用同一种子 RNG；
- 布局文件中已**无任何 `Math.random` 调用**（只剩注释里说明"不再用"）；
- 未修改 `DEFAULTS` 中任何力导向参数。

### 1.3 ③ 新节点锚点生长 —— **降级登记（不硬做）**

- 现状：图谱每次 `loadGraphData()` 全量重载（`app.js#loadGraphData` → `applyGraphGroupLayout({relayout:true})`），
  没有"增量 setGraph"入口；要实现"增量节点在已有邻居附近生长"需要新增：节点集合 diff、旧位置保留、邻居锚点插值、与组/筛选/worker warmup 的交互 —— 成本超出本任务（>1 天、且会触碰布局语义）。
- 按任务允许的降级路径：**登记 U-KGV-7**，v0 不做；当前"同语料同种子 ⇒ 位置一致"已解决"每次打开大跳"，增量生长属于 v1。
- 若将来做，前置条件：图谱加载改为增量 diff（不是全量 reload），且锚点生长不触发全局 reheat。

---

## 2. 真机验证（`verify_seed.json` + `shots/`）

**环境/语料**：pywebview/WebView2，HEAD `f43c4478`，语料 = 工作区 `docs/example/AAA_Vocab` 现场副本（**134 节点 / 404 边**，manifest sha `583ed4ed…`，与设计 §7 一致）。
**比较口径**：为排除"运行时帧预算 tick 数不同"的干扰，T-stable-1/3 的比较统一用
`layout.stop() → view.resetSimulation() → 等 worker ready → layout.stop()` 的**确定性 warmup 位置**；这是"初始化是否一致"的最严格口径（下详 §4 局限）。

### 2.1 T-stable-1 / 2（2D，真机）
```
count=134  seed=2654435769 (0x9E3779B9)
firstEqualsSecond=true    aHash=bHash=1769879743
换 alt seed 0x12345678:
  differentSeedChanged=true  changedNodes=134/134
  restoreEqualsFirst=true（恢复默认种子后与首次完全一致）
```

### 2.2 T-stable-1（3D，真机）
```
hasSeedApi=true  count=134
firstEqualsSecond=true   differentSeedChanged=true   changedNodes=134/134   restoreEqualsFirst=true
```
（3D 同种子二次初始化一致、换种子全变；证明 3D 也真的用了种子，不是摆设。）

### 2.3 T-stable-3（同一库连续打开 3 次）
```
positionHashes = [1769879743, 1769879743, 1769879743]   positionsIdentical=true
pngSha256 = [96bc345c…, 96bc345c…, 96bc345c…]           pngIdentical=true
```
即 3 次独立启动的节点位置（x/y 全精度哈希）与截图**都字节级一致**。

### 2.4 T-stable-4（会话内保位）
```
hover=true  zoom=true  styleSwitch=true  select=true  allUnchanged=true
zoomK=0.15208386（zoom 生效，但布局坐标未变）
```
- hover：`engine._emit('hover')` 真实事件路径；
- zoom：canvas 上派发真实 `WheelEvent`（transform.k 变化，布局不变）；
- select：真实 `pointerdown/pointerup` 命中节点（走生产 `nodeClick` 路径，布局不变）；
- styleSwitch：`view.applyOptions({graphStyle:'galaxy'|'force'})`（只重绘/重建渲染对象，不重置布局）。

### 2.5 截图
```
shots/01_graph2d_seeded.png      2D 确定性布局（开图后）
shots/stable3_run1..3.png        3 次独立启动，PNG 字节一致（T-stable-3 直接证据）
shots/04_graph3d_seeded.png      3D 确定性布局
```

---

## 3. 机检（`tests/test_kgviz_layout_seed.py`，5 条）

用 Node VM 加载真实生产 JS（`graph-engine.js` + `graph-bh-tree.js` + `graph-layout-sim-core.js` + 两个 layout），
对 60 节点合成图调用真实 `loadFromEngine()`：

| 测试 | 内容 |
|---|---|
| `test_t_stable_1_same_seed_twice_is_byte_identical_2d_and_3d` | 2D/3D 同种子两次初始化坐标**字符串全等**；恢复默认种子后仍一致 |
| `test_t_stable_2_different_seed_changes_layout` | 2D/3D 换种子后 ≥90% 节点坐标改变（实测 134/134 真机；合成 60/60） |
| **`test_t_stable_1_red_fixture_nondeterministic_rng_is_detected`** | **必红 fixture**：把 RNG 覆盖回宿主 `Math.random` ⇒ 连续两次初始化坐标**必须不同**（证明 T-stable-1 有判别力） |
| `test_t_stable_5_both_layout_modules_have_injected_seed` | 两模块都有 `DEFAULT_LAYOUT_SEED/makeLayoutRng/setSeed/getSeed`，且无 `Math.random` 调用 |
| `test_engine_exposes_seeded_rng_and_default_seed` | mulberry32 同种子同序列/异种子异序列；engine `setLayoutSeed` 生效 |

---

## 4. 诚实局限（登记，不掩盖）

| # | 项 | 说明 |
|---|---|---|
| L1 | **自然运行后的微小漂移** | 力导向在 `start()` 后仍按帧预算持续 tick（原设计不改迭代/参数），帧数受运行时影响；因此"打开后等 N 秒再截图"可能有**亚像素级**差异。本任务用「reset 后 warmup 位置」作为最严格比较口径（T-stable-1/3），并实测冻结态字节一致。**未改**任何收敛参数来强行冻结。 |
| L2 | **worker warmup 一致性** | 134 节点走 worker（`>=60`）；worker 与主线程用同一 `graph-layout-sim-core`（本身已无 `Math.random`）；实测 3 次启动一致。不同机器/浏览器的浮点结果原则上应一致（IEEE754），但未做跨机器实测 ⇒ U-KGV-8。 |
| L3 | **种子来源固定常量** | v0 默认固定种子（任务允许"默认值固定，v0 不强求 UI"）。不同语料因节点/边不同天然得到不同布局；若将来要"按语料派生种子"，`hashStringToSeed` 已预留。 |
| L4 | **新节点锚点生长未实现** | 见 §1.3 / U-KGV-7；需要增量加载改造，不在 v0。 |
| L5 | **3D 端到端截图** | 3D 状态机截图已给（`04_graph3d_seeded.png`）；T-stable-3 的"截图字节一致"用 2D 验证（同一 seed 机制为两模块共享实现）。 |

---

## 5. 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q`（基线 1535） | **1540 passed / 0 failed**（+5 新测，含必红 fixture） |
| `node --check` 全部前端 js | **0 fail** |
| `i18n_selftest.js` | **PASS，exit 0** |
| `scripts/agent/team_audit.py` | **FAIL=0** |
| 12 交互剧本 | **12/12，failed=0**（26.3s，`scripts/benchmark/surface/results/raw-interaction-t176-final_f43c4478.json`） |

---

## 6. 改动文件

```
src/memoria/ui/static/app/js/graph-engine.js    +47   （MemoriaGraphSeed + engine layoutSeed）
src/memoria/ui/static/app/js/graph-layout-2d.js +81/-36（注入种子 / setSeed / 全随机源替换）
src/memoria/ui/static/app/js/graph-layout-3d.js +83/-36（同上，3D）
tests/test_kgviz_layout_seed.py                 新增 171 行（5 条机检，含必红 fixture）
artifacts/agent/verify/todo/kgviz-layout-seed/  报告/JSON/截图/verify_seed.py
```
`git diff --stat`：3 files changed，+175/−36（不含新增测试）。

## 7. 复跑

```powershell
# 机检（含必红 fixture）
.venv\Scripts\python.exe -m pytest tests/test_kgviz_layout_seed.py -q

# 真机（启动/结束自己的 app 实例，不动用户进程；需 WebView2）
.venv\Scripts\python.exe artifacts/agent/verify/todo/kgviz-layout-seed/verify_seed.py
```
产物：`verify_seed.json`、`t-stable` 读数、`shots/`。

## 8. 登记未知（U-KGV）

```
U-KGV-7  新节点锚点生长的增量加载改造（v1；需先做节点 diff/位置保留，成本 >1 天）
U-KGV-8  跨机器/浏览器浮点确定性（当前同机 3 次启动字节一致；跨机器未测）
U-KGV-9  自然运行 N 秒后的亚像素漂移是否会被用户感知（当前用 warmup 冻结口径验收）
```
