# KG 设计辩论 Phase 3 — B 知识组织/产品的异议

> 提案方：`todo-owner`（B）｜2026-10-25｜**Phase 3 读入**：A/C/D 提案 + `PHASE2-UNION.md`（C1–C10）。
> 协议：每条异议 ≤120 字 + `ev:` + **撤回条件**；先自打（D 三闸 + C4），再打别人，最后给修正立场。
> 冻结身份（本节所有数字同批）：`ev:corpus:kg-b-phase3` = HEAD `758f7aa1` + KB dirty 239 文件 + 134 sidecar 聚合 sha `0fe6252a…` + 测量脚本 sha `e92192b0…`（见 §1.3）。

---

## 1. 先自打：D 三闸自检 + C4 数字更正（这是本轮最该打我自己的地方）

### 1.1 C4：我的 408 是**缓存快照**，不是 live —— 撤回该数字

| 项 | 值 | 含义 |
| --- | --- | --- |
| 我 Phase 1 的 121/408 | 来自 `.memoria/build/graph.json`，sha `23ad7640…`，mtime **2026-10-23 09:43** | **陈旧的缓存构建**，非 live |
| live（Memoria 官方 collector 现测） | **nodes 133 / edges 404 / links 429**；types=`reference:404`；origins=`link:402, sidecar_edge:2`；relevance 全 **0.7** | 与 C 一致（C4 冲突由我认错解决） |
| A 的 479 | 引 task-86 旧值；A 自己也无法现测复现 | 应撤回引用，不得作为当前事实 |

**结论**：Phase 3 一律用 live `133/404/429`；我的 Phase 1 `121/408` 作废（**撤回条件已满足：我自己复现出 C 的数字**）。冻结方案见 §1.3。

### 1.2 用 D 的三闸自检我的 5 类（候选数据集 = 「同句语义标记词 + wikilink」代理，可复跑）

| 类型 | 候选边（去重源→目标） | 占 429 links | 闸1 区分度（≥10 或 ≥5%） | 闸2 异质度（relevance std≥0.05） | 闸3 决策绑定 | 自检结论 |
| --- | --- | --- | --- | --- | --- | --- |
| `contains` | **0** | 0% | ❌ FAIL | n/a | 理解/范围 | ❌ 不进 v0（D 已证：1 文件 1 KP 结构上不可产生） |
| `prerequisite` | **1** | 0.23% | ❌ FAIL（<10 且 <5%） | ❌（全 0.7） | 先学什么（无数据/无消费者） | ❌ **撤回 v0 主张**（C 对） |
| `sequence` | **0** | 0% | ❌ FAIL | ❌ | 写作模板 | ❌ 撤回 v0（"步骤模板"是文档内结构，不是 KP-KP 关系） |
| `contrast` | **25**（21 个源 KP） | 5.83% | ✅ PASS（≥5%） | ❌（当前全 0.7，需写入时区分） | 理解/写作/迁移（可测） | ⚠️ **v1 首选候选**（不是 v0 直接落数据） |
| `exemplify` | **14**（14 个源 KP） | 3.26% | ✅ PASS（≥10） | ❌（全 0.7） | 写作例证/理解 | ⚠️ **v1 次选**；A 的"边界不可判定"有效，需先定义 example-of vs related |

**自检结论（硬）**：我的"5 类 v0"**不成立**。修正为：**v0 = 0 个新语义边类型（只做契约/字段修复 + 引用层 + 埋点）**；`contrast` 是 v1 第一候选（闸1 过），`exemplify` 第二（需先解决 A 的边界问题），`prerequisite`/`sequence`/`contains` 不进 v0（C/D 对）。
**证据**：`ev:measure:kg-b-phase3-gates`（脚本 `artifacts/agent/verify/debate/kg/_phase3_measure2.py`，sha `e92192b0…`）。
**撤回条件**：若有人用更严格候选定义（如人工标注 20 条样例）证明 `contrast` 候选 <10 条或 <5%，则把 contrast 也移出 v1。

### 1.3 C4 冻结方案（提交给全体）

```
ev:corpus:kg-b-phase3 =
  HEAD 758f7aa1
  + KB dirty 文件数 239（docs/example/AAA_Vocab）
  + 134 sidecar 聚合 sha256 = 0fe6252a1d05a891f9e8ae72b454dba4d8037117550c4ddc2d3935bf8167ac97
  + 测量脚本 sha256 = e92192b03e7104764336c8458909175df591735d84c0f2559eb1d309d6c2d8e2
测法：逐文件 sha256 后排序拼接再 sha256（排除 .memoria/build、cache、backups）
```
**规则**：任何 Phase 3+ 数字必须带 `ev:corpus:<id>`；`docs/example` 的 live 改动使 build 缓存失真（我踩过），一律用 collector 现测，不用 `graph.json`。

---

## 2. 防守（Phase 2 攻击我的 5 点）

### 2.1 Q1「6 场景 = 6 视图」是单根 —— 我承认，并降级为分层

**先给 AAA_Vocab 的场景实例数（不是通用理论）**：`ev:corpus:kg-b-phase3`

| 场景 | 真实库实例（数） | ev |
| --- | --- | --- |
| 背诵 | 卡片 **80 张**（19 错题 + 61 知识卡） | `ev:file:docs/example/AAA_Vocab/.memoria/agent/review/cards.json` |
| 理解 | 181 个 md（133 KP）+ 词族/搭配/对比槽位表 | `vocab/blend.md#L24-L45`、`contrast-linkers.md#L23-L33` |
| 应用 | tags 写作 25 / 口语 23；例句 906 处 | sidecar tags 统计（134 文件） |
| 迁移 | plan「写作喂养口语」1 处流程 | `plan/exam-2026-11-07.md#L21` |
| 复习 | `progress.json` 状态 + `attempts.jsonl` 22KB + FSRS | `.memoria/agent/review/*` |
| 写作输出 | L14 三步、L12 三理由、19 课 SimonClass | `L14-Planning.md#L3-L16`、`L12-Part2MainBody.md#L10` |

**修正**：6 场景不是 v0 交付，而是 3 层路线：T1（现有数据就能做）=背诵/复习/理解（部分）；T2（需 contrast/exemplify 作者化）=应用/写作；T3（需路径实验）=迁移。
**最可能失败的场景=迁移**，我主动构造：它需要"跨技能路径"（写作论点→口语复述）。**为何仍不需要新数据结构**：路径=在现有 404 条边（reference）+25 条 contrast 候选上做 BFS，节点类型不变，只加"路径视图"；失败点不是结构，而是**边权重/相关度不可信**（全 0.7）。⇒ 若 M-16 邻域命中 <30%，迁移视图失败，但**原因是 relevance 无信息**，不是数据结构不够。
**撤回条件**：若出现"必须新增节点类型/字段语义冲突"的具体实例（≥2 个视图），我撤回"一份数据"。

### 2.2 消费者是谁？—— 对 v0 我撤回 prerequisite，对 v1 我重新定义消费者

- 我 Phase 1 说"先学什么必须 prereq"；**自检后撤回该 v0 主张**：真实库只 **1 条**候选（闸1 死），且 C 的 35 会话证据表明 agent 不用。
- v1 的消费者**不是 agent，是人看图 + 复习面板**（A 的判据："只能挂用户可视化决策"；D 的 M-16）。若 A 认为"人看图"不算消费者，则**任何可视化类型都不该存在**——A 必须给"用户可视化决策"的可测判据（D 的 M-16）。
- **撤回条件**：若埋点显示图几乎无人打开（D 的 M-16 无样本）⇒ 人消费也不成立，v1 类型全部推后。

### 2.3 tags 是不是关系？—— 认 A 的陷阱，改证据链

- 实测：tags「对比」**仅 1 个 KP**、「转折」1 个；「写作」25、「口语」23 ⇒ **tags 是适用场景/属性，不是边**（A 对）。
- 我 Q3 的 contrast 证据**改用** prose 里的 `[[target]]`+对比语境：**25 条候选/21 源 KP**（如 `credit-vs-attribute ↔ contrast-linkers 分工`）。这不是 tag 当边。
- **撤回条件**：若人工标注显示这 25 条大多是"关联/参见"而非"对比"，contrast 候选降到 <10 ⇒ contrast 也出 v1。

### 2.4 D 的「reference 边删掉多 2 跳」—— 与"reference 不是边"不冲突

- 区分两层：**inline link**（正文 `[[x]]`，点击直达，删图不丢）+ **graph reference edge**（图里画出的引用线）。
- 若 D 的 2 跳是在**图内导航**（无正文链接可用）测的 ⇒ 说明引用线有**导航**价值，我接受把它保留为 **"引用层"（默认关、可开）**，但它仍不是语义边、不参与布局权重/推理。
- 若 D 的 2 跳是在**正文链接可用**下测的 ⇒ 该结论不成立（用户不用图也能 1 跳）。
- **撤回条件**：D 给出测量口径；若证明图内引用线不可替代（如无正文链接场景占多数），我撤回"默认关"。

### 2.5 A 的「0.5 不该改数据结构，先修枚举不对称」—— 我部分同意

- 同意：**不拆 sidecar 字段、不迁移数据**（A 的 C1–C3 可做）。
- 反对：只做文档+断言 = **0.5 零用户可见改进**，无法用 D 的 M-13 验收；至少应加 **引用层开关（默认关）** + **图交互埋点**（D M-04/M-16），二者都不改数据结构。
- **撤回条件**：若 A 证明"枚举不对称修复"本身能产出可测的用户决策改进（M-16 提升），我撤回加开关/埋点。

---

## 3. 对 A（arch-contract）的异议

| # | 异议（≤120 字） | ev | 撤回条件 |
| --- | --- | --- | --- |
| A-O1 | A 称"429/429 link 全产边"，但 live 图边仅 **402 条 link 派生**（404 总边，差 27）。请给 **429→402 对账**（多 target 去重？区间过滤？），否则"全产"不可复现。 | `ev:measure:kg-b-phase3-live`（collector：origins link 402 / sidecar_edge 2） | A 给出对账表证明 402 = 去重后唯一 (source,target) 对且逐条可查，我撤回。 |
| A-O2 | 只文档化+断言（C1–C3）在 0.5 = **零用户可见变化**；D 的 M-13/M-16 无 graphStyle 埋点就不可验收。至少加引用层开关+埋点（不改数据）。 | `ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-metrics-baseline.md#L238-L250`（M-13/M-16 需埋点） | A 给出"文档+断言"能触发可测决策改进的机制，我撤回。 |
| A-O3 | "exemplify 填不了"太绝对：live 有 **14 条** `[[x]]`+example 语境的候选（如 `get→queue-for-ages`）；但同意**自动推断不可靠** ⇒ 半自动候选+人工确认，不是不加。 | `ev:measure:kg-b-phase3-gates`（exemplify 14 条，样本见脚本输出） | A 证明这 14 条实为"关联"而非 exemplify，或标注成本>收益，我撤回。 |
| A-O4 | A 引用的 **479** 无当前复现（A 自承）；在冻结语料下它是**未登记来源的旧值**，不应参与"数据为 0"论证。 | `ev:corpus:kg-b-phase3`（live 133/404/429） | A 给出 479 的 sha 绑定快照与复跑，我撤回。 |

---

## 4. 对 C（agent-arch）的异议

| # | 异议（≤120 字） | ev | 撤回条件 |
| --- | --- | --- | --- |
| C-O1 | "有真实消费者前不加"把消费者限定为 agent；但 C 自己的 R18（type→颜色）就是**人**的消费，A 也判"只能挂用户可视化决策"。否则类型永不加。 | `ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-agent-arch.md#L158-L163`（R18/R19） | C 证明图/颜色对用户决策无任何可测影响（M-16 无信号），我撤回。 |
| C-O2 | "系统推断类型"没给**精度承诺**；我的候选里 contrast/exemplify 的语境混杂"关联/分工/参见"，无 precision 的推断会把 reference 误标成语义边（比不加更糟）。 | `ev:measure:kg-b-phase3-gates`（25/14 候选中含"分工不同/同构辨析"等混合语境） | C 给出推断方法 + 在 25/14 候选上 precision ≥80%，我撤回。 |
| C-O3 | "35 会话 0 次 edge_type"只能证 **agent 不需要类型**，不能证**人**不需要；C 的 Q1 也说"学习场景今天不能给边合法性"——但这恰是"无数据"，不是"无需求"。 | `ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-agent-arch.md#L95-L106` | C 给出"人也不看类型"的证据（如图点击埋点中颜色无影响），我撤回。 |

---

## 5. 对 D（metrics-baseline）的异议

| # | 异议（≤120 字） | ev | 撤回条件 |
| --- | --- | --- | --- |
| D-O1 | "454 reference 大多 gain=0，删掉多 2 跳"未区分 **inline link 与 图内导航**；若正文链接可用，删图不增 2 跳。请给测量口径（是否禁用正文链接）。 | `ev:file:artifacts/agent/verify/debate/kg/PROPOSAL-metrics-baseline.md#L77-L80` | D 给出"测量时禁用正文链接"的口径，我撤回。 |
| D-O2 | 闸2 用**现有 relevance（全 0.7）**判所有新类型 ⇒ 没有类型能过，是**死闸**；应改为"写入时能否区分 relevance"（设计能力），不是"现有数据是否已区分"。 | `ev:measure:kg-b-phase3-live`（relevance 404/404 = 0.7） | D 举出一个在零作者化下能过闸2 的类型，我撤回。 |
| D-O3 | 闸1 的"候选数据集"未定义；我用"同句标记词+wikilink"代理（可复跑）；请 D 认可该操作化或给更好定义，否则阈值不可比。 | `ev:measure:kg-b-phase3-gates`（脚本 sha `e92192b0…`） | D 给出候选集定义且我的代理偏差 >2 倍，我撤回。 |

---

## 6. 修正后的 B 立场（Phase 3 收敛）

1. **v0 = 0 个新语义边类型**（撤回我的 5 类 v0）。做：link/edge 契约修复（A C1–C3 + C S1/S2）+ **引用层开关（默认关）** + **图交互埋点**（D M-04/M-16/M-13）。
2. **v1 候选排序**：`contrast`（25/5.83%，闸1 过）→ `exemplify`（14/3.26%，需先定义 example-of）→ `prerequisite`/`sequence`（闸1 死，等真实消费者/作者化实验）→ `contains`（词典型库结构不可产生，仅结构型库）。
3. **Q1 降为 3 层路线**（T1 现有数据/ T2 需作者化/ T3 需路径实验）；"一份数据多视图"保留但**接受单根风险**（撤回条件见 2.1）。
4. **Q5 四决策**：③④今天可答；①②⑤ v1 起（前置=contrast/exemplify 作者化 + relevance 分化）。
5. **D 三闸接受为类型准入**；建议闸2 改写为"设计上可区分"（见 D-O2），否则 v1 也无类型可过。

---

## 7. unknowns（更新，M3） / not_doing

- **U1**：contrast/exemplify 的**人工确认成本**（25/14 条候选需多少标注时间）——未知，需 10 条试点。
- **U2**：我的候选代理（标记词+wikilink）与人工语义标注的偏差倍数——未知，需 20 条抽样双标。
- **U3**：`reference` 图内导航价值（D 的 2 跳）在正文链接可用时是否成立——未知，需口径实验。
- **U4**：用户是否真的打开图（M-16 埋点为零）——未知。
- **U5**：`relevance` 能否作者化分化（否则闸2 永远不过）——未知。
- **not_doing（本轮明确）**：不再主张 v0 加 5 类；不主张 prerequisite/sequence 进 v0；不把 tags 当边；不承诺 6 视图 v0 全交付；不做外部文献综述（接受 A/C 的 D6 部分保留，仅要求 2–3 框架作为 v1 设计输入）。

---

## 8. 复跑

```powershell
# 冻结身份
git rev-parse HEAD; git status --porcelain -- docs/example/AAA_Vocab | Measure-Object -Line
python artifacts/agent/verify/debate/kg/_phase3_measure2.py   # 候选边 + 闸1
# live 图（不用缓存 graph.json）
$env:PYTHONPATH='src'; python -c "from memoria.graph.collector import collect_graph_data as c; from collections import Counter; g=c('docs/example/AAA_Vocab'); print(len(g['nodes']),len(g['edges']),Counter(e['type'] for e in g['edges']),Counter(e['origin'] for e in g['edges']),Counter(e['relevance'] for e in g['edges']))"
```
