# S7 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S7-RULINGS.md`（sha `4067b810…`，R-S7-1..R-S7-6）+ `S6-ADDENDUM-1.md`（sha `f9918dfd…`）。
> **对象**：`S7-agent-proposal-A-v2.md`（主办研究，sha **`605f0032cc9ec2a270e309d9bed0a1cc6cf459d1675a36d0e0d80d5f99eb5118`**，26,868 B）与 `S7-agent-proposal-B-v2.md`（本复核方，sha **`8c1ada3426f9783d5b15437a9702b48a7104091c7d76ad2cb1888792740064e3`**，17,299 B）。
> **性质**：B-v2 以 R-S7 为依据独立修订，完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S7-RULINGS/S0–S6。

---

## 0. R-S7 关闭矩阵

| 裁决 | A-v2 | B-v2 | 判定 |
|---|---|---|---|
| R-S7-1 `graph_resolve_ref` 只读/审计/DataSource | 5 工具含 resolve_ref；返回 resolved/kp/file/line/anchor/stale/claim_type；走 DataSource/索引 | 同 | **关闭** |
| R-S7-2 edges 只 shown + summary + explain | ViewResponse.edges 只 shown；suppressed_summary/rule_histogram；explain 受控 | 同 | **关闭** |
| R-S7-3 5 snake_case 工具/无 path/错误表 | 5 工具；无 path/query；错误表逐码映射 S6+ADDENDUM-1 | 同工具/无 path；错误表 6+部分 S6 码 | **基本关闭**：B 错误表少于 A（缺 `GRAPH_INPUT_INVALID` 等，P2-3） |
| R-S7-4 字段统一 | view_model_id/frame_id(审计)/aggregate_count/member_count | 同 | **关闭** |
| R-S7-5 幂等/expand 无 nav/写 forbidden | 幂等键 `(tool,args,edition,budget)`；expand 不改 nav；写 forbidden | 同 | **关闭**（但工具 args 无 edition 输入，见 P1-1） |
| R-S7-6 默认/G7/S9-S10 | 4000/200；G7 引用 G6；S9/S10 边界 | 同 | **关闭** |

**结论**：R-S7-1/2/3/4/5/6 两版已基本关闭；**无 P0**；剩余 P1 为工具/引用层语义缺口（edition、source_assertion 内容）与 B 表/字段吸收（P2）。

---

## 1. A-v2 / B-v2 逐项差异（S7-1..S7-12）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S7-1 定位/读路径 | 只读；AgentQuery；不直读 DataSource/文件/缓存；S10 写 | 同 | 一致；B 需明确 `kb_id` 多 KB（P2-3）。 |
| S7-2 可见层 | ViewResponse：view_model_id/frame_id(审计)、nodes/edges(shown)、clusters[]、suppressed_summary/rule_histogram、aggregate_count | AgentView：view_model_id/frame_id、nodes/edges(shown)、summary；缺 `clusters[]` 与部分字段 | A 更完整；**B 缺 `clusters[]`/SummaryResponse schema（P2-3）**。 |
| S7-3 查询 | 5 工具：focus/explain/expand/summary/resolve_ref；无 path/query | 同 5 工具；无 path/query | 一致；B 工具输入缺 `kb_id`（A 有；P2-3）。 |
| S7-4 token/截断 | 4000/200；summary 优先；truncated/omitted；suppressed_summary | 同 | 一致；SummaryResponse 字段未冻结（P2-4）。 |
| S7-5 工具/错误/幂等 | 5 工具 snake_case；错误表 11+；幂等 `(tool,args,edition,budget)`；audit | 5 工具；错误表 13 类但缺 `GRAPH_INPUT_INVALID` 等；幂等同 | A 更全；B 表需吸收 A/S6（P2-3）；**工具 args 无 edition 输入（P1-1）**。 |
| S7-6 写边界 | 无写；S10；GRAPH_WRITE_FORBIDDEN | 同 | 一致。 |
| S7-7 引用 | claim_type；resolve_ref 解析；anchor/run/key；unknown | 同 | 一致；**resolve_ref 无 source excerpt（P1-2）**。 |
| S7-8 S9 | S7 消费；S9 candidate/recall；错误传播；no_semantic | 同 | 一致；S9 candidate schema 归 S9（P2-5）。 |
| S7-9 S10 | S10 写；edition stale；刷新 | 同 | 一致。 |
| S7-10 多维度/多归属 | 默认 H/A 显式；memberships | 同 | 一致。 |
| S7-11 失败/降级 | no_semantic/预算/数据/unknown/stale 显式 | 同 | 一致。 |
| S7-12 G7 | G7 引用 G6；指标/audit | 同 | 一致；阈值 S8（P2-6）。 |

---

## 2. 仍需解决的 3 点

### P1-1（A/B）工具 args 无 `edition` 输入，幂等键 `(tool,args,edition,budget)` 无法由调用方确定

- **现状**：R-S7-5 冻结幂等键 `(tool,args,edition,budget)`；A-v2/B-v2 工具 schema 均为 `{kb_id?, level/view_family/dimension/focus/... budget}`，**没有 `edition`/`expected_edition` 参数**；`edition_sha` 只在 ViewResponse/Audit 返回。同一 `(tool,args,budget)` 在 S10 写后或数据刷新后可能解析到不同 edition；调用方无法 pin edition，幂等键无法复算；stale 处理也不确定（用当前 edition 还是 expected）。
- **反例**：调用 `graph_focus{level,focus,budget}` 在 edition A 与 edition B 下同名参数；返回不同结果但幂等键中的 edition 由服务端隐式取当前值，客户端无法预知/复现；缓存/重试可能混 edition。
- **修复**：工具 schema 增加 **`edition`（可选，pin）或 `expected_edition`**；响应/审计带回 `edition_sha`；未传时服务端使用当前 edition 并在响应/meta 明示；幂等键用实际 edition；edition 不匹配 ⇒ `GRAPH_EDITION_STALE`；机检同键同结果/跨 edition 显式失败。A/B 统一。
- **严重度**：幂等/引用/缓存正确性 ⇒ **P1（冻结前）**。

### P1-2（A/B）`graph_resolve_ref` 只返回 ref 元数据，无 source_assertion 内容，S7-7 的 `source_assertion` 无法由工具契约落地

- **现状**：R-S7-1 冻结 `graph_resolve_ref` 输出 `{resolved,kp_id,file,line,anchor,stale,claim_type}`；A-v2/B-v2 照此实现。但 S7-7 要求 `claim_type=source_assertion` 的 claim 必须带原文断言（`kp_id+file+line/anchor`）；resolve_ref 只校验/解析引用，**不返回任何原文片段/断言内容**；S7-1 禁止 agent 直接读文件/DataSource raw。因此 agent 只能“引用位置”而无法“引用原文断言”，S7-7 的 source_assertion 只能靠 prompt 外部上下文/不可验证记忆，契约不闭合。
- **反例**：agent 回答“原文说 X”，refs 只有 file/line；无法通过工具确认 line 内容是否为 X；直接读文件违反 S7-1；引用完整率可算但“内容一致性”不可验。
- **修复**（二选一）：① `graph_resolve_ref` 增加**有界 `source_excerpt`/`quote`**（例如 ≤500 字符、含 offset/anchor、stale 标记、隐私/版权约束）；② 把 `source_assertion` 限定为“agent 外部已持有原文 + ref 仅定位”，并明确 S7 不保证断言内容、G7 记 `source_verified=false`；推荐①，且 excerpt 只读、审计、不缓存正文。A/B 统一。
- **严重度**：引用/证据契约核心 ⇒ **P1（冻结前）**。

### P2-3（B）B 工具/ViewResponse 缺 `kb_id`、`clusters[]`/SummaryResponse schema，错误表少于 A/S6

- **现状**：A-v2 5 工具均含 `kb_id`；ViewResponse 含 `clusters[]`；SummaryResponse 有 schema；错误表含 `GRAPH_INPUT_INVALID` 等 S6 码。B-v2 工具 schema 无 `kb_id`（多 KB 边界无法路由）；ViewResponse 无 `clusters[]`（S7-4 摘要无载体）；SummaryResponse 未定义字段/失败码；错误表缺 `GRAPH_INPUT_INVALID` 等。
- **影响**：多 KB/摘要/错误映射不完整，S7 工具契约与 S6 不一致；B 需吸收 A 的字段/错误表与 `kb_id`。
- **修复**：B-v2 吸收 A 的 `kb_id` 参数、`clusters[]`/SummaryResponse schema、完整错误表（S6+ADDENDUM-1）；SummaryResponse 定义 `{clusters[{cluster_id,run_id,cluster_key,label,member_count,coverage}], counts, data_state, truncated}`。
- **严重度**：B 契约完整性 ⇒ P2（冻结前可补）。

> 其他 P2：SummaryResponse schema（A/B 均需冻结）；S7 token budget 到 S4 `max_nodes/max_edges` 映射；S9 candidate_ref 归 S9；S10 刷新/人工确认；G7/G6 字段关系；G7 阈值/隐私 S8；path 未来显式 `allow_two_hop` 另开修订；kb_id/edition 多 KB 边界。

---

## 3. 点名审查结论（v2）

1. **只读边界/是否绕 DataSource/写 sidecar**：A/B **PASS**（5 只读工具；AgentQuery；无写；`GRAPH_WRITE_FORBIDDEN`；不读文件/缓存/sidecar）。
2. **可见层是否把 VM/缓存当事实**：A/B **PASS**（VM 派生；事实回 DataSource/refs）；A clusters[] 更全；B 缺 clusters[]（P2-3）。
3. **查询是否复用 S4 focus-only/S5 导航/无隐式 2 跳**：A/B **PASS**（focus F={focus} hop=1；expand 一层；无 path/query；无隐式 2 跳）。
4. **explain/expand 语义**：A/B **PASS**（explain_edge 受控解释 suppressed；expand 不递归/不改 S5 nav）。
5. **token/静默截断/unknown/suppressed**：A/B **PASS**（4000/200；truncated/omitted；edges 只 shown；suppressed_summary/rule_histogram；unknown≠无）。
6. **工具 schema/`GRAPH_*`/幂等/审计**：A **PASS**（5 工具/错误表/幂等/audit）；B 基本 PASS，错误表需吸收 A（P2-3）；**edition 入参 P1-1**。
7. **引用契约可机检**：A/B 有 resolve_ref/claim_type；**source_assertion 内容 P1-2**；kp/file/line/cluster_key/run_id 可机检。
8. **S9/S10 边界（不夹带）**：A/B **PASS**（S9 候选/召回；S10 写；S7 只读；edition stale）。
9. **多维度/多归属**：A/B **PASS**（显式 dim/family；memberships；不合并；默认 H）。
10. **失败降级**：A/B **PASS**（no_semantic/预算/数据/unknown/stale 显式；不编造；`GRAPH_*`）。
11. **指标/G7**：A/B **PASS**（G7 引用 G6；不复制事实；阈值 S8）。

---

## 4. 最严重 3 条 / 结论

1. **P1-1（A/B）工具无 edition 入参**：幂等键 `(tool,args,edition,budget)` 无法由调用方复算；需 `edition/expected_edition`、响应/审计回带、stale 映射；否则跨 S10 写/刷新行为不确定。
2. **P1-2（A/B）resolve_ref 无 source_assertion 内容**：S7-7 `source_assertion` 只能引用位置、不能验证原文；需有界 excerpt 或收紧 source_assertion 并记 `source_verified=false`；否则引用契约不闭合。
3. **P2-3（B）缺 kb_id/clusters[]/SummaryResponse/错误表**：B 需吸收 A 的多 KB 路由、摘要载体、完整错误表（S6+ADDENDUM-1）；否则 B 契约不完整。
- 两版**无 P0**；R-S7-1..6 基本关闭；A-v2 更完整，B-v2 需补上述 P2；P1-1/P1-2 为**两版共同**契约缺口，冻结前必须补。未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：R-S7 `S7-RULINGS.md:18-41`；S6-ADDENDUM-1；A-v2 S7-2/S7-3/S7-5/S7-7；B-v2 S7-2/S7-3/S7-5/S7-7。
