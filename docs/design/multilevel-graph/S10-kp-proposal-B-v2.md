# S10 agent 设计知识点与语义边提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S10-RULINGS.md`（R-S10-1..R-S10-5）+ `S6-ADDENDUM-2.md`；上游冻结 S0（`241b1e1e…`）、S1（`6676c71d…`）、S2（`92bb0041…`）、S3（`0ca4ea0e…`+ADDENDUM-1）、S4（`2576f6c8…`）、S5（`7f4c4515…`）、S6（`40f12e5f…`+ADDENDUM-1/2）、S7（`70dd8748…`）、S8（`c6a135ff…`）、S9（`42f36423…`），不得违反。
> **输入**：B v1（`b323c82b…`）、A v1（`d0a09404…`）、`S10-objections.md`（`ea21e5d8…`）。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S10-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S10-RULINGS/S0–S9 冻结。
> **日期**：2026-11-04（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S10）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S10-4 | 语义边类型含 contain/ref/extend 但表述未钉 E_sem 门槛 | **SemanticEdge.type 允许 S0 全部**：contain（contain_kind∈{structural,semantic}）/reference/extend；**只有 label=semantic 或 contain_kind=semantic 进 E_sem**；结构/ref 不得标语义；新增类型须 S0/S1 修订（R-S10-1） | 修正 |
| 2 | S10-11 | 失败码模糊/可能 `S10_*` | **统一 `GRAPH_*` + S6-ADDENDUM-2 码表**（legacy/i18n/severity/audit_id）；无 `S10_*`；未知 `GRAPH_INTERNAL`（R-S10-2） | 修正 |
| 3 | S10-1/S10-6 | 写路径“curated overlay”可能被实现为 graph 写 sidecar | **agent 只 propose_write，不写任何文件**；apply 由产品 curation writer 在人工确认后执行；无 sidecar/正文写；失败零写入；metadata/audit 白名单（R-S10-3） | 修正 |
| 4 | S10-9 | 质量指标缺可执行 eval | **可执行 eval**：golden path/schema/sha、`eval-kp` 命令/exit、指标 JSON+sha、人工抽检样本/阈值；S8 消费；未校准 soft（R-S10-4） | 新增 |
| 5 | S10-2/S10-4/S10-7/S10-8 | kp_id/direction/merge/失效未统一 | **kp_id 全局唯一**；单 section/不重叠（嵌套 future）；merge 保留 canonical+alias+history；`direction` 允许 `both`（默认 source→target）；S10 未启用 S7/S9 只读；写后 S9 失效/重建（R-S10-5） | 修正 |
| 6 | 全篇 | 未吸收 A schema | 吸收 A 的 KP schema/WritePlan/质量指标/merge 历史；补失败码表/WritePlan 细节；更新差异清单 | 并集 |

---

## S10-1 定位与边界（propose_write only）

**规则**：S10 规范 agent **只提出** KP/语义边/curation 提案（proposal/plan），**不写任何文件/事实/sidecar/正文**；apply 由**产品 curation writer** 在人工确认后执行（plan/approval/backup/atomic/undo/audit）；0.5 不做。
**形式化/机检**：
```
agent 输出：KPProposal[]/SemanticEdgeProposal[]/CurationProposal[] + evidence
禁止：写 .md/正文/sidecar/manifest/registry；graph/agent 服务无 sidecar 写权限
apply：产品 curation writer 执行（人工确认后）；plan/approval/backup/atomic/undo/audit
0.5：S10 不实现/无写工具/feature flag off
```
**反例**：agent 直接写 md/sidecar；graph 服务写 sidecar；绕过 propose_write；0.5 自动 semantic。
**边界**：无源/低置信/冲突/权限；S10 未启用；产品 curation writer 未接入。
**U 映射**：U-12、U-25、U-29、U-34。
**建议裁决**：冻结 propose_write only/不写文件/apply 由产品 curation writer/0.5 不做。
**证据等级**：A（S6-1/S6-8/S6-10；S0 D-3；R-S10-3）+ R。

---

## S10-2 KP 定义/粒度/字段

**规则**：KP = 可标注语义单元，锚定 md 连续 range；字段：
```
KP{
  kp_id: string globally unique（跨 KB/文件唯一；anchor+label 仅辅助校验）,
  title:string≤120, aliases:string[]=[]（去重）, summary?:string≤500（可空）,
  file:string（KB 相对）, range{start{line,anchor?},end{line,anchor?}},
  section_ref?{heading,line,anchor}, tags:string[]=[],
  evidence{file,line_start,line_end,anchor_id},
  confidence:float 0..1=0, status∈{proposed,approved,rejected,merged}=proposed,
  curated_by?, curated_at?, curated_version?, parent_kp_id?（嵌套 future）
}
粒度：单文件；默认单 section、不跨 section；一个 section 多 KP；KP 范围默认不重叠；
  嵌套/重叠需显式 parent_kp_id + 人工确认（v1 默认禁止，future 另开修订）；
  最小可标注短语/句；最大单 section；禁止整文档 KP；不写正文
```
**机检**：schema/枚举/默认/失败码；kp_id 全局唯一（索引冲突检测）；range 在文件/单 section；不重叠；anchor 可解析；不写正文。
**反例**：整篇一个 KP；跨文件 range；kp_id 重复；重叠无 parent；summary 当正文。
**边界**：标题行/无 section/代码块/超大 section；跨语言 alias。
**U 映射**：U-12、U-19、U-21、U-22。
**建议裁决**：冻结 KP schema/全局 id/单 section/不重叠/嵌套 future。
**证据等级**：A（S0 KP；S6 anchor；R-S10-5）+ PI（长度/阈值）。

---

## S10-3 KP 抽取/生成

**规则**：输入 DataSource 只读 + 现有 sidecar（只读）；输出 KPProposal（带 file/line/anchor/evidence/confidence/reason/source_hash）；**无源不生成**；低置信 `GRAPH_KP_LOW_CONFIDENCE` 不 apply；幂等/去重。
**机检**：每 proposal 有锚且可解析；无源=FAIL；confidence 阈值；同 anchor+normalized title 去重；2x 幂等；不写正文。
**反例**：无锚生成；锚不命中；低置信自动写；重复 KP。
**边界**：无源/歧义/多语言/sidecar 缺失。
**U 映射**：U-12、U-13、U-14。
**建议裁决**：冻结证据锚/无源禁止/低置信/幂等去重。
**证据等级**：A（S6 DataSource；R-S10-4）+ R。

---

## S10-4 语义边设计（全类型 + E_sem 门槛）

**规则**：
```
SemanticEdge{
  edge_id: canonical(type|source|target|direction|label),
  type∈{contain,reference,extend}, contain_kind?∈{structural,semantic},
  label∈{semantic,structural,navigation}（语义边必须 label=semantic 或 contain_kind=semantic）,
  source_id/target_id: KP ids（不相等；不跨 KB）,
  direction∈{source_to_target,both}（默认 source_to_target）,
  evidence{file,line_start,line_end,anchor_id}（双端/assertion）,
  confidence:0..1, reason:非空,
  provenance{...S10-5}
}
E_sem 门槛：
  只有 label=semantic 或 contain_kind=semantic 进入 E_sem；
  contain(structural)/reference/extend 默认结构/引用；结构/引用不得标 semantic；
  结构/引用边语义贡献=0，不得计入 μ/β/簇/检索语义分；
  新增类型须 S0/S1 修订；S10 不静默增删。
```
**机检**：type/contain_kind/label 枚举；E_sem 门槛；结构/ref 标 semantic 报 `GRAPH_EDGE_SEMANTIC_MISMATCH`；方向；证据；自环/跨 KB；每条边 evidence+reason。
**反例**：contain(structural) 标 semantic；无证据；新增类型；跨 KB；自环。
**边界**：同义/反向/双向；多证据；低置信；冲突。
**U 映射**：U-13、U-14、U-15、U-27。
**建议裁决**：冻结 S0 全类型/E_sem 门槛/结构引用不得标语义/方向 both/新类型须 S0-S1。
**证据等级**：A（S0-3 E_relation_min；S1 relation_sources；S2 semantic-only；R-S10-1）+ R。

---

## S10-5 双引用/curation/人工确认/undo

**规则**：KP/边必须有双引用 provenance：
```
Provenance{source_id,target_id?,assertion_source{file,line_start,line_end,anchor_id},
 evidence_refs[], curated_by, curated_at, decision_id, method∈{agent,human},
 review_status∈{proposed,approved,rejected}, approval_id?, undo_ref?}
```
- source/target/assertion 不可只写一端；`curated_by/at` 必填；apply 前 `review_status=approved` + `approval_id`；undo 保留 before/after；audit.
**机检**：双引用可解析；curated_by/at；approval；undo；audit；元数据只在 S6 curation 白名单。
**反例**：无 target/assertion；无 curated_by；未确认 apply；undo 不可逆；curation 元数据写 sidecar。
**边界**：批量/多确认/冲突/撤销重提。
**U 映射**：U-21、U-22、U-29。
**建议裁决**：冻结双引用/curated/approval/undo/元数据白名单。
**证据等级**：A（S6 curation/audit；R-S10-3/R-S10-5）+ R。

---

## S10-6 写路径（propose_write only + 产品 curation writer）

**规则**：
```
agent: propose_write(plan{ops[],evidence[],actor,expected_edition}) → 只返回 plan，不写
产品 curation writer（apply）:
  validate(plan) → human_confirm(approval_id) → backup(before image)
  → atomic apply（全成功或零写入）→ audit → undo token
WritePlan{plan_id,kb_id,expected_edition,ops[],approvals[],evidence[],
          backup_id?,created_by,created_at,status}
WriteOp{op_id,op_type∈{kp.upsert,kp.alias,kp.merge,edge.upsert,edge.retract,curation},
        params,preconditions{base_version,anchor_exists,kp_id_unique},evidence_refs[],dry_run_result}
```
- **禁止**：agent 写文件/sidecar/正文；graph 服务写 sidecar；绕过 propose_write/approval；部分写入；自动 apply。
- **失败**：任一步失败 ⇒ 零写入（snapshot diff=0）；批处理整体回滚；`GRAPH_CURATION_ROLLBACK_FAILED` 可见。
**机检**：agent 无写 API；plan schema；apply approval；atomic 零写；backup/undo/audit；无 sidecar/正文；批处理事务。
**反例**：agent 直接写；产品 writer 无 approval；部分成功；无 backup；写 sidecar。
**边界**：并发/edition 变/审批拒绝/回滚失败。
**U 映射**：U-21、U-29、U-32。
**建议裁决**：冻结 propose-only/产品 curation writer/approval/atomic/backup/undo/audit/零写。
**证据等级**：A（S6-1/S6-8；现有 plan/apply/backup/approvals；R-S10-3）+ R。

---

## S10-7 冲突/去重/合并

**规则**：重复 KP（同 id/name）/alias/range 重叠/同边同型/反向/语义冲突：分类判定；重复去重；冲突保留双方 + 人工裁决；merge 保留 canonical id + aliases + `merged` redirect + history；不破坏性删除；`GRAPH_KP_DUPLICATE`/`GRAPH_EDGE_DUPLICATE`/`GRAPH_CURATION_CONFLICT`。
**机检**：冲突类；去重键；人工裁决；merge history/redirect；旧 id 可解析；无覆盖。
**反例**：自动覆盖；静默合并；丢历史；重复边。
**边界**：同义/多语言/跨文件/批量。
**U 映射**：U-12、U-14、U-19、U-21。
**建议裁决**：冻结冲突类/去重/人工/merge history/redirect。
**证据等级**：A（S0/S2 身份；R-S10-5）+ R。

---

## S10-8 版本/失效/回滚

**规则**：apply 成功 ⇒ edition 变化 ⇒ **S9 索引失效/重建**；S2 新 run；旧 KP/边/history 保留；`expected_edition` CAS；回滚恢复 before image 并重建 S9；S10 未启用时 S7/S9 只读；写后 S7 读新 edition。
**机检**：edition/CAS；S9 失效/重建；旧数据保留；回滚；S10 disabled 时 S7/S9 只读。
**反例**：写后不失效；旧索引混用；回滚丢历史；CAS 缺失。
**边界**：批量/失败/回滚/跨 KB。
**U 映射**：U-21、U-22、U-29、U-32。
**建议裁决**：冻结 edition/CAS/S9 失效重建/旧数据/回滚/S10 disabled 只读。
**证据等级**：A（S6/S9；R-S10-5）+ R。

---

## S10-9 质量/评估（可执行 eval）

**规则**：
```
golden path: docs/design/multilevel-graph/golden/S10-kp-golden-set.json（S10a 定稿唯一）
GoldenSet{golden_version,kb_id,edition_sha,KPs[{kp_id,file,range,title,labels}],
          edges[{source,target,type,label,direction}], human_samples[]}
eval command: python scripts/benchmark/graph/eval_kp.py --golden <path> --kb <kb> \
  --out artifacts/agent/verify/graph/kp_eval/<run>.json --sha256
exit 0 PASS；≠0 FAIL
metrics JSON{eval_version,golden_sha,edition,KP:{precision,recall,evidence_rate},
  EDGE:{precision,recall,sem_purity}, human_sample:{n,pass_rate}, determinism_sha}
```
- 指标：Q-KP-P/R、Q-EDGE-P/R、Q-EVIDENCE=100%、Q-SEM-PURITY=1.0、人工抽检样本/通过率；阈值未校准 soft；S8 消费；2× 确定性；无正文/PII。
**机检**：golden 存在/sha；命令/exit；JSON+sha；抽检；阈值；2×；Q-EVIDENCE/Q-SEM-PURITY。
**反例**：无 golden/命令/exit；指标无 sha；结构边标 semantic；抽检偏；2× 不同。
**边界**：无 golden/小样本/多语言；阈值假设。
**U 映射**：U-12、U-14、U-32。
**建议裁决**：冻结 eval 契约/golden/命令/exit/sha/抽检/阈值；S8 消费。
**证据等级**：A（S8-12；R-S10-4）+ PI（阈值）。

---

## S10-10 与 S1 registry/S2 clustering

**规则**：KP 目录独立于 S1 维度 registry；S10 不改 registry/只读（新增维度须 S1 修订）；S2 按新 edition 重建 run；多归属允许；S10 不写 cluster/membership；cluster 稳定性归 S2；S10 不做簇合并/拆分。
**机检**：S10 无 S1 registry 写；无 cluster 写；S2 新 run；多归属；稳定性可复算。
**反例**：S10 改 registry 删维度；写 cluster；合并簇；强制单归属。
**边界**：多归属/无簇/S2 未运行/旧 edition。
**U 映射**：U-6、U-10、U-11、U-21、U-31。
**建议裁决**：冻结 S1 只读/S2 重建/多归属/不写簇。
**证据等级**：A（S1/S2 冻结）+ R。

---

## S10-11 失败/降级/隐私（GRAPH_* 码表）

**码表（S6-ADDENDUM-2 + S6）**：
| code | 触发 | legacy | severity | i18n |
|---|---|---|---|---|
| `GRAPH_KP_INVALID` | KP 字段/range/锚非法 | GRAPH_INTERNAL | error | graph.kp.invalid |
| `GRAPH_KP_DUPLICATE` | 同 id/name 重复未合并 | GRAPH_INTERNAL | warn | graph.kp.duplicate |
| `GRAPH_KP_EVIDENCE_MISSING` | 无 file/line/anchor | GRAPH_INTERNAL | error | graph.kp.evidence_missing |
| `GRAPH_KP_AMBIGUOUS` | 锚歧义/多候选 | GRAPH_INTERNAL | warn | graph.kp.ambiguous |
| `GRAPH_KP_LOW_CONFIDENCE` | 低于阈值不 apply | GRAPH_INTERNAL | warn | graph.kp.low_confidence |
| `GRAPH_EDGE_INVALID` | type/direction/字段非法 | GRAPH_INTERNAL | error | graph.edge.invalid |
| `GRAPH_EDGE_DUPLICATE` | 同 pair/type 重复 | GRAPH_INTERNAL | warn | graph.edge.duplicate |
| `GRAPH_EDGE_EVIDENCE_MISSING` | 无 evidence/assertion | GRAPH_INTERNAL | error | graph.edge.evidence_missing |
| `GRAPH_EDGE_SEMANTIC_MISMATCH` | 结构/引用标 semantic | GRAPH_INTERNAL | error | graph.edge.semantic_mismatch |
| `GRAPH_CURATION_CONFLICT` | 冲突未裁决 | GRAPH_INTERNAL | warn | graph.curation.conflict |
| `GRAPH_CURATION_APPROVAL_REQUIRED` | 无人工确认 apply | GRAPH_INTERNAL | error | graph.curation.approval_required |
| `GRAPH_CURATION_PRIVACY_REJECTED` | PII/正文边界 | GRAPH_INTERNAL | error | graph.curation.privacy_rejected |
| `GRAPH_CURATION_BUDGET_EXCEEDED` | 提案超预算 | GRAPH_INTERNAL | warn | graph.curation.budget_exceeded |
| `GRAPH_CURATION_ROLLBACK_FAILED` | 回滚零写校验失败 | GRAPH_INTERNAL | error | graph.curation.rollback_failed |
| `GRAPH_INTERNAL` | 未知 | — | error | graph.error.internal |
- 所有码带 `audit_id`；禁止 `S10_*`；新码只增不删；失败不 apply/零写；隐私不写正文/PII。
**机检**：码表/映射/severity/i18n/audit；无 S10_*；失败零写；无正文/PII。
**反例**：S10_* 码；无 audit；低置信 apply；隐私正文；半写。
**边界**：无源/歧义/冲突/预算/权限。
**U 映射**：U-29、U-32。
**建议裁决**：冻结 GRAPH_* 码表/失败零写/隐私；禁止 S10_*。
**证据等级**：A（S6-9 + ADDENDUM-2；R-S10-2）+ R。

---

## S10-12 与 0.5 边界

**规则**：S10 设计**不在 0.5**；0.5 无 S10 写工具/自动 semantic；S10 未启用时 S7/S9 只读；未来 apply 需人工确认 UI + approval；不影响 0.5 DoD；feature flag off。
**机检**：0.5 无 S10 写；S10 disabled 时 S7/S9 只读；人工确认；不夹带；不影响 S8。
**反例**：0.5 自动 semantic；S10 改 DoD；无人工确认。
**边界**：0.5 验收/未来版本/回滚。
**U 映射**：U-29、U-32、U-34。
**建议裁决**：冻结 S10 不在 0.5/disabled 只读/人工确认/不夹带。
**证据等级**：A（S6-12；R-S10-5）+ R。

---

## 附：R-S10 自检（5 条）

| 裁决 | B-v2 落位 |
|---|---|
| R-S10-1 全类型/E_sem 门槛 | S10-4（contain/ref/extend；label semantic/contain_kind semantic；结构/ref 不标；新类型须修订） |
| R-S10-2 GRAPH_*/ADDENDUM-2 | S10-11（码表；无 S10_*；legacy/i18n/severity/audit） |
| R-S10-3 propose-only/D-3 | S10-1/S10-6（agent 不写；产品 curation writer；无 sidecar/正文；零写） |
| R-S10-4 质量 eval | S10-9（golden/命令/exit/JSON+sha/抽检/阈值/S8） |
| R-S10-5 身份/方向/合并/失效 | S10-2/S10-4/S10-7/S10-8（kp_id 全局/单 section/不重叠/direction both/merge history/S9 失效） |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S10-objections-v2.md`；未写产品代码/契约，未 commit。
