# KGViz 可视化设计研讨会 · Phase 3 交叉异议 — B（学习场景/产品）

> 提案方：`todo-owner`（B）｜2026-10-26｜Phase 3（Lead 并集 §9 V1–V8 对抗）
> **读入集**：`PROTOCOL.md`（FROZEN）、`PHASE2-UNION.md` 全文、`PROPOSAL-{arch-contract,metrics-baseline,render-perf}.md`、`docs/design/kg-ontology-v0.md`、自己 Phase 1 提案。
> **证据身份（E1）**：`ev:file:<repo-rel>#L<n>` / `ev:bench:<id> (sha)`；本文件所有测量来自 Phase 1 冻结脚本 `_phase1_measure.py`（sha256 `7013715c9ab47ca13c8e11ee0d97a92106af9ce4a40a80eac04f9bcfd5d7acc3`），语料 = KG 辩论冻结 `ev:corpus:kgviz-b-1`。
> **纪律**：每条异议带 ev + 撤回条件（falsifier）；先自打（V2/V6/V1/V4 我主动降级），再打 A/C/D。

---

## 1. 自打与降级（三处必须诚实，一处加固）

### 1.1 V2｜12–13 档：**撤回**（这是我最弱的一环，不硬撑）

**我 Phase 1 写"实测桶：degree 12 档、内容 13 档"（`ev:file:artifacts/agent/verify/debate/kgviz/PROPOSAL-todo-owner.md#L62`）——现在明确：那是「映射后不同半径取值的个数」，不是「人可辨档数」。**它把"程序能生成 12 个不同半径"偷换成了"人能分辨 12 档"，是无效推论。

- 对照证据：C 的 4 档建立在**自承经验值** 3px/20%（`ev:file:.../PROPOSAL-metrics-baseline.md#L84-L90`，原文 U-1：「3px/20% 是经验值，不是本项目实测」）；A 的 5 档用「直径差 ≥4px」也是经验值（`ev:file:.../PROPOSAL-render-perf.md#L69`）。**三方没有任何一方有判读实测**（union L334 同判）。
- **撤回**：撤回「12–13 档可辨」主张，撤回把"桶数"当"可辨档数"的推论。
- **降级后的可验证替代主张**（我主张、可裁）：
  1. **v0 档数不依赖任何未实测阈值**：先采用 **C 的保守 4 档（6→15px）** 作为默认上界（它是三方中最小、最保守的），**并把它标为"待判读实验校准的默认值"**，不是已证明的可辨档数。
  2. **判读实验是 v0 前置验收项**（我认领设计、C 认领执行）：2AFC，同一 133 节点密度、8–24px 直径、相邻档对比、n≥30，正确率 ≥80% 才算该档位可辨；**实测前任何档数（含 4/5/12）都不得写进 release notes**。
- **撤回条件（对我的替代主张）**：若判读实验显示 8px 以上直径差（即 >2 档）在 133 节点密度下识别率 <80% ⇒ 我撤回"4 档默认"，接受 2 档（等同现状，V2 归零）。反之若实验显示 12 档可达 ≥80% ⇒ A/C 的 4–5 档也应上调。

### 1.2 V6｜布局稳定性：**降级为两级主张**（承认"空间记忆是 v0 目标"无证据）

**Lead 实测事实**（union L176-186；代码 `ev:file:src/memoria/ui/static/app/js/graph-layout-2d.js#L37-L51,L244-L246`）：每次 `setGraph` 随机初始位置 + `alpha=1` ⇒ 每次打开大跳。**但"所以空间记忆是 v0 目标"我没有用户证据**——我撤掉这个推理跳跃，拆成两级：

| 级 | 主张 | 成本 | 证据状态 |
| --- | --- | --- | --- |
| **v0 最小（我坚持）** | **同一会话内布局稳定**：hover/zoom/节点选中/面板开关不得触发全局 reheat；新节点从邻居 anchor 生长（≈300ms），其余节点不动；"重新布局"只能由显式按钮触发 | 低（改 reheat 触发条件，不改数据结构） | 现状缺（每次 setGraph alpha=1）；但"用户因此受损"无实测 |
| **v1 假设（我撤回 v0 要求）** | **跨会话位置持久化**（KB path + graph hash → 位置） | 中（localStorage + 新节点入场策略） | 未验证；C 已给可测指标 V-07「重开定位耗时 ≤1.5×首次」（`ev:file:.../PROPOSAL-metrics-baseline.md#L38`） |

**"不做会失去什么具体决策能力"**（正面回答 Lead）：① 复习时再次打开图定位上次看到的 hub/孤立词——重找时间增加；② 对照同一节点两次打开的位置（空间锚点）——无法建立；③ 沿路径"为什么相关"的跟随——每次重排后路径记忆失效。**但这三条都是推理，没有实测**。⇒ 因此 v0 只承诺"不主动破坏参照"（会话内稳定），跨会话收益交给 V-07 实验；**若 V-07 实测重开 ≤1.5×（无持久化也能快速定位）⇒ 我撤回 v1 持久化**（falsifier 已写）。
- **撤回条件（对 v0 最小主张）**：若 C 的埋点显示用户在图上的停留 <5s/次、或节点点击主要发生在打开图后 10s 内（说明没人建立空间参照）⇒ 我撤回"会话内稳定"的必要性，降为 nice-to-have。

### 1.3 V1｜内容体量做备选 size 模式：**撤回 v0 要求，保留 v1 候选**

- 我主张「哪块最厚 → 阅读成本」是真实决策（`ev:file:.../PROPOSAL-todo-owner.md#L31,L47`）：真实库 chars 707–32,847（**46×**），top：International Tourism 32,847 / Income Equality 29,042；plan 按内容量分配阅读时间（`ev:file:docs/example/AAA_Vocab/plan/exam-2026-11-07.md#L11-L19`）。
- **但承认：无用户行为数据证明用户"在图上看厚薄"**（没做 A/B）。A 反对的两条我逐条回：
  1. **"动态范围仅 3.1×"（A L58）是 `end_line−start_line` 行数口径**；chars 口径是 46×（`ev:bench:kgviz-b-phase1`）。行跨度与 chars 不是同一量——A 用行数否定 chars 信息量，口径不成立。
  2. **"D-KG-07 禁用长度/行数"是【验收判据】禁用，不是【数据字段/视觉编码】禁用**（`ev:file:docs/design/kg-ontology-v0.md#L131-L138`：该节标题=「指标裁决」，原文是"禁用判据：长度/行数/块数"）。把"不可作验收指标"扩大成"不可作视觉信号"是误用。
- **降级**：v0 接受 A 的"只进 tooltip"；**备选 size 模式 = v1 候选**，准入条件 = T2 A/B（同文档两节点比厚薄，正确率 ≥90%、时间 ≤8s）通过。
- **撤回条件**：若实测 chars 与行跨度相关性 >0.95（则行数即足够，无需 chars）；或 T2 在 tooltip 下已达标（则无需 size 模式）。

### 1.4 V4｜3D 大小：**接受 A 的"3D 等大 + 度数用颜色"**（撤回我的 1.0–1.25 收紧）

A 实测同一 world 半径在 3D 透视下屏幕尺寸差 **1.78×**（`ev:file:.../PROPOSAL-render-perf.md#L43`），我的"收紧到 1.0–1.25"仍落在该混淆区间内 ⇒ 不可解释。**撤回我的 V4 方案**，v0 采用 A/D：3D 不启用大小语义，度数用颜色/亮度；3D 仅探索用途（与 KG 本体辩论 Q6 一致）。

**保留的加固项（针对 A/C）**：见 §2-3 的 3D 标签/方向异议。

---

## 2. 对 A（render-perf）的异议

| # | 异议（含证据身份） | 撤回条件 |
| --- | --- | --- |
| **A-O1** | A 用「直径差 ≥4px、人眼可稳定区分」（`ev:file:.../PROPOSAL-render-perf.md#L69`）支撑 5 档，但这与 C 的 3px 一样是**经验值**；A 未做判读实验却把它写成"稳定可辨"的事实（我 §1.1 已认同样错误）。**档数必须由统一判读实验裁，不能由任一方案自证**（M1）。 | A 提供判读实验数据（n≥30、2AFC、133 节点密度、相邻档正确率 ≥80%）支持 4px 阈值，我撤回。 |
| **A-O2** | A 用「内容长度动态范围仅 3.1×（行数）」+「D-KG-07 禁用长度/行数」否定内容体量（`.../PROPOSAL-render-perf.md#L44,L58`）；但 chars 口径 46×，且 D-KG-07 是**验收判据**禁用（`ev:file:docs/design/kg-ontology-v0.md#L131-L138`），不是视觉信号禁令。**建议 V1 裁"v1 候选 + tooltip 先行"，而不是"永不"**。 | A 证明 chars 与行跨度不可分（相关 >0.95）或用户判读分不出厚薄（A/B <80%），我撤回。 |
| **A-O3** | A 主张"上大小编码前必须先做标签裁剪"（`.../PROPOSAL-render-perf.md#L103`：标签占 70–75% 成本），我同意顺序；**但缺"裁掉标签后大小可辨率变化"的验收**：标签消失可能让大小差异更难辨（无文字参照），也可能更易辨。顺序≠充分。 | A 补一组 A/B：有/无标签下同一档位识别率；若差异 <5%，我撤回本条，接受其顺序即可。 |

---

## 3. 对 C（metrics-baseline）的异议

| # | 异议（含证据身份） | 撤回条件 |
| --- | --- | --- |
| **C-O1** | C 把「可辨档数 ≥3」写成 V-02 验收 gate（`ev:file:.../PROPOSAL-metrics-baseline.md#L33,L100`），但其 3px 判据**自承是经验值、需 A/B 校准**（同文件 L84-L90，U-1）⇒ **用未验证判据当 gate 违反 M1**。应改为「判读实验通过率 ≥80%」为 gate，档数只是结果。 | C 提供判读数据证明 3px 在本 UI（133 节点、8–24px 直径）成立，我撤回。 |
| **C-O2** | C 的 V-01「挑出最枢纽 3 个点，正确率 ≥随机基线 5 倍≈11.5%」只测正确率、**无时间基线与无辅助控制**（`.../PROPOSAL-metrics-baseline.md#L32`）；hover 高亮/标签都可能让用户"蒙对"，正确率可被 UI 提示污染。 | C 给出 pilot 显示时间与非辅助条件正确率同样敏感，我撤回。 |
| **C-O3** | C 的 V-07「重开后定位已知节点耗时 ≤1.5×首次」是好指标（`.../PROPOSAL-metrics-baseline.md#L38`），但"重开"= 跨会话，**恰好用于验证我的 v1 持久化假设**；C 同时说无埋点不可测（同文件 L20）。⇒ 应明确：V-07 是**埋点后的 v1 实验指标**，不是 v0 验收项，避免"不可测的验收"。 | 埋点落地且在 v0 内完成 V-07 基线，我撤回"仅 v1"。 |

---

## 4. 对 D（arch-contract）的异议

| # | 异议（含证据身份） | 撤回条件 |
| --- | --- | --- |
| **D-O1** | D 主张「视觉属性（radius/color/alpha）绝不进数据层」（`.../PROPOSAL-arch-contract.md#L24-L25`），但其自己的 F2 指出内容体量可由 node 的 `start_line/end_line` 派生（同文件 L42；`ev:file:src/memoria/graph/collector.py#L61-L70` 已含该字段）⇒ **内容体量不需要契约变更**。D 的"跨域 join=污染"判据不能推出"内容体量不能做 size"；应补充规则："**派生自 node 现有字段的视觉量可在渲染层算**"，否则会误杀 V1。 | D 证明 chars 需读正文文件（跨域 IO）而渲染层不可算（行跨度 ≠ chars 且差异 >10%），我撤回。 |
| **D-O2** | D 的毛球判定「不需要新字段，它是 `node.group` 的函数」（`.../PROPOSAL-arch-contract.md#L244`），但同文件 L245 自承**分组无后端字段**、前端 Union-Find；我 Phase 1 实测 Union-Find 最大组 **120/133=90.2%**（`ev:bench:kgviz-b-phase1`）⇒ 用 group 判毛球会恒真/无意义。v0 毛球判定应用 degree/边密度/标签数（均为现有量），**不是 group**。 | D 给出 `node.group` 的稳定语义与数据来源（非 Union-Find 退化），我撤回。 |
| **D-O3** | D 主张 degree 进 collector（`.../PROPOSAL-arch-contract.md#L101`），但 §8 已证 **collector 与 kb_build 是两条后端路径**（union L262-L280）⇒ 若 degree 只由 collector 算，UI 的 degree 与 agent/kb_build 侧不一致，会成为第三事实源。**契约应先冻结"图谱数据路径"，再谈 degree 字段**；否则 V3 的"契约可表达"建在未冻结路径上。 | D 给出"图谱数据路径冻结条款"并明确 degree 的权威来源，我撤回。 |

**支持项（不计异议，供 Phase 4 并入）**：D 的三层分层（数据/映射/渲染，`.../PROPOSAL-arch-contract.md#L127-L145`）和 sizeScale 契约可表达性（L25）我全支持；我的 p10–p90 + sqrt 映射就是 `sizeScale=quantile` 的一个实例（`.../PROPOSAL-todo-owner.md#L61`）。

---

## 5. V1–V8 逐条表态（Phase 4 可直接引用）

| 冲突 | 我的立场 | 依据/条件 |
| --- | --- | --- |
| **V1 内容体量备选模式** | **v0 不做（tooltip）**；**v1 候选**，准入=T2 A/B 通过 | §1.3；A-O2 |
| **V2 可辨档数** | **撤回 12–13**；v0 用 C 的 4 档（6→15px）作"待校准默认值"；判读实验是 v0 前置验收 | §1.1；C-O1；A-O1 |
| **V3 sizeScale** | 支持 D：映射层必须有 `sizeScale: linear\|quantile`；分位≠线性（长尾），我 Phase 1 的 p10–p90 是实例 | D L25/L145；我 L61 |
| **V4 3D 大小** | 撤回我的 1.0–1.25；支持 A「3D 等大 + 度数用颜色」；3D 仅探索 | §1.4；A L43 |
| **V5 标签前置** | 支持 A/B：标签裁剪先于大小编码；但需 A-O3 的补充 A/B | A L103；我 L17/L79-L82 |
| **V6 布局稳定性** | v0 = **会话内稳定**（拒绝 hover/zoom/select 触发全局 reheat + 新节点锚点生长）；**跨会话持久化 = v1 假设**（V-07 测） | §1.2；C L38 |
| **V7 埋点四字段** | 支持 v0 埋点（C 四字段）；约束：只记结构量（graph_style/node_degree/radius_px/zoom/edge_id），不记内容（C P1/P2） | C L20/L235；KG 本体 D-KG-07 |
| **V8 毛球零新增字段** | 反对"依赖 node.group"；改用 degree/边密度/标签数（均现有量，无需 group）；**零新增字段**结论可保留、依据要换 | §4 D-O2；union §5 |

---

## 6. §8 跨场发现（collector vs kb_build）对学习场景意味着什么

D 的发现（union L262-L280：`get_graph_data()`→`collect_graph_data` 404 边 / 9 字段，`kb_build` 454 边）**修正了 KG 辩论 C4 的归因**（从"快照不同"改为"两条后端函数"）。从学习场景看，这意味着：

1. **"图"与"检索/agent 的解释"可能基于不同事实源**：图 UI 用 collector（404），而 KB 构建/知识包侧用 kb_build（454）。当用户问"为什么这两块相关"时，图与 agent 的解释可能不一致 ⇒ 学习决策（先学什么/为什么相关）被两个数字撕裂。
2. **学习场景验收必须绑定路径**：我 Phase 1 的 T1/T2/T4 任务数字、C 的 V-01 正确率，都必须注明"基于 collector 404 边"；否则跨路径比较无意义。
3. **v0 建议（新增，供裁）**：在可视化数据入口暴露 `graph_source: collector|kb_build` 元数据（只读），并在导出/图 UI 的"关于数据"里显示；**不新增业务字段**，只是元数据标签。
4. **对 V3 的影响**：degree 若进 collector，必须与"路径冻结"绑定（D-O3），否则学习场景的"枢纽"数字会随路径漂移。

**撤回条件**：若两条路径在 degree/edges 上实测等价（同冻结语料 454=404 通过去重/多 target 解释），则本条降为"无实际影响"，仅作元数据建议。

---

## 7. unknowns / not_doing（M3 更新）

### unknowns（新增/更新）
- **U-1 判读实验未做**：3px/4px/12 档均无本项目实测（我认领实验设计，C/A 认领执行；Phase 4 前若无人做 ⇒ V2 只能裁"待测"）。`if_true_then`：若实测相邻档识别率 <80%，v0 回落到 2 档。
- **U-2 空间记忆未做用户研究**：V-07 指标存在但无埋点；v0 只有"会话内稳定"，跨会话持久化收益未知。`if_true_then`：若 V-07 ≤1.5× ⇒ 持久化撤销。
- **U-3 chars vs 行跨度**：46× vs 3.1× 的口径差未实测哪个更贴近"阅读成本"。`if_true_then`：若相关 >0.95 ⇒ 用行跨度即可。
- **U-4 双路径对用户的影响未测**：collector/kb_build 差异是否可被用户感知（图与解释不一致）——未做用户研究。
- **U-5 3D 等大后"度数颜色"可辨性**：A 未给 3D 颜色档可辨数据（只给成本）；若颜色不可辨，3D 度数编码也无效。

### not_doing（本轮明确）
- 不再主张 v0 12–13 档；不再主张 3D 大小差异化；不再主张 v0 跨会话持久化；不把内容体量作为 v0 size 默认；不做用户研究（成本高，转交判读实验/A/B 任务）；不自行改 `src/**`。

---

## 8. 证据索引（供 Phase 4 复核）

```
ev:file:artifacts/agent/verify/debate/kgviz/PHASE2-UNION.md#L88-L107,L176-L202,L262-L295
ev:file:artifacts/agent/verify/debate/kgviz/PROPOSAL-render-perf.md#L39,L43-L44,L58,L63,L69,L103
ev:file:artifacts/agent/verify/debate/kgviz/PROPOSAL-metrics-baseline.md#L20,L32,L38,L84-L90,L96-L100,L235
ev:file:artifacts/agent/verify/debate/kgviz/PROPOSAL-arch-contract.md#L24-L25,L42,L101,L127-L145,L244-L246
ev:file:artifacts/agent/verify/debate/kgviz/PROPOSAL-todo-owner.md#L13-L17,L31,L47,L61-L62,L79-L82
ev:file:docs/design/kg-ontology-v0.md#L131-L138（D-KG-07 禁用判据=验收判据）
ev:file:src/memoria/ui/static/app/js/graph-view-2d.js#L611,L632
ev:file:src/memoria/ui/static/app/js/graph-layout-2d.js#L37-L51,L244-L246
ev:file:src/memoria/ui/static/app/js/graph-settings.js#L38
ev:file:src/memoria/graph/collector.py#L61-L70
ev:bench:kgviz-b-phase1（脚本 sha256 7013715c9ab47ca13c8e11ee0d97a92106af9ce4a40a80eac04f9bcfd5d7acc3：chars 707–32,847；degree 桶 12；Union-Find 120/133=90.2%；cards 67/133）
ev:file:docs/example/AAA_Vocab/plan/exam-2026-11-07.md#L11-L19
```
