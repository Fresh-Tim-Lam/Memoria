# S8 度量与验收提案 B（独立复核方）

> **依据**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0`（`241b1e1e…`）、`S1`（`6676c71d…`）、`S2`（`92bb0041…`）、`S3`（`0ca4ea0e…`+ADDENDUM-1）、`S4`（`2576f6c8…`）、`S5`（`7f4c4515…`）、`S6`（`40f12e5f…`+ADDENDUM-1）、`S7`（…），不得违反；本场 `S8-charter.md`。
> **性质**：独立复核方提案；写作时**未读** `S8-metrics-proposal-A.md`（尚未落盘）；写完再对照，差异见 `S8-objections.md`。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S7 冻结。
> **日期**：2026-11-04（Asia/Shanghai）。

---

## 0. 总原则

1. **每个指标必须可机判**：定义/公式/阈值/命令/exit code/证据路径/快照 sha；不得只写“好/快”。
2. **P0 硬门禁**必须机器执行（命令退出码 + G6/G7 快照 sha）；软指标有趋势/门槛，不得替代 P0。
3. **G6 字段严格 = S6-contract-v1 `G6_SNAPSHOT`**；不可变、可复跑、sha 稳定；S8 只加测量元数据（命令/版本/环境）到**外层 envelope**，不改 G6 字段。
4. **G7 严格 = S7**：引用 G6、不复制事实、`write_attempts=0` 硬约束。
5. 性能必须有来源/测量条件（冷热/硬件/样本/分位），不得拍脑袋。
6. 可解释性/降级必须可机测（DOM/事件/快照），不靠人工观感。
7. 数据质量**只用 semantic 边**；结构/引用边不得计入；语料质量差不得误判为算法失败（单独信号）。
8. 故障注入覆盖预算/空语义/stale/缺失/非法/审计失败；回放确定性；失败可见。
9. 回归门禁明确 P0/软门禁、flaky 政策、本地 vs CI 差异。
10. 0.5 DoD 对齐 I-01..I-13；S9/S10 指标归其所有。

### 0.1 覆盖矩阵（U + S0–S7）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-3/U-16 | 规模/选择性=S8-4 | U-32 | 预算/性能=S8-4/S8-6 |
| U-27 | presence/存无=S8-3/S8-5 | U-34 | 议程/验收=S8-1/S8-10 |
| S3 | 视觉/性能=S8-4/S8-5 | S4 | presence/subset=S8-3 |
| S5 | nav/事务=S8-3/S8-7 | S6 | G6/S8-2 |
| S7 | G7/agent=S8-6 | S9/S10 | 边界=S8-12 |

---

## S8-1 指标框架与优先级

**规则**：指标分类：
```
CORRECTNESS: registry/run/presence/subset/closure/behind/VM schema
DETERMINISM: run_id/cluster_key/presence/G6 sha 可复算
PERFORMANCE: 60fps/≤180ms/后端延迟/预算
EXPLAINABILITY: rule_id 解释率/unknown/suppressed/降级可见
AGENT: G7 token/工具/引用/unknown/写尝试
DATA_QUALITY: semantic coverage/no_semantic/curation
REGRESSION: gate/CI/snapshot diff/flaky
```
- 主指标（P0 硬门禁）vs 诊断指标（趋势/soft）；P0 不允许用平均/单一指标掩盖失败。
- 每项 metric 记录 `{id, class, formula, threshold, command, exit_code, artifact_sha, owner}`。
**机检**：metric schema 完整；P0 有命令/exit code；无“人工判断”P0；分类覆盖；阈值来源。
**反例**：只看平均帧率掩盖 p95 卡顿；P0 用“评审觉得好”；无命令。
**边界**：本地/CI/无 GPU；软指标趋势；阈值可调（S8 修订）。
**U 映射**：U-32、U-34。
**建议裁决**：冻结分类/主诊断/P0-软门禁/metric schema。
**证据等级**：A（S6/S7 门禁）+ R。

---

## S8-2 G6 快照冻结

**规则**：`G6_SNAPSHOT` **严格字段 = S6-contract-v1**：
```
{g6_version, data_source_sha, run_ids[], registry_sha, vm_sha, frame_ids[],
 frame_sha, nav_sha, rule_histogram, node_count, edge_count, subset_ok,
 determinism_sha, closure_violations:0, behind_violations:0, history_signed}
```
- 外层 envelope（S8 允许，不改变 G6 字段）：`{snapshot_id, command, harness_version, env{cpu/gpu/os/python}, edition, created_at}`；snapshot_id=sha256(canonical(G6 fields))。
- 存储 `artifacts/agent/verify/graph/g6/<snapshot_id>.json`；**不可变**（同 id 不覆盖）；基线 `baseline.json` 引用 snapshot_id；更新基线需决策记录。
- 复跑命令：`python scripts/benchmark/graph/g6_snapshot.py --edition <sha> --out ... --sha256`；exit 0 且 `snapshot_id` 稳定。
**机检**：字段 == S6；sha 可复算；2x 同 id；不可变；命令/exit；baseline 引用。
**反例**：加/删 G6 字段；覆盖同 id；无命令；baseline 手改。
**边界**：空 KB；无簇；3D 不实现；环境变化（记录但不改字段）。
**U 映射**：U-32、U-34；S6-11。
**建议裁决**：冻结 G6 字段/外层 envelope/路径/不可变/复跑/基线。
**证据等级**：A（S6-11；ENGINEERING-PLAN I-11）+ R。

---

## S8-3 正确性/确定性

**规则/阈值（P0）**：
```
determinism=100%: 同输入 2x run_id/cluster_key/presence/G6 sha 相同
registry: registry_sha 链有效；history 只增；失败 GRAPH_* fail-closed
presence: 每条候选 presence∈{shown,suppressed,unknown} + rule_id；11 类
subset_ok=true: candidates(full)⊇default ∧ reserved(full)==shown(default) ∧ budget_full≥default
closure_violations=0；behind_violations=0
tie_break: 同 input 同排序；run_id/params_hash 可复算
```
**机检**：命令 `g6_snapshot` + `pytest`/gate；exit code；字段；2x sha；非法 presence 0。
**反例**：随机 tie-break；subset 只断言；closure/behind >0；registry 断链。
**边界**：重复 cluster key；`no_semantic_edges`；预算边界；空图。
**U 映射**：U-27、U-32。
**建议裁决**：冻结 P0 正确性/确定性阈值。
**证据等级**：A（S2/S4/S6）+ R。

---

## S8-4 性能/预算

**规则/阈值**：
```
60fps: 交互期间 p95 frame time ≤16.7ms（S3）
frame 切换 ≤180ms（S3，p95；冷/热分开）
VM 预算 max_nodes=200/max_edges=400（S3/S4；S8 可调）
后端延迟：默认查询 p95 ≤500ms（本地基准；CI 用相对回归）
```
- **测量条件**：硬件/OS/浏览器/Python 版本记录；样本 ≥100 帧/≥30 次查询；冷/热分开；p50/p95/max；禁用调试；固定数据 edition；同一 harness；CI 性能只作回归（±20% 告警），不因 CI 硬件直接判 P0。
- 预算不可满足：可见 `GRAPH_BUDGET_INVALID`/`GRAPH_TOOL_BUDGET_EXCEEDED`，不静默丢。
**机检**：`scripts/benchmark/graph/perf.py`；输出 JSON；exit code；p95 字段；冷热；环境；预算失败可见。
**反例**：拍脑袋数值；只看平均；CI 慢即失败；无样本；调试模式测。
**边界**：无 GPU/低端机；冷启动；full；大图；CI 抖动。
**U 映射**：U-3、U-16、U-32。
**建议裁决**：冻结性能阈值/测量条件/预算/可见失败。
**证据等级**：A（S3-11；S4 budget）+ PI（阈值来源需基线实测）。

---

## S8-5 可解释性/UX 验收

**规则/阈值（P0）**：
```
rule_id 解释率=100%：所有 suppressed/unknown 节点/边有 rule_id（VM/审计）
unknown≠无关系：unknown 标记不渲染为“无边”；可解释
无静默：任何截断/降级有 visible state（DOM aria-live/banner/事件）
suppressed 解释：summary/rule_histogram 与 explain 可复算
可见降级：no_semantic/budget/data/stale 有 UI 文案/事件
```
- 机测方式：浏览器 DOM snapshot（Playwright/Cypress）断言 selector/aria；事件日志断言 `degraded/truncated`；G6/G7 快照；**不靠人工观感**。
**机检**：DOM/aria 断言；事件；快照；rule 直方图；unknown 语义；无静默。
**反例**：人工“看起来没问题”；silent truncate；unknown 画成无边；无 aria-live。
**边界**：无簇；空图；预算 0；全展开；读屏。
**U 映射**：U-27、U-32。
**建议裁决**：冻结可解释性/降级 DOM/事件/快照机测与 P0。
**证据等级**：A（S3-8/10；S4-6；S6-5）+ R。

---

## S8-6 G7 agent 指标

**规则/阈值**：
```
G7_EVENT{tool,tokens,refs,unknown,truncated,write_attempts,error_histogram,edition}
G7_SNAPSHOT{g7_version,g6_run_ids[],g6_frame_ids[],edition,metrics...}
write_attempts=0（P0 硬约束）
ref_completeness=resolved_refs/refs ≥0.95（软→P0 门槛待基线）
unknown_ratio、truncation_ratio 有趋势门槛；token/call 有预算
```
- G7 只引用 G6，不复制事实；采样/隐私：不存正文/PII，只 id/anchor/count；保留期 S8-11。
**机检**：G7 schema；write_attempts=0；G6 引用；ref/unknown/truncation 公式；无正文。
**反例**：写尝试非0；G7 复制 VN；含正文；无阈值。
**边界**：空会话；S9 挂；预算截断；多 KB。
**U 映射**：U-29、U-32。
**建议裁决**：冻结 G7 字段/引用/写尝试=0/阈值/隐私。
**证据等级**：A（S7-12；S7 G7）+ PI（阈值）。

---

## S8-7 数据质量度量

**规则（semantic only）**：
```
semantic_edge_coverage = |E_semantic| / |E_relation_min|（仅 count semantic，不含 structural/reference）
no_semantic_ratio = runs with status=no_semantic_edges / total runs
cluster_coverage = clusters with representative / total clusters（按 S2）
curation_ratio = curated semantic edges / semantic edges
```
- 结构/引用边 **不计入**；语料质量作为**独立信号**（`corpus_semantic_density`），不得与算法失败混判；`no_semantic_edges` 是合法状态，不是算法失败；`algorithm_failed` 才是失败。
**机检**：只语义计数；分母公式；no_semantic vs algorithm_failed 分离；coverage 可复算；G6 记录。
**反例**：把 structural 边算 semantic coverage；no_semantic 判算法失败；语料差怪 HAC。
**边界**：零语义边；小语料；多 KB；旧数据。
**U 映射**：U-6、U-27、U-32。
**建议裁决**：冻结 semantic-only/独立语料信号/no_semantic 合法。
**证据等级**：A（S2 status；S0 E_relation）+ R。

---

## S8-8 故障注入/回放

**规则**：故障矩阵：
```
budget_exhausted, no_semantic_edges, edition_stale, missing_anchor/data,
invalid_input, audit_failure, S9_unavailable, renderer_budget_exceeded
```
- 每个故障：注入方式/期望错误码/可见降级/exit code/快照；回放固定 seed/edition/env；失败可见；G6/G7 diff 确定。
- 回放确定性：同 fixture 2x 同 snapshot sha；随机源固定（seed/tie-break canonical）。
**机检**：fault harness；期望码；可见；2x sha；覆盖矩阵。
**反例**：只测正常路径；回放随机；失败静默；缺 audit failure。
**边界**：组合故障；CI 断网；审计盘满。
**U 映射**：U-27、U-32。
**建议裁决**：冻结故障矩阵/回放确定性/可见失败。
**证据等级**：A（S6 失败码；S7 错误表）+ PI（harness）。

---

## S8-9 回归门禁/CI

**规则**：
```
P0 CI gates（阻断）:
  G6 determinism/subset/closure/behind
  schema validators (S6 I-13)
  mermaid PARSE_OK
  presence/rule_id/VM 白名单
  G7 write_attempts=0
  fault matrix smoke
软门禁（告警/趋势）:
  perf p95/relative regression; flaky 重试统计
flaky: P0 不允许 flaky；失败 2 次重试仅诊断，不能改 P0 结果；quarantine 记录；本地 vs CI 用同一 harness/edition；性能 CI 只相对回归
```
- 每个 gate 命令/exit code/产物 sha；CI 与本地同脚本；差异（OS/浏览器）记录；gate 结果进 G6/G7。
**机检**：gate 清单；命令/exit；flaky 规则；本地/CI 同 harness；失败可见。
**反例**：CI 只跑单测；flaky 重试过 P0；本地/CI 两套脚本；性能硬编码。
**边界**：CI 资源小；网络；并行；缓存。
**U 映射**：U-34。
**建议裁决**：冻结 P0/软门禁/flaky/本地 CI 一致性。
**证据等级**：A（工程门禁；S6/S7）+ R。

---

## S8-10 0.5 验收清单（DoD）

**规则**：0.5 DoD 与 I-01..I-13 对齐，逐项：

| I | 验收项（P0） | 阻断级别 |
|---|---|---|
| I-01 DataSourceReader | 只读、E_relation_min、无 sidecar 写 | P0 |
| I-02 GraphViewBuilder | `(level,view_family)`、不缓存事实 | P0 |
| I-03 RegistryService | schema/history/签名/只增 | P0 |
| I-04 ClusterRunBuilder | run_id/五状态/membership | P0 |
| I-05 AdmissionService | presence/rule_id/MANDATORY/subset/事务 | P0 |
| I-06 ViewModelBuilder | S3 白名单+ADDENDUM-1/data_edge_ids 禁读 | P0 |
| I-07 RendererAdapter | 2D 实现；3D capability=false；同签名 | P0（3D 接口） |
| I-08 NavController | T01–T30/frame_id/事务 diff=0 | P0 |
| I-09 CacheStore | `.memoria/cache/graph/`、可删重建、GC | P0 |
| I-10 AuditLog | append-only、不参与事实 | P0 |
| I-11 G6Snapshot | 字段/复跑/sha/不可变 | P0 |
| I-12 ErrorMap | `GRAPH_*`+legacy+i18n | P0 |
| I-13 SchemaValidator | 字段/枚举/默认/失败码 fail-closed | P0 |

- 不做项（不阻断但不得夹带）：3D 实现、agent 写/自动 semantic、跨库、时间维、图编辑器、破坏性迁移、旧 graph-groups 迁移。
- 退出：全部 P0 通过 + G6/G7 快照冻结 + SE PASS；任一 P0 失败即不退出 0.5。
**机检**：DoD 表；I 映射；P0 通过；不做项；退出条件。
**反例**：DoD 缺 I 项；P0/P1 混；夹带 3D/agent 写。
**边界**：3D capability=false 算通过；no_semantic 合法；旧 KB。
**U 映射**：U-32、U-34。
**建议裁决**：冻结 DoD/I 映射/阻断/退出。
**证据等级**：A（S6-12；I-01..13）+ R。

---

## S8-11 度量存储/隐私/成本

**规则**：
```
G6/G7 落 artifacts/agent/verify/graph/{g6,g7}/；大小上限（单快照≤1MB；批量≤?）；保留期（默认 90 天；baseline 永久）
PII：只 id/anchor/count，不含正文；如需正文片段（S7 excerpt）不落 G7
成本：每 KB 快照数/大小；采样率；删除/重建（G6 可重建，G7 聚合可重算）
```
- G6 不可变；G7 可聚合；baseline 引用 snapshot_id；删除不删事实。
**机检**：路径/大小/保留；PII 扫描（无正文）；可重建；baseline 引用。
**反例**：快照含正文；无限增长；删除 baseline；不可重建。
**边界**：大图；高频 agent；CI 清理。
**U 映射**：U-32。
**建议裁决**：冻结路径/大小/保留/PII/重建。
**证据等级**：A（S6-8/S7-12）+ PI（保留值）。

---

## S8-12 与 S9/S10 边界

**规则**：S9 检索质量（recall/precision/latency）归 S9；S10 KP/语义边设计质量归 S10；S8 只消费其指标（间接：agent ref completeness/hit rate/data quality），不定义算法/阈值；S9/S10 指标变更不得改 S8 P0；接口 `metric_ref{owner,id,value}`。
**机检**：S8 无 S9/S10 算法；指标 owner；接口；不夹带。
**反例**：S8 定义 BM25 阈值；S10 质量算 S8 P0；S8 改 S9 算法。
**边界**：S9 不可用；S10 未实现；指标缺失。
**U 映射**：U-32、U-34。
**建议裁决**：冻结边界/指标 owner/不夹带。
**证据等级**：A（S8 章程）+ R。

---

## 附：S8 章程预注册判据自检

| 判据 | 本提案 |
|---|---|
| 每指标定义/公式/阈值/证据/失败 | S8-1..S8-12 |
| P0 可机判命令/exit/sha | S8-2/S8-3/S8-9 |
| G6 与 S6 一致/复跑/不可变 | S8-2 |
| 性能来源/测量条件 | S8-4 |
| 可解释性/降级机测 | S8-5 |
| G7 与 S7/写尝试=0 | S8-6 |
| 数据质量 semantic only | S8-7 |
| 故障注入/回放 | S8-8 |
| 回归/CI/flaky/本地 CI | S8-9 |
| 0.5 DoD/I-01..13 | S8-10 |
| S9/S10 边界 | S8-12 |
| A/B 差异逐条 | 见 `S8-objections.md` |
| 不写产品代码/契约/commit | 本文件只写设计 |

> 独立声明：本文件写作时未读 `S8-metrics-proposal-A.md`（尚未落盘）；差异与判断见 `S8-objections.md`，逐项列不合并。
