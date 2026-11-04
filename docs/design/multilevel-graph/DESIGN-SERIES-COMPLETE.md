# 多层次图谱设计研讨 · 收口（S0–S10 全部冻结）

> **日期**：2026-11-04（Asia/Shanghai）。
> **状态**：**S0–S10 十场设计研讨全部冻结**；0.5 实现可全面启动。
> **最高依据**：`multilevel-graph-vision.md`（U-1..U-35，逐字存档，不得改写）。

## 1. 冻结清单

| 场次 | 主题 | 冻结稿 | sha256（前 16） | 记录 |
|---|---|---|---|---|
| S0 | 术语 | `S0-terms-v1.md` | `241b1e1e…` | `S0-FREEZE-RECORD.md` |
| S1 | 层级/维度/注册表 | `S1-dimensions-v1.md` | `6676c71d…` | `S1-FREEZE-RECORD.md` |
| S2 | 聚类/run/稳定性 | `S2-clustering-v1.md` | `92bb0041…` | `S2-FREEZE-RECORD.md` |
| S3 | 视觉语言 | `S3-visual-v1.md` + `S3-ADDENDUM-1.md` | `0ca4ea0e…` | `S3-FREEZE-RECORD.md` |
| S4 | 渲染/取景 | `S4-render-v1.md` | `2576f6c8…` | `S4-FREEZE-RECORD.md` |
| S5 | 导航状态机 | `S5-nav-v1.md` | `7f4c4515…` | `S5-FREEZE-RECORD.md` |
| S6 | 数据契约 | `S6-contract-v1.md` + `S6-ADDENDUM-1/2` | `40f12e5f…` | `S6-FREEZE-RECORD.md` |
| S7 | agent 如何使用图谱 | `S7-agent-v1.md` | `70dd8748…` | `S7-FREEZE-RECORD.md` |
| S8 | 度量与验收 | `S8-metrics-v1.md` | `c6a135ff…` | `S8-FREEZE-RECORD.md` |
| S9 | 后端检索 | `S9-retrieval-v1.md` | `42f36423…` | `S9-FREEZE-RECORD.md` |
| S10 | agent 设计 KP/语义边 | `S10-kp-v1.md` | `a5db0f1c…` | `S10-FREEZE-RECORD.md` |

**工程图纸**：`ENGINEERING-PLAN.md`（33 图，mermaid 11.16.0 `9198f632…`，全部 `PARSE_OK`）。

## 2. 贯穿原则（冻结语义摘要）

- **单一真源**：事实 = `.md` + `.memoria` sidecar/manifest；图谱/缓存/VM 全是派生，可重建；D-3 禁 graph 服务写 sidecar。
- **多层次/多维度**：level/view_family/dimension 正交；focus-only 一跳；选择性渲染 + presence/rule_id 可解释。
- **2D/3D 不分家**：同一接口，0.5 只发 2D，3D `capability=false`。
- **agent 只读消费（0.5）**：S7 5 工具、candidate_ref、引用/excerpt、edition 幂等审计；S10 的 agent 写 KP/语义边**不在 0.5**。
- **语义纯净**：结构/引用边不得冒充 semantic；`no_semantic_edges` 合法；语料质量差由 S10 curation 解决，不伪造。
- **可验收**：S8 P0 硬门禁（G6/G7/X-RULE/G-G7/DoD）+ S9 可执行 eval + S10 eval；关闭项显式登记。

## 3. 0.5 实现入口

- 实现顺序：S6a **I-01..I-13**（DataSourceReader → GraphViewBuilder → RegistryService → ClusterRunBuilder → AdmissionService → ViewModelBuilder → RendererAdapter → NavController → CacheStore → AuditLog → G6Snapshot → ErrorMap → SchemaValidator）；
- 验收：S8 DoD（I-05/06/07/08 P0，I-07 只验 2D）；
- 检索：S9 契约（golden/eval/GATE-RET）；
- S10：未来版本（人工确认 UI 才 apply）。

## 4. 过程与裁决

- 每场：章程 → A/B 独立提案（B 先落盘、A 不偷看）→ 差异/异议 → Lead 裁决 → 修订 v2 → SE 工程校核 → Lead 独立机检 → 冻结 + 决策 + 记录 + commit。
- 各场抓到的真实问题（举例）：S4 `candidates(full)⊇default`、S5 149 vs 148 边、S6 B 误读 S3 role、S7 缺 resolve_ref/edges 口径/错误码、S8 X-RULE 漏节点/G6 双路径、S9 `id/ref` vs `candidate_ref`、S10 缺 contain(semantic)/`S10_*` 码/D-3 写路径。
- 全部决策在 `team/decisions.jsonl`；冻结记录逐场可查。

## 5. 边界

- 设计冻结 ≠ 产品实现；0.4.11 不含图谱 UI/写能力；0.5 才实现 2D 图谱板块。
- 本文件是收口索引；语义以各场 `*-v1.md` 冻结稿为准。
