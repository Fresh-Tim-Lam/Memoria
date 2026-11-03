# S6 提案 A · 证据与机检清单

> 配套：`S6-contract-proposal-A.md`｜票：task-320｜日期：2026-11-03
> 用途：另一人可按本文件复核 S6 每条 schema/断言（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S6 复核方草稿；不引用其结论。
> 纪律：未改产品代码/契约/schema/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S6 用途 |
|---|---|---|
| A | 冻结条款/工程/代码事实 | 单一真源、schema 字段、run 公式、VM/presence、nav T01–T30 |
| B | 单源实测产物 | 引用 S2 probe 的 E_sem=0 事实（no_semantic 合法） |
| C | 单源推理 | 少量设计取舍（并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | 存储路径/GC 数值/错误码名/0.5 范围 |

**统计**：A 级锚点见 §1–§12；**本项目假设 10 条**（§14）；B 引用 S2 probe 1 份。

---

## 1. S6-1 契约范围/单一真源

| 主张 | 锚 | 等级 |
|---|---|---|
| D-3 不写产品 sidecar/新段；semantic overlay 走 v0.3 | `S0-terms-v1.md:100-107`（D-3） | A |
| DataSource 读取事实（正文/sidecar/manifest）；只读 | `collector.py:46-99`（collect_md_files/load_sidecar） | A |
| 派生缓存可重建；事实源 vs 缓存 | `ENGINEERING-PLAN.md:201-222`（实体表）、`:562`（事实/缓存） | A（工程） |
| 实体归属表 | 本提案 §1 + `ENGINEERING-PLAN.md:201-222` | A+本项目假设 |

---

## 2. S6-2 DataSource/GraphView/C-*

| 主张 | 锚 | 等级 |
|---|---|---|
| `(level,view_family)` partition；跨族多归属 | `S0-terms-v1.md:28-33,63-68`（S0-2/S0-7） | A |
| `E_relation_min`/kind 枚举 | `S0-terms-v1.md:35-41`（S0-3）；S0-9 | A |
| R-3 `data_edge_ids`/expand 子集 | `S0-terms-v1.md:56-61,102` | A |
| C-1..C-6 冻结映射 | `ENGINEERING-PLAN.md:282-291`；S0/S1/S3 对应条款 | A |
| DataSource 节点/边现状 | `collector.py:57-95`；`edge_derivation.py:787-793` | A |
| 字段/接口名 | 本提案 §2 | 本项目假设 |

---

## 3. S6-3 registry/history

| 主张 | 锚 | 等级 |
|---|---|---|
| DIMENSION 全字段/类型/枚举/默认/失败码 | `S1-dimensions-v1.md:22-51`（S1-2 schema） | A |
| history 不可变 append-only、content_sha、链闭合 | `S1-dimensions-v1.md:48`（R-S1-9） | A |
| 只增不删/S0_REOPEN | `S1-dimensions-v1.md:69-72`（S1-6） | A |
| history 存储路径/签名字段 | 本提案 §3 | 本项目假设 |

---

## 4. S6-4 run/membership/身份

| 主张 | 锚 | 等级 |
|---|---|---|
| run 公式/params 字段集/五状态 | `S2-clustering-v1.md:31-50`（S2-4/S2-7） | A |
| cluster_key/run-scoped id/D-2 | `S2-clustering-v1.md:47-51`；`S0-terms-v1.md:104` | A |
| 多归属/role=member/不写 sidecar | `S2-clustering-v1.md:42-45,68-71` | A |
| 现有 groups 无版本/单值（反例） | `graph-groups.js:83-134,123-126` | A |
| 参数默认值/S8 范围 | 本提案 §4 | 本项目假设 |

---

## 5. S6-5 Visual/VM

| 主张 | 锚 | 等级 |
|---|---|---|
| VM 白名单 + 节点 presence/rule_id | `S3-visual-v1.md:71-75`；`S3-ADDENDUM-1.md:16-26` | A |
| 只画 shown；data_edge_ids 审计禁读 | `S3-visual-v1.md:36-39,72-75`（R-S3-9） | A |
| 2D/3D 同签名/capabilities | `S3-visual-v1.md:41-44,66-69` | A |
| token map 字段名 | 本提案 §5 | 本项目假设 |

---

## 6. S6-6 Frame/presence/rule

| 主张 | 锚 | 等级 |
|---|---|---|
| presence 三值/11 类 rule_id/unknown 4 类 | `S4-render-v1.md:41-44`；S0-6 | A |
| MANDATORY/subset 构造证明 | `S4-render-v1.md:36-39,56-60` | A |
| frame_id/预算/失败码 | S5 R-S5-9；S4-5/S4-9 | A |
| 错误码命名 | 本提案 §6/§9 | 本项目假设 |

---

## 7. S6-7 Nav schema

| 主张 | 锚 | 等级 |
|---|---|---|
| GraphNavFrame 字段/只在 Presentation | `S5-nav-v1.md:16-19`（S5-1） | A |
| 9 主状态/正交变量/表↔图 | `S5-nav-v1.md:21-24`（S5-2/R-S5-10） | A |
| T01–T30 唯一真源/148 边 | `S5-nav-v1.md:117-155`（附录 A） | A |
| frame_id 派生/edition 本地 | `S5-nav-v1.md:17-18`（R-S5-9） | A |
| 持久化白名单 | `S5-nav-v1.md:73-75`（S5-12） | A |
| NAV_EVENT/存储字段 | 本提案 §7 | 本项目假设 |

---

## 8. S6-8 存储/审计/GC/版本

| 主张 | 锚 | 等级 |
|---|---|---|
| 缓存派生可重建；D-3 | `S0-terms-v1.md:100-107`；`ENGINEERING-PLAN.md:562` | A |
| 现有 build 缓存路径 | `ENGINEERING-PLAN.md:591-593`；`graph-engine.js:167-216` | A（工程） |
| 审计 append-only | `ENGINEERING-PLAN.md:221-222`（AUDIT_EVENT） | A |
| 路径/GC 数值 | 本提案 §8 | 本项目假设 |

---

## 9. S6-9 错误码

| 主张 | 锚 | 等级 |
|---|---|---|
| S1–S5 已有失败码 | S1-2 表；S2 五状态；S3 VM/预算；S4 presence；S5 nav | A |
| 统一命名空间/映射 | 本提案 §9 | 本项目假设（名字/策略） |
| i18n 归属 | S3-10 文案；本提案 §9 | A+本项目假设 |

---

## 10. S6-10 兼容/迁移

| 主张 | 锚 | 等级 |
|---|---|---|
| 旧 graph-groups 无版本/前端现算 | `graph-groups.js:83-134`；S2-11 | A |
| 不写事实/无破坏性迁移 | S0-10/D-3；S2-11 | A |
| 旧 payload 读取现状 | `graph-engine.js:167-216` | A |
| fallback/feature flag/回滚 | 本提案 §10 | 本项目假设 |

---

## 11. S6-11 G6

| 主张 | 锚 | 等级 |
|---|---|---|
| G6 指标需求（确定性/subset/rule 直方图） | S3-11/S4-12/S5-12 | A |
| 快照内容/命令/阈值 | 本提案 §11 | 本项目假设（字段/命令） |
| 规模/复跑要求 | U-32；`ENGINEERING-PLAN.md:660` | A |

---

## 12. S6-12 0.5 边界

| 主张 | 锚 | 等级 |
|---|---|---|
| S0-11 范围外清单 | `S0-terms-v1.md:87-90` | A |
| 2D/3D 同签名（接口） | S3-6；U-33 | A |
| nav 基础/事务化 | S5-1..S5-12 | A |
| 0.5 子集/3D 延后/验收阈值 | 本提案 §12 | 本项目假设 |

---

## 13. Schema 完整性检查

| schema | 字段/类型/枚举/默认 | 失败码 | 位置 |
|---|---|---|---|
| DataSource | ✅ | ✅（GRAPH_SCHEMA/INPUT/EDITION/NODE/EDGE） | §2 |
| GraphView | ✅ | ✅（SCOPE/PARTITION） | §2 |
| DIMENSION/HISTORY | ✅ | ✅（DIM_*） | §3 |
| CLUSTER_RUN/CLUSTER/MEMBERSHIP | ✅ | ✅（RUN/PARAMS/STATUS/PARENT） | §4 |
| ViewModel/VM_NODE/VM_EDGE | ✅ | ✅（VM_*） | §5 |
| FRAME_SPEC/PRESENCE/ADMISSION | ✅ | ✅（FRAME/HOP/PRESENCE/BUDGET/SUBSET） | §6 |
| GraphNavFrame/STACK/EVENT | ✅ | ✅（NAV_*） | §7 |
| CACHE_MANIFEST/AUDIT_EVENT | ✅ | ✅（CACHE/EDITION） | §8 |
| G6_SNAPSHOT | ✅ | ✅（SCHEMA/EDITION） | §11 |

> 注：表中失败码为 S6-9 统一命名空间的代表码；每个字段行已给具体码（见提案 §2–§7）。

---

## 14. 本项目假设清单（10 条）

1. 存储根：`.memoria/build/graph/`（派生）、`.memoria/config/graph/`（registry/history）、`.memoria/audit/graph/`（审计）、`artifacts/graph/g6/`（G6）。
2. GC：保留 adopted/current + 最近 20 run + 90 天；只删派生，不删事实/审计。
3. 错误码统一为 `GRAPH_*`，并为 S2–S5 旧码保留映射（不破坏冻结文档引用）。
4. registry history 采用 `content_sha` 作为 id、`previous_sha` 链；签名字段暂按 `payload_sha`（S6a 可加签）。
5. cache key = `sha256(contract_version+edition_sha+run_id/frame_id)`。
6. 0.5 只实现 2D 渲染；3D adapter 同签名但 `capability=false`，实现延后。
7. 0.5 不做 3D/agent 写/自动 semantic/跨库/时间维/图编辑器/破坏性迁移。
8. G6 命令路径 `scripts/verify/g6_snapshot.py`（S6a/SE 定）；阈值 determinism=100%、subset=true、closure/behind=0。
9. 旧 payload 只读 fallback 可选，默认不启用（由 feature flag 控制）。
10. NAV_EVENT 的 event_id 可用 `sha256(canonical(seq,type,payload,frame_id))`（S6a 定）。

---

## 15. 现状证据（只读代码）

| 主张 | 锚 |
|---|---|
| DataSource 返回 `{status,nodes,edges}` | `collector.py:46-99` |
| 边 canonical id | `edge_derivation.py:787-793` |
| 旧 groups 前端现算/无版本 | `graph-groups.js:83-134` |
| 旧 payload 单入口 | `graph-engine.js:167-216` |
| KP 点击统一 jumpToTarget（无 kind 分流） | `app.js:1661-1677` |
| 文件导航栈（非图谱栈） | `nav-stack.js:23-36` |
| 实体/缓存/审计/状态图草案 | `ENGINEERING-PLAN.md:150-222,562,583,660,980-1048` |

---

## 16. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) S6 12 议项 + schema 关键词
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S6-contract-proposal-A.md').read_text(encoding='utf-8'); print('missing S6:',[f'S6-{i}' for i in range(1,13) if f'S6-{i}' not in t]); print('GRAPH_ codes', t.count('GRAPH_'))"
# 2) 现状锚
python -c "from pathlib import Path; t=Path('src/memoria/graph/collector.py').read_text(encoding='utf-8'); print('collect_graph_data', 'def collect_graph_data' in t); t2=Path('src/memoria/ui/static/app/js/graph-groups.js').read_text(encoding='utf-8'); print('computeGraphGroups', 'computeGraphGroups' in t2)"
# 3) S5 T01-T30 真源存在
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S5-nav-v1.md').read_text(encoding='utf-8'); print('T01', 'T01' in t, 'T30', 'T30' in t, '148', '148' in t)"
```

**实测结果（2026-11-03）**：
- S6-1..S6-12 全部含 定义/规则·机检·反例·边界·U 映射·建议裁决·证据等级（缺失 0）。
- `GRAPH_` 码命名空间已在提案中出现；S5 v1 T01–T30/148 边真源存在。
- 现状锚 OK：`collect_graph_data`、`computeGraphGroups` 存在。

---

## 17. 已知限制

1. 本场为契约提案，未实现/未运行 schema validator；字段名/错误码需 S6a/SE 落成 JSON Schema 后复验。
2. 存储路径/GC 数值/0.5 范围/3D 延后为建议，需 Lead 裁决。
3. 旧 `.memoria` sidecar/manifest 具体字段未逐项展开（只读输入）；S6a 需与现有 schema 对照。
4. 错误码 `GRAPH_*` 与冻结文档旧码（`S4_BUDGET_INVALID` 等）的映射需在实现层保持双向可追溯。
5. G6 命令/阈值需 S6a 固定；本文件只给 schema/原则。
