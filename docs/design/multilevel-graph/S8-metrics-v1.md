# S8 度量与验收 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`；`S8-charter.md`；`S8-RULINGS.md`。
> **上游冻结**：S0–S7 八份 v1 + `S3-ADDENDUM-1`、`S6-ADDENDUM-1` —— 不得违反。
> **输入**：A-v2（`7459b957…`）、B-v2（`76707304…`）、异议-v2（`0234364a…`）。
> **状态**：冻结候选 v1，待 SE 工程校核（task-333）与 Lead 独立机检后冻结；冻结前不写产品代码。

---

## 0. 一句话口径

每个指标必须有**定义/公式/阈值/命令/证据路径/失败语义**；P0 硬门禁全部机器可判（exit code + 产物 sha），soft 指标只做趋势/相对回归；G6 快照唯一落 `.memoria/agent/audit/graph/g6/`，G7 只存引用/counts、无正文；0.5 DoD 按 I-01..I-13 逐项阻断。

## 1. 规范性条款（S8-1..S8-12）

### S8-1 指标框架与优先级
- **7 类**：正确性、确定性、性能、可解释性、agent（G7）、数据质量、回归；**P0 硬门禁**（命令/exit/产物 sha，失败阻断）vs **soft**（趋势/相对回归，不阻断发布但需记录）。
- **禁止单一指标掩盖失败**；每指标必须给定义/公式/阈值/证据/失败语义；soft 不得写成 P0，P0 不得下调阈值。
- **机检**：指标表完整性；P0 有命令与产物；soft 标注。

### S8-2 G6 快照冻结
- 字段严格 = S6 `G6_SNAPSHOT`（`g6_version/data_source_sha/run_ids/registry_sha/vm_sha/frame_ids/frame_sha/nav_sha/rule_histogram/counts/subset_ok/determinism_sha/closure_violations/behind_violations/history_signed`）。
- **唯一路径** `.memoria/agent/audit/graph/g6/<snapshot_id>.json`（基线/CI 事实源）；`artifacts/agent/verify/graph/g6/` 只放报告副本；
  `snapshot_id = sha256(canonical(G6_SNAPSHOT without snapshot_id))`；不可变；基线更新需 `decision_id`，旧快照保留；G6 ≤1MB。
- **机检**：字段 == S6；路径唯一；sha 可复算；快照只追加。

### S8-3 正确性/确定性（P0）
- HAC 两次运行一致（determinism 100%）；`run_id` 可复算；registry 链/只增不删；presence/rule_id 完整；`subset_ok=true`；`closure_violations=0`、`behind_violations=0`；tie-break 确定性。
- `C-REGISTRY`：`signed=false` 记录但**不算失败**（S6 可选签名）。
- **机检**：命令 + G6/DIFF 产物 sha。

### S8-4 性能/预算
- **冻结值（S3/S4 来源）**：`max_nodes=200`、`max_edges=400`、60fps（2D）、30fps（3D）、动画 ≤180ms。
- **假设值（需实测基线，未校准前只 soft/相对回归）**：P95 交互 ≤200ms、首开 ≤1500ms、切页签 ≤300ms、Admission ≤50ms。
- 测量条件：冷/热、参考硬件、样本 N≥30；CI 无 GPU 只跑结构性 P0，性能在本地参考硬件；相对回归 ±20% 告警。
- **机检**：冻结值 P0；假设值标 `hypothesis`；环境记录。

### S8-5 可解释性/UX
- `X-RULE = (non-shown nodes with rule_id + non-shown edges with rule_id) / (all non-shown nodes + all non-shown edges)` = **100%**；`X-NODE-RULE`/`X-EDGE-RULE` 分项；`rule_id=null` 的 non-shown 记 FAIL。
- `X-SUMMARY` 对齐 S4 `suppressed_summary{rule_id:count}` + `rule_histogram`；unknown 必须有 `reason`；`truncated` 可见；降级必须 banner/aria/事件可见；**无静默**。
- **机检**：VM/Admission fixture（节点+边）+ DOM/aria/事件/快照，不靠人工。

### S8-6 G7 agent 指标
- **P0**：`write_attempts=0`、只读 100%；G7 引用 G6 `run_ids/frame_ids`；**无正文/excerpt/PII**。
- **soft**（S8 冻结建议值）：引用完整率 ≥99%、unknown ≤20%、token/call ≤4000、calls ≤8。
- 保留：90 天或 100k 条 / ≤64MB；只存 id/anchor 引用/counts。
- **机检**：G7 envelope；G-G7 gate。

### S8-7 数据质量（semantic only）
- `D-SEM-PURITY` P0：μ/β 输入 == `E_sem`；结构/`reference` 边不计入、不得伪造；
- `semantic edge/KP coverage`、`no_semantic` 比例、簇覆盖、curation 比例为**语料信号**，不设 P0 下限（避免用结构边凑数）；`no_semantic_edges` 合法 ≠ `algorithm_failed`。
- **机检**：输入集合 == E_sem；信号记录；无伪边。

### S8-8 故障注入/回放
- **8 类**：预算、空语义、stale、缺失、非法输入、审计失败、renderer budget（`RENDER_BUDGET_EXCEEDED`）、S9 unavailable（`GRAPH_RETRIEVAL_UNAVAILABLE`）。
- 预期：可见错误/降级 + `rule_id/degraded_reason`；确定性回放（同快照 sha）；G6 diff；无静默。
- **机检**：失败注入 fixture；exit/产物 sha。

### S8-9 回归门禁/CI
- **P0 CI gates**：schema、determinism、presence/X-RULE、subset、closure/behind、audit、no-write、G6 snapshot sha、mermaid parse、**G-G7**（`write_attempts=0`/`read_only=100%`/引用 G6/无正文-excerpt-PII）。
- flaky：P0 不 flaky；诊断性重试 ≤3；阈值不得因 flaky 下调；本地 vs CI 同 harness；CI 无 GPU 性能只本地。
- **机检**：每个 gate 有命令/exit/产物 sha；失败阻断。

### S8-10 0.5 验收清单（DoD）
- **I-01..I-13** 逐项验收；**I-05/I-06/I-07/I-08 为 P0 阻断**（I-07 只验 2D；3D 同签名接口 + `capability=false` 不阻断），其余 P1。
- **不做**：3D 实现、agent 写、自动 semantic、跨库、时间维、图编辑器、破坏性迁移；S7–S10 设计不在 0.5。
- **退出**：P0 全 PASS 才可发 0.5；P1 有记录。

### S8-11 度量存储/隐私/成本
- G6 快照/基线不 GC（永久，≤1MB/份）；G7 90 天或 100k 条/≤64MB；只存 id/anchor 引用/counts，**不存正文/excerpt/PII**；删除/重建不影响事实。
- **机检**：保留策略；无正文扫描；大小上限。

### S8-12 与 S9/S10 边界
- S9 检索质量、S10 KP 质量归各自；S8 只消费指标/定义 gate，不实现其算法/阈值；`candidate_ref`/KP 质量 schema 归 S9/S10。
- **机检**：无越界 schema；边界记录。

## 2. 跨议题裁决（R-S8-1..R-S8-6）

- **R-S8-1**：X-RULE 节点+边联合分母 100% + 分项；null FAIL。
- **R-S8-2**：G6 唯一路径 `.memoria/agent/audit/graph/g6/`；artifacts 只报告；snapshot_id 公式；基线 decision_id/旧快照保留。
- **R-S8-3**：CI P0 加 `G-G7`。
- **R-S8-4**：S3/S4 冻结值 vs 假设值分离；假设需基线；冷热/硬件/N≥30。
- **R-S8-5**：故障 8 类；flaky 统一；signed=false 不失败。
- **R-S8-6**：X-SUMMARY 对齐 S4；DoD I-07 2D P0/3D false；G7 隐私/保留。

## 3. 冻结前机检（SE + Lead）

M-S8-1 指标框架；M-S8-2 G6 字段/路径/sha/不可变；M-S8-3 正确性/确定性；M-S8-4 性能冻结/假设/环境；M-S8-5 X-RULE 节点+边/X-SUMMARY/降级；M-S8-6 G7/G-G7/隐私；M-S8-7 semantic-only；M-S8-8 故障 8 类/回放；M-S8-9 CI gates/flaky；M-S8-10 DoD；M-S8-11 存储/隐私；M-S8-12 S9/S10 边界 + 工程图 `PARSE_OK`。

## 4. 冻结后

- S9（后端检索）、S10（agent 设计知识点）按议程；
- 0.5 实现按 S6a I-01..I-13 + 本场 DoD 执行；实现前先补 G6/G7 命令与基线（S8a/SE 定稿）。

## 5. 变更控制

- 加指标/阈值/gate：S8 修订 + 决策；删/改 P0 门禁/G6 字段/DoD：重开 S8；假设值校准后写回 S8 修订（不重开）。
