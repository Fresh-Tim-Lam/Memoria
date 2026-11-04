# S10 裁决（Lead）：并集、异议处置与修订轮

> **依据**：`multilevel-graph-vision.md`；`S10-charter.md`；
> 上游冻结 S0–S9（`241b1e1e…/6676c71d…/92bb0041…/0ca4ea0e…/2576f6c8…/7f4c4515…/40f12e5f…/70dd8748…/c6a135ff…/42f36423…`）。
> **输入**：提案 A（`d0a09404…`）、提案 B（`b323c82b…`）、异议（`ea21e5d8…`）。
> **状态**：S10 **未冻结**；两版无 P0，3 条 P1 需冻结前修。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核动作 | 结论 |
|---|---|---|
| P1-1 A 排除 contain(semantic) | 读 S0-3 `E_relation_min`、S1 `relation_sources` | **成立**：S0 含 contain/reference/extend；S10 schema 静默排除会让 E_sem 缺 contain 语义 |
| P1-2 `S10_*` 码 vs S6 `GRAPH_*` | 读 S6-9、S7 `S6-ADDENDUM-1` | **成立**：第二套命名空间会破坏 S8/G7/客户端映射 |
| P1-3 写路径 vs D-3 | 读 S6-1/S6-8/D-3 与 A/B | **成立**：agent 只能 propose_write；apply 必须由产品 curation writer 在人工确认后执行，graph 服务无 sidecar 写权限 |
| 其余点名 | 边界/KP/语义/双引用/冲突/质量/S1-S2/隐私/0.5 | 方向 PASS；P2 合并 |

## 1. 跨议题裁决（R-S10-1..R-S10-5）

### R-S10-1 语义边类型对齐 S0（P1-1）
- **裁决**：`SemanticEdge.type` 允许 **S0 `E_relation_min` 全部**：`contain`（`contain_kind ∈ {structural, semantic}`）、`reference`、`extend`；**只有 `label=semantic` 或 `contain_kind=semantic` 进入 `E_sem`**；结构/引用边不得标 semantic/不得计入 E_sem；`contain` 的 structural 由系统派生、不可手标为 semantic；新增类型须 S0/S1 修订，S10 不静默增删。

### R-S10-2 错误码统一 `GRAPH_*`（P1-2）
- **裁决**：S10 只用 S6 `GRAPH_*`；新增 `GRAPH_KP_*`/`GRAPH_EDGE_*`/`GRAPH_CURATION_*` 通过 **`S6-ADDENDUM-2`** 登记（legacy/i18n/severity/audit_id）；禁止 `S10_*` 新命名空间；未知 `GRAPH_INTERNAL`。

### R-S10-3 写路径与 D-3（P1-3）
- **裁决**：agent **只产 `propose_write`**（KP/边/curation 提案 + evidence），**不写任何文件**；apply 必须由**产品 curation writer** 在人工确认后执行（plan/approval/backup/atomic/undo/audit）；graph/agent 服务**无 sidecar/正文写权限**；`curated_by/curated_at` 与 curation 元数据只写 S6 允许的 metadata/audit 白名单；失败零写入；机检无 sidecar 写、无事实写入。

### R-S10-4 质量/评估可执行（P2）
- **裁决**：S10 质量指标（KP/边 precision/recall、证据锚 100%、semantic 纯净=1.0）必须有 golden schema/路径/sha、`eval-kp` 命令/exit、指标 JSON+sha、人工抽检样本/阈值；S8 消费；阈值未校准前 soft。

### R-S10-5 身份/嵌套/合并/边界（P2）
- **裁决**：`kp_id` 全局唯一（anchor+label 仅辅助）；默认单 section/不重叠，嵌套 future；merge 保留 canonical+alias+history；`direction` 允许 `both`（默认 source→target）；curation 元数据存 S6 curation 白名单；S10 未启用时 S7/S9 只读；写后 S9 失效/重建。

## 2. 修订轮任务

**A-v2**：语义边全类型（contain/reference/extend + E_sem 门槛）；`GRAPH_*`/ADDENDUM-2 码表；写路径 D-3（propose_write only）；质量 eval 可执行；kp_id/direction/merge/边界。
**B-v2**：同口径全类型/码表/D-3；补失败码表/WritePlan 细节；质量 eval；更新差异清单。
**SE（task-344）**：等 v2 齐后校核 + KP/边/写路径图 + 质量草案 + `PARSE_OK`。

## 3. S10 冻结门禁

1. A-v2/B-v2 关闭 R-S10-1..5（逐条证据）；
2. SE 工程校核 PASS（KP/边/写路径/失效/质量，与 S0–S9 一致）；
3. Lead 独立机检（全类型/E_sem 门槛/码表/D-3/质量/0.5）；
4. 与 S0–S9 无冲突；
5. 冻结 `S10-kp-v1.md` 并写决策。

## 4. 边界

不写产品代码；不改 S0–S9 冻结稿（仅 S6-ADDENDUM-2 扩码）；S10 冻结前不开工实现；修订保留旧版。
