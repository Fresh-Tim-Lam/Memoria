# C0 语料库设计 · 冻结稿 v1（候选）

> **依据**：人 2026-11-05「真实的语料库需要精细设计，联网搜索，得开研讨」；`CHARTER.md`；`C0-RULINGS.md`。
> **输入**：A-v2（`fc9a927a…`）、B-v2（`125429dc…`）、异议-v2（`ee01ef16…`）。
> **状态**：冻结候选；待 SE 工程校核（C0a）与 Lead 独立机检后冻结；**0.5 保持 HOLD**，C 系列冻结后先做 pilot。

## 0. 一句话口径

先做**开放许可教材 1 章 pilot**：按“来源/许可 → KP → 语义边 → 双人标注 → IAA/裁决 → golden → GATE-RET 分型”产出可复核语料；Tier B（不可再分发）只进隔离评测、不进发布包/golden；0.5 只有在 pilot 的 IAA/证据/语义纯度/graph 分型全部达线后才重跑。

## 1. 规范性条款（C1–C12）

### C1 用户/用途/成功标准
- 服务学习者/教师 + agent；首个 pilot 选 **开放许可教材 1 章**；
- 三层成功标准：① 标注质量（IAA/证据）；② 检索（GATE-RET 分型）；③ graph 分型从 `NOT_APPLICABLE` 变为可评估且达线。

### C2 来源/许可/隐私（R-C0-3）
- **Tier A 可发布**：CC BY / CC BY-SA / CC0 / 公有领域 / 自著且授权；
- **Tier B 仅内部评测**：CC BY-NC / ND / 购买 / 用户授权但不可再分发——隔离副本、不导出原文、**不进发布包/golden**；
- **Tier C 禁用**：许可不明/禁止/无法核实；
- 逐文档 `license/SPDX/redistribution/DB-right/fair-use/PII`；PII 用 Presidio+人工；发布前 NOTICE/许可清单；PII 不入库。

### C3 本体/关系 schema
- 实体：`Document/Section/KP/Cluster`；关系只用 S0 `E_relation_min`：`contain(structural|semantic)/reference/extend`；
- SKOS 仅作概念注释/词表，**不新增图关系**；新增类型须 S0/S1 修订；语义边必须 `label=semantic`/`contain_kind=semantic` 才进 E_sem；结构/引用边不得冒充。

### C4 KP 定义/粒度
- KP = 单文件连续 span、可独立引用/断言的最小语义单元；
- 默认 **1 概念/术语/公式 + 1–3 句解释、单 section、不重叠**；嵌套 future；
- pilot 同时试**命题级**变体，由 C8 IAA 决定采用哪个。

### C5 标注协议
- 先 KP 后边；手册含 **30+ 正例 / 30+ 负例 / 20+ 边界例**；
- 歧义三级裁决（A 标注者自决/B 复核/C Lead 裁决）；培训 + 试标 20 项；
- 标注单位/上下文/字段/导出格式固定；不得边标边改手册（改则重标受影响样本）。

### C6 语义边
- S0 三类型；方向默认 `source→target`，`both` 显式物化两条有向边；
- 每条边有 **双端/断言证据 span**、置信三档（high/medium/low）、理由；
- 负例单列（不应存在的边/结构冒充语义）；跨文档边需更强证据；`E_sem` 门槛与 S10 `SemanticEdge` 一致。

### C7 规模/采样/金标准
- pilot：1 章 / **50 KP / 30 边 / 20 query**；
- 主集：10 章 / 500 KP / 300 边 / 100 query；
- 按章分层、dev/test 隔离；`edition = sha256(files + annotations + manual)`；
- pilot 预算上限 **2 人 × 2 天 ≈ 32 人时**，记录实际工时；超预算缩规模，不降质量。

### C8 质量/IAA（R-C0-1）
- pilot **100% 双人独立**；10% 抽检 + 裁决记录；
- KP **span/边界**：Krippendorff unitizing α（或 exact-boundary/overlap F1）；
- KP **类型/方向**：Cohen/Fleiss κ；
- 语义边：**tuple-set F1**（类型+方向+端点）+ 裁决一致率；
- 合格线：span α≥0.67、κ≥0.67、边 tuple F1≥0.70；目标 0.8；**分指标报告**（observed/expected/缺失/样本量/裁决数）；不达线不扩主集。

### C9 评测协议
- 三层：检索（recall@5/NDCG@10/MRR）、链路（正确率/可复述/支撑推理）、任务（人判 A/B）；
- GATE-RET **按 query_type 分型**（keyword/vector/hybrid/graph）；graph 仅在库有语义边时适用，0 命中 FAIL；`NOT_APPLICABLE` 不算通过；
- 消融：去掉语义边/某类边，任务是否变差；禁止合成数据/聚合掩盖。

### C10 工具/工作流
- 标注在**隔离副本**；用户库只读；INCEpTION/brat 候选；导出 JSONL/standoff/CoNLL-U/Croissant；
- 校验：schema/证据锚/许可/UTF-8 offset；版本+审计；**不写用户 sidecar**；Tier B 隔离不导出。

### C11 与 S10/0.5 衔接（R-C0-6）
- S10 agent 只 `propose_write` + evidence；人工确认后产品 curation writer apply；写后 edition→S9 失效/重建；
- 0.5 重跑门槛：① C8 IAA 达线；② `Q-EVIDENCE=100%`、`Q-SEM-PURITY=1.0`；③ graph 分型适用且 `recall@5≥0.80`、`sem_purity=1.0`；④ 无事实/无 sidecar 写；⑤ 2× 确定性。
- 未满足则 0.5 保持 HOLD。

### C12 交付/维护
- 交付包：语料快照 + golden + 标注手册 + 许可清单/NOTICE + Datasheet/Data Statement + Croissant 元数据 + 评测脚本 + 变更日志；
- 维护：owner/节奏/edition/废弃策略；避免一次性 demo；Tier B 不进发布资产。

## 2. 跨议题裁决（R-C0-1..R-C0-6）

见 `C0-RULINGS.md`：IAA 分型；URL 核验；许可三层；并集；粒度/成本；0.5 门槛。

## 3. C0a 待定（SE 校核）

- **URL 核验（核心证据政策）**：核心证据每 C 项 ≥2 条 HTTP 200+标题；`C0-URL-VERIFY.json` 保留 30 PASS / 5 FAIL / 3 BLOCKED；8 个失败/阻断项按 `C0-URL-DISPOSITION.md` 删除或降级为“未核验背景”，**不得冒充 200**；不再要求“提案中每个 URL 都 200”（反爬环境不可控）。
- **GATE-RET 可执行契约**：合并 A 三层/B 命令，冻结唯一脚本/产物/JSON sha/exit；graph 阈值 soft 直至 pilot。
- **unitizing α 实现**：脚本/成熟库 + 单测；INCEpTION 导出 UTF-8 offset 后跑，报告 α/observed/expected/缺失。
- **标注 schema/工具状态图**：ER（Concept/KP/Relation/EvidenceSpan/Annotation/Curation/Quality）；状态 `draft/annotating/review/conflict/adjudicated/frozen`；`PARSE_OK`。

## 4. 冻结前门禁（SE + Lead）

M-C0-1 来源/许可/Tier；M-C0-2 本体/关系/E_sem；M-C0-3 KP 粒度/边界；M-C0-4 标注协议；M-C0-5 边证据/方向/负例；M-C0-6 规模/采样/edition；M-C0-7 IAA 分型/阈值；M-C0-8 评测分型/消融/禁聚合；M-C0-9 工具只读/版本/审计/UTF-8；M-C0-10 S10/0.5 门槛；M-C0-11 交付/维护/数据卡；M-C0-12 URL 核验 + 图 `PARSE_OK`。

## 5. 冻结后

- 先做 pilot（1 章/50 KP/30 边/20 query，32 人时上限），报告 IAA/证据/成本；
- pilot 达线 → 0.5 重跑 GATE-RET → 再讨论 0.5 发布；未达线 → 修订 C 系列。

## 6. 变更控制

- 加字段/指标/工具：C 系列修订 + 决策；删/改许可边界/本体/标注协议/评测门槛：重开对应 C 项；pilot 实测数据写回修订（不重开）。
