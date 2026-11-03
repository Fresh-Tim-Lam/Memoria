# S6 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`；`S6-charter.md`；
> 上游冻结 S0/S1/S2/S3(+ADDENDUM-1)/S4/S5（`241b1e1e…/6676c71d…/92bb0041…/0ca4ea0e…/2576f6c8…/7f4c4515…`）。
> **输入**：提案 A `S6-contract-proposal-A.md`（`af67ca9f…`）、提案 B（`f9eb5c13…`）、`S6-objections.md`（`82ecfa9b…`）。
> **状态**：S6 **未冻结**；A 无 P0，3 条 P1 中 **2 条成立、1 条不成立**（B 误引 S3）。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 A `nav_id` vs S5 `frame_id` | 读 S5-nav-v1 L17-19/L59 | **成立**：S5 冻结字段是 `frame_id`；S6 必须一致，`nav_id` 只能作别名 |
| P1-2 A `FRAME_SPEC` 超界 | 读 S4-render-v1 与 S5 L17-19 | **成立**：S4 的 `frame_spec` 只有 `level/view_family/dimension/focus/hop/new_hop/mode/budget`；`frame_id/edition` 是 S5 派生/本地字段，不得塞进 S4 输入 |
| P1-3 B 「S3 role∈{member,focus}」 | 读 S3-visual-v1 L17 | **不成立**：S3 冻结原文是 **`role ∈ {member}`（v1 只有 member）**；`focus/selected/hover` 是渲染器/Presentation 瞬态，不进 VM。A 的 `role:"member"` 正确；B 必须撤回该异议 |
| history 签名 | 读 S1/章程要求 | 成立：history 需**可选 `signature?` + 签名位置/算法**；作为 S6 可选字段，不重开 S1 |
| 存储路径 | D-3 与 AGENTS 单一事实源 | 需统一：派生缓存/registry/audit 分目录，派生可删重建 |

## 1. 跨议题裁决（R-S6-1..R-S6-6）

### R-S6-1 `frame_id` 为唯一导航帧身份（P1-1）
- **裁决**：S6-7 全部使用 **`frame_id`**（禁止 `nav_id` 作为 schema 字段；可保留 `nav_id` 仅作文档别名）；失败码统一 **`GRAPH_FRAME_ID_INVALID`**；`NAV_STACK_ENTRY`/`NAV_EVENT`/持久化/G6/curation 引用全部 `frame_id`；机检「S6 nav schema 字段 == S5-1/R-S5-9」。

### R-S6-2 `FRAME_SPEC` 严格等于 S4 冻结输入（P1-2）
- **裁决**：`FRAME_SPEC = {level, view_family(view_id), dimension_id, focus, hop, new_hop, mode, budget}`；**`frame_id/edition` 不属于 S4 输入**：`frame_id=sha256(canonical(FRAME_SPEC))` 由 S5 派生；`edition` 由 S5 从 corpus/manifest 派生并本地校验。S6 可定义 `NAV_FRAME` 含 `frame_id/edition`，但必须明确「S5 派生，不传 S4」；机检字段集。

### R-S6-3 撤回 B 的 role 异议（P1-3 不成立）
- **裁决**：`VM_NODE.role` 冻结为 **`"member"`**（S3 原文）；`focus` 不是 VM role，focus 高亮由 Presentation 瞬态实现；S6-5 采用 A 的 `role:"member"`，B 的 `role∈{member,focus}` 异议**撤回**，并在 B-v2 异议表中标 `WITHDRAWN (misread S3)`。

### R-S6-4 registry history 签名（P2→冻结）
- **裁决**：`DIMENSION_HISTORY_ENTRY` 增加可选 **`signature?`**：`{alg:"ed25519"|"hmac-sha256", key_id:string, sig:string}`；存放位置：同目录 detached `.sig` 或以字段落盘（二选一，S6a 定），**不得只写口头**；无签名时 `signed=false` 且 G6 标记；签名验证失败 ⇒ fail-closed `GRAPH_HISTORY_SIGNATURE_INVALID`。

### R-S6-5 存储路径与 GC（统一）
- **裁决**：
  - 派生缓存：**`.memoria/cache/graph/`**（可删除重建；不入库；GC 只删此类）；
  - registry/history：**`.memoria/config/graph/`**（配置+不可变 history；由显式操作写，非 sidecar 自动写）；
  - 审计：**`.memoria/agent/audit/graph/`**（append-only；不参与事实源）；
  - **禁止**向 `.md` sidecar 写簇/run/VM（D-3）；旧 `graph-groups` 不迁移，只读 fallback 可保留（默认关闭）。
  - GC：派生缓存 N=20 个 run 或 90 天（先到者），registry history 永不 GC；审计 append-only 不 GC。

### R-S6-6 错误命名空间与 0.5 边界
- **裁决**：**`GRAPH_*` 为 canonical**，保留 S2–S5 旧码作为 `legacy_code` 映射；未知错误 `GRAPH_INTERNAL` 不静默；i18n key 归 UI 层（S3）。
- **0.5 边界**：按 A —— 2D 先发；3D 只留同签名接口 + `capability=false`；不做 agent 写/自动 semantic/跨库/时间维/图编辑器/破坏性迁移；S7–S10 不在 0.5。
- **G6**：字段统一为 `g6_version, data_source_sha, run_ids, registry_sha, vm_sha, frame_sha, nav_sha, rule_histogram, node/edge counts, subset_ok, determinism_sha, closure_violations=0, behind_violations=0`；阈值 `determinism=100%`、`subset_ok=true`、`closure/behind=0`。

## 2. 修订轮任务

**A-v2**：R-S6-1（nav_id→frame_id）、R-S6-2（FRAME_SPEC 去 frame_id/edition，改为 S5 派生）、R-S6-4（history signature）、R-S6-5（路径）、R-S6-6（错误码/G6/0.5 边界）。
**B-v2**：撤回 P1-3（S3 role 误读）；吸收 A 的字段表/token map/统一 `GRAPH_*`/G6/0.5 清单；补 T30/事件集；采用 A 的 registry/history 签名位置与存储路径。
**SE（task-322）**：等 v2 齐后出 S6a 定稿 + 接口清单 + mermaid `PARSE_OK`。

## 3. S6 冻结门禁

1. A-v2/B-v2 关闭 R-S6-1..6（逐条证据；B 撤回 role 异议）；
2. SE 工程校核 + S6a 定稿 PASS；
3. Lead 独立机检（字段集/失败码/单一真源/缓存可重建/G6/0.5 边界）；
4. 与 S0–S5 无冲突；
5. 冻结 `S6-contract-v1.md` 并写决策；**S0–S6 全冻结 → 0.5 实现计划**。

## 4. 边界

不写产品代码；不改 S0–S5 冻结稿；S6 冻结前不开工实现；修订保留旧版。
