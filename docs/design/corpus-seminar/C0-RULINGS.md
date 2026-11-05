# C0 裁决（Lead）：语料库设计研讨并集与修订轮

> **依据**：`CHARTER.md`（C1–C12）；A（`18b1674d…`）、B（`1c0989d7…`）、异议（`e199db84…`）。
> **状态**：C 系列**未冻结**；两版无 P0，3 条 P1 需冻结前修。本文件是修订轮唯一依据。

## 0. Lead 复核

| 项 | 复核 | 结论 |
|---|---|---|
| P1-1 A 的 IAA | 读 A §C8：KP 用 Cohen κ（二分类）、边用 F1 | **成立**：span/边界/重叠标注不能用二分类 κ；边 F1 不是 IAA |
| P1-2 SemEval URL | 实测 `W09-2415` 为 SemEval-2010 Task 8；A 写 `S10-1002` | **成立**：A 必须改；所有 URL 需 HTTP/标题核验 |
| P1-3 A 许可分层 | 读 A §C2：仅“可发布 + 用户库私有” | **成立**：缺内部评测层（NC/ND/购买/授权不可再分发），实现者可能误发布或无法纳入真实教材 |
| 其余点名 | 本体/关系、KP 粒度、规模、工具、S10/0.5、交付 | 方向 PASS；P2 合并 |

## 1. 跨议题裁决（R-C0-1..R-C0-6）

### R-C0-1 IAA 分型（P1-1）
- **裁决**：KP **span/边界**用 **Krippendorff unitizing α**（或 exact-boundary/overlap F1）为主，**类型/方向**用 Cohen/Fleiss κ；**语义边**用 tuple-set F1（类型+方向+端点）+ 裁决一致率；**分指标合格线**（不得用一个 κ 概括全部）。
- pilot 100% 双人独立；合格线：span α≥0.67（目标 0.8）、类型/方向 κ≥0.67（目标 0.8）、边 tuple-set F1≥0.70（目标 0.80）；10% 抽检+裁决记录。
- **机检**：报告必须列分指标、样本量、缺失处理；不达线不得扩主集。

### R-C0-2 证据 URL 核验（P1-2）
- **裁决**：A 的 SemEval 链接改为 `https://aclanthology.org/W09-2415/`；所有外部 URL 必须做 **HTTP 200 + 页面标题**核验并记录（日期/方式）；错误 URL 即 P1。
- **机检**：证据表含 `url/title/http_status/verified_at`。

### R-C0-3 许可分层（P1-3）
- **裁决**：三层：
  - **Tier A 可发布**：CC BY / CC BY-SA / CC0 / 公有领域 / 自著且授权；
  - **Tier B 仅内部评测**：CC BY-NC / ND / 购买 / 用户授权但**不可再分发**——隔离副本、不导出、不进发布包；
  - **Tier C 禁用**：许可不明/禁止使用/无法核实。
- 逐文档记录 `license/SPDX/redistribution/DB-right/fair-use/PII`；PII 用 Presidio/人工；发布前 NOTICE/许可清单；Tier B 不进 golden 发布资产（可进内部评测报告但注明不可再分发）。
- **机检**：无 license 字段的文档不得进 Tier A；Tier B 不得出现在发布包/golden 目录。

### R-C0-4 并集
- 采 A 的 C1 GraphRAG/HITL、C5 例数、C9 三层、C12 DVC；采 B 的 C2 Tier+Presidio、C8 span IAA、C10 PII、C12 FAIR/Croissant/Data Statement；冲突按 R-C0-1/3 定。

### R-C0-5 粒度/成本（P2 升级为冻结前必须写清）
- C4：默认 **概念+1–3 句解释、单 section、不重叠**；pilot 同时试“命题级”变体，用 R-C0-1 的 IAA 决定采用哪个；嵌套 future。
- C7：pilot 预算上限 **2 人 × 2 天（≈32 人时）**；记录实际工时；超预算则缩规模，不得降标注质量。

### R-C0-6 0.5 重跑门槛（C9/C11）
- 只有 pilot 同时满足：① IAA 达线；② `Q-EVIDENCE=100%`、`Q-SEM-PURITY=1.0`；③ 有语义边后 **graph 分型适用**（非 NA）且 `recall@5≥0.80`、`sem_purity=1.0`；④ 无写事实/无 sidecar 写；⑤ 2× 确定性；才允许 0.5 重跑 GATE-RET 并讨论发布。
- 禁止用合成数据/聚合掩盖；`NOT_APPLICABLE` 不算通过。

## 2. 修订轮任务

**A-v2**：修 R-C0-1/2/3，采 B 的 C2/C8/C10/C12 并集；更新证据核验表与 C7 成本。
**B-v2**：修 P2（unitizing 实现、成本口径、GATE-RET 阈值/命令），采 A 的 C1/C5/C9/C12；确认 P1 关闭。
**SE（task-363）**：等 v2 齐后校核（本体/标注/评测/工具/许可）+ 图 `PARSE_OK`。

## 3. C 系列冻结门禁

1. A-v2/B-v2 关闭 R-C0-1..6；
2. SE 工程校核 PASS；
3. Lead 独立机检（许可分层/IAA 分型/URL 核验/评测分型/工具只读/S10 衔接/成本）；
4. 产 `C0-corpus-v1.md` + `C0-FREEZE-RECORD.md`；
5. 冻结后先做 pilot，再决定 0.5 重跑。

## 4. 边界

不写产品代码、不发布 0.5、不改 S0–S10；A/B 旧版保留。
