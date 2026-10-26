# task-177 — 标签 LOD/避让（D-KGV-06）

> **基线**：HEAD `48547803`（开工时）；本任务只改 3 个前端文件 + 1 个新测试 + artifacts，未 commit。
> **设计依据（只读）**：`docs/design/kg-visualization-v0.md §3`（可读性前置成立；性能前置已撤回）、§8（T-label）；`PHASE4-RULINGS.md D-KGV-06`。
> **纪律**：未改 `docs/**`、`docs/example/**`、`Package/**`、`services/**`、layout 模块；**目标理由是可读性，不是性能**（未把性能收益写成设计依据）。

---

## 0. 一句话结论

**134 个标签无条件全画的问题已解决**：
- 2D：标签改为**屏幕空间**绘制（不再随缩放缩到 1px），按 **度数高 > 度数低** 优先级 + **包围盒碰撞检测** 决定可见集合；默认 54–55 个可见、**两两包围盒重叠 0（100% 不相交）**；hover 被隐藏标签**必然出现**；放大后可见数 54→79（稀疏后重新出现）。
- 3D：标签 LOD（默认 topN=10 可见；相机拉近 <900 或 `labelLod:false` 时全显；hover/焦点必显）。
- **先证红**：关闭避让（`labelLod:false`）⇒ 134 个标签全画 ⇒ 默认密度下**两两重叠 321 对**（`disjointRatio=96.4%`），机检必红 fixture 检出；开启后 0 对。

| 验收 | 结果 |
|---|---|
| **T-label-1** 标签包围盒两两不相交比例 = 100%（机检，非肉眼） | ✅ 真机 `drawnLabels=54, overlapPairs=0, disjointRatio=1.0`；`_labelLodStats.overlap=0` |
| **T-label-2** 度数最高 N 个节点标签必然可见 | ✅ N=10：`perilous / concessive-inversion / missed-train-plan-change / heritage / rewarding / good-news-flight-transfer / assimilation / troubled / flail / mainstream` 全部可见 |
| **T-label-3** 密度下降后隐藏标签重新出现 | ✅ 2D 滚轮放大：可见 54 → 79（k 0.138→0.202）；3D 相机 1839→644：可见 10 → 134 |
| **T-label-4** 真人可读率 ≥80%（可选） | ⏸ 未做（需真人）⇒ 登记 U-KGV-11 |
| **T-label-5** 关闭避让可回退 | ✅ `labelLod:false` ⇒ 134 全部显示（可回退），恢复后回到 LOD |
| **先证红**（改前两两重叠比例 >0） | ✅ 真机红态 134 标签 / **321 对重叠**；单测必红 fixture（`lod:false`）同样红 |
| hover 被隐藏标签必须出现 | ✅ 2D 被隐藏 `utilitarian` hover 后可见（截图 02）；3D `a-real-head-scratcher` hover 后 `labelVisible=true` |
| 不许破坏（点击/跳转/2D/3D/大小/种子） | ✅ 点击路径未改；pytest 1547 全绿、12 剧本 12/12 |

---

## 1. 实现

### 1.1 标签布局纯函数（`graph-label.js`，可机检）

```
layoutNodeLabels(items, options)
  items: [{id, text, x, y, r, degree}]           // x/y 为屏幕坐标（2D 传入经过 transform 的坐标）
  options: {fontSize=10, labelHeight=12, padX/padY, gap=1, topN=10,
            hoverIds, lod, measureText}
顺序：
  1) hover 标签最高优先（被隐藏也必须出现）
  2) 度数 topN 必然可见
  3) 其余按 degree 降序做碰撞检测：每个标签尝试 12 个候选锚位
     （下/上/左/右/斜向/更远 lane），取第一个与已放置盒不重叠的位置；找不到则隐藏
返回：{visibleIds, boxes, hiddenIds, topIds, overlapCount, visibleCount, allCount, lod}
```
- `boxesOverlap(a,b,gap)`：严格包围盒判定（供 T-label-1 机检复用）；
- 关闭 LOD（`lod:false`）时全部强制显示（回退 / 必红 fixture）；
- 渲染层传入真实 `ctx.measureText` 宽度（缓存同一文本），与画布实际文本一致。

### 1.2 2D 渲染（`graph-view-2d.js`）

- 标签从"世界坐标 per-node 绘制"改为 **`ctx.restore()` 之后的屏幕空间绘制**：
  位置 = `node.x * k + transform.x`（y 同理），字体固定 10px ⇒ 不再随缩放变 1px，也不随缩放漂移；
- 每次 draw 计算一次可见集合（O(N log N + N×候选)），存 `this._visibleLabelIds / _labelBoxes / _labelLodStats`（机检可直接读）；
- hover/focus 标签强制可见；`opts.labelLod === false` 可回退到全画；
- 点击/拖拽/命中的代码路径**未改**（只改标签绘制）。

### 1.3 3D 渲染（`graph-view-3d.js`）

- 3D 标签是 sprite（世界坐标锚定，重排会破坏锚点），v0 采用**优先级 LOD**而不是包围盒避让：
  · 默认只显示度数 topN=10 + hover/extFocus；
  · 相机距离 < 900（拉近）或 `labelLod:false` ⇒ 全部显示；
  · 每帧只在相机距离变化 >40 时重算一次（不是逐帧全量重算）；
- `_labelLodStats / _labelLodVisibleIds` 暴露给机检。

---

## 2. 真机验证（`verify_label.json` + 5 张截图）

环境/语料：pywebview/WebView2，HEAD `48547803`，语料 = 工作区 `docs/example/AAA_Vocab` 现场副本（**134 节点 / 404 边**，与设计 §7 一致）。
**T-label-1 机检口径**：拦截画布真实 `fillText`，用与渲染相同的 `10px system-ui, sans-serif` 经 `measureText` 构造屏幕包围盒（x−w/2, y−6, w, 12），两两判定相交。

### 2.1 默认（最密）视图
```
drawnLabels=54   overlapPairs=0   disjointRatio=1.0
_labelLodStats={visible:54, hidden:80, overlap:0, lod:true}
topVisible=true（topN=10）
```
### 2.2 必红 fixture（同一默认缩放，关闭避让）
```
labelLod=false ⇒ drawnLabels=134   overlapPairs=321   disjointRatio=96.4%   detectedAsOverlapping=true
恢复 labelLod=true ⇒ 回到 54 可见
```
截图 04 可见文字明显互相覆盖、糊成一片（与 01 形成对照）。

### 2.3 缩放稀疏后重新出现（T-label-3）
```
滚轮放大前 k=0.138258, visible=54
滚轮放大后 k=0.202424, visible=79   moreLabels=true
```

### 2.4 hover 被隐藏标签
```
hiddenId=utilitarian ⇒ 鼠标移入该节点 ⇒ appeared=true（截图 02）
```

### 2.5 3D
```
默认：labelSprites=134  visible=10  hidden=124  showAll=false  camDist=1839.5  topNVisible=true
hover 被隐藏的 a-real-head-scratcher ⇒ labelVisible=true
相机拉近到 643.8 ⇒ showAll=true, visible=134, hidden=0
```

### 2.6 截图
```
shots/01_label_lod.png              默认 LOD：可见标签互不重叠（对照 04）
shots/02_hover_hidden_label.png     hover 被隐藏标签「utilit…」出现并高亮
shots/03_zoom_more_labels.png       放大后更多标签出现（54→79）
shots/04_red_all_labels.png         必红态：关闭避让后 134 标签重叠糊成一片（321 对）
shots/05_graph3d_label_lod.png      3D 标签 LOD
```

---

## 3. 机检（`tests/test_kgviz_label_lod.py`，7 条）

Node VM 加载真实 `graph-label.js`，对 134 个密集合成标签（18×16px 网格）调用 **生产函数** `layoutNodeLabels`：

| 测试 | 内容 |
|---|---|
| `test_t_label_1_no_pairwise_bbox_overlap_at_100pct` | LOD 后两两包围盒重叠 = 0；可见 >0 |
| `test_t_label_1_red_fixture_all_labels_overlap` | **必红 fixture**：`lod:false` ⇒ 全部可见且重叠 >0（有判别力） |
| `test_t_label_2_highest_degree_topn_always_visible` | topN=10 全部可见 |
| `test_t_label_3_zoom_in_reveals_more_labels` | 屏幕坐标 ×1.8（稀疏化）⇒ 可见数增加 |
| `test_hovered_hidden_label_can_appear` | 被隐藏 id 作为 `hoverIds` 后可见（信息不丢） |
| `test_t_label_5_toggle_off_reverts_to_all_labels` | `lod:false` 时 visible == all |
| `test_2d_view_uses_label_lod_and_exposes_machine_state` | 2D 接入 `layoutNodeLabels`、暴露 `_visibleLabelIds/_labelBoxes/_labelLodStats`，且标签绘制在 `ctx.restore()` 之后（屏幕空间） |

---

## 4. 门禁

| 门禁 | 结果 |
|---|---|
| `pytest -q`（基线 1540） | **1547 passed / 0 failed**（+7 新测，含必红 fixture） |
| `node --check` 全部前端 js | **0 fail** |
| `i18n_selftest.js` | **PASS，exit 0** |
| `scripts/agent/team_audit.py` | **FAIL=0** |
| 12 交互剧本 | **12/12，failed=0**（27.2s，`scripts/benchmark/surface/results/raw-interaction-t177-final_48547803.json`） |

---

## 5. 改动文件

```
src/memoria/ui/static/app/js/graph-label.js   +162  （label LOD 纯函数 + 包围盒判定）
src/memoria/ui/static/app/js/graph-view-2d.js +87   （屏幕空间标签绘制 + 可见集合/机检状态）
src/memoria/ui/static/app/js/graph-view-3d.js +42   （3D sprite 标签优先级 LOD）
tests/test_kgviz_label_lod.py                 新增 117 行（7 条机检，含必红 fixture）
artifacts/agent/verify/todo/kgviz-label-lod/  报告/JSON/5 截图/verify_label.py
```
`git diff --stat`：3 files changed，+290/−1（不含新增测试）。

## 6. 复跑

```powershell
.venv\Scripts\python.exe -m pytest tests/test_kgviz_label_lod.py -q
.venv\Scripts\python.exe artifacts/agent/verify/todo/kgviz-label-lod/verify_label.py
```
产物：`verify_label.json`、`shots/`。

## 7. 诚实局限 / 登记未知

| # | 项 | 说明 |
|---|---|---|
| U-KGV-11 | **T-label-4 真人可读率（≥80%）未做** | 需真人判读，v0 可选项；已登记（非静默跳过） |
| L1 | **3D 标签用优先级裁剪，不是包围盒避让** | 3D 标签是 sprite、世界坐标锚定；重排会破坏锚点。T-label-1 的机检口径是 2D 屏幕空间；3D 用"topN + 拉近全显 + hover 必显"满足可读性/密度要求。若要求 3D 也无重叠，需要 CSS2D/屏幕空间标签层，属 v1 |
| L2 | **topN 固定 10** | 无 UI 设置项（v0 不需要）；`labelTopN` 作为 opts 可传。 |
| L3 | **标签宽度依赖系统字体** | 用画布 `measureText` 实测，与渲染一致；不同字体（system-ui 解析差异）会改变可容纳标签数（但机检每次用同一字体口径）。 |
| L4 | **隐藏标签没有任何"可发现性"提示** | hover 会显示，但用户不知道哪些被隐藏；设计未要求（可 v1 加"缩放查看更多"提示）。 |
| L5 | **标签不响应点击** | 原实现标签也不可点击（点击走节点命中），未改交互语义。 |
