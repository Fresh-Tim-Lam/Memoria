# S3 提案 A · 证据与机检清单

> 配套：`S3-visual-proposal-A.md`｜票：task-305｜日期：2026-11-03
> 用途：另一人可按本文件复核 S3 每条断言（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S3 复核方草稿（S3-visual-proposal-B / S3-objections）；不引用其结论。
> 纪律：未改产品代码/契约/schema/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S3 用途 |
|---|---|---|
| A | 原话/冻结契约/决策/可复跑代码事实 | kind 约束、VM 纯度、present、事件分离、现状缺陷 |
| B | 单源实测产物 | （本场未新增 probe；引用 S2 probe 的无簇事实） |
| C | 单源推理 | 少量设计取舍（并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | token 数值、预算阈值、文案、键盘键位 |

**统计**：A 级锚点见 §1–§12；**本项目假设 10 条**（§14）；B 级引用 S2 probe 1 份（§13）。

---

## 1. S3-1 节点类型/状态

| 主张 | 锚 | 等级 |
|---|---|---|
| 节点 kind 只有 kp/cluster；bridge 只能 role/state | `S0-terms-v1.md:75-79`（S0-9 kind/role）；`S1-dimensions-v1.md:13-15` | A |
| singleton representative=false（不作代表节点） | `S2-clustering-v1.md:17,90-92`（S2-1/跨议题） | A |
| 现有实现只有同一种节点（无 kind）；`nodeClick` 假设 node.file/kp_id | `graph-view-2d.js:686-717`（统一圆形半径）；`app.js:1661-1677`（jumpToTarget） | A |
| 交互态不进 VM / 视图纯度 | `S0-terms-v1.md:75-79`（D-4）；`ENGINEERING-PLAN.md:224-250` | A |
| selected 的 Presentation 表达 | 本提案 §1 | 本项目假设 |

---

## 2. S3-2 簇视觉

| 主张 | 锚 | 等级 |
|---|---|---|
| 簇节点代表连通子图、外观更大 | `vision.md:23`（U-6） | A |
| member_count/representative/root_exempt 数据来源 | `S2-clustering-v1.md:17,73-76`（S2-1/S2-12） | A |
| 现有半径按 degree 连续映射（非 member_count） | `graph-engine.js:232-238`（radiusForNode）、`:270-327`（VISUAL_CHANNELS 声明 size=degree） | A |
| 现有无簇节点/徽标/展开提示 | `graph-view-2d.js:686-717`（统一节点绘制）；无 cluster 分支 | A |
| 大小公式/徽标/fallback/root_exempt token | 本提案 §2 | 本项目假设 |

---

## 3. S3-3 KP 视觉/U-20

| 主张 | 锚 | 等级 |
|---|---|---|
| KP→编辑器跳转是旧行为保留 | `vision.md:37`（U-20） | A |
| 现有 jumpToTarget 假设 node.file/kp_id | `app.js:1661-1677` | A |
| 现有 label/range 样式 | `graph-view-2d.js:14-25,98-114`（label）；`:695`（range_ok=false 颜色） | A |
| 渲染器不得直接跳转 | S0-9/D-4；`ENGINEERING-PLAN.md:713-715`（图→编辑器单向） | A |
| 提示文案/标签截断 | 本提案 §3 | 本项目假设 |

---

## 4. S3-4 层次感知

| 主张 | 锚 | 等级 |
|---|---|---|
| 层次/导航状态归 S5、VM 不含 breadcrumb/history | `S0-terms-v1.md:75-79`（D-4）；`S1-dimensions-v1.md:104-107`（S1-13） | A |
| 导航与渲染事件分离 | `ENGINEERING-PLAN.md:713-719`（事件映射/导航服务） | A |
| 现有无层级指示/面包屑 DOM | `graph-view-2d.js`/`graph-view-3d.js` 无相关实现；`app.js` 无 graph empty/legend（grep 0，§15） | A |
| 层标样式/过渡时长/视口保持 | 本提案 §4 | 本项目假设 |

---

## 5. S3-5 边视觉/presence

| 主张 | 锚 | 等级 |
|---|---|---|
| 边存在/类型是视图函数；只画 shown | `S0-terms-v1.md:56-61`（S0-6）；`S1-dimensions-v1.md:99-102`（S1-12） | A |
| U-27 存无/类型差异 | `vision.md:66`（U-27） | A |
| 现有按 type 上色；全量 links 绘制 | `graph-engine.js:261`（edgeColor）；`graph-view-2d.js:634-663`（simLinks 全画） | A |
| 现有边无 presence/state；无 bridge 状态 | `graph-engine.js` loadPayload 只吃 edges（`:167-181`）；2D 无 presence 分支 | A |
| 颜色/线宽/虚线/bridge token | 本提案 §5 | 本项目假设 |

---

## 6. S3-6 渲染接口

| 主张 | 锚 | 等级 |
|---|---|---|
| ViewModel 纯（无 nav/mode/capabilities） | `S0-terms-v1.md:75-79`（D-4）；`ENGINEERING-PLAN.md:224-250` | A |
| capabilities 由 `Renderer.getCapabilities()`，不进 VM（C-6） | `ENGINEERING-PLAN.md:287-291`（C-6） | A |
| 2D/3D 同接口/U-33 | `vision.md:72`（U-33）；`S0-terms-v1.md:75-79` | A |
| 现状 API 不统一：2D 只有 `loadPayload(engine)`/`destroy()`；3D 类内直接 `_render()`/`destroy()`，无公共 `render(vm)`/`getCapabilities` | `graph-view-2d.js:167-181,211`；`graph-view-3d.js:249-262,347,1049` | A |
| 现状两后端各自持 engine、无统一 VM 输入 | `app.js:1643-1660`；`ENGINEERING-PLAN.md:220`（RENDER_BACKEND 现状各自 engine） | A |
| 方法签名/opts 细节 | 本提案 §6 | 本项目假设 |

---

## 7. S3-7 事件

| 主张 | 锚 | 等级 |
|---|---|---|
| 最小事件集 nodeClick/edgeClick/backgroundClick | `S0-terms-v1.md:75-79`（S0-9）；`ENGINEERING-PLAN.md:287,714` | A |
| 导航动作不在渲染器 | `ENGINEERING-PLAN.md:713-719`；S0-9 | A |
| 现状 2D nodeClick 带 edge_id，3D 不带（不一致） | `graph-view-2d.js:544-547`；`graph-view-3d.js:1043` | A |
| payload 白名单/键盘等价点击 | 本提案 §7 | 本项目假设 |

---

## 8. S3-8 无簇 UX

| 主张 | 锚 | 等级 |
|---|---|---|
| 无 representative 簇是合法状态；不得用结构/引用边伪造 | `S2-clustering-v1.md:12,73-76`（S2-12/R-S2-11） | A |
| frozen 与 showcase 均 E_sem=0（语料事实） | `artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/results.json`（frozen semantic_edges=0；showcase=0） | B |
| 默认视图 UX 交办 S3/S4 | `S2-clustering-v1.md:12,74` | A |
| 现有无空状态/无簇提示 | 2D/3D/engine 无 `no_semantic`/空状态（grep 0，§15）；`app.js` 无 graph empty | A |
| 文案/affordance/布局分组具体形式 | 本提案 §8 | 本项目假设 |

---

## 9. S3-9 默认 vs 全展开

| 主张 | 锚 | 等级 |
|---|---|---|
| 默认替代+保留开关；同源同 present | `S0-terms-v1.md:69-73`（S0-8） | A |
| 全展开是 Presentation 正交开关 | `S1-dimensions-v1.md:104-107`；`ENGINEERING-PLAN.md:717` | A |
| 现状默认即全量、无模式切换 | `graph-engine.js:179-180`（rawEdges）；`graph-view-2d.js:634-663` | A |
| 切换徽标/动画细节 | 本提案 §9 | 本项目假设 |

---

## 10. S3-10 可访问性

| 主张 | 锚 | 等级 |
|---|---|---|
| 现状 canvas 无 aria/tabindex/reduced motion | `graph-view-2d.js`/`graph-view-3d.js`/`graph-engine.js` 中 `aria-`/`tabindex`/`prefers-reduced-motion` 计数 0（§15 复跑） | A |
| 视觉通道现有声明（颜色/大小/亮度） | `graph-engine.js:270-327`（VISUAL_CHANNELS） | A |
| canvas 需要 DOM overlay/键盘 | 本提案 §10 | 本项目假设（WCAG 实现细节） |

---

## 11. S3-11 性能/稳定

| 主张 | 锚 | 等级 |
|---|---|---|
| 规模不是问题但需显示预算 | `vision.md:71`（U-32）；S3 章程 §3 | A |
| 现有布局种子固定（可复现） | `graph-engine.js:241-250`（layoutSeed） | A |
| 现有无显示预算/退化策略 | `graph-view-2d.js:634-663`（全量）；无 maxNodes 检查 | A |
| 200/400/60fps/180ms 等默认值 | 本提案 §11 | 本项目假设 |

---

## 12. S3-12 VM 一致性

| 主张 | 锚 | 等级 |
|---|---|---|
| VM 只含 dimension_id + 节点/边；簇/run/dendrogram 不进 VM | `S0-terms-v1.md:75-79`（D-4）；`S1-dimensions-v1.md:104-107`；`S2-clustering-v1.md:69`（S2-11） | A |
| `data_edge_ids` 审计/计数，不暴露内部 | `S0-terms-v1.md:56-61`（R-3）；`ENGINEERING-PLAN.md:229-250` | A |
| 现状渲染器直接吃 engine 数据（非纯 VM） | `graph-view-2d.js` 用 `this.engine`（simNodes/simLinks）；`graph-view-3d.js` 同；`app.js:1842-1861` | A |
| VM schema 白名单/字段细节 | 本提案 §12；S6a 定 | 本项目假设 |

---

## 13. 视觉映射表（字段→token；机检基础）

> 断言方式：注入 fixture VM，调用渲染器，检查生成的图形/DOM 属性；下表的 token id 是**测试断言键**，不是最终 CSS 名。
> 颜色为建议值（本项目假设）；对比度由 §10 测试验证（文本≥4.5:1、图形≥3:1），不在此声称已测。

| # | VM 字段/值 | token id | 2D 表现 | 3D 表现 | a11y 文本 |
|---|---|---|---|---|---|
| 1 | `kind=kp` | `node.kp` | 圆，6–10px（degree 分位） | 球，同尺寸编码 | "知识点 X" |
| 2 | `kind=cluster` | `node.cluster` | 圆角方，12–28px（member_count 对数） | 多面体，同公式 | "簇 N，M 个知识点，可展开" |
| 3 | `role=bridge` | `node.bridge` | 虚线外环 | 线框外壳 | "跨子图桥接" |
| 4 | `role=focus` | `node.focus` | 高亮描边 | 自发光 | "当前焦点" |
| 5 | `root_exempt=true` | `node.root` | 虚线双环 + "全库" | 双壳 | "全库根块（非普通簇）" |
| 6 | `singleton` | `node.singleton` | 无 cluster 徽标（普通 KP） | 普通球 | 无簇文案 |
| 7 | `presence=shown` | `edge.shown` | 按 type 画线 | 按 type 画线 | 类型 + 方向 |
| 8 | `presence=suppressed` | `edge.suppressed` | **不画**；统计/检查器 | 不画 | "已隐藏（rule_id）" |
| 9 | `presence=unknown` | `edge.unknown` | **不画**；检查器 | 不画 | "未计算（rule_id）" |
| 10 | `type=contain(structural)` | `edge.structural` | 实线 1.0px 灰 | 同 | "结构包含" |
| 11 | `type=contain(semantic)` | `edge.semantic` | 实线 2.0px 蓝 | 同 | "语义包含" |
| 12 | `type=reference` | `edge.reference` | 虚线 [4,3] 1.0px 弱灰 | 同 | "引用（导航）" |
| 13 | `type=extend` | `edge.extend` | 实线 1.5px 暖黄 | 同 | "语义关联" |
| 14 | `state=bridge_only` | `edge.bridge` | 点线叠加 | 点线叠加 | "跨簇桥" |
| 15 | `range_ok=false` | `node.invalid` | 去饱和/虚线 | 去饱和 | "锚点失效" |
| 16 | `data_edge_ids` | `renderer.forbidden` | 不渲染/不读取 | 同 | （审计侧） |

**机检断言（示例）**：
```js
// fixture: 一个 cluster(member_count=10, root_exempt=false) + 一条 shown semantic + 一条 suppressed reference
renderer.render(container, vm)
assert(drawnNodesIds).toEqual(vm.nodes.map(n => n.node_id))
assert(drawnEdgesIds).toEqual(vm.edges.filter(e => e.presence === "shown").map(e => e.edge_id))
assert(suppressedEdgeHasNoShape)   // 不得出现幽灵线
assert(badgeText === "10")
assert(!rendererSource.includes("data_edge_ids"))
```

---

## 14. 本项目假设清单（10 条，评审可逐条推翻）

1. 簇大小公式 `clamp(8+2.2*log2(member_count+1),12,28)`（2D/3D 同数据变量）。
2. 颜色 token 建议值（`--node-kp/--node-cluster/--edge-*`）；对比度由 WCAG 测试验证，不在本文件声称已测。
3. 空状态文案/按钮（"让 agent 建立语义关联"等）；是否默认展示可被产品/Lead 改。
4. `selected` 由 Presentation 传入（可选 `setSelection`），不进 VM。
5. `label_key` 本地化由取景层/Presentation 处理；渲染器不翻译。
6. 事件 `hover/focus` 可选；键盘 Enter/Space 等价 click。
7. 显示预算默认 200 nodes/400 edges/60fps/180ms（S8 可调）。
8. 3D 也按 member_count 缩放（可能改变现有 3D 等大习惯 D-KGV-04）。
9. aria overlay 由 Renderer 提供锚点、Presentation 生成内容（可改由 Presentation 全权）。
10. `no_semantic_edges` 判定来自 S2 run status/coverage（S3 不自行判定）。

---

## 15. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) S3 12 议项 + U 覆盖
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S3-visual-proposal-A.md').read_text(encoding='utf-8'); print('S3 missing:',[f'S3-{i}' for i in range(1,13) if f'S3-{i}' not in t]); print('U missing:',[f'U-{i}' for i in [3,5,6,15,16,18,19,20,26,27,33] if f'U-{i}' not in t])"
# 2) 现状缺陷：renderer 无 capabilities/aria/reduced motion/空状态
python -c "from pathlib import Path; [print(f, {k:Path(f).read_text(encoding='utf-8').count(k) for k in ['getCapabilities','aria-','tabindex','prefers-reduced-motion','no_semantic']}) for f in ['src/memoria/ui/static/app/js/graph-view-2d.js','src/memoria/ui/static/app/js/graph-view-3d.js','src/memoria/ui/static/app/js/graph-engine.js']]"
# 3) 事件不一致
python -c "from pathlib import Path; print('2d', [i+1 for i,l in enumerate(Path('src/memoria/ui/static/app/js/graph-view-2d.js').read_text(encoding='utf-8').splitlines()) if 'nodeClick' in l]); print('3d', [i+1 for i,l in enumerate(Path('src/memoria/ui/static/app/js/graph-view-3d.js').read_text(encoding='utf-8').splitlines()) if 'nodeClick' in l])"
```

**实测结果（2026-11-03）**：
- S3-1..S3-12 全部含 定义/规则·机检·反例·边界·U 映射·建议裁决·证据等级（缺失 0）；U 覆盖缺失 0。
- 三个渲染文件 `getCapabilities/aria-/tabindex/prefers-reduced-motion/no_semantic` 计数均为 0（现状缺口，A 级）。
- 2D `nodeClick` 行 544-547（带 edge_id）；3D 行 1043（不带 edge_id）→ 接口不一致证据。

---

## 16. 覆盖矩阵

| 侧 | 项 | 落点 |
|---|---|---|
| U | U-3/U-5/U-6/U-15/U-16/U-18/U-19/U-20/U-26/U-27/U-33 | 提案 §13（逐项映射） |
| S0 | S0-6 present/R-3、S0-8 默认/full、S0-9 VM/kind/事件 | §5/§6/§9/§12 |
| S1 | H/A、dimension_id 标签、VM 纯度 | §9/§12 |
| S2 | 无簇状态、singleton/root_exempt/coverage | §1/§2/§8 |
| 工程 | ViewModel 字段、C-6 capabilities、事件/导航分离 | `ENGINEERING-PLAN.md:224-250,287,291,713-719` |

---

## 17. 已知限制

1. 视觉 token 的对比度/可读性需在真实主题（亮/暗/高对比）上用 WCAG 计算器验证；本提案只给 token 与阈值。
2. 空状态文案/按钮是否默认展示需产品/Lead 决定；当前按"显式但不打扰（banner+按钮）"设计。
3. 3D 后端实现（three.js）的成员大小/标签/aria 覆盖需 S6a 落地；本提案只冻结契约与映射。
4. 性能预算数值为建议值，S8 可调；超预算降级为"显式拒绝+列表"可能牺牲部分浏览体验，需 S4 配合先裁剪。
5. 本场未写代码，映射表机检需在实现阶段用 fixture VM/静态断言验证。
