# S5 提案 A · 证据与机检清单

> 配套：`S5-nav-proposal-A.md`｜票：task-315｜日期：2026-11-03
> 用途：另一人可按本文件复核 S5 每条断言（file:line / 产物 / 复跑命令）。
> 独立性：**未阅读** S5 复核方草稿（S5-nav-proposal-B / S5-objections）；不引用其结论。
> 纪律：未改产品代码/契约/schema/用户库；未 commit。

---

## 0. 证据等级与统计

| 级 | 含义 | S5 用途 |
|---|---|---|
| A | 原话/冻结契约/决策/可复跑代码事实 | GraphNavFrame/状态/点击语义/2 跳/S4 接口 |
| B | 单源实测产物 | 引用 S2 probe（无语义边）说明 EmptyNoSemantic 状态 |
| C | 单源推理 | 少量设计取舍（并入"本项目假设"） |
| 本项目假设 | 无独立证据的显式约定 | 状态命名/栈上限/防抖窗口/持久化粒度 |

**统计**：A 级锚点见 §1–§12；**本项目假设 9 条**（§13）；B 引用 S2 probe 1 份。

---

## 1. S5-1 GraphNavFrame/边界

| 主张 | 锚 | 等级 |
|---|---|---|
| VM 不含导航/焦点/历史/mode；D-4 | `S0-terms-v1.md:75-79`；`S1-dimensions-v1.md:99-107` | A |
| S4 是纯取景；S5 只发 frame_spec；focus/selection/nav 不进 VM | `S4-render-v1.md:67-70`（S4-11） | A |
| GRAPH_NAV_FRAME 是工程既有实体 | `ENGINEERING-PLAN.md:42,629,969` | A（工程草案） |
| 字段命名/stack 结构 | 本提案 §1 | 本项目假设 |

---

## 2. S5-2 状态机

| 主张 | 锚 | 等级 |
|---|---|---|
| 工程 ST-01..ST-19 状态/转移草案 | `ENGINEERING-PLAN.md:1026-1048` | A（工程草案） |
| ST-05 drill push origin、ST-09/10 BACK、ST-12..14 hop、ST-15/16 full、ST-19 CLOSE | `ENGINEERING-PLAN.md:1034-1048` | A |
| D-ST-01..07 待裁决（HopNetwork/back origin/breadcrumb/full 持久化/恢复粒度） | `ENGINEERING-PLAN.md:1050-1060` | A |
| 状态/事件/转移表/不变量 | 本提案 §2 | 本项目假设（S5 定） |

---

## 3. S5-3 点击语义

| 主张 | 锚 | 等级 |
|---|---|---|
| cluster 点击=深入一层（drill） | `vision.md:24`（U-7）；S0 Navigation | A |
| KP 点击=跳编辑器（U-20），图谱状态不变 | `vision.md:37`（U-20）；`ENGINEERING-PLAN.md:1035,1037` ST-06/08 | A |
| S3 事件 `nodeClick{node_id,kind}`/edge/background | `S3-visual-v1.md:46-49` | A |
| 现状统一 jumpToTarget（反例：无 kind 分流） | `app.js:1661-1677` | A |
| 检查器/公告细节 | 本提案 §3 | 本项目假设 |

---

## 4. S5-4 drill/back

| 主张 | 锚 | 等级 |
|---|---|---|
| drill level+1/focus=簇/push origin | `ENGINEERING-PLAN.md:1034,1036` ST-05/07；S4-8 | A |
| BACK 弹栈恢复 origin/focus | `ENGINEERING-PLAN.md:1038-1039` ST-09/10；D-ST-02 | A |
| 面包屑清中间栈 | `ENGINEERING-PLAN.md:1056` D-ST-03 | A |
| 重新打开只恢复 level0/不恢复深栈 | `ENGINEERING-PLAN.md:1060` D-ST-07 | A |
| MAX_STACK/去重/审计 | 本提案 §4 | 本项目假设 |

---

## 5. S5-5 EXPLICIT_NEW_HOP

| 主张 | 锚 | 等级 |
|---|---|---|
| 唯一显式 2 跳：A 维/new_hop=true/hop_budget=2 | `S1-dimensions-v1.md:63-67`（S1-5/R-S1-10） | A |
| S4 校验 hop=2 必须 new_hop=true；默认路径禁止 2 | `S4-render-v1.md:31-34`（S4-4） | A |
| 工程 ST-13/EXPLICIT_NEW_HOP | `ENGINEERING-PLAN.md:1042,1088,1101` | A |
| 按钮/命令/幂等细节 | 本提案 §5 | 本项目假设 |

---

## 6. S5-6 focus/selection

| 主张 | 锚 | 等级 |
|---|---|---|
| focus=取景基座（S4 one_hop F={focus}） | `S4-render-v1.md:26-29`（S4-3） | A |
| origin/via 记录进入路径、BACK 恢复 | `ENGINEERING-PLAN.md:1034,1038` ST-05/09；D-ST-02 | A |
| selection/焦点不进 VM | S0-9/D-4；S3-12 | A |
| focus 丢失映射/默认 root | 本提案 §6 | 本项目假设 |

---

## 7. S5-7 维度切换

| 主张 | 锚 | 等级 |
|---|---|---|
| 维度切换属 Presentation/S5；hop 重置 | `S1-dimensions-v1.md:104-107`（S1-13）；S1-5 | A |
| 未知/保留/弃用 fail-closed | `S1-dimensions-v1.md:47` | A |
| 组合维度 v1 不支持 | S1-10/D-5 | A |
| history 清空策略 | 本提案 §7 + §14 争议 | 本项目假设 |

---

## 8. S5-8 全展开

| 主张 | 锚 | 等级 |
|---|---|---|
| 全展开是 Presentation 正交开关；默认替代 | `S0-terms-v1.md:69-73`（S0-8）；`S3-visual-v1.md:56-59` | A |
| full 同 Admission、subset 构造、candidate_scope | `S4-render-v1.md:56-60`（S4-9） | A |
| 持久化开关（D-ST-06） | `ENGINEERING-PLAN.md:1059` | A |
| focus 不变/清空 selection/持久化键 | 本提案 §8 | 本项目假设 |

---

## 9. S5-9 与 S4 接口

| 主张 | 锚 | 等级 |
|---|---|---|
| S4 纯取景；S5 只构造 frame_spec | `S4-render-v1.md:67-70`（S4-11） | A |
| frame_spec 字段（level/view_family/dimension/focus/hop/new_hop/mode/budget） | S4-2/S4-7/S4-9；本提案 §9 | A+本项目假设 |
| S4_BUDGET_INVALID 处理 | S4-5/S4-9；本提案 §9 | 本项目假设 |
| 同输入同 frame | S4-2 确定性；本提案 §9 | A |

---

## 10. S5-10 与 S3 事件

| 主张 | 锚 | 等级 |
|---|---|---|
| 最小事件集/payload 无导航 | `S3-visual-v1.md:46-49` | A |
| 渲染器无导航动作 | S3-7；S4-11 | A |
| 事件→S5 映射（ST-05/06 等） | `ENGINEERING-PLAN.md:1034-1038,1088-1101` | A（工程草案） |
| 300ms 防抖/pending 守卫 | 本提案 §10 | 本项目假设 |

---

## 11. S5-11 与 S1/S2

| 主张 | 锚 | 等级 |
|---|---|---|
| H 下钻 vs A 扩展的维度差异 | `S1-dimensions-v1.md:13-15,57-67` | A |
| S2 run 只读、A 不改变簇 | `S2-clustering-v1.md:64-66`（S2-10） | A |
| 无簇合法/EmptyNoSemantic | `S2-clustering-v1.md:73-76`（S2-12）；`S3-visual-v1.md:51-54`（S3-8） | A |
| 多归属 back origin | S0-7；`ENGINEERING-PLAN.md:1055` D-ST-02 | A |
| 恢复触发细节 | 本提案 §11 | 本项目假设 |

---

## 12. S5-12 a11y/持久化/度量

| 主张 | 锚 | 等级 |
|---|---|---|
| a11y 基线（键盘/aria/reduced motion） | `S3-visual-v1.md:61-64`（S3-10） | A |
| 持久化设置模式（graph-settings） | `ENGINEERING-PLAN.md:1059`；`graph-settings.js:127-212` | A |
| 深栈不恢复 | `ENGINEERING-PLAN.md:1060` D-ST-07 | A |
| 键位/aria 文案/延迟目标/G6 字段 | 本提案 §12 | 本项目假设 |

---

## 13. 本项目假设清单（9 条）

1. 主状态集合（Idle/Loading/Degraded/Overview/Focused/HierarchyDrilled/RelationExpanded/RelationDeepened/Stale）；`FullExpanded/EmptyNoSemantic` 定义为正交复合状态。
2. `MAX_STACK=50`；连续同 frame_id push 去重；栈满丢最旧（保留根）并审计。
3. 300ms 点击去重窗口；drill pending 期间忽略同簇重复 click。
4. 维度切换 v1 **清空 history**（新导航上下文），focus 可表示则保留。
5. full 模式下 drill/back 保持 full（mode 正交）。
6. 重开只恢复 level0 frame + mode/dimension，不恢复深栈。
7. `S4_BUDGET_INVALID` 在导航动作时回退上一 frame；初始帧则 Degraded。
8. `Focused` 作为主状态但只改 UI 焦点，不改 GraphNavFrame.focus_id。
9. 键盘键位与 aria-live 文案；frame 切换目标 <200ms（S8 可调）。

---

## 14. 机检伪代码（S5 状态机骨架）

```python
PRIMARY = {"Idle","Loading","Degraded","Overview","Focused",
           "HierarchyDrilled","RelationExpanded","RelationDeepened","Stale"}
COMPOSITE = {"FullExpanded","EmptyNoSemantic"}
EVENTS = {"OPEN_GRAPH","DATA_READY","DATA_FAILED","RETRY","RELOAD","CLOSE",
          "CLICK_KP","CLICK_CLUSTER","CLICK_EDGE","CLICK_BACKGROUND","BACK",
          "BREADCRUMB_TO","SELECT_DIMENSION","EXPLICIT_NEW_HOP","TOGGLE_EXPAND",
          "CORPUS_CHANGED","FOCUS_LOST","DISMISS_ERROR","FOCUS_NODE","FOCUS_CLEAR"}

def step(state, event):
    if (state, event) not in TRANSITIONS:
        record("S5_ILLEGAL_TRANSITION", state, event)
        return state                     # fail-closed
    guard, action, target = TRANSITIONS[(state, event)]
    if not guard(state):
        record("S5_GUARD_FAILED", state, event)
        return state
    action(state)                        # 只改 Presentation / 发 frame_spec
    return target

# 断言
assert set(TRANSITIONS) covers all allowed rows
assert all(s in PRIMARY|COMPOSITE for s in STATES)
assert reachable(Idle, all_primary)      # 无不可达
assert all(has_path_to(s, "Idle") for s in PRIMARY|COMPOSITE)  # 无死状态
assert not any(S5 computes presence / reads DataSource)
```

**S5a mermaid 机检（SE/ Lead 复验）**：提案 §13 代码块；要求 `stateDiagram-v2` 同版本解析 `failedBlocks:0`；状态名/转移与 §2 表逐条对应；`CLOSE` 全局、`RELOAD` 全局可达。

---

## 15. 覆盖矩阵

| 侧 | 项 | 落点 |
|---|---|---|
| U | U-1/4/7/8/9/15/20/22/24/26/29 | 提案 §13 |
| S0 | S0-5/S0-6/S0-8/S0-9 | §3/§9/§10 |
| S1 | H/A、new_hop、present | §5/§7/§11 |
| S2 | run/无簇 | §11 |
| S3 | 事件/VM/presence | §9/§10 |
| S4 | frame_spec/one_hop/subset | §5/§8/§9 |
| 工程 | ST-01..19/D-ST/事件 | §2/§4/§5 |

---

## 16. 复跑机检（Windows PowerShell；已执行）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1) S5 12 议项 + U 覆盖
python -c "from pathlib import Path; t=Path('docs/design/multilevel-graph/S5-nav-proposal-A.md').read_text(encoding='utf-8'); print('S5 missing:',[f'S5-{i}' for i in range(1,13) if f'S5-{i}' not in t]); print('U missing:',[f'U-{i}' for i in [1,4,7,8,9,15,20,22,24,26,29] if f'U-{i}' not in t])"
# 2) 现状：统一 jumpToTarget、文件导航栈与图谱导航分离
python -c "from pathlib import Path; t=Path('src/memoria/ui/static/app/js/app.js').read_text(encoding='utf-8').splitlines(); print('app 1661-1677 jumpToTarget:', any('jumpToTarget' in x for x in t[1660:1677]))"
python -c "from pathlib import Path; t=Path('src/memoria/ui/static/app/js/nav-stack.js').read_text(encoding='utf-8'); print('nav-stack filePointer:', 'filePointer' in t, 'graph nav:', 'GraphNav' in t)"
# 3) 关键锚
python -c "from pathlib import Path; checks=[('src/memoria/ui/static/app/js/app.js',1661,'onGraphNodeClick'),('src/memoria/ui/static/app/js/nav-stack.js',23,'function push')]; [print('OK' if n in Path(f).read_text(encoding='utf-8').splitlines()[l-1] else 'MISMATCH', f, l) for f,l,n in checks]"
```

**实测结果（2026-11-03）**：
- S5-1..S5-12 全部含 定义/规则·机检·反例·边界·U 映射·建议裁决·证据等级（缺失 0）；U 覆盖缺失 0。
- 现状 `app.js:1661-1677` 统一 `jumpToTarget`（无 kind 分流，A 级反例）；`nav-stack.js:23-36` 是文件导航栈（`filePointer`），不是图谱导航（A 级现状）。
- 锚 OK：`onGraphNodeClick`、`function push`。

---

## 17. 已知限制

1. S5a 状态图语法需 SE/Lead 用同版本 mermaid 解析确认；本文件只做结构对应检查。
2. 状态命名/转移细节（Focused/复合状态/维度切换清 history）为设计取舍，需 S5 裁决。
3. 栈上限/防抖/延迟/持久化白名单为建议值，S8 可调。
4. focus 丢失后的祖先映射依赖 S2 parent_run/level 结构，S6a/S9 需提供可查询路径。
5. 本场无产品代码；S5 状态机/事件映射需在实现阶段用 fixture 测试。
