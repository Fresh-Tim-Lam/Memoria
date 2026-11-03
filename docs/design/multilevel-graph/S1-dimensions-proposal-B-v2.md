# S1 维度体系提案 B-v2（独立复核方修订版）

> **依据（唯一裁决依据）**：`docs/design/multilevel-graph/S1-RULINGS.md`（R-S1-1..R-S1-8）；最高原话 `multilevel-graph-vision.md`（U-1..U-35）；上游冻结 `S0-terms-v1.md`（sha `241b1e1e…`，R-1/R-2/R-3、D-4/D-5 不得违反）。
> **输入**：B v1（sha `9947dd7a…`）、A v1（sha `58d6d4f6…`）、`S1-objections.md`。A-v2 写作时尚未落盘；本文件先独立完成（完成后才对照 A-v2，见 `S1-objections-v2.md`）。
> **性质**：独立复核方修订提案；不覆盖旧版；不写产品代码/契约；未 commit。
> **证据等级**：A=可执行/机检源码；B=冻结数据/实测；C=冻结契约/文档推断；PI=本项目假设；R=S1-RULINGS/S0 冻结。
> **日期**：2026-11-03（Asia/Shanghai）。

---

## 0. B-v2 变更表（相对 B v1；逐条落 R-S1）

| # | 位置 | B v1 | B-v2（依据） | 类型 |
|---|---|---|---|---|
| 1 | S1-2 | 字段简版（无 hop_unit/registry_sha/active set） | 吸收 A：`hop_unit`、`registry_sha`、v1 active 集合固定 `{hierarchy, association}`；增加 `registry_history`（R-S1-3/R-S1-8） | 补字段 |
| 2 | S1-4 | H 用层偏移当 hop；relation_sources=[] | **H `relation_sources=[]`；H 不设 hop（`hop_unit=n/a`）；H 的块→子块派生边带 `data_edge_ids`；S0-5 只约束 A**（R-S1-1/R-S1-2/R-S1-4） | 修正 |
| 3 | S1-6 | 只增断言 `new⊇old`，无历史 schema | 补 **`registry_history` 存储 schema（append-only：version/content_sha/previous_sha/relation_sources）**；跨版本 `new⊇old`；删除/改名 ⇒ `S0_REOPEN_REQUIRED`（R-S1-3） | 新增 |
| 4 | S1-5/S1-7 | A 无显式 hop 口径 | A：`hop_unit=edge`、`hop_default=1`、`hop_max=2`（2 仅显式「新一跳」，U-22）；沿边最短距离/去重/跨维重置（R-S1-5） | 修正 |
| 5 | S1-9 | 终止通用 | H 终止 = KP 叶子/无子块/取消；A = hop/node/fixpoint；均须有限+rule_id；max_nodes 数值归 S8（R-S1-5） | 明确 |
| 6 | S1-8 | 4 枚举（无 up） | 吸收 A：5 枚举 `down/up/both/out/in`；H=down、A=both（可配 out/in）；up 仅保留不激活（R-S1-5） | 并集 |
| 7 | S1-11 | 三态，deprecated→active 禁止直接 | 三态映射；**deprecated→active 只允许经 S1 重开 + registry 版本升级**；插件不得注册/激活/改写（R-S1-6/R-S1-8） | 修正 |
| 8 | S1-14 | agent 无 fallback | **显式 fallback 到默认 H（带 `fallback_reason` 审计）**；registry 可配置禁止 fallback（fail-closed）；不得静默（R-S1-6） | 新增 |
| 9 | S1-15 | 8 候选含 density | 候选改为 `time/evidence/task/controversy/authorship/similarity/path`；**density 移出维度归 S2**；similarity 作派生源须走 S1-6（R-S1-7） | 修正 |
| 10 | S1-12 | 通用 present | H 派生边 `data_edge_ids` + A 的 E_relation；维度只改 presence/ctx，不改事实；切片标签（R-S1-4/S0-6） | 强化 |
| 11 | S1-10 | 组合单维度 | 吸收 A：`DIM_COMBINATION_UNSUPPORTED` + 切换语义；v1 单 active（R-S1-8） | 并集 |
| 12 | S1-1/S1-3 | 定义/槽位 | 吸收 A 的 M1–M6 判定 + 槽位 draft/why_not_v1；v1 不晋升任何 reserved（R-S1-7/R-S1-8） | 并集 |

---

## 0.1 覆盖矩阵（S1 相关 U 全部出现）

| U# | 落点 | U# | 落点 |
|---|---|---|---|
| U-8 | H 定义=S1-4 | U-25 | 开放槽位=S1-3/S1-15 |
| U-9 | 其他维度=S1-2/S1-3/S1-15 | U-27 | 存无/类型=S1-12 |
| U-10 | A 关系源=S1-5/S1-6（E_relation_min） | U-30 | A 定义=S1-5 |
| U-11 | 跳数=S1-7 | U-32 | 规模/检索=S1-9/S1-14 |
| U-12 | 更多维度=S1-3/S1-15 | U-33 | 2D/3D≠维度=S1-1/S1-13 |
| U-4/U-5 | 层次/默认=S1-4 | U-34 | 逐议项=本文件 |
| U-6/U-7 | 簇节点/下钻=S1-4/S1-13 | U-13/U-14 | 簇定义承接 S0-4 |
| U-15/U-17/U-18 | 一跳/背后图/防污染=S1-5/S1-7/S1-9 | U-21/U-31 | 多归属=S1-4/S1-12 |
| U-22 | 新一跳/更深=S1-5/S1-7 | U-26 | 默认/全展开=S1-13 |
| U-28 | 最小粒度=S1-4 | U-29 | agent 设计 KP=S1-14（S10） |

---

## S1-1 维度定义与边界

**定义/规则**：维度 = 同一层次上的**取景规则**：给定 `(DataSource, level, view_family, focus, dimension_id, hop/budget)`，唯一决定取哪些关系源、什么方向、扩展几步、何时停。维度 ≠ 层次、≠ 视觉风格（`graphStyle`）、≠ 全展开（Presentation mode）、≠ 2D/3D（渲染后端）、≠ 边类型。

**判定条件（并集 A 的 M1–M6）**：
```
M1 可计算：同 (DataSource, frame_spec) 输出唯一 ViewModel
M2 非粒度：不改变 level 划分/最小粒度
M3 非风格：不改变视觉 token / graphStyle / 2D/3D
M4 非模式：全展开是 Presentation 正交开关
M5 有注册项：id/status/version；未知 id fail-closed
M6 不改事实：维度只影响视图投影（presence/selection），不写 DataSource/sidecar
```
**机检**：`dimension_id ∉ {graphStyle, 2d, 3d, full_expand, level}`；VM 无维度切换状态；同输入同输出字节一致。
**反例**：graphStyle/2D/3D/full_expand/level 冒充维度；搜索过滤/临时高亮当维度；用维度写回事实。
**边界用例**：H/A 都满足 M1–M6；time 候选满足但仅 reserved；非法 direction fail-closed。
**U 映射**：U-8、U-9、U-10、U-12、U-25、U-33。
**建议裁决**：冻结 M1–M6 + 排除清单；`graphStyle/2D/3D/full_expand/level` 不是维度。
**证据等级**：A（`graph-settings.js:38`、`graph-view-2d.js:617` graphStyle 是视觉风格；S0-3）+ C（M1–M6）。

---

## S1-2 维度注册表 schema（含 hop_unit/registry_sha/active 集合/history）

**定义/规则**：注册表是**版本化配置**（非事实源）；v1 active 集合固定 `{hierarchy, association}`；每个 active 维度字段带类型/枚举/默认/失败语义；未知/保留/弃用 fail-closed；注册表整体有 `registry_sha256`；历史 append-only。

**Schema（要点）**：
```jsonc
{
  "schema": "multilevel-dimension-registry/v2",
  "registry_version": "2.0.0",
  "registry_sha256": "<canonical JSON sha256>",
  "dimensions": [
    {
      "dimension_id": "hierarchy",
      "name": "层次维",
      "kind": "hierarchy_navigation",          // R-S1-8 吸收 A：类别字段
      "basis": {"kind": "level_partition"},
      "relation_sources": [],                 // R-S1-1：H 不参与 E_relation
      "direction": "down",
      "hop_unit": "n/a",                       // R-S1-2：H 无关系 hop
      "hop_default": null, "hop_max": null,
      "termination": {"leaf_required": true, "stop_on_no_new": true, "max_nodes": 200},
      "status": "active", "priority": 10, "version": "1.0.0",
      "definition": "沿层次划分下钻一层，到 KP 叶子终止（U-8/U-28）"
    },
    {
      "dimension_id": "association",
      "name": "关联维",
      "kind": "relation_expansion",
      "basis": {"kind": "relation_expansion"},
      "relation_sources": ["contain(structural)","contain(semantic)","reference","extend"],
      "direction": "both",
      "hop_unit": "edge",
      "hop_default": 1, "hop_max": 2,
      "termination": {"max_nodes": 200, "fixpoint": true, "stop_on_no_new": true},
      "status": "active", "priority": 20, "version": "1.0.0",
      "definition": "沿 E_relation_min 边挂接 ≤hop_max 跳关联节点（U-10/U-11/U-15）"
    },
    {"dimension_id": "time", "basis": {"kind": "reserved"}, "status": "reserved",
     "version": "0.0.0-reserved", "definition": "时间/有效区间取景（v1 不实现）",
     "activation_criteria": "..."}
  ]
}
```
**字段规则**：
- `dimension_id` 唯一、kebab；`name` 可缺省；`kind ∈ {hierarchy_navigation, relation_expansion}` 且与 `basis.kind` 匹配（H⇒level_partition，A⇒relation_expansion）；`basis.kind ∈ {level_partition, relation_expansion, reserved}`；
- `relation_sources`：仅 `basis=relation_expansion` 允许非空且 `⊇ E_relation_min`（R-1 作用域修正）；`basis=level_partition` 必须 `[]`；无 `basis=reserved` 的可执行字段；
- `hop_unit ∈ {n/a, level, edge}`：H=`n/a`；A=`edge`；任何非 n/a 维度必须有 `hop_default/hop_max` 且有限；H **无 hop 字段值**（`hop_default=hop_max=null`，R-S1-2）；
- `termination`：active 必须有有限界（H：leaf_required/stop_on_no_new；A：hop_max/max_nodes/fixpoint 至少一）；
- `status ∈ {reserved,active,deprecated}`；`priority` active 内唯一；`version` semver；`registry_sha256` 可复算。

**校验伪代码**：
```python
MIN = {"contain(structural)","contain(semantic)","reference","extend"}
def validate_registry(reg):
    assert reg["schema"] == "multilevel-dimension-registry/v2"
    assert sha256(canonical_json({k:v for k,v in reg.items() if k!="registry_sha256"})) == reg["registry_sha256"]
    ids = [d["dimension_id"] for d in reg["dimensions"]]
    assert len(ids)==len(set(ids)), "DIM_DUPLICATE"
    for d in reg["dimensions"]:
        assert d["status"] in {"active","reserved","deprecated"}
        if d["status"]=="reserved": continue
        assert d["basis"]["kind"] in {"level_partition","relation_expansion"}
        assert d.get("kind") in {"hierarchy_navigation","relation_expansion"}
        if d["basis"]["kind"]=="relation_expansion":
            assert d["kind"]=="relation_expansion"
            assert MIN <= set(d["relation_sources"]), "DIM_MISSING_MIN"   # R-1 只约束 A
            assert d["hop_unit"]=="edge" and d["direction"] in {"both","out","in"}
            assert finite_termination(d["termination"])
        else:
            assert d["kind"]=="hierarchy_navigation"
            assert d["relation_sources"]==[], "H_MUST_NOT_RELATE"        # R-S1-1
            assert d["direction"]=="down" and d["hop_unit"]=="n/a"
            assert d["hop_default"] is None and d["hop_max"] is None     # R-S1-2
            assert d["termination"].get("leaf_required") is True
    actives=[d for d in reg["dimensions"] if d["status"]=="active"]
    assert {d["dimension_id"] for d in actives} == {"hierarchy","association"}  # v1 fixed
    assert len({d["priority"] for d in actives})==len(actives)
    return validate_history(reg)   # R-S1-3

def resolve_dimension(reg, dimension_id):
    d = next((x for x in reg["dimensions"] if x["dimension_id"]==dimension_id), None)
    if d is None: raise FailClosed("DIM_UNKNOWN")
    if d["status"]!="active": raise FailClosed("DIM_NOT_ACTIVE")
    return d
```
**反例**：H 带 relation_sources（R-S1-1 违反）；H 设 hop；A 缺 min；active 集合变 3 个；未知 id 回退默认；registry_sha 不匹配；未知/保留维度被渲染。
**边界用例**：registry 空/损坏 ⇒ 全局 fail-closed；reserved 只登记；v2 registry 升级只追加；旧 frame 按 edition 解释。
**U 映射**：U-8、U-9、U-10、U-11、U-12、U-25、U-32。
**建议裁决**：冻结 v2 schema + H/A 分工 + active 集合固定 + registry_sha + fail-closed。
**证据等级**：A（S0-3/R-1/D-5；现有 `graph-settings.js:38` 无维度注册表）+ R（R-S1-1/2/5/8）+ PI（字段默认值）。

---

## S1-3 开放槽位登记（U-25）与晋升

**定义/规则**：未实现维度登记为 `reserved`：只登记定义/草案/why_not_v1/activation_criteria；**不得进渲染分支/ctx/frame/ViewModel**；切换 reserved/未知 ⇒ fail-closed；v1 不晋升任何 reserved。

**登记格式**：
```jsonc
{"dimension_id":"time","name":"时间维","basis":{"kind":"reserved"},
 "status":"reserved","version":"0.0.0-reserved",
 "definition":"按 valid_from/valid_to 取景（一句话）",
 "draft":{"relation_sources_draft":[],"direction_draft":"...","hop_draft":"...",
          "termination_draft":"...","evidence_needed":["..."]},
 "why_not_v1":"字段只存不用/无覆盖率", "activation_criteria":"..."}
```
**机检**：
```python
assert all(s["status"]=="reserved" for s in slots)
assert all(s.get("activation_criteria") and s.get("why_not_v1") for s in slots)
assert not any(s["dimension_id"] in active_ids for s in slots)
assert no_render_branch(s["dimension_id"])       # 代码/配置无 reserved 分支
```
**反例**：reserved 出现在设置下拉/默认；`if dim=="time"` 占位实现；未升版本直接 active；用 reserved 作 fallback。
**边界用例**：reserved 草案不参与校验；deprecated 可读历史 ViewModel（不重算）；v1 结束前不晋升。
**U 映射**：U-9、U-12、U-25、U-30。
**建议裁决**：冻结槽位格式 + 晋升四要件（S1 修订/Lead 决策/机检/版本）；v1 不晋升。
**证据等级**：C（U-25）+ R（R-S1-7）+ PI（审批细节）。

---

## S1-4 H（层次维度）精确定义（R-S1-1/2/4）

**定义/规则**：H 是**层次划分的导航取景**：basis=`level_partition`；**不参与关系扩展**（`relation_sources=[]`）；**不设关系 hop**（`hop_unit=n/a`）；一次下钻 = 一层的导航动作（由 S5 推进 focus/level，不是 S0-5 的 hop）；块→子块边是**层次派生边**，必须带 `data_edge_ids` 映射回 DataSource 的 `contain(structural)` 数据边。

**形式化**：
```
H(ctx) 输入：(level ℓ, view_family f, focus block b_ℓ)
H 节点：当前层 Π_{ℓ,f} 的块；focus 的子块 = {b_{ℓ+1}∈Π_{ℓ+1,f} | b_{ℓ+1}⊆b_ℓ}
H 边：派生包含边 (b_ℓ→b_{ℓ+1})，direction=down；
      每条 H 边 data_edge_ids = 该子块成员 KP 对应的 contain(structural) 数据边 id 集（R-S1-4）
H 终止：focus 到 Π_L（KP 叶子）或 children 为空或用户取消
H 无 hop 预算（hop_unit=n/a）；"下钻一层"由 S5 导航动作推进，不参与 S0-5 机检
```
**机检条件**：
```python
assert H.basis.kind=="level_partition" and H.relation_sources==[]      # R-S1-1
assert H.direction=="down" and H.hop_unit=="n/a" and H.hop_default is None and H.hop_max is None  # R-S1-2
assert H.termination.leaf_required is True
assert all(e.data_edge_ids for e in H.view_edges)                      # R-S1-4
assert expand_data_edges(H_vm) <= DataSource.edges                     # R-S1-4/R-3
assert all(child.kind in {"kp","cluster"} for child in children)
assert children(focus,level+1) covers focus.members and disjoint        # S0-2
```
**反例**：H 使用 E_relation 拉跨层节点（R-S1-1 违反）；H 设 hop/闭包；H 派生边无 data_edge_ids；H 一次下钻多层；H 跨 view_family。
**边界用例**：focus 是 KP（叶层）⇒ 无可下钻；focus 无子块 ⇒ fail-closed/unknown（不伪造）；单成员簇；H↔A 切换不改 level/family。
**U 映射**：U-4、U-5、U-6、U-7、U-8、U-17、U-28。
**建议裁决**：冻结 H：`relation_sources=[]`、无 hop、direction=down、一次一层、data_edge_ids；S0-5 只约束 A；H 下钻由 S5。
**证据等级**：A（S0-2/R-2/R-3）+ R（R-S1-1/2/4）+ PI（H 导航细节）。

---

## S1-5 A（关联维度）精确定义（R-S1-5）

**定义/规则**：A 是关系扩展取景：basis=`relation_expansion`；`E_relation(A) ⊇ E_relation_min`（U-10：包含/引用/语义关联）；按 `direction`、`hop_unit=edge`、`hop_default=1`、`hop_max=2` 扩展；**2 跳仅在用户显式「新一跳」（U-22）时使用**，默认 1；标签只作显示/消费准入，不作挂接开关。

**形式化**：
```
E_relation(A) = E_relation_min ∪ additions  # R-1 只增
候选 = { v | ∃ path focus→v, edges∈E_relation(A), dir, length≤hop_budget，v∉V0 }
hop_budget = hop_default（默认1）；显式「新一跳」才允许 2；>2 fail-closed（v1 hop_max=2）
显示节点 = V0 ∪ 候选（去重；最小 hop）
显示边 = 两端可见且 hop≤budget 的 E_relation(A) 边；每条带 label + hop
一跳（S0-5，仅 A）：hop=1 只显示端点+边，不展开背后邻域（U-17/U-18）
```
**U-10 覆盖**：`contain(structural)`、`contain(semantic)`、`reference`、`extend` 全部进 `E_relation(A)`；三类均按边计 1 跳；标签 semantic/structural/navigation 只显示。
**机检条件**：
```python
assert set(A.relation_sources) >= E_RELATION_MIN
assert A.hop_unit=="edge" and A.hop_default==1 and A.hop_max==2
assert all(n.hop<=ctx.hop_budget for n in shown_nodes)
assert hop_budget in {1,2}                    # v1；2 需显式「新一跳」标记
assert no_closure: shown_edges 不含 hop>budget 的边
# 反例测试：仅 reference / 仅 structural contain 连接的两 KP 必须出现在 A 候选（U-10）
```
**反例**：A 只走 semantic（U-10 窄化）；默认 2 跳/闭包；hop>2；标签当挂接开关；A 改变 H 基座/level/family；把 reference 标 semantic。
**边界用例**：hop=0=H 基座；hop=1 默认；用户显式「新一跳」允许 2；同一目标多路径去重；目标是 cluster 只显示节点不展开；无新节点提前终止。
**U 映射**：U-10、U-11、U-15、U-17、U-18、U-19、U-22、U-30。
**建议裁决**：冻结 A = E_relation_min + 扩展（只增）、hop_unit=edge/默认1/最大2、2 跳需显式「新一跳」、方向 both（可配 out/in）、标签不作开关。
**证据等级**：A（S0-3/S0-5/U-10/R-1）+ R（R-S1-5）。

---

## S1-6 E_relation 扩展规则 + `registry_history`（R-S1-3）

**定义/规则**：`E_relation_min` 冻结；S1 只能新增；**跨版本 append-only 必须可机检**；删除/改名任何已冻结源 ⇒ `S0_REOPEN_REQUIRED`（硬失败）。

**新增准入**：数据承载、可复算、分类（edge_type/projection/derived；derived 不得 active）、标签映射（S0-1）、validator/夹具、S1 修订+Lead 决策+版本升级、只增历史。

**`registry_history` schema（append-only）**：
```jsonc
{
  "schema": "multilevel-dimension-registry-history/v1",
  "entries": [
    {"version":"2.0.0","content_sha256":"...","previous_sha256":null,
     "relation_sources":["contain(structural)","contain(semantic)","reference","extend"],
     "active_dimensions":["hierarchy","association"],"decided_by":"..."},
    {"version":"2.1.0","content_sha256":"...","previous_sha256":"<2.0.0 content sha>",
     "relation_sources":["...","co_citation"],"active_dimensions":["hierarchy","association"],
     "decided_by":"..."}
  ]
}
```
**校验伪代码**：
```python
def validate_history(history, current):
    entries = history["entries"]
    assert entries, "HISTORY_EMPTY"
    # append-only：版本递增、previous_sha 串联
    for prev, cur in zip(entries, entries[1:]):
        assert semver_gt(cur["version"], prev["version"]), "HISTORY_VERSION"
        assert cur["previous_sha256"] == prev["content_sha256"], "HISTORY_CHAIN"
        assert set(cur["relation_sources"]) >= set(prev["relation_sources"]), "ERELATION_REMOVED"
        assert set(cur["active_dimensions"]) >= set(prev["active_dimensions"]), "ACTIVE_DIM_REMOVED"
    assert set(current["relation_sources"]) >= set(entries[-1]["relation_sources"])
    # 删除/改名检测：任何已出现源不在新集合 ⇒ 硬失败
    for s in set().union(*[set(e["relation_sources"]) for e in entries]):
        if s not in current["relation_sources"]:
            raise FailClosed("S0_REOPEN_REQUIRED", s)   # R-S1-3
    # 改名视同删除：用 canonical source id 比较，不靠显示名
    return True
```
**触发条件（硬失败）**：
1. 任何历史 `relation_sources` 中的源在当前 registry 缺失/改名；
2. `E_relation_min` 任一源不在当前 active relation_expansion 维度；
3. 历史 `previous_sha256` 断裂/content_sha 不匹配（审计链断裂）；
4. 未经 S1 修订/决策就修改 history/registry version。
**反例**：v2.1 加 `co_citation`，v2.2 删除它仍 ⊇ min ⇒ 本校验必须 FAIL（A v1 validator 会 PASS，P1-2）；改名 `reference`→`link` 当删除；只改显示名但 canonical id 变；history 丢失。
**边界用例**：新增源只在 later version 出现；active 集合不变但 relation_sources 增加；history 为空 ⇒ registry invalid；v1（首个版本）previous_sha=null。
**U 映射**：U-10、U-12、U-25、U-30。
**建议裁决**：冻结 history schema + 跨版本 append-only 断言 + `S0_REOPEN_REQUIRED`；v1 不新增关系源。
**证据等级**：A（S0 R-1）+ R（R-S1-3）+ PI（history 存储格式）。

---

## S1-7 跳数与方向/终止（R-S1-5）

**定义/规则**：
- **A**：hop_unit=edge；`hop_default=1`；`hop_max=2`；2 跳只在显式「新一跳」请求（U-22）；沿边最短距离 + 节点去重；跨维重置为 default；节点预算与 hop 分离。
- **H**：hop_unit=n/a；**无关系 hop**；一次下钻=一层（S5 导航），终止 KP 叶子/无子块/取消。
- 终止必须有穷、确定性、截断带 `rule_id`；`max_nodes` 数值归 S8，S1 只要求字段存在。

**形式化**：
```
A: hop(v)=min{|p| focus→v, edges∈E_relation(A), dir}
   hop_budget = hop_default（默认1）；显式 new_hop=true 才可为 2；>2 fail-closed
   跨维切换 ⇒ hop=新维度 hop_default（重置）
H: 无 hop；children/focus 层推进由 S5；终止 leaf/no_children/cancel
共同: termination_reason ∈ {leaf,no_children,hop_budget,node_budget,fixpoint,cancel}
     max_nodes 超限 ⇒ presence=suppressed + rule_id=node.budget
```
**机检**：
```python
assert A.hop_unit=="edge" and A.hop_default==1 and A.hop_max==2
assert hop_budget in {1,2}; if hop_budget==2: assert ctx.new_hop is True
assert all(dist[v]<=hop_budget); assert node ids unique
assert H.hop_unit=="n/a" and H.hop_default==H.hop_max==0
assert termination_reason is not None and finite
switch_dimension(); assert frame.hop == target_registry.hop_default
```
**反例**：H 设 hop/闭包；A 默认 2 跳；hop 按节点数计；跨维继承 hop；无界；截断无 rule_id。
**边界用例**：hop=0/1/2；显式新一跳；多路径去重；H 叶层；max_nodes 截断。
**U 映射**：U-10、U-11、U-15、U-18、U-22、U-32。
**建议裁决**：冻结 A hop 口径（1 默认/2 显式）、H 无 hop、跨维重置、终止有穷+rule_id。
**证据等级**：A（S0-5/U-22/U-32）+ R（R-S1-5）。

---

## S1-8 方向 `dir(D)`

**定义/规则**：枚举 `{down, up, both, out, in}`；H=down；A=both（可配 out/in）；`up` 仅保留不激活（v1 无 active 使用）；方向只影响取景，不改边事实/类型/label。

**枚举语义**：down=父→子（H 派生边）；up=子→父（保留）；both/out/in=数据边双向/正向/反向。A both 下同一事实边只出现一次（不重复计数）；反向邻居在 out 下不可见。
**机检**：`direction` 枚举合法；H=down；A∈{both,out,in}；不改变 edge source/target；H 视图无 up 边；A both 同一 edge id 只出现一次。
**反例**：H both/up；A out 却显示反向；方向写回数据；非法方向静默默认。
**边界用例**：同 pair 多类型边；H 叶层；未知方向 fail-closed。
**U 映射**：U-10、U-11、U-15、U-30。
**建议裁决**：冻结 5 枚举 + H down/A both + up reserved + 方向不改事实。
**证据等级**：A（S0-5）+ R（R-S1-5）。

---

## S1-9 终止条件

**定义/规则**：
- H：终止 = 到 KP 叶子 / 无子块 / 用户取消；无 hop 预算。
- A：终止 = hop_max / max_nodes / frontier 空（fixpoint）/ 用户取消；必须有穷。
- 任何截断必须 presence=suppressed/unknown + rule_id；不得静默丢边。

**机检**：active 维度 finite；H leaf_required/stop_on_no_new；A max_nodes+hop_max；termination_reason 可枚举；同输入同输出；`max_nodes` 存在但数值 S8。
**反例**：无界 BFS；静默截断；H 无限下钻；同输入不同输出。
**边界用例**：max_nodes 恰好满；frontier 空；H 叶层；取消。
**U 映射**：U-11、U-18、U-22、U-32。
**建议裁决**：冻结终止并集 + 有限预算 + rule_id；H 无 hop 终止；A hop/node/fixpoint。
**证据等级**：A（U-32/S0-6）+ R（R-S1-5）。

---

## S1-10 维度组合（D-5）

**定义/规则**：v1 单 active 维度；组合只登记 reserved；ctx 出现组合参数 ⇒ `DIM_COMBINATION_UNSUPPORTED`；切换维度 = 新 frame（S5），hop 重置；ViewModel 无维度列表。
**组合槽位格式**：`{combination_id, dimension_ids[], order[], composition_rule:"reserved", status:"reserved", activation_criteria}`
**机检**：active count=1；ctx 无 dimension_list/combination_id；组合槽位 reserved 且无渲染分支；ViewModel 无列表。
**反例**：H+A 同时激活；组合优先级偷加预算；组合槽位进渲染。
**边界用例**：切换 H↔A；组合需求登记；v1 不晋升。
**U 映射**：U-8、U-9、U-12、U-25、U-30、U-34。
**建议裁决**：冻结 v1 单维度 + `DIM_COMBINATION_UNSUPPORTED` + 切换语义。
**证据等级**：A（S0 D-5）+ R（R-S1-8）。

---

## S1-11 状态机与能力闸（R-S1-6）

**定义/规则**：状态 `{reserved, active, deprecated}`；`deprecated→active` **只允许经 S1 重开 + registry 版本升级**；插件不得注册/激活/改写维度；未知/保留/弃用 fail-closed；registry 是产品配置（非插件、非事实源）并只读加载 + `registry_sha` 校验。

**状态机**：
| 当前 | 事件 | 目标 | 条件 |
|---|---|---|---|
| reserved | promote | active | S1 修订 + Lead 决策 + 机检 + 版本升级 |
| active | deprecate | deprecated | 决策 + 替代/迁移说明 |
| deprecated | reopen | active | **重开 S1 + Lead 决策 + registry 版本升级**（R-S1-6） |
| active | →reserved | — | 禁止（只能 deprecate） |
| 任意 | unknown/reserved/deprecated 请求 | — | fail-closed |
**机检**：状态枚举/转移表；未知 id `DIM_UNKNOWN`/保留 `DIM_NOT_ACTIVE`；deprecated→active 必须有 S1 reopen 记录；插件无 registry 写权限；VM 无维度状态。
**反例**：插件自激活；deprecated 静默复活；registry 状态写产品事实源；未知 id 回退。
**边界用例**：registry 损坏 ⇒ 全局 fail-closed；旧 frame 用旧 registry edition；v1 只有 H/A active。
**U 映射**：U-9、U-12、U-25、U-33、U-34。
**建议裁决**：冻结三态 + 重开规则 + 插件禁写 + registry 只读配置。
**证据等级**：A（S0-11/U-25；`plugins.py` 声明无执行代码）+ R（R-S1-6）。

---

## S1-12 维度与 present/选择性渲染

**定义/规则**：维度通过 `ctx.dimension_id` 进入 `present(e,ctx)`：A 用 `E_relation(A)`；H 用层次派生边（带 `data_edge_ids`，R-S1-4）。维度只改变 presence/ctx，不改边 type/label/DataSource；presence 三值 + rule_id 仍是唯一判据；视图缺席 ≠ 数据缺席（U-27）。

**形式化**：
```
A shown(e) ⇔ e∈E_relation(A) ∧ 端点在 ≤hop 路径 ∧ dir 合法 ∧ 预算内
H shown(e) ⇔ e 是 focus 块→子块派生边（data_edge_ids 映射 contain structural）
suppressed/unknown ⇒ rule_id（hop.budget/node.budget/cluster.folded/source.unavailable 等）
切换维度：同一 e 的 presence 可变，type/label/data identity 不变
```
**机检**：
```python
assert all(H_view.edges[e].data_edge_ids for e in shown H edges)
assert expand_data_edges(VM) <= DataSource.edges
assert presence != shown implies rule_id
assert same e across H/A: base_type/contain_kind/label unchanged
```
**反例**：H 派生边无 data_edge_ids；维度改 type；切换维度删除数据边；无 rule_id 静默丢边。
**边界用例**：同 pair 多类型边；折叠边 suppressed+data_edge_ids；预算耗尽；源不可用 unknown。
**U 映射**：U-10、U-16、U-17、U-27。
**建议裁决**：冻结维度只改 presence/selection；H 派生边 data_edge_ids；A 用 E_relation；类型不变；rule_id 可枚举。
**证据等级**：A（S0-6/R-3）+ R（R-S1-4）。

---

## S1-13 维度与 UI/导航契约

**定义/规则**：维度切换属 Presentation/S5；ViewModel 只带 `dimension_id` 标签，不含 mode/nav/history/capabilities；Renderer 无维度切换事件；S5 保存当前维度/焦点/历史，切换生成新 frame。
**机检**：VM 无切换/状态字段；Renderer 事件无 dimensionToggle；切换只改 frame.dimension_id；切换后 hop=目标 hop_default。
**反例**：ViewModel 带维度列表/模式；Renderer 处理切换；切换丢焦点无提示。
**边界用例**：H↔A；reserved 目标 fail-closed；全展开与维度正交；2D/3D 切换不改维度。
**U 映射**：U-7、U-8、U-9、U-25、U-33。
**建议裁决**：冻结切换归 S5/Presentation；VM 只带 dimension_id；Renderer 无维度事件。
**证据等级**：A（S0-9/D-4）+ C（S5 接口）。

---

## S1-14 维度与 agent（fallback 显式+审计）

**定义/规则**：agent 只能请求确定性取景服务：`frame(DataSource, frame_spec)` 纯函数；请求带 active `dimension_id` 与参数；agent 不能注册/激活维度、不能改渲染状态/拼 ViewModel；未知/保留/弃用 fail-closed；**允许显式 fallback 到默认 H，但必须带 `fallback_reason` 审计，registry 可配置禁止 fallback**。

**形式化**：
```
frame_spec = {level_id, view_family_id, dimension_id, focus_id, hop_budget, new_hop?, fallback?}
agent 允许：只读 DataSource/registry；调用 frame；提议 frame_spec
agent 禁止：写 registry/status/version；写 ViewModel/presence；改渲染/导航
fallback：仅显式 fallback=true；输出/审计含 fallback_reason；默认 fail-closed；registry.fallback_allowed=false ⇒ 拒绝
错误码：DIM_UNKNOWN/DIM_NOT_ACTIVE/DIM_COMBINATION_UNSUPPORTED/FALLBACK_DISABLED
审计：{dimension_id, hop, focus, registry_sha, fallback_reason?, status}
```
**机检**：frame 纯函数；请求 dimension active；fallback 必须显式+reason；fallback_allowed=false 时拒绝；agent 无写接口；审计字段完整。
**反例**：agent 静默 fallback；agent 用 reserved；agent 拼 ViewModel；同请求两次不同。
**边界用例**：agent 请求 hop=2 需 `new_hop=true`；registry 不可用 ⇒ fail-closed；跨 KB 拒绝。
**U 映射**：U-2、U-29、U-32、U-35。
**建议裁决**：冻结确定性服务 + active 白名单 + 显式 fallback+审计 + registry 可禁 fallback；S7/S9 细化。
**证据等级**：A（S0-10/S0-8）+ R（R-S1-6）。

---

## S1-15 其他维度候选清单（reserved；density 移出）

**定义/规则**：v1 只登记 reserved 候选：`time/evidence/task/controversy/authorship/similarity/path`；`density` 归 S2 簇算法参数，**不是维度**；`similarity` 若作派生关系源必须先走 S1-6 分类（derived 不得进 active）；v1 不晋升任何 reserved。

| id | 一句话定义 | 类别/说明 | 为何 v1 不做 |
|---|---|---|---|
| time | 按 valid_from/valid_to 取景 | 时间轴 | 字段只存不用；无覆盖率/机检口径 |
| evidence | 按断言证据强度/类型取景 | 证据 | 与 semantic 标签重叠；T3 消费准入未定 |
| task | 按 agent 任务上下文取景 | 任务 | 非持久/隐私/不可复算；S7/S9 |
| controversy | 按争议/裁决状态取景 | 研究争议 | 研究产物不得成为产品事实 |
| authorship | 按作者/标注者取景 | 审计身份 | 覆盖不全/隐私 |
| similarity | 相似/近邻扩展（派生关系源） | 派生源 | 需 S1-6 分类、S9 算法、人工抽检；v1 不 active |
| path | 路径/链条扩展（prerequisite 等） | 新语义类型 | 无类型/数据；S0 v1 范围外，需准入 |

**机检**：reserved 集合含上述 7 个；无 density 维度；similarity 不得出现在 active A 的 relation_sources（除非 S1-6 通过）；reserved 不进渲染。
**反例**：density 作为维度；similarity 直接 active；候选进设置默认。
**边界用例**：候选可作 UI filter（另行评审）而非维度；v1 不晋升。
**U 映射**：U-9、U-12、U-25、U-30。
**建议裁决**：冻结 7 个 reserved；density→S2；similarity 走 S1-6；v1 不晋升。
**证据等级**：C（U-25/U-12）+ R（R-S1-7）。

---

## 附：B-v2 对 R-S1 自检

| 裁决 | B-v2 落位 |
|---|---|
| R-S1-1 H relation_sources=[] | S1-2/S1-4（校验 `H_MUST_NOT_RELATE`） |
| R-S1-2 H 无 hop/S0-5 只约束 A | S1-4/S1-7（hop_unit=n/a） |
| R-S1-3 registry_history + S0_REOPEN_REQUIRED | S1-6（history schema + 跨版本断言） |
| R-S1-4 H data_edge_ids | S1-4/S1-12 |
| R-S1-5 A hop 1/2、方向、终止 | S1-5/S1-7/S1-8/S1-9 |
| R-S1-6 三态/deprecated→active/插件禁入/fallback 审计 | S1-11/S1-14 |
| R-S1-7 候选 7 个/density→S2/similarity 走 S1-6 | S1-15 |
| R-S1-8 吸收 A 的 hop_unit/registry_sha/active set/H/状态机 | S1-2/S1-4/S1-11 |

> 独立声明：B-v2 先于 A-v2 完成（A-v2 落盘后才对照）；差异与判断见 `S1-objections-v2.md`；未写产品代码/契约，未 commit。
