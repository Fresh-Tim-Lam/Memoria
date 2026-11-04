# 20. 0.5 图谱板块实现计划（2D 多层次图谱；2026-11-04 冻结后）

> **本文件是 `docs/todo.md §20` 的详情附件**。状态事实源 = `docs/todo.md §20` 索引行；本文件只放范围/批次/验收/风险。
> **依据（冻结输入，不得改写）**：`docs/design/multilevel-graph/DESIGN-SERIES-COMPLETE.md`（S0–S10 全冻结）、`S6-contract-v1.md` + `S6-ADDENDUM-1/2`、`S7-agent-v1.md`、`S8-metrics-v1.md`、`S9-retrieval-v1.md`、`S10-kp-v1.md`（**不在 0.5**）、`ENGINEERING-PLAN.md`（I-01..I-13）。
> **版本口径**：0.5（按 `docs/conventions/version.md#L12` 人 2026-10-27 裁：0.5 = 图谱驱动的 agent 检索优化；0.6 = 导出/导入）。**不写三段版本号**。
> **本文含任务板 id**（创建后回填）；**不含实现代码**。

## 0. 一句话

0.5 交付**可被 agent 只读消费的 2D 多层次图谱板块**：按 S6a 13 个接口（I-01..I-13）分 **6 批**实现，DoD 以 S8 的 I-05/06/07/08 P0 为硬阻断（I-07 只验 2D、3D `capability=false`），检索侧按 S9 契约出 `GATE-RET`；**S10（agent 写 KP/语义边）不在本版**。

## 1. 审计现状（先审计再排期）

### 1.1 `docs/todo.md §13` 当前状态（2026-11-04 实测，索引统计行）

| 类别 | 数量 | 说明 |
| --- | --- | --- |
| 活跃索引 | **53** | 其中 ✅10 / 🔄·K2 **30** / 🔄 3 / ⏳7 / 💡1 / ⚠️1 / 🔴1 |
| 已归档 ✅→§10.5 | 27 | 已完成并出表 |
| 已作废 ⛔ | 27 | 已并入/作废（含 AG59/60/63 等） |
| 合计 | **107 行** | 证据：`docs/todo.md §13` 统计行；详情 `docs/todo/13-agent-panel.md` |

⇒ §13 是 **agent 面板**域，**与多层次图谱实现不重叠**；不重复排期。K2 30 条仍为"代码完成·真机验收未闭环"，**不是本版范围**（除 Lead 另有指令）。

### 1.2 图谱 / agent 相关既有台账项

| 台账位置 | 条目 | 状态 | 与本计划关系 |
| --- | --- | --- | --- |
| §4 图谱 | **G01** 图谱推理·新边提议 + 边类型梳理 | 🔄 K1 | 边提议/边类型属 **S10 未来**（0.5 不做）；不排入 |
| §4 图谱 | **G02** 边抑制后点构建/刷新仍显示该边 | 🔴 | 新引擎的 presence/subset（B3）会替换该路径；**B4 收口时复验并收口**，不单独建 0.5 任务 |
| §4 图谱 | **G05** 图谱节点渲染性能（D2b 树扁平化待做） | 🔄 K1 | 旧 2D 引擎性能债；B4 若替换旧 2D 入口 ⇒ 需在 B4 后复核（见风险 R5），**不并入 0.5 DoD** |
| §12 | **C4** 图谱增量更新（布局/数据层） | ⏳ K1 | 增量更新不在 S6a 0.5 边界（S9 v1 全量重建）；**不排入** |
| §12 | **E3** design 文档评审（export/maintenance/durable-flush） | ⏳ K3 | 非图谱，不排入 |
| §10 归档 | KG 本体 v0/v0.2、KG 可视化 v0（节点大小连续/标签 LOD/布局种子/3D 光晕等，0.4.10 已发布） | ✅ | **已交付，不重排**；0.5 新引擎需做**功能对齐**（见 §6 R1） |
| §19 ideas | **I-14** 确保知识图谱设计完善（本体+可视化 v0） | ✅ 已落地 | 设计已冻结；本计划是其实现 |
| §19 ideas | **I-23**「图谱作为 agent 索引」 | ⏳ 待排期 | **本计划 B6 即该项的首个交付**（S7 只读工具）；验收用 S8 G7/S9 GATE-RET，不重复立项 |
| §19 ideas | **I-27** KGviz 三项真人判读（U-KGV-5） | ⏳ 待排期 | 需人参与；**不并入 0.5**，保持待排期 |
| §18 | 导出/导入板块（原写 0.5.x） | 计划在案 | **版本归属改为 0.6**（见 §1.4）；不排入 0.5 |

### 1.3 上一版（0.4.11，2026-11-03，tag v0.4.11）已带走什么（避免重复排期）

依据 `docs/releases/0.4.11-notes.md`（中英双语发布说明）与 `git log v0.4.10..v0.4.11`：

- **带走（已发布）**：① 语义整体—部分 curation（`curate_contain` / `contain_kind`，KG 本体 v0.2，含写前备份/undo/审计身份）；② 7 项交互/词法修复（mermaid 小窗滚动与关闭按钮 task-198、链接面板 mermaid、行内公式 Markdown 活跃字符、预览图片编辑回顶、块编辑聚焦、ask 快照携带 pending summons 等）；③ 许可切 AGPL-3.0-only（v0.4.11 起）；④ 团队治理/todo 索引拆分等内部改进。
- **没带走（明确 docs-only）**：多层级图谱 **S0–S5 仅设计冻结，S6 进行中**；**0.4.11 不含任何多层级图谱 UI/行为**。S6 之后 S7–S10 在 0.4.11 发布后继续冻结（现在已全冻结）。
- **结论**：I-01..I-13 **零实现**，无重复排期风险；0.4.11 已落地的 KG 语义包含是 **S10 未来的前置**（0.5 不重做）；发布说明已写明"实现推迟到 0.5"。

### 1.4 版本归属修正（本次审计发现的漂移）

- `docs/conventions/version.md#L12`（人 2026-10-27 裁）：**0.5 = 图谱驱动的 agent 检索优化；0.6 = 导出/导入板块**。
- `docs/todo.md §18` 仍写"0.5.x 导出/导入板块"；`docs/todo/ideas.md` **I-29** 仍写"0.5.x 专属导出/导入" ⇒ **两者已被同一裁决取代**。本计划随附修正：§18 改 0.6；I-29 标"已否决或已缩范围（被 2026-10-27 版本路线取代）"。**版本号本身（version.md）不改**（人权限）。

## 2. 范围（做 / 不做）

### 2.1 做（0.5）

- **2D 多层次图谱板块**：S6a I-01..I-13（DataSourceReader → GraphViewBuilder → RegistryService → ClusterRunBuilder → AdmissionService → ViewModelBuilder → RendererAdapter(2D) → NavController → CacheStore → AuditLog → G6Snapshot → ErrorMap → SchemaValidator）。
- **agent 只读消费**：S7 的 5 个只读工具（`graph_focus` / `graph_explain_edge` / `graph_expand_cluster` / `graph_summary` / `graph_resolve_ref`）+ `candidate_ref`/`edition`/审计；**S9 检索契约**（candidate/ranking、golden、`GATE-RET`）作为 B6 交付。
- **验收**：S8 DoD（I-05/06/07/08 P0；I-07 只验 2D）+ G6/G7 快照 + `GATE-RET`。

### 2.2 不做（0.5 边界，逐条）

| 不做 | 依据 |
| --- | --- |
| **3D 实现** | S6a 定稿：3D 只留 I-07 接口，`capability=false`，不阻断 |
| **S10：agent 写 KP/语义边/curation** | `S10-kp-v1.md#S10-12`：S10 不在 0.5 |
| **自动 semantic（自动推断语义边）** | S8-7 / S10-4：语义只来自 `E_sem` 门槛，结构边不得冒充 |
| **跨库、时间维** | S6-12 明列不做 |
| **图编辑器** | 同上 |
| **破坏性迁移** | S6-10：旧 graph-groups 不迁移、只读 fallback 默认关闭 |
| **`graph_path` 隐式多跳** | S7-3：v1 无 path；两跳需另开修订 |
| **两套存储/第二事实源** | S6-1：事实 = md + sidecar/manifest，图谱/缓存全派生 |

## 3. 批次/顺序（6 批，每批独立可验收）

> 依赖方向：B1→B2→B3→B4→B5；**B6 依赖 B1–B5 的只读接口与 VM（可与 B4 并行做接口层，但验收需 B4 的 2D VM 真数据）**。
> 预估 = **估算**（无历史速率基线，含测试/证据但**不含冲突缓冲**）；单位：人·工作日。

| 批 | 内容（I 项） | 依赖 | 写域（产物级） | 预估 | 独立验收（见 §4/§5） |
| --- | --- | --- | --- | --- | --- |
| **B1 契约与只读底座** | I-01 `DataSourceReader`、I-12 `ErrorMap`、I-13 `SchemaValidator` + 契约 JSON schema 落盘 + `tests/graph` 骨架 | 无（冻结契约） | `src/memoria/graph/multilevel/{datasource,errors,schema}.py`、`src/memoria/graph/contracts/schemas/*.json`、`tests/graph/test_contracts.py`、`tests/graph/fixtures/**` | 2–3 | 只读/无 sidecar 写（D-3）；schema fail-closed；错误码表覆盖 S6+ADDENDUM-1/2；契约冻结 sha 绑定 |
| **B2 视图 / 维度 / 聚类** | I-02 `GraphViewBuilder`、I-03 `RegistryService`、I-04 `ClusterRunBuilder` | B1 | `src/memoria/graph/multilevel/{graph_view,registry,cluster_run}.py`、`tests/graph/test_graph_view.py`、`test_registry.py`、`test_cluster_run.py` | 3–4 | `run_id` 可复算、2× 确定性 100%；五状态/多归属；registry 只增不删/history 链；无结构边冒充 semantic |
| **B3 取景与 VM（P0）** | I-05 `AdmissionService`、I-06 `ViewModelBuilder` | B2 | `src/memoria/graph/multilevel/{admission,view_model}.py`、`tests/graph/test_admission.py`、`test_view_model.py` | 3–4 | **P0**：X-RULE=100%（节点+边、分项）、subset_ok、closure/behind=0、presence 11 rule_id、MANDATORY、事务化 diff=0、VM 白名单、`data_edge_ids` Renderer 禁读 |
| **B4 2D 渲染 + 导航（P0）** | I-07 `RendererAdapter`（**仅 2D**；3D `capability=false`）、I-08 `NavController` | B3 | `src/memoria/ui/static/app/js/graph-multilevel/**`、必要的 `graph-view-2d.js` 适配（只加挂载点）、`tests/graph/render/**`、`tests/graph/nav/**`、`node --check` | 4–6 | **P0**：2D 渲染 smoke/事件/同签名；`max_nodes=200`/`max_edges=400`/动画≤180ms（冻结值 P0，结构断言）；3D capability=false 不阻断；T01–T30 转换矩阵；`frame_id` 可复算；nav 事务化 diff=0；**旧 KGviz 功能对齐清单**（§6 R1） |
| **B5 缓存 / 审计 / G6/G7 + 门禁工具（P1，含 CI）** | I-09 `CacheStore`、I-10 `AuditLog`、I-11 `G6Snapshot` + **创建缺失的验收工具**（见 §5） | B1–B4 | `src/memoria/graph/multilevel/{cache,audit,g6}.py`、`scripts/benchmark/graph/{g6_snapshot,g7_snapshot}.py`、`scripts/verify/parse_mermaid.js`、`tests/graph/test_g6.py`、`tests/graph/test_g7.py`、`tests/graph/test_cache_audit.py` | 3–4 | G6 唯一路径/字段/sha/2× replay/≤1MB；G7 无正文/PII/保留期；GC 只删 cache；audit append-only；P0 门禁脚本 exit≠0 可红（负向自证）；mermaid 27 图 `PARSE_OK` |
| **B6 agent 只读消费 + 检索（0.5 价值出口）** | S7 5 工具 + S9 检索契约/golden/`GATE-RET` | B1–B5（B4 的 VM 真数据） | `src/memoria/services/agent/tools/graph.py`（新）、`src/memoria/graph/retrieval/**`、`scripts/verify/eval-retrieval.py`、`docs/design/multilevel-graph/golden/S9-golden-set.json`（**新建，不改冻结稿**）、`tests/graph/test_agent_tools.py`、`test_retrieval_eval.py` | 4–6 | S7：5 工具 schema/错误码/edition/幂等/审计；`expand` 不改 nav；`resolve_ref` excerpt ≤500 字/stale；无写工具/写路径（grep）。S9：`eval-retrieval.py` exit0、golden 2× 确定性、provisional 阈值（recall@5≥0.80 等）、`GATE-RET`、**G-G7（`write_attempts=0`/`read_only=100%`/无正文）** |

**总预估（估算）：19–27 人·工作日**（不含 Lead 裁决/人审与冲突缓冲；0.5 发版门禁另计）。

## 4. S8 DoD 映射（I-01..I-13）

| I | 模块 | 阻断 | 批次 |
| --- | --- | --- | --- |
| I-01 | DataSourceReader | P1 | B1 |
| I-02 | GraphViewBuilder | P1 | B2 |
| I-03 | RegistryService | P1 | B2 |
| I-04 | ClusterRunBuilder | P1 | B2 |
| I-05 | AdmissionService | **P0** | B3 |
| I-06 | ViewModelBuilder | **P0** | B3 |
| I-07 | RendererAdapter | **P0**（3D capability=false 不阻断） | B4 |
| I-08 | NavController | **P0** | B4 |
| I-09 | CacheStore | P1 | B5 |
| I-10 | AuditLog | P1 | B5 |
| I-11 | G6Snapshot | P1 | B5 |
| I-12 | ErrorMap | P1 | B1 |
| I-13 | SchemaValidator | P1 | B1 |

> 发 0.5 前：**P0 全 PASS**；P1 有记录（S8-10）。S9 `GATE-RET` 与 S7 G-G7 按 B6 验收（若 Lead 将 B6 移出 0.5，见 §7 需人裁决 1）。

## 5. 验收门禁 / 命令（**关键：这些工具目前仓库里还不存在**）

S8a/S9a 已冻结"命令"，但**实测仓库现状**：`tests/graph/`、`scripts/benchmark/graph/`、`scripts/verify/`、`docs/design/multilevel-graph/golden/`、`parse_mermaid.js` **均不存在**（设计阶段未入库；`pytest -q tests/graph` 会直接失败）。⇒ **B5/B6 必须先造工具**，否则 DoD 不可执行。建议门禁脚本（0.5 内新建）：

```
python -m pytest -q tests/graph
node --check <changed js>
node scripts/verify/parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md   # 27 图 PARSE_OK（vendored mermaid 11.16.0 + jsdom）
python scripts/benchmark/graph/g6_snapshot.py --verify-baseline
python scripts/benchmark/graph/g7_snapshot.py --assert-g-g7
python scripts/verify/eval-retrieval.py --kb <kb> --golden docs/design/multilevel-graph/golden/S9-golden-set.json --out artifacts/agent/verify/graph/retrieval/<run>.json   # GATE-RET
python scripts/check_todo_size.py            # 台账
python scripts/agent/team_audit.py           # 过程
```

- P0 失败 exit≠0 + 产物 sha；**负向自证**：B5 必须演示"故意破坏一个 P0 断言 ⇒ 门禁必须红"（防"看起来成功"）。
- 性能：冻结值（`max_nodes=200`/`max_edges=400`/60fps/动画≤180ms）P0 用**结构断言**；P95 假设值只本地参考硬件（N≥30、冷/热、环境记录），CI 不阻断性能 P0。
- flaky：P0 不豁免；诊断重试 ≤3；阈值不得因 flaky 下调。

## 6. 风险（含已实测前提）

| # | 风险 | 影响 | 缓解 |
| --- | --- | --- | --- |
| **R1** | **新引擎替换旧 2D 图谱 UI ⇒ 功能回退**：0.4.10 已发布 KGviz v0（节点大小连续、标签 LOD/避让、布局确定性种子+会话内保位、tooltip、3D 光晕等）；0.5 新架构不天然包含这些 | 用户可见回退，违反"不破坏已发布能力" | B4 加**功能对齐清单**（逐项对照 0.4.10 已发布项 + 现有 G02/G05 场景）；feature flag + 回退开关；对齐项不达标不得发 0.5（登记为 B4 验收） |
| **R2** | **验收工具/黄金集缺席**（§5 实测） | DoD 不可执行，B5/B6 返工 | B5/B6 把"造工具"列为交付物与验收；B1 先落 `tests/graph` 骨架 |
| **R3** | 契约实现漂移：S6 v1 + 2 个 ADDENDUM 的字段/错误码若被"顺手改" | 审计/评测不可复核 | I-13 fail-closed + S6 sha 绑定测试；**不改冻结设计稿**；新增码只走 ADDENDUM |
| **R4** | 聚类/取景确定性依赖 edition/manifest；用户库写操作（agent 读不写，但人编辑）会触发 edition 变化 | G6 determinism 假红/缓存频繁重建 | B2/B5 确定性测试固定 fixture sha；edition 不匹配"重建"而非"报错"；G6 快照带 edition |
| **R5** | G05（旧 2D 引擎 D2b 性能债）与新渲染器关系未定：若 B4 替换旧入口，D2b 可能自然消解，也可能使性能回退（新多层级取景/簇聚合） | 性能预算 P0 风险 + 台账状态失真 | B4 后**实测复核 G05**：新架构达标则 G05 收口/改判，不达标则保留并另排；见 §7 需人裁决 4 |
| **R6** | 写域冲突：`graph-*.js` / `app.js` / `agent/tools/kb.py` 与现有 Owner（render-perf / sync-mapper / agent-arch）重叠 | 串行化等待/冲突 | 批次**串行** B1→B5；B6 在 B4 后；每个实现任务写域到文件级，Lead 派发时串行 |
| **R7** | 隐私：G6/G7/审计写入用户库 `.memoria/agent/audit/graph/**` | 用户数据边界 | 只存 id/anchor/引用/counts，**无正文/excerpt/PII**（S8-11）；G7 保留期与大小上限 |
| **R8** | S9 golden/阈值是 **provisional**（S9-10 明示发布前需基线校准） | GATE-RET 初期可能误红 | B6 标 provisional；校准写回 S9 修订（不重开）；`GATE-RET` 作为**趋势+硬门槛组合**（阈值修订走决策） |
| **R9** | 已知台账漂移：§18 版本归属、I-29 规则被取代（§1.4） | 后人按旧版本号排期 | 本计划顺手修正（todo/ideas 层），version.md 不改（人权限） |

## 7. Lead 裁决（2026-11-04，`dec-20261104-7e6e9d63`）

1. **B6 进 0.5**：B6（S7 5 只读工具 + S9 检索/golden/GATE-RET）算 0.5 交付；0.5 的目标是「图谱驱动 agent 检索优化」，B6 是价值出口。
2. **旧 3D/旧入口保留 legacy + 显式 beta**：0.5 不静默删除已发布旧 3D；新 3D 仅同签名接口 `capability=false`。
3. **增加 soft A/B，不设 P0**：≥10 题「答对率不降 + iterations 下降」作为 soft 证据项；不进 P0 阻断。
4. **G05 在 B4 后复核**：新 2D 渲染覆盖 G05 场景且有实测 ⇒ 收口 G05 的 D2b；否则保留并另排。
5. **接受 §18/I-29 修正**：§18 导出/导入改归 0.6；I-29 标「已被 2026-10-27 版本路线取代」；`version.md` 不动（人权限）。

**其余无。**

## 8. 任务板 id（与文档一致）

| 批 | 任务板 id | 建议 owner（Lead 派发时可改） |
| --- | --- | --- |
| B1 契约与只读底座 | **task-348** | arch-contract |
| B2 视图/维度/聚类 | **task-349** | graph-se-architect（SE）+ arch-contract 复核 |
| B3 取景与 VM（P0） | **task-350** | arch-contract（契约/引擎） |
| B4 2D 渲染 + 导航（P0） | **task-351** | render-perf（渲染）+ ui-designer（S3 视觉 token） |
| B5 缓存/审计/G6/G7/门禁工具 | **task-352** | metrics-baseline |
| B6 agent 只读消费 + 检索 | **task-353** | agent-arch（工具）+ metrics-baseline（GATE-RET） |

> 依赖关系（已写入任务板）：B1(task-348) → B2(task-349) → B3(task-350) → B4(task-351) → B5(task-352) → B6(task-353)；B6 `blocked_by=[task-351,task-352]`。所有任务 `plan_ref` 指向本文件；owner 暂为 lead，派发时由 Lead 指定实现 owner。

## 9. 证据索引（本文引用）

```
docs/design/multilevel-graph/DESIGN-SERIES-COMPLETE.md:28-39
docs/design/multilevel-graph/ENGINEERING-PLAN.md:929-949（I-01..I-13 + S6a 定稿）
docs/design/multilevel-graph/S6-contract-v1.md:75-79（S6-12 边界）
docs/design/multilevel-graph/S7-agent-v1.md:27-76
docs/design/multilevel-graph/S8-metrics-v1.md:64-67（DoD）、21-25（G6）
docs/design/multilevel-graph/S8-engineering-check.md:60-76（DoD 映射）、46-58（CI）
docs/design/multilevel-graph/S9-retrieval-v1.md:57-63（golden/eval/GATE-RET）
docs/design/multilevel-graph/S10-kp-v1.md:61-63（不在 0.5）
docs/conventions/version.md:11-12（版本路线）
docs/releases/0.4.11-notes.md:3,33,46（上一版已带走/未带走）
docs/todo.md §13 统计行；docs/todo/04-graph.md；docs/todo/12-build-table.md
```
