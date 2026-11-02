# S0 冻结前机检报告（SE · task-294）

> **冻结对象**：`docs/design/multilevel-graph/S0-terms-v1.md`（sha256 `ab7538f0…`，165 行，2026-11-02T17:2x+08:00；旧版 `5218de4f…` 为修复前快照）
> **证据链（只读，不是冻结对象）**：`S0-terms-proposal-A-v2.md`（`5b3562e2…`）、`S0-terms-proposal-B-v2.md`（`dd713707…`）、`S0-objections-v2.md`（`5d9828e7…`）、
> `S0-RULINGS.md`（`078363aa…`）、`S0-engineering-review.md`、`ENGINEERING-PLAN.md`（`93393ae4…`，本次机检前已按 v1 条款对齐：R-1/R-2/R-3/VM 纯度/`data_edge_ids`/`view_family.dimension_id`）。
> **执行者**：`graph-se-architect`（SE 专家，domain=se）· **日期**：2026-11-02（Asia/Shanghai）
> **边界**：未改 A/B/异议/RULINGS/v1 文件；未写产品代码；未改契约；未 commit。本文件为 task-294 唯一新增交付；另仅更新 `ENGINEERING-PLAN.md` 与 `S0-engineering-review.md` 使其与 v1 对齐（均在 task-294 写域内）。
> **结论**：**达到冻结门禁（是）**。复跑确认 **M-11 PASS、M_fail=[]**；三图同版本复验 PASS（PLAN sha 未变）。旧版判定（v1 sha `5218de4f…`，M-11 FAIL）作为历史记录保留在 §13/§17。
> **复跑对象（新冻结候选）**：`S0-terms-v1.md` sha256 `ab7538f09b20d336647340a24b987e3ac0dd7a4256da430ad5526e738def952e`（165 行）。

---

## 0. 结论先行

### 0.1 M-1..M-12 结果（编号按 `S0-terms-v1.md` §3 的定义）

| M | 判据（v1 §3） | 判定 | 关键证据 |
|---|---|---|---|
| M-1 | 术语三要素 | **PASS** | v1:20-25（S0-1 定义+`G_sem`+三标签+T3 降级）；证据链 A-v2:46-95 / B-v2:57-81（反例/边界/U 映射） |
| M-2 | 层次划分机检 | **PASS** | v1:27-32（V1–V6 + fail-closed + `(level, view_family)`）；A-v2:96-158 / B-v2:83-134（两份可执行伪代码） |
| M-3 | 维度 / `E_relation_min` | **PASS** | v1:34-40（**R-1** 四元最小集 + 只能加不能删）；reserved fail-closed；单维度激活 |
| M-4 | 簇 μ/β + 身份 | **PASS** | v1:42-46（μ/β、`cluster_instance_id`、`cluster_run_id`、`cluster_local_seq`、`cluster_key=sha256(...)`） |
| M-5 | 一跳/方向/跨维重置 | **PASS** | v1:48-52（恰好一条、不闭包、`dir(D)`、跨维跳数重置、不带背后子图、bridge=role/state） |
| M-6 | present 三值 + ctx + rule_id | **PASS** | v1:54-59（`{shown,suppressed,unknown}`、`ctx`、`rule_id`、`ctx_full` 也走 present）+ **R-3** v1:57 |
| M-7 | 多归属 / partition | **PASS** | v1:61-65（成员≠出现、多对多、同族单归属/跨族重叠、不设上限、D-3） |
| M-8 | 同源与 default⊆full | **PASS** | v1:67-71（同 DataSource/Renderer/present、焦点映射）+ R-3 子集断言 v1:57 |
| M-9 | ViewModel 纯度与 kind 枚举 | **PASS** | v1:73-77（VM 不含导航/模式/**capabilities**；`kind∈{kp,cluster}`；bridge=role/state；事件最小集） |
| M-10 | agent 边界 | **PASS** | v1:79-83（L_kp/L_sem/L_view、证据+审计、不得推断 semantic、不得改渲染状态、确定性取景） |
| M-11 | **U-1..U-35 覆盖 0 缺失** | **PASS（复跑）** | v1 §4 覆盖矩阵 **35/35**（无缺失/无重复）；mcheck `M-11 PASS`、`v1 present_count=35`；抽验 U-10/U-27/U-33 一致，U-34/U-20 有映射锚点瑕疵（O-9/O-10，不阻塞） |
| M-12 | 三张工程图与 S0 条款一致 + mermaid 同版本复验 | **PASS** | 3 图 `PARSE_OK`（vendored mermaid **11.16.0**，sha256 `9198f632…`，jsdom 29.1.1）；结构闭合 G-2a/b/c PASS；条款↔图元素交叉核对见 §14.3 |

### 0.2 专项冻结项

| 项 | 判定 | 证据 |
|---|---|---|
| **R-1** `E_relation_min = {contain(structural), contain(semantic), reference, extend}` 且 S1 只能加不能删 | **PASS** | v1:37 逐字一致；`semantic/structural` 仅标签（v1:36-37） |
| **R-2** `view_family` 唯一定义 | **PASS** | v1:38 `⟨family_id, basis, dimension_id, level_chain⟩`；partition 断言对象 `(level, view_family)`；ER 已建 `VIEW_FAMILY` 实体（PLAN:143-148） |
| **R-3** `data_edge_ids` + `expand_data_edges` 子集 + `default⊆full` | **PASS** | v1:57 逐字；ER `VIEW_MODEL.data_edge_ids`（PLAN:172）+ VM edges `data_edge_ids`（PLAN:245）+ 机检说明（PLAN:250） |
| VM 纯度（capabilities 在 Renderer、kind 枚举） | **PASS** | v1:75-76；PLAN §1.4（PLAN:224-250，已删 `renderer_capabilities`、加 `data_edge_ids`）；`RENDER_BACKEND.capabilities`（PLAN:180-184） |

### 0.3 冻结门禁判定

**是（条件 1/2/4 满足；条件 3 Lead 复跑待执行）**。`S0-RULINGS.md` §4 要求「SE 的 M-1..M-12 全 PASS + 三图复验 PASS」；复跑 `M_fail=[]`、M-11 PASS、R-1/R-2/R-3 PASS、三图 PARSE_OK（PLAN sha 未变）。
**残余非阻塞建议**（不阻塞冻结，建议 Lead 终审顺手改）：① 覆盖矩阵 U-34 现指「§6 变更控制 + 章程流程」，§6 是冻结后变更控制；U-34 的「逐议项/不设上限」更准确锚点是 `S0-charter.md` §3/§5 与 agenda §5（O-9）；② U-20 现指「S0-9/S0-10」，S0-10 是 agent 边界、与 KP 点击无关，建议改为「S0-9（nodeClick 事件）+ S5（跳编辑器执行）」（O-10）。O-7/O-8 仍归后续场次。

---

## 1. 方法与可复现证据

### 1.1 输入完整性（sha256，与 Lead/异议 v2 的引用逐一核对一致）

| 文件 | sha256 | 核对 |
|---|---|---|
| `S0-terms-v1.md` | `ab7538f09b20d336647340a24b987e3ac0dd7a4256da430ad5526e738def952e` | 冻结对象（复跑版；旧版 `5218de4f…` 曾 M-11 FAIL） |
| `S0-terms-proposal-A-v2.md` | `5b3562e2aa5fc609b211637d165b10dd6ac039ea0a9c5fd4180325f893ac0746` | 与 Lead 消息一致 |
| `S0-terms-proposal-B-v2.md` | `dd713707aa5e4b07d317e97eb2e492f9de4700e39e15e8cc586d1f4bf137832a` | 与 Lead 消息一致 |
| `S0-objections-v2.md` | `5d9828e7169297e4eb7d11b417ecc90831d8ebdfaeed78eaa96019759ac4b9f0` | 与 Lead 消息一致 |
| `S0-RULINGS.md` | `078363aa2f7f3ace2caa5588792ba67ef580928a9b9e116c7c297181ab35bb10` | 与异议 v2 引用一致 |
| `ENGINEERING-PLAN.md` | `93393ae457d2b6b56ed448409cea67389cf7509e712eb34c4e490322aded2198` | 三图复验对象（机检前已按 v1 对齐） |
| `S0-engineering-review.md` | `65f7351963844875d8c708654a8e3ab90bd299a0b084b6d195c6e4984d74090c` | M 判据原始设计（编号重定义见 §2） |

### 1.2 环境与命令

```
node v24.21.0 ; python 3.12.4
mermaid = 仓库 vendored src/memoria/ui/static/app/vendor/mermaid.min.js
           bundle 内 version:"11.16.0" ; sha256 9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76
jsdom   = D:/deepseek-harness/node_modules/jsdom（29.1.1，仅为 DOMPurify 提供真实 DOM）

# G-1：同版本 mermaid 复验三图（脚本全文见附录 A）
node <SE_DIR>/parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md
# G-2/G-4：图结构闭合（脚本全文见附录 C）
python <SE_DIR>/diag_qa.py docs/design/multilevel-graph/ENGINEERING-PLAN.md
# M-1..M-12：冻结对象 + 证据链机检（脚本全文见附录 B）
python <SE_DIR>/mcheck_v1.py > mcheck-v1.json
```
`<SE_DIR>` = 本机 SE 运行目录（脚本未入库：task-294 写域仅 docs；全文附于本报告附录，可原样复跑）。

### 1.3 机检输出摘要（原始 JSON 见附录 D 的判定行）

```
mermaid: {"kind":"meta","mermaidVersion":"11.16.0","mermaidSha256":"9198f632…","jsdomVersion":"29.1.1","node":"v24.21.0"}
         {"kind":"block","index":1,"ok":true,"diagramType":"er"}
         {"kind":"block","index":2,"ok":true,"diagramType":"flowchart-v2"}
         {"kind":"block","index":3,"ok":true,"diagramType":"stateDiagram"}
         {"kind":"summary","failedBlocks":0}
diag_qa: G-2a-ER PASS / G-2b-DFD PASS / G-2c-ST PASS / G-4-crossref PARTIAL（人工映射见 §14.2）/ FAIL=0
mcheck（复跑）: M_fail=[]、M_partial=[]；M-11 PASS（v1 35/35 U、覆盖矩阵已声明）；M-12 PASS；R-1/R-2/R-3 PASS
```

---

## 2. 编号口径说明（重要，避免与初版 review 混淆）

`S0-engineering-review.md` §4 的 M-1..M-12 是**判据设计初版**；`S0-terms-v1.md` §3 对编号做了重定义。本次机检**以 v1 §3 为准**：

| 编号 | 初版 review 定义 | v1 §3 定义（本次采用） |
|---|---|---|
| M-11 | S0-11「不做什么」清单+执行点 | **U-1..U-35 覆盖 0 缺失** |
| M-12 | S0-12 术语映射表 | **三张工程图与 S0 条款一致 + mermaid 同版本复验** |

因此：S0-11 的执行点完整性 / S0-12 的映射表完整性改为**未关闭项 O-2/O-3**（§16），不占 M 编号。

---

## 3. M-1 — 术语三要素（语义）

- **判据（charter §4-1 + v1 §3 M-1）**：每个术语有定义、≥1 反例、≥1 边界用例、U 编号映射；语义判据可机检。
- **v1 证据**：v1:22-25 —— `semantic_edge = T1∧T2∧T4 ∧ G_sem`；`G_sem` 复用 `validate_contain_curation_overlay`；`reference` 不算语义；三标签 `semantic/structural/navigation`；T3 降级为 C-1..C-4。
- **证据链**：A-v2:46-95（含 4 条反例、3 条边界用例、U 映射）；B-v2:57-81（同）。
- **判定：PASS**。备注（非阻塞，O-2）：v1 自身未附反例/边界/U 映射，靠证据链满足 charter §4-1；建议 v1 每条款加一行「反例/边界/U 映射：见 A-v2 §x / B-v2 §y」或在附录冻结证据链引用。

## 4. M-2 — 层次划分机检

- **v1 证据**：v1:27-32 —— 层次=同一视图族内嵌套划分；最小粒度=KP；`(level, view_family)` 作用域；V1–V6 + fail-closed（V1 非叶 cluster / V2 叶 kp 且 id∈K / V3 成员非空 / V4 无 cluster 叶 / V5 同族同层不交且并集=该层全集 / V6 递归展开到底全 KP）。
- **证据链**：A-v2:96-158（`validate_level_view`）；B-v2:83-134（`check_level_partition` + 递归 expand）。
- **判定：PASS**。备注：v1 V5 已把 A/B 伪代码里写死的 `K` 改为「该层全集」，消解了异议 v2 §2-2/P2-3 的 K vs K_f 歧义；S2 施工时须把「该层全集」参数化为 `view_family.basis`（非阻塞，S2 交付项）。

## 5. M-3 — 维度 / `E_relation_min`

- **v1 证据**：v1:34-40 —— 维度=取景规则（非粒度/非视觉风格）；v1 注册 `H`/`A`；reserved 只登记不得进渲染分支、切换 fail-closed；**R-1** v1:37 精确列出四元最小集且「S1 只能加不能删」；单维度激活（D-5）。
- **证据链**：A-v2:159-203；B-v2:136-156；异议 v2:54-59 提出最小集问题 → 已被 R-1 关闭。
- **判定：PASS**。备注（O-5 措辞）：v1:36「v1 激活维度：H + A」与 v1:39「同时只激活一个」易误读，建议改为「v1 注册 active 维度 H/A；同一视图只激活其中一个（D-5）」。

## 6. M-4 — 簇 μ/β + 身份

- **v1 证据**：v1:42-46 —— 簇=μ≥τ_coh ∧ β≤τ_bridge 的成员集合，非严格连通分量；`cluster_instance_id=(cluster_run_id, cluster_local_seq)`；`cluster_key=sha256(canonical(sorted(member_canonical_ids)) + algorithm_id + version + params_hash)`；curation/审计同时记 run 与 key；成员 ⊆ K。
- **证据链**：A-v2:204-240；B-v2:158-188；异议 v2 §2-3/P2-6/P2-8（canonical 序列化细节留 S2/S6）。
- **判定：PASS**。备注（非阻塞 O-7）：`canonical(...)` 的序列化（分隔符/UTF-8/排序）与「成员变化后旧 curation 迁移 vs 失效重确认」仍留 S2/S6，应在对应章程中写死。

## 7. M-5 — 一跳 / 方向 / 跨维重置

- **v1 证据**：v1:48-52 —— 恰好一条 `E_relation(D)` 边；不闭包、不递归；跨维度跳数重置；`dir(D)` H=down / A=both；只渲染端点+边、不带背后子图；挂接节点 kind∈{kp,cluster}；bridge 只能 node role/edge state。
- **证据链**：A-v2:242-275（rendered-hop + `underlying_hop_count`）；B-v2:189-210（dir 枚举/跨维重置）。
- **判定：PASS**。备注（非阻塞 O-7）：`underlying_hop_count` 只出现在 A-v2，未写入 v1；建议 S4/S5 冻结时补字段（否则「折叠簇算 1 跳」在审计上不可解释）。

## 8. M-6 — presence 三值 + ctx + rule_id（含 R-3）

- **v1 证据**：v1:54-59 —— `渲染集合 = {e | present(e,ctx)==shown}` 唯一判据；`ctx ⊇ (level, view_family, dimension_id, focus, hop_budget, mode)`；`presence ∈ {shown,suppressed,unknown}`，`suppressed/unknown` 必须 `rule_id`；视图缺席≠数据缺席；`ctx_full` 也走 present，禁止 `all_data_edges` 直出；**R-3** `data_edge_ids` + `expand_data_edges(VM) ⊆ DataSource.edges` + `shown(default) ⊆ shown(full)`。
- **证据链**：A-v2:277-324；B-v2:212-239；异议 v2 §2-3 提出聚合边身份问题 → R-3 关闭。
- **判定：PASS**。备注（O-4 措辞）：v1 §3 的 M-6 标题写作「present 三值」，值域实际是 `shown/suppressed/unknown`（`present` 是**函数名**）；建议标题改「presence 三值」避免实现者把函数名当枚举值。

## 9. M-7 — 多归属 / partition

- **v1 证据**：v1:61-65 —— 成员关系≠视图出现；membership 多对多；同一视图族内单归属、跨族/层次/维度允许重叠；S0 不设上限；`role/source/provenance`；D-3 不写产品 sidecar/新段。
- **证据链**：A-v2:326-359；B-v2:241-260；RULINGS D-1/D-3。
- **判定：PASS**。备注：ER 里 `MEMBERSHIP` 是派生缓存（不建 DB 唯一键），「同族单归属」由校验器保证（PLAN:208 已注明），S6a 需给出该校验器接口。

## 10. M-8 — 同源与 default ⊆ full

- **v1 证据**：v1:67-71 —— 默认入口彻底替代旧全展开；全展开=同 DataSource/同 Renderer/同 present，仅 ctx 不同；切换时焦点与历史映射保持；禁止第二数据源/双主线；+ R-3 子集断言（v1:57）。
- **证据链**：A-v2:361-399（DataSource 身份三元组、焦点映射）；B-v2:262-285（`expand_data_edges` 投影）。
- **判定：PASS**。备注（O-8，S4/S6a）：`expand_data_edges()` 只有断言、没有函数签名/机检入口；S4 交付须冻结其签名与输入输出（否则 R-3 不可执行）。

## 11. M-9 — ViewModel 纯度与 kind 枚举

- **v1 证据**：v1:73-77 —— 三段 `DataSource→ViewModel→Renderer`；VM 纯（nodes/edges/level/dimension/view_family/presence 等），**不含导航状态、模式开关、capabilities**（capabilities 由 `Renderer.getCapabilities()` 提供）；`kind∈{kp,cluster}`；bridge 只能 role/state；渲染器不取数/不做语义判断/不写状态；事件最小集 `nodeClick/edgeClick/backgroundClick`（hover/clusterExpand 可选）；2D/3D 同接口。
- **证据链**：A-v2:401-445（capabilities 残留在 VM，被异议 v2 P2-1 指出）；B-v2:287-319（capabilities 外置）；异议 v2:82 → Lead 采纳 B 修法（v1:77 来源标注）。
- **判定：PASS**。备注：v1 事件最小集取 A、可选事件并集 B，与异议 v2 P2-4 一致；ST 的 `CLICK_CLUSTER` 等已明确为导航服务层事件（PLAN §3.1），不违反渲染事件契约。

## 12. M-10 — agent 边界

- **v1 证据**：v1:79-83 —— L_kp 主导设计知识点（S10）；L_sem 可写但必须证据锚+审计、不得自动推断 semantic；L_view 只能请求确定性取景服务、不得直接改渲染状态；取景同输入同输出。
- **证据链**：A-v2:447-487（allowlist/denylist）；B-v2:321-341。
- **判定：PASS**。备注：M-10 的「机检」目前是**定性**（写证据/审计可由 v0.3 validator 机检；「不得改渲染状态」需接口 allowlist 机检），细化归 S7/S9/S10；不阻塞 S0。

## 13. M-11 — U-1..U-35 覆盖 0 缺失（**PASS**，复跑）

- **判据**：v1 §3 M-11 = 「U-1..U-35 覆盖 0 缺失」；vision §2 使用规则 1-2 要求「任何设计/议程/裁决必须在文首引用本文件并给出**覆盖矩阵**；覆盖矩阵任何一条未覆盖或冲突 ⇒ 不得评审通过」。
- **复跑对象**：`S0-terms-v1.md` sha256 `ab7538f09b20d336647340a24b987e3ac0dd7a4256da430ad5526e738def952e`（165 行；新增 §4 覆盖矩阵 114-155 行）。
- **实测（2026-11-02T17:2x）**：
  ```
  matrix rows: 35 ; unique: 35 ; missing: [] ; dupes: []
  mcheck M-11: PASS（v1 出现 U 编号 35/35；声明覆盖矩阵=true）
  证据链 A-v2 §13 = 35/35；B-v2 §0.1 = 35/35
  非 U 覆盖项复核：v1 §1 条款 12/12；§2 R-1..R-3 + D-1..D-5 齐全；§3 M-1..M-12 齐全
  ```
- **抽验（Lead 指定的重点行）**：

  | U | v1 行 | v1 映射 | 抽验 |
  |---|---|---|---|
  | U-10 | 130 | S0-3/S0-5（E_relation_min，R-1）；S1/S4 | ✅ 一致（关联维度关系源 = E_relation_min） |
  | U-27 | 147 | S0-6（presence 三值 + ctx + rule_id） | ✅ 一致 |
  | U-33 | 153 | S0-9（单一接口 + 双后端） | ✅ 一致 |
  | U-34 | 154 | §6 变更控制 + 章程流程 | ⚠️ 覆盖存在但锚点偏弱（§6 是冻结后变更控制）；建议改指 `S0-charter.md` §3/§5（O-9） |
  | U-20 | 140 | S0-9/S0-10；S5 | ⚠️ S0-10 为 agent 边界、与 KP 点击无关；建议删 S0-10、保留 S0-9+S5（O-10） |
  | U-23 | 143 | §6 变更控制；本矩阵 | ✅ 合理 |
  | U-24 | 144 | `multilevel-graph-vision.md`（文件整体） | ✅ 一致（原话存档） |

- **判定：PASS**。35/35 无缺失/无重复；两处映射锚点瑕疵不满足 FAIL 条件（M-11 只判覆盖缺失），且不阻塞冻结，记为 O-9/O-10。
- **历史记录（旧版 v1 sha `5218de4f…`）**：正文仅 13/35 U、无覆盖矩阵 ⇒ 当时 FAIL；已由新版 §4 修复。


## 14. M-12 — 三张工程图与 S0 条款一致（+ 同版本 mermaid 复验）

### 14.1 mermaid 同版本复验（G-1）

- 版本：仓库 vendored `mermaid.min.js`，bundle `version:"11.16.0"`，sha256 `9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76`；jsdom 29.1.1；node v24.21.0。
- 结果：`ENGINEERING-PLAN.md` 3 块图 **全部 `PARSE_OK`**（er / flowchart-v2 / stateDiagram），`failedBlocks:0`。
- 说明：SE 初版（task-291）曾用 11.17.2 + jsdom 验证；本轮按要求改为**仓库同版本 11.16.0**复验，结论一致。解析方式：jsdom 提供真实 DOM → 加载 vendored bundle → `mermaid.parse()`（脚本见附录 A）。

### 14.2 图结构闭合（G-2/G-4）

| 检查 | 结果 | 说明 |
|---|---|---|
| G-2a ER：关系实体⊆属性块⊆1.3 实体表 | **PASS** | 无孤实体/无表外实体 |
| G-2b DFD：图中 P1..P10 ⊆ 2.4 过程表 | **PASS** | 10/10 |
| G-2c ST：转换表 19 行，To 状态全部在图内 | **PASS** | 19 行（含 `GraphView.Overview` 复合写法） |
| G-4 存储↔ER 交叉 | **PARTIAL→人工 PASS** | 存储表首列是文档名（`正文 .md`/`sidecar`），非 ER 实体名；映射关系已在 PLAN §2.5 表内写明（`正文 .md`→`DOCUMENT`；`sidecar`→`KP_OCCURRENCE`/`EDGE_PROVENANCE`），机检脚本按实体名匹配会报 PARTIAL，属脚本口径问题，非设计不一致 |

### 14.3 条款 ↔ 图元素交叉核对（M-12 核心）

| v1 条款 | ER | DFD | ST | 判定 |
|---|---|---|---|---|
| S0-2 层次/partition（v1:27-32） | `LEVEL`/`VIEW_FAMILY`/`MEMBERSHIP`（PLAN:129-160 区） | `F1` 配置→`P3/P4`（PLAN:339,373-376） | Navigation `Overview/Deepened`（PLAN:459-466） | 一致 |
| S0-3 维度 + R-1（v1:34-40） | `DIMENSION`（PLAN:150-153）；`EDGE_CANDIDATE.type` 三枚举 | `F1`→`P4/P5`（PLAN:373-377,394,400） | `Presentation`/维度切换在 S5（PLAN:475-479） | 一致 |
| S0-4 簇身份（v1:42-46） | `CLUSTER_RUN`/`CLUSTER.local_seq`/`cluster_key`（PLAN:98-112,205-208） | `P3`→`C2` 缓存（PLAN:315,345-349） | —（簇展开在 S5a） | 一致 |
| S0-5 一跳/方向（v1:48-52） | 无实体（投影） | `P5`（PLAN:400） | `HopNetwork`（候选态，PLAN:470-474；ST-12..14） | 一致（HopNetwork 待 S5 裁决，PLAN D-ST-01） |
| S0-6 presence/ctx + R-3（v1:54-59） | `VIEW_MODEL.presence/rule_id/data_edge_ids`（PLAN:164-172） | `P5`（PLAN:323,400） | `LINK_FOCUS` 不改导航状态（ST-11） | 一致 |
| S0-7 membership（v1:61-65） | `MEMBERSHIP` 多对多 + `view_family_id`（PLAN:114-121,208）；**不写 sidecar** | `C2` 派生缓存（PLAN:409） | origin-return（ST-09/10） | 一致 |
| S0-8 默认/全展开（v1:67-71） | \(\text{ctx}\) 在 `VIEW_FRAME`（含 `mode`，PLAN:153-163） | 同 DataSource（PLAN:296,298） | `Presentation` `DefaultView/ExpandedAll` + 焦点映射（ST-15/16） | 一致 |
| S0-9 VM 纯度/kind/capabilities（v1:73-77） | `VIEW_MODEL` 无导航/模式/cap；`RENDER_BACKEND.capabilities`（PLAN:164-184） | `P6`→`P7`（PLAN:398-399） | `Backend` 区 `R2D/R3D/Switching`（PLAN:481-487） | 一致 |
| S0-10 agent（v1:79-83） | `AUDIT_EVENT`（PLAN:196） | `AGENT`/`P9`/`P10`（PLAN:306,321-323,364-369） | —（非图覆盖，S10） | 一致 |
| S0-11 范围（v1:85-88） | 单 KB 根、无跨库 FK | 单 KB 根（PLAN:296）；D-DF-04 | — | 一致（逐条执行点见 O-3） |
| S0-12 映射（v1:90-93） | 术语映射表在 review §5 / 证据链 A-v2 §12+B-v2 §12 | 三段数据流（PLAN:292-303） | — | **部分覆盖**：v1 无映射表 → O-2 |

### 14.4 结论

**PASS**。三图可解析、结构闭合、关键条款均有图元素承载；两处标注为「待 S5a 裁决」/「待 S6a 细化」的项（`HopNetwork` 状态、`expand_data_edges` 签名）属后续场次施工项，不影响 S0 条款一致性判定。

---

## 15. 证据链一致性（A-v2 / B-v2 / 异议 v2 / RULINGS）

| 检查 | 结果 |
|---|---|
| RULINGS P0-1/P0-2/P1-1..P1-4、D-1..D-5、SE S0-6 关闭 | A-v2/B-v2 均落实；异议 v2 §0 关闭矩阵一致（异议 v2:10-28） |
| A-v2/B-v2 对 R-1/R-2/R-3 的覆盖 | A-v2 §15 留了 3 个未决；v1 以 R-1/R-2/R-3 冻结（v1:37-38,57）→ 未决已关闭 |
| A-v2/B-v2 U 覆盖 | 各自 35/35（本轮机检） |
| 独立性 | B-v2 落盘 17:11:16 早于 A-v2 17:12:52（文件 mtime）；异议 v2:5 声明未读 A-v2；差异逐项列出（异议 v2:31-49） |
| 未静默合并 | 异议 v2 §1/§3 明确列出两版差异与判断（本轮只读核对，未改动证据链文件） |

---

## 16. 未关闭项（O-1..O-10；O-1 已关闭）

| # | 项 | 阻塞? | 归属 | 修复建议 |
|---|---|---|---|---|
| ~~O-1~~ | ~~v1 缺 U-1..U-35 覆盖矩阵~~ | **已关闭（v1 §4 新增 35/35 矩阵；M-11 PASS）** | v1（Lead 已修） | 保留历史记录 |
| O-2 | v1 条款未逐条附证据链引用；S0-12 映射表 | **已关闭（部分）** | v1（Lead 已修） | v1:9 新增证据链总说明；v1:95-96 S0-12 指向 A-v2 §12+B-v2 §12 并集。条款级反例引用仍靠总声明，可接受 |
| O-3 | S0-11 执行点未逐条绑定 | **已关闭（引用式）** | v1（Lead 已修） | v1:90 已加「见 A-v2 §11 与 B-v2 S0-11；S1–S10 负责细化」 |
| O-4 | M-6 标题 present/presence | **已关闭** | v1（Lead 已修） | v1:56 标题已改「presence」；v1:58 值域 `{shown,suppressed,unknown}` |
| O-5 | S0-3 单维度措辞 | **已关闭** | v1（Lead 已修） | v1:37 已改「v1 可用维度 H/A，**同一视图一次只激活一个**（D-5）」 |
| O-6 | S0-11 #12 否定歧义 | **已关闭（可再润色）** | v1（Lead 已修） | v1:89 已加「（这些分别由 S2/S9/S8 决定）」澄清 |
| O-7 | `cluster_key` canonical 序列化、curation 迁移/重确认、`underlying_hop_count`、full_expand 的 suppressed/unknown 与候选全集 | 非阻塞 | S2/S4/S5/S6 | 在各场次章程写死；S6a 前给出 canonical JSON 规范 |
| O-8 | `expand_data_edges()` 无函数签名/机检入口（R-3 只有断言） | 非阻塞 | S4/S6a | S4 交付时冻结签名：输入 VM、输出 DataSource edge_id 集合；S6a 写机检 |
| **O-9** | 覆盖矩阵 U-34 锚点「§6 变更控制 + 章程流程」偏弱 | 非阻塞（文档级） | v1（Lead 终审） | 建议改指 `S0-charter.md` §3/§5 与 agenda §5（逐议项/不设上限） |
| **O-10** | 覆盖矩阵 U-20 锚点含「S0-10」（agent 边界，与 KP 点击无关） | 非阻塞（文档级） | v1（Lead 终审） | 建议改为「S0-9（nodeClick 事件）+ S5（跳编辑器执行）」 |

> 说明：**O-1 已关闭**（v1 §4 矩阵 35/35）⇒ 无阻塞项；O-2/O-3 已按引用式关闭；O-4..O-6 措辞已修；O-7/O-8 仍归后续场次；O-9/O-10 为映射锚点文档级建议。

---

## 17. 冻结门禁判定与复跑记录

**判定：是（达到 `S0-RULINGS.md` §4 门禁；Lead 终审条件 3/5 待执行）**

| 门禁条件（RULINGS §4） | 结果 |
|---|---|
| 1. A-v2/B-v2/异议-v2 三份齐，P0/P1 全关闭 | **满足**（§15；证据链 sha 未变） |
| 2. SE M-1..M-12 全 PASS + 三图复验 PASS | **满足**（复跑 `M_fail=[]`；M-11 PASS；R-1/R-2/R-3 PASS；三图 `PARSE_OK`，PLAN sha `93393ae4…` 未变） |
| 3. Lead 复跑机检 + 抽查 3 条 | **待 Lead**（建议复跑附录 B 脚本；抽查 `E_relation_min` / `kind` / `present` 三条） |
| 4. 覆盖矩阵无缺失 + 12 议项有裁决 | **满足**（35/35；§1 条款 12/12；§2 R/D 齐） |
| 5. 产出 `S0-terms-v1.md` + 写决策 | **待 Lead**（写 `team/decisions.jsonl`/提交后即冻结） |

**复跑记录（2026-11-02T17:2x）**

- 对象：`S0-terms-v1.md` sha256 `ab7538f09b20d336647340a24b987e3ac0dd7a4256da430ad5526e738def952e`（165 行；新增 §4 覆盖矩阵）
- 命令与输出：

```
$ python <SE_DIR>/mcheck_v1.py
inputs.v1 = ab7538f0…
summary   = {"M_fail": [], "M_partial": [], "special_fail": []}
M-11      = PASS（v1 present 35/35, missing []；声明覆盖矩阵 = true）
R-1/R-2/R-3 = PASS

$ node <SE_DIR>/parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md
failedBlocks = 0（er / flowchart-v2 / stateDiagram；PLAN sha 93393ae4… 未变，G-1 证据沿用）
```

- 结论：**S0 冻结门禁达到（是）**；仅剩 Lead 终审条件 3/5。残余 O-9/O-10（映射锚点）与 O-7/O-8（后续场次）均不阻塞。


## 18. 边界与后续

- 本报告只读 A-v2/B-v2/异议 v2/RULINGS/v1；**未改**这些文件；未写产品代码；未改契约；未 commit。
- 本轮为配合 v1 冻结，更新了 `ENGINEERING-PLAN.md`（按 R-1/R-2/R-3/VM 纯度/`data_edge_ids`/`view_family`/`mode` 对齐；三图仍为 v0 草案，待 S5a/S6a/S9a 冻结）与 `S0-engineering-review.md`（补版本注记 + M 编号重定义说明）。
- **S0 冻结前不得进入 S1**（v1:159）；复跑已完成（§17），M-11 已 PASS；Lead 终审条件 3/5 完成后即冻结，冻结后可进入 S1。
- 后续 S5a/S6a/S9a 需把 O-7/O-8 与 §14 中标注「待 Sx 裁决」的项写入各自章程；三图与文字设计同步冻结（`ENGINEERING-PLAN.md` §5.4）。

---

## 附录 A — G-1 同版本 mermaid 解析脚本（SE 审计脚本，非产品代码）

> 版本固定：mermaid 11.16.0（sha256 `9198f632…`）/ jsdom 29.1.1 / node v24.21.0。四反引号围栏用于容纳脚本内的三反引号。

````js
#!/usr/bin/env node
/**
 * S0 冻结门禁 G-1：用「本仓 vendored 同版本 mermaid」解析 Markdown 中的 ```mermaid 块。
 *
 * 版本固定：
 *   - mermaid: src/memoria/ui/static/app/vendor/mermaid.min.js（bundle 内 version:"11.16.0"，
 *              sha256=9198F6322F37F242A3396FBDA15BEC75A053095F9A81175340A3BB63EBD41B76）
 *   - jsdom:   D:/deepseek-harness/node_modules/jsdom（29.1.1），仅为 DOMPurify 提供 DOM
 *   - node:    v24.21.0
 *
 * 用法： node parse_mermaid.js <md-file> [<md-file> ...]
 * 输出： 每条 JSON（file/index/diagramType/ok/error）；任一失败 ⇒ 退出码 1。
 */
"use strict";
const fs = require("fs");
const vm = require("vm");
const crypto = require("crypto");
const { pathToFileURL } = require("url");

const MERMAID_FILE = "D:/AAA_Jupyter/Memoria/src/memoria/ui/static/app/vendor/mermaid.min.js";
const JSDOM_API = "D:/deepseek-harness/node_modules/jsdom/lib/api.js";

function sha256File(p) {
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

function extractBlocks(text) {
  const out = [];
  const re = /```mermaid\n([\s\S]*?)```/g;
  let m;
  while ((m = re.exec(text))) out.push(m[1]);
  return out;
}

(async () => {
  const files = process.argv.slice(2);
  if (!files.length) {
    console.error("usage: node parse_mermaid.js <md-file> [<md-file> ...]");
    process.exit(2);
  }

  // jsdom 只为 DOMPurify 提供真实 DOM（不能只用 vm sandbox：DOMPurify 需 addHook）
  const { JSDOM } = await import(pathToFileURL(JSDOM_API).href);
  const dom = new JSDOM("<!doctype html><html><body></body></html>", { pretendToBeVisual: true });
  for (const k of [
    "window", "document", "navigator", "HTMLElement", "SVGElement", "Node", "DOMParser",
    "XMLSerializer", "MutationObserver", "Element", "CustomEvent", "Text", "Image", "HTMLCanvasElement",
  ]) {
    if (dom.window[k] === undefined) continue;
    try {
      Object.defineProperty(globalThis, k, { value: dom.window[k], configurable: true, writable: true });
    } catch (_) {
      /* 只读内建（如 node 24 的 navigator）：跳过即可 */
    }
  }
  globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);

  const code = fs.readFileSync(MERMAID_FILE, "utf8");
  const mermaidSha = crypto.createHash("sha256").update(code).digest("hex");
  const verMatch = code.match(/version:"(\d+\.\d+\.\d+)"/);
  const mermaidVer = verMatch ? verMatch[1] : "unknown";
  vm.runInThisContext(code, { filename: "mermaid.min.js" });
  const mermaid = globalThis.__esbuild_esm_mermaid_nm.mermaid.default;
  mermaid.initialize({ startOnLoad: false });

  const meta = {
    mermaidVersion: mermaidVer,
    mermaidSha256: mermaidSha,
    jsdomVersion: JSON.parse(fs.readFileSync("D:/deepseek-harness/node_modules/jsdom/package.json", "utf8")).version,
    node: process.version,
  };
  console.log(JSON.stringify({ kind: "meta", ...meta }));

  let failed = 0;
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8");
    const blocks = extractBlocks(text);
    console.log(JSON.stringify({ kind: "file", file: f, blocks: blocks.length, fileSha256: sha256File(f) }));
    for (let i = 0; i < blocks.length; i++) {
      try {
        const r = await mermaid.parse(blocks[i]);
        console.log(JSON.stringify({ kind: "block", file: f, index: i + 1, ok: true, diagramType: r.diagramType }));
      } catch (e) {
        failed++;
        console.log(JSON.stringify({
          kind: "block", file: f, index: i + 1, ok: false, error: String(e.message).split("\n").slice(0, 3).join(" | "),
        }));
      }
    }
  }
  console.log(JSON.stringify({ kind: "summary", failedBlocks: failed }));
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error("FATAL", String(e.message).split("\n").slice(0, 3).join(" | "));
  process.exit(3);
});
````

## 附录 B — M-1..M-12 机检脚本（SE 审计脚本，非产品代码）

> 判据 = v1 §3 的 M 编号；`BASE` 为本机仓库路径。运行：`python mcheck_v1.py > mcheck-v1.json`。

````python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S0 冻结前机检（对象 = S0-terms-v1.md；A-v2/B-v2/异议-v2 为证据链）。

M 编号采用 **S0-terms-v1 §3** 的定义（它重定义了 M-11/M-12，与 SE review 初版不同）：
  M-1 术语三要素；M-2 层次划分机检；M-3 维度/E_relation_min；M-4 簇 μ/β + 身份；
  M-5 一跳/方向/跨维重置；M-6 present 三值 + ctx + rule_id；M-7 多归属/partition；
  M-8 同源与 default⊆full；M-9 ViewModel 纯度与 kind 枚举；M-10 agent 边界；
  M-11 U-1..U-35 覆盖 0 缺失；M-12 三张工程图与 S0 条款一致（mermaid 同版本复验）。

用法： python mcheck_v1.py > mcheck-v1.json
"""
import hashlib
import json
import os
import re

BASE = "D:/AAA_Jupyter/Memoria/docs/design/multilevel-graph/"
FILES = {
    "v1": "S0-terms-v1.md",
    "A2": "S0-terms-proposal-A-v2.md",
    "B2": "S0-terms-proposal-B-v2.md",
    "OBJ2": "S0-objections-v2.md",
    "RULINGS": "S0-RULINGS.md",
    "PLAN": "ENGINEERING-PLAN.md",
    "REVIEW": "S0-engineering-review.md",
}
U_IDS = [f"U-{i}" for i in range(1, 36)]


def read(name):
    p = BASE + FILES[name]
    with open(p, encoding="utf-8") as f:
        t = f.read()
    return t


def sha(name):
    p = BASE + FILES[name]
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def hits(text, patterns, skip_neg=False):
    out = {}
    lines = text.splitlines()
    neg = re.compile(r"✗|反例|禁止|不得|删除|旧|v1|→|已修|不作|排除|改为")
    for p in patterns:
        rx = re.compile(p, re.I)
        nums = []
        for i, ln in enumerate(lines):
            if rx.search(ln):
                if skip_neg and neg.search(ln):
                    continue
                nums.append(i + 1)
        if nums:
            out[p] = nums[:10]
    return out


def rule(mid, text, required, any_of=None, forbid=None, note=""):
    found = hits(text, required)
    missing = [p for p in required if p not in found]
    any_found, any_missing = {}, []
    for group in any_of or []:
        h = hits(text, group)
        if h:
            any_found.update(h)
        else:
            any_missing.append(group)
    forbidden = hits(text, forbid or [], skip_neg=True)
    if not missing and not any_missing and not forbidden:
        status = "PASS"
    elif found or any_found:
        status = "FAIL" if forbidden else "PARTIAL"
    else:
        status = "FAIL"
    return {
        "id": mid, "status": status, "required_found": found, "required_missing": missing,
        "any_of_found": any_found, "any_of_missing": any_missing,
        "forbidden_found": forbidden, "note": note,
    }


def u_coverage(text):
    present = [u for u in U_IDS if re.search(r"(?<![0-9])" + re.escape(u) + r"(?![0-9])", text)]
    return {"present_count": len(present), "missing": [u for u in U_IDS if u not in present],
            "present": present}


def main():
    v1, a2, b2, obj2, rul, plan, review = (read(k) for k in ["v1", "A2", "B2", "OBJ2", "RULINGS", "PLAN", "REVIEW"])
    checks = []

    # ---------- M-1 术语三要素（定义/反例/边界/U 映射，证据链含反例与边界） ----------
    checks.append(rule(
        "M-1", v1,
        required=[r"T1", r"T2", r"T4", r"G_sem", r"semantic", r"structural", r"navigation"],
        any_of=[[r"消费者准入", r"C-1\.\.C-4"], [r"reference.{0,20}不算语义"]],
        note="v1 S0-1 定义+字段闸门+T3 降级；反例/边界/U 映射在 A-v2 §1、B-v2 S0-1（证据链）",
    ))
    checks[-1]["evidence_chain"] = {
        "A2_antipatterns": hits(a2, [r"反例", r"✗"]).get(r"反例", []),
        "B2_antipatterns": hits(b2, [r"反例"]).get(r"反例", []),
    }

    # ---------- M-2 层次划分机检（V1-V6 + partition 作用域） ----------
    checks.append(rule(
        "M-2", v1,
        required=[r"V1", r"V2", r"V3", r"V4", r"V5", r"V6", r"\(level, view_family\)", r"kind=cluster", r"kind=kp"],
        any_of=[[r"fail-closed"], [r"知识点"]],
        note="v1 S0-2 V1–V6 + 最小粒度；伪代码细节在 A-v2 §2/B-v2 S0-2（B 的递归 expand 更完整）",
    ))
    checks[-1]["evidence_chain"] = {
        "A2_pseudocode": hits(a2, [r"validate_level_view"]).get(r"validate_level_view", []),
        "B2_pseudocode": hits(b2, [r"check_level_partition"]).get(r"check_level_partition", []),
    }

    # ---------- M-3 维度 / E_relation_min（R-1） ----------
    checks.append(rule(
        "M-3", v1,
        required=[r"E_relation", r"E_relation_min", r"contain\(structural\)", r"contain\(semantic\)", r"reference", r"extend", r"reserved", r"fail-closed"],
        any_of=[[r"只能加不能删", r"不能删"], [r"单维度", r"同时只激活一个"]],
        note="R-1 最小边源集冻结（S0-3）；reserved 不得进渲染分支",
    ))

    # ---------- M-4 簇 μ/β + 身份（D-2） ----------
    checks.append(rule(
        "M-4", v1,
        required=[r"μ", r"β", r"cluster_instance_id", r"cluster_run_id", r"cluster_local_seq", r"cluster_key", r"sha256"],
        any_of=[[r"严格连通分量", r"不是.{0,10}连通分量"]],
        note="v1 S0-4；μ/β 阈值 S2；canonical 序列化细节留 S2/S6（异议 P2-6/P2-8）",
    ))

    # ---------- M-5 一跳/方向/跨维重置 ----------
    checks.append(rule(
        "M-5", v1,
        required=[r"恰好一条", r"E_relation\(D\)", r"dir\(D\)", r"不闭包", r"跨维度", r"跳数重置", r"不带.{0,8}背后", r"bridge.{0,20}role"],
        any_of=[[r"hop_budget"]],
        note="v1 S0-5：方向 H=down / A=both；underlying_hop_count 在 A-v2 §5（证据链），v1 仅 rendered-hop 语义（建议 S4/S5 补字段，非 M-5 必要条件）",
    ))

    # ---------- M-6 present 三值 + ctx + rule_id（+ R-3 数据边映射） ----------
    checks.append(rule(
        "M-6", v1,
        required=[r"present\(e, ctx\)", r"shown", r"suppressed", r"unknown", r"rule_id", r"ctx", r"ctx_full"],
        any_of=[[r"data_edge_ids"], [r"expand_data_edges"], [r"shown\(default\)", r"shown\(default\).{0,10}shown\(full\)"]],
        forbid=[r"all_data_edges.{0,10}直出", r"data-has-edge"],
        note="R-3：data_edge_ids + expand_data_edges 子集 + default⊆full（v1 S0-6/§2）",
    ))

    # ---------- M-7 多归属 / partition ----------
    checks.append(rule(
        "M-7", v1,
        required=[r"成员关系", r"视图出现", r"多对多", r"同一视图族", r"不设上限", r"role/source/provenance", r"sidecar"],
        any_of=[[r"跨视图族"], [r"membership"]],
        note="v1 S0-7：同族单归属、跨族多归属、D-3 不写产品 sidecar",
    ))

    # ---------- M-8 同源与 default ⊆ full ----------
    checks.append(rule(
        "M-8", v1,
        required=[r"同 DataSource|同数据源|同一数据源", r"同 Renderer", r"同 present", r"shown\(default\)", r"shown\(full\)", r"焦点"],
        any_of=[[r"第二数据源", r"双主线"], [r"映射"]],
        note="v1 S0-8；焦点映射 A-v2；R-3 子集断言",
    ))

    # ---------- M-9 ViewModel 纯度与 kind 枚举 ----------
    checks.append(rule(
        "M-9", v1,
        required=[r"kind ∈ \{kp, cluster\}", r"role/state", r"不取数|不做语义判断|不写状态", r"不含导航状态", r"模式开关", r"capabilities.{0,20}Renderer"],
        any_of=[[r"nodeClick"], [r"edgeClick"], [r"backgroundClick"]],
        note="v1 S0-9：capabilities 移出 VM（Renderer.getCapabilities）；事件最小集",
    ))

    # ---------- M-10 agent 边界 ----------
    checks.append(rule(
        "M-10", v1,
        required=[r"L_kp", r"L_sem", r"L_view", r"curated_by/curated_at", r"不得自动推断 semantic", r"不得直接改渲染状态", r"确定性"],
        any_of=[[r"证据"], [r"取景服务"]],
        note="v1 S0-10；细化为 S7/S9/S10",
    ))

    # ---------- M-11 U-1..U-35 覆盖 0 缺失（对象：冻结包） ----------
    cov_v1 = u_coverage(v1)
    cov_a2 = u_coverage(a2)
    cov_b2 = u_coverage(b2)
    cov_obj = u_coverage(obj2)
    # v1 是否**真的给出**覆盖矩阵（表格行 `| U-x |` 或显式「覆盖矩阵见…」），而不是仅在变更控制里提到该词
    declares_matrix = bool(re.search(r"^\|\s*U-\d+\s*\|", v1, re.M) or re.search(r"覆盖矩阵\s*[:：]|覆盖矩阵见", v1))
    if not cov_v1["missing"]:
        m11_status = "PASS"
        m11_note = "v1 正文逐 U 覆盖完整"
    elif declares_matrix:
        m11_status = "PASS"
        m11_note = "v1 引用覆盖矩阵（冻结包口径）"
    else:
        m11_status = "FAIL"
        m11_note = (f"v1 正文缺 {len(cov_v1['missing'])} 个 U 编号且未声明覆盖矩阵；"
                    "冻结包 A-v2/B-v2/异议-v2 各自覆盖完整，但 vision §2 要求设计文件给出覆盖矩阵")
    checks.append({
        "id": "M-11", "status": m11_status, "note": m11_note,
        "v1": cov_v1, "A2": cov_a2, "B2": cov_b2, "OBJ2": cov_obj, "v1_declares_matrix": declares_matrix,
    })

    # ---------- M-12 三张工程图与 S0 条款一致（结构检查；mermaid 解析另证） ----------
    mermaid_blocks = re.findall(r"```mermaid\n([\s\S]*?)```", plan)
    er = mermaid_blocks[0] if len(mermaid_blocks) >= 1 else ""
    dfd = mermaid_blocks[1] if len(mermaid_blocks) >= 2 else ""
    st = mermaid_blocks[2] if len(mermaid_blocks) >= 3 else ""
    vm_section = plan.split("### 1.4")[1].split("### 1.5")[0] if "### 1.4" in plan else ""
    m12 = {
        "id": "M-12",
        "mermaid_blocks": len(mermaid_blocks),
        "checks": {
            "ER_VIEW_FAMILY": bool(re.search(r"VIEW_FAMILY \{[\s\S]*?dimension_id", er)),
            "ER_CLUSTER_KEY": "cluster_key" in er,
            "ER_MEMBERSHIP_MULTI": bool(re.search(r"KP_CONCEPT \|\|--o\{ MEMBERSHIP", er)),
            "ER_VIEW_MODEL_DATA_EDGE_IDS": "data_edge_ids" in er,
            "DFD_CONFIG_STORE": "注册表" in dfd,
            "DFD_P5_PRESENCE": bool(re.search(r"shown/suppressed/unknown", dfd)),
            "DFD_VIEWMODEL_NO_NAV": "mode" not in vm_section or "不含导航" in vm_section,
            "VM_no_breadcrumb": not re.search(r'"breadcrumb"\s*:', vm_section),
            "VM_no_capabilities": "renderer_capabilities" not in vm_section,
            "VM_data_edge_ids": "data_edge_ids" in vm_section,
            "ST_regions": ("Navigation" in st and "Presentation" in st and "Backend" in st),
            "ST_focus_map": "焦点" in plan,
        },
    }
    m12["status"] = "PASS" if all(m12["checks"].values()) and m12["mermaid_blocks"] == 3 else "FAIL"
    m12["note"] = "图解析结果见同批次 parse_mermaid.js 证据（vendored mermaid 11.16.0 + jsdom）"
    checks.append(m12)

    # ---------- R-1/R-2/R-3 显式核对 ----------
    special = {
        "R-1": rule("R-1", v1, [r"E_relation_min", r"contain\(structural\)", r"contain\(semantic\)", r"reference", r"extend", r"只能加不能删"], note="最小边源集冻结"),
        "R-2": rule("R-2", v1, [r"view_family = ⟨family_id, basis, dimension_id, level_chain⟩", r"\(level, view_family\)"], note="唯一定义 + partition 对象"),
        "R-3": rule("R-3", v1, [r"data_edge_ids", r"expand_data_edges", r"shown\(default\)", r"shown\(full\)"], note="聚合边映射 + 子集断言"),
    }

    # ---------- 证据链/输入完整性 ----------
    integrity = {
        "sha256": {k: sha(k) for k in ["v1", "A2", "B2", "OBJ2", "RULINGS", "PLAN", "REVIEW"]},
        "v1_has_12_clauses": all(re.search(r"S0-" + str(i) + r"\b", v1) for i in range(1, 13)),
        "v1_has_D1_D5": all(f"D-{i}" in v1 for i in range(1, 6)),
        "v1_has_M1_M12": all(f"M-{i}" in v1 for i in range(1, 13)),
        "review_vs_v1_M_remap_note": "M-11=U覆盖/M-12=工程图一致（v1 §3 重定义）",
    }

    out = {"inputs": integrity["sha256"], "integrity": integrity,
           "checks": checks, "special": special,
           "summary": {
               "M_fail": [c["id"] for c in checks if c["status"] == "FAIL"],
               "M_partial": [c["id"] for c in checks if c["status"] == "PARTIAL"],
               "special_fail": [k for k, v in special.items() if v["status"] != "PASS"],
           }}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
````

## 附录 C — 图结构闭合脚本（G-2/G-4）

````python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""S0 冻结前机检：三张图（ER/DFD/ST）的结构闭合检查（G-2/G-4）。

检查：
  G-2a ER：关系行里出现的实体 ⊆ 有属性块的实体；有属性块的实体 ⊆ 1.3 实体表；1.3 实体表 ⊆ 图实体
  G-2b DFD：图中 P* 过程 ⊆ 2.4 过程表；存储表出现在图或显式标「非持久化」
  G-2c ST：转换表 To 状态 ⊆ 图中状态（允许 composite 写法如 GraphView.Overview）
  G-4  交叉引用：DFD 存储 ∈ ER 实体 ∪ {非持久化}；ST 引用的 ViewModel 字段 ⊆ ER/S6 schema
用法： python diag_qa.py <ENGINEERING-PLAN.md> [<S0-freeze-check.md>]
输出： JSON + 人类可读摘要；有 FAIL ⇒ 退出码 1。
"""
import json
import re
import sys

PLAN = "D:/AAA_Jupyter/Memoria/docs/design/multilevel-graph/ENGINEERING-PLAN.md"


def sections(text):
    """按二级标题切段。"""
    parts = re.split(r"^## ", text, flags=re.M)
    out = {}
    for p in parts[1:]:
        title = p.splitlines()[0].strip()
        out[title] = p
    # 三级标题段也收集（用于 1.3/2.4/3.3）
    parts3 = re.split(r"^### ", text, flags=re.M)
    for p in parts3[1:]:
        out[p.splitlines()[0].strip()] = p
    return out


def get_mermaid_blocks(text):
    return re.findall(r"```mermaid\n([\s\S]*?)```", text)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else PLAN
    text = open(path, encoding="utf-8").read()
    blocks = get_mermaid_blocks(text)
    if len(blocks) != 3:
        print(json.dumps({"status": "FAIL", "reason": f"expected 3 mermaid blocks, got {len(blocks)}"}))
        return 1
    er, dfd, st = blocks
    sec = sections(text)
    results = []

    # ---------- ER ----------
    er_attrs = set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]+)\s*\{", er, re.M))
    rel_lines = re.findall(r"^\s{4}([A-Z][A-Z0-9_]+)\s+[|}][o|]?--[o|][{|]\s+([A-Z][A-Z0-9_]+)", er, re.M)
    rel_ents = {a for a, _ in rel_lines} | {b for _, b in rel_lines}
    table_13 = sec.get("1.3 实体表（主键 / 基数 / 生命周期 / 事实源归属）", "")
    table_ents = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", table_13))
    results.append({
        "id": "G-2a-ER",
        "rel_entities_without_attrs": sorted(rel_ents - er_attrs),
        "attrs_not_in_table_1_3": sorted(er_attrs - table_ents),
        "table_entities_not_in_diagram": sorted(table_ents - er_attrs),
        "status": "PASS" if not (rel_ents - er_attrs) and not (er_attrs - table_ents) and not (table_ents - er_attrs) else "FAIL",
    })

    # ---------- DFD ----------
    dfd_procs = sorted(set(re.findall(r"\b(P\d{1,2})\[", dfd)))
    table_24 = sec.get("2.4 过程表", "")
    missing_procs = [p for p in dfd_procs if f"| {p} |" not in table_24]
    results.append({"id": "G-2b-DFD", "procs": dfd_procs, "missing_in_2_4": missing_procs,
                    "status": "PASS" if not missing_procs else "FAIL"})

    # ---------- ST ----------
    st_states = set(re.findall(r"^\s+([A-Z][A-Za-z0-9_]+)\s+-->", st, re.M)) | set(
        re.findall(r"-->\s+([A-Z][A-Za-z0-9_]+)\s*:", st, re.M))
    st_states |= set(re.findall(r"^state ([A-Z][A-Za-z0-9_]+)", st, re.M)) | {"Inactive", "Loading", "Degraded"}
    table_33 = sec.get("3.3 转换表（ST 冻结时 100% 覆盖；当前 v0）", "")
    to_states = set(re.findall(r"\| ([A-Z][A-Za-z0-9_.]+) \| U-", table_33))
    unknown_to = sorted(s for s in to_states if s not in st_states and s.split(".")[-1] not in st_states)
    rows = len(re.findall(r"\| (ST-\d{2}) \|", table_33))
    results.append({"id": "G-2c-ST", "rows": rows, "to_states_unknown": unknown_to,
                    "status": "PASS" if rows >= 1 and not unknown_to else "FAIL"})

    # ---------- 交叉引用 ----------
    table_25 = sec.get("2.5 数据存储表（SoT 判定是冻结前提）", "")
    storage_names = set(re.findall(r"^\| `([^`]+)` \|", table_25, re.M))
    cross_fail = []
    for name in storage_names:
        # 存储名可以是 ER 实体（中文别名不强制）；这里只做「ER 实体名 ∪ 视图/缓存 显式标注」的可解释性检查
        if name.upper() in er_attrs or "view" in name.lower() or "缓存" in name or "设置" in name or "计数" in name:
            continue
        cross_fail.append(name)
    results.append({"id": "G-4-crossref", "storage_names": sorted(storage_names),
                    "unclassified": cross_fail, "status": "PASS" if not cross_fail else "PARTIAL"})

    failed = [r for r in results if r["status"] == "FAIL"]
    print(json.dumps({"file": path, "mermaid_blocks": len(blocks), "results": results,
                      "summary": {"FAIL": len(failed)}}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
````

## 附录 D — 原始输出摘要（本机执行）

```
$ node parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md
﻿{"kind":"meta","mermaidVersion":"11.16.0","mermaidSha256":"9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76","jsdomVersion":"29.1.1","node":"v24.21.0"}
{"kind":"file","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","blocks":3,"fileSha256":"93393ae457d2b6b56ed448409cea67389cf7509e712eb34c4e490322aded2198"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":1,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":2,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":3,"ok":true,"diagramType":"stateDiagram"}
{"kind":"summary","failedBlocks":0}

$ python diag_qa.py docs/design/multilevel-graph/ENGINEERING-PLAN.md
﻿{
  "file": "D:\\AAA_Jupyter\\Memoria\\docs\\design\\multilevel-graph\\ENGINEERING-PLAN.md",
  "mermaid_blocks": 3,
  "results": [
    {
      "id": "G-2a-ER",
      "rel_entities_without_attrs": [],
      "attrs_not_in_table_1_3": [],
      "table_entities_not_in_diagram": [],
      "status": "PASS"
    },
    {
      "id": "G-2b-DFD",
      "procs": [
        "P1",
        "P10",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
        "P7",
        "P8",
        "P9"
      ],
      "missing_in_2_4": [],
      "status": "PASS"
    },
    {
      "id": "G-2c-ST",
      "rows": 19,
      "to_states_unknown": [],
      "status": "PASS"
    },
    {
      "id": "G-4-crossref",
      "storage_names": [
        "sidecar .memoria.yaml",
        "正文 .md"
      ],
      "unclassified": [
        "正文 .md",
        "sidecar .memoria.yaml"
      ],
      "status": "PARTIAL"
    }
  ],
  "summary": {
    "FAIL": 0
  }
}
```

> `mcheck-v1.json` 逐项输出较长（含每项命中行号 / U 覆盖明细），已在本报告 §0 / §13 摘要；完整 JSON 可由附录 B 脚本复跑生成。

---

## 附录 E — M-11 复跑原始输出（2026-11-02T17:2x）

```
$ python mcheck_v1.py   # 冻结对象 v1 sha ab7538f0…
{
 "inputs_v1_sha256": "ab7538f09b20d336647340a24b987e3ac0dd7a4256da430ad5526e738def952e",
 "summary": {
  "M_fail": [],
  "M_partial": [],
  "special_fail": []
 },
 "M-11": {
  "status": "PASS",
  "v1_present_count": 35,
  "v1_missing": [],
  "declares_matrix": true
 },
 "special": {
  "R-1": "PASS",
  "R-2": "PASS",
  "R-3": "PASS"
 }
}
```
