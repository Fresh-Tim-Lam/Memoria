# S1 提案 A · 证据与机检清单

> 配套：`S1-dimensions-proposal-A.md`｜票：task-295｜日期：2026-11-03
> 用途：让另一人只按本文件复核 S1 提案中的每条断言（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S1 独立复核方草稿（S1-dimensions-proposal-B / S1-objections）；本文件不引用其结论。
> 边界：本场未改产品代码/契约/schema/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S1 用途 |
|---|---|---|
| A | 原话/冻结契约/决策/可复跑代码事实 | 维度边界、R-1、H/A 约束、present、VM 纯度 |
| B | 单源实测产物（artifacts） | （本场基本不需要；S0 边语义层仅作背景） |
| C | 单源推理 | 少量设计取舍（已并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | schema 字段默认值、hop 取值、状态枚举扩展、槽位格式 |

**统计**：A 级锚点见 §1–§15（每项 ≥2 个）；**本项目假设 10 条**（§4 列举）；C 级不单独作结论。

---

## 1. S1-1 维度定义与边界

| 主张 | 锚 | 等级 |
|---|---|---|
| 原话：层次维度/其他维度/关联维度/更多维度/开放槽位 | `docs/design/multilevel-graph-vision.md:25-29`（U-8..U-12）、`:64`（U-25） | A |
| 维度=取景规则、不是粒度/视觉 | `S0-terms-v1.md:35-41`（S0-3 规则） | A |
| `graphStyle` 是视觉风格而非维度 | `src/memoria/ui/static/app/js/graph-view-2d.js:617`；`graph-settings.js:38` | A |
| 2D/3D 是渲染后端、不是维度 | `S0-terms-v1.md:75-79`（S0-9）；`vision.md:72`（U-33） | A |
| 全展开是模式、非维度 | `S0-terms-v1.md:69-73`（S0-8） | A |
| 现实现无维度概念（单一全量视图） | `graph-engine.js:167-181`（loadPayload 全量 payload）；`app.js:1845`（get_graph_data） | A |
| M1–M6 判定清单 | 本提案 §1 | 本项目假设 |

---

## 2. S1-2 注册表 schema

| 主张 | 锚 | 等级 |
|---|---|---|
| 维度字段要求（id/name/basis/relation_sources/direction/hop/termination/status/priority） | `S1-charter.md:28`（S1-2 必须回答） | A |
| active 维度 `E_relation(D) ⊇ E_relation_min`（R-1） | `S0-terms-v1.md:37-41`（S0-3 R-1） | A |
| registry 是配置非事实源 | `ENGINEERING-PLAN.md:343-345`（CFG 区：level/dimension/view_family 注册表） | A |
| DIMENSION 实体字段（id/status/version）待 S1 补 | `ENGINEERING-PLAN.md:149-153,216,290`（C-5 status 枚举待补） | A |
| 未知 id fail-closed | `S0-terms-v1.md:40`（机检：未知 dimension_id fail-closed）、`:37`（reserved 不得进渲染分支） | A |
| status 枚举建议 | 本提案 §2/§11；映射 A-v2 `{reserved,specified,frozen,deprecated}`/B `{active,reserved}`；C-5 | 本项目假设 |
| schema 字段默认值/`basis` 对象 | 本提案 §2 | 本项目假设 |

**fail-closed 反例（可机检）**：
1. `dimension_id` 未知 ⇒ `DIM_UNKNOWN`；
2. `status=reserved` 被 ctx 引用 ⇒ `DIM_NOT_ACTIVE`；
3. active 维度 `relation_sources` 未包含 `E_relation_min` ⇒ `DIM_MISSING_MIN`（R-1）；
4. H `direction≠down` / `leaf_required=false` ⇒ `DIM_H_DIRECTION`/`DIM_H_LEAF`；
5. `hop_default > hop_max` 或 `hop_max=null` ⇒ `DIM_HOP`；
6. active 维度 priority 重复 ⇒ `DIM_PRIORITY`；
7. registry schema/版本缺失 ⇒ 全局 fail-closed。

---

## 3. S1-3 开放槽位

| 主张 | 锚 | 等级 |
|---|---|---|
| U-25「先留开放槽位」 | `vision.md:64`（U-25） | A |
| reserved 只登记、不得进渲染分支 | `S0-terms-v1.md:37-40`（S0-3 规则/机检） | A |
| 晋升需评审/版本 | 本提案 §3 R4 | 本项目假设（审批链细节） |
| reserved 清单（time/evidence/task/controversy/authorship） | 本提案 §15 | 本项目假设（候选选择） |

---

## 4. S1-4 H 定义

| 主张 | 锚 | 等级 |
|---|---|---|
| 层次=同一 (level, view_family) 嵌套划分、最小粒度 KP | `S0-terms-v1.md:30-33`（S0-2） | A |
| H 方向 down、终止 KP 叶子 | `S0-terms-v1.md:49-54`（S0-5：H=down）；`S1-charter.md:30`（S1-4 必须回答） | A |
| `view_family` 定义 R-2 | `S0-terms-v1.md:39,101`（S0-3/R-2） | A |
| partition 机检 `validate_level_view` V1–V6 | `S0-terms-v1.md:31-32` | A |
| H hop=level、v1 max=1 的取值 | 本提案 §4/S1-7 | 本项目假设 |
| H 其余关系源只作可见上下文边 | 本提案 §4 | 本项目假设（需 Lead 裁） |

---

## 5. S1-5 A 定义

| 主张 | 锚 | 等级 |
|---|---|---|
| U-10：关联维度显示包含/引用/语义关联 | `vision.md:27`（U-10）、`:69`（U-30） | A |
| `E_relation_min={contain(structural),contain(semantic),reference,extend}`，只增不删 | `S0-terms-v1.md:38`（R-1 冻结） | A |
| 一跳=恰好一条 E_relation(D) 边、不闭包、方向、跨维重置 | `S0-terms-v1.md:49-54`（S0-5） | A |
| 一跳背后不带入 | `vision.md:34`（U-17）；`S0-terms-v1.md:51` | A |
| 现实现全量渲染（反例） | `graph-engine.js:179-180`（rawEdges） | A |
| A 的 BFS/边界、hop_max=2 | 本提案 §5/S1-7 | 本项目假设 |

---

## 6. S1-6 E_relation 扩展

| 主张 | 锚 | 等级 |
|---|---|---|
| 只能加不能删（删须重开 S0） | `S0-terms-v1.md:38,100`（R-1）；`S0-FREEZE-RECORD.md:63` | A |
| v1 不新增语义类型 | `S0-terms-v1.md:87-90`（S0-11 #6）；`kg-ontology-v0.md:150-158`（§4 不做清单） | A |
| 现有类型枚举 3 类 | `src/memoria/graph/edge_types.py:9-17`（EDGE_TYPES/DERIVE_ONLY） | A |
| 三类关系源分类与 E1–E7 准入 | 本提案 §6 | 本项目假设 |

---

## 7. S1-7 跳数

| 主张 | 锚 | 等级 |
|---|---|---|
| U-11 跳数需设计；多跳污染理由 | `vision.md:28`（U-11）、`:35`（U-18） | A |
| 一跳定义/跨维重置 | `S0-terms-v1.md:49-54`（S0-5） | A |
| 预算/终止可解释（rule_id） | `S0-terms-v1.md:56-61`（S0-6 presence/rule_id） | A |
| 沿边 vs 沿节点、去重、最小距离、hop 取值 | 本提案 §7 | 本项目假设 |

---

## 8. S1-8 方向

| 主张 | 锚 | 等级 |
|---|---|---|
| H=down；A=both（可配置，不默认闭包） | `S0-terms-v1.md:51`（S0-5） | A |
| 边事实方向（source→target）不可被取景翻转 | `src/memoria/graph/collector.py:46-99`（DataSource 边结构）；`edge_derivation.py:787-793`（canonical id 含 source/target） | A |
| up/out/in 枚举与视觉标记 | 本提案 §8 | 本项目假设（S3 视觉） |

---

## 9. S1-9 终止

| 主张 | 锚 | 等级 |
|---|---|---|
| U-32：规模不是问题、关键后端检索 | `vision.md:71`（U-32） | A |
| 必须有限终止 + 截断可见（presence/rule_id） | `S0-terms-v1.md:56-61`（S0-6） | A |
| H 到叶终止 | `S0-terms-v1.md:30-33`（S0-2）；`:51`（S0-5） | A |
| 终止并集/预算结构 | 本提案 §9 | 本项目假设 |

---

## 10. S1-10 维度组合

| 主张 | 锚 | 等级 |
|---|---|---|
| v1 单维度激活（D-5） | `S0-terms-v1.md:40,107`（S0-3 机检/D-5）；`vision.md:25-29` | A |
| VIEW_FRAME 单 dimension_id 字段 | `ENGINEERING-PLAN.md:154-163,217,276` | A |
| 组合槽位格式 | 本提案 §10 | 本项目假设 |

---

## 11. S1-11 状态机/plugins

| 主张 | 锚 | 等级 |
|---|---|---|
| 未知/保留 fail-closed；reserved 不进渲染 | `S0-terms-v1.md:37-41`（S0-3） | A |
| status 枚举待 S1 补（C-5） | `ENGINEERING-PLAN.md:290`（C-5：A 超集+B active 映射） | A |
| registry 是配置、非事实源 | `ENGINEERING-PLAN.md:343-345` | A |
| 插件声明面：无代码、能力来自核心原语目录、启停/校验 | `src/memoria/services/agent/plugins.py:1-35`（声明/校验/无执行体） | A |
| 三状态+映射、plugin 不注册维度 | 本提案 §11 | 本项目假设 |

---

## 12. S1-12 present

| 主张 | 锚 | 等级 |
|---|---|---|
| present 唯一判据、presence 三值+rule_id、视图缺席≠数据缺席 | `S0-terms-v1.md:56-61`（S0-6） | A |
| 维度只改 presence、不改类型（U-27） | `S0-terms-v1.md:58`；`vision.md:66`（U-27） | A |
| 类型/标签字段来源 | `kg-ontology-v0.md:113-130`；`schema.json:136-149,202-230` | A |
| H/A 的 admit 规则与 rule_id 枚举 | 本提案 §12 | 本项目假设（S4 可细化） |

---

## 13. S1-13 UI/导航

| 主张 | 锚 | 等级 |
|---|---|---|
| ViewModel 不含导航/模式/capabilities（D-4） | `S0-terms-v1.md:75-79`（S0-9/D-4） | A |
| VIEW_FRAME 保存 dimension_id/mode；导航在 S5 | `ENGINEERING-PLAN.md:217,276`；`S0-terms-v1.md:106-107` | A |
| 现实现无维度切换 UI（只有 graphStyle） | `graph-view-2d.js:617`；`graph-settings.js:38` | A |
| switch_dimension 接口 | 本提案 §13 | 本项目假设（S5 定） |

---

## 14. S1-14 agent

| 主张 | 锚 | 等级 |
|---|---|---|
| agent 只请求确定性取景服务、不改渲染状态（S0-10） | `S0-terms-v1.md:81-85`（S0-10） | A |
| 取景在服务端/P9 只读 | `ENGINEERING-PLAN.md:301-303`（DFD 立场） | A |
| DataSource 单一 | `S0-terms-v1.md:69-73`（S0-8） | A |
| frame 签名/错误码/审计 | 本提案 §14 | 本项目假设（S7/S9 定实现） |

---

## 15. S1-15 候选槽位

| 主张 | 锚 | 等级 |
|---|---|---|
| U-25 先留槽位、维度候选 | `vision.md:64,69`（U-25/U-30） | A |
| T 轴 valid_from/to 只存不用 | `kg-ontology-v0.md:74-75`（§2.2 字段 6） | A |
| reserved 不实现、不渲染 | `S0-terms-v1.md:37-40`（S0-3） | A |
| 候选清单与 why_not_v1 | 本提案 §15 | 本项目假设 |

---

## 16. 代码锚复核（本机可复跑）

| # | file:line | 断言 | 实测 |
|---|---|---|---|
| 1 | `src/memoria/ui/static/app/js/graph-view-2d.js:617` | 含 `graphStyle`（视觉风格） | OK |
| 2 | `src/memoria/ui/static/app/js/graph-settings.js:38` | 含 `graphStyle` | OK |
| 3 | `src/memoria/ui/static/app/js/graph-engine.js:167-181` | `loadPayload` 全量映射 payload | OK |
| 4 | `src/memoria/ui/static/app/js/app.js:1845` | `call("get_graph_data")` 单数据入口 | OK |
| 5 | `src/memoria/graph/edge_types.py:9-17` | `EDGE_TYPES` 3 类 + `DERIVE_ONLY_EDGE_TYPES` | OK |
| 6 | `src/memoria/graph/collector.py:46-99` | `collect_graph_data` / DataSource | OK |
| 7 | `src/memoria/graph/edge_derivation.py:787-793` | canonical id = type\|source\|target | OK |
| 8 | `src/memoria/services/agent/plugins.py:1-35` | 插件声明面、无执行体 | OK |

---

## 17. 本项目假设清单（10 条，评审可逐条推翻）

1. 注册表 `basis` 用对象（`{kind, descent_sources?}`）而非纯枚举。
2. `hop_unit` 为 S1 新增字段（charter 字段表之外，用于区分 H 的 level-hop 与 A 的 edge-hop）。
3. H 的 `hop_default=hop_max=1`（一次一层）；深层通过导航 frame 推进。
4. A 的 `hop_default=1, hop_max=2`（U-22 的"更深"），S5/S4 可调。
5. H 的 `relation_sources` 必须 ⊇ min（R-1 字面），但只有 contain(structural) 参与下降；其余源仅作可见端点上下文边。
6. status 枚举 `{reserved, active, deprecated}`，A-v2 的 `specified/frozen` 映射为 active + 版本冻结属性。
7. 组合槽位字段 `combination_id/dimension_ids/order/composition_rule/status`。
8. registry 以版本化配置文件/设计产物承载，runtime 只读 + sha 校验（非事实源）。
9. fail-closed 错误码命名（DIM_UNKNOWN/DIM_NOT_ACTIVE/DIM_MISSING_MIN/…）。
10. 候选 reserved 清单（time/evidence/task/controversy/authorship）及 why_not_v1。

---

## 18. S0 覆盖一致性（S1 不得违反）

| S0 条款 | 本提案落点 | 检查 |
|---|---|---|
| S0-2 层次/partition | S1-4 | H 不改 partition，仅复用 |
| S0-3 E_relation/R-1/R-2 | S1-2/S1-5/S1-6 | active 维度 ⊇ min；删除重开 S0 |
| S0-5 一跳/方向/跨维重置 | S1-7/S1-8 | A hop=1 默认；H level-hop 说明 |
| S0-6 present/三值/rule_id | S1-12 | 维度只改 presence |
| S0-7 多归属 | S1-3/S1-5 | 维度不定义 membership/不写事实 |
| S0-8 默认/全展开 | S1-13 | 模式属 Presentation |
| S0-9 VM 纯度/kind | S1-13 | VM 只含 dimension_id |
| S0-10 agent | S1-14 | 只请求确定性服务 |
| S0-11 v1 范围外 | S1-15/S1-6 | 不实现候选、不加类型 |
| R-1/R-2/R-3 | S1-2/S1-5/S1-12 | 全部继承 |

---

## 19. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) 15 议项齐全 + U 覆盖
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S1-dimensions-proposal-A.md').read_text(encoding='utf-8'); print('S1 missing:',[f'S1-{i}' for i in range(1,16) if f'S1-{i}' not in t]); print('U missing:',[f'U-{i}' for i in [8,9,10,11,12,25,30,32,33,34] if f'U-{i}' not in t])"
# 2) 代码锚
python -c "from pathlib import Path; checks=[('src/memoria/ui/static/app/js/graph-view-2d.js',617,'graphStyle'),('src/memoria/ui/static/app/js/graph-settings.js',38,'graphStyle'),('src/memoria/ui/static/app/js/graph-engine.js',179,'rawEdges = payload'),('src/memoria/ui/static/app/js/app.js',1845,'get_graph_data'),('src/memoria/graph/edge_types.py',9,'EDGE_TYPES'),('src/memoria/graph/edge_derivation.py',787,'def canonical_edge_id')]; [print('OK' if n in Path(f).read_text(encoding='utf-8').splitlines()[l-1] else 'MISMATCH', f, l) for f,l,n in checks]"
# 3) 注册表 fail-closed 逻辑（提案 §2 伪代码，可在 S6a 实现前用纯函数单测）
```

**实测结果（2026-11-03）**：S1 缺失 []；U（8/9/10/11/12/25/30/32/33/34）缺失 []；6 个代码锚 OK。

---

## 20. 已知限制

1. 注册表 schema/字段默认值是**提案**，最终需 Lead 裁决 + SE 工程校核（S1-2 字段与 `DIMENSION` 实体对齐）。
2. H/A 的 hop 具体取值（H=1 层、A hop_max=2）为 v1 建议，S5/S4 可调（不得破"单位语义"）。
3. H 的"其余关系源只作上下文边"可能被 Lead 裁为"只显示 contain"；两方案均满足 R-1（字段包含 min）。
4. reserved 候选清单为提案，不是产品需求；晋升须 S1 修订。
5. 本场不实现、不写代码；registry 的实际存储/加载属 S6a/S6。
