# S0 提案 A · 证据与反例清单

> 配套：`S0-terms-proposal-A.md`｜票：task-289｜日期：2026-11-02
> 用途：让另一人**只按本文件**即可复核提案中的每一条断言（file:line / 产物路径 / 复跑命令）。
> 独立声明：**未阅读**独立复核方草稿（`S0-terms-proposal-B.md` / `S0-objections.md` / 工程复核）；本提案仅基于章程、原话、议程、现有契约与只读代码撰写；若本场目录中出现其他成员文件，本提案未读取其内容、未引用其结论。

---

## 0. 证据等级与统计

| 级 | 含义 | 本提案主要用途 |
|---|---|---|
| A | 原话/冻结契约/决策/现有可复跑代码事实 | 术语边界、现有行为、契约限制 |
| B | 单源实测产物（artifacts 研究证据） | 边语义数量、退化边、消费读取点 |
| C | 单源推理/待验证假设 | （本提案尽量不用；少量标在"待验证"） |
| 本项目假设 | 无独立证据的显式设计约定 | 形式化选择（划分、划分互斥、状态枚举等） |

**统计**（按提案 12 项主裁决计）：A 级锚点逐行列于 §1–§12（file:line / 决策 id，均可 grep 复核；未做人工计数以避免不可复现数字）；B 级产物 **5 份**（见 §13：`contain-evidence.json`、`G2-L2-protocol.md`、`G4-link-semantics.md`、`CONTAIN-SEMANTICS.md`、`CONTAIN-AUTHOR-FLOW.md`）；**本项目假设 12** 条（逐条列于 §15）；C 级 0 条主张被当作结论（仅 §17 已知限制列为待验证）。

---

## 1. S0-1「语义」的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| reference 是"无断言跳转"、不进语义边集 | `docs/design/kg-ontology-v0.md:51-59`（§2.1 reference 定名） | A |
| contain 有 structural/semantic 两义；structural 不承诺整体-部分 | `docs/design/kg-ontology-v0.md:113-130`（§2.3）；`docs/design/kg-edge-provenance.schema.json:136-149`（contain_kind 描述） | A |
| semantic 必须有 assertion_source（schema allOf 强制） | `docs/design/kg-edge-provenance.schema.json:202-230`（allOf：semantic→assertion_source；system_range→structural） | A |
| 原话：图谱最重要的是语义 | `docs/design/multilevel-graph-vision.md:18`（U-1） | A |
| 原话：一跳背后图不一定有语义关系 | `vision.md:34`（U-17） | A |
| 原话：边有存无/类型差异 | `vision.md:66`（U-27） | A |
| 语义谓词/判据已有研究协议（P1…） | `artifacts/agent/verify/debate/graph-utility/G2-L2-protocol.md:13,102,115`（5 谓词+退化标签；contain 只承载 P1） | B |
| 8 条退化 contain 的名单与数量 | `artifacts/agent/verify/debate/graph-utility/contain-evidence.json`（`counts.contain_degenerate=8`、`l2_contain_sample` 9 条） | B |
| "语义边层"历史研究只作输入，不是多层次设计 | 本提案 §0；`docs/design/multilevel-graph-seminar-agenda.md:10-12`（旧边语义降级为输入） | A |

**T3（决策绑定）为严格判据**：本项目假设（提案 §14 列为争议点 4）。

---

## 2. S0-2 层次/最小粒度的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：非全展开、节点不再是单个 KP | `vision.md:22`（U-5） | A |
| 原话：最小节点粒度=知识点"毋庸置疑" | `vision.md:67`（U-28） | A |
| 原话：层次维度 | `vision.md:25`（U-8） | A |
| 原话：最深层次由会议研讨 | `vision.md:67`（U-28 前句） | A |
| KP 的现有定义/字段（最小粒度的数据载体） | `src/memoria/graph/collector.py:46` 起 `collect_graph_data`；节点字段 id/name/label/description/file/kp_id/start_line/end_line/range_ok（`kg-ontology-v0.md:212-219` 记录） | A |
| KP 身份应用 `kp_id`，同名不同 id 存在 | `artifacts/.../graph-utility/G4-link-semantics.md:78,89`（7 条同名不同 id + OCR） | B |
| `derive_contain_edges` 每次按 range 重派生（层次证据来源之一） | `src/memoria/graph/edge_derivation.py:319-371` | A |

**"层次=嵌套划分"为形式化选择**：本项目假设（提案 §14 争议点 1）。

---

## 3. S0-3 维度的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：层次维度/关联维度/更多维度/开放槽位 | `vision.md:25-29`（U-8..U-12）、`vision.md:64`（U-25）、`vision.md:69`（U-30） | A |
| 议程：已定两维（层次、关联），其余槽位 | `docs/design/multilevel-graph-seminar-agenda.md:26-28,51-57` | A |
| 现存 `graphStyle`（force/galaxy）是视觉风格，非取景规则 | `src/memoria/ui/static/app/js/graph-settings.js` 中 `graphStyle` 相关项；`graph-engine.js:203-215`（hairball 仅视觉提示） | A |
| 现有图谱只有一套全量取景（无维度概念） | `app.js:1842-1861`（`loadGraphData` → `get_graph_data` → `loadPayload`） | A |

**维度组合顺序/单关联维限制**：本项目假设（S1 可改）。

---

## 4. S0-4 簇/代表子图的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：不算严格连通的"连通子图"，内聚高+零星桥 | `vision.md:30`（U-13） | A |
| 原话：按语义关系划分的小群 | `vision.md:31`（U-14） | A |
| 原话：代表节点、点击进入子图 | `vision.md:23-24`（U-6/U-7） | A |
| 现有 `graph-groups.js` = 并查集闭包（接近连通分量），不能直接作新簇 | `src/memoria/ui/static/app/js/graph-groups.js:2`（文件头注释）、`:83`（`computeGraphGroups`） | A |
| 8 退化边必须排除出语义内聚证据 | `contain-evidence.json`（`degenerate_reason` 字段：7 same_name + 1 ocr_prefix）；`G4-link-semantics.md:67,78` | B |
| 现有 contain 边 33/62（语义边层规模） | `contain-evidence.json` `counts`（total 62、contain 33、by_origin range 33） | B |

**"层内簇族必须构成划分、重叠归多归属"**：本项目假设（提案 §14 争议点 2）。

---

## 5. S0-5 一跳挂接的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：挂接一跳、避免多跳污染 | `vision.md:32-35`（U-15..U-18） | A |
| 原话：点击 KP→编辑器；点簇→子图 | `vision.md:36-38`（U-19/U-20） | A |
| 原话：一跳背后图不一定是本图关系 | `vision.md:34`（U-17） | A |
| 当前实现："数据里所有边都被展开渲染"（无跳数/选择性语义） | `graph-engine.js:88`（`expandLinks`）、`:179-181`（`rawEdges=payload.edges; links=expandLinks(...)`） | A |
| 旧 ego-only/0.5 范围（相关但不同） | `kg-ontology-v0.md:262`（D4：0.5 只做域概览+ego） | A |

**"仅语义边、跨维度重置跳数"**：本项目假设（S1/S4 细化）。

---

## 6. S0-6 选择性渲染 + 边存无/类型的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：旧版两端都渲染；新设计选择性渲染 | `vision.md:33`（U-16） | A |
| 原话：边有"存无/类型"不同；必须处理 | `vision.md:66`（U-27） | A |
| 旧行为 = payload 全部边渲染 | `graph-engine.js:179-180`；`app.js:1857`（`loadPayload(res,...)`） | A |
| 类型差异的数据基础：structural vs semantic contain | `kg-ontology-v0.md:113-130`；`schema.json:136-149` | A |
| 视图缺席≠数据缺席（旧版无此概念） | 现有代码无"edge state/缺席原因"字段（`graph-engine.js:167-181` 仅映射基础字段） | A（现状事实）/本项目假设（新枚举） |

**边状态枚举取值为建议**：本项目假设（S4 可细化，但"必须可解释"为裁决点）。

---

## 7. S0-7 多归属的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：一个 KP 可能在不同子图/层次/维度 | `vision.md:38`（U-21） | A |
| 原话：多归属先定义；或不设上限 | `vision.md:70`（U-31） | A |
| 现状：KP 只在所属 sidecar `knowledge_points[]`，无成员关系概念 | `src/memoria/storage/sidecar.py`（load/save 结构）；`document.py:3038` 起 `create_edge` 只写边；`graph-engine.js:167-181` 只认 KP 节点 | A |
| 现有视图出现=payload 全量节点 | `app.js:1842-1861` | A |

**"层内单归属、跨层嵌套、跨维多归属"**：本项目假设（S2/S6 决定上限与存储）。

---

## 8. S0-8 默认视图 vs 全展开的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：默认彻底替代；保留开关全展开 | `vision.md:65`（U-26）；`vision.md:78-80`（§0.4 解读约束：彻底替代指默认入口） | A |
| 原话：规模不是问题，关键后端检索 | `vision.md:71`（U-32） | A |
| 现状：默认全量渲染，无"模式"概念 | `app.js:1842-1861`（loadGraphData）、`graph-engine.js:167-181` | A |
| 现有 2D/3D 两后端已共存（可复用为同接口实现） | `app.js:1630-1660`（initGraphPanel 创建 engine+2D+3D） | A |

**切换焦点映射规则**：本项目假设（S5 细化）。

---

## 9. S0-9 渲染接口的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：2D/3D 不分家、只是带接口的渲染板块 | `vision.md:72`（U-33） | A |
| 现有 2D/3D 共用 engine，但事件字段已不一致 | `graph-view-2d.js:544-547`（nodeClick 带 `edge_id`） vs `graph-view-3d.js:1043`（nodeClick 不带 edge_id） | A（实测代码） |
| 渲染器当前直接吃 `get_graph_data` payload（未抽象 ViewModel） | `app.js:1845`（`call("get_graph_data")`）、`:1857`（`loadPayload`）、`graph-engine.js:167-181` | A |
| 隐私边界（事件只记交互标识） | `graph-view-2d.js:532-542`（D-KG-07 注释：只记 node.id/edge_id/edge_type/origin，不记正文/用户输入/不落盘） | A |
| 现有事件仅有 nodeClick/hover 等 | `graph-view-2d.js:544-547`、`:554`；`graph-view-3d.js:1043` | A |

**ViewModel/事件最小字段集**：本项目假设（S3/S6 可扩展、不可减少）。

---

## 10. S0-10 agent 角色边界的证据锚

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：关键在 agent 怎么设计知识点 | `vision.md:68`（U-29） | A |
| 原话：后端检索算法关键 | `vision.md:71`（U-32） | A |
| v0.3：agent 全权接管知识组织设计；semantic 可经 `curate_contain` 落库并要求审计 | `kg-ontology-v0.md:4`（v0.3 补丁记录）、`:126`（§2.3 规则 1）、`:77-78`（curated_by/curated_at） | A |
| 决策：v0.3 / G6 门禁 / 禁止影子写 | `team/decisions.jsonl`：`dec-20261102-5f71d1da`、`dec-20261102-7b140e94`、`dec-20261102-50f0acdb`（可 grep） | A |
| 现状：agent 检索路径不读边 | `kg-ontology-v0.md:23`（19 读取点/零读取点表）、`:16` | A |
| 现有 agent 工具限 contain 禁手标 | `src/memoria/services/agent/plan.py:100,137,165`（OP_UPSERT_EDGE）、`:205,439,915`（PLAN_EDGE_TYPES） | A |

**"三层权责边界"细节**：本项目假设（机制留 S9/S10）。

---

## 11. S0-11 v1 不做什么的证据锚

| 不做项 | 锚 | 等级 |
|---|---|---|
| 词级/句级节点不做 | `vision.md:67`（U-28）；`vision.md:64`（U-25 槽位） | A |
| 跨库图不做 | 无原话需求；本场未把跨库列入议程（agenda §3） | 本项目假设（范围） |
| 时间/时态维度不做 | `vision.md:64`（U-25）；`kg-ontology-v0.md:74-75`（T 轴只存不用） | A |
| 不自动改写正文 | 本仓 AGENTS.md §1/§2（人拥有正文；agent 只提案）；`vision.md:68-71` | A（边界文件） |
| 不自动推断 semantic | `kg-ontology-v0.md:128`（规则 3） | A |
| 不加新语义类型 | `kg-ontology-v0.md:150-158`（§4 不做清单） | A |
| 不拆 2D/3D 双线 | `vision.md:72`（U-33） | A |
| 全展开不做默认/双主线 | `vision.md:65`（U-26）、`:78-80`（§0.4） | A |
| 渲染器不直读 KB | 本提案 S0-9；现状耦合反证 `app.js:1845` | A（边界）/本项目假设（目标架构） |
| 视图出现不持久化为成员 | 本提案 S0-7；现状无成员概念 | 本项目假设 |
| 不做无审计批量 curation | `kg-ontology-v0.md:126`（审计要求） | A |
| S0 不定簇/检索算法/性能阈值 | `S0-charter.md:13-18`（不在范围） | A |

---

## 12. S0-12 术语映射的证据锚

| 新术语 | 现有锚 | 等级 |
|---|---|---|
| 语义/结构/语义包含 | ontology §2.1/§2.3；schema contain_kind | A |
| 层次/维度 | 无现有字段；`graphStyle` 是视觉风格（`graph-settings.js`） | A（无）/本项目假设（新名） |
| 簇 | `graph-groups.js:2,83`（并查集闭包） | A |
| 代表节点 | 现有节点无 kind 字段（`graph-engine.js:167-178` 映射字段列表） | A |
| 一跳 | 旧 ego-only（`kg-ontology-v0.md:262`） | A |
| 选择性渲染 | 现状全量（`graph-engine.js:179-180`） | A |
| ViewModel | `get_graph_data` payload（`document.py:2124`；`app.js:1845`） | A |
| 渲染后端 | `graph-view-2d.js`/`graph-view-3d.js`/`graph-engine.js` | A |
| 成员关系 | 无；`sidecar.py` 的 `knowledge_points[]` 是存储归属 | A（无）/本项目假设（新概念） |
| 多归属 | 现状 KP 在单文件 sidecar（`sidecar.py` 结构） | A |
| 全展开 | 现状默认（`app.js:1842-1861`） | A |
| curation | v0.3 ontology `:4,126` + schema `:144` | A |

---

## 13. 现有"图谱渲染/边读取"读取点清单（只读证据）

| # | file:line | 现状 | 与本提案关系 |
|---|---|---|---|
| 1 | `src/memoria/services/document.py:2124` | `get_graph_data()` → collector | 唯一数据入口（S0-8 单数据源依据） |
| 2 | `src/memoria/ui/static/app/js/app.js:1842-1861` | `loadGraphData()` 调 `get_graph_data`、`loadPayload` | 现状"无视图层"证据 |
| 3 | `src/memoria/ui/static/app/js/graph-engine.js:167-181` | `loadPayload` 映射 nodes/edges；`expandLinks` 全量 | 旧"数据有边即渲染"证据 |
| 4 | `src/memoria/ui/static/app/js/graph-engine.js:88-110` | `expandLinks` 只做端点/方向投影 | 无类型/语义过滤 |
| 5 | `src/memoria/ui/static/app/js/graph-view-2d.js:544-547` | `nodeClick`（node+edge_id） | 事件契约现状（2D） |
| 6 | `src/memoria/ui/static/app/js/graph-view-3d.js:1043` | `nodeClick`（仅 node） | 事件不一致（U-33 依据） |
| 7 | `src/memoria/ui/static/app/js/app.js:1661-1677` | `onGraphNodeClick` → `jumpToTarget`（假设 `node.file/kp_id`） | 代表节点需要 kind 区分（S0-12 冲突） |
| 8 | `src/memoria/ui/static/app/js/graph-groups.js:2,83` | 并查集闭包分组 | 现有分组≠新簇（S0-4） |
| 9 | `src/memoria/ui/static/app/js/graph-view-2d.js:532-542` | D-KG-07 隐私边界注释 | 事件契约隐私约束（S0-9） |

**边语义输入（不是多层次设计）**：
- `contain-evidence.json`：62 边、33 contain、8 退化、14 消费读取点；
- `CONTAIN-SEMANTICS.md`（v0.2 语义区分）、`CONTAIN-AUTHOR-FLOW.md`（v0.3 curation 通路）；
- `G4-link-semantics.md`：62 raw / 54 clean（剔 8 退化）。

---

## 14. 反例清单（提案中引用的全部反例，逐条可复现）

| # | 反例 | 复核方式 |
|---|---|---|
| R1 | 几何 contain 当语义整体-部分 | `contain-evidence.json`：33/33 contain 无 semantic/assertion_source（structural） |
| R2 | reference 边当语义边 | ontology §2.1（reference 不进语义边集） |
| R3 | 同一文件/标题下=语义 | 结构 vs 语义反例（S0-1 T4） |
| R4 | 句子/段落作为层次 | U-28 原话 |
| R5 | 节点不对应 K 子集（搜索结果集） | S0-2 形式化定义的反例 |
| R6 | graphStyle 当维度 | graph-settings.js 中 graphStyle 仅视觉选项 |
| R7 | 按文件夹分组当簇 | graph-groups.js 并查集闭包 ≠ 内聚+零星桥 |
| R8 | 用 8 退化边作内聚证据 | contain-evidence.json degenerate=8 / G4 §C7 |
| R9 | 展示 2 跳邻居 | U-18 原话 |
| R10 | 一跳时展开 v 的背后子图 | U-17 原话 |
| R11 | 视图中无边⇒数据无关系 | 现状无 edge state（graph-engine.js:167-181）；S0-6 |
| R12 | 全展开绕过类型映射 | S0-6 一致性要求 |
| R13 | 把渲染出现当成员关系 | S0-7 二分定义 |
| R14 | 双入口/全展开默认 | U-26 + §0.4 |
| R15 | 2D/3D 各自事件结构 | 2D:544-547 vs 3D:1043 实测 |
| R16 | agent 自动标注 semantic | ontology v0.2 §2.3 规则 3 |
| R17 | 渲染器直接取数 | app.js:1845 现状（目标架构禁止） |
| R18 | 无审计批量 curation | ontology v0.3 §2.3 规则 1 |

---

## 15. 本项目假设清单（12 条，评审可逐条推翻）

1. 用"KP 集合的嵌套划分"来形式化层次（而非缩放尺度/非划分覆盖族）。
2. 每层簇族构成划分（互斥完备）；重叠簇归多归属/关联维度。
3. 维度组合顺序：层次先定基座，关联只做增量；v1 只允许一个关联维度生效。
4. 一跳默认只沿语义边（不含 structural contain），跨维度跳数重置。
5. "语义"操作判据中 T3（决策绑定）是必要条件（可能偏严）。
6. 边视图状态最小枚举取值为 `full/bridge_only/folded/hidden_by_level/hidden_by_dim/hidden_by_budget/unknown`。
7. 层内单归属、跨层嵌套、跨维度多归属；S0 不设上限。
8. 全展开与默认视图共享同一 ViewModel/类型映射；模式仅两个。
9. 渲染接口事件最小集 = nodeClick/clusterExpand/edgeClick/breadcrumbClick/modeToggle/navigateBack。
10. agent 三层边界：L_kp 主导、L_sem 有证据写入、L_view 设计/执行取景但不做渲染。
11. 视图出现不持久化为成员关系；成员关系需 provenance（来源）。
12. v1 不做项清单（S0-11）的"范围外"解释（尤其跨库、时间维度、新语义类型）。

---

## 16. 复跑与机检（Windows PowerShell；已在本机执行）

```powershell
$env:PYTHONIOENCODING='utf-8'

# 1) 12 议项 + U-1..U-35 是否齐全
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S0-terms-proposal-A.md').read_text(encoding='utf-8'); print('S0 missing:',[f'S0-{i}' for i in range(1,13) if f'S0-{i}' not in t]); print('U missing:',[f'U-{i}' for i in range(1,36) if f'U-{i}' not in t])"

# 2) 现有代码锚（逐条 file:line 可核）
python -c "from pathlib import Path; checks=[('src/memoria/graph/edge_derivation.py',319,'def derive_contain_edges'),('src/memoria/graph/edge_derivation.py',630,'def dedupe_graph_edges'),('src/memoria/services/document.py',2124,'def get_graph_data'),('src/memoria/ui/static/app/js/graph-engine.js',179,'rawEdges = payload'),('src/memoria/ui/static/app/js/graph-view-2d.js',544,'nodeClick'),('src/memoria/ui/static/app/js/graph-view-3d.js',1043,'nodeClick')]; [print('OK' if n in Path(f).read_text(encoding='utf-8').splitlines()[l-1] else 'MISMATCH', f, l, n) for f,l,n in checks]"

# 3) 语义边层证据（B 级产物）
python -c "import json; d=json.load(open('artifacts/agent/verify/debate/graph-utility/contain-evidence.json',encoding='utf-8')); print(d['counts'])"
```

**实测结果（2026-11-02，本机）**：

```text
1) S0 missing: []          U missing: []
2) OK src/memoria/graph/edge_derivation.py 319 def derive_contain_edges
   OK src/memoria/graph/edge_derivation.py 630 def dedupe_graph_edges
   OK src/memoria/services/document.py 2124 def get_graph_data
   OK src/memoria/ui/static/app/js/graph-engine.js 179 rawEdges = payload
   OK src/memoria/ui/static/app/js/graph-view-2d.js 544 nodeClick
   OK src/memoria/ui/static/app/js/graph-view-3d.js 1043 nodeClick
3) {'total_edges': 62, 'contain_edges': 33, 'contain_valid': 25,
    'contain_degenerate': 8, 'by_origin': {'link': 3, 'range': 33, 'sidecar_edge': 26}}
```

---

## 17. 已知限制（不假装解决）

1. **阈值/算法未定**：τ_coh/τ_bridge、层数 L、默认预算 B0 属 S2/S9，本提案只给判据形式。
2. **未做用户实验**：U-2/U-3 的体验目标需 S8 指标验证（C 级，不作结论）。
3. **旧研究证据的语料范围**：`contain-evidence.json` 来自 frozen 62 边语料（B 级单源）；live 库当前规模见 ontology §5.1（134 节点/404 边，A 级但口径需带 manifest sha）。
4. **未读复核方草稿**：两份提案的差异需 Lead 并集时逐条列出（章程 §4.2），本文件不预判。
5. **v0.3 的 agent curation 细则**（`curate_contain` 产品实现）尚在设计中（`CONTAIN-AUTHOR-FLOW.md` 为设计+原型，B 级）；S0-10 只冻结边界，不冻结接口。
6. **现有 2D/3D 事件不一致是现状事实**，修复属 S3/S4 产品设计，不在本场改代码。

---

## 18. 文件与校验信息

```text
docs/design/multilevel-graph/S0-terms-proposal-A.md    （本提案）
docs/design/multilevel-graph/S0-evidence-A.md          （本文件）
docs/design/multilevel-graph-vision.md                 （最高依据，未改）
docs/design/multilevel-graph-seminar-agenda.md         （V0.2，未改）
docs/design/multilevel-graph/S0-charter.md             （未改）
docs/design/kg-ontology-v0.md                          （v0.3，未改）
docs/design/kg-edge-provenance.schema.json             （未改）
```

只读声明：本场未修改任何产品代码/契约/schema/用户库；未 commit（`git status --porcelain -- src docs/design` 应只出现本文件与提案）。
