# S2 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S2-clustering-v1.md`（13 条规范 + R-S2-1..R-S2-13 + U 覆盖矩阵）。
> **冻结时间**：2026-11-03T19:55+08:00（Asia/Shanghai）。
> **决策**：`dec-20261103-ec432887`（Lead；S0 `dec-20261102-a6af89e1`、S1 `dec-20261103-35844b56` 已冻结）。
> **状态**：**已冻结**。S3 可开；S0–S6 冻结前仍不写产品代码。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S2-clustering-v1.md`（**冻结稿最终态**） | S2 唯一规范来源 | `92bb004190d3f93795fe4916cdf904f4dc7574eaaccb43eff9d63edb5b27a6c6` |
| `S2-engineering-check.md` | SE 工程校核（M-S2-1..12 + 独立 probe） | `90c0a3c3…` |
| `S2-clustering-proposal-A-v2.md` | 证据链（主办研究） | `154cf098…` |
| `S2-clustering-proposal-B-v2.md` | 证据链（独立复核） | `5a1d299d…` |
| `S2-objections-v2.md` | 差异/异议 | `864a9cdd…` |
| `S2-RULINGS.md` | Lead 裁决（R-S2-1..8） | `4a83c8a9…` |
| `s2-semantic-probe/{probe.py,results.json}` | 语义-only probe（合成+真实语料） | `0dc7b198…` / `f3f07893…` |
| `ENGINEERING-PLAN.md`（S2 增量） | ER-03/DF-03/ST-03 | `a12735fc…` |

**冻结轮次**：SE 首轮 9 PASS / 3 FAIL（μ 端点对未去重；tie-break 不精确 + 后验失败规则缺失 + 四态笔误；VM 纯度缺失）；Lead 修三处后 SE 复跑 **12/12 PASS、M_fail=[]**；Lead 独立机检（13 条款、R-S2-1..13、pair-dedup、tie-break、五状态、VM 纯度、无簇状态、params_hash）PASS。冻结身份取最终态 sha `92bb0041…`。

## 2. S2 冻结了什么（一句话版）

1. **簇 = 仅 semantic 边**构成的语义内聚小群（μ 达标、β 不超标），**不是**严格连通分量；结构/引用边权重 0，只作 `diag_struct_*` 诊断；
2. **μ/β 端点对去重**：同一对节点多语义边只计一次，`0≤μ,β≤1`；
3. **确定性 HAC**：纯自实现 average-linkage + dendrogram + cut_policy；tie-break=合并后成员集合 canonical 字典序最小；后验 μ/β 校验失败按 cut_policy 调 k，仍失败 ⇒ `algorithm_failed`，绝不输出违规簇；
4. **五状态**：`ok / no_semantic_edges / partial_disconnected / size_exceeded / algorithm_failed`；
5. **run 粒度** `(level, view_family)`；run_id 公式与 **params_hash 字段集冻结**；curation/审计记 `run_id+cluster_key`；
6. **τ 默认** `0.5/0.25`（出处：合成语义夹具 probe；真实语料 E_sem=0 属语料质量问题，S8 live 复标定；默认值进 params_hash）；
7. **无语义边合法**：`no_semantic_edges`、coverage=0；**禁止用结构/引用边伪造簇**；默认视图 UX 交 S3/S4；修复路径 = agent 建立语义（S10）；
8. **单点簇**：`μ=null`、`representative=false`；L0 `root_exempt`；coverage=覆盖 KP/全库 KP；
9. **多归属**：`Membership` 多对多、同 `(level,view_family)` 单归属、跨族/层/维多归属、v1 不设上限；`role={member}`；
10. **A 维度不产生/不改变簇**（机检不变性）；
11. **持久化**：全部派生缓存，**禁止写产品 sidecar/新段（D-3）**；簇/run/dendrogram/候选 run **不得进入 ViewModel（D-4）**；
12. **agent**：v1 只读；可请求候选 run（`requester/reason/params/base_run_id` 审计，candidate 不自动采用、不覆盖旧 run）；
13. **稳定性**：run 不可变；触发=manifest/semantic 边/算法/params 变化或显式请求；Jaccard/churn/split/merge 可复算。

## 3. 机检与证据

- SE M-S2-1..12：`M_fail=[]`、12/12 PASS；三处 FAIL 的修复证据在 `S2-engineering-check.md`；
- **独立 probe**（SE 另行实现、不 import A probe）：frozen 357KP/62 边、showcase 35KP/73 边均 E_sem=0；与 A `results.json` 一致；τ=0.5/0.25 出处成立（合成夹具 two_triangles_bridge）；
- 同版本 mermaid（vendored，sha `9198f632…`）：PLAN 9 图 + 报告 3 图全部 `PARSE_OK`；
- 与 S0/S1 一致性：R-1/R-3、S0-2 partition、S0-7 多归属、D-2/D-3/D-4、S1 H/A、`view_family`、R-S1-11 全 PASS；
- Lead 独立机检 PASS（见 §1）。

## 4. 未关闭项（不阻塞冻结）

- O-S2-4..10：S6a run 失败回滚/跨 run H 谓词/canonical 序列化；S8 τ live 复标定；β=0.25 边界单测；A probe tie-break 历史注记。

## 5. 变更控制

- 加算法/cut_policy/参数：S2 修订 + 决策 + params_hash 版本；
- 删/改 μ/β 语义-only、身份公式、无簇状态规则：重开 S2；
- 冻结身份 = 本记录 + `S2-clustering-v1.md`；未记录的字节改动视为破坏冻结。

## 6. 下一步

- S3（节点视觉与渲染接口）章程起草 → 人确认议程 → 逐议项研讨；S3 必须处理 `no_semantic_edges` 状态的 UX，但不得把结构边当语义簇；
- 产品实现仍等 S0–S6 冻结。
