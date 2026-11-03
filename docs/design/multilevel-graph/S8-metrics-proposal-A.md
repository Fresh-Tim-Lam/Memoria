# S8 提案 A：度量与验收（G6/G7、正确性/确定性/性能/可解释、CI 与 0.5 DoD）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-331｜**日期**：2026-11-04（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结（不得违反）**：S0–S7 八份 v1 + `S3-ADDENDUM-1` + `S6-ADDENDUM-1`。
> **本场章程**：`docs/design/multilevel-graph/S8-charter.md`（S8-1..S8-12）。
> **工程输入**：`ENGINEERING-PLAN.md`（24 图、I-01..I-13）、现有 `scripts/agent/*`、`scripts/benchmark/**`（只读）。
> **独立性**：未阅读 S8 复核方草稿；本提案独立撰写。
> **纪律**：只写度量/验收契约；不写产品代码；不改 S0–S7 冻结稿；不 commit。

---

## 0. 总口径

```
S8 只回答「怎么算达标」：指标 = 定义 + 公式 + 阈值 + 证据 + 失败语义。
P0 硬门禁：机器可判（命令/exit code/snapshot sha），失败阻断；软指标有趋势/门槛。
G6 = 图契约快照（S6 字段）；G7 = agent 侧事件/快照（S7 字段；引用 G6，不复制事实）。
数据质量只算 semantic 边；结构/引用边不得计入簇/覆盖；no_semantic 合法但必须可见。
```

**证据等级**：A（冻结条款/工程/代码事实）；B（实测产物，如 S2 probe）；C（推理）；**本项目假设**（阈值/采样/CI 命令）。

---

## 1. S8-1 指标框架与优先级

**定义/规则（一句话）**：指标分 7 类（正确性/确定性/性能/可解释/agent/数据质量/回归），每类有 P0 硬门禁与软指标；**任何单一指标不得掩盖失败**，P0 失败即阻断。

**分类与优先级**：
| 类 | P0 硬门禁（阻断） | 软指标（趋势/门槛） |
|---|---|---|
| 正确性 | presence/rule_id 完整、subset、closure/behind=0、schema 校验 | 覆盖率、解释率 |
| 确定性 | HAC/run_id/tie-break 两次一致、G6 determinism_sha 相同 | 重跑耗时 |
| 性能 | max_nodes/max_edges 硬上限、无静默截断 | FPS、P95 延迟、冷/热 |
| 可解释 | suppressed/unknown 有 rule_id、unknown≠无关系、可见降级 | 解释率/可读性 |
| agent | write_attempts=0、只读工具、引用可解析 | token/call、unknown 比例、工具调用数 |
| 数据质量 | μ/β 输入==E_sem（semantic-only） | semantic 覆盖率、no_semantic 比例、簇覆盖率 |
| 回归 | CI gate PASS、G6 sha 稳定、mermaid PARSE_OK | flaky 率、性能漂移 |

**规则**：
```
每条指标必须有：metric_id, 定义, 公式, 阈值, gate=P0|SOFT, 证据(命令/快照), 失败语义
P0 失败 ⇒ gate FAIL（阻断合并/冻结/0.5 退出）；不得用平均分掩盖
soft 失败 ⇒ WARN + 记录趋势；S8 可设趋势门槛，但不阻断 P0
```
**反例**：只报“平均 FPS 60”掩盖 P0 失败；用结构边提高 coverage；把 unknown 比例低当正确。
**边界**：无簇/空图；低端硬件；CI 无 GPU；指标缺失。
**机检条件**：
```
- 指标表字段齐全；每个 P0 有可执行命令/快照断言
- 无单指标汇总替代 P0；P0 失败 exit≠0
- soft 指标有阈值和趋势记录
```
**U 映射**：U-32、U-34。
**建议裁决**：采纳 7 类 + P0/soft 双轨；禁止单指标掩盖。
**证据等级**：A（S3/S4/S6/S7 门禁；U-32）；**本项目假设**（分类命名）。

---

## 2. S8-2 G6 快照冻结

**定义/规则（一句话）**：G6 快照字段与 S6 `G6_SNAPSHOT` 完全一致；不可变、可复跑、sha 稳定；基线只在契约/edition 变更时显式更新，旧快照保留。

**字段（严格 S6）**：
```
G6_SNAPSHOT{
  g6_version, data_source_sha, run_ids[], registry_sha,
  vm_sha, frame_ids[], frame_sha, nav_sha,
  rule_histogram{rule_id:count}, node_count, edge_count,
  subset_ok, determinism_sha, closure_violations:0, behind_violations:0,
  history_signed
}
envelope（不参与 canonical sha）：{snapshot_id, created_at, command, tool_env}
snapshot_id/sha = sha256(canonical(S6 字段 + g6_version))
```
**路径/命令/基线**：
```
路径：.memoria/agent/audit/graph/g6/<snapshot_id>.json（append-only；不 GC）
基线：.memoria/agent/audit/graph/g6/baseline.json（当前基线；更新需 decision_id）
命令（示例）：python scripts/verify/g6_snapshot.py --kb <kb> \
  --level L0 --dim H --out .memoria/agent/audit/graph/g6/<id>.json
复跑：同 edition/contract/registry/params/工具版本 ⇒ 同 snapshot sha
更新：仅当 contract/registry/edition/schema 变更；旧基线保留；G6 diff 记录
```
**反例**：字段与 S6 不一致；快照含时间戳参与 sha；基线静默更新；手工改快照；不同环境浮点导致 sha 漂移。
**边界**：空 KB；no_semantic；full/default 两快照；跨机器；缓存删除后重建。
**机检条件**：
```
- 字段集 == S6 G6_SNAPSHOT；sha 可复算；同输入同 sha
- 快照不可变（内容 sha 校验）；基线更新有 decision_id
- 命令可从干净缓存重建
```
**U 映射**：U-32、U-34。
**建议裁决**：采纳 G6 字段/路径/命令/基线策略；与 S6 一致。
**证据等级**：A（S6-11；S6-8 路径；S6-9 错误）；**本项目假设**（G6 路径/命令名）。

---

## 3. S8-3 正确性 / 确定性

**定义/规则（一句话）**：正确性=契约字段/枚举/引用/闭包全部通过；确定性=同输入同输出（HAC/registry/presence/tie-break）；P0 阈值 100%。

**指标表**：
| ID | 定义/公式 | 阈值 | Gate | 证据/失败 |
|---|---|---|---|---|
| `C-HAC-DET` | `canonical partition(run1)==run2`；`run_id` 可复算 | 100% | P0 | 两次 run + G6 determinism_sha |
| `C-REGISTRY` | schema/history 链/只增不删/签名验证 | 100% | P0 | registry validator + history |
| `C-PRESENCE` | 每条候选节点/边有 presence+rule_id；unknown 仅 4 类 | 100% | P0 | AdmissionResult fixture |
| `C-SUBSET` | `shown(default) ⊆ shown(full)`；reserved==shown(default) | 100% | P0 | subset proof + G6 |
| `C-CLOSURE` | closure_violations=0；behind_violations=0 | 0 | P0 | G6 字段 |
| `C-TIE` | tie-break `(tier,hop,relation_class,label_rank,canonical_id)` 可复算 | 100% | P0 | 两次排序/固定 fixture |
| `C-SCHEMA` | 所有 schema 校验 PASS | 100% | P0 | SchemaValidator |
**反例**：只测一次；用随机顺序；允许 suppressed 边无 rule_id；subset 事后补；用结构边提升簇。
**边界**：空图；no_semantic；full；边界预算；多归属。
**机检条件**：
```
- 同 fixture 两次 run canonical/determinism sha 相同
- registry/presence/subset/closure/tie 断言各 100%
- G6 字段 closure/behind=0；失败 exit≠0
```
**U 映射**：U-13、U-14、U-27、U-32。
**建议裁决**：采纳 P0 100% 正确性/确定性指标。
**证据等级**：A（S2-4；S4-2/6/9；S6-11；S5 R-S5-10）；**本项目假设**（fixture 命名）。

---

## 4. S8-4 性能 / 预算

**定义/规则（一句话）**：硬预算（节点/边/渲染上限）为 P0；帧率/延迟为 soft 但有测量条件与门槛；冷/热、首开/切页签分别测。

**指标表**：
| ID | 定义/条件 | 阈值 | Gate |
|---|---|---|---|
| `P-NODES` | 单屏 VM nodes | ≤200（S8 可调） | P0 |
| `P-EDGES` | 单屏 VM edges | ≤400 | P0 |
| `P-BUDGET` | 超预算可见 suppressed+rule_id；无静默 | 100% | P0 |
| `P-FPS` | 参考硬件、2D、N=30 秒、P50 | ≥55（目标 60；低端≥30） | soft |
| `P-ANIM` | 动画时长（reduced motion=0） | ≤180ms | soft |
| `P-INT-P95` | 交互到下一帧 P95（参考硬件/浏览器） | ≤200ms（**假设**） | soft |
| `P-FIRST` | 首开首帧 P95（冷/热分别） | ≤1500ms（**假设**） | soft |
| `P-TAB` | 切页签回到图谱 P95 | ≤300ms（**假设**） | soft |
| `P-ADM` | Admission P95（单帧） | ≤50ms（**假设**） | soft |
**测量条件**：
```
参考硬件/浏览器版本/视口/主题/缩放；冷缓存 vs 热缓存；样本 N≥30；
首开/切页签/连续交互分开统计；CI 无 GPU ⇒ 只跑结构性 P0；FPS 本地门禁
```
**反例**：只测热缓存；用平均 FPS 掩盖 P95；CI 上测 FPS；预算超限不标。
**边界**：低端硬件；大图；3D capability=false；无数据。
**机检条件**：
```
- P0 计数/无静默截断；基准 fixture
- FPS/延迟有环境记录与样本；soft 阈值可配置
- 预算失败可见（banner/error），不白屏
```
**U 映射**：U-3、U-16、U-32。
**建议裁决**：采纳硬预算 P0 + 性能 soft 指标/条件；数值 S8 可调。
**证据等级**：A（S3-11 60/30/180ms/200/400；S4-2）；**本项目假设**（P95/首开数值）。

---

## 5. S8-5 可解释性 / UX 验收

**定义/规则（一句话）**：所有 suppressed/unknown 可解释（rule_id）、unknown≠无关系、截断/降级可见；用 VM/Admission fixture + DOM 断言机测，不靠人工观感。

**指标表**：
| ID | 定义/公式 | 阈值 | Gate | 机测 |
|---|---|---|---|---|
| `X-RULE` | `non_shown edges with rule_id / non_shown edges` | 100% | P0 | AdmissionResult + VM edge presence |
| `X-SUMMARY` | `suppressed_summary count == suppressed_count`；rule 直方图一致 | 100% | P0 | VM fixture |
| `X-UNKNOWN` | unknown 全部带 reason；unknown 不回答“无关系” | 100% | P0 | fixture + 响应检查 |
| `X-TRUNC` | truncated/omitted 字段在超预算时出现 | 100% | P0 | 预算注入 |
| `X-DEGRADE` | no_semantic/stale/error 有可见 banner/aria | 100% | P0 | DOM/aria |
| `X-EXPLAIN-RATE` | `explain_edge 可解释 suppressed / 请求` | ≥95% | soft | 抽样 |
**反例**：suppressed 无 rule_id；unknown 省略；截断不标；降级只 console；用颜色暗示。
**边界**：no_semantic；预算极小；unknown 4 类；审计失败。
**机检条件**：
```
- VM/Admission fixture 断言 rule coverage==1
- DOM/aria 断言 banner/live region 存在
- 超预算/未知场景 fixture；无静默
```
**U 映射**：U-3、U-13、U-27。
**建议裁决**：采纳可解释性 P0 + DOM/VM 机测。
**证据等级**：A（S3-8/S3-10；S4-6；S7-11）；**本项目假设**（解释率/抽样）。

---

## 6. S8-6 G7 agent 指标

**定义/规则（一句话）**：G7 按 S7 字段采集 agent 侧指标；只引用 G6 `run_ids/frame_ids`，不复制事实/正文；`write_attempts=0` 为 P0。

**指标表**：
| ID | 定义/公式 | 阈值 | Gate |
|---|---|---|---|
| `A-WRITE` | 写工具/写路径尝试 | 0 | P0 |
| `A-READONLY` | 工具 `read_only=true` 比例 | 100% | P0 |
| `A-REF` | `resolved_refs / refs`（引用完整率） | ≥99% | soft |
| `A-UNKNOWN` | `unknown_claims / claims` | ≤20% | soft |
| `A-TOKEN` | `sum(tokens)/calls` | ≤4000 | soft |
| `A-CALLS` | 每任务工具调用数 | ≤8 | soft |
| `A-DEGRADE` | 降级/错误有可见标记 | 100% | P0 |
| `A-AUDIT` | 审计落盘成功 | 100% | P0 |
**采样/隐私**：
```
100% agent 调用记 G7_EVENT；G7_SNAPSHOT 聚合；不存正文/excerpt/文件内容；
只存 ids/anchor 引用/counts/token/status；保留期 S8-11；阈值 S8 可调。
```
**反例**：G7 存用户正文；write 不记；只统计总和；unknown 不上报。
**边界**：空会话；S9 不可用；no_semantic；极端 token。
**机检条件**：
```
- G7 字段与 S7 一致；write_attempts=0；read_only 100%
- 引用/unknown/token 可复算；无正文/PII
- G7 引用 g6_run_ids/frame_ids
```
**U 映射**：U-2、U-29、U-32。
**建议裁决**：采纳 G7 指标/采样/隐私；写=0 P0。
**证据等级**：A（S7-12；S7-1/6；S6-8 审计）；**本项目假设**（阈值/采样）。

---

## 7. S8-7 数据质量

**定义/规则（一句话）**：只统计 semantic 边；结构/引用边不得计入簇/覆盖/质量；no_semantic 是合法语料信号，不是用结构边补簇的理由。

**指标表**：
| ID | 定义 | 阈值 | Gate |
|---|---|---|---|
| `D-SEM-PURITY` | `μ/β_input == E_sem`；非 semantic 边进簇判据=0 | 100% | P0 |
| `D-SEM-EDGE` | `semantic_edge_pairs / relation_pairs` | 语料信号（无 P0 下限） | soft |
| `D-SEM-KP` | `KPs incident to E_sem / all KPs` | 信号 | soft |
| `D-NOSEM` | `no_semantic_edges` run 比例；coverage=0 | 合法；必须可见 | soft/P0 可见性 |
| `D-CLUSTER-COV` | `covered_kp / total_kp`（S2-12） | 信号；不得恒 1 | soft |
| `D-CURATION` | curated semantic edges / semantic edges | 信号 | soft |
**规则**：
```
结构/reference 不得进入 μ/β、簇覆盖、质量分子；不得用其“提升 coverage”
frozen 语料/showcase 的 E_sem=0（S2 probe）⇒ no_semantic 合法，不是失败
```
**反例**：用 contain(structural) 当语义；coverage=Σ|C|/|K| 恒 1；no_semantic 隐藏。
**边界**：无 semantic；部分 semantic；多归属；curation 变更。
**机检条件**：
```
- D-SEM-PURITY==100%；非 semantic 边不进入簇
- no_semantic 可见；coverage 按 S2 公式
- 指标可复算（run/DataSource）
```
**U 映射**：U-1、U-13、U-14、U-27。
**建议裁决**：采纳 semantic-only 数据质量；结构边不计；no_semantic 合法可见。
**证据等级**：A（S2-2/3/12；S2 probe B）；**本项目假设**（信号阈值）。

---

## 8. S8-8 故障注入 / 回放

**定义/规则（一句话）**：对预算/空语义/stale/缺失/非法/审计失败注入，验证预期错误/降级可见、无静默、可确定性回放；G6 快照 diff 可复现。

**故障矩阵**：
| 注入 | 预期 | 证据 |
|---|---|---|
| 预算超限 | suppressed+rule_id / 可见 banner | VM/G6 |
| no_semantic | data_state=empty_nosemantic；无簇；banner | VM/DOM |
| stale edition | `GRAPH_EDITION_STALE`；不混用 | 响应/审计 |
| 数据缺失 | unknown/`GRAPH_ANCHOR_STALE`；不编造 | 响应 |
| 非法输入 | `GRAPH_TOOL_INPUT_INVALID`/`GRAPH_INPUT_INVALID`；fail-closed | 响应 |
| 审计失败 | `GRAPH_TOOL_AUDIT_FAILED`；可见 | 审计/响应 |
**回放**：
```
固定 fixture/edition/params；两次回放同 G6 determinism_sha；
G6 diff 列字段差异；故障注入不得改事实；无静默 fallback
```
**反例**：故障静默降级；回放随机；G6 diff 忽略 schema；审计失败仍返回成功。
**边界**：组合故障；缓存损坏；空图；低端。
**机检条件**：
```
- 六类故障各有可见错误/降级；无静默
- 同 fixture 两次回放 sha 相同
- G6 diff 可读/可断言
```
**U 映射**：U-27、U-32。
**建议裁决**：采纳六类故障注入 + 确定性回放 + G6 diff。
**证据等级**：A（S4-6/S6-9/S7-11；S5 事务）；**本项目假设**（fixture）。

---

## 9. S8-9 回归门禁 / CI

**定义/规则（一句话）**：P0 门禁进 CI（schema/确定性/presence/subset/closure/审计/无写/G6/mermaid）；性能与 FPS 本地/参考硬件；flaky 有隔离与复跑上限，不得放宽阈值。

**CI gate 清单**：
| gate | 内容 | 阻断 |
|---|---|---|
| G-SCHEMA | SchemaValidator 全 schema | P0 |
| G-DET | 两次 run/G6 determinism_sha | P0 |
| G-PRESENCE | presence/rule_id 100% | P0 |
| G-SUBSET | subset proof | P0 |
| G-CLOSURE | closure/behind=0 | P0 |
| G-AUDIT | 审计 append-only/失败可见 | P0 |
| G-NOWRITE | 无 sidecar/写工具；write_attempts=0 | P0 |
| G-G6 | G6 字段/sha/基线 diff | P0 |
| G-MERMAID | 所有 mermaid PARSE_OK | P0 |
| G-I18N | i18n key 存在 | P1 |
| G-FAULT | 故障注入 6 类 | P1 |
| G-PERF | FPS/P95（本地/参考硬件） | soft |
**规则**：
```
CI 只跑结构性 P0（无 GPU/浏览器可用）；FPS/延迟在本地参考硬件跑；
flaky：同一 gate 3 次内失败可复核；不得降低阈值；隔离 flaky 需 owner+issue；
G6 baseline 变化必须 PR 说明 + decision_id。
```
**反例**：CI 跑 FPS 用容器数值；flaky 重试到过；踩阈值下调；mermaid 不解析。
**边界**：无浏览器 CI；大图；跨平台。
**机检条件**：
```
- P0 gate 有命令/exit code；G6 基线 diff
- CI 与本地结果差异记录；flaky 策略可审计
- 阈值不放宽；mermaid 解析
```
**U 映射**：U-32、U-34。
**建议裁决**：采纳 P0 CI 清单 + 本地性能 + flaky 政策。
**证据等级**：A（S3-11；S6-11；S5a PARSE_OK；现有门禁 scripts/agent/*）；**本项目假设**（CI 命令/阈值）。

---

## 10. S8-10 0.5 验收清单 / DoD

**定义/规则（一句话）**：0.5 以 I-01..I-13 为验收单元，每项有可执行验收、阻断级别；不做项明确；P0 全 PASS 才退出。

**DoD 表**：
| 接口 | 验收项 | 阻断 |
|---|---|---|
| I-01 DataSourceReader | 只读/`expand_data_edges⊆DataSource.edges`/canonical id | P0 |
| I-02 GraphViewBuilder | `(level,view_family)` partition/kind | P0 |
| I-03 RegistryService | schema/history 链/只增不删/签名（可选） | P0 |
| I-04 ClusterRunBuilder | HAC 两次一致/五状态/no_semantic 合法 | P0 |
| I-05 AdmissionService | focus-only 一跳/presence/rule/MANDATORY/subset/事务 | P0 |
| I-06 ViewModelBuilder | S3 白名单+ADDENDUM-1/node presence/aggregate | P0 |
| I-07 RendererAdapter | 2D 渲染/不裁剪/同签名（3D capability=false） | P0 |
| I-08 NavController | T01–T30/S5a/frame_id/事务 diff=0 | P0 |
| I-09 CacheStore | 删缓存重建/GC 不删事实 | P0 |
| I-10 AuditLog | append-only/每次工具审计 | P0 |
| I-11 G6Snapshot | 字段/sha/复跑/基线 | P0 |
| I-12 ErrorMap | `GRAPH_*`+legacy/i18n | P0 |
| I-13 SchemaValidator | 全 schema fail-closed | P0 |
**不做项**：3D 实现、agent 写、自动 semantic、跨库、时间维、图编辑器、破坏性迁移、S7–S10（S8 验收不包含其算法）。
**反例**：用截图代替验收；I-07 只做 3D 未做 2D；G6 无 sha；DoD 漏 I-12。
**边界**：2D-only 0.5；无 semantic；低端；旧 KB。
**机检条件**：
```
- I-01..I-13 各有 fixture/命令/证据；P0 全 PASS
- 不做项有 feature flag/守卫；无夹带
- G6/G7 快照可复跑
```
**U 映射**：U-32、U-34。
**建议裁决**：采纳 I-01..I-13 DoD + 不做项 + P0 阻断。
**证据等级**：A（S6-12 0.5 边界；I-01..I-13 工程）；**本项目假设**（验收命令）。

---

## 11. S8-11 度量存储 / 隐私 / 成本

**定义/规则（一句话）**：G6 快照/基线不可变保留；G7 事件聚合保留 90 天/10 万条；只存 id/anchor 引用/counts，不存正文/excerpt/PII；删除/重建不影响事实。

**存储/保留**：
```
G6：.memoria/agent/audit/graph/g6/；快照/基线不 GC（每个 edition 保留）
G7：.memoria/agent/audit/graph/g7/；事件 90 天或 100k 条（先到）；快照聚合长期
大小：G6 ≤1MB/快照；G7 ≤64MB/库；超限滚动/告警
隐私：不存正文/excerpt/文件内容/用户输入；只 id/anchor 引用；G7 不含 source_excerpt
删除：删 G7 事件不影响事实；G6 删派生可重建（基线需重生成）
成本：每 KB 每月 G6/G7 增量 <X MB（S8 定）；不阻塞主流程
```
**反例**：G7 存正文；G6 写进事实源；无上限；删 G6 断审计。
**边界**：大 KB；多会话；审计失败；迁移。
**机检条件**：
```
- 路径/保留期/上限；无正文/PII 字段；G6/G7 可重建/可删
- 成本/大小监控
```
**U 映射**：U-29、U-32。
**建议裁决**：采纳存储/保留/隐私/成本策略。
**证据等级**：A（S6-8 路径；S7-12 G7；S6-11 G6）；**本项目假设**（保留期/大小）。

---

## 12. S8-12 与 S9 / S10 度量边界

**定义/规则（一句话）**：S9 检索质量（recall/precision/latency/recall@k）与 S10 KP 质量（覆盖/正确/命名/粒度）归各自；S8 只消费其指标并定义接口/验收形态，不定义算法/阈值。

**边界**：
```
S9：retrieval recall/precision/latency/empty rate；S8 只要求接口返回 candidate_refs 与错误码
S10：KP 质量/语义边写入质量/curation 正确性；S8 只要求通过 S7 resolve_ref 可验证
S8 指标：消费 S9/S10 提供的测量结果，不重算其算法；边界指标仅作 regression gate
G6/G7 可引用 S9/S10 指标但不在 S8 定义其算法
```
**反例**：S8 自己实现 recall；用 S9 分数当事实；S10 质量问题算到 S8。
**边界**：S9 不可用；S10 未实现；跨 KB。
**机检条件**：
```
- S8 无检索/聚类/KP 设计实现；指标表只消费接口
- S9/S10 指标有 own 定义；S8 仅 gate/阈值引用
```
**U 映射**：U-32、U-34。
**建议裁决**：采纳边界；S9/S10 指标归各自。
**证据等级**：A（S8 章程 §2；S6-12；S7-8/9）；**本项目假设**（接口形态）。

---

## 13. 覆盖矩阵

| 侧 | 覆盖 | 落点 |
|---|---|---|
| S0–S2 | presence/簇/no_semantic/数据质量 | S8-3/S8-7 |
| S3 | 性能/VM/a11y | S8-4/S8-5 |
| S4 | 预算/subset/rule | S8-3/S8-4 |
| S5 | T01–T30/事务 | S8-9/S8-10 |
| S6 | G6/路径/错误 | S8-2/S8-9/S8-10 |
| S7 | G7/工具/只读 | S8-6 |
| U | U-2/3/6/10/11/12/13/14/15/17/19/27/32/34 | 各条 U 映射 + 本矩阵 |

---

## 14. 仍存争议 / 待 Lead·SE 裁决

1. **性能阈值来源**：60/30 FPS、180ms 来自 S3；P95 交互/首开数值为本项目假设，需 S8/SE 用实测基线定。
2. **G6 路径/命令**：`.memoria/agent/audit/graph/g6/` 与 `scripts/verify/g6_snapshot.py` 需 S6a/SE 确认（S6 未冻结 G6 路径）。
3. **G7 保留期/上限**：90 天/100k/64MB 为建议，需 S8/隐私评审。
4. **`D-SEM-*` 是否设 P0 下限**：本提案只定语义纯净 P0；coverage 为语料信号，避免用结构边凑。
5. **CI 范围**：无 GPU/浏览器时只跑结构 P0；性能本地门禁是否阻断发布需 S8/CI 决定。
6. **0.5 I-07**：只 2D、3D capability=false；3D 验收是否后置需 S8/SE 确认。

---

## 15. 证据锚

```text
S0：S0-terms-v1.md:56-61（presence）、:100-107（D-3）、:75-79（VM）
S1：S1-dimensions-v1.md:22-51（registry）、:99-107（present）
S2：S2-clustering-v1.md:17-45（簇/run/五状态）、:73-76（no_semantic）
S3：S3-visual-v1.md:36-39（presence）、:66-69（预算/60/180）、:71-75（VM）
S4：S4-render-v1.md:26-60（一跳/presence/MANDATORY/subset）
S5：S5-nav-v1.md:21-75,117-155（状态/T01–T30）
S6：S6-contract-v1.md:57-66（存储/审计/错误）、:71-73（G6）、:75-78（0.5）
S7：S7-agent-v1.md:20-76（G7/工具/只读）
工程：ENGINEERING-PLAN.md:933-945（I-01..I-13）、:1026-1048（ST）
实测：artifacts/agent/verify/debate/graph-utility/s2-semantic-probe/results.json（E_sem=0）
门禁：scripts/agent/*（compontent/curator/decide 等）、scripts/benchmark/**（只读）
```
