# 正交避障连线路由：开放实现取证 + XERJ 查询结论（给 task-249）

> 本票只做取证与方案推荐，**不写实现代码、不引依赖、不改仓库其余文件、不打包**。
> 取证日：2026-10-30（Asia/Shanghai）。作者：index-evidence-oss（task-250）。
> 证据等级沿用本队口径：**【实】**=可由 URL/路径/命令直接复核；**【推】**=由材料推出；**【待测】**=需实验/原型。
> 适用范围：task-249 panel-graph 的 `engine/` 纯函数引擎（`layout()` + `route()`），26 节点 / 30 边、`layout()<16ms`、`composeFrame() p95<4ms`（[ENGINE-ACCEPTANCE.md](ENGINE-ACCEPTANCE.md) L174、L330；[GRAPH-ENGINE.md](GRAPH-ENGINE.md) L309）。
>
> **勘误记录（2026-10-30，task-250 勘误）**：`portStub` 6→**12 px**（依据 [GRAPH-ENGINE.md](GRAPH-ENGINE.md) §11.7 / A11-2 `MIN_STUB=12`；旧值按 A11-2 必红）。同轮对齐现行规范常量：`cell` 8→**4**（§11.7 `ASTAR_STEP=4`，8 为允许备选）、`clearance` 8→**10**（§11.7 `PARALLEL_CLEARANCE=10`）、`bendCost` 12→**4**（§11.7 规则 5 `cost=长度+4×转向次数`）、`crossCost` 4→**0**（规范 A* 代价未含交叉项；交叉合法性由 §12.1/A12 判）、`overlapCost` 保留 **∞**（§12.1/A12-3 共线重叠=违规）；新增 `MIN_LINE_GAP=8`、`MIN_CROSS_ANGLE=15`（§12.1/A12-1/A12-3）；`maxBends=6` 对齐 [FEASIBILITY-REVIEW.md](FEASIBILITY-REVIEW.md) C5；`maxTracks=4`、`maxExpansions=20000` 为本文实现护栏（规范未给数值）。旧版 sha256 `ce328707…`，新版以提交为准。

---

## 0. 结论摘要（先给 task-249 的 5 条硬结论）

1. **"不重叠"不是 A* 能单独保证的**：A* 只找一条路；成熟实现都靠**后处理**——libavoid 的 **nudge**（把重叠/贴近平行段推移到不同通道，`idealNudgingDistance=4`，10 次递减尝试）【实】；ELK 的 **slot 分配 + 冲突依赖图**（conflict/critical conflict → 不同 routing slot；critical 环则拆 segment）【实】；VLSI 的 **track assignment**（先分轨再细节布线）【实】。A* / 可见性图只是"找路"。
2. **"允许交叉"是代价函数 + 渲染两层的事**：libavoid 用 `crossingPenalty`/`clusterCrossingPenalty` **软惩罚**（默认 0，即允许）【实】；ELK 用 `CROSSING_PENALTY=16`、`conflict=1` 的软代价【实】；GoJS 用 `Curve.JumpOver/JumpGap` 把正交交叉渲染成**桥/断口**（这正是甲方要的"桥接样式"）【实】。
3. **最贴合我们场景的是"网格 A* + 占用表 + 轨道 nudge + 桥接后处理"的混合方案**，而不是移植 libavoid（LGPL、C++、~500KB）或 ELK（EPL、Java/elkjs ~1.3–1.7MB）【实+推】。X6 的 manhattan 路由给了纯 TS 的 A* 骨架（MIT，~16KB 相关源码），但它**只避节点、不避边**，必须补占用表/nudge/bridge【实】。
4. **XERJ 不是"路由知识库"，而是本地搜索服务**（Apache-2.0 Rust 单二进制，ES 兼容 API，官方用例就是"clone 开源仓 → `xerj autoindex` → 检索"）【实】。本机默认索引（`ax-docs` 51 docs + memory namespaces）**查不到任何正交路由/避障/轨道分配条目**（见 §1）；我们用隔离实例索引 libavoid 源码后，查询能命中 `nudge`/`crossing penalty`/`orthogonal visibility` 等真实代码位置（见 §1.3）。**结论：可用作开发期代码检索工具，不作为运行时依赖；task-249 无必须使用 XERJ 的项。**
5. **26 节点/30 边、layout<16ms：可达，但有条件**【推/待测】。按 §4 的预算分析，一次 `routeAll` 主要成本是 30 条边 ×（有界 A* + 占用写 + 两次 nudge + 435 对交叉检测），估算 **2–6ms（TS，dev 机）**；前提是：**布局只在数据变更时跑**（GRAPH-ENGINE §5.1 已如此规定）、每条边只在自身 bbox+margin 内搜索、不做全局可见性图、nudge 迭代 ≤2 轮。**若每帧全量重路由或做 libavoid 式全局可见图，16ms 风险高**【推】。替代：路由缓存 + 增量重路由 + 预计算障碍栅格（§4.4）。

---

## 1. XERJ 结论（它是什么 / 查到了什么 / 没查到什么）

### 1.1 XERJ 是什么（先定位，再查询）

| 项 | 事实 | 证据 |
|---|---|---|
| 产品 | "XERJ: the search engine for AI agents"，**一个 Rust 单二进制**，索引代码/文档/规范/日志，返回带引用的结果；**说 Elasticsearch API**；**Apache-2.0** | 官网 <https://xerj.org>（2026-10-30 抓取）；GitHub <https://github.com/xerj-org/xerj>（GitHub API：`license=Apache-2.0`，2026-10-30）【实】 |
| 官方用法 | "Clone the open-source repos closest to what you're building, index them once with `xerj autoindex`, and the agent retrieves the exact definition" —— **就是"参考编码/reference coding"** | <https://xerj.org> 首屏与 `llms.txt` 链接（页面文本）【实】 |
| 本机服务 | `http://127.0.0.1:9200/` 返回 `{"name":"local","cluster_name":"xerj",...,"version":{"number":"8.13.0",...}}`（ES 8.13.0 兼容面）；进程 `C:\ProgramData\xerj\xerj.exe --insecure --data-dir "C:\Users\Lam Tim\xerj-data"`；另有 4 个 `xerj.exe mcp` 子进程 | 本机 HTTP 探测 + Win32 进程表（2026-10-30）【实】 |
| 本机客户端 | `D:\AAA_Work\ALLELab\agents\xerj.mjs`：`status/search <index> <query>/mem store|recall|list/index <folder>`，默认 `XERJ_URL=http://127.0.0.1:9200`，`index` 调 `xerj autoindex <folder> --url ...` | 文件 L5、L47-74、L151-165【实】 |
| 本机数据 | 索引：`ax-docs`（51 docs，ALLELab agents 代码/文档）、`autoindex-catalog`（数据集目录）、`.xerj-memory-*`（团队记忆命名空间）；**没有**任何路由/图论语料 | `GET /_cat/indices`（2026-10-30）【实】 |
| 版本注记 | 本机索引 `xerj_meta.json` 报 `1.0.0-rc.97`；官网当前 `v1.0.0-rc.100`；**版本不同，查询行为以本机为准** | 本机 `C:\Users\Lam Tim\xerj-data\ax-docs\xerj_meta.json`；xerj.org 页面【实】 |

### 1.2 直接查本机 XERJ：**无相关条目**

查询条件：本机 `:9200`，`ax-docs` + 全部 `.xerj-memory-*` 索引，`query_string` 检索以下词（2026-10-30）：

| 检索词 | `ax-docs` 命中 | 说明 |
|---|---:|---|
| `orthogonal` | 0 | — |
| `routing` | 0 | — |
| `路由` | 0 | — |
| `连线` | 0 | — |
| `避障` | 0 | — |
| `libavoid` | 0 | — |
| `ELK` | 0 | — |
| `Hanan` | 0 | — |
| `轨道` | 0 | — |
| `track assignment` | **1（假阳性）** | 命中 `org.json` 的 `"Track Leads"`（组织层级名），**不是** routing 的 track assignment【实】 |

`.xerj-memory-*`（team-panel/ui/ops/pft/cua-lead/archivist/harness/agents-edges/alelab-ops 等）对 `routing` 均 **0 命中**【实】。

> **结论 A（可直接写进验收）**：本机 XERJ **可达**（HTTP 200），但其**现有索引没有"图连线正交路由/避障/轨道分配"相关条目**；唯一疑似命中是组织名假阳性。**不得**把 XERJ 现有索引当作路由方案来源。

### 1.3 按 XERJ 官方用法做"参考编码"查询：索引 libavoid 源码后命中

为了验证"XERJ 查询"是否可行，我做了**隔离实例**实验（不动本机 `ax-docs`，不污染默认前缀）：

- 隔离服务：`xerj.exe --insecure --port 9399 -d %TEMP%\xerj-routing-src\data`（独立 data dir；不写本机 `xerj-data`）【实】
- 索引对象：Adaptagrams/libavoid 的 12 个源文件（`orthogonal.cpp`、`router.cpp`、`makepath.cpp`、`connector.cpp`、`visibility.cpp`、`graph.cpp`、`hyperedgeimprover.cpp`、`router.h`、`orthogonal.h`、`connector.h`、`makepath.h`、`LICENSE.LGPL` + README），共 **429,530 bytes**【实】
- `xerj autoindex --url http://127.0.0.1:9399 --prefix rt` 结果：`xerj-done ok=true ... files=12 records=260`；补齐一个被截断文件后重跑：`rt-docs` **296 docs**（索引目录 `%TEMP%\xerj-routing-src\data`）【实】
- 检索结果（`/rt-docs/_search`，2026-10-30）：

| 查询 | 命中数 | 命中文件（XERJ 返回） |
|---|---:|---|
| `nudge orthogonal segments` | 109 | hyperedgeimprover.cpp, connector.cpp, router.cpp, router.h, orthogonal.cpp |
| `crossing penalty` | 28 | connector.cpp, router.cpp, makepath.cpp, router.h, orthogonal.cpp |
| `improve orthogonal topology` | 120 | router.cpp, router.h, orthogonal.cpp, hyperedgeimprover.cpp |
| `crossingPenalty` | 6 | router.cpp, makepath.cpp, router.h |
| `orthogonal visibility graph` | 121 | connector.cpp, router.cpp, makepath.cpp, visibility.cpp, connector.h |
| `segment nudge` | 65 | hyperedgeimprover.cpp, connector.cpp, router.cpp, orthogonal.cpp |

> **结论 B**：XERJ 作为"索引源码后检索"的工具**可用**；它能把 `nudge`/`crossingPenalty`/`visibility` 定位到文件级（本机实验返回文件列表；未逐条核验行号）。但它**不提供答案**——答案来自读源码。**任务交付的代码事实以 §2 直接读源码为准，XERJ 只作为复核/检索辅助。**

**对 task-249 的用法建议（不引运行时依赖）**：开发期可 `git clone --depth 1` libavoid/ELK，`xerj autoindex --prefix rt <dir>` 到**临时 data dir**检索关键词；**不要把 XERJ 写进产品依赖**，也不要在 CI 里依赖外部服务【推】。

---

## 2. 开源实现对照（≥4 个；均给 URL/路径 + 许可 + 关键结论 + 可借鉴点）

### 2.1 对照表

| # | 实现 | 许可 / 体积（相关源码） | 如何保证"不重叠" | 如何处理"允许交叉" | 复杂度/规模 | 可借鉴点 / 不适用点 |
|---|---|---|---|---|---|---|
| 1 | **libavoid / Adaptagrams**（C++）<br>`github.com/mjwybrow/adaptagrams` → `cola/libavoid/` | **LGPL-2.1**（`cola/libavoid/LICENSE.LGPL`）；核心源 ~500KB：`orthogonal.cpp` 118KB、`router.cpp` 99KB、`connector.cpp` 79KB、`makepath.cpp` 52KB、`hyperedgeimprover.cpp` 42KB【实】 | **后处理 nudge**：路由完 → `ImproveOrthogonalRoutes::execute()` 逐维 `simplify → unifying → nudgeOrthogonalRoutes → resimplify → improveOrthogonalTopology`（orthogonal.cpp L2533-2595）；nudge 以 `idealNudgingDistance`（默认 **4**）为分离距离，**10 次递减尝试**（L2604-2608）；`NudgingShiftSegment` 用约束求解器移动段（L115-265）；collinear 重叠检测 `overlapsWith`（L304-349）【实】 | **软惩罚**：`crossingPenalty` 默认 **0**（=允许）；>0 时 `improveCrossings()` 找交叉对并重路由（router.cpp L1409-1483、L1411-1475）；另有 `clusterCrossingPenalty=4000`、`fixedSharedPathPenalty`；**不做桥接渲染**（交给上层）【实】 | 交互式编辑器级；可见性图 + A* + nudge，26/30 节点在 C++ 中很小；**无 JS 版** | **最优参考**：pipeline 顺序（route → crossing 重路由 → nudge → topology）、惩罚项公式、nudge 的"分离距离+递减尝试"；**不适用**：LGPL + C++，不能直接嵌进 0 依赖 TS（需重写）【实+推】 |
| 2 | **Eclipse ELK Layered**（Java）<br>`github.com/eclipse/elk` → `p5edges/OrthogonalEdgeRouter.java`、`p5edges/orthogonal/OrthogonalRoutingGenerator.java` | **EPL-2.0**（`LICENSE.md`）；两个类 14KB + 25KB（另 HyperEdge* 若干）【实】 | **slot 分配 + 冲突依赖图**：`OrthogonalRoutingGenerator` 计算 `conflictThreshold=0.5×edgeSpacing`、`criticalConflictThreshold=0.2×minDistance`；冲突段分配**不同 routing slot**；critical 冲突成环则 **split hyperedge segment**（L68-110、L180-241）；`OrthogonalEdgeRouter` 用 `slotsCount` 算 `routingWidth=(slots-1)*edgeEdgeSpacing`（L242-281）【实】 | **软代价**：`CONFLICT_PENALTY=1`、`CROSSING_PENALTY=16`（L76-79）；交叉**允许**但计入代价；跨层交叉由层次布局/端口约束共同决定【实】 | 工业级布局，数百节点；Java；elkjs 体积约 1.3–1.7MB【推/待复核】 | 借"冲突→slot/依赖图/拆段"的思路与常量；**不适用**：EPL、体积大、面向层次布局（我们的语义泳道是固定结构）【实+推】 |
| 3 | **ELK 的 Libavoid 算法封装**（ELK reference） | EPL-2.0；作为 ELK 算法 `org.eclipse.elk.alg.libavoid` | 同 libavoid（nudge） | 同 libavoid（`crossingPenalty` 默认 0） | 同 libavoid | 证明 libavoid 已被生产化集成；其**默认参数表**可直接借：`segmentPenalty=10`、`idealNudgingDistance=4`、`shapeBufferDistance=4`、`processTimeout=10000`、`crossingPenalty=0`、`nudgeOrthogonalSegmentsConnectedToShapes=false`、`nudgeOrthogonalTouchingColinearSegments=false`、`nudgeSharedPathsWithCommonEndPoint=true`、`performUnifyingNudgingPreprocessingStep=true`【实】 |
| 4 | **AntV X6 manhattan 路由**（TS）<br>`github.com/antvis/X6` → `src/registry/router/manhattan/` | **MIT**（`LICENSE`）；`router.ts` 10.9KB、`obstacle-map.ts` 5.7KB、`options.ts` 5.3KB【实】 | **网格 A***：`util.getGrid(options.step, ...)`（router L47-48）、openSet + `maxLoopCount`（L88、L118）；障碍栅格 `ObstacleMap` 以 `mapGridSize=100` 建格、`paddingBox` 膨胀节点（obstacle-map L21、L91-96、L115）——**只避节点，不避其他边**（无 edge occupancy/nudge）【实】 | 不处理：允许交叉/重叠（由上层渲染决定）；有 `fallbackRouter` 兜底（options L116-133）【实】 | 纯 TS、轻量；适合 20–200 节点；**默认 `step=10`、`maxLoopCount=2000`、`maxDirectionChange=90`**（options L145-153）【实】 | **最贴近我们的 A* 骨架**（MIT、纯 TS、无依赖）；**缺口**：不避边、不 nudge、不桥接 → 需补 §3 的占用表 + nudge + bridge【实+推】 |
| 5 | **OpenROAD TritonRoute**（C++，VLSI 详细布线）<br>`github.com/The-OpenROAD-Project/OpenROAD` → `src/drt/` | **BSD-3-Clause**（`LICENSE`）；整个 drt 插件体量大（MB 级），**只可读思路** | **track assignment**：先 pin access → **track assignment** → initial detailed routing → search & repair → DRC（`src/drt/README.md` L4-8）【实】 | **换层/via**：交叉由多层金属 + via 解决，不是 2D 桥接；DRC 修复循环（rip-up & reroute）【实】 | 芯片级（百万线网）；不适用本场景规模 | 借"先分轨再细节路由 + 迭代修复"的**阶段划分**；**不适用**：领域/规模/语言完全不匹配【实+推】 |
| 6 | **GoJS（文档层面，非开源）**<br>`gojs.net` | **商业许可**（Northwoods Software License，`https://gojs.net/latest/license`；不是 OSI 开源）【实】 | `Link.routing = go.Link.Orthogonal` / `AvoidsNodes`；AvoidsNodes 可绕节点，但**明显更慢**，且"节点围成一圈时会放弃并穿过节点"（links 文档原文）【实】 | **桥接**：`Link.curve = go.Curve.JumpOver / JumpGap`——"Orthogonal link segments will veer around / be discontinuous where they cross over other orthogonal link segments"（Curve API 文档）【实】 | 商业库；文档可参考 | **桥接语义的直接先例**（JumpOver=跃过、JumpGap=断口）；`fromEndSegmentLength/toEndSegmentLength` 控制出线直段；**不抄代码/不引依赖**（商业许可）【实】 |
| — | jsPlumb | 尝试：`github.com/jsplumb/jsplumb` 的 `main` 只剩 `README.md`（GitHub Contents API 2026-10-30），**代码不可得**；不再作为对照【实】 | — | — | — | 记录为"取不到"，不编造 |

### 2.2 "不重叠"的三种实现范式（对照后的归纳）

| 范式 | 代表 | 机制 | 代价/风险 |
|---|---|---|---|
| **A. 找路 + nudge（后处理）** | libavoid | A*（可见性图）找路；nudge 沿垂直方向把重叠/过近的平行段推移到不同通道，分离距离 `idealNudgingDistance`；10 次递减尝试 | nudge 可能失败（空间不足）；可能改变已路由段；每轮 O(段数²) 级冲突检测【实】 |
| **B. 通道 slot 分配** | ELK | 先按层/通道把边段分到 slot；冲突阈值判定 → 不同 slot；critical 环 → 拆段；依赖图拓扑排序后算坐标 | 需要"层/通道"结构；槽位用尽会增宽布局【实】 |
| **C. 网格占用 + 预留轨道** | 我们的推荐（X6 + 自研） | A* 的 grid 单元带占用标记；同向占用=禁止（重叠），横向占用=允许但计交叉代价；路由后按轨道 pitch 做局部 nudge | 栅格分辨率/内存；复杂稠密区可能无解，需要降级【推】 |
| （补充）D. VLSI track assignment | OpenROAD | 先给每个 net 分配轨道，再细节布线；交叉走不同层 | 需要多层/换层概念，2D 面板不适用【实+推】 |

### 2.3 "允许交叉"的两种处理（对照后的归纳）

1. **软代价（不禁止）**：libavoid `crossingPenalty=0` 默认允许；ELK `CROSSING_PENALTY=16` 但允许；X6 无交叉代价（允许）。→ **交叉是常态，不应作为硬约束**；只在"交叉过多导致可读性差"时提高代价/重路由【实+推】。
2. **桥接渲染（视觉消歧）**：GoJS `JumpOver/JumpGap` 是"正交交叉处断开/跃过"的直接先例；libavoid/ELK 只给几何，不给桥接样式。→ 我们的**桥接应在渲染层做**：路由输出 `bridges[]`（交叉点 + 哪条边在上），SVG 用 `A` 弧或 `stroke-dasharray` 断口【实+推】。

---

## 3. 对 task-249 的推荐骨架（伪代码 + 参数 + 风险）

### 3.1 与现有 GRAPH-ENGINE v1 的关系（先对齐，不推翻）

[GRAPH-ENGINE.md](GRAPH-ENGINE.md) §4.1（L251-256）已有"正交 + 专用通道"方案：同带水平直线、跨带三段/五段、`channels[]`/`vChannels[]` 按 `(from,to,id)` 排序占通道（`ch=idx%MAX_CH`，冲突取下一个），输出 ≤4–6 段。**本报告建议 v1.1 增量**（不推翻 v1）：

1. **保留**：确定性排序、专用通道、`path: Point[]` 输出契约（便于胶囊/断言）。
2. **新增 a（占位）**：通道占用表必须记录 `(band, channel, [x1,x2]/[y1,y2], edgeId)`；`idx%MAX_CH` 复用通道前必须检查区间是否重叠——**这是 v1 产生重叠的根因**【推】。
3. **新增 b（端口扇出）**：同侧多边必须有 port slot（A10 已要求动态分布），否则起点即重叠【实 GRAPH-ENGINE L669】。
4. **新增 c（A* 兜底/复杂边）**：通道路径放不下或跨多带时，用有界 grid A*（只在该边 bbox+margin 内）找路径；成功后再走占用表/nudge。
5. **新增 d（桥接）**：路由后求正交交叉点，输出 `bridges[]`，渲染成 JumpOver/JumpGap。

> 这样既满足"自动规划"，又不把 1,200–1,800 LOC 的纯自研方案（GRAPH-ENGINE §9.2 L486-490）改成移植大库。

### 3.2 算法骨架（可直接照抄的伪代码；无依赖、确定性）

```ts
// 输入：nodes: {id, x,y,w,h, sidePorts:{left:Point[],right:Point[],top:Point[],bottom:Point[]}}[]
//       edges: {id, fromNode, fromPort, toNode, toPort, kind, priority}[]（已由 layout 给出节点坐标）
// 输出：routes: Map<edgeId, Point[]>；bridges: {edgeId, at:Point, horizontalOverVertical:boolean}[]

type Dir = 0|1|2|3; // E,S,W,N
type Cell = { x:number; y:number; dir:Dir };
type RouteOpts = {
  cell: number;              // 4 px（§11.7 ASTAR_STEP=4；8 为允许备选）
  margin: number;            // 24 px（A* 搜索边界相对 bbox 的外扩）
  clearance: number;         // 10 px（§11.7 PARALLEL_CLEARANCE；卡外扩/贴边平行判定）
  portStub: number;          // 12 px（§11.7 / A11-2 MIN_STUB）
  minLineGap: number;        // 8 px（§12.1 MIN_LINE_GAP）
  bendCost: number;          // 4（§11.7 规则5：cost=长度+4×转向次数）
  crossCost: number;         // 0（规范 A* 代价无交叉项；交叉合法性按 §12.1/A12 判）
  overlapCost: number;       // Infinity（禁止同向共格；§12.1/A12-3）
  maxBends: number;          // 6（FEASIBILITY-REVIEW C5）
  maxExpansions: number;     // 20000/edge（本文实现护栏；规范未给值）
  maxTracks: number;         // 4/通道（本文实现护栏；规范未给值，超过则加宽或降级）
};

function routeAll(nodes, edges, opts): {routes, bridges} {
  const obstacles = inflateAndIndex(nodes, opts.clearance);      // 栅格/区间索引
  const occ = new Map<string, {edgeId, dir}>();                  // key = `${x},${y}`；方向 0/1=水平, 2/3=垂直
  const routes = new Map();
  const failed: Edge[] = [];

  // 1) 稳定排序：priority 高 → 短边优先（短边选择少）；ties 用 edge.id 码点序
  const order = edges.slice().sort((a,b) =>
    (b.priority - a.priority) || (len(a) - len(b)) || cmp(a.id,b.id));

  // 2) 逐边路由
  for (const e of order) {
    const stubA = extend(e.fromPort, sideNormal(e.fromSide), opts.portStub);
    const stubB = extend(e.toPort, sideNormal(e.toSide), opts.portStub);
    let path = astar(stubA, stubB, e, obstacles, occ, opts);     // 见 3.3
    if (!path) { failed.push(e); continue; }
    path = simplify(path);                                        // 合并共线段
    reserve(occ, path, e.id);                                     // 写入占用（同向格禁止复用）
    routes.set(e.id, path);
  }

  // 3) 对失败边：允许穿"非卡片"的临时占用（只记交叉代价），或走 v1 通道兜底
  for (const e of failed) {
    const path = astarFallback(e, obstacles, opts);               // 忽略 occ，仍避卡片
    if (path) { routes.set(e.id, simplify(path)); reserve(occ, path, e.id); }
    else routes.set(e.id, channelFallback(e));                    // GRAPH-ENGINE §4.1 通道
  }

  // 4) 共享段 nudge（≤2 轮）：同向且共线/贴 < trackPitch 的段，按 pitch 推移
  for (let iter = 0; iter < 2; iter++) {
    const conflicts = findParallelConflicts(routes, occ, opts);   // 区间重叠/间距不足
    if (conflicts.length === 0) break;
    nudgeInTracks(conflicts, routes, opts);                       // 见 3.4
  }

  // 5) 交叉检测 → 桥接（正交交叉 = 一水平一垂直在格点相交）
  const bridges = detectOrthogonalCrossings(routes);              // 见 3.5
  validate(routes, nodes, opts);                                  // 断言：不穿卡/不共段/弯数≤maxBends
  return {routes, bridges};
}
```

### 3.3 A*：方向感知状态（关键：用 `(x,y,dir)` 才能计拐弯）

```ts
function astar(a:Point, b:Point, e:Edge, obstacles, occ, opts): Point[]|null {
  // 有界：搜索窗 = bbox(a,b) 外扩 opts.margin；超出即失败（防 16ms 抖动）
  const start = cellOf(a, opts.cell), goal = cellOf(b, opts.cell);
  const open = new MinHeap();                                   // 按 f 排序；ties 用 (x,y,dir)
  const g = new Map<string, number>();                          // key = `${x},${y},${dir}`
  const parent = new Map<string, string>();
  open.push(start, h(start, goal));
  let expansions = 0;

  while (!open.empty() && expansions++ < opts.maxExpansions) {
    const cur = open.pop();
    if (cur.x === goal.x && cur.y === goal.y) return reconstruct(parent, cur);

    for (const d of [0,1,2,3]) {
      const nx = cur.x + DX[d], ny = cur.y + DY[d];
      if (!inWindow(nx,ny) || blocked(obstacles,nx,ny)) continue;
      const cell = occ.get(key(nx,ny));
      let step = 1;
      if (cell) {
        if (sameAxis(cell.dir, d) && cell.edgeId !== e.id) step = opts.overlapCost; // 禁止共段
        else if (!sameAxis(cell.dir, d)) step = opts.crossCost;                    // 允许交叉
      }
      if (d !== cur.dir) step += opts.bendCost;                                    // 拐弯代价
      const nd = (g.get(key(cur)) ?? Infinity) + step;
      if (nd >= (g.get(key(nx,ny,d)) ?? Infinity)) continue;
      g.set(key(nx,ny,d), nd); parent.set(key(nx,ny,d), key(cur));
      open.push({x:nx,y:ny,dir:d}, nd + h(nx,ny,goal));
    }
  }
  return null; // 失败 → channelFallback / 增大 margin 重试一次
}
```

**确定性**：`MinHeap` 的 ties 必须用 `(f, x, y, dir, edgeId)` 全序；禁止 `Set/Map` 迭代顺序参与选择；不随机。

### 3.4 nudge：按轨道 pitch 推移平行段（借 libavoid 的"分离距离 + 递减尝试"）

```ts
function nudgeInTracks(conflicts, routes, opts) {
  const pitch = opts.minLineGap;                // 8px：§12.1 MIN_LINE_GAP（不是 cell）
  // 分组：同一 y（水平段）或同一 x（垂直段）上的所有段，按区间排序
  for (const group of groupByLine(conflicts)) {
    // 目标：让相邻段中心距 ≥ pitch；优先移动"优先级低/弯少"的段
    const tracks = assignFirstFit(group, pitch);   // 每段一个 track 索引
    for (const seg of group) {
      const shift = (trackIndex(seg) - currentTrack(seg)) * pitch;
      shiftSegment(seg, shift, { maxShift: 2*pitch, avoid: obstacles });
    }
  }
}
```
- 若 shift 后撞卡/越界：回退该段，标记"未化解"，走 A* 重路由（最多 1 次）；仍失败则接受交叉（渲染桥接）并记诊断【推】。

### 3.5 桥接：检测正交交叉 → 只桥接一次

```ts
function detectOrthogonalCrossings(routes) {
  const bridges = [];
  // 对每对边做线段求交（垂直线段 vs 水平线段），O(E²)，30 边 = 435 对，可忽略
  for (const (a,b) of edgePairs(routes)) {
    for (const p of intersectOrthogonal(routes[a], routes[b])) {
      // 只让"优先级低"的边断开（避免两次桥接同一交叉）
      const under = lowerPriority(a,b);
      bridges.push({edgeId: under, at: p, horizontalOverVertical: isHorizontal(a,b,p)});
    }
  }
  return bridges.filter(dedupe);  // 同坐标只保留一条
}
```
- 渲染：`under` 边在 `at` 处画 3px 断口 + 半圆（`A r=3`）；或 `stroke-dasharray` 断口。**不要**给两条边都画桥（视觉双断）【推】。
- 只保留锐角 **≥15°** 的真交叉（§12.1/A12-3）；`<15°` 的浅角交叉按违规处理：先加惩罚改道，无法改道则按 §12 合法合并（不是桥接）【实+推】。

### 3.6 参数建议（起始值 → 调参范围）

| 参数 | 建议值 | 依据/说明 |
|---|---|---|
| `cell` 网格步长 | **4 px**（8 为允许备选） | 规范 §11.7 `ASTAR_STEP=4`（"示例；可 4/8"）；4 是默认口径，8 只应是性能降级备选【实】 |
| `clearance` 卡外扩 | **10 px** | 规范 §11.7 `PARALLEL_CLEARANCE=10`（贴边平行判定距离，严格 <10 即违规）；A11-3 要求非 stub 段到卡边最小距离 ≥10px【实】 |
| `portStub` 出线直段 | **12 px** | 规范 §11.7 / A11-2 `MIN_STUB=12`；首/末段必须垂直且 ≥12px【实】 |
| `bendCost` | **4** | 规范 §11.7 规则 5：`cost = 长度 + 4×转向次数 + 0.2×贴边邻近惩罚`【实】 |
| `crossCost` | **0** | 规范 A* 代价未含交叉项；交叉合法性由 §12.1/A12-3 判定（≥15° + bridge），不应靠 A* 代价替代【实】 |
| `overlapCost` | **∞** | §12.1/A12-3：共线重叠（0°）按违规处理；由 nudge/改道消除【实】 |
| `MIN_LINE_GAP` | **8 px** | §12.1/A12-1：任意两线出 stub 后最小间距 ≥8px（卡边 8px 带内豁免）【实】 |
| `MIN_CROSS_ANGLE` | **15°** | §12.1/A12-3：交叉锐角 ≥15°；<15° 浅角交叉按违规处理（改道或合法合并）【实】 |
| `maxBends` | **6** | [FEASIBILITY-REVIEW.md](FEASIBILITY-REVIEW.md) C5：折弯 ≤6；GRAPH-ENGINE §4.1 L256 "≤4–6 段"【实】 |
| `maxExpansions` | **20000/边** | 本文实现护栏；规范未给数值；26/30 场景单边远低于此【推】 |
| `maxTracks` | **4/通道**，超过则加宽通道/降级 | 本文实现护栏；规范 §4.1 只有 `MAX_CH` 占位未给数值；ELK slot 分配思路可参考【实+推】 |
| nudge 轮数 | **≤2** | libavoid 内部最多 10 次递减尝试（更重）；我们 UI 场景 2 轮够【实+推】 |
| 路由缓存 key | `nodePositionsHash + edgeIds + portAssignments` | 布局不变即复用（§4.4）【推】 |

### 3.7 风险清单（给实现者）

| 风险 | 症状 | 缓解 |
|---|---|---|
| 通道饱和 | 多条边挤同一 band，nudge 无轨可移 | 加宽通道/重排端口；超 `maxTracks` 时允许桥接交叉并记诊断【推】 |
| 端口共点 | 同侧多边起点重叠 | A10 端口扇出（按边数均分，±4px 偏移）；起点 stub 长度分层【实 GRAPH-ENGINE L669】 |
| 桥接视觉噪声 | 交叉密集区大量断口 | 只桥"优先级低"的边；交叉数 >N 时降级为普通交叉并提示；`prefers-reduced-motion` 不影响静态桥【推】 |
| A* 非确定 | 同输入两次路径不同 | ties 全序（f,x,y,dir,edgeId）；禁用随机/Set 迭代顺序；单测固定种子【推】 |
| 布局每帧重算 | <16ms 不稳 | 遵守 GRAPH-ENGINE §5.1：布局只在数据变更时跑；动画只 tween 坐标【实】 |
| 障碍膨胀不一致 | 路径穿卡/贴边 | 障碍 = 卡片 rect + clearance；端口 12px 内豁免；断言"path 不进入任何 inflated rect"【实 GRAPH-ENGINE L256】 |
| 退化输入 | 边连接同节点、自环、重叠卡片 | 自环走固定 3 段环；重叠卡片先由布局消除（§3 已保证不重叠）【推】 |

---

## 4. 规模结论：26 节点 / 30 边、layout <16ms 是否可达？

### 4.1 预算拆解（【推】，单位 ms，dev 机；需 task-249 实测【待测】）

| 阶段 | 估算 | 说明 |
|---|---:|---|
| 障碍栅格/索引 | 0.2–0.5 | 26 卡片 × 4 边 + 30×2 端口，一次性建窗 |
| 30 条边 A*（有界） | 1.5–3.5 | 每边搜索窗 ≤ ~40×40 格；单边 expansions 通常 <2k；direction 状态 ×4 |
| 占用写 + 冲突检测 | 0.2–0.5 | 30 条 path，段数 ≤6 |
| nudge 2 轮 | 0.5–1.5 | 冲突段数远小于总段数；O(段数²) 但段数 ~100 级 |
| 交叉检测（435 对） | <0.1 | 线段求交，30 边 |
| 桥列表 + 断言 | <0.1 | — |
| **合计** | **≈2.5–6 ms** | 在 16ms 内，留 ~10ms 给节点布局/React 提交/余量 |

**结论**：
- **可达**【推/待测】：26/30 属于小规模；`layout()` 只在数据变更时执行（不是每帧），16ms 裕量足够。
- **风险条件**【推】：① 每帧全量路由；② 使用 libavoid 式全局可见性图 + 多轮 topology 优化；③ 无 `maxExpansions`/无界搜索窗；④ 每条边都做全图 A*。任一出现都可能把 30 条边推到 >16ms。
- **必须实测**：在 `engine` 单测里加 benchmark（3 次运行取最小 p95），记录 `routeAll` 单独耗时【待测】；不要用 dev React 渲染路径计时（GRAPH-ENGINE §7-A5 已要求 headless 纯函数）。

### 4.2 若实测不达标：替代方案（按优先级）

1. **缓存**：`routeCache` key = 节点坐标 hash + edge 集合 + port 分配；节点未动直接复用（最常见）【推】。
2. **增量路由**：只重路由"端点移动/新增/删除"的边；其余边保留 path，再做全局冲突检查（局部 nudge）【推】。
3. **预计算**：障碍栅格/端口坐标在 `layout()` 一次性算好，`route()` 复用；搜索窗按边 bbox 裁剪【推】。
4. **降级**：先保"不穿卡/不重叠"，桥接只画前 N 个；超密集时回退 v1 通道 + 允许交叉不桥（必须显示诊断，不能静默）【推】。
5. **拆分**：`layout()` 与 `route()` 分离为两个可独立计时的纯函数（ENGINE-ACCEPTANCE 已要求纯函数引擎包）；必要时把路由推迟到 `requestIdleCallback`（但首帧不能空白）。

### 4.3 验收断言建议（可直接给 task-249 的单测）

- **A-r1 不穿卡**：每条 path 的每个点都不在任何 `inflate(node, clearance)` 内（端口 12px 豁免）【实 GRAPH-ENGINE L256 口径】。
- **A-r2 不重叠**：任意两条不同边的同向共线段交集长度 = 0；出 stub 后平行段中心距 ≥ `MIN_LINE_GAP=8`（nudge 后；§12.1/A12-1）【实】。
- **A-r3 桥接完整**：每个正交真交叉点恰有一条边被标记 `bridges[]`；同坐标不重复；交叉锐角 ≥ `MIN_CROSS_ANGLE=15°`（§12.1/A12-3）【实】。
- **A-r4 确定性**：同一 `(nodes,edges,viewport)` 连跑 3 次，`routes` 序列化逐字节相同【实 GRAPH-ENGINE §7-A1 确定性要求】。
- **A-r5 预算**：26/30 fixture 上 `routeAll` p95 < 8ms（留 8ms 给布局/提交）；`layout` 总 p95 <16ms【待测】。

---

## 5. 引用清单（真实 URL / 路径 / 许可 / DOI）

### 5.1 XERJ

- XERJ 官网（产品定位、ES 兼容、Apache-2.0、reference coding 用法）：<https://xerj.org>（2026-10-30 抓取）【实】
- XERJ 源码仓：<https://github.com/xerj-org/xerj>（Apache-2.0）【实】
- 本机服务：`http://127.0.0.1:9200/`（ES 8.13.0 兼容面）；二进制 `C:\ProgramData\xerj\xerj.exe`；数据目录 `C:\Users\Lam Tim\xerj-data`【实】
- 本机客户端：`D:\AAA_Work\ALLELab\agents\xerj.mjs`（L5、L47-74、L151-165）【实】
- 隔离检索实验：`%TEMP%\xerj-routing-src\data`（port 9399，prefix `rt`；12 个 libavoid 源文件，296 docs；2026-10-30）【实】

### 5.2 开源实现

| 实现 | URL / 本地路径 | 许可 |
|---|---|---|
| Adaptagrams / libavoid | <https://github.com/mjwybrow/adaptagrams>；`cola/libavoid/`（`orthogonal.cpp` L115-265、L2509-2621；`router.cpp` L86-97、L641-657、L925-1034、L1409-1483；`makepath.cpp` L84-131、L310-481；`doc/description.doc`） | **LGPL-2.1**（`cola/libavoid/LICENSE.LGPL`）|
| ELK | <https://github.com/eclipse/elk>；`plugins/org.eclipse.elk.alg.layered/src/org/eclipse/elk/alg/layered/p5edges/OrthogonalEdgeRouter.java`（L59、L218-281）、`.../p5edges/orthogonal/OrthogonalRoutingGenerator.java`（L68-110、L180-241） | **EPL-2.0**（`LICENSE.md`）|
| ELK Libavoid 算法/默认参数 | <https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-alg-libavoid.html>；<https://eclipse.dev/elk/reference/options/org-eclipse-elk-edgeRouting.html> | EPL-2.0（文档）|
| AntV X6 manhattan | <https://github.com/antvis/X6>；`src/registry/router/manhattan/{router.ts,obstacle-map.ts,options.ts}`（router L47-48/L88/L118；obstacle L21/L91-115；options L145-153） | **MIT**（`LICENSE`）|
| OpenROAD TritonRoute | <https://github.com/The-OpenROAD-Project/OpenROAD>；`src/drt/README.md`（L4-8） | **BSD-3-Clause**（`LICENSE`）|
| GoJS（文档层面） | <https://gojs.net/latest/learn/links>（Routing/AvoidsNodes/end segment lengths）；<https://gojs.net/latest/api/symbols/Curve.html>（JumpOver/JumpGap）；<https://gojs.net/latest/license> | **商业许可**（非开源）|

### 5.3 经典论文（Crossref 元数据核对，2026-10-30）

| 论文 | DOI / 年份 | 与本方案的关系 |
|---|---|---|
| Hanan, "An Algorithm for Path Connections and Its Applications", IRE Trans. Electronic Computers | <https://doi.org/10.1109/TEC.1961.5219222>（1961）【实】 | **Hanan grid** 出处：路径只可能在"穿过障碍边界/端点的坐标线"交点转弯，网格可大幅裁剪 |
| Hashimoto & Stevens, "Wire routing by optimizing channel assignment within large apertures", DAC'71 | <https://doi.org/10.1145/800158.805069>（1971）【实】 | **channel routing / track assignment** 的源头（左边界算法） |
| Rivest & Fiduccia, "A 'Greedy' Channel Router", 19th DAC | <https://doi.org/10.1109/DAC.1982.1585533>（1982）【实】 | 贪心 + rip-up/reroute；对应我们的"失败边重路由/迭代修复" |
| Wybrow, Marriott, Stuckey, "Orthogonal connector routing", GD'09 | <https://doi.org/10.1007/978-3-642-11805-0_22>（2009/2010 LNCS 5849）【实】 | libavoid 的算法论文（正交连接线 + 障碍 + nudge） |
| Wybrow, Marriott, Stuckey, "Incremental connector routing", GD'05 | <https://doi.org/10.1007/11618058_40>（2006 LNCS 3843）【实】 | **增量路由**：只重路由受影响的连接线（对应 §4.4 增量化） |
| Wybrow, Marriott, Stuckey, "Orthogonal hyperedge routing", Diagrams 2012 | <https://doi.org/10.1007/978-3-642-31223-6_10>（2012）【实】 | 多端（hyperedge）正交路由；若未来出现"一组边共享主干"可参考 |
| Marriott, Stuckey, Wybrow, "Seeing Around Corners: Fast Orthogonal Connector Routing", Diagrams 2014 | <https://doi.org/10.1007/978-3-662-44043-8_4>（2014）【实】 | 快速正交路由（性能优化思路） |

### 5.4 本仓对齐文档

- [GRAPH-ENGINE.md](GRAPH-ENGINE.md) §4.1（L251-256：正交通道）、§5.1（L307-309：布局不在每帧）、§9.2（L486-490：纯自研 vs elkjs）、A10（L669：端口动态分布）【实】
- [ENGINE-ACCEPTANCE.md](ENGINE-ACCEPTANCE.md) L174（layout<16ms、compose p95<4ms）、L330（A5）【实】

---

## 6. 一句话交付

**甲方要的四件事**：不重叠 → 占用表 + 轨道 nudge（libavoid/ELK 范式）；不穿方框 → 障碍膨胀 + A* 阻挡；允许交叉 → 软代价（ELK/libavoid 默认允许）+ GoJS 式桥接渲染；自动规划 → 确定性 `routeAll`（排序/A* 全序/无随机）。**建议在 GRAPH-ENGINE §4.1 的通道方案上做 v1.1 增量（占用表 + 端口扇出 + A* 兜底 + 桥接），不引入 libavoid/ELK 依赖，26/30 边 <16ms 结构性可达（2–6ms 估算，需实测）。**
