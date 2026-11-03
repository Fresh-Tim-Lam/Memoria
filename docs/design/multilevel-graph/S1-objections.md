# S1 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；**上游冻结** `S0-terms-v1.md`（sha `241b1e1e…`）+ `S0-FREEZE-RECORD.md`；`S1-charter.md`。
> **对象**：`S1-dimensions-proposal-A.md`（主办研究，sha **`58d6d4f633f24d4fc4db7b9f2d56da4e354bc167938a685999db00040a7f2289`**，54,205 B）与 `S1-dimensions-proposal-B.md`（本复核方，sha **`9947dd7aad6864a1aaa2692592c45e6351ecb058310ca96af899d27cdca04341`**，33,553 B）。
> **独立性**：B 于 18:47:19 落盘，A 于 18:50:44 落盘；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0 冻结条款。

---

## 0. A/B 差异总表（S1-1..S1-15；逐项可对照）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与工程判断 |
|---|---|---|---|
| S1-1 维度定义 | M1 可计算/M2 非粒度/M3 非风格/M4 非模式/M5 有注册/M6 不改事实；排除 graphStyle/2D/3D/full_expand/level | 定义 + 最小字段 + 排除清单（graphStyle/2D/3D/full_expand/edge type） | **A 更强**（M1–M6 判定条件完整）；B 应吸收 M1–M6。证据：A S1-1（`graph-settings.js:38`、`graph-view-2d.js:617`）；B S1-1。 |
| S1-2 注册表 | 完整 JSON schema：basis 对象、`hop_unit`、priority、registry_sha、active 集合固定 `{hierarchy,association}`；reserved 专用 basis | 字段 schema 较简：basis 字符串、无 hop_unit/registry_sha/active-set 硬约束；H `relation_sources=[]` | **A 更强**（可机检字段更全）；B 缺 hop_unit/registry_sha/active 集合（P2，见 §3）。**关键差异**：H 的 relation_sources（A 含 min 作上下文边；B 为 []，H 不参与 E_relation）。证据：A S1-2；B S1-2。 |
| S1-3 开放槽位 | reserved 格式含 draft（关系源/方向/hop/termination/evidence_needed/why_not_v1）；R1–R5 规则 | reserved 格式 + 四要件；无 draft 子结构 | A 更细（draft/why_not_v1 强）；B 够用。建议合并 A 的 draft 字段。 |
| S1-4 H 定义 | H 只沿 `contain(structural)` 下降；H.relation_sources ⊇ E_relation_min，其余源作"可见端点上下文边"；hop=1 层 | H.relation_sources=[]；H 的簇→子块边为派生边，必须带 `data_edge_ids`；hop=1 层 | **B 更强**（R-3 data_edge_ids）；**A 更强**（context 边语义）；A 的 S1-4 与 S1-12 对 H 是否显示非 contain 边自相矛盾（P1-1）；B 的 H=[] 需说明与 R-1 的关系（P2）。 |
| S1-5 A 定义 | A=relation_neighborhood；E_relation(A)=min+extensions；按边计跳；含 U-10 三类表；不改变基座 | 同；B 的 E_relation(A) 明写 ⊇ min；关系源含 U-10 三类；标签不作开关 | 基本一致；A 的 U-10 关系源表更显式；B 的"凡 E_relation(A) 可挂接"表述更硬。并集。 |
| S1-6 E_relation 扩展 | 三类分类（edge_type/projection/derived）+ E1–E7；删除=重开 S0；验证器+版本 | 五要件（数据承载/可复算/分类/不破坏 H/A/U/审计）；只增断言 `new ⊇ old`；删除=重开 S0 | **A 更细**（分类/准入）；**B 有历史版本 diff 断言**（A 只有当前 min⊆；历史 append-only 机检不足，P1-2）。并集。 |
| S1-7 跳数 | hop_unit=level/edge；H=level-hop、A=edge-hop；C1–C6；跨维重置；预算 rule_id | 沿边计数、去重、hop_default/hop_max、跨维重置、节点预算分离 | A 更完整（hop_unit 字段）；B 缺 hop_unit（P2）。核心一致。 |
| S1-8 方向 | 5 枚举 `down/up/both/out/in`；H=down、A=both/out/in；方向不改事实 | 4 枚举 `down/out/in/both`（无 up）；H=down、A=both；方向不改事实 | A 多 `up` 保留值；B 更小集。两者语义一致；建议 v1 保留 up 但声明未用（A）或删除（B）需 Lead 定。 |
| S1-9 终止 | stop = leaf ∨ hop_max ∨ max_nodes ∨ frontier∅ ∨ cancel；leaf_required/stop_on_no_new；rule_id | 至少一有限界；hop/node/fixpoint/leaf/no_edges；termination_reason | A 更细（leaf_required/stop_on_no_new）；B 结构等价。并集。 |
| S1-10 组合 | 单维度 + combination 槽位格式 + `DIM_COMBINATION_UNSUPPORTED` fail-closed | 单维度 + 组合槽位 + 切换语义；无明确组合错误码 | A 多错误码；B 多切换语义。并集。 |
| S1-11 状态机 | `reserved→active→deprecated`；允许 deprecated 经重开 S1 回 active；插件不得自注册 | 三状态表；deprecated→active **禁止（必须重开 S1）**；插件只读 | 实质等价（都需 S1 重开）；A 更细（插件能力面/持久化）；B 更严格措辞。 |
| S1-12 维度与 present | 详细 H/A shown 公式；presence/rule_id；维度不改变类型 | 同；维度只改 ctx/E_relation；不改事实；R-3 聚合 | A 更细，但 **H shown 只 contain 与 S1-4 的 context 边矛盾（P1-1）**；B 简洁一致。 |
| S1-13 UI/导航 | 切换属 Presentation/S5；VM 只带 dimension_id；Renderer 无切换事件 | 同；VM 只带 dimension_id；S5 API | 一致；A 更细（S5 接口/历史）。 |
| S1-14 agent | frame() 纯函数 + request + fail-closed + 显式 fallback 审计 | 确定性服务 + request schema + 不改渲染；无 fallback | A 更细（审计/fallback）；B 更严格（无静默 fallback）。建议采纳 A 的审计 + B 的 fail-closed（fallback 仅显式参数且审计）。 |
| S1-15 候选 | 5 个：time/evidence/task/controversy/authorship | 8 个：+similarity/path/contrast/density | B 覆盖更广（U-12），但 `density` 属 S2 结构/视觉、`similarity` 是新增派生关系源（须过 S1-6）、`path/contrast` 需新语义类型；A 更保守。建议 **B 的 8 个中剔除 density，其余保留**；A 可加 similarity/path 为 reserved。 |

**总判断**：A 在注册表 schema/状态机/agent/终止/H 定义细节上更强；B 在 H 的 data_edge_ids、E_relation 历史只增断言、S1-2 简洁性、候选维度覆盖上更强。**按议项并集，不整份择优**。

---

## 1. 异议（按严重度；P0=违反 S0/原话，P1=冻结前必须裁决，P2=可冻结但后续场次补）

### P1-1（A）H 的 `relation_sources`/context 边在 S1-2、S1-4、S1-12 三处自相矛盾

- **议项**：S1-2 / S1-4 / S1-12（H；R-1/R-3）。
- **异议**：A 的 S1-2 校验要求所有 active 维度 `relation_sources ⊇ E_relation_min`（含 H）；S1-4 说 H 只沿 `contain(structural)` 下降，但**其余关系源若端点均可见可作"层内上下文边"显示**；S1-12 的 H 规则形式化写 `H: shown(e) ⇔ e.type=contain(structural) …`，**同一段括号又写"其余源仅当两端均可见作上下文边"**（A L661-662）。三处冲突：形式化 iff 排除 context 边，括号和 S1-4 又允许；S1-2 强制 relation_sources ⊇ min 使 context 边成为合法候选。H 是否显示 reference/extend 上下文边没有唯一结论。
- **反例**：H 视图中有两个端点均可见的 `reference` 边：按 S1-4 应显示为 context 边；按 S1-12 形式化 `iff contain` 不显示、但同段括号又允许；按 S1-2 校验 reference 又在 relation_sources 中（合法候选）。同一输入三种读法，无法机检唯一视图（违反 S1 章程预注册判据 1）。
- **可行动修复**：二选一并写死：
  (a) H **不参与 E_relation**：`H.relation_sources=[]`，H 的块→子块派生边用 `data_edge_ids` 映射（B 的做法）；R-1 只约束 basis=relation_expansion 的维度。或
  (b) H 参与 E_relation：`H.relation_sources` 固定为 `{contain(structural)}`（仅下降源），context 边另开字段 `context_relation_sources`（不得混入 relation_sources），并把 S1-12 的 H shown 规则改为"contain(structural) 下降边 + context 边（label 非 semantic）"。
  推荐 (a)（最贴 S0：H=划分/层次，A=E_relation 关系扩展；R-1 本义只约束 A），并在 S1-4 补 `data_edge_ids`（R-3）。
- **严重度**：S1 冻结前必须消除；否则 H 无法唯一实现 ⇒ **P1（冻结阻断）**。

### P1-2（A；B 需补历史校验）`E_relation` 的"只增不删"机检不完整

- **议项**：S1-6（R-1）。
- **异议**：A 的校验只断言**当前 active 维度** `relation_sources ⊇ E_relation_min`；这只能防止删除 min 中的源，**不能检出"删掉此前已新增的非 min 源"**（例如 v1.1 新增 `co_citation`，v1.2 删除它但仍 ⊇ min ⇒ A 的 validate 通过，违反"只增不删"）。章程/任务明确要求"是否真的只增不删且可机检"；A 只在文字里说"删除必须重开 S0"，没有把历史版本 diff 写成可执行断言。B 的 S1-6 有 `set(new) ⊇ set(old)` 断言，但 B 未定义历史 registry 的存储/加载（旧版保留只说了一句）。
- **反例**：registry v1.0 有 `{min..., co_citation}`；v1.1 删除 `co_citation`，current 仍 ⊇ min ⇒ A validator PASS；无历史 diff 检查 ⇒ R-1 未被机检。
- **修复**：S1 冻结 `registry_history`（旧版 registry/内容 sha 不可删除）；校验器增加 `assert set(new.relation_sources) >= set(old.relation_sources)` 且 `E_relation_min` 不变；删除/改名任何源 ⇒ `S0_REOPEN_REQUIRED`；CI 跑跨版本 diff。
- **严重度**：R-1 是 S0 冻结硬约束；不补则 S1 可静默删源 ⇒ **P1（冻结阻断）**。

### P1-3（A/B 共同）H 的 hop 语义与 S0-5「一跳 = 恰好一条 E_relation 边」不一致

- **议项**：S1-7 / S1-4（U-11；S0-5 冻结）。
- **异议**：A 和 B 都把 H 的 hop 定义为**层偏移**（`hop_unit=level`，H 一次下一层），但 S0-5 冻结文字是"当前视图只挂接**恰好一条 `E_relation(D)` 边**的邻居；跨维度重置"。H 的"下一层"不是数据 `E_relation(D)` 的一条边，而是划分派生关系；把 H 的层步叫 hop 会与 S0-5 的机检（`视图边数 ≤ |F| × hop_budget` / `hop=1 时不存在二跳边`）冲突。A 自己在 §17.1 把"H 是否算 hop"列为待裁，B 未识别。
- **反例**：H 视图 hop=1 时，块→子块边不是 DataSource 的 `E_relation(D)` 边（是聚合/派生边），S0-5 的"每条挂接边来自 E_relation(D)"在 H 上不成立；若按 S0-5 机检 H 会 FAIL。
- **修复**：Lead/SE 裁决二选一：
  (a) H **不使用 hop 预算**（H 只表达"一次下钻一层"，由 S5 导航动作推进，不是 S0-5 的 hop）；S1-7 明确"H 的 hop 不参与 S0-5 机检"；
  (b) H 的块→子块边视为 `contain(structural)` 的派生投影（`data_edge_ids` 映射），`E_relation(H)={contain(structural)}`，S0-5 的"边"按投影后数据边计；这要求 S1-2 H relation_sources 固定 contain structural（对 P1-1 的选项 b）。
  推荐 (a)：H 是导航层次，不是关系跳；S0-5 只约束 A。必须在 S1 冻结前写死，避免 H 实现按 hop 预算被 S0-5 判违规。
- **严重度**：与 S0 冻结条款一致性 ⇒ **P1（冻结阻断）**。

### P1-4（A）H 的派生边未声明 `data_edge_ids`（R-3）

- **议项**：S1-4（R-3）。
- **异议**：A 的 S1-4 定义 H 的块→子块边，但未写它们必须携带 `data_edge_ids`；S0 R-3 冻结要求聚合/折叠边必须能映射回 DataSource 边。H 的父子块边是聚合边，缺映射则 `expand_data_edges(VM) ⊆ DataSource.edges` 无法验证。
- **反例**：H 的 cluster→child 边无 data_edge_ids；S0 R-3 机检无法通过；S0-8 default⊆full 无法投影。
- **修复**：S1-4 明确 H 派生边 `data_edge_ids` 指向其成员 KP 的 `contain(structural)` 数据边（或直接列出成员 KP canonical id + 边 id）；B 已写（S1-4/S1-12）。
- **严重度**：R-3 硬约束 ⇒ **P1（冻结前）**。

### P2 清单

| # | 项 | 异议/证据 | 修复 |
|---|---|---|---|
| P2-1 | B 的 S1-2 缺 `hop_unit`、`registry_sha`、active 集合固定 | B registry 无法机检 H/A 的 hop 单位/内容完整性；A 有 | B 吸收 A 字段（hop_unit/registry_sha/active set） |
| P2-2 | B 的 H `relation_sources=[]` 与 R-1 的关系未写清 | 读者会问"R-1 只约束 A 吗" | B 在 S1-2 注明 R-1 作用域=relation_expansion；H 不参与 |
| P2-3 | B 的 S1-15 候选含 `density`（S2 结构/视觉）与 `similarity`（派生源需 S1-6） | 把非维度候选混入 U-25 槽位；`density` 不应作维度 | B 剔除 density；similarity/path 标 reserved + 需 S1-6 准入 |
| P2-4 | A 的 S1-8 `up` 枚举是否保留 | S0 冻结 dir 枚举/方向；`up` v1 无 active 使用 | Lead 决定保留（未用）或删除；写清机检 |
| P2-5 | A 的 S1-15 候选只有 5 个，B 有 8 个 | A 可能漏 similarity/path 等 U-12 候选 | 并集：A 增加 similarity/path（reserved），B 剔 density |
| P2-6 | A 的 S1-11 `deprecated→active` 允许（重开 S1），B 禁止直接转 | 状态机语义需统一 | Lead 选 A（重开 S1 后允许）或 B（禁止，必须新维度 id） |
| P2-7 | A 的 S1-14 允许 `fallback=true` 显式回退 H；B 不允许 fallback | S0-10 agent 不得静默替换；显式 fallback 可审计（A 有 audit），但需确保不是默认 | 合并：仅显式参数 + 审计；默认 fail-closed |
| P2-8 | A/B 的 `termination.max_nodes` 默认值/归属 | A 例 200、B 无值；S8 定数值，S1 冻结"必须有穷" | S1 冻结结构，S8 定值；写清 |
| P2-9 | A 的 S1-2 `active` 集合固定为 `{hierarchy,association}`，B 未固定 | 防未来偷偷 active | B 吸收 A 的 active set 断言 |
| P2-10 | A/B 的 `view_family` 与 S0 R-2 一致性 | H 使用 `(level, view_family)`；维度切换不改 view_family | 在 S1-4/S1-13 明写"维度不改变 view_family/level"（A/B 均需补） |

---

## 2. 点名审查项结论

1. **A 维是否完整覆盖 U-10（包含/引用/语义关联）**：A S1-5 关系源表与 B 均覆盖 `contain(structural)`、`contain(semantic)`、`reference`、`extend`，且 `E_relation(A) ⊇ E_relation_min`；**A 未窄化，PASS**。需保留 A 的 U-10 三类表，B 的"A 不改变 H 基座"。
2. **`E_relation` 只增不删是否可机检**：A 当前仅"当前 ⊇ min"（**不足**，见 P1-2）；B 有 `new ⊇ old` 断言但缺历史 registry 存储。**需补历史 diff 机检才 PASS**。
3. **H/A 注册表 fail-closed**：A S1-2 校验完整（未知/保留/弃用、active 集合、hop/termination），B 较简；**A 更强，B 需补 active set/registry_sha**。A 的 H relation_sources 自相矛盾（P1-1）。
4. **跳数/方向/终止可机检**：A 有 hop_unit/终止/方向；B 有 termination/方向；但**H hop 与 S0-5 不一致（P1-3）**；节点预算 A 的 `max_nodes` 有，B 有 termination max_nodes；方向 A 含 up，B 无 up；**大致可机检，需裁 H hop**。
5. **维度是否被塞进 ViewModel**：A/B 都明确 ViewModel 只带 dimension_id 标签、无切换/mode/capabilities；**PASS**（A S1-13/B S1-13）。B 更严格无 fallback；A 的 fallback 是请求参数层面，不进 VM。
6. **v1 单维度 vs 组合槽位双真相**：A/B 都 v1 单维度 + 组合 reserved；A 有 `DIM_COMBINATION_UNSUPPORTED`，B 有切换语义；**PASS**，但需统一错误码/切换接口。
7. **reserved 是否被偷偷实现**：A/B 都写 reserved 不进渲染/ctx；A 有 R1–R5 + draft 隔离，B 有四要件；**PASS**；需 CI grep reserved id 分支。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1 H 的 relation_sources/context 边自相矛盾**：A 的 S1-2/S1-4/S1-12 对 H 是否显示非 contain 边给出三种结论；必须在冻结前二选一（推荐 H 不参与 E_relation、relation_sources=[]，H 派生边带 data_edge_ids；或 H 固定 `{contain(structural)}` + context 边另立字段），否则 H 无法唯一机检。
2. **P1-2 E_relation 只增不删的机检不完整**：A 只校当前 ⊇ min，无法检出删除此前新增的非 min 源；须补 registry 历史/跨版本 diff 断言（B 的 `new⊇old` 方向正确但需历史存储），否则 R-1 可被静默绕过。
3. **P1-3 H 的 hop 与 S0-5 冲突**：S0-5 冻结"一跳=恰好一条 E_relation(D) 边"，A/B 都把 H 的层偏移当 hop；须裁 H 不参与 hop 预算（推荐）或将 H 的块边投影为 contain(structural) 数据边并固定 `E_relation(H)={contain(structural)}`；否则 H 实现会被 S0-5 机检判违规。

> 另有 P1-4（A 的 H 派生边缺 `data_edge_ids`，R-3）也应同轮修；P2 清单可后续场次补。

---

## 4. 结论

- **A/B 均覆盖 S1-1..S1-15，无 P0**；A 在注册表 schema/状态机/agent/终止/H 定义细节更强，B 在 H 的 R-3 数据边、E_relation 版本只增断言、候选维度覆盖更强。
- **A 当前不能直接冻结**：P1-1（H 三种结论）、P1-2（E_relation 只增机检不足）、P1-3（H hop 与 S0-5 不一致）、P1-4（H 派生边缺 data_edge_ids）须修；B 需补 hop_unit/registry_sha/active-set 与 H/R-1 作用域说明。
- 差异已逐项列出，未静默合并；未写产品代码/契约，未 commit。

> 参考锚：S0 冻结 `S0-terms-v1.md:35-41,49-61,75-107`；U-10 `vision:27,47`；graphStyle 现状 `graph-settings.js:38`、`graph-view-2d.js:617`；`ENGINEERING-PLAN.md:149-173,216-247,301-345`。
