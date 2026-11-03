# S5 独立异议与 A/B 差异

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（`241b1e1e…`）、`S1-dimensions-v1.md`（`6676c71d…`）、`S2-clustering-v1.md`（`92bb0041…`）、`S3-visual-v1.md`（`0ca4ea0e…`）+ `S3-ADDENDUM-1`、`S4-render-v1.md`（`2576f6c8…`），不得违反；`S5-charter.md`。
> **对象**：`S5-nav-proposal-A.md`（主办研究，sha **`6eee4f6685490f5415ab4c3594a4483e2eac0d3ba587ef7512a76be866486a40`**，33,878 B）与 `S5-nav-proposal-B.md`（本复核方，sha **`81066c59943e14a4bd7273ed81de3ee2bb19014093b097425c0096fc2631f9bf`**，19,049 B）。
> **独立性**：B 于 21:10:28 落盘，A 于 21:13:03 才出现；B 写作时未读 A。以下为写完后对照，逐项列、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0–S4 冻结。

---

## 0. A/B 差异总表（S5-1..S5-12）

| 议项 | A 的立场（A-v1） | B 的立场（B-v1） | 差异与判断 |
|---|---|---|---|
| S5-1 GraphNavFrame | 字段全：frame_id/focus/level/family/dimension/hop/new_hop/mode/budget/origin/edition；NavState 有 stack/selection/data_state | 字段较简：level/family/dim/focus/hop/new_hop/mode/history；GraphNavFrame 不进 VM | A 更细（origin/edition/budget）；B 缺 origin/edition，栈/生命周期表达较简。 |
| S5-2 状态机 | 9 主状态（Idle/Loading/Degraded/Overview/Focused/HierarchyDrilled/RelationExpanded/RelationDeepened/Stale）+ 正交 Full/EmptyNoSemantic；28 条转移；I1–I12 | 7 状态（Idle/Focused/HierarchyDrilled/RelationExpanded/FullExpanded/EmptyNoSemantic/ErrorRecoverable）；转移较少 | **A 更强**（加载/降级/stale/关系加深/非法转移完整）；B 缺 Loading/Degraded/Stale；B 的 `FullExpanded` 是独立状态但无进入转移（可达性问题，P1-B）。 |
| S5-3 点击 | kind 唯一；kp 跳编辑器、cluster drill；edge/background 不改导航 | 同 | 一致；A 的 `range_ok/file` 缺失处理更细。 |
| S5-4 drill/back | push/pop 恢复 focus/level/dimension/hop/mode；MAX_STACK=50；去重；面包屑截断；重开只恢复 level0 | push/pop 恢复；栈上限/去重；无重开策略 | 核心一致；A 更细（origin/面包屑/重开）；B 需补重开/面包屑细节。 |
| S5-5 NEW_HOP | 唯一 A 维、hop=1→2；push；幂等；默认隔离；H/无 focus fail-closed | 同 | 一致；A 更细（错误码/默认 frame_spec 检查）。 |
| S5-6 focus/selection | focus=导航、selection=UI；清空规则；FOCUS_LOST 向祖先/root；默认 root focus；Focused 是 UI 焦点 | 同核心；恢复 3 步；默认 frame；selection 不进 frame/VM | 一致；A 的 FOCUS_LOST 栈回溯更细；B 的恢复规则清晰。 |
| S5-7 维度切换 | 未知 fail-closed；hop reset/new_hop=false；**v1 清空 history**；focus 可表示保留否则 parent/root | 未知 fail-closed；hop reset；**push 当前 frame，back 可恢复维度**；focus 有效保留否则默认 | **关键差异**：A 清空 history（维度切换不可 back）；B push（可逆）。需 Lead 裁（P1-2）；与 S5-4 back 可逆/维度恢复要求相关。 |
| S5-8 全展开 | 正交；只改 mode；不 push；focus/level/stack 不变；持久化 mode；S4 subset 前提；失败回退 | 同核心；不 push；focus 保持；S4 契约 | 一致；A 的持久化/失败细节更细。 |
| S5-9 S4 接口 | frame_spec 白名单；S5 不算 presence；S4_BUDGET_INVALID 回退上一帧/初始降级；DIM_* fail-closed | 同；错误退上一帧；无 presence | 一致；A 更细（错误码/确定性）。 |
| S5-10 S3 事件 | 最小事件；payload 白名单；300ms 去重/pending；hover 不改导航；渲染器无导航 | 同核心；250ms 去重；键盘等价 | 一致；A 的 pending/stale 事件处理更细。 |
| S5-11 S1/S2 | H drill→HierarchyDrilled；A→RelationExpanded/Deepened；S2 run 只读；EmptyNoSemantic；多归属 origin | 同核心；EmptyNoSemantic；A 不改簇 | 一致；A 更细（data_state 复合）。 |
| S5-12 a11y/持久化/度量 | 键盘表/aria-live/持久化白名单/G6 指标 | 同核心；持久化 schema 较简 | 一致；A 更细（D-ST-06/07、延迟指标）。 |

**总判断**：A 在状态机完整性、加载/降级/stale、origin/edition、focus 恢复、a11y/持久化上明显更强；B 在 focus 一跳、VM 严格性、维度切换可逆上更保守。**A 的 S5a 状态图与转移表不一致、维度切换清空 history、S4 失败事务性**需修；B 需补加载/降级/stale 状态与 `FullExpanded` 可达性。

---

## 1. 异议（按严重度；P0=违反 S0–S4；P1=冻结前必须裁；P2=可冻结但后续补）

### P1-1（A）S5a mermaid 状态图与转移表不一致，复合状态被画成独立状态

- **议项**：S5-2 / S5a（S5 章程要求状态图与转移表同版本 `PARSE_OK`、无不可达/死状态）。
- **异议**：A 的 S5-2 声明 `FullExpanded`/`EmptyNoSemantic` 是**正交复合状态**，不是第二主状态；但 S5a mermaid 把 `FullExpanded` 画成独立状态，且只有 `Overview→FullExpanded`/`FullExpanded→Overview` 两条边；表 T20 允许 `TOGGLE_EXPAND` 从**任意可显示状态**（含 HierarchyDrilled/RelationExpanded/RelationDeepened）切换。同样 `Focused` 在 mermaid 只有 `Overview→Focused`，表 T26 允许从多状态 `FOCUS_NODE`；`Stale` 表 T21 从任意可显示状态，mermaid 只列部分。状态图与表不一致，S5a 机检会 FAIL，且 `<FullExpanded>` 可能与主状态并存/丢失。
- **反例**：在 `HierarchyDrilled` 打开全展开：表 T20 保持主状态 + mode=full；按 mermaid 只能到 `FullExpanded`（丢失 drilled 状态）或没有边（非法）。冻结后实现二选一，状态语义不唯一。
- **修复**：二选一：① 把 `FullExpanded/EmptyNoSemantic` 作为 **正交变量**（不画成主状态，图中用注释/子状态表达 mode/data_state）；② 若坚持画独立状态，必须为每个主状态补 `TOGGLE_EXPAND` 边与退出边，并声明复合状态优先级/恢复。同样补 `Focused`/`Stale` 的全状态边；S5a 与转移表逐条对应，mermaid `PARSE_OK` + 自动 diff 表。
- **严重度**：状态机闭包/图-表一致性是 S5 硬门禁 ⇒ **P1（冻结前）**。

### P1-2（A/B）维度切换是否可 back 恢复（A 清空 history vs B push）未裁

- **议项**：S5-7 / S5-4（U-8/U-9；S5 章程 S5-4 可逆栈、S5-7 history 处理）。
- **异议**：A 的 T18/S5-7 明确 **v1 清空 history**（"新导航上下文"），切换维度后 back 无法回到原维度/focus；B 选择 push 当前 frame，back 可恢复维度。S5-4 要求 drill/back 恢复 focus/level/**dimension**（drill 本身不改 dimension，但 back 可恢复），S5-7 要求 history 处理但未说清空；用户任务点名"drill/back 是否可逆（focus/level/dimension 恢复）"。A 的清空策略使"切换维度→back"不可逆，且丢失旧栈，可能与可逆栈语义冲突；A 自己 §14 列为待裁。
- **反例**：H→A 切换后按 back：A 无历史，回到默认/无操作，无法回到 H 的原 focus；用户认为"返回"应回 H；B 能回。
- **修复**：Lead 裁：推荐 **维度切换 push 当前 frame**（B），back 恢复 dimension/focus/hop/mode；或若 v1 清空 history，必须显式声明"维度切换不可 back"并同步 S5-4/S5-7 机检与 UX（提供"切回 H"动作），不能既说可逆栈又清空。二者只能一个。
- **严重度**：导航可逆/状态语义 ⇒ **P1（冻结前裁）**。

### P1-3（A/B）S4 失败（BUDGET_INVALID/FOCUS_UNRESOLVED）时导航转移的事务性/栈一致性未定义

- **议项**：S5-9 / S5-4（S4 R-S4-9；S5 状态机）。
- **异议**：A 的 S5-9 说导航动作遇 `S4_BUDGET_INVALID` "回退上一 frame，状态不变"；但 drill/new_hop/dimension 的实现通常是**先 push/改 frame 再调 S4**（A 的 T06/T16/T18 effect 写明 push/请求），若 S4 失败，必须回滚 push/stack/focus/mode 且保持原子性；A 未定义回滚点/栈事务，可能出现 `stack` 已 push 但状态未变、或 frame 已改但 VM 仍旧的混合态。B 的 S5-9 也未定义事务，只写退上一帧。S4 的 `S4_BUDGET_INVALID`/`S4_FOCUS_UNRESOLVED`/`DIM_*` 都可能失败。
- **反例**：drill：push frame → S4 报 BUDGET_INVALID → 回滚 frame 但未 pop stack ⇒ 下一次 back 恢复到错误帧；或先改 focus 再失败 ⇒ focus 指向无效节点。
- **修复**：冻结**转移事务**：所有导航动作先构造候选 `nextFrame`（不修改当前 frame/stack），调用 S4；成功才 commit（push/更新 state）；失败保持原 state/frame/stack 并公告；back 亦先验证目标 frame 可用再 commit。机检：失败注入后 state/frame/stack 与转移前 canonical 相等。
- **严重度**：状态一致性/可复算 ⇒ **P1（冻结前）**。

### P1-4（B）B 的 `FullExpanded` 是不可达/无退出状态，且缺 Loading/Degraded/Stale

- **议项**：B 的 S5-2（对照 S5 章程状态机闭包/无死状态）。
- **异议**：B 状态集含 `FullExpanded`，但转移表 `FULL_TOGGLE` 写"同状态"（不进入 FullExpanded），没有边进入 `FullExpanded`；它成为不可达状态。B 也缺 `Loading/Degraded/Stale/Overview/RelationDeepened`，加载失败/数据 stale/更深 2 跳的 UI 状态不完整；S5 章程/上游 S4 有 ST 状态。B 应吸收 A 的主状态集合或删除未用状态并把全展开作为正交变量。
- **反例**：初始加载无 Loading 状态；加载失败无 Degraded；语料变化无 Stale；FullExpanded 永远不出现；S5a 状态图有不可达节点。
- **修复**：B 吸收 A 的 `Loading/Degraded/Stale/Overview`（或至少 `Loading/Degraded/Stale`）与 `RelationDeepened`；`FullExpanded/EmptyNoSemantic` 改为正交变量或补全进入/退出边；S5a 与表同步。若 B 坚持 7 状态，必须删除 `FullExpanded` 并证明加载/失败/stale 由上层处理且可机检。
- **严重度**：状态机闭包/无死状态硬门禁 ⇒ **P1（B 冻结前修）**。

### P2 清单

| # | 项 | 异议/证据 | 修复 |
|---|---|---|---|
| P2-1 | A 的 `frame_id`/`edition_sha` 与 S4 frame_spec 字段未对齐 | A 用 frame_id=S4 VM/frame id 或 sha(frame_spec)；S4 frame_spec 无 edition_sha（S5 可自行用于 stale） | 冻结 frame_id 生成规则/edition 来源；不传给 S4 的字段不进 frame_spec |
| P2-2 | A 的 `FullExpanded`/`EmptyNoSemantic` 复合状态优先级 | 复合状态与主状态并存时 UX/aria 表示未冻结 | 定义复合状态优先级/显示；S5a 用正交表达 |
| P2-3 | A 的 `Focused` 主状态 vs frame.focus | Focused 是 UI 键盘焦点，frame.focus 是导航坐标，容易混淆 | 明命名 `kbdFocus` vs `frameFocus`；状态机机检 |
| P2-4 | A 的 S5-4 `BREADCRUMB_TO` 截断中间栈 | 只审计，未定义被丢弃帧的恢复/去重 | 定义截断/审计/不可恢复；栈上限 |
| P2-5 | A 的 S5-4 重开只恢复 level0（D-ST-07） | 与 S5-7 清空 history 一致，但与"重开状态恢复"需产品确认 | Lead/UX 确认；若需深栈恢复则改 |
| P2-6 | A 的 S5-12 URL/书签不含深导航 | 只存 mode/dimension/level0/focus；stale 处理 | 冻结 URL schema；edition 校验 |
| P2-7 | A/B 的事件去抖窗口不同（A 300ms/B 250ms） | 数值未冻结；S3 事件无时间戳/seq | S8 定值；去抖规则统一（同 node/kind 窗口） |
| P2-8 | A 的 T18 清空 history 与 B push 差异 | 见 P1-2；若选 A 必须写"维度切换不可 back" | 同 P1-2 |
| P2-9 | A 的 S5-11 EmptyNoSemantic 恢复转移 | 复合状态恢复 via data_state 变化；状态表无显式边 | 补 data_state 恢复转移/aria |
| P2-10 | G6 导航指标字段 | A 有延迟/深度/back 成功率/illegal/focus_lost；B 较简 | 合并 G6 字段；S8 阈值 |

---

## 2. 点名审查项结论

1. **GraphNavFrame 是否不进 VM / S5 是否偷算 presence**：A/B **PASS**（frame/stack 在 Presentation；S5 只发 frame_spec；VM 无 nav/focus/history/mode；S5 不算 presence）。
2. **状态机闭包/死状态/非法转移 fail-closed**：A 主状态/转移表/不变量完整，但 **S5a 图与表不一致（P1-1）**；B 有不可达 `FullExpanded`/缺 Loading/Degraded/Stale（P1-4）；非法转移两版均 fail-closed。
3. **点击语义按 kind 唯一**：A/B **PASS**（kp→编辑器、cluster→drill、edge/background 不改导航；未知 kind fail-closed）。
4. **drill/back 可逆/focus/level/dimension/hop 重置/栈上限/去重**：A **PASS**（栈/恢复/上限/去重/面包屑，但维度切换清空 history P1-2）；B 基本 PASS（维度切换可 back；加载/stale 缺失 P1-4）。
5. **EXPLICIT_NEW_HOP 唯一/幂等/隔离**：A/B **PASS**（A 维/hop1→2/push once/默认隔离/H 禁止）。
6. **focus vs selection 生命周期/删除/重聚类恢复/无 focus 默认 frame**：A/B **PASS**（focus 导航、selection UI；清空规则；FOCUS_LOST 恢复/默认 root）；A 更细（栈回溯）。
7. **维度切换/全展开与 focus 交互/未知 fail-closed/S4 subset**：A/B 方向 **PASS**；**维度切换 history 可逆性 P1-2**；全展开正交、S4 subset 前提两版一致。
8. **S3 事件/VM 纯度、S1/S2 只读 run/无簇**：A/B **PASS**（最小事件/payload 白名单/无导航；S2 run 只读；EmptyNoSemantic 不伪造簇）。
9. **可访问性/持久化/度量可机检**：A **PASS**（键盘/aria-live/持久化白名单/G6）；B 方向 PASS但细节较简。

---

## 3. 最严重 3 条（给 Lead 裁决顺序）

1. **P1-1（A）S5a 图与转移表不一致/复合状态被画成独立状态**：`FullExpanded` 仅 `Overview` 进出，但 T20 从任意可显示状态可 toggle；`Focused`/`Stale` 同样缺边；S5a 必 FAIL。修复：把 `FullExpanded/EmptyNoSemantic` 表达为正交变量（或补全每个主状态的进出边）；`Focused/Stale` 补全；S5a 与转移表逐条 diff、`PARSE_OK`。
2. **P1-2（A/B）维度切换是否可 back 恢复未裁**：A v1 清空 history（不可 back 到原维度），B push（可 back）。S5-4 可逆栈与 S5-7 history 处理冲突，用户任务点名"dimension 恢复"。修复：Lead 裁；推荐维度切换 push 当前 frame，back 恢复 dimension/focus/hop/mode；若清空则显式声明不可逆并提供切回动作，不能既称可逆栈又清空。
3. **P1-3（A/B）S4 失败时导航转移的事务性/栈一致性未定义**：drill/new_hop/dimension 先 push/改 frame 再调 S4；若 `S4_BUDGET_INVALID`/`FOCUS_UNRESOLVED`/`DIM_*` 失败，必须原子回滚 frame/stack/focus/state。修复：先构造 `nextFrame`、S4 成功才 commit；失败保持转移前 canonical state；失败注入测试。

> P1-4（B）B 的 `FullExpanded` 不可达/缺 Loading/Degraded/Stale，需吸收 A 的主状态或改正交；S5a 同步。

## 4. 结论

- **A 无 P0**，整体强于 B（状态机/加载/降级/stale/焦点恢复/a11y）；但 **P1-1（图-表不一致）、P1-2（维度切换 history）、P1-3（S4 失败事务）** 需冻结前修。
- **B 需修 P1-4**（不可达 `FullExpanded`、缺 Loading/Degraded/Stale）；其余 B 可作为维度切换可逆/focus 一跳的对照。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：S0-9/D-4 `S0-terms-v1.md:75-79`；S1-13；S3-7 事件；S4 R-S4-1..10 `S4-render-v1.md`；A S5-2/S5-4/S5-7/S5-9/S5a；B S5-2/S5-4/S5-7/S5-9。
