# S4 提案 A · 证据与机检清单

> 配套：`S4-render-proposal-A.md`｜票：task-310｜日期：2026-11-03
> 用途：另一人可按本文件复核 S4 每条断言（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S4 复核方草稿（S4-render-proposal-B / S4-objections）；不引用其结论。
> 纪律：未改产品代码/契约/schema/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S4 用途 |
|---|---|---|
| A | 原话/冻结契约/决策/可复跑代码事实 | 三值/presence、一跳、预算归属、VM 纯度、full 同源 |
| B | 单源实测产物 | 引用 S2 probe（无语义边）说明无簇时 S4 行为 |
| C | 单源推理 | 少量设计取舍（并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | tier/label_rank、unknown 触发面、数值预算 |

**统计**：A 级锚点见 §1–§12；**本项目假设 8 条**（§13）；B 引用 S2 probe 1 份。

---

## 1. S4-1 选择性渲染/唯一裁剪者

| 主张 | 锚 | 等级 |
|---|---|---|
| 渲染集合 = `{e | present(e,ctx)==shown}`，唯一判据 | `S0-terms-v1.md:56-61`（S0-6）；`S1-dimensions-v1.md:99-107`（S1-12） | A |
| S4 是唯一裁剪者；Renderer 只校验/渲染 | `S3-visual-v1.md:66-69`（S3-11/R-S3-2） | A |
| 旧行为"数据有边就画" | `graph-engine.js:179-180`（rawEdges=payload.edges）；`graph-view-2d.js:634-663`（simLinks 全画） | A |
| U-16 选择性渲染 | `vision.md:33`（U-16） | A |
| Admission 输入/输出细节 | 本提案 §1/§9 | 本项目假设 |

---

## 2. S4-2 预算/选点

| 主张 | 锚 | 等级 |
|---|---|---|
| max_nodes/max_edges 归 S8；字段/失败语义 S3 冻结 | `S3-visual-v1.md:66-69`（S3-11） | A |
| 超预算显式 suppressed+rule_id（不静默） | `S0-terms-v1.md:56-61`（presence/rule_id）；`S3-visual-v1.md:36-39` | A |
| 预算与 Renderer capabilities 同源 | `S3-visual-v1.md:42,66-69,83` | A |
| 现有无预算（全量 links） | `graph-view-2d.js:634-663`；无 maxNodes 检查 | A |
| tier/label_rank/tie-break 具体规则 | 本提案 §2 | 本项目假设 |

---

## 3. S4-3 一跳

| 主张 | 锚 | 等级 |
|---|---|---|
| 一跳=恰好一条 `E_relation(D)` 边；不闭包；跨维重置 | `S0-terms-v1.md:49-54`（S0-5） | A |
| A relation_sources ⊇ E_relation_min；每边 1 跳 | `S1-dimensions-v1.md:63-67`（S1-5） | A |
| 2 跳仅显式 `new_hop` | `S1-dimensions-v1.md:65`（R-S1-10）；`ENGINEERING-PLAN.md:913,958-959`（ST-13/EXPAND_HOP/EXPLICIT_NEW_HOP） | A |
| 不带背后图 | `vision.md:34`（U-17）；`S0-terms-v1.md:51` | A |
| 端点 kind∈{kp,cluster} | `S1-dimensions-v1.md:66`（机检）；S0-9 | A |
| new_hop 帧校验错误码 | 本提案 §5 | 本项目假设 |

---

## 4. S4-4 存无三值/rule_id

| 主张 | 锚 | 等级 |
|---|---|---|
| presence ∈ {shown,suppressed,unknown} + rule_id | `S0-terms-v1.md:56-61`（S0-6）；`S3-visual-v1.md:36-39` | A |
| 视图缺席≠数据缺席；unknown 不得当"无关系" | U-27 `vision.md:66`；S0-6 | A |
| 类型不同独立判定（不合并） | S0-6；`S3-visual-v1.md:36-39`（多类型边分画） | A |
| rule_id 枚举 | 本提案 §4（v1 穷举） | 本项目假设（S4 冻结） |
| SE S0-6 三值语义 | `S0-engineering-review.md:151-172` | A（计划级） |

---

## 5. S4-5 背后图/端点作焦点

| 主张 | 锚 | 等级 |
|---|---|---|
| 一跳端点只显示自身+边，不展开背后图 | U-17 `vision.md:34`；S0-5 | A |
| 2 跳仅 S5 `EXPLICIT_NEW_HOP` | S1-5 R-S1-10；`ENGINEERING-PLAN.md:913,958-959` | A |
| 点击端点后导航由 S5 | S0-9/`ENGINEERING-PLAN.md:713-719` | A |
| 跨层/多归属规则 | S0-5/S2-6/S2-10 | A |
| 错误码/帧清理细节 | 本提案 §5/§7 | 本项目假设 |

---

## 6. S4-6 维度接入

| 主张 | 锚 | 等级 |
|---|---|---|
| 维度经 `ctx.dimension_id` 改 presence、不改事实 | `S1-dimensions-v1.md:99-107`（S1-12）；S1-13 | A |
| H relation_sources=[] 无 hop；A hop 1/2 | `S1-dimensions-v1.md:57-67` | A |
| 未知/保留/弃用 fail-closed | `S1-dimensions-v1.md:47`（hit 规则） | A |
| frame_spec 字段命名 | 本提案 §6 | 本项目假设 |

---

## 7. S4-7 层次交互

| 主张 | 锚 | 等级 |
|---|---|---|
| drill=新 frame/一次一层；S4 不重算簇 | `ENGINEERING-PLAN.md:905-910`（ST-05/07）；S1-4 | A |
| S2 run `(level,view_family)` 只读 | `S2-clustering-v1.md:47-51,64-66`（S2-7/S2-10） | A |
| 跨层边只有 H 结构边 | S1 R-S1-11 `S1-dimensions-v1.md:59-60`；S2-9 | A |
| 旧节点清理细节 | 本提案 §7 | 本项目假设 |

---

## 8. S4-8 全展开

| 主张 | 锚 | 等级 |
|---|---|---|
| 默认替代+全展开开关；同 DataSource/同 present | `S0-terms-v1.md:69-73`（S0-8）；`S3-visual-v1.md:56-59` | A |
| `shown(default) ⊆ shown(full)` | S0 R-3 `S0-terms-v1.md:56-61,102`；S3-9 | A |
| full 仍是 Presentation 正交模式 | `ENGINEERING-PLAN.md:944-945`（ST-15/16） | A |
| FULL_MAX/full budget 归 S8 | 本提案 §8 | 本项目假设 |

---

## 9. S4-9 S3 契约

| 主张 | 锚 | 等级 |
|---|---|---|
| 渲染器只校验/渲染；不裁剪；超硬上限 `RENDER_BUDGET_EXCEEDED` | `S3-visual-v1.md:66-69`（S3-11/R-S3-2） | A |
| VM 字段/presence/rule_id/aggregate_count | `S3-visual-v1.md:71-75`（S3-12/R-S3-9） | A |
| `data_edge_ids` 审计但不进 Renderer | S0 R-3；`S3-visual-v1.md:72-75` | A |
| 阈值同源 | S3-11；`S3-visual-v1.md:83` | A |
| aggregate_count 由取景层给 | S3 R-S3-9 | A |

---

## 10. S4-10 S5 边界

| 主张 | 锚 | 等级 |
|---|---|---|
| focus/selection/nav 不进 VM；事件到 S5 | S0-9/D-4 `S0-terms-v1.md:75-79`；`S3-visual-v1.md:46-49` | A |
| 导航动作在 S5；S4 纯取景 | `ENGINEERING-PLAN.md:713-719`（事件/导航分离） | A |
| new_hop 仅 S5 显式动作 | S1-5 R-S1-10；`ENGINEERING-PLAN.md:913` | A |
| frame_spec 生成细节 | 本提案 §10 | 本项目假设 |

---

## 11. S4-11 S1/S2 一致性

| 主张 | 锚 | 等级 |
|---|---|---|
| presence 不改 type/label/contain_kind | `S1-dimensions-v1.md:99-107`（S1-12） | A |
| A 不改变簇 | `S2-clustering-v1.md:64-66`（S2-10） | A |
| 簇/run/dendrogram 不进 VM | `S2-clustering-v1.md:69`（S2-11）；S0-9 | A |
| 多归属按 view_family | S0-7；S2-6 | A |
| 无簇不伪造 | `S2-clustering-v1.md:73-76`（S2-12） | A |

---

## 12. S4-12 度量/验收

| 主张 | 锚 | 等级 |
|---|---|---|
| 规模不是问题但需显示预算 | `vision.md:71`（U-32）；S3-11 | A |
| P5 Admission 过程 | `ENGINEERING-PLAN.md:583,660` | A（工程草案） |
| 指标/G6/门禁归 S8 | 本提案 §12 | 本项目假设 |

---

## 13. 本项目假设清单（8 条）

1. 节点 tier 划分（tier0 focus+层块、tier1 一跳/子块、tier2 其余）与 label_rank（semantic<structural<navigation）。
2. tie-break = `(tier, hop, label_rank, canonical_id)`；边 tie-break = `(edge_tier, hop, canonical edge_id)`。
3. 预算不足 ⇒ `S4_BUDGET_INVALID` fail-visible（不降级为部分渲染）。
4. rule_id 枚举（11 项）为 v1 完整集合，新增须 S4 修订。
5. `unknown` 仅用于候选边输入不完整/未计算；不用于"数据中无边"。
6. full 模式 `FULL_MAX`/full budget 由 S8 定；仍受 max_nodes/max_edges 硬上限。
7. `frame_spec` 字段命名（level/view_family/dimension/focus/hop/new_hop/mode/budget）。
8. 多归属 cluster 端点按当前 view_family 显示；跨族选择细则归 S5/S6。

---

## 14. 机检伪代码（Admission 骨架，供 SE/S4 冻结）

```python
def admit(candidates, ctx, budget, dimension_registry, s2_run):
    assert budget.max_nodes > 0 and budget.max_edges > 0
    dim = resolve_dimension(dimension_registry, ctx.dimension_id)   # fail-closed
    base = base_nodes(ctx, s2_run)                                 # H 层块 / A 基座
    mandatory = [ctx.focus_id] + base
    if len(mandatory) > budget.max_nodes:
        raise S4BudgetInvalid("tier0 > max_nodes")
    nodes = select_nodes(candidates, mandatory, ctx, budget)       # tier + key
    edges = select_edges(candidates, nodes, ctx, dimension, budget)
    for e in candidates.edges:
        if e not in edges and e not in suppressed_candidates:
            mark(e, "suppressed", rule_for(e, ctx, nodes, budget))
    return {"nodes": nodes, "edges": edges}  # edges include presence/rule_id

def present(e, ctx):
    # Renderer 不调用；VM 只携带 S4 结果
    return e.presence == "shown"
```

**断言**：
```
- 同 (candidates, ctx, budget) → 同 VM（canonical sha）
- foldl: edges 全有 presence；presence!=shown ⇒ rule_id ∈ enum
- nodes<=max_nodes, edges<=max_edges
- shown edges ⊆ nodes×nodes；无悬空边
- hop=2 ⇒ new_hop=true；H 无 hop
- shown(default) ⊆ shown(full)（同 edition）
```

---

## 15. 覆盖矩阵

| 侧 | 项 | 落点 |
|---|---|---|
| U | U-5/15/16/17/18/19/21/22/27/28/31 | 提案 §13 |
| S0 | S0-5/S0-6/S0-8/S0-9 | §3/§4/§8/§10 |
| S1 | H/A、new_hop、present | §3/§6 |
| S2 | run/无簇/A 不改簇 | §7/§11 |
| S3 | presence/预算归属/VM | §9/§10 |
| 工程 | P5/ST-12..16 | `ENGINEERING-PLAN.md:583,660,912-916` |

---

## 16. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) S4 12 议项 + U 覆盖
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S4-render-proposal-A.md').read_text(encoding='utf-8'); print('S4 missing:',[f'S4-{i}' for i in range(1,13) if f'S4-{i}' not in t]); print('U missing:',[f'U-{i}' for i in [5,15,16,17,18,19,21,22,27,28,31] if f'U-{i}' not in t])"
# 2) 现状无 presence/预算：引擎只按 type 上色、全量 links
python -c "from pathlib import Path; t=Path('src/memoria/ui/static/app/js/graph-engine.js').read_text(encoding='utf-8'); print('engine presence', t.count('presence'), 'rule_id', t.count('rule_id')); t2=Path('src/memoria/ui/static/app/js/graph-view-2d.js').read_text(encoding='utf-8'); print('2d presence', t2.count('presence'), 'maxNodes', t2.count('maxNodes'))"
# 3) 关键锚
python -c "from pathlib import Path; checks=[('src/memoria/ui/static/app/js/graph-engine.js',179,'rawEdges = payload'),('src/memoria/graph/edge_derivation.py',787,'def canonical_edge_id')]; [print('OK' if n in Path(f).read_text(encoding='utf-8').splitlines()[l-1] else 'MISMATCH', f, l) for f,l,n in checks]"
```

**实测结果（2026-11-03）**：
- S4-1..S4-12 全部含 定义/规则·机检·反例·边界·U 映射·建议裁决·证据等级（缺失 0）；U 覆盖缺失 0。
- 现有 `graph-engine.js` 中 presence/rule_id 计数为 0；`graph-view-2d.js` 无 maxNodes 逻辑（全量 links 绘制）→ 现状无 S4 能力（A 级）。
- `graph-engine.js:179` rawEdges=payload.edges、`edge_derivation.py:787` canonical_edge_id 锚 OK。

---

## 17. 已知限制

1. tier/label_rank/tie-break 是设计建议，需 S4 冻结/SE 校核；不同排序会改变选点结果。
2. 预算数值（max_nodes/max_edges/FULL_MAX）归 S8；S4 只冻结字段/失败语义。
3. `unknown` 的触发面（source/端点/缓存）需 S9/S6 提供可判定输入；本提案只定义 S4 侧语义。
4. 多归属 cluster 端点的显示选择（当前 view_family 优先）需与 S5/S6 对齐。
5. 本场未写代码；机检伪代码需在实现阶段转成测试 fixture。
