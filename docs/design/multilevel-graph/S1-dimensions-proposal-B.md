# S1 维度体系提案 B（独立复核方）

> **依据（不可改写）**：`multilevel-graph-vision.md` U-1..U-35；上游冻结 `S0-terms-v1.md`（sha `241b1e1e…`，R-1/R-2/R-3、D-1..D-5 不得违反）；`S0-FREEZE-RECORD.md`；本场章程 `S1-charter.md`；议程 V0.2。
> **性质**：独立复核方提案；**写作时未读** `S1-dimensions-proposal-A.md`（当时尚未落盘）；写完后再对照 A，差异见 `S1-objections.md`。
> **证据等级**：A=可执行/机检源码（file:line）；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S0 冻结条款/裁决。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. 总原则（S1 只做维度体系，不重开 S0）

1. 维度 = **同一层次上的取景规则**；不是层次、不是视觉风格、不是全展开、不是 2D/3D（S0-3）。
2. v1 只允许 **H（层次维）/ A（关联维）** 两个 active 维度；**同一视图一次只激活一个**（D-5）；组合只登记 reserved 槽位。
3. `E_relation_min = {contain(structural), contain(semantic), reference, extend}` 冻结；**S1 只能加不能删**（R-1）。A 维必须覆盖 U-10 的包含/引用/语义关联，不得窄化。
4. 未知/保留/废弃维度一律 **fail-closed**；reserved 维度**不得**进渲染分支/默认取景/ViewModel。
5. ViewModel 保持 S0 D-4 纯度：**不含导航状态/mode/capabilities/维度切换逻辑**；`dimension_id` 只作为视图上下文元数据。
6. `present(e,ctx)` 仍是唯一渲染判据；维度只改变 `ctx` 与 `E_relation(D)`，不改变数据事实。

### 0.1 覆盖矩阵（S1 相关 U；本场所有 U 必须出现）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-8 | 层次维度=S1-4 | U-25 | 开放槽位=S1-3/S1-15 |
| U-9 | 其他维度=S1-2/S1-3/S1-15 | U-27 | 存无/类型=S1-12 |
| U-10 | 关联维度=S1-5/S1-6（E_relation_min） | U-30 | 关联维定义=S1-5 |
| U-11 | 跳数=S1-7 | U-32 | 规模/检索=S1-9/S1-14 |
| U-12 | 更多维度=S1-3/S1-15 | U-33 | 2D/3D≠维度=S1-1/S1-13 |
| U-4/U-5 | 层次/默认=S1-4（承接 S0） | U-34 | 逐议项结构=本文件 |
| U-6/U-7 | 簇节点/深入=S1-4/S1-13 | U-13/U-14 | 簇定义承接 S0-4 |
| U-15 | 一跳=S1-5/S1-7 | U-17/U-18 | 背后图/防污染=S1-7/S1-9 |
| U-21/U-31 | 多归属=S1-4/S1-12 | U-26 | 默认/全展开=S1-13 |
| U-28 | 最小粒度=S1-4 | U-29 | agent 设计 KP=S1-14（S10 细化） |

---

## S1-1 维度定义与边界

**定义/规则**：维度是一个**可命名的取景规则**：给定 `(DataSource, level, view_family, focus, hop/budget, dimension_id)`，唯一决定"取哪些节点/边、沿哪些关系源、什么方向、扩展几步、何时停"。维度**不是**：
- 层次（level 改变粒度；维度不改变粒度）；
- 视觉风格（`graphStyle=force|galaxy` 是渲染样式，不是维度；A 级现状 `graph-settings.js:38,585-587`）；
- 全展开（`mode` 是 Presentation 正交开关，S0-8）；
- 2D/3D（渲染后端，U-33）；
- 边类型（type 是边属性/标签，不是取景维度）。

**取景规则最小字段**（完整 schema 见 S1-2）：
```
dimension_id, name, basis, relation_sources, direction,
hop_default, hop_max, termination, status, priority, version, u_refs
```
**机检条件**：
```python
assert dimension_id not in {"graphStyle","force","galaxy","2d","3d","full_expand","level"}
assert basis in {"level_partition","relation_expansion"}
assert "dimension" not in vm_fields          # VM 无维度切换/配置字段
```
**反例**：把 graphStyle 改名为 "visual 维度"；把 3D 当独立维度；把 full_expand 当第三维度；把边类型枚举当维度。
**边界用例**：active 维度切换但不改变 level；维度配置来自注册表而非代码分支；2D/3D 切换不改变 `dimension_id`。
**U 映射**：U-8、U-9、U-12、U-25、U-33。
**建议裁决**：冻结定义 + 最小字段 + 排除清单（graphStyle/2D/3D/full_expand/edge type 不是维度）。
**证据等级**：A（`graph-settings.js:38,578,585-587` 证明 graphStyle 是样式；S0-3 冻结）+ R（D-5）。

---

## S1-2 维度注册表 schema（机检 + fail-closed）

**定义/规则**：v1 维度集合只存在于**注册表**（研究/配置层，不写产品 sidecar/新段）；注册项字段、类型、枚举、默认值、失败语义如下。

**形式化（JSON schema 要点）**：
```json
{
  "dimension_id": "^[a-z][a-z0-9_]{2,31}$",
  "name": "string",
  "basis": "level_partition|relation_expansion",
  "relation_sources": ["contain(structural)","contain(semantic)","reference","extend", "..."],
  "direction": "down|out|in|both",
  "hop_default": "integer >=0",
  "hop_max": "integer >= hop_default",
  "termination": {"max_hops": "int>=0?", "max_nodes": "int>0?", "fixpoint": "bool", "reasons": ["string"]},
  "status": "reserved|active|deprecated",
  "priority": "integer (仅组合槽位使用)",
  "version": "semver",
  "u_refs": ["U-8", "..."],
  "owner": "string",
  "activation_criteria": "string (仅 reserved)"
}
```
**约束**：
- `dimension_id` 全局唯一；`status=active` 的条目才能被请求；
- `basis=relation_expansion` ⇒ `relation_sources ⊇ E_relation_min`（R-1）；`basis=level_partition` ⇒ `relation_sources=[]` 且 `direction="down"`；
- 每个 active 维度必须有**有限终止**：`termination` 至少含 `max_hops`/`max_nodes`/`fixpoint` 之一，且 `hop_max` 有限；
- `reserved` 维度必须有 `activation_criteria`，不得有渲染分支/默认取景；
- 未知 `dimension_id` ⇒ `DIM_UNKNOWN`，**fail-closed**（不渲染/返回错误，不回退默认）；
- 注册表 content hash/version 必须可复算；新增只追加，不删除历史（审计）。

**机检伪代码**：
```python
def validate_dimension(d, registry, E_MIN):
    errors = []
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", d["dimension_id"]): errors.append("bad id")
    if d["dimension_id"] in {x["dimension_id"] for x in registry if x is not d}: errors.append("duplicate id")
    if d["status"] not in {"reserved","active","deprecated"}: errors.append("bad status")
    if d["basis"] == "relation_expansion":
        if not set(E_MIN) <= set(d["relation_sources"]): errors.append("R-1 violation: relation_sources missing E_relation_min")
        if d["direction"] not in {"out","in","both"}: errors.append("bad direction")
    elif d["basis"] == "level_partition":
        if d["relation_sources"] != []: errors.append("H must not use relation sources")
        if d["direction"] != "down": errors.append("H direction must be down")
    else: errors.append("bad basis")
    if not (isinstance(d["hop_default"], int) and isinstance(d["hop_max"], int)
            and 0 <= d["hop_default"] <= d["hop_max"]): errors.append("bad hop")
    if d["status"] == "active" and not finite_termination(d["termination"]): errors.append("unbounded active dimension")
    if d["status"] == "reserved" and not d.get("activation_criteria"): errors.append("reserved needs criteria")
    return errors
def resolve_dimension(dimension_id, registry):
    d = registry.get(dimension_id)
    if d is None: raise FailClosed("DIM_UNKNOWN")
    if d.status != "active": raise FailClosed("DIM_NOT_ACTIVE")   # reserved/deprecated
    return d
```
**反例**：注册表无该 id 却按默认渲染；reserved 维度被切到 active 但无评审记录；active 维度无 hop_max 且 fixpoint=false（可能无限）；H 把 relation_sources 写成 U-10 关系源（H 不是关系扩展）。
**边界用例**：`hop_max=0`（只当前层）、单节点 focus、空 registry、新维度新增（只追加）、id 大小写/空格拒绝。
**U 映射**：U-9、U-12、U-25、U-30、U-34。
**建议裁决**：冻结注册表 schema + fail-closed + active 必须有限终止 + reserved 无渲染分支。
**证据等级**：A（S0-3/R-1；现有 graphStyle 读取点说明"无维度注册表"）+ PI（字段默认值/上限）。

---

## S1-3 开放槽位登记（U-25）与晋升

**定义/规则**：未实现维度一律登记为 `reserved`；reserved **只登记、不实现、不进 ViewModel/渲染分支**；切换 reserved/未知维度必须 fail-closed（`DIM_NOT_ACTIVE`/`DIM_UNKNOWN`），不得静默回退默认。

**登记格式**：
```
Slot = {slot_id, candidate_name, one_line_definition, u_refs, owner,
        why_not_v1, activation_criteria, status:"reserved", added_in:"S1-v1", version}
```
**晋升规则（机检）**：
1. 新 S1 修订（版本递增）+ Lead 决策（`team/decisions.jsonl`）+ SE 工程校核；
2. 覆盖矩阵补 U 编号；relation_sources 若新增必须符合 S1-6（只增不删 R-1）；
3. active 前必须补：basis/direction/hop/termination/有限终止/机检用例；
4. 代码/配置不得存在 reserved→active 的隐式分支（不得用 `status` 布尔或 feature flag 绕过）。

**机检条件**：
```python
assert all(s.status == "reserved" for s in slots)
assert all(s.activation_criteria for s in slots)
assert not any(render_branch(s.slot_id) for s in slots)      # 无渲染分支
assert not any(s.slot_id in vm for vm in view_models)
```
**反例**：reserved 候选"顺手"接入 UI 下拉框；用 feature flag 让 reserved 维度在 dev 生效并默认打开；晋升不补机检用例；从 reserved 直接写进产品契约。
**边界用例**：reserved 槽位出现在设置页但置灰（允许？S0/U-25 要求先留槽位；建议仅登记在文档/研究层，UI 不出现）；候选被废弃（deprecated）；多个候选共享槽位。
**U 映射**：U-9、U-12、U-25、U-34。
**建议裁决**：冻结登记格式 + fail-closed + 晋升四要件；**v1 UI 不展示 reserved 维度**（避免误实现）。
**证据等级**：C（U-25）+ PI（登记字段/晋升流程）。

---

## S1-4 H（层次维度）精确定义

**定义/规则**：H 是**层次划分的导航取景**：basis=`level_partition`；从当前层块/焦点出发，沿划分的**直接子块**向下一层；`direction=down`；终止于 KP 叶子（`L_max`）；只渲染当前层的块节点与父子包含关系，不把子层成员全部展开（U-5/U-17）。

**形式化**：
```
H(ctx) 输入：(level ℓ, view_family f, focus block B∈Π_{ℓ,f})
输出：当前层节点 = Π_{ℓ,f} 的块（cluster/kp）；焦点 B 的子块 = {B'∈Π_{ℓ+1,f} | B'⊆B}
H 的边 = 派生包含边 (B → B')，必须映射 data_edge_ids（S0 R-3）；不直接读 E_relation_min 作数据边
direction=down；hop_default=1；hop_max=1（H 一次只下一层；层深上限由 S0-2/S1-9 终止）
终止：level L_max（全部 kp）或 hop 用完；无更深层 ⇒ 不再下钻，提示可进入 A/全展开
```
**机检条件**：
```python
assert H.basis == "level_partition" and H.direction == "down"
assert H.relation_sources == []
assert children(focus, level+1) covers focus.members and disjoint  # S0-2 V5
assert all(child.kind in {"cluster","kp"} for child in children)
assert all(edge.data_edge_ids for edge in H.view_edges)           # R-3
assert H.hop_max == 1  # 或 S1 明确允许 1..k？v1 固定一层
```
**反例**：H 一次展开多级（U-5 全展开）；H 使用 `E_relation` 关系源（把 A 维混入 H）；H 的簇→子块边无 `data_edge_ids`；H 终止在非 KP 叶子。
**边界用例**：当前层就是 L_max ⇒ 子节点为空（提示不可下钻）；焦点是单 KP ⇒ 无子块；单成员簇；跨 `view_family` 不共享划分（R-2）。
**U 映射**：U-4、U-5、U-6、U-7、U-8、U-17、U-28。
**建议裁决**：冻结 H = 划分下降一层、direction=down、hop=1、终止 KP 叶子、派生边带 data_edge_ids；H 不使用 E_relation（只做划分包含）。
**证据等级**：A（S0-2/S0-3/R-2/R-3 冻结）+ PI（H hop_max=1 的具体取值）。

---

## S1-5 A（关联维度）精确定义（U-10/U-30）

**定义/规则**：A 是"显示平时不显示的关联节点"的取景：basis=`relation_expansion`；关系源 = `E_relation(A) ⊇ E_relation_min`（U-10：包含关系、引用、语义关联等）；从当前层可见节点/焦点出发，沿这些关系边在跳数预算内挂接；**标签 semantic/structural/navigation 只作显示/语义强度，不作能否挂接的开关**。

**形式化**：
```
E_relation(A) = E_relation_min ∪ additions(D)      # R-1：只增不删
E_relation_min = {contain(structural), contain(semantic), reference, extend}
A 的候选节点 = BFS/DFS over E_relation(A)，按 dir(A)=both（可配）与 hop_budget；
节点集合 = { v | ∃ path focus→v 长度 ≤ hop_budget，边 ∈ E_relation(A) }
挂接边必须带 label（semantic/structural/navigation）+ data_edge_ids（若聚合）
"平常不显示"的判定：节点/边不在当前 H 默认视图中，但通过 A 的关系源可达且通过 present 准入
终止：hop/节点预算/无新节点；跨维切换重置（S0-5）
```
**必须覆盖 U-10 三类**：
1. 包含关系：`contain(structural)` / `contain(semantic)` 都进 `E_relation(A)`；
2. 引用：`reference`；
3. 语义关联：`extend` 等（标签 semantic 仅表示有证据；无证据的 extend 仍可作 navigation 挂接，但不得标 semantic）。
**机检条件**：
```python
assert set(A.relation_sources) >= E_RELATION_MIN
assert "contain(structural)" in A.relation_sources and "contain(semantic)" in A.relation_sources
assert "reference" in A.relation_sources and "extend" in A.relation_sources
# 反例测试：两个 KP 仅由 reference 边相连 ⇒ A 候选包含它（U-10）
# 反例测试：两个 KP 仅由 structural contain 相连 ⇒ A 候选包含它（U-10）
# 反例测试：label=navigation/structural 的边仍可挂接（标签不是开关）
```
**反例**：A 只走 semantic 边（P0-1 重演，U-10 窄化）；把 reference/structural 过滤掉；把 `E_relation(A)` 写成 `label=semantic` 的边集；A 的候选带出端点背后子图（U-17）。
**边界用例**：A 在 KP 层/簇层都可激活；同一对节点多类型边分别计边；一跳节点是 cluster ⇒ 以桥边聚合、不展开内部；A 与 H 互斥（D-5），切 A 后 H 的划分退为背景/面包屑；A 在无关系数据时为空集（不是全展开）。
**U 映射**：U-9、U-10、U-11、U-12、U-15、U-17、U-18、U-30。
**建议裁决**：冻结 A = `E_relation_min + 扩展`（只增）、关系源含 contain 两 kind/reference/extend、标签不参与挂接开关、覆盖 U-10 三类；具体预算/聚合 S4。
**证据等级**：A（S0-3 R-1/U-10 冻结；`reference`/`contain` 现有数据字段）+ R（R-1）。

---

## S1-6 E_relation 扩展规则（R-1：只增不删）

**定义/规则**：`E_relation_min` 是冻结下界；S1 只允许**新增**关系源，不允许删除/重命名/改语义；删除必须重开 S0（记录原因/影响/回滚）。

**新增准入条件（缺一不可）**：
1. **数据承载**：有现有可读字段/边/link/派生源（file:line/schema），不能凭空发明；
2. **可复算**：给定图 + 参数可确定性提取，附最小验证器/样例；
3. **语义分类**：新增源必须声明 label ∈ {semantic, structural, navigation}（或按证据判 label）；
4. **不破坏 H/A 核心**：H 仍不依赖 E_relation；A 的 present/一跳/终止仍可机检；
5. **U 覆盖**：对应的 U 编号/维度候选登记；新增源若用于 reserved 维度，只登记不实现；
6. **审计**：S1 修订版本 + Lead 决策 + 回归用例（原 E_relation_min 的 golden 测试不变）。

**机检条件**：
```python
assert set(E_relation_min) <= set(E_relation(A))     # 只增不删
assert not (set(E_relation_min) - set(E_relation(A))) # 显式断言
# 历史版本对比：
assert set(new.relation_sources) >= set(old.relation_sources)  # 仅追加
assert new.version > old.version and new.u_refs >= old.u_refs
```
**反例**：把 `reference` 从 A 删除（P0-1 复发）；把 `contain(structural)` 改名为 `contain` 并声称等价；新增"相似度"关系但无数据字段；新增后旧 golden 测试改预期（说明删/改）。
**边界用例**：新增 `co_citation`/`embedding_neighbor` 等候选 → 先登记 reserved 维度（S1-15），v1 不激活；新增后 A 候选集只增不减；删除请求 ⇒ `S0_REOPEN_REQUIRED`。
**U 映射**：U-10、U-12、U-25、U-30。
**建议裁决**：冻结 R-1 机检 + 新增五要件 + 删除必须重开 S0；v1 不新增实际关系源（最小集够 U-10）。
**证据等级**：A（S0-3 R-1 冻结）+ C（新增流程）。

---

## S1-7 跳数（U-11；沿边 vs 节点、去重、跨维重置）

**定义/规则**：跳数 = **沿 `E_relation(D)` 的边步数**，不是节点数；`hop_default/hop_max` 是 A 的默认/上限；H 的"跳"= 层次下降的层数（H 固定 1 层/视图）。去重按 canonical node id；多个路径取最短/是否可达即可；**切换维度重置计数**（S0-5）；预算与选择性渲染由 `present` 统一裁决。

**形式化**：
```
hop_budget = clamp(hop_default, 0, hop_max)（运行时可由 ctx/present 限制）
reachable(D, focus, k) = { v | ∃ path focus→v of length ≤ k，边∈E_relation(D)，满足 dir(D) }
hop(v) = min path length；node 只出现一次（canonical id）
H: hop = level 差；H.hop_default=H.hop_max=1
A: hop_default=1；hop_max 由 S4/S9 定上限（v1 建议 ≤2，具体 S4）
跨维：切换 active dimension 时 hop 计数从 0 开始，不继承上一维度
节点预算：与 hop 分开（S1-9）；预算耗尽 ⇒ suppress + rule_id=budget
```
**机检条件**：
```python
assert isinstance(hop_budget, int) and 0 <= hop_budget <= D.hop_max
result = BFS(focus, E_relation(D), dir(D), max_depth=hop_budget)
assert all(dist[v] <= hop_budget for v in result)
assert len({v.id for v in result}) == len(result)       # 去重
assert not (hop_budget == 1 and any(dist[v] == 2 for v in result))  # 无二跳
switch_dimension(); assert current_hop_count == 0       # 跨维重置
```
**反例**：按节点数计跳（把节点预算当跳数）；一跳算出两跳（闭包）；重复节点；切换维度继承 hop 导致超预算；hop_max 无上限。
**边界用例**：hop=0（只看焦点）；hop=1（一跳挂接 S0-5）；多路径同节点（最短路径/去重）；A 无新节点时提前终止（S1-9）；H 到叶子后 hop 不再增加。
**U 映射**：U-10、U-11、U-15、U-18、U-32。
**建议裁决**：冻结沿边计数 + 去重 + hop_default/hop_max + 跨维重置 + 节点预算分离；A 的 hop_max 具体值 S4。
**证据等级**：A（S0-5 冻结：恰好一条/跨维重置）+ PI（A.hop_max 值）。

---

## S1-8 方向 `dir(D)`

**定义/规则**：方向定义**边的可遍历方向**，枚举与 S0 一致：`down | out | in | both`。
- `down`：H 专用，父块→子块（外层→内层）；
- `out`：数据边 source→target；
- `in`：target→source；
- `both`：双向；**同一条边只计一次**（不因双向重复挂接）。
A 的默认 `both`，可按注册表配置 `out/in`（但 v1 推荐 both）；方向只影响可达性/箭头显示，不改变边 label/type。

**形式化**：
```
traverse(e, dir) = 
  dir=="out": (source→target)
  dir=="in":  (target→source)
  dir=="both": both（边只出现一次；节点集合去重）
  dir=="down": 仅 H 的父→子派生边
```
**机检条件**：
```python
assert D.direction in {"down","out","in","both"}
assert (D.basis=="level_partition") == (D.direction=="down")
# both 不重复边：
assert len([e for e in result_edges if e.id == eid]) == 1
# in/out 对反向不可达：
assert reverse_edge not in traverse_out_only
```
**反例**：H 用 both（会把子→父也算一跳）；A 用 in 但 UI 仍画 out 箭头（语义/显示不一致）；both 把同一条边两次计数；方向不写注册表（代码默认双向，两实现歧义）。
**边界用例**：无向 contain 边在 both 下两个方向都可挂接但只计一条；reference 边方向由 source/target 决定；跨层 H 的 down 不允许向上；切换方向需改维度配置（不是 per-view 临时）。
**U 映射**：U-10、U-11、U-15、U-17。
**建议裁决**：冻结 dir 枚举 + H=down + A=both（可配 out/in）+ both 不重复计数。
**证据等级**：A（S0-5 方向/一跳冻结）+ PI（A 默认 both）。

---

## S1-9 终止条件（可机检；有限预算）

**定义/规则**：每次取景必须在有限步内终止；终止条件可组合，但 **active 维度至少有一个有限界**；U-32 的"规模不是问题"指**数据/后端规模**，不是允许无限渲染，仍必须有显示预算。

**形式化**：
```
termination = {max_hops?, max_nodes?, fixpoint: bool, reasons[]}
active 维度要求：max_hops 或 max_nodes 至少一个有限，且 fixpoint 可作为额外提前停
执行：BFS 按层扩展，每步检查：
  (a) hop > hop_max → stop reason=hop_budget
  (b) len(nodes) >= max_nodes → stop reason=node_budget
  (c) no new nodes → stop reason=fixpoint
  (d) H 到 L_max / A 无更多关系边 → stop reason=leaf/no_edges
输出必须记录 termination_reason（对应 present rule_id）
```
**机检条件**：
```python
assert finite_termination(D.termination)  # active
assert all(t in {"hop_budget","node_budget","fixpoint","leaf","no_edges"} for t in reasons)
assert result.termination_reason != None
assert len(result.nodes) <= D.termination.max_nodes (if set)
assert max(hop) <= D.hop_max
# 无界用例必须被 validate_dimension 拒绝
```
**反例**：A 不设 hop_max 且无 fixpoint（可能沿环无限）；"不设上限"被解释成无显示预算；终止原因不记录（无法区分 suppressed/unknown）；预算耗尽却静默丢节点（无 rule_id）。
**边界用例**：hop=0；max_nodes=1；A 图有环（fixpoint 提前停）；H 叶子；预算正好等于节点数；空图。
**U 映射**：U-11、U-18、U-32。
**建议裁决**：冻结"active 必须有限终止 + 终止原因可机检"；数据/检索规模问题交 S9，显示预算 S4/S8。
**证据等级**：A（U-32 原话/S0-6 预算）+ PI（默认数值）。

---

## S1-10 维度组合（D-5：v1 单维度）

**定义/规则**：v1 **同一视图只激活一个维度**（active count=1）；多维度组合只登记 reserved 槽位；组合顺序/优先级/算子**只登记不实现**；切换维度是一次 Presentation/S5 动作，不是同时叠加两维。

**组合槽位格式**：
```
CombinationSlot = {combination_id, dimensions:[dim_id...], composition:"union|intersection|priority",
                   order:[dim_id...], status:"reserved", activation_criteria, version}
```
**切换语义**：
```
switch(from_dim, to_dim):
  assert to_dim.status == "active" and to_dim != from_dim
  reset hop_count/visited/render set
  if focus 在新维度可见 ⇒ 保持 focus；否则映射到包含它的最近 cluster/当前 level 根
  记录 reason（S5）；不合并 from/to 的 present 集合（禁止双真相）
```
**机检条件**：
```python
assert number_of_active_dimensions(vm) == 1
assert not any(c.status != "reserved" for c in combination_slots)
assert no_render_branch(combination_id)
assert switch_resets_hop and no_union_present(from_dim,to_dim)
```
**反例**：v1 同时开 H+A（双主真相）；把组合算子直接写进 present 分支；组合槽位被默认启用；切换不重置跳数。
**边界用例**：两个 active 维度之一被 deprecated；切换目标 reserved ⇒ fail-closed；切换回同维度（no-op）；组合候选登记但不显示。
**U 映射**：U-8、U-9、U-12、U-25、U-34。
**建议裁决**：冻结 v1 单维度 + 组合槽位 reserved + 切换语义（重置/焦点映射/不合并）。
**证据等级**：R（D-5 冻结）。

---

## S1-11 维度状态机与能力闸

**定义/规则**：维度状态机：`reserved → active → deprecated`；**晋升/降级必须有 S1 修订 + Lead 决策 + SE 校核**；未知/保留/废弃维度请求 fail-closed；状态持久化在 Presentation/设置层，**不得进 ViewModel**；插件能力面只能**读/请求**维度，不能私开 reserved。

**状态表**：
| 当前 | 事件 | 目标 | 条件 |
|---|---|---|---|
| reserved | activate | active | S1 修订 + 决策 + 机检用例 + 覆盖矩阵 |
| active | deprecate | deprecated | 决策 + 迁移/回滚 + 兼容说明 |
| reserved | deprecate | deprecated | 决策（不激活） |
| active | reserved | — | 禁止（必须重开 S1） |
| deprecated | active | — | 禁止（必须重开 S1） |
| 任意 | unknown id | fail-closed | `DIM_UNKNOWN` |

**机检条件**：
```python
assert status in {"reserved","active","deprecated"}
assert transition_allowed(old,new)  # 只允许上表
assert unknown_id → FailClosed("DIM_UNKNOWN")
assert reserved/deprecated → FailClosed("DIM_NOT_ACTIVE"/"DIM_DEPRECATED")
assert "dimension_status" not in vm_fields  # 持久化不在 VM
assert plugin_capability_dimensions ⊆ active_dimension_ids
```
**反例**：插件绕过注册表直接启用 reserved；把 active→reserved 当降级（应 deprecated）；状态存在 ViewModel；未知 id 静默回退 H。
**边界用例**：无插件能力时 active 维度仍可用（基础）；插件声明支持某维度但注册表 reserved ⇒ fail-closed；deprecated 维度迁移提示。
**U 映射**：U-9、U-12、U-25、U-34。
**建议裁决**：冻结状态机 + fail-closed + 状态不进 VM + 插件只读 active。
**证据等级**：C（章程/U-25）+ PI（状态迁移细节）。

---

## S1-12 维度与选择性渲染/边存无

**定义/规则**：维度只通过 `ctx.dimension_id` 影响 `present(e, ctx)` 的**候选关系源选择与跳数/终止**；`presence ∈ {shown,suppressed,unknown}` 与 `rule_id` 仍是唯一判据；维度切换使同一对节点的边 presence 可不同（U-27），但**数据边本身不删/不改 type/label**；视图缺席 ≠ 数据缺席。

**形式化**：
```
ctx = ⟨level, view_family, dimension_id, focus, hop_budget, mode⟩
C(ctx) = { e ∈ DataSource.edges | type(e) ∈ E_relation(D) }  # H 用派生包含边
present(e,ctx) = shown | suppressed(rule_id) | unknown(rule_id)
切换 D1→D2：同一 e 的 presence 可变化；e.type/label 不变；DataSource 不变
聚合/折叠边带 data_edge_ids（R-3）；expand_data_edges(VM) ⊆ DataSource.edges
```
**机检条件**：
```python
assert set(C(ctx)) <= DataSource.edges  # 候选来自数据
assert all(e.type == data_type and e.label == data_label for e in edges)  # 不改事实
assert present(e,ctx1) != present(e,ctx2) implies e.id same and data identity same
assert all(suppressed/unknown has rule_id)
assert expand_data_edges(VM) ⊆ DataSource.edges
```
**反例**：切维度时改 `e.type`/删除数据边；视图缺席被读成"关系不存在"；维度导致 `unknown` 被当 absent；H 把 contain 改写成 reference。
**边界用例**：同一对节点多类型边分别 present；A→H 后边 suppressed 有 rule_id；H→A 后重新计算；full_expand 的 ctx 不同但 present 同源（S0）。
**U 映射**：U-10、U-16、U-17、U-27。
**建议裁决**：冻结"维度只改 ctx/E_relation，不改数据事实；present 三值不变；切换可改变 presence 但不改边身份"。
**证据等级**：A（S0-6/S0-3 冻结）+ C（U-27）。

---

## S1-13 维度与 UI/导航契约

**定义/规则**：维度切换入口属于 **Presentation/导航层（S5 状态机）**，不属于 ViewModel/Renderer；ViewModel 只带 `dimension_id` 上下文元数据（S0-9 允许），不带切换状态/模式/历史；Renderer 不发 `dimensionToggle` 事件；S5 负责保存/恢复当前维度、焦点、历史栈。

**形式化**：
```
Presentation/S5: state = ⟨level, dimension_id, focus, history, mode⟩
ViewModel = { view_model_id, level_id, dimension_id, view_family_id, nodes, edges }   # 无 switch/mode/history
Renderer events: nodeClick/edgeClick/backgroundClick；不出现 dimensionToggle
S5 API: setDimension(dimension_id) -> new ctx -> buildViewModel
```
**机检条件**：
```python
assert "dimensionToggle" not in renderer_events
assert "dimension_state" not in vm_fields
assert setDimension 只通过 S5/presentation 层
assert ViewModel.dimension_id in active_dimension_ids
```
**反例**：Renderer 持有当前维度/切换按钮；ViewModel 带 `dimension_switch`/`active_dims`；切维度不经过 S5 导致历史栈丢失。
**边界用例**：切到 reserved ⇒ S5 fail-closed；切到同维度 no-op；切维度后 focus 映射（S1-10）；2D/3D 切换不影响 dimension_id。
**U 映射**：U-8、U-9、U-33（2D/3D 不混入）。
**建议裁决**：冻结切换归 S5/Presentation；VM 只带 dimension_id 元数据；Renderer 无维度事件。
**证据等级**：A（S0-9 D-4 冻结）+ C（S5 接口）。

---

## S1-14 维度与 agent

**定义/规则**：agent 只能通过**确定性取景服务**请求按维度取景：请求参数 = `(dimension_id, level, view_family, focus, hop_budget, node_budget, filters)`；服务 `frame(DataSource, request)` 纯函数（同输入同输出）；agent **不得**直接拼 ViewModel、改渲染状态、改维度状态；未知/保留维度 fail-closed；A 维的 `E_relation` 参数化，agent 不能私扩关系源（只能请求注册表内 active 维度）。

**形式化**：
```
Request = {dimension_id:str, level_id:str, view_family_id:str, focus:kp|cluster,
           hop_budget:int?, node_budget:int?, filters:[...]?}
response = frame(DataSource, request)  # 纯函数：无会话态/无写操作
agent 可调用 S9 检索算法生成 request 参数；不可直接调用 renderer.update / 写 ViewModel
```
**机检条件**：
```python
assert is_pure(frame)                    # 无全局状态/无写
assert request.dimension_id in active_dimension_ids
assert not agent_can_write("view_state"/"view_model"/"renderer")
assert unknown/reserved -> FailClosed
```
**反例**：agent 直接给前端发 ViewModel/改 DOM；agent 请求 3 跳但 hop_max=1 时服务应截断/拒绝，而不是绕过；agent 请求未注册维度；用 agent 会话态影响 frame 输出。
**边界用例**：agent 离线 → 默认 H 基线；agent 请求 H/A 切换；budget 截断；未来 S7 评测接入。
**U 映射**：U-29、U-32。
**建议裁决**：冻结确定性取景服务 + 请求 schema + agent 不改渲染状态；S7/S9 细化。
**证据等级**：A（S0-10 冻结）+ C（S7/S9）。

---

## S1-15 其他维度候选清单（reserved，U-25）

**定义/规则**：未来候选一律登记为 reserved（S1-3 格式），v1 **不实现**；每个候选：一句话定义、U 映射、为何 v1 不做、激活条件。

| slot_id | 候选 | 一句话定义 | U | 为何 v1 不做 | 激活条件 |
|---|---|---|---|---|---|
| `time` | 时间/证据维 | 按 `valid_from/valid_to`/curation 时间取景 | U-12、U-25 | G5 时间轴"只存不用"；无时间查询/正确性证据 | S6 定义时间语义+数据覆盖 |
| `evidence` | 证据/置信维 | 按 provenance/confidence/断言证据强度取景 | U-1、U-12 | `confidence` 仅 L2 后；语义证据覆盖不足 | L2 判据/G6 评测通过 |
| `task` | 任务/agent 上下维 | 按 agent 当前任务/检索上下文取景 | U-9、U-29 | 无任务→图映射/评测；易过度个性化 | S7/S9 接口+评测 |
| `controversy` | 争议/冲突维 | 显示矛盾/未裁决 curation/冲突边 | U-12 | 冲突数据模型未定义 | S6 数据契约+人工协议 |
| `similarity` | 语义相似维 | embedding/近邻扩展（非现有边） | U-10、U-12 | 无冻结嵌入/相似阈值；引入新关系源需 S1-6 | S9 算法+人工抽检 |
| `path` | 路径/链条维 | 沿 prerequisite/链式关系扩展 | U-12、U-22 | v1 无 prerequisite 数据/类型（S0 v1 范围外） | S6/新语义类型准入 |
| `contrast` | 对比/反面维 | 对照/反例关系取景 | U-12 | 新语义类型未准入；数据 0 | v1 语义类型准入三闸 |
| `density` | 结构密度维 | 按簇内聚/桥/度数取景 | U-13 | 属 S2 聚类/视觉，不是维度 | S2 冻结后可登记 |

**机检条件**：
```python
assert all(slot.status == "reserved" for slot in candidates)
assert all(slot.activation_criteria for slot in candidates)
assert not any(slot.slot_id in active_dimension_ids)
assert no_render_branch(slot.slot_id)
```
**反例**：把 `similarity` 在 v1 作为 A 的隐藏扩展（绕过 S1-6）；time 维度直接读未启用字段；候选出现在 UI 默认维度列表。
**边界用例**：多个候选共享同一数据源；某候选被废弃（deprecated）；未来激活走 S1-3 晋升。
**U 映射**：U-9、U-12、U-25、U-30（+U-32）。
**建议裁决**：冻结候选清单为 reserved；v1 不实现；激活走 S1-3 四要件。
**证据等级**：C（U-25/U-12）+ PI（候选取舍）。

---

## 附：S1 对 S0 冻结条款的遵从自检

| S0 条款 | S1 落点 |
|---|---|
| R-1 `E_relation_min` 只增不删 | S1-2/S1-5/S1-6（机检集合包含） |
| R-2 `view_family` 唯一定义/partition | S1-4（H 用 `(level, view_family)`） |
| R-3 聚合边 `data_edge_ids` | S1-4/S1-12 |
| D-4 ViewModel 纯 | S1-1/S1-13（维度切换不进 VM） |
| D-5 v1 单维度 | S1-10（active count=1） |
| `present` 唯一判据 | S1-12 |
| kind ∈ {kp,cluster} | S1-1/S1-4（H 子块 kind） |

> 独立声明：本文件写作时未读 `S1-dimensions-proposal-A.md`（尚未落盘）；差异对照见 `S1-objections.md`，逐项列不合并。
