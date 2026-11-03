# S8 度量与验收提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S8-RULINGS.md`（R-S8-1..R-S8-6）；上游冻结 `S0`（`241b1e1e…`）、`S1`（`6676c71d…`）、`S2`（`92bb0041…`）、`S3`（`0ca4ea0e…`+ADDENDUM-1）、`S4`（`2576f6c8…`）、`S5`（`7f4c4515…`）、`S6`（`40f12e5f…`+ADDENDUM-1）、`S7`（`70dd8748…`），不得违反。
> **输入**：B v1（`c59570d0…`）、A v1（`114acd53…`）、`S8-objections.md`（`b53d2fa8…`）。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S8-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S8-RULINGS/S0–S7 冻结。
> **日期**：2026-11-04（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S8）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S8-5 | rule_id 解释覆盖节点+边（文本）但无联合公式 | **X-RULE 联合分母（节点+边）100%**；加 **X-NODE-RULE/X-EDGE-RULE**；`rule_id=null` 的 non-shown 记失败（R-S8-1） | 修正 |
| 2 | S8-2/S8-11 | G6 路径 artifacts | **G6 唯一 audit 域 `.memoria/agent/audit/graph/g6/`**；artifacts 只报告；`snapshot_id=sha256(canonical(G6_SNAPSHOT without snapshot_id))`；基线 decision_id/旧快照保留（R-S8-2） | 修正 |
| 3 | S8-9 | 无 G-G7 | **CI P0 加 `G-G7`**：write_attempts=0/read_only=100%/引用 G6/无正文；命令/exit/产物 sha；失败阻断（R-S8-3） | 新增 |
| 4 | S8-4 | 性能值混合 | **冻结值 vs 假设分离**：60/30/180/200/400 来自 S3/S4；P95/首开/切页签/Admission 标“假设，需实测基线”；冷/热/硬件/N≥30；CI 无 GPU 只本地（R-S8-4） | 修正 |
| 5 | S8-8/S8-3 | 故障 6 类；signed 未处理 | 故障补 **renderer budget/S9 unavailable**；flaky 统一“P0 不 flaky/诊断重试≤3/阈值不降”；`signed=false` 不是失败（R-S8-5） | 修正 |
| 6 | S8-5/S8-10/S8-11 | DoD/隐私较简 | `X-SUMMARY` 字段统一；DoD **I-07 只 2D P0/3D capability=false**；G7 只存 id/anchor/counts、无正文/excerpt/PII、90 天/100k/≤64MB（R-S8-6）；吸收 A 指标表/G7 阈值/DoD | 并集 |

---

## 0.1 指标总表（定义/公式/阈值/证据/失败）

| ID | 类 | 定义/公式 | 阈值 | Gate | 证据/失败 |
|---|---|---|---|---|---|
| C-HAC-DET | 正确性 | 同输入两次 `run_id`/partition 相同 | 100% | P0 | G6 determinism_sha；exit≠0 |
| C-REGISTRY | 正确性 | schema/history 链/只增；`signed=true` 验签，`signed=false` 记录但不失败 | 100% 链；签名按 S6 可选 | P0 | registry validator；断链失败 |
| C-PRESENCE | 正确性 | 全部候选节点/边 presence + rule_id；unknown 仅 4 类 | 100% | P0 | AdmissionResult fixture；缺 rule=FAIL |
| C-SUBSET | 正确性 | candidates(full)⊇default ∧ reserved(full)==shown(default) ∧ budget_full≥default | 100% | P0 | subset proof；G6 |
| C-CLOSURE | 正确性 | closure/behind 违规 | 0 | P0 | G6 字段 |
| C-TIE | 正确性 | `(tier,hop,relation_class,label_rank,canonical_id)` 两次一致 | 100% | P0 | fixed fixture |
| C-SCHEMA | 正确性 | 所有 schema 字段/枚举/默认/失败码 | 100% | P0 | SchemaValidator |
| X-RULE | 可解释 | `(non_shown nodes with rule_id + non_shown edges with rule_id)/(all non_shown nodes + all non_shown edges)` | 100% | P0 | VM/Admission fixture；`rule_id=null` 记 FAIL |
| X-NODE-RULE | 可解释 | non_shown nodes with rule_id / non_shown nodes | 100% | P0 | 分项 |
| X-EDGE-RULE | 可解释 | non_shown edges with rule_id / non_shown edges | 100% | P0 | 分项 |
| X-SUMMARY | 可解释 | `suppressed_summary`/`rule_histogram` 与 suppressed 计数一致（S4 字段名） | 100% | P0 | VM fixture |
| X-UNKNOWN | 可解释 | unknown 全带 reason；unknown≠无关系 | 100% | P0 | fixture/响应 |
| X-TRUNC | 可解释 | 超预算 `truncated/omitted` 出现 | 100% | P0 | 预算注入 |
| X-DEGRADE | 可解释 | no_semantic/stale/error 可见（DOM/aria/事件） | 100% | P0 | DOM/aria/事件 |
| P-NODES | 性能 | 单屏 VM nodes | ≤200（冻结；S8 可调需决策） | P0 | VM |
| P-EDGES | 性能 | 单屏 VM edges | ≤400（冻结） | P0 | VM |
| P-BUDGET | 性能 | 超预算可见 suppressed+rule_id；无静默 | 100% | P0 | VM/DOM |
| P-FPS | 性能 | 参考硬件 2D N=30s P50 | ≥55（目标 60；低端≥30） | SOFT | 本地 harness |
| P-ANIM | 性能 | 动画时长（reduced motion=0） | ≤180ms（冻结） | SOFT | 本地 |
| P-INT-P95 | 性能 | 交互到下一帧 P95 | 假设 ≤200ms（待实测基线） | SOFT | 本地 |
| P-FIRST | 性能 | 首开首帧 P95（冷/热） | 假设 ≤1500ms（待校准） | SOFT | 本地 |
| P-TAB | 性能 | 切页签回图谱 P95 | 假设 ≤300ms（待校准） | SOFT | 本地 |
| P-ADM | 性能 | Admission P95 | 假设 ≤50ms（待校准） | SOFT | 本地 |
| A-WRITE | agent | write_attempts | 0 | P0 | G7；非0失败 |
| A-READONLY | agent | read_only tools 比例 | 100% | P0 | 工具注册表 |
| A-REF | agent | resolved_refs/refs | ≥99% | SOFT | G7 |
| A-UNKNOWN | agent | unknown_claims/claims | ≤20% | SOFT | G7 |
| A-TOKEN | agent | tokens/call | ≤4000（默认；S8 可调） | SOFT | G7 |
| A-CALLS | agent | tools/task | ≤8（建议） | SOFT | G7 |
| A-DEGRADE | agent | 降级/错误可见 | 100% | P0 | G7/响应 |
| A-AUDIT | agent | 审计落盘成功 | 100% | P0 | G7/audit |
| D-SEM-PURITY | 数据质量 | μ/β 输入 == E_sem；非 semantic 进簇=0 | 100% | P0 | S2 run |
| D-SEM-EDGE | 数据质量 | semantic_edge_pairs/relation_pairs（仅 semantic） | 语料信号 | SOFT | DataSource |
| D-SEM-KP | 数据质量 | KPs incident E_sem/all KPs（仅 semantic） | 信号 | SOFT | DataSource |
| D-NOSEM | 数据质量 | no_semantic run 比例；coverage=0 | 合法；可见 | SOFT+P0 可见性 | S2 run/VM |
| D-CLUSTER-COV | 数据质量 | covered_kp/total_kp（S2 公式） | 信号 | SOFT | run |
| D-CURATION | 数据质量 | curated semantic edges/semantic edges | 信号 | SOFT | curation |
| GATE-G6 | 回归 | G6 字段/sha/基线 diff | 100% | P0 | CI |
| GATE-G7 | 回归 | G-G7 断言 | 100% | P0 | CI |
| GATE-MERMAID | 回归 | mermaid PARSE_OK | 100% | P0 | CI |
| GATE-SCHEMA | 回归 | I-13 schema | 100% | P0 | CI |
| GATE-FAULT | 回归 | 故障矩阵 smoke | 100% | P1 | CI |
| GATE-PERF | 回归 | 本地性能相对回归 | ±20% 告警 | SOFT | 本地 |

---

## S8-1 指标框架与优先级

**规则**：7 类（正确性/确定性/性能/可解释/agent/数据质量/回归）；每类 P0 硬门禁 + 软指标；**禁止单一指标掩盖失败**；每条 metric 有 `id/class/formula/threshold/gate/command/exit/artifact_sha`。
**机检**：总表字段完整；P0 有命令/exit；无软指标替代 P0；P0 失败 exit≠0。
**反例**：平均 FPS 掩盖 P95；用结构边提升 coverage；unknown 低当正确。
**边界**：无簇/空图/低端硬件/CI 无 GPU。
**U 映射**：U-32、U-34。
**建议裁决**：冻结分类/P0-soft/总表 schema。
**证据等级**：A（S3/S4/S6/S7）+ R。

---

## S8-2 G6 快照冻结（唯一 audit 路径）

**规则**：
```
G6_SNAPSHOT = S6-contract-v1 字段（严格）:
{g6_version, data_source_sha, run_ids[], registry_sha, vm_sha, frame_ids[],
 frame_sha, nav_sha, rule_histogram, node_count, edge_count, subset_ok,
 determinism_sha, closure_violations:0, behind_violations:0, history_signed}
snapshot_id = sha256(canonical(G6_SNAPSHOT without snapshot_id))
唯一落盘：.memoria/agent/audit/graph/g6/<snapshot_id>.json（基线/CI 事实源）
artifacts/agent/verify/graph/g6/：仅人类可读报告/副本，不作基线/CI 事实源
基线：.memoria/agent/audit/graph/g6/baseline.json；更新需 decision_id；旧快照保留
复跑：python scripts/benchmark/graph/g6_snapshot.py --edition <sha> --out <audit path> --sha256
```
- 外层 envelope（不参与 canonical）：`{created_at, command, harness_version, env{cpu/gpu/os/python/browser}, report_copy_path}`。
- 不可变：同 snapshot_id 不覆盖；diff 只读。
**机检**：字段==S6；路径唯一；sha 可复算；2x 同 id；不可变；baseline decision_id/旧快照；CI 读 audit。
**反例**：G6 写 artifacts 当基线；加/删字段；覆盖同 id；基线静默更新；时间戳入 sha。
**边界**：空 KB/no_semantic/full/跨机器/缓存删重建。
**U 映射**：U-32、U-34；S6-11。
**建议裁决**：冻结 G6 字段/audit 路径/snapshot_id 公式/基线/不可变。
**证据等级**：A（S6-11；S6-8；R-S8-2）+ R。

---

## S8-3 正确性/确定性

**规则**：
```
C-HAC-DET 100%；C-REGISTRY 100% 链（signed=false 记录不失败）；
C-PRESENCE 100%（节点/边 presence+rule_id）；C-SUBSET 100%；
C-CLOSURE closure/behind=0；C-TIE 100%；C-SCHEMA 100%。
```
- 同 fixture 2x `run_id/cluster_key/presence/G6 determinism_sha` 相同；失败 exit≠0。
**机检**：命令/exit；字段；2x sha；schema；subset proof；registry signed 分档。
**反例**：随机 tie-break；subset 事后断言；signed=false 判失败；节点 rule 缺失。
**边界**：空图/no_semantic/full/预算边界/多归属。
**U 映射**：U-13、U-14、U-27、U-32。
**建议裁决**：冻结 P0 正确性/确定性/签名分档。
**证据等级**：A（S2/S4/S6；R-S8-5）+ R。

---

## S8-4 性能/预算（冻结值 vs 假设分离）

**规则**：
```
冻结值（S3/S4 来源，不得改）: max_nodes=200, max_edges=400, 60fps 目标,
 低端≥30fps, 动画≤180ms
假设值（需实测基线校准，S8 未冻结）: P95 交互≤200ms, 首开≤1500ms,
 切页签≤300ms, Admission≤50ms
测量: 参考硬件/OS/浏览器/视口/主题/缩放；冷/热分开；N≥30；P50/P95/max；
 CI 无 GPU ⇒ 只跑结构 P0；性能本地参考硬件，记录环境；CI 相对回归±20%告警
```
- 预算超限：可见 `GRAPH_BUDGET_INVALID`/`GRAPH_TOOL_BUDGET_EXCEEDED`/banner，不静默。
**机检**：P-NODES/P-EDGES/P-BUDGET P0；性能 soft 标注假设/环境/样本；CI 不硬判 FPS。
**反例**：把 P95 假设写成冻结阈值；只测热缓存；CI 容器测 FPS 判失败；无样本。
**边界**：低端/大图/3D capability=false/无数据。
**U 映射**：U-3、U-16、U-32。
**建议裁决**：冻结硬值/预算可见；假设值待基线；测量条件/CI 策略。
**证据等级**：A（S3-11；S4 budget；R-S8-4）+ R。

---

## S8-5 可解释性/UX 验收（X-RULE 联合分母）

**规则（P0）**：
```
X-RULE = (non_shown nodes with rule_id + non_shown edges with rule_id)
         / (all non_shown nodes + all non_shown edges) = 100%
X-NODE-RULE = non_shown nodes with rule_id / non_shown nodes = 100%
X-EDGE-RULE = non_shown edges with rule_id / non_shown edges = 100%
X-SUMMARY: suppressed_summary/rule_histogram 与 suppressed 计数一致
X-UNKNOWN: unknown 全带 reason；unknown≠无关系
X-TRUNC: 超预算 truncated/omitted 出现
X-DEGRADE: no_semantic/stale/error 可见（DOM/aria/事件）
rule_id=null 的 non-shown（节点或边）一律记 FAIL
```
- 机测：VM/AdmissionResult fixture + DOM/aria 断言 + 事件/快照；不靠人工观感。
**机检**：联合分母/分项 100%；null 失败；summary 字段 S4 名；DOM/事件；无静默。
**反例**：只算边（X-RULE 100% 但节点抑制无 rule）；rule_id=null 仍通过；unknown 画无边；截断不标。
**边界**：no_semantic；预算极小；unknown 4 类；审计失败。
**U 映射**：U-27、U-32。
**建议裁决**：冻结 X-RULE 联合分母/分项/null 失败/DOM 机测。
**证据等级**：A（S3-8/10；S4-6；S6-5/ADDENDUM-1；R-S8-1）+ R。

---

## S8-6 G7 agent 指标

**规则**：
```
A-WRITE=0（P0）；A-READONLY=100%（P0）；A-DEGRADE=100%（P0）；A-AUDIT=100%（P0）
A-REF≥99%（soft）；A-UNKNOWN≤20%（soft）；A-TOKEN≤4000（soft）；A-CALLS≤8（soft）
G7_SNAPSHOT{g7_version, g6_run_ids[], g6_frame_ids[], edition, metrics...}
G7 只引用 G6、不复制事实/正文；只存 id/anchor/counts；无 excerpt/PII
```
**机检**：字段==S7；write=0；read_only=100%；G6 引用；阈值；无正文。
**反例**：write 非0；G7 存正文/excerpt；ref 低仍 PASS；G7 复制 VM。
**边界**：空会话/S9 挂/预算截断/多 KB。
**U 映射**：U-2、U-29、U-32。
**建议裁决**：冻结 G7 字段/阈值/写=0/隐私。
**证据等级**：A（S7-12；R-S8-3/R-S8-6）+ R。

---

## S8-7 数据质量（semantic only）

**规则**：
```
D-SEM-PURITY = μ/β 输入 == E_sem；非 semantic 进簇=0（P0 100%）
D-SEM-EDGE = semantic_edge_pairs/relation_pairs（仅 semantic；语料信号）
D-SEM-KP = KPs incident E_sem/all KPs（仅 semantic；信号）
D-NOSEM = no_semantic run 比例；coverage=0（合法、可见）
D-CLUSTER-COV = covered_kp/total_kp（S2 公式；信号，不恒 1）
D-CURATION = curated semantic edges/semantic edges（信号）
结构/reference 不得进入 μ/β/coverage/质量分子；no_semantic 合法 ≠ algorithm_failed
```
**机检**：semantic-only；公式；no_semantic vs algorithm_failed 分离；可复算。
**反例**：结构边算 coverage；no_semantic 判算法失败；语料差怪 HAC。
**边界**：零语义/小语料/多 KB/旧数据。
**U 映射**：U-1、U-13、U-14、U-27。
**建议裁决**：冻结 semantic-only/信号/no_semantic 合法。
**证据等级**：A（S2；S0 E_relation）+ R。

---

## S8-8 故障注入/回放

**规则（8 类）**：
```
budget_exhausted, no_semantic_edges, edition_stale, missing_anchor/data,
invalid_input, audit_failure, renderer_budget_exceeded, s9_unavailable
```
- 每个：注入方式/期望 `GRAPH_*`/可见降级/exit code/快照；固定 fixture/edition/env/seed；2x 回放同 determinism sha；G6 diff 可断言；无静默 fallback。
- flaky 统一：P0 不 flaky；诊断性重试最多 3 次；阈值不得因 flaky 下调；隔离需 owner/issue。
**机检**：8 类覆盖；期望码/可见；2x sha；G6 diff；flaky 审计。
**反例**：只测正常；回放随机；审计失败仍成功；flaky 重试过 P0。
**边界**：组合故障/缓存损坏/空图/低端。
**U 映射**：U-27、U-32。
**建议裁决**：冻结 8 类故障/回放/flaky 政策。
**证据等级**：A（S6/S7 错误；R-S8-5）+ R。

---

## S8-9 回归门禁/CI（含 G-G7）

**CI P0 gates（阻断）**：
| gate | 内容 | 命令/exit | 产物 |
|---|---|---|---|
| G-SCHEMA | SchemaValidator 全 schema | `python scripts/verify/schema_check.py` exit0 | 报告 sha |
| G-DET | 两次 run/G6 determinism_sha | `pytest tests/graph/test_determinism.py` exit0 | G6 |
| G-PRESENCE | 节点/边 presence+rule_id 100% | `pytest tests/graph/test_presence.py` exit0 | fixture |
| G-SUBSET | subset proof | `pytest tests/graph/test_subset.py` exit0 | proof |
| G-CLOSURE | closure/behind=0 | G6 assert | G6 |
| G-AUDIT | 审计 append-only/失败可见 | `pytest tests/graph/test_audit.py` exit0 | audit |
| G-NOWRITE | 无 sidecar/写工具 | `pytest tests/graph/test_nowrite.py` exit0 | audit |
| **G-G7** | **write_attempts=0 / read_only=100% / G7 引用 G6 / 无正文** | `python scripts/verify/g7_gate.py --audit ...` exit0 | g7 gate sha |
| G-G6 | G6 字段/sha/基线 diff | `python scripts/benchmark/graph/g6_snapshot.py --check` exit0 | G6 |
| G-MERMAID | 所有 mermaid PARSE_OK | `python scripts/verify/mermaid_parse.py` exit0 | 报告 |
| G-FAULT | 8 类故障 smoke | `pytest tests/graph/test_faults.py` exit0 | 报告 |
| G-PERF | 本地参考硬件相对回归 | 本地 harness；CI 不硬判 | 环境+样本 |
**规则**：CI 只跑结构 P0（无 GPU）；性能本地；flaky P0 不重试通过（诊断≤3 次，阈值不降）；G6/G7 产物 sha 进 CI；本地/CI 同 harness/edition。
**机检**：P0 gates 命令/exit/产物；G-G7 存在；flaky 政策；mermaid；基线 decision_id。
**反例**：CI 跑 FPS 容器判失败；flaky 重试过 P0；G-G7 缺失；阈值下调。
**边界**：无浏览器 CI/大图/跨平台。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 P0 清单（含 G-G7）/本地性能/flaky。
**证据等级**：A（S6/S7；R-S8-3）+ R。

---

## S8-10 0.5 验收清单 / DoD

**规则**：I-01..I-13 全 P0；每项命令/fixture/证据；不做项 feature flag；P0 全 PASS 才退出 0.5。DoD 表（吸收 A）：
| I | 验收项（P0） |
|---|---|
| I-01 DataSourceReader | 只读/`expand_data_edges⊆DataSource.edges`/canonical id/无 sidecar 写 |
| I-02 GraphViewBuilder | `(level,view_family)` partition/kind/不缓存事实 |
| I-03 RegistryService | schema/history 链/只增/签名（signed=false 记录） |
| I-04 ClusterRunBuilder | HAC 两次一致/五状态/no_semantic 合法 |
| I-05 AdmissionService | focus 一跳/presence/rule/MANDATORY/subset/事务 |
| I-06 ViewModelBuilder | S3 白名单+ADDENDUM-1/node presence/aggregate |
| I-07 RendererAdapter | **2D 渲染 P0；3D 同签名接口 P0、capability=false、实现不做** |
| I-08 NavController | T01–T30/S5a/frame_id/事务 diff=0 |
| I-09 CacheStore | `.memoria/cache/graph/` 可删重建/GC 不删事实 |
| I-10 AuditLog | append-only/每次工具审计 |
| I-11 G6Snapshot | 字段/sha/复跑/基线 audit 路径 |
| I-12 ErrorMap | `GRAPH_*`+legacy/i18n |
| I-13 SchemaValidator | 全 schema fail-closed |
**不做项**：3D 实现、agent 写/自动 semantic、跨库、时间维、图编辑器、破坏性迁移、S7–S10 算法。
**机检**：I 映射；P0 全 PASS；不做项守卫；G6/G7 复跑。
**反例**：I-07 只做 3D；截图代替验收；漏 I-12。
**边界**：2D-only/无 semantic/旧 KB。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 DoD/I-07 2D P0/3D 接口/不做项/退出。
**证据等级**：A（S6-12；I-01..13；R-S8-6）+ R。

---

## S8-11 度量存储/隐私/成本

**规则**：
```
G6：.memoria/agent/audit/graph/g6/；快照/基线不 GC（每 edition 保留）；≤1MB/快照
G7：.memoria/agent/audit/graph/g7/；事件 90 天或 100k 条（先到）；聚合快照长期；≤64MB/库
隐私：只 id/anchor 引用/counts；不存正文/excerpt/PII；G7 不含 source_excerpt
删除：G7 可删不影响事实；G6 删派生可重建（基线重生成）；不删事实
```
**机检**：路径/保留/上限；无正文/PII 扫描；可重建；G6/G7 分离。
**反例**：G7 存正文；G6 写事实源；无限增长；删事实。
**边界**：大 KB/多会话/审计失败/迁移。
**U 映射**：U-29、U-32。
**建议裁决**：冻结路径/保留/隐私/成本。
**证据等级**：A（S6-8/S6-11/S7-12；R-S8-6）+ R。

---

## S8-12 与 S9/S10 度量边界

**规则**：S9 检索质量（recall/precision/latency）与 S10 KP/语义边质量归各自；S8 只消费其指标/接口（`metric_ref{owner,id,value}`），不定义算法/阈值；S9/S10 变更不改 S8 P0；缺失可降级/不阻断。
**机检**：S8 无 S9/S10 算法；owner/接口；不夹带。
**反例**：S8 定义 BM25 阈值；S10 质量算 S8 P0；S8 改 S9 算法。
**边界**：S9 不可用/S10 未实现/跨 KB。
**U 映射**：U-32、U-34。
**建议裁决**：冻结边界/指标 owner/不夹带。
**证据等级**：A（S8 章程）+ R。

---

## 附：R-S8 自检（6 条）

| 裁决 | B-v2 落位 |
|---|---|
| R-S8-1 X-RULE 节点+边/分项/null 失败 | S8-5（联合分母 100%；X-NODE/X-EDGE；null FAIL） |
| R-S8-2 G6 audit 路径/snapshot_id/基线 | S8-2/S8-11（唯一 audit 路径；artifacts 报告；decision_id；旧快照） |
| R-S8-3 G-G7 CI P0 | S8-9（write=0/read_only=100%/引用 G6/无正文；命令/exit/产物） |
| R-S8-4 性能冻结 vs 假设 | S8-4（60/30/180/200/400 冻结；P95/首开假设；冷热/硬件/N≥30；CI 本地） |
| R-S8-5 故障/flaky/signed | S8-8/S8-3（renderer/S9；flaky 统一；signed=false 不算失败） |
| R-S8-6 DoD/隐私/字段 | S8-10/S8-11/S8-5（I-07 2D/3D 接口；G7 隐私；X-SUMMARY 字段） |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S8-objections-v2.md`；未写产品代码/契约，未 commit。
