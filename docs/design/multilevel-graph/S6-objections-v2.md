# S6 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S6-RULINGS.md`（sha `93d89efa…`，R-S6-1..R-S6-6）。
> **对象**：`S6-contract-proposal-A-v2.md`（主办研究，sha **`9e71d54010517ed38a7d3fa0507a151ccd162b808845d6f046b86dcf5f8368d3`**，37,715 B）与 `S6-contract-proposal-B-v2.md`（本复核方，sha **`4e262068570de72f45f389ff7cdf241846d440bb5348e86fd7188748bcc96c02`**，21,836 B）。
> **性质**：B-v2 以 R-S6 为依据独立修订，完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S6-RULINGS/S0–S5。

---

## 0. 异议处置（含撤回）

| 编号 | 首轮异议 | 处置 | 证据/理由 |
|---|---|---|---|
| P1-1 | A `GraphNavFrame.nav_id` vs S5 `frame_id` | **成立/已修** | R-S6-1；S5 L17-19/L59；A-v2 全改 frame_id，禁止 nav_id schema 字段 |
| P1-2 | A `FRAME_SPEC` 含 frame_id/edition | **成立/已修** | R-S6-2；S4 frame_spec 无二者；A-v2 拆 `S4_FRAME_SPEC` + S5 派生 |
| P1-3 | B「VM role 应 {member,focus}」 | **WITHDRAWN (misread S3)** | S3 冻结原文 `role∈{member}`；focus/selected/hover 是 Presentation 瞬态、不进 VM；A 的 `role:"member"` 正确；**不再提** |
| P2 | history 签名/路径/统一错误/G6/0.5 | 已并入 R-S6-4/5/6 | 见矩阵 |

**B 的 P1-3 撤回声明**：首轮 `S6-objections.md` 的 P1-3 系误读 S3-1；S3 冻结 `VM_NODE.role="member"`，B-v2 采用 A 的同字段，不再作为异议。

---

## 1. R-S6 关闭矩阵

| 裁决 | A-v2 | B-v2 | 判定 |
|---|---|---|---|
| R-S6-1 frame_id 唯一 | S6-7 frame_id；nav_id 仅文档别名；失败码 `GRAPH_FRAME_ID_INVALID` | 同 | **关闭** |
| R-S6-2 FRAME_SPEC==S4 | `S4_FRAME_SPEC` 仅 S4 字段；frame_id/edition S5 派生/本地 | 同 | **关闭** |
| R-S6-3 role 撤回 | `role:"member"` | `role:"member"` | **关闭** |
| R-S6-4 history 签名 | `signature?{alg,key_id,sig}`；`.sig`/字段二选一；`GRAPH_HISTORY_SIGNATURE_INVALID`；signed=false G6 | 同 schema/位置/失败码 | **关闭** |
| R-S6-5 路径/GC/D-3 | `.memoria/cache/graph/`、`config/graph/`、`agent/audit/graph/`；GC 20/90；history 不 GC；旧分组不迁移 | 同底路径/GC/D-3/不迁移 | **关闭** |
| R-S6-6 GRAPH_*/G6/0.5 | `GRAPH_*` canonical+legacy；G6 字段/阈值；0.5 边界 | 同 | **关闭** |

**结论**：R-S6-1..6 两版**全部关闭**；无 P0/P1；剩余为 S6a 落盘细节与 B 吸收 A 的详表（P2）。

---

## 2. A-v2 / B-v2 逐项差异（S6-1..S6-12）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S6-1 单一真源/ER | 事实/配置/派生/视图/审计实体细分；DOCUMENT/KP_CONCEPT/KP_OCCURRENCE/EDGE_PROVENANCE | 同类但实体较简 | A 更细；B 已覆盖核心实体；S6a 以 A ER 为准（P2-3）。 |
| S6-2 DataSource/GraphView | 字段表+失败码 `GRAPH_*`；GraphView/C-* | 字段/枚举/失败码/只读；GraphView | 一致；A 字段表更细。 |
| S6-3 registry/history | 签名 schema/位置/失败码/链 | 同 schema/位置/失败码 | 一致；签名 `.sig` vs 字段由 S6a 定（P2-1）。 |
| S6-4 run/membership | run_id/params_hash/μ/β/label/五状态 | 同 | 一致。 |
| S6-5 VM/Visual | role member；VM 白名单；token map/capabilities | role member；VM 白名单；token map/capabilities | 一致；A 字段表更细。 |
| S6-6 Frame/presence | S4_FRAME_SPEC 严格；frame_id/edition S5；presence/rule/MANDATORY/subset | 同 | 一致。 |
| S6-7 Nav | frame_id；NAV_STACK/EVENT；T01–T30；frame_id 派生 | 同；T01–T30 引用 S5 附录、事件 21 | 一致；A 表更细；B 需 S6a 生成 S5a（P2-2）。 |
| S6-8 存储/审计/GC | cache/config/audit 路径；GC 20/90；D-3 | 同底路径；B cache 加 `<edition>` 层 | 基本一致；cache 子布局/edition 位置由 S6a 统一（P2-2）。 |
| S6-9 错误 | `GRAPH_*` canonical+legacy+i18n | 同 | 一致。 |
| S6-10 兼容/迁移 | 旧 graph-groups 不迁移/只读 fallback；旧 build cache 重建 | 同核心 | 一致；B 需补旧 build cache 处理。 |
| S6-11 G6 | 字段/阈值/sha/复跑 | 同字段/阈值 | 一致；A 更细。 |
| S6-12 0.5 边界 | 2D 先发/3D capability=false/接口清单 | 做/不做/验收；接口清单较简 | 一致；B 需吸收 A 的 S6a 接口清单（P2-3）。 |

**总判断**：两版在 R-S6 核心上已收敛；A-v2 在 ER 实体/接口清单/字段表/G6 细节上更强；B-v2 的 frame_id/FRAME_SPEC/role/签名/路径/GRAPH_* 均已对齐。**无新增 P0/P1**；以下 3 项为 S6a 落盘细节/吸收项。

---

## 3. 仍未解决 3 点（P2；冻结前可由 S6a 定）

### P2-1 history 签名落盘形态与 key 管理（R-S6-4 已允许二选一）
- **现状**：A-v2/B-v2 均写 `signature?{alg,key_id,sig}` + `.memoria/config/graph/history/`；但 **同目录 detached `.sig` 或 entry `signature` 字段**二选一未定；`ed25519`/`hmac-sha256` 的 key 管理（key_id 生成/轮换/本地信任）未定。
- **影响**：同一 entry 两套落盘形态会导致 `content_sha` 计算（是否含 signature）与签名验证不一致；`signed=false` 的 G6 标记需明确。
- **建议**：S6a 冻结：`content_sha = sha256(canonical(entry 不含 signature))`；签名放 detached `<content_sha>.sig`（推荐，history 文件保持纯内容）或 `signature` 字段（二选一）；key 以 `key_id` 引用本地信任文件；验证失败 fail-closed `GRAPH_HISTORY_SIGNATURE_INVALID`；signed=false 在 G6 `registry_signed` 标记。A/B 统一。
- **证据**：R-S6-4；A S6-3/S6-15.1；B S6-3。

### P2-2 cache 子布局与 GC 命名（R-S6-5 只冻结根路径与策略）
- **现状**：R-S6-5 冻结 `.memoria/cache/graph/`；A 用 `{level}/{view_family}/{run_id}.json`（edition 在 run_id/内部），B 用 `<edition>/<level>/<family>/<run_id>.json`（edition 一级目录）；两者都可重建，但同一 cache 查找/GC 扫描路径不同；A 旧 `.memoria/build/**` 处理，B 未提。
- **影响**：S6a/实现必须唯一 cache 路径；GC 20 run/90 天按哪个目录键计数需一致；否则同一 edition 两套缓存并存（非事实但影响可复跑）。
- **建议**：S6a 冻结唯一 cache 子布局（推荐 A 的 `{level}/{view_family}/{run_id}.json`；edition 写入 run metadata/key），GC 以 `run_id` 为键（20 run/90 天）；旧 `.memoria/build/**` 不读/可删；B 补旧 build 处理。
- **证据**：R-S6-5；A S6-8；B S6-8。

### P2-3 S6a ER/DFD/接口清单吸收 A 的完整粒度
- **现状**：A-v2 已有 ER 实体细分（DOCUMENT/KP_CONCEPT/KP_OCCURRENCE/EDGE_CANDIDATE/EDGE_PROVENANCE）、S6a 接口清单（DataSource/GraphView/DIMENSION/CLUSTER_RUN/VM/FRAME_SPEC/NAV/CACHE/AUDIT/G6）；B-v2 的实体/接口清单较简（缺 DOCUMENT/OCCURRENCE/EDGE_PROVENANCE 细分与部分接口签名）；R-S6 要求 S6a 定稿 ER/DFD/ST 与接口清单，必须吸收 A 粒度并保持 B 的 frame_id/FRAME_SPEC 约束。
- **影响**：若 S6a 只按 B 简表，ER 与现有 `.memoria` 事实实体（KP occurrence/sidecar/manifest）映射不完整，DFD 写路径/只读边界不闭合；若只按 A，需确保 A-v2 的 `S4_FRAME_SPEC`/role/签名/路径已按 v2 修正（已修）。
- **建议**：S6a 以 A-v2 的 ER/字段表/接口清单为主干，吸收 B-v2 的 `S4_FRAME_SPEC` 拆分、`role:"member"`、frame_id 派生、`GRAPH_*`/G6/路径；输出与 S0–S5 逐条映射的 ER/DFD/ST + 接口清单 + mermaid `PARSE_OK`；0.5 边界按 R-S6-6。
- **证据**：R-S6-6；A S6-1/S6-12/S6a 接口清单；B S6-1/S6-12。

---

## 4. 点名审查结论（v2）

1. **单一真源/并行事实源**：A/B **PASS**（事实 `.md`+sidecar/manifest 只读；DataSource 投影；派生缓存可重建；D-3 不写 sidecar/新段）。
2. **schema 字段/类型/枚举/默认/失败码**：A/B **PASS**；A 字段表更全；无 role 冲突（已撤回）。
3. **registry_history 不可变/可复算/签名**：A/B **PASS**（content-addressed/history 链/`signature?`/失败码）；签名落盘形态 P2-1。
4. **run/membership 身份/stale/curation/五状态**：A/B **PASS**（run_id/params_hash/cluster_key/五状态/curation；A 含 μ/β/label）。
5. **S3 白名单+ADDENDUM-1/data_edge_ids 禁读**：A/B **PASS**（role member；node/edge presence；Renderer 禁读 data_edge_ids）。
6. **S4 候选/MANDATORY/budget/subset 失败码**：A/B **PASS**（S4_FRAME_SPEC 严格；presence/rule_id/MANDATORY/subset；失败码）。
7. **S5 T01–T30/表↔图/frame_id/持久化**：A/B **PASS**（frame_id 派生、T30/事件、S5a 生成、持久化白名单）。
8. **存储/审计/GC/D-3**：A/B **PASS**（cache/config/audit 路径；GC 20/90；history 不 GC；旧分组不迁移）；cache 子布局 P2-2。
9. **失败码统一/i18n**：A/B **PASS**（`GRAPH_*` canonical+legacy；未知 `GRAPH_INTERNAL`；i18n 归 UI）。
10. **兼容/迁移/回滚**：A/B **PASS**（无破坏迁移；旧 graph-groups 忽略；删缓存回滚）。
11. **G6 可复跑**：A/B **PASS**（字段/阈值/sha/复跑；determinism 100%、subset true、closure/behind 0）。
12. **0.5 边界**：A/B **PASS**（2D 先发；3D capability=false；不做 S7–S10/agent 写/自动 semantic/跨库/时间维/编辑器/破坏迁移）；接口清单 P2-3。

---

## 5. 结论

- **S6 两版无 P0/P1**；R-S6-1..6 全部关闭；B 的 role 异议已标 **WITHDRAWN (misread S3)**，不再提。
- A-v2 在 ER/字段表/接口清单/G6 细节上更强；B-v2 的 frame_id/FRAME_SPEC/role/签名/路径/`GRAPH_*` 与裁决一致。剩余 P2-1（签名落盘/key）、P2-2（cache 子布局/GC 命名）、P2-3（S6a 吸收 A 完整粒度）由 S6a/SE 定稿。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：R-S6 `S6-RULINGS.md:18-43`；S5 `S5-nav-v1.md:16-19/59/117-155`；S4 `S4-render-v1.md`（frame_spec 字段）；S3-1 role；A-v2 S6-1/S6-3/S6-5/S6-6/S6-7/S6-8/S6-12；B-v2 同项。
