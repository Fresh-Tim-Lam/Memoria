# S5 异议与 A/B 差异 v2（复核方修订版对照）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S5-RULINGS.md`（sha `8285a8b3…`，R-S5-1..R-S5-8）。
> **对象**：`S5-nav-proposal-A-v2.md`（主办研究，sha **`538506a436b51bbe87fad2f98cd76b58249cea6278fd2197ea49d52bc81f1e19`**，42,303 B）与 `S5-nav-proposal-B-v2.md`（本复核方，sha **`84ba06f7b5e990c882d99488a2f778e8ef013246f7eb5e9e36a817dfa5287253`**，25,093 B）。
> **性质**：B-v2 以 S5-RULINGS 为依据独立修订，完成后对照 A-v2；逐项列差异、不合并。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S5-RULINGS/S0–S4。

---

## 0. R-S5 关闭矩阵

| 裁决 | A-v2 落位 | B-v2 落位 | 判定 |
|---|---|---|---|
| R-S5-1 S5a 表↔图/正交 | 9 主状态；mode/data_state 正交；30 组表展开 148 边、S5a 逐条生成；Focused/Stale 补边 | 9 主状态；mode/data_state 正交；S5a 草案+生成规则（表为准） | A **关闭**；B 基本关闭但 S5a 尚未由脚本生成（B 需 SE 生成，P2） |
| R-S5-2 维度切换可 back | S5-7 push；back 恢复 focus/level/dim/hop/mode；history 仅 CLOSE/RELOAD/RESET 清 | 同 | **关闭** |
| R-S5-3 事务化 | S5-9 nextFrame→S4→commit；失败 diff=0；初始 Degraded；非初始保持 | 同 | **关闭**；A 的事务依赖 `res.frame_id/edition`（P1-1） |
| R-S5-4 主状态并集 | 9 主状态；每状态进出；CLOSE/RELOAD 全局 | 同 | **关闭** |
| R-S5-5 Focused | Focused 主状态；不改 frame.focus；selection 瞬态 | 同 | **关闭** |
| R-S5-6 栈/重开 | MAX_STACK=50/去重/截断/重开 level0+mode+dim | 同 | **关闭** |
| R-S5-7 full/drill 正交 | mode 正交；drill 保持 full；失败事务化 | 同 | **关闭** |
| R-S5-8 并集/frame_id/edition | frame_id=S4 `res.frame_id`、edition=`res.edition_sha`（P1-1：S4 未定义） | frame_id=sha256(canonical(frame_spec))；edition 本地；去抖 300ms；G6 统一 | **部分关闭**：A 需改 frame_id/edition 来源（P1-1）；B 已自洽 |

**结论**：R-S5-1/2/3/4/5/6/7 两版已关闭；**R-S5-8 的 frame_id/edition 来源在 A 侧仍未闭环**（P1-1）；A 转移表有重复行（P1-2）；B 缺焦点丢失/数据刷新转移（P1-3）。

---

## 1. A-v2 / B-v2 逐项差异（S5-1..S5-12）

| 议项 | A-v2 | B-v2 | 差异与判断 |
|---|---|---|---|
| S5-1 frame | frame_id=`S4 AdmissionResult/VM frame_id`；edition=`res.edition_sha`；origin 等 | frame_id=`sha256(canonical(frame_spec))`；edition 本地；history 栈 | **A 更强字段/状态细节**；但 A 依赖 S4 未定义字段（P1-1）；B 自洽。 |
| S5-2 状态机 | 9 主状态 + 30 组转移展开 148 边；I1–I12；Focused/Stale 补边 | 9 主状态 + 29 组转移；正交 mode/data_state；S5a 草案 | A 更完整（DATA_REFRESHED/FOCUS_LOST）；**A 表 T13 与 T14–T17 重叠重复（P1-2）**；B 缺 FOCUS_LOST/DATA_REFRESHED（P1-3）。 |
| S5-3 点击 | kind 唯一；kp 不改 frame；cluster 事务 drill | 同 | 一致。 |
| S5-4 drill/back | 事务 push/pop；MAX_STACK=50；去重；breadcrumb 截断；重开 level0 | 同 | 一致；A 更细（origin）。 |
| S5-5 NEW_HOP | 唯一 A 维；push；幂等；H/无 focus fail | 同 | 一致。 |
| S5-6 focus/selection | Focused 不改 frame.focus；FOCUS_LOST 最近祖先/root | 同核心；恢复 3 步；但无 FOCUS_LOST 转移 | 一致；**B 缺 FOCUS_LOST 事件（P1-3）**。 |
| S5-7 维度切换 | push；back 恢复；history 仅 CLOSE/RELOAD/RESET 清 | 同 | 一致。 |
| S5-8 全展开 | 正交 mode；drill 保持 full；事务失败回退 | 同 | 一致。 |
| S5-9 S4 接口 | nextFrame→S4→commit；**res.frame_id/edition**；初始 Degraded | nextFrame→S4→commit；frame_id=sha(frame_spec) | 事务一致；**A frame_id/edition 来源 P1-1**；B 更自洽。 |
| S5-10 事件 | 最小事件；300ms 去抖；hover 不导航 | 同 | 一致。 |
| S5-11 S1/S2 | H/A 状态；run 只读；EmptyNoSemantic 正交 | 同 | 一致；B 需补 DATA_REFRESHED 驱动 data_state 恢复（P1-3）。 |
| S5-12 a11y/持久化/G6 | 详细；持久化 focus（edition 匹配） | 同核心；持久化白名单；G6 统一 | 一致；A 的 focus 持久化与 R-S5-6 白名单需对齐（P2）。 |

**总判断**：A-v2 在状态机完整性（DATA_REFRESHED/FOCUS_LOST）、origin/edition、a11y/G6 上更强；B-v2 在 frame_id 自洽、focus 生命周期、无不可达状态上更保守。**A 的 P1-1/P1-2、B 的 P1-3 是最后收口**。

---

## 2. 仍需解决的 3 点

### P1-1（A）`frame_id`/`edition_sha` 依赖 S4 未定义的字段

- **现状**：A-v2 S5-1 写 `frame_id = S4 AdmissionResult/VM frame_id`，S5-9 写 `cand.frame.frame_id = res.frame_id`、`cand.frame.edition_sha = res.edition_sha`；但 **S4-render-v1 的冻结接口没有 `frame_id`/`edition_sha` 字段**（`S4-render-v1.md` 只定义 AdmissionResult/VM 的候选载体/presence，无 frame_id/edition；S4 frame_spec 也无 edition）。R-S5-8 要求 frame_id/edition 与 S4 frame_spec 对齐，但 S4 未提供这两个输出；A 的依赖不可实现。
- **反例**：S5 调 S4，返回 `{nodes,edges,...}` 无 `frame_id`/`edition_sha` ⇒ A 的 `cand.frame.frame_id=undefined`，事务失败判断/stack 去重/`origin.from_frame_id` 全部失效。
- **修复**（推荐 B 的派生法）：`frame_id = sha256(canonical(frame_spec))`（S4 同输入同 frame_spec ⇒ 同 id；与 S4 `view_model_id` 可用映射校验）；`edition_sha` 由 S5 从 `corpus_manifest_sha + view_family edition` 派生/传入（S5 本地 stale 校验），**不要求 S4 返回未冻结字段**；如需让 S4 返回 edition，必须走 S4 修订/`S4-ADDENDUM` 并由 Lead 批，S5 冻结稿不能假设。机检：frame_id 与 frame_spec 一一对应；edition 与 S4 输入身份一致（S5 记录）。
- **严重度**：S4/S5 接口契约 ⇒ **P1（冻结前）。

### P1-2（A）S5-2 转移表 T13 与 T14–T17 重叠，同一 `(state,event)` 多条转移

- **现状**：A-v2 T13 `From = Overview/Focused/HierarchyDrilled/RelationExpanded/RelationDeepened`，Event=`CLICK_CLUSTER`；而 T14 `Focused`、T15 `HierarchyDrilled`、T16 `RelationExpanded`、T17 `RelationDeepened` 也有 `CLICK_CLUSTER`（各自 To 不同）。同一 `(Focused,CLICK_CLUSTER)`、`(HierarchyDrilled,CLICK_CLUSTER)` 等有 2 条转移，状态机非确定；T13 与 T14–T17 谁优先、S5a 生成哪条边、失败语义均不唯一。
- **反例**：`HierarchyDrilled + CLICK_CLUSTER`：T13 可到 Hierarchy/Relation，T15 到 Hierarchy；S5a 生成两条边/一个 event 两个 To；实现按表序或集合序不知；机检"每个 (state,event) 唯一"FAIL。
- **修复**：互斥化 From 集合：**T13 只保留 `Overview`**（或只保留 `Focused` 的 UI delegation），T14–T17 各自处理 Focused/Hierarchy/Relation/Deepened；或删除 T14–T17 让 T13 统一处理（但 Focused 要清 UI focus/各状态 To 不同，建议保留专表并删 T13 中的重叠状态）。S5a 生成器断言 `from_state × event` 唯一。
- **严重度**：状态机确定性/S5a 表图一致 ⇒ **P1（冻结前）。

### P1-3（B）B-v2 缺 `FOCUS_LOST`/`DATA_REFRESHED` 转移，focus 失效与 data_state 恢复无事件入口

- **现状**：B-v2 S5-6 写 focus 丢失恢复 3 步、S5-11 写 `data_state` 恢复，但 S5-2 转移表没有 `FOCUS_LOST`/`DATA_REFRESHED` 行；`RUN_UPDATED`/`CORPUS_CHANGED` 只到 `Stale`。因此 focus 失效（删除/重聚类）和 empty→ok 的恢复没有可机检的状态转移，S5a 也缺边；R-S5-4 无死状态/闭包不成立（恢复路径不可达/事件未定义）。
- **反例**：重聚类后 focus 消失：无 `FOCUS_LOST` 事件 ⇒ 只能停在旧 frame/非法 focus；`data_state` empty→ok 无 `DATA_REFRESHED` ⇒ EmptyNoSemantic 恢复不定义；状态图缺边。
- **修复**：B 吸收 A 的 T18 `FOCUS_LOST`（显示态集合→祖先/root，事务）与 T07 `DATA_REFRESHED`（edition_match，重算 data_state，不重取景，SELF）；补 S5a 边；机检 focus 恢复路径可达、data_state 恢复有转移；`FOCUS_LOST` 不得作为非法静默。
- **严重度**：状态闭包/focus 生命周期 ⇒ **P1（B 冻结前）。

> 另：A 的 S5a 声称由 30 组表展开 148 边；T13/T14–T17 重叠会导致生成器产生重复/歧义边，须先修 P1-2 再生成 S5a（P2-1）。B 的 S5a 目前是草案，须由表生成（R-S5-1），B 应在 SE 前用脚本生成并断言表↔图一致（P2-2）。

## 3. 其余 P2

| # | 项 | 建议 |
|---|---|---|
| P2-1 | A S5a 148 边生成/T13 重叠 | 修 P1-2 后由表生成，断言 `(state,event)` 唯一、边集=表集合 |
| P2-2 | B S5a 为草案/手工图 | B/SE 用脚本从表生成，`mermaid PARSE_OK`，表↔图一致 |
| P2-3 | A `edition_sha`/frame_id 持久化与 S4/S6a | 见 P1-1；edition 可进 S5 frame，不写入 VM |
| P2-4 | A S5-12 持久化 focus（edition 匹配）与 R-S5-6 白名单 | R-S5-6 只恢复 level0 frame+mode+dim；focus 只能是 root，否则不恢复；明确 |
| P2-5 | A `T18 FOCUS_LOST` 的祖先选择规则 | 最近祖先/root 可复算；若多归属，按当前 view_family |
| P2-6 | A/B 去抖 300ms 的 pending/seq | 统一以 `(event,id,frame_id)` 去重；stale 事件丢弃审计 |
| P2-7 | A/B G6 字段 | 合并：frame_switch_latency、depth、back_success、illegal、focus_lost、empty entries、new_hop、dimension/mode switch、state_distribution |
| P2-8 | A/B URL/书签 schema | 归 S6a；v1 不编码深栈；edition 校验 |
| P2-9 | A `RESET`→Loading vs `CLOSE`→Idle | 语义一致化；S5a 生成器覆盖 |
| P2-10 | B `Focused`/`Stale` 边与表一致 | 补 P1-3 后重生成 S5a |

---

## 4. 点名审查结论（v2）

1. **GraphNavFrame 不进 VM / S5 不偷算 presence**：A/B **PASS**（frame/stack Presentation；只 frame_spec；VM 无 nav/focus/history/mode；不调 S4 presence）。
2. **状态机闭包/死状态/非法 fail-closed**：A 状态/表完整但 **T13/T14–T17 重叠（P1-2）**；B 状态集完整但缺 FOCUS_LOST/DATA_REFRESHED（P1-3）；非法转移两版 fail-closed。
3. **点击 kind 唯一**：A/B **PASS**（kp 编辑器、cluster drill；edge/background 不导航；未知 kind fail-closed）。
4. **drill/back 可逆/focus/level/dimension/hop/栈上限/去重**：A/B **PASS**（事务/快照/MAX=50/去重/面包屑/重开 level0）。
5. **NEW_HOP 唯一/幂等/隔离**：A/B **PASS**。
6. **focus vs selection/删除/重聚类恢复/无 focus 默认 frame**：A **PASS**（FOCUS_LOST T18）；B 逻辑有但状态表缺事件（P1-3）。
7. **维度切换/全展开/focus/未知 fail-closed/S4 subset**：A/B **PASS**（push/back 恢复；full 正交；S4 前提）。
8. **S3 事件/VM 纯度、S1/S2 只读 run/无簇**：A/B **PASS**。
9. **a11y/持久化/度量**：A **PASS**（键盘/aria/白名单/G6）；B 方向 PASS 细节较简。

---

## 5. 结论

- **两版均关闭 R-S5-1/2/3/4/5/6/7 的 P1**；**A 的 P1-1（frame_id/edition 依赖 S4 未定义字段）和 P1-2（T13 重叠）**、**B 的 P1-3（缺 FOCUS_LOST/DATA_REFRESHED 转移）** 需冻结前修。
- A-v2 在状态完整性/事务/焦点恢复/a11y/G6 上更强；B-v2 在 frame_id 自洽/VM 严格性上更好。建议冻结稿以 A 状态机/事务为主干，取 B 的 frame_id 派生并补 B 的 FOCUS_LOST/DATA_REFRESHED。
- 未写产品代码/契约，未 commit；差异逐项列出未静默合并。

> 参考锚：R-S5 `S5-RULINGS.md:18-50`；S4 `S4-render-v1.md`（无 frame_id/edition 字段）；A-v2 S5-1/S5-2/S5-9/S5a；B-v2 S5-1/S5-2/S5-6/S5-11。
