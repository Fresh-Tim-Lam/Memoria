# S10 agent 设计知识点与语义边 · 冻结稿 v1（候选）

> **依据**：`multilevel-graph-vision.md`；`S10-charter.md`；`S10-RULINGS.md`。
> **上游冻结**：S0–S9 十份 v1 + `S3-ADDENDUM-1`、`S6-ADDENDUM-1/2` —— 不得违反。
> **输入**：A-v2（`db71ccd4…`）、B-v2（`48d8760d…`）、异议-v2（`22238f80…`）。
> **状态**：冻结候选 v1，待 SE 工程校核（task-344）与 Lead 独立机检后冻结；S10 不在 0.5。

---

## 0. 一句话口径

agent **只产 KP/语义边/curation 提案**（`propose_write` + 证据锚），**不写任何文件**；人工确认后由**产品 curation writer** 执行 plan/approval/backup/atomic/undo/audit；语义边允许 S0 全类型、只有 semantic 标记进 `E_sem`；错误码统一 `GRAPH_*` + `S6-ADDENDUM-2`；**S10 不在 0.5**。

## 1. 规范性条款（S10-1..S10-12）

### S10-1 定位与边界
- agent 只产 KP 元数据/语义边/curation **提案**；**不写事实正文/不写文件/不写 sidecar**；`propose_write` 唯一入口；人工确认；0.5 不做。
- **机检**：无写路径；只 propose；无 sidecar/正文写。

### S10-2 KP 定义/粒度/字段
- KP = 可标注语义单元，锚定连续 range；字段 `kp_id/title/alias[]/summary/file/range{start_line,end_line}/section_ref/tags[]/evidence[]/confidence/status`；`kp_id` **全局唯一**；默认单 section/不重叠；嵌套 future。
- **机检**：字段；唯一 id；range 合法；无重叠。

### S10-3 KP 抽取/生成
- 从 md/sidecar **只读**抽取；每条提案有 `file/line/anchor/evidence`；无源不生成；低置信不 apply（`GRAPH_KP_LOW_CONFIDENCE`）；幂等/去重（`GRAPH_KP_DUPLICATE`）。
- **机检**：证据锚；无源拒绝；低置信拒绝；幂等。

### S10-4 语义边
- `type ∈ {contain, reference, extend}`；`contain.contain_kind ∈ {structural, semantic}`；`E_sem = (contain ∧ contain_kind=semantic) ∪ (reference|extend ∧ label=semantic)`；结构/引用边不得标 semantic、语义贡献=0（`GRAPH_EDGE_SEMANTIC_MISMATCH`）；`direction ∈ {source_to_target, both}`；`both` **物化为两条有向边**（共享证据），非第三种语义；每条边有 evidence/confidence/reason。
- **机检**：全类型；E_sem 门槛；结构不冒充；both 物化；证据。

### S10-5 双引用/curation
- `Provenance{source_id,target_id,assertion_source,evidence_refs,curated_by,curated_at,decision_id}`；人工确认；undo；审计；`curated_by/at` 必填。
- **机检**：双引用；必填；人工确认；undo。

### S10-6 写路径（D-3）
- agent 只 `propose_write`（plan/evidence/dry-run/影响面）；**apply 由产品 curation writer** 在人工确认后执行 `plan → approval → backup → atomic apply → undo/audit`；graph/agent **无 sidecar/正文写权限**；失败零写入；批处理可回滚（`GRAPH_CURATION_ROLLBACK_FAILED`）。
- **机检**：propose-only；无 sidecar 写；零写入；审计；回滚。

### S10-7 冲突/去重/合并
- 冲突类：同 id/同 name/同 pair 同 type/跨文件；去重；合并保留 `canonical + alias[] + history/redirect`；人工裁决；历史不删。
- **机检**：冲突码；去重；merge 历史。

### S10-8 版本/失效
- 写后 edition 变化 ⇒ S9 索引失效/重建、S2 新 run；旧 KP/边/审计保留；`expected_edition` CAS；backup 回滚。
- **机检**：edition；S9 失效；旧数据保留；回滚。

### S10-9 质量/评估（可执行）
- 指标：`Q-KP-P/Q-KP-R/Q-EDGE-P/Q-EDGE-R/Q-EVIDENCE/Q-SEM-PURITY`；`Q-EVIDENCE=100%`、`Q-SEM-PURITY=1.0`（结构/引用边不得计入）；`Q-KP-P≥0.90`、`Q-KP-R≥0.80`、`Q-EDGE-P≥0.90`、`Q-EDGE-R≥0.80` 为 **soft（待校准）**；`confidence τ=0.6`（soft）。
- **golden**：`docs/design/multilevel-graph/golden/S10-golden-set.json`（schema/sha，含 no-semantic/多语言子集）；**命令** `python scripts/verify/eval-kp.py --kb <kb> --golden <path> --out <metrics.json>`；exit 0/非 0；metrics JSON+sha；2× 确定性；人工抽检 20/批；S8 消费。
- **机检**：golden；eval exit；metrics sha；2×；阈值 soft 标注。

### S10-10 与 S1/S2 交互
- KP 目录/KP_HISTORY 独立于 S1 维度 registry（S1 只读）；写语义边后 S2 重算；多归属合法；不强制单归属。
- **机检**：S1 只读；S2 重算；多归属。

### S10-11 失败/降级/隐私
- 无源/歧义/低置信/冲突/超预算/PII 可见拒绝；**不自动 apply**；正文只读、PII 不入库；审计；错误码统一 `GRAPH_*` + `S6-ADDENDUM-2`。
- **机检**：失败码；不自动 apply；隐私；审计。

### S10-12 与 0.5 边界
- S10 **不在 0.5**；0.5 无写工具/自动 semantic；未来版本 + 人工确认 UI 才 apply；不影响 0.5 DoD。
- **机检**：0.5 无 S10 写；边界。

## 2. 跨议题裁决（R-S10-1..R-S10-5）

- **R-S10-1**：语义边全类型 + E_sem 门槛；结构/引用不冒充；新类型须 S0/S1 修订。
- **R-S10-2**：统一 `GRAPH_*` + `S6-ADDENDUM-2`；禁 `S10_*`。
- **R-S10-3**：agent 只 propose_write；apply 由产品 curation writer 人工确认后执行；无 sidecar/正文写。
- **R-S10-4**：质量 eval 可执行；阈值 soft。
- **R-S10-5**：kp_id 唯一；单 section；merge 历史；direction both（物化两条）；元数据白名单；S10 未启用 S7/S9 只读；写后 S9 失效。

## 3. S10a 定稿（候选，SE 校核）

- golden 唯一路径 `docs/design/multilevel-graph/golden/S10-golden-set.json`；eval `scripts/verify/eval-kp.py`；产物 `artifacts/agent/verify/graph/kp/<run>.json`；`GATE-KP`。
- curation 元数据/KP_HISTORY 只写 `.memoria/agent/audit/graph/curation/`（append-only，不 GC）；KP 事实定义存 sidecar（由产品 curation writer 在人工确认后写）；graph/agent 无 sidecar 写权限。
- `direction=both` 物化两条有向边（共享 evidence）；不是第三种语义。
- Q-EVIDENCE/Q-SEM-PURITY 为 P0；P/R 与 τ 为 soft，基线与 golden 校准后写回 S10 修订。

## 4. 冻结前机检（SE + Lead）

M-S10-1 边界；M-S10-2 KP 字段/唯一/不重叠；M-S10-3 证据/无源/低置信/去重；M-S10-4 全类型/E_sem/both；M-S10-5 双引用/curated/undo；M-S10-6 propose-only/D-3/零写/审计；M-S10-7 冲突/合并；M-S10-8 edition/S9/回滚；M-S10-9 eval/golden/sha/2×；M-S10-10 S1/S2；M-S10-11 失败/隐私；M-S10-12 0.5 + 工程图 `PARSE_OK`。

## 5. 冻结后

- S0–S10 全部冻结；0.5 实现按 S6a I-01..I-13 + S8 DoD + S9 检索契约；S10 进入未来版本 roadmap（人工确认 UI 才 apply）。

## 6. 变更控制

- 加字段/指标/阈值：S10 修订 + 决策；删/改 KP 定义/语义边语义/写边界：重开 S10；阈值校准写回修订（不重开）。
