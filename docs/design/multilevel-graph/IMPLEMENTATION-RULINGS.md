# 0.5 实现期契约裁决（Implementation Rulings）

> 用途：实现批次中发现的**冻结稿冲突/欠定义**，由 Lead 在实现期裁决并留痕；不替代 S0–S10 冻结稿。
> 冻结稿语义仍以各 `*-v1.md` 为准；本文件只记录「实现按哪条」与「是否需要 ADDENDUM/重开」。

## B2（2026-11-04）

### R-B2-1 `run_id` 公式冲突 → 按 S2-7（不含 dimension）
- **冲突**：S6-4 公式含 `dimension`；S2-7 六元组不含 `dimension`；S2-10 冻结切 H/A 维度不改变簇。
- **裁决**：实现按 **S2-7 六元组**；S6-4 文本更正见 `S6-ADDENDUM-3.md`；不得把 dimension 放进 `run_id`。
- **证据**：`tests/graph/test_cluster_run.py::test_run_id_is_independent_of_dimension`。

### R-B2-2 `GRAPH_REGISTRY_*` 不存在 → 用已冻结码 + detail
- **冲突**：任务书写 `GRAPH_REGISTRY_*`，但 S6 + ADDENDUM-1/2 无该命名空间。
- **裁决**：不新增码；canonical 用 `GRAPH_INTERNAL`，S1 `DIM_*` 细分放 `detail.dim_code`；签名失败用已冻结 `GRAPH_HISTORY_SIGNATURE_INVALID`。若未来需要独立 registry 码，走 S6-ADDENDUM 登记（本次不做）。

### R-B2-3 edge 契约缺 `contain_kind` 等字段 → 先修 schema 再进 B3（最高优先）
- **冲突**：`contracts/schemas/edge.json` 未含 `contain_kind`/`assertion_source`/`curated_by`/`curated_at`，且 `additionalProperties:false` ⇒ 语义边无法从 DataSource 传入，B3 Admission 也会漏。
- **裁决**：**修 B1 的 edge schema**（增加 `contain_kind ∈ {structural,semantic}`、`assertion_source?`、`curated_by?`、`curated_at?`，与 S0/S6/S10 字段一致），补 B1/B2 测试；**在 B3 开工前完成**。这是 schema 欠定义修复，不是 S6 语义变更。
- **派单**：见 task-354。

### R-B2-4 `partial_disconnected` 在 average-linkage HAC 下不可达
- **冲突**：五状态冻结，但 HAC 簇天然连通，端到端算不出 `partial_disconnected`。
- **裁决**：保留五枚举；实现允许状态机直测覆盖；**文档明确当前算法下端到端不可达**，不得造假数据；若未来换算法/要求可达，重开 S2 修订。B2 不改算法。

### R-B2-5 `contain_kind=semantic` 但证据不全：B3 显式报错，不静默降级
- **背景**：`is_semantic_edge()` 按 S0-1 G_sem 门控返回 false；若读取路径静默降级，会把"标了 semantic 但缺 assertion_source/curated_by/at"伪装成结构边。
- **裁决**：B3 Admission 对 `contain_kind=semantic` 或 `label=semantic` 的边做证据完整性检查：缺 `assertion_source`/`curated_by`/`curated_at` ⇒ **`GRAPH_EDGE_SEMANTIC_MISMATCH`（可见失败）**，不得静默当非语义；结构边（缺省/structural）不要求这些字段。
- **读取路径**：不重算 `quote_sha256`（B5/G6 的 G6 快照可复核）；写入路径仍由既有 curation 校验器逐字校验。
