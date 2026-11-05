# S3-ADDENDUM-3：新 2D 图谱视觉与旧 KGviz 对齐（人裁）

> **来源（人原话，2026-11-05）**：「图谱的元素样式 风格请保持 和旧的一样」
> **性质**：视觉值修订，不改 S3 的语义/结构契约（kind/edge type/presence/白名单不变）。
> **范围**：仅 `graph-multilevel` 2D Renderer 的**元素外观**；3D、旧 KGviz 不动。

## A3-1 视觉基线 = 0.4.10 旧 KGviz 2D

新 Renderer 的节点/边/标签/背景必须使用旧 KGviz 的视觉值（来源 `graph-theme.js`、`graph-view-2d.js`、`graph-engine.js`、`graph-label.js`）：

| 元素 | 旧值（必须一致） |
|---|---|
| 画布背景 | `#0a0d13`；容器 `#161b22` |
| KP 节点半径 | 连续分位映射 `radiusForDegree(degree, distinctSorted, baseRadius=6)` ≈ 4.5–9.9px；hover +3px、target +2px；不得回退为固定 8px |
| 节点色 | 有 degree 统计时 galaxy 渐变 `rgb(139,148,158)` → `rgb(240,246,252)`；无统计时 `#c9d1d9` |
| hover / target / dim / invalid | `#f0f6fc` / `#79c0ff` / `#3d4350` / `#3a4152` |
| 光晕/星形 | 旧 galaxy 的 star + halo（半径/亮度按 degree ratio），颜色同旧 |
| 标签 | `10px system-ui, sans-serif`；填充 `#adbac7`（invalid `#6e7681`）；halo `rgba(13,17,23,0.92)`、lineWidth 3 |
| 边色 | `contain #3fb950` / `reference #58a6ff` / `extend #d29922`；旧线宽/透明度 |
| 边类型 additive | `semantic #e06c75`（旧 KGviz 无此类型，作为唯一新增色，保持旧调性） |
| 新 chrome | 图例/工具栏/“Beta”徽标必须**降级为旧视图的提示条风格**（10px、muted、半透明、无大卡片）；功能保留，不抢视觉 |

## A3-2 不做

- 不改 S3 的节点/边**语义字段**、白名单、presence、`data_edge_ids` 禁读；
- 不改旧 KGviz/3D；
- 不引入新图形库；不为了“像旧”而伪造 degree/节点类型。

## A3-3 验收

- 同库同数据下，新旧视图节点色/半径/标签/边色可对照（截图 + 样式常量断言）；
- degree 越大半径越大（连续、非分桶）；hover/target 加成正确；
- `node --check`、`i18n_selftest`、12/12 交互、`pytest tests/graph` 全绿；
- 旧 KGviz 切换仍完整。

## A3-4 变更控制

用户再次要求调整视觉时，修订本 ADDENDUM；不得静默改 S3 正文或旧 KGviz。
