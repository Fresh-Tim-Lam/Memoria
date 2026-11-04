# S10 提案 A-v2：agent 设计 KP 与语义边（curation 写路径、证据、质量与 0.5 边界）

> **修订依据**：`docs/design/multilevel-graph/S10-RULINGS.md` + `S6-ADDENDUM-2.md`（R-S10-1..5）。
> **本文件**：A 修订版；**不覆盖** `S10-kp-proposal-A.md`（v1 `d0a09404…`），保留审计链。

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-342｜**日期**：2026-11-04（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35，重点 U-12/13/14/19/21/22/25/27/32）。
> **上游冻结（不得违反）**：S0–S9 十份 v1 + `S3-ADDENDUM-1` + `S6-ADDENDUM-1`。
> **本场章程**：`docs/design/multilevel-graph/S10-charter.md`（S10-1..S10-12）。
> **工程输入**：`ENGINEERING-PLAN.md`（30 图、I-01..I-13）；现有写路径 `src/memoria/services/agent/plan.py`/`apply.py`/`backup.py`/`approvals.py`（只读证据）。
> **独立性**：未阅读 S10 复核方草稿；本提案独立撰写。
> **纪律**：只写未来 curation 设计规格；**0.5 不实施**；不写产品代码；不改 S0–S9 冻结稿；不 commit。

---

## 0. 总口径

```
S10（未来版本）= agent 在证据锚 + 人工确认下，写 KP 元数据/语义边/curation provenance；
不写事实正文；不自动 apply；0.5 不做；写路径 propose_write → plan evidence → 人工确认 → atomic apply → backup/undo/audit。
结构/引用边不得当语义边；语义边只来自 label=semantic 且证据可解释。
```

**证据等级**：A（冻结条款/工程/代码事实）；B（实测产物）；C（推理）；**本项目假设**（字段名/阈值/未来工具名）。

---

## 1. S10-1 定位与边界

**定义/规则（一句话）**：agent **只产 `propose_write`**（KP/边/curation 提案 + evidence），**不写任何文件**；apply 由产品 curation writer 在人工确认后执行；**0.5 不做**。

**形式化**：
```
agent 允许：propose_write(KP/边/curation) + evidence + 只读校验
agent 禁止：写任何文件（含 .md/sidecar/manifest/registry）、apply、自动 semantic、
            结构/引用边伪装语义、绕过审批
apply 所有者：产品 curation writer（人工确认后）执行 plan/approval/backup/atomic/undo/audit
graph/agent 服务：无 sidecar/正文写权限；只产提案
S0-10 三层：L_kp（agent 设计 KP）/L_sem（写语义需证据+审计）/L_view（只读）
S6 单一真源：事实仍 .md+sidecar/manifest；curation 元数据只写 S6 白名单
0.5：明确不做；S10 设计不影响 0.5 DoD
```
**反例**：agent 写文件/apply；自动写 sidecar；结构/引用伪装 semantic；无人工确认 apply；0.5 开写工具。
**边界**：无源；低置信；冲突；批量；未来版本。
**机检条件**：
```
- agent 只产 propose_write（op 白名单 kp.*/edge.*/curation.*）；无任何文件写
- apply 仅由产品 curation writer 在 approval 后执行；graph/agent 无 sidecar/正文写
- 0.5 无 S10 写工具/默认关闭
- E_sem 门槛见 S10-4；结构/引用不冒充
```
**U 映射**：U-12、U-13、U-14、U-32、U-34。
**建议裁决**：agent 只 propose_write；apply 归产品 curation writer（人工确认）；无 sidecar/正文写；0.5 不做。
**证据等级**：A（S0-10；S6-1；S7-6；S10 章程）；**本项目假设**（未来工具名）。

---

## 2. S10-2 KP 定义 / 粒度 / 字段

**定义/规则（一句话）**：KP = 可标注的语义单元，锚定到 md 的连续 range；title/alias/summary 是元数据，不改正文；KP range 与 section/KP range 关系明确。

**KP schema**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `kp_id` | string | 全局唯一（语料内） | `GRAPH_KP_INVALID` |
| `title` | string | 非空；≤120 字符 | `GRAPH_KP_INVALID` |
| `aliases[]` | string[] | 默认 `[]`；去重 | `GRAPH_KP_INVALID` |
| `summary` | string | ≤500 字符；可空 | `GRAPH_KP_INVALID` |
| `file` | string | KB 相对路径 | `GRAPH_KP_INVALID` |
| `range` | object | `{start:{line,anchor?},end:{line,anchor?}}` | `GRAPH_KP_INVALID` |
| `section_ref` | object? | `{heading,line,anchor}` | `GRAPH_KP_INVALID` |
| `tags[]` | string[] | 默认 `[]` | `GRAPH_KP_INVALID` |
| `evidence` | object | `{file,line_start,line_end,anchor_id}` | `GRAPH_KP_EVIDENCE_MISSING` |
| `confidence` | float | 0..1；默认 0 | `GRAPH_KP_INVALID` |
| `status` | enum | `proposed/approved/rejected/merged`；默认 proposed | `GRAPH_KP_INVALID` |
**粒度/关系规则**：
```
KP range 必须落在单文件内；默认不跨 section；一个 section 可含多个 KP；
KP 不改变正文；range 必须命中真实文本（anchor/line 可解析）
最小：可标注短语/句（非空 anchor）；最大：单 section（禁止整文档）
同文件 KP range 默认不重叠；允许嵌套时须显式 parent_kp_id 且人工确认
section 是结构容器，不等于 KP；section_ref 只引用不写正文
```
**反例**：整篇文档一个 KP；跨文件 range；无 anchor；summary 当正文；KP 重叠未标 parent。
**边界**：标题行；无 section 文档；代码块；超大 section。
**机检条件**：
```
- schema 字段/类型/枚举/默认/失败码；range 可解析
- 单文件/单 section/长度上限；不写正文
- 重叠需 parent 且人工确认
```
**U 映射**：U-12、U-19、U-21、U-22。
**建议裁决**：采纳 KP schema/粒度/单 section/不写正文。
**证据等级**：A（S0-4 KP 语义单元；`plan.py:346-405` upsert_kp 字段/range）；**本项目假设**（长度/嵌套规则）。

---

## 3. S10-3 KP 抽取 / 生成

**定义/规则（一句话）**：从 md/sidecar 抽取 KP 候选；每条必须有证据锚（file/line/anchor），不得编造；低置信不 apply；幂等/去重。

**形式化**：
```
输入：DataSource（md 正文只读）+ 现有 sidecar KP/links（只读）
输出：KPProposal{kp_id?, title, aliases[], summary, file, range, evidence,
                 confidence, reason, source_hash}
证据锚：file + line_start/end + anchor_id；原文片段只读（不写回）
置信：confidence∈[0,1]；低于 τ_kp（S10a，如 0.6）⇒ 不进入 apply 候选
不得编造：无源/锚不命中 ⇒ rejected/unknown，不生成 KP
幂等：同 (file, kp_id) 更新；同 anchor+normalized title 去重；重复提交不重复写
```
**反例**：无 anchor 生成 KP；锚不命中仍写；低置信自动 apply；重复创建同 KP。
**边界**：无源；歧义标题；sidecar 缺失；跨语言别名。
**机检条件**：
```
- 每条 proposal 有 file/line/anchor；锚可解析
- confidence 阈值；低置信不 apply
- 幂等键/去重键可复算
- 不写正文；无编造（无源即 rejected）
```
**U 映射**：U-12、U-13、U-14。
**建议裁决**：采纳证据锚/不编造/低置信不 apply/幂等去重。
**证据等级**：A（S0-10；现有 kp_index/plan 校验）；**本项目假设**（阈值）。

---

## 4. S10-4 语义边设计

**定义/规则（一句话）**：语义边允许 S0 `E_relation_min` 全部类型（contain/reference/extend）；只有 `label=semantic` 或 `contain_kind=semantic` 进 `E_sem`；结构/引用不得冒充语义；每条边可解释。

**SemanticEdge schema**：
| 字段 | 类型 | 枚举/默认 | 失败码 |
|---|---|---|---|
| `edge_id` | string | canonical(type|source|target) | `GRAPH_EDGE_INVALID` |
| `type` | enum | `contain`/`reference`/`extend`（S0 E_relation_min） | `GRAPH_EDGE_INVALID` |
| `contain_kind` | enum|null | `structural`/`semantic`；type=contain 必填，否则 null | `GRAPH_EDGE_INVALID` |
| `label` | enum|null | `semantic`/`structural`；reference/extend 可 semantic（需证据）；contain(structural) 不得 semantic | `GRAPH_EDGE_INVALID` |
| `source_id`/`target_id` | string | KP id；不相等 | `GRAPH_EDGE_INVALID` |
| `direction` | enum | `source_to_target`/`both`；默认 source_to_target | `GRAPH_EDGE_INVALID` |
| `evidence` | object | `{file,line_start,line_end,anchor_id}`；双端或断言源 | `GRAPH_EDGE_EVIDENCE_MISSING` |
| `confidence` | float | 0..1 | `GRAPH_EDGE_INVALID` |
| `reason` | string | 可解释；非空 | `GRAPH_EDGE_INVALID` |
| `provenance` | object | 见 S10-5 | `GRAPH_EDGE_INVALID` |
**规则**：
```
只写 KP↔KP（不写文件边/跨 KB）；contain 由系统派生/不手标 structural；
E_sem = {contain_kind=semantic} ∪ {reference/extend 且 label=semantic 且证据支持}；
contain(structural)/无 label 的 reference/extend 不得计入 E_sem/μ/β/语义分；
方向允许 source_to_target 或 both（both 须显式、双向语义同源）；
新增类型须 S0/S1 修订；边可解释：reason+evidence 可复述；不得无证据建边
```
**反例**：contain(structural) 标 semantic；无证据 reference 标 semantic；新增未登记类型；跨 KB；自环。
**边界**：同义/反向边；多证据；低置信；冲突。
**机检条件**：
```
- type/contain_kind/label/方向/schema；只有 label=semantic 或 contain_kind=semantic 进 E_sem
- contain(structural)/无 semantic label 的边不计 μ/β/语义分；新增类型须 S0/S1
- 每条边有 evidence+reason；无自环/跨 KB
```
**U 映射**：U-13、U-14、U-27。
**建议裁决**：采纳 S0 全类型（contain/reference/extend）+ E_sem 门槛 + 证据/方向 both/可解释。
**证据等级**：A（S0-3 R-1；S2-2/3 semantic-only；`plan.py:892-954` edge 校验）；**本项目假设**（字段/阈值）。

---

## 5. S10-5 双引用 / curation / 人工确认 / undo

**定义/规则（一句话）**：每条 KP/边有双引用 provenance（source/target/assertion_source）+ `curated_by/curated_at`；人工确认才 apply；可 undo。

**Provenance schema**：
```
Provenance{
  source_id, target_id?, assertion_source{file,line_start,line_end,anchor_id},
  evidence_refs[], curated_by, curated_at, decision_id, method:"agent"|"human",
  review_status:"proposed"|"approved"|"rejected", undo_ref?
}
规则：
  双引用：source_id/target_id + assertion_source；不可只写一端
  curated_by/curated_at 必填；method 区分 agent/human
  人工确认：approval_id 必需；未确认 status=proposed，不 apply
  curation 元数据白名单：curated_by/curated_at/decision_id/evidence_refs/undo_ref；只写 S6 白名单
  undo：保留 before/after + undo token；可恢复到 apply 前
```
**反例**：无 target/assertion_source；无 curated_by；未确认 apply；无 undo。
**边界**：批量；多人确认；冲突；撤销后重提。
**机检条件**：
```
- provenance 字段完整；双引用可解析
- apply 前 review_status=approved + approval_id
- undo_ref/审计可追溯
```
**U 映射**：U-21、U-22、U-29。
**建议裁决**：采纳双引用/ curated_by/at/人工确认/undo。
**证据等级**：A（S0-10；S6-3 curation；现有 approvals/backup）；**本项目假设**（字段/流程）。

---

## 6. S10-6 写路径（propose_write/plan/atomic/backup/undo/audit）

**定义/规则（一句话）**：agent 只 `propose_write`；apply 由产品 curation writer 在人工确认后执行 `plan → approval → atomic → backup → undo/audit`；禁止绕过；失败零写入。

**WritePlan schema**：
```
WritePlan{plan_id, kb_id, expected_edition, ops[], approvals[], evidence[],
          backup_id?, created_by, created_at, status}
WriteOp{
  op_id, op_type ∈ {kp.upsert,kp.alias,kp.merge,edge.upsert,edge.retract,curation},
  params, preconditions{base_version, anchor_exists, kp_id_unique},
  evidence_refs[], dry_run_result
}
流程：
agent propose_write（无文件写）→ 产品 curation writer validate/plan（无写）
  → 人工 approval → atomic apply → backup → audit → undo token
失败：任一步失败 ⇒ 零写入（no partial）；批处理整体回滚
禁止：agent apply/body/file ops、graph/agent 直接 sidecar、绕过 approval、自动 apply；
approval 缺失 ⇒ GRAPH_CURATION_APPROVAL_REQUIRED
```
**反例**：先写后校验；失败半写；无 backup；无 audit；批次部分成功。
**边界**：并发；edition 变化；审批拒绝；撤销。
**机检条件**：
```
- agent 仅 propose_write；op 白名单无 body/file；无文件写
- apply 属产品 curation writer；approval 后 atomic；失败 snapshot diff=0
- backup/undo/audit 可追溯；批处理事务；graph/agent 无 sidecar 写
```
**U 映射**：U-21、U-29、U-32。
**建议裁决**：agent 仅 propose_write；apply 归产品 curation writer；plan/approval/atomic/backup/undo/audit；失败零写入。
**证据等级**：A（`plan.py/apply.py` 校验/apply、`backup.py`、`approvals.py`；S0-10）；**本项目假设**（未来接口名）。

---

## 7. S10-7 冲突 / 去重 / 合并

**定义/规则（一句话）**：重复 KP/别名/同义边有明确冲突类；保留 vs 合并由人工裁决；历史保留，不破坏性删除。

**冲突规则**：
```
冲突类：kp_id 重复 / title 同 / alias 同 / range 重叠 / 边同型同端 / 反方向 /
       语义冲突（同 pair 不同 type）
处理：
  同 id 同文件 ⇒ update；跨文件 ⇒ 冲突（人工）
  alias/title 同 ⇒ 建议合并（alias 指向 canonical），人工确认
  range 重叠 ⇒ 拒绝或显式 parent；人工确认
  同 pair 同 type ⇒ 去重（幂等）；不同 type ⇒ 保留双（人工）
  合并：保留 canonical id + aliases；旧 id 标 merged/redirect；历史保留
禁止：自动删除/覆盖旧 KP/边；不保留 history 的 merge
```
**反例**：自动覆盖；静默合并；旧 id 丢失；同边重复。
**边界**：同义不同名；多归属；跨文件同名；批量。
**机检条件**：
```
- 冲突类可判定；merge 前人工确认
- 旧 id/边保留 history/redirect；无破坏性删除
- 幂等去重
```
**U 映射**：U-19、U-21、U-22。
**建议裁决**：采纳冲突类/人工裁决/merge 保留历史。
**证据等级**：A（S0-4 KP 身份；S2-7 cluster 身份；现有 kp_id 唯一校验）；**本项目假设**（合并规则）。

---

## 8. S10-8 版本 / 失效 / 回滚

**定义/规则（一句话）**：写后 edition 变化；S9 索引失效/重建；S2 重算；旧 KP/边保留；可回滚。

**形式化**：
```
apply 成功 ⇒ edition_sha 变化 ⇒ S9 invalidate/rebuild；S2 run 新 edition
旧 KP/边/审计保留（只读）；回滚 = restore backup + 新 edition 重建索引
并发：expected_edition 不匹配 ⇒ 拒绝（不覆盖）
```
**反例**：写后不失效；旧索引混用；回滚覆盖历史；edition 不校验。
**边界**：批量写；部分失败；回滚；跨 KB。
**机检条件**：
```
- edition 变化触发 S9 失效；旧数据保留
- 回滚恢复 before image；索引重建
- expected_edition CAS
```
**U 映射**：U-29、U-32。
**建议裁决**：采纳 edition 失效/旧数据保留/回滚。
**证据等级**：A（S6-8/S6-10；S9-11/S9-12）；**本项目假设**（事件形态）。

---

## 9. S10-9 质量 / 评估

**定义/规则（一句话）**：KP/边 precision/recall + golden + 人工抽检 + 阈值；错误类型可归类；S8 消费。

**eval 契约（可执行；R-S10-4）**：
```
golden 路径（唯一）：.memoria/agent/audit/graph/golden/S10-golden-set.json
  （S10a 定稿唯一；不得双源）
golden schema：
  {golden_version, kb_id, edition_sha, kps[{kp_id,file,line_start,line_end,
   anchor_id,title,aliases[],grade 0..3}], edges[{edge_id,source,target,type,
   contain_kind?,label?,grade 0..3,evidence}], sampling{human_sample_n}}
  文件 sha256 可复算；labels 不由 agent 生成
命令：python scripts/verify/eval-kp.py --kb <kb> --golden <golden.json>   --out <metrics.json>
exit：指标满足阈值 ⇒ 0；回归超容差/缺 golden/sha 不符 ⇒ ≠0
指标 JSON：{eval_version, golden_sha, edition_sha, query_count,
  metrics{kp_precision,kp_recall,edge_precision,edge_recall,evidence_rate,
  semantic_purity}, human_sample{n,passed}, passed, failed_metrics[]}
metrics.json sha256 记录；人工抽检样本与阈值写入 golden/报告
阈值（未校准前 soft，S10a 定）：Q-KP-P≥0.9、Q-KP-R≥0.8、Q-EDGE-P≥0.9、
  Q-EDGE-R≥0.8、Q-EVIDENCE=1.0、Q-SEM-PURITY=1.0；S8 消费该命令/产物
```
**指标表（与 eval JSON 对应）**：
| ID | 定义/公式 | 阈值/证据 |
|---|---|---|
| `Q-KP-P` | 人工抽检 correct KP / sampled KP | ≥0.9（soft，S10a 校准） |
| `Q-KP-R` | golden KP 被提出 / golden KP | ≥0.8（soft） |
| `Q-EDGE-P` | correct semantic edge / proposed | ≥0.9（soft） |
| `Q-EDGE-R` | golden semantic edge / found | ≥0.8（soft） |
| `Q-EVIDENCE` | 有可解析证据锚的 KP/边比例 | 100% |
| `Q-SEM-PURITY` | contain(structural)/无 semantic label 边进入 E_sem 次数 | 0 |
**反例**：无 golden/命令/exit；metrics 无 sha；人工抽检样本未记录；结构边算 semantic；阈值未校准当硬。
**边界**：小样本；无 semantic；多语言；golden edition 不匹配。
**机检条件**：
```
- golden 路径/schema/sha 可复算；eval-kp exit=0/非0 可判
- metrics JSON+sha；人工抽检样本/阈值；Q-EVIDENCE=100%；Q-SEM-PURITY=0
- S8 gate 引用命令/产物；阈值未校准标 soft
```
**U 映射**：U-12、U-13、U-14、U-32。
**建议裁决**：采纳可执行 eval 契约（golden/命令/exit/metrics sha/人工抽检/阈值/S8 消费）。
**证据等级**：A（S8-12 边界；S2 semantic-only）；**本项目假设**（golden 路径/命令/阈值）。

---

## 10. S10-10 与 S1 registry / S2 clustering

**定义/规则（一句话）**：KP 目录/ID 注册独立于 S1 维度 registry；写语义边后 S2 重算 membership；多归属合法；不得改 registry 语义。

**形式化**：
```
KP → KP 目录（现有 sidecar/index；非 S1 维度 registry）；kp_id 全局唯一（anchor+label 辅助）
S1 registry：只读；S10 不改维度/关系源；新增维度须 S1 修订
S2：语义边变化触发新 run；KP 可多归属（跨族/层）；稳定性按 S2-5；不自动 adopted
默认单 section/不重叠；嵌套 future；direction 允许 both；merge 保留 canonical+alias+history
S10 未启用时 S7/S9 只读；写后 S9 失效/重建
KP_HISTORY{history_id(content_sha), kp_id, change, before_sha, decision_id, at, curated_by}
  append-only；记录 KP 创建/更新/合并/retract；不覆盖旧版本；与 S1 DIMENSION_HISTORY 分离
```
**反例**：S10 改 S1 registry；把 KP 当维度；写后不重算 S2；强制单归属。
**边界**：多归属；新 KP；semantic 空；run 稳定。
**机检条件**：
```
- S10 无 S1 registry 写；KP 目录独立
- 写后新 run；多归属允许；稳定性可复算
```
**U 映射**：U-6、U-10、U-12、U-21。
**建议裁决**：采纳 kp_id 全局唯一/单 section 不重叠（嵌套 future）/merge 历史/direction both/S10 未启用只读/写后 S9 失效。
**证据等级**：A（S1-2；S2-6/S2-7；S6-3）；**本项目假设**（KP 目录形态）。

---

## 11. S10-11 失败 / 降级 / 隐私

**定义/规则（一句话）**：无源/歧义/低置信/冲突/超预算/隐私风险均可见拒绝；不自动 apply；正文/PII 边界；审计。

**失败矩阵**：
| 场景 | 行为 | 码 |
|---|---|---|
| 无源/锚不命中 | rejected，不生成 | `GRAPH_KP_EVIDENCE_MISSING` |
| 歧义标题/多候选 | 人工裁决 | `GRAPH_KP_AMBIGUOUS` |
| 低置信 | 不进入 apply | `GRAPH_KP_LOW_CONFIDENCE` |
| 冲突 | 人工裁决 | `GRAPH_CURATION_CONFLICT` |
| 超预算（批量/大小） | 分批/拒绝可见 | `GRAPH_CURATION_BUDGET_EXCEEDED` |
| PII/敏感 | 不落盘/脱敏；人工 | `GRAPH_CURATION_PRIVACY_REJECTED` |
**错误码映射（S6-ADDENDUM-2；全部带 audit_id）**：
\GRAPH_KP_INVALID/GRAPH_KP_DUPLICATE/GRAPH_KP_EVIDENCE_MISSING/GRAPH_KP_AMBIGUOUS/GRAPH_KP_LOW_CONFIDENCE\；
\GRAPH_EDGE_INVALID/GRAPH_EDGE_DUPLICATE/GRAPH_EDGE_EVIDENCE_MISSING/GRAPH_EDGE_SEMANTIC_MISMATCH\；
\GRAPH_CURATION_CONFLICT/GRAPH_CURATION_APPROVAL_REQUIRED/GRAPH_CURATION_PRIVACY_REJECTED/GRAPH_CURATION_BUDGET_EXCEEDED/GRAPH_CURATION_ROLLBACK_FAILED\；
未知 \GRAPH_INTERNAL\；legacy/i18n/severity 见 ADDENDUM-2。
**规则**：不自动 apply；正文只读；PII 不入 KP summary/证据；审计保留 decision。
**反例**：低置信自动写；PII 写 summary；冲突静默覆盖；超预算截断不报。
**边界**：部分失败；批量；多语言；敏感语料。
**机检条件**：
```
- 六类失败有可见码/拒绝；不自动 apply
- 无正文写/PII；审计可追溯
```
**U 映射**：U-29、U-32。
**建议裁决**：采纳失败矩阵/不自动 apply/隐私边界。
**证据等级**：A（S0-10；S6-8 审计）；**本项目假设**（码名/策略）。

---

## 12. S10-12 与 0.5 边界

**定义/规则（一句话）**：S10 设计**不在 0.5**；0.5 无写工具/自动 semantic；未来版本实现；只有人工确认 UI 才 apply。

**形式化**：
```
0.5：不做 S10；无 propose_write/apply/自动 semantic；S7 只读；S8 DoD 不含 S10
未来：S10 实现需独立计划；apply 前必须人工确认 UI + approval
不影响 0.5：S10 工具 default off；feature flag；不阻断 G6/G7
```
**反例**：0.5 开自动写；S10 设计夹带实现；无人工确认 apply。
**边界**：0.5 验收；后续版本；回滚。
**机检条件**：
```
- 0.5 无 S10 写工具/自动 apply；feature flag
- 人工确认 UI 才 apply；0.5 DoD 不含 S10
```
**U 映射**：U-32、U-34。
**建议裁决**：采纳 S10 不在 0.5、未来实施、人工确认才 apply。
**证据等级**：A（S6-12；S7-6；S8-10）；**本项目假设**（未来排期）。

---

## 13. 覆盖矩阵

| 侧 | 覆盖 | 落点 |
|---|---|---|
| S0 | 语义/KP/边/单一真源 | S10-1/S10-4 |
| S1 | 维度 registry 只读 | S10-10 |
| S2 | 语义边/簇/多归属 | S10-4/S10-10 |
| S6 | 事实/curation/cache | S10-1/S10-6/S10-8 |
| S7 | 只读消费/写 forbidden | S10-12 |
| S8 | 质量指标消费 | S10-9 |
| S9 | edition 失效/重建 | S10-8 |
| U | U-12/13/14/19/21/22/25/27/32/34 | 各条 |

---

## 14. A-v2 变更表（逐条旧→新）

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S10-4 type 仅 reference/extend，排除 contain | 允许 S0 全部 contain(contain_kind)/reference/extend；E_sem 仅 label=semantic 或 contain_kind=semantic；结构/引用不冒充；新增类型须 S0/S1 | R-S10-1 |
| 2 | S10 用 `S10_*` 错误码 | 删除 S10_*；统一 S6 `GRAPH_*` + `S6-ADDENDUM-2`（GRAPH_KP_*/EDGE_*/CURATION_*），含 legacy/i18n/severity/audit_id | R-S10-2 |
| 3 | S10-1/6 agent 写路径含 apply/sidecar 风险 | agent 只 propose_write，不写任何文件；apply 归产品 curation writer（人工确认后 plan/approval/backup/atomic/undo/audit）；graph/agent 无 sidecar/正文写；失败零写入 | R-S10-3 |
| 4 | S10-9 只有指标名 | 可执行 eval：golden 路径/schema/sha、`eval-kp` 命令/exit、metrics JSON+sha、人工抽检/阈值、S8 消费 | R-S10-4 |
| 5 | S10-4/10 direction/身份/边界未钉 | kp_id 全局唯一；单 section/不重叠；嵌套 future；merge canonical+alias+history；direction both；S10 未启用 S7/S9 只读；写后 S9 失效 | R-S10-5 |

## 15. 仍存争议 / 待 Lead·SE 裁决

1. **S10 是否仍是 0.5 后第一优先**：本提案明确不在 0.5；实施顺序需 roadmap。
2. **KP 粒度/嵌套**：单 section/不重叠为默认；嵌套 parent 是否允许需 S10a/UX。
3. **语义边类型集合**：S0 只给 reference/extend/contain；S10 是否允许新增语义关系类型需 S1/S0 修订。
4. **低置信阈值/ golden 规模**：0.6/0.9 等为建议，需实测/人工校准。
5. **合并策略**：保留双 id vs redirect 的默认需 S10a；历史保留已定。
6. **写路径是否复用现有 plan/apply**：本提案倾向复用并限制 op 白名单，需 SE 校核。

---

## 16. 证据锚

```text
原话：vision.md:27-36（U-10..U-15, U-19）、:66（U-27）、:71（U-32）
S0：S0-terms-v1.md:35-41（E_relation_min/R-1）、:43-47（簇/KP）、:81-85（agent 三层）、:100-107（D-3）
S1：S1-dimensions-v1.md:22-51（registry 只读）、:99-107（present）
S2：S2-clustering-v1.md:17-28（semantic-only/μ/β）、:42-51（多归属/run）、:73-76（no_semantic）
S6：S6-contract-v1.md:17-19（单一真源）、:32-36（run/membership）、:57-61（audit/cache）
S7：S7-agent-v1.md:16-18（只读）、:47-49（写 forbidden）
S9：S9-retrieval-v1.md（edition 失效/重建）
工程：ENGINEERING-PLAN.md:933-945（I-01..I-13）、:1219（P1 KP 索引）
现有写路径：plan.py:346-405（upsert_kp）、:892-954（edge 校验）、apply.py:249（compile_plan）、backup.py；approvals.py
```
