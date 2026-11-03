# S1 提案 A-v2：维度体系（H 层次导航 / A 关系扩展 / 开放槽位）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-298｜**日期**：2026-11-03（Asia/Shanghai）
> **唯一修订依据**：`docs/design/multilevel-graph/S1-RULINGS.md`（R-S1-1..R-S1-8；Lead 已逐条复核 P1）。
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35）。
> **上游冻结**：`S0-terms-v1.md`（sha `241b1e1e…`）+ `S0-FREEZE-RECORD.md`（不得违反）。
> **关系**：本文件是 **A 的修订版**；**不覆盖** `S1-dimensions-proposal-A.md`（v1，sha `58d6d4f6…`），保留审计链。
> **纪律**：不写产品代码、不改 S0 冻结稿/契约、不 commit；独立写，不照抄 B。

---

## 0. 修订摘要（R-S1 → 结构变化）

| 裁决 | v1 问题 | v2 落实 |
|---|---|---|
| **R-S1-1** H 不参与关系扩展 | v1 要求 H `relation_sources ⊇ E_relation_min`，同一 reference 上下文边出现三种结论（不唯一） | `H.relation_sources=[]`；H 只产**层次派生边**（块→子块），不挂接关系邻居；R-1 只约束**关系扩展维度**（v1=A） |
| **R-S1-2** 一跳只约束 A | v1 给 H 设 `hop_unit=level`，与 S0-5「恰好一条 E_relation(D) 边」冲突 | H `hop_unit=n/a`、无 hop 预算；一次下钻=一层；S0-5 仅约束 A |
| **R-S1-3** 只增不删跨版本机检 | v1 validator 只查当前 ⊇min，删历史源可静默 PASS | 冻结 `registry_history`（append-only，`version/content_sha/previous_sha`）；跨版本断言 `set(new.relation_sources) ⊇ set(old.relation_sources)`；删/改名 ⇒ `S0_REOPEN_REQUIRED` |
| **R-S1-4** H 派生边身份 | v1 H 边无 `data_edge_ids`（违反 S0 R-3） | H 每条派生边带 `data_edge_ids`，映射回 DataSource 的 `contain(structural)` 边 |
| **R-S1-5** v1 hop 口径 | v1 未把「2 跳仅显式新一跳」写死 | A：`hop_unit=edge, hop_default=1, hop_max=2`（可配 1..2；2 仅显式「新一跳」）；沿边最短距离+去重；跨维重置；终止有穷/确定性/截断带 rule_id；`max_nodes` 数值归 S8 |
| **R-S1-6** 状态机/fallback | v1 deprecated→active 未写"只能重开"；fallback 未明确 | 三态；deprecated→active 只经 S1 重开+registry 版本；agent fallback 显式+审计（`fallback_reason`），registry 可配禁止 fallback；插件不得注册/激活/改写维度 |
| **R-S1-7** 候选覆盖 | v1 仅 5 个候选，缺 similarity/path；density 未排除 | reserved：`time/evidence/task/controversy/authorship/similarity/path`；`density` 归 S2 非维度；similarity 作派生源须走 S1-6；v1 不晋升 |
| **R-S1-8** 并集 | — | 吸收 B 的 `registry_history`、H `data_edge_ids`、候选覆盖；统一 deprecated/fallback 表述、`DIM_COMBINATION_UNSUPPORTED` 与切换语义 |

**数据流三段（S0 冻结）**：`DataSource → ViewModel（纯） → Renderer（2D/3D）`；维度只进入 `present(e,ctx)`，维度切换属 Presentation（S5）。

**证据等级**：A（原话/冻结契约/裁决/可复跑代码事实）；B（单源实测产物）；C（单源推理）；**本项目假设**（无独立证据的显式约定）。

---

## 1. S1-1 维度定义与边界（新增维度类别）

**定义/规则（一句话）**：维度是**取景规则**；v1 有两类：**层次导航维度 H**（沿层次划分下钻，`relation_sources=[]`）与**关系扩展维度 A**（沿关系边挂接邻居，`relation_sources ⊇ E_relation_min`）；维度不是粒度、不是视觉风格、不是全展开。

**判定条件**：
```
M1 可计算：给定 (DataSource, frame_spec) 唯一确定 ViewModel（同输入同输出）
M2 非粒度：不改变 level 划分/最小粒度（S0-2）
M3 非风格：不改渲染 token；graphStyle/2D/3D 不是维度
M4 非模式：全展开是 Presentation 正交开关（S0-8）
M5 有注册项：registry entry（id/status/version/kind）；未知 fail-closed
M6 不改事实：只影响视图投影，不写 DataSource/sidecar
类别由 basis.kind 决定：
  level_partition      ⇒ 层次导航维度（H）；relation_sources = []；hop_unit = n/a
  relation_neighborhood⇒ 关系扩展维度（A）；relation_sources ⊇ E_relation_min；hop_unit = edge
```
**机检条件**：
```
- 每个维度 entry 有 kind ∈ {hierarchy_navigation, relation_expansion}，且 kind 与 basis.kind 匹配
- H：relation_sources == []；hop_unit == "n/a"；direction == "down"（R-S1-1/R-S1-2）
- A：relation_sources ⊇ E_relation_min；hop_unit == "edge"；1 ≤ hop_default ≤ hop_max ≤ 2
- ViewModel.dimension_id ∈ active 集合；graphStyle/2D/3D/mode 不是 dimension_id
- 同一 (DataSource, frame_spec) 两次输出一致；维度不改 type/label/DataSource（M1/M6）
```
**反例**：graphStyle 当维度；2D/3D 当维度；全展开当维度；level 当维度；H 挂接 reference/extend 邻居（越界，见 R-S1-1）。**边界**：H 的块→子块边是**层次派生边**（非 E_relation）；A 才做关系扩展；未来"既下钻又挂接"的新维度必须重开 S1 并明确类别。

**U 映射**：U-8、U-9、U-10、U-12、U-25。

**建议裁决**：采纳两类维度定义；H 不参与关系扩展；A 覆盖 U-10；`graphStyle/2D/3D/全展开/level` 排除。

**证据等级**：A（R-S1-1 `S1-RULINGS.md:23-27`；S0-3 `S0-terms-v1.md:35-41`；`graph-view-2d.js:617`、`graph-settings.js:38`）；**本项目假设**（M1–M6 清单、basis.kind 作为类别判别）。

---

## 2. S1-2 维度注册表 schema + registry_history（R-S1-1/3/6）

**定义/规则（一句话）**：注册表是版本化配置（非事实源）；条目按类别声明取景规则；**历史 append-only 且跨版本只增不删**；未知/保留/弃用 fail-closed。

**Schema（v2）**：
```jsonc
{
  "schema": "multilevel-dimension-registry/v2",
  "registry_version": "2.0.0",
  "registry_sha256": "<当前 canonical JSON sha256>",
  "history": [                                  // append-only（R-S1-3）
    { "version": "1.0.0", "content_sha256": "<旧内容 sha>", "previous_sha256": null, "decision_id": "..." },
    { "version": "2.0.0", "content_sha256": "<本内容 sha>", "previous_sha256": "<1.0.0 sha>", "decision_id": "..." }
  ],
  "dimensions": [
    {
      "dimension_id": "hierarchy",
      "name": "层次维",
      "kind": "hierarchy_navigation",            // enum: hierarchy_navigation | relation_expansion
      "basis": { "kind": "level_partition" },
      "relation_sources": [],                    // R-S1-1：H 不做关系扩展
      "direction": "down",
      "hop_unit": "n/a",                         // R-S1-2：H 无关系跳
      "hop_default": null,
      "hop_max": null,
      "termination": { "max_nodes": 200, "leaf_required": true, "stop_on_no_new": true },
      "status": "active",
      "priority": 10,
      "version": "1.0.0",
      "definition": "沿层次划分逐层下钻到 KP 叶子（U-8/U-28）；块→子块派生边带 data_edge_ids"
    },
    {
      "dimension_id": "association",
      "name": "关联维",
      "kind": "relation_expansion",
      "basis": { "kind": "relation_neighborhood" },
      "relation_sources": [                      // ⊇ E_relation_min（R-1，只约束本类）
        "contain(structural)", "contain(semantic)", "reference", "extend"
      ],
      "direction": "both",
      "hop_unit": "edge",
      "hop_default": 1,
      "hop_max": 2,                              // v1 可配 1..2；2 仅显式「新一跳」
      "termination": { "max_nodes": 200, "leaf_required": false, "stop_on_no_new": true },
      "status": "active",
      "priority": 20,
      "version": "1.0.0",
      "definition": "沿 E_relation_min 边挂接 ≤hop 跳关联节点（U-10/U-11/U-15）"
    },
    {
      "dimension_id": "time",
      "name": "时间维",
      "kind": "relation_expansion",              // 候选草案（未实现）
      "basis": { "kind": "reserved" },
      "relation_sources": [],
      "status": "reserved",
      "version": "0.0.0-reserved",
      "definition": "按 valid_from/valid_to 取景（U-25；v1 不实现）"
    }
  ]
}
```

**字段/类型/失败语义（增量）**：

| 字段 | 规则 |
|---|---|
| `kind` | `hierarchy_navigation` \| `relation_expansion`；必须与 basis.kind 匹配，否则 `DIM_KIND_MISMATCH` |
| `relation_sources` | hierarchy_navigation **必须 = []**（R-S1-1）；relation_expansion active **必须 ⊇ E_relation_min** |
| `hop_unit`/`hop_default`/`hop_max` | H：`n/a`+null+null（R-S1-2）；A：`edge`+int+int（1..2，default 1） |
| `termination.max_nodes` | 必填 positive int；**数值由 S8 冻结**，S1 只要求存在与截断语义（示例 200 非规范） |
| `history` | append-only 数组；每条 `version/content_sha256/previous_sha256/decision_id`；`history[-1].content_sha256 == registry_sha256` |
| `status` | `{reserved,active,deprecated}` |
| `version` | semver；active 改动必须升版本并追加 history |

**校验伪代码（v2，含跨版本只增）**：
```python
MIN = {"contain(structural)", "contain(semantic)", "reference", "extend"}  # R-1 冻结

def validate_registry(reg, previous_registry=None):
    assert reg["schema"] == "multilevel-dimension-registry/v2"
    hist = reg["history"]
    assert hist and hist[-1]["content_sha256"] == reg["registry_sha256"]
    for i, h in enumerate(hist):
        assert set(h) >= {"version", "content_sha256", "previous_sha256"}
        if i > 0:
            assert h["previous_sha256"] == hist[i-1]["content_sha256"], "DIM_HISTORY_CHAIN"
    ids = [d["dimension_id"] for d in reg["dimensions"]]
    assert len(ids) == len(set(ids)), "DIM_DUPLICATE"
    for d in reg["dimensions"]:
        assert d["kind"] in {"hierarchy_navigation", "relation_expansion"}, "DIM_KIND"
        if d["kind"] == "hierarchy_navigation":
            assert d["basis"]["kind"] == "level_partition", "DIM_KIND_MISMATCH"
            assert d["relation_sources"] == [], "DIM_H_RELATION_MUST_BE_EMPTY"      # R-S1-1
            assert d["hop_unit"] == "n/a" and d["hop_default"] is None and d["hop_max"] is None, "DIM_H_NO_HOP"  # R-S1-2
            assert d["direction"] == "down", "DIM_H_DIRECTION"
            assert d["termination"]["leaf_required"] is True, "DIM_H_LEAF"
        else:
            assert d["basis"]["kind"] == "relation_neighborhood", "DIM_KIND_MISMATCH"
            assert MIN <= set(d["relation_sources"]), "DIM_MISSING_MIN"                # R-1（仅本类）
            assert d["hop_unit"] == "edge" and 1 <= d["hop_default"] <= d["hop_max"] <= 2, "DIM_A_HOP"  # R-S1-5
            assert d["direction"] in {"both", "out", "in"}, "DIM_A_DIRECTION"
        assert d["termination"]["max_nodes"] > 0, "DIM_BUDGET"
        # 历史/跨版本只增（R-S1-3）
        if previous_registry is not None:
            old = source_union(previous_registry)     # 旧 active relation_expansion 的 relation_sources 并集
            new = source_union(reg)
            assert new >= old, "S1_RELATION_SOURCE_REMOVED"        # 删除/改名 ⇒ 见下
    assert {d["dimension_id"] for d in reg["dimensions"] if d["status"]=="active"} == {"hierarchy","association"}, "DIM_ACTIVE_SET"
    return {"ok": True, "sha256": sha256(canonical_json(reg))}

def source_union(reg):
    return {s for d in reg["dimensions"] if d["kind"]=="relation_expansion" for s in d["relation_sources"]}

# 删除/改名：source 名称从历史 union 中消失（或对应 dimension_id 改名）：
#   raise FailClosed("S0_REOPEN_REQUIRED", detail)
```
**机检条件**：
```
- validate_registry 通过：schema/version/ids/kind/hop/termination/status/priority（§2 伪代码）
- history 链：history[-1].content_sha256 == registry_sha256；previous_sha256 逐条匹配
- 跨版本：source_union(new) ⊇ source_union(old)；删除/改名 ⇒ S0_REOPEN_REQUIRED
- H relation_sources == []；H hop 全 null；A relation_sources ⊇ min
- active 集合 v1 == {hierarchy, association}
```
**fail-closed 反例（≥3）**：
1. 未知 `dimension_id` ⇒ `DIM_UNKNOWN`；reserved/deprecated 被 ctx 引用 ⇒ `DIM_NOT_ACTIVE`。
2. H 出现 `relation_sources` 非空（如 `["reference"]`）⇒ `DIM_H_RELATION_MUST_BE_EMPTY`。
3. H 设置 `hop_unit="level"`/hop 非 null ⇒ `DIM_H_NO_HOP`（R-S1-2）。
4. relation_expansion 缺 `E_relation_min` 中任一项 ⇒ `DIM_MISSING_MIN`（R-1）。
5. 新 registry 删除/改名历史源（如删 `reference`）⇒ `S0_REOPEN_REQUIRED`（R-S1-3）。
6. history 链断裂（`previous_sha256` 不匹配）或末条 sha≠当前 ⇒ `DIM_HISTORY_CHAIN`。
7. A `hop_default=3`/`hop_max=3`（v1 超出 1..2）⇒ `DIM_A_HOP`。

**反例/边界**：注册表空/缺 history ⇒ invalid；history 只增（旧版本保留可读）；reserved 条目无 relation_sources/无 hop；active 集合 v1 固定 `{hierarchy, association}`。

**U 映射**：U-8、U-9、U-10、U-12、U-25。

**建议裁决**：采纳 schema v2 + registry_history + 三类硬失败；R-1 断言限定 `kind=relation_expansion`；H `relation_sources=[]`；`max_nodes` 数值留 S8。

**证据等级**：A（R-S1-1/3 `S1-RULINGS.md:23-47`；S0-3/R-1；`ENGINEERING-PLAN.md:149-153,290,343-345`）；**本项目假设**（`kind` 字段、history 字段形状、schema v2 命名）。

---

## 3. S1-3 开放槽位登记（U-25；R-S1-7）

**定义/规则（一句话）**：reserved 只登记定义/草案/why_not_v1，不得进入渲染分支；晋升 active 必须重开 S1 + registry 版本追加 history；v1 不晋升任何 reserved。

**登记格式**：
```jsonc
{
  "dimension_id": "similarity",
  "name": "相似度维",
  "kind": "relation_expansion",
  "basis": { "kind": "reserved" },
  "relation_sources": [],
  "status": "reserved",
  "version": "0.0.0-reserved",
  "definition": "按向量/共引相似度取景（U-25；v1 不实现）",
  "draft": { "relation_sources_draft": ["derived:embedding_neighbor"], "direction_draft": "both",
             "hop_draft": 1, "termination_draft": "S8", "evidence_needed": ["S1-6 分类", "S9 评测"],
             "why_not_v1": "派生相似是研究判断，不得进 active（S1-6 derived）" }
}
```
**规则**：
```
R1 reserved 不得被 ctx/frame 引用（DIM_NOT_ACTIVE）
R2 不得有渲染分支（代码/配置不得 if dim==<reserved>）
R3 draft 只作文档，不参与校验/取景
R4 晋升（全部满足）：定义/机检/反例/边界/证据等级齐全；M1 可计算；关系源过 S1-6 准入；
   S1 修订 + Lead 裁决（涉契约需人批）；registry version 升 minor + history 追加
R5 只增不删：维度 id 不可改名/删除；淘汰只能 deprecated（且 deprecated→active 只能重开 S1）
R6 similarity 若作为派生关系源，必须先按 S1-6 分类（derived 不得进 active）；density 不登记为维度（归 S2）
```
**反例**：`time` 出现在设置开关；reserved 当 fallback；未升版本静默改 reserved→active；把 `density` 登记为维度（应归 S2 簇算法参数）。**边界**：reserved 可无关系源/hop；deprecated 可读旧 ViewModel 但不重算；槽位数量不设上限。

**U 映射**：U-9、U-12、U-25、U-30。

**建议裁决**：采纳登记格式 + 晋升/只增规则；候选清单见 S1-15；v1 不晋升。

**证据等级**：A（U-25；R-S1-7 `S1-RULINGS.md:54-57`；S0-3）；**本项目假设**（晋升审批链、draft 字段）。

---

## 4. S1-4 H（层次维度）精确定义（R-S1-1/2/4）

**定义/规则（一句话）**：H 是**层次导航维度**：在当前 `(level, view_family)` 的划分上沿 `contain(structural)` 下钻**一层**；`relation_sources=[]`、不挂接关系邻居、无 hop 预算；块→子块派生边带 `data_edge_ids`。

**形式化**：
```
H.kind = hierarchy_navigation
H.basis = {kind: level_partition}
H.relation_sources = []                          # R-S1-1：不参与关系扩展
H 输入：frame(level ℓ, view_family f, focus block b_ℓ, drill=1 次)
H 节点：children(b_ℓ) = { b_{ℓ+1} ∈ Π_{ℓ+1,f} | b_{ℓ+1} ⊆ b_ℓ }（一次下钻一层）
H 派生边：e_H = (b_ℓ → b_{ℓ+1})，label=structural
   e_H.data_edge_ids = [ canonical_id(contain(structural)) ... ]   # R-S1-4/R-3
   （映射到 DataSource 中对应 outer→inner 的 contain(structural) 边）
H 终止：children=∅（到达 Π_L 单 KP）/ 无子块 / 用户取消
H 无 hop：hop_unit="n/a"；hop_default=hop_max=null；一次下钻=一层（R-S1-2）
H 不是关系扩展：不显示 reference/extend/contain(semantic) 带来的邻居；若它们的两端恰好
   已在当前层可见，**也不由 H 渲染**（避免 v1 的三种结论；需要时由 A 或 S3/S4 另行设计）
```
**机检条件**：
```
- H.relation_sources == []（registry validator）
- H.hop_unit == "n/a" ∧ hop_default/hop_max == null（DIM_H_NO_HOP）
- 每条 H 派生边 data_edge_ids 非空，且 expand_data_edges(H_vm) ⊆ DataSource.edges（R-3）
- data_edge_ids 对应的 DataSource 边均为 type=contain ∧ contain_kind=structural
- H 视图节点只来自 children(focus)，不出现关系邻居节点
- 到 Π_L 后无 cluster 节点（S0-2 V4）
- H 无 hop 字段参与 present；下钻动作由 S5 导航（新 frame），不是 hop_budget
```
**反例**：
- ✗ H `relation_sources` 非空 / 通过 H 显示一条 reference 邻居（R-S1-1 禁止）。
- ✗ H 设置 `hop_unit=level`/hop_budget（与 S0-5 冲突，R-S1-2）。
- ✗ H 派生边无 `data_edge_ids` 或映射到 semantic contain（R-S1-4）。
- ✗ H 一次下钻多层（一次一层；多层由 S5 连续动作）。
- ✗ H 跨 view_family 下钻（应通过 S5/多归属）。

**边界用例**：
- focus 为叶 KP：H 视图=该 KP；无子块终止。
- 无子块/数据缺失：presence=unknown + rule_id，不伪造。
- H 与 A 切换：H 保持 level/family；A 扩展可见节点（S1-13）。
- H 派生边多条映射到同一 DataSource contain 边：`data_edge_ids` 去重并可枚举。
- H 的块→子块边若跨多个原始 contain 边（折叠），`data_edge_ids` 携带全部（R-3）。

**U 映射**：U-4、U-5、U-7、U-8、U-28。

**建议裁决**：采纳 H 定义；H 不参与关系扩展、无 hop、派生边带 data_edge_ids；S0-5 一跳只约束 A。

**证据等级**：A（R-S1-1/2/4 `S1-RULINGS.md:23-47`；S0-2/S0-5/R-3；`ENGINEERING-PLAN.md:229-247` 的 data_edge_ids）；**本项目假设**（H 派生边 label=structural 的显示约定）。

---

## 5. S1-5 A（关联维度）精确定义（U-10/U-30；R-S1-5）

**定义/规则（一句话）**：A 是**关系扩展维度**：从当前视图节点出发，沿 `E_relation(A) ⊇ E_relation_min` 按方向挂接 ≤hop 的关联节点（U-10：包含/引用/语义关联都算，每条边=1 跳）；v1 `hop_default=1/hop_max=2`，2 跳仅在用户显式「新一跳」时使用。

**形式化**：
```
A.kind = relation_expansion
A.relation_sources ⊇ E_relation_min = {contain(structural), contain(semantic), reference, extend}
E_relation(A) = DataSource 中 type ∈ relation_sources 的边（label 只作显示/消费，不影响挂接）
输入：base view V0（H 当前层）、focus F、dir(A)、hop_budget ∈ {1,2}
候选：BFS 从 F 出发，沿 E_relation(A)/dir，最短边数 ≤ hop_budget 到达的节点（∉V0）
显示节点：V0 ∪ 候选（按 id 去重，取最小 hop）
显示边：E_relation(A) 中两端点均显示且位于 BFS 邻接/路径的边；每条边带 hop
一跳（S0-5，仅约束 A）：hop=1 时只显示端点+这条边，不展开背后（U-17）
2 跳：仅当用户显式触发「新一跳」（U-22），预算 hop_budget=2；默认不自动 2 跳
跨维：切换维度后 hop 重置为目标维度 default（R-S1-5）
```
**U-10 覆盖表（保持 v1）**：contain(structural/semantic)、reference、extend 每类每条边=1 跳；label 不参与挂接决策。

**机检条件**：
```
- A.relation_sources ⊇ E_relation_min（R-1，仅 relation_expansion）
- hop_unit=="edge"、hop_default==1、1≤hop_max≤2（v1）
- 所有 shown 节点/边 hop ≤ hop_budget ≤ hop_max
- 节点 id 唯一；边 canonical id 唯一；无 hop>budget 的 shown 元素
- hop=1 视图无第 2 跳边（S0-5）
- 切换维度后 frame 的 hop==目标 default
```
**反例**：只走 semantic；2 跳自动；节点去重失败；跨维保留 hop；不去重同 pair 多类型边；hop_max>2（v1 超范围）。

**边界用例**：同 pair 多类型边分别显示；目标 cluster 不展开（U-17）；hop=0=H 基座；无新节点提前终止；hop_budget=2 仍逐跳预算驱动。

**U 映射**：U-10、U-11、U-15、U-17、U-18、U-19、U-22、U-30。

**建议裁决**：采纳 A；hop_default=1/hop_max=2（2 显式）；沿边最短+去重+跨维重置；S0-5 一跳只约束 A。

**证据等级**：A（R-S1-5 `S1-RULINGS.md:43-47`；S0-3/R-1；S0-5）；**本项目假设**（hop_max 可配 1..2 的 v1 取值）。

---

## 6. S1-6 E_relation 扩展规则（R-1 + R-S1-3 跨版本机检）

**定义/规则（一句话）**：`E_relation` 是关系扩展维度可用的关系源集合；**冻结下界 `E_relation_min` 只增不删**，由 `registry_history` 跨版本机检；删除/改名任何已冻结源 ⇒ `S0_REOPEN_REQUIRED`。

**分类**（同 v1；明确相似度归属）：
| 类别 | 例子 | v1 | 要求 |
|---|---|---|---|
| `edge_type` | contain(structural/semantic)/reference/extend | ✅ 已在 min | 不得新增产品类型（S0-11 #6） |
| `projection` | 未来 raw links 投影等 | 条件 | 只读、canonical id、不写事实、validator |
| `derived` | co-citation/embedding/similarity | ❌ v1 | 标 research_only；须 S1-6 分类 + 证据 + S1 修订；不得进 active |
**新增准入（E1–E7，v2 增加跨版本）**：
```
E1 稳定 canonical id；E2 只读；E3 分类明确（similarity 默认 derived）；
E4 label 映射沿用 S0-1（不得绕过 G_sem）；
E5 validator+测试夹具；E6 S1 修订+Lead（涉契约人批）+registry version+history 追加；
E7 新源加入后：新 registry 的 source_union ⊇ 旧 source_union（R-S1-3 断言）；
   新增只影响 relation_expansion 维度，不得改变 H（H.relation_sources=[]）
删除/改名：source 从历史 union 消失 ⇒ validator 抛 S0_REOPEN_REQUIRED（硬失败）
```
**反例**：删 `reference` 静默通过（v1 bug）；改名 `extend`→`extends`；把 similarity 直接加入 active A（derived）；新增源不写 history；新增源改变 H 的行为。**边界**：projection 与已有 edge 重叠按 canonical id 去重；derived 只可作研究/评估输入；历史版本保留可读。

**U 映射**：U-9、U-10、U-12、U-25、U-30、U-32。

**建议裁决**：采纳 E1–E7 + `S0_REOPEN_REQUIRED`；v1 不新增源；similarity 若产品化须走 derived 分类且不得进 active。

**证据等级**：A（R-S1-3 `S1-RULINGS.md:33-38`；S0 R-1：`S0-terms-v1.md:38`；S0-11 #6；`edge_types.py:9-17`）；**本项目假设**（E1–E7 细节）。

---

## 7. S1-7 跳数（U-11；R-S1-2/5）

**定义/规则（一句话）**：**A** 的跳数沿关系边计（最短距离、节点去重、跨维重置为 default）；**H 无关系跳**（`hop_unit=n/a`，一次下钻=一层，属导航动作，S0-5 不适用）。

**形式化**：
```
A: hop(v) = min{|p| : p 为 F→v 的关系边路径，每条∈E_relation(A)，方向符合 dir}
   hop_default=1；hop_max=2；hop_budget∈{1,2}；2 仅显式「新一跳」
   节点按 id 去重（保留最小 hop）；边按 canonical id 去重；同 pair 多类型边可并存
H: hop_unit=n/a；hop_default=hop_max=null；一次下钻=一层；
   连续下钻=连续导航 frame（S5），不是 hop_budget 递增
共同：跨维重置为 default；越预算截断 ⇒ presence=suppressed + rule_id
     （A: hop.budget/node.budget；H: level.leaf/no_child/cancelled）
```
**机检**：A 的 shown 元素 hop ≤ hop_budget；H 不存在 hop 字段参与取景；H 的下钻次数由 S5 frame 历史计，不进 ViewModel；同输入确定性。**反例**：H 用 level-hop 预算（P1-3）；A 自动 2 跳；跨维不重置；按节点数计跳。**边界**：hop=0=A 基座；H 叶层终止；预算截断可解释。

**U 映射**：U-11、U-15、U-18、U-22。

**建议裁决**：采纳"仅 A 有 hop、H 无 hop"；A 值 1/2；跨维重置；截断 rule_id；`max_nodes` 数值归 S8。

**证据等级**：A（R-S1-2/R-S1-5 `S1-RULINGS.md:29-46`；S0-5）；**本项目假设**（H 下钻次数由 S5 记录的实现细节）。

---

## 8. S1-8 方向 `dir(D)`（R-S1-5）

**定义/规则（一句话）**：方向枚举 `{down,up,both,out,in}` 决定取景遍历方向；H 固定 `down`，A 默认 `both`（可配 out/in）；方向只影响选择，不改事实/类型。

**枚举/约束**：H=down（validator 强制）；A ∈ {both,out,in}（v1 active A=both）；up 保留（未来/导航），v1 无 active 使用；非法/不匹配 fail-closed。方向与 hop：每跳按 dir 走一条边；反向边仍显示原始 source→target（视觉由 S3）；方向不改 label/type。**机检条件**：
```
- direction ∈ {down,up,both,out,in}；H=down；A∈{both,out,in}；非法 fail-closed
- 方向只影响选择：同一 DataSource/focus 下边 type/source/target 不变
- H 视图无 up 方向边；A out/in 视图反向邻居不可见
```
**反例**：H both；out/in 翻转事实；未知方向默认；方向当标签开关。**边界**：A both 同 pair 不因方向重复；out 反向不可见需显式切 both；H 无子终止。

**U 映射**：U-10、U-11、U-15、U-30。**建议裁决**：同上。**证据等级**：A（R-S1-5 `S1-RULINGS.md:47`；S0-5）；**本项目假设**（up 的保留语义）。

---

## 9. S1-9 终止条件（R-S1-5）

**定义/规则（一句话）**：A 终止于 hop 预算/节点预算/无新节点/取消；H 终止于 KP 叶子/无子块/取消；终止必须有穷、确定性、截断带 `rule_id`；`max_nodes` 字段必填但数值归 S8。

**形式化/机检**：
```
A terminate ⇔ frontier=∅ ∨ hop≥hop_budget ∨ nodes≥max_nodes ∨ cancelled
H terminate ⇔ children=∅ ∨ focus∈Π_L ∨ cancelled
共同：visited 集合 + 有穷 hop/max_nodes（H 无 hop）⇒ 必然停机；
      输出 size≤max_nodes；截断候选 presence∈{suppressed,unknown}+rule_id 可枚举；
      同输入两次输出一致
```
**反例**：无界 BFS；H 用 hop 终止；"看起来够了"；静默丢 frontier；max_nodes=null/∞；同输入不同输出。**边界**：预算恰好；frontier 空；H 叶层；取消 rule_id=cancelled。**U 映射**：U-11、U-18、U-22、U-32。**建议裁决**：采纳；max_nodes 数值 S8，字段 S1 必须存在。**证据等级**：A（R-S1-5 `S1-RULINGS.md:45-46`；S0-6）；**本项目假设**（终止清单）。

---

## 10. S1-10 维度组合（D-5；R-S1-8 统一）

**定义/规则（一句话）**：v1 单维度激活；组合只登记 reserved；`ctx` 出现组合参数统一返回 `DIM_COMBINATION_UNSUPPORTED`；切换维度=新 frame（S5）。

**形式化**：`VIEW_FRAME.dimension_id` 单值；组合槽位 `{combination_id,dimension_ids[],order[],composition_rule:"reserved",status:"reserved"}`；v1 校验拒绝组合参数；切换后 hop：H→无、A→default。**机检条件**：
```
- ctx 只允许单个 dimension_id；出现 combination_id/dimension_list ⇒ DIM_COMBINATION_UNSUPPORTED
- active 集合 == {hierarchy, association}；组合槽位 status=reserved 且无渲染分支
- ViewModel 无组合字段/维度列表（D-4）
```
**反例**：同时激活 H+A；组合叠加预算；ViewModel 带组合；组合槽位进渲染分支。**边界**：需求用两次切换；晋升需 S1 修订+S6a 字段扩展；顺序只登记。**U 映射**：U-8、U-9、U-12、U-25、U-30。**建议裁决**：采纳。**证据等级**：A（S0 D-5；`ENGINEERING-PLAN.md:217,276`；R-S1-8 统一表述）；**本项目假设**（组合槽位字段）。

---

## 11. S1-11 状态机与能力闸（R-S1-6）

**定义/规则（一句话）**：维度状态 `{reserved,active,deprecated}`；`deprecated→active` **只能重开 S1 + registry 版本升级 + history 追加**；插件不得注册/激活/改写维度；未知/保留/弃用 fail-closed。

**状态机/规则**：
```
reserved --promote(S1 修订+审批+version+history)--> active
active   --deprecate(替代方案/决策)--> deprecated
deprecated --reactivate(只允许 S1 重开 + registry 版本 + history)--> active
active   --(禁止 delete/rename)--> 只能 deprecate（id 不可变）
未知状态/非法转移 ⇒ registry invalid（fail-closed）
registry_history append-only；跨版本 source_union 只增（R-S1-3）
插件：v1 能力面无维度提供者；插件声明不得新增/激活/改写维度；registry 是产品配置非插件面
```
**机检**：状态枚举；deprecated 不在 active 集合；deprecated→active 必须带 S1 重开决策 id+version+history；插件清单不含 dimension 注册能力；reserved/deprecated 无渲染分支。**反例**：静默复活 deprecated；插件自激活；registry 被插件写；删除/改名 active 维度。**边界**：缺 registry 全局 fail-closed；旧 frame 用旧 edition；frozen 作为 active 版本属性（C-5 映射）。**U 映射**：U-9、U-12、U-25、U-33。**建议裁决**：采纳三态+重开规则；插件禁注册；`{reserved,active,deprecated}` 为唯一枚举。**证据等级**：A（R-S1-6 `S1-RULINGS.md:49-52`；`ENGINEERING-PLAN.md:290`；`plugins.py:1-35`）；**本项目假设**（历史/审批字段）。

---

## 12. S1-12 维度与选择性渲染/边存无（present；R-S1-1/4）

**定义/规则（一句话）**：维度经 `ctx.dimension_id` 进入 `present(e,ctx)`；**H 的派生边不是 E_relation 边**，其存在由 H 取景决定并带 `data_edge_ids`；A 的边由 `E_relation(A)` 候选决定；维度只改 presence，不改 type/label/事实。

**形式化**：
```
presence(e,ctx) ∈ {shown,suppressed,unknown}；render={e|presence==shown}
H: e_H=(block→child) 为派生边（label=structural）
   shown ⇔ 是 focus 的直接子块派生边；data_edge_ids 非空且 ⊆ DataSource(contain(structural))
   suppressed/unknown：无子块/数据缺失/取消（rule_id: level.leaf/no_child/cancelled）
   H 不产生 E_relation 邻居边
A: candidate(e) ⇔ e.type∈relation_sources(A) ∧ 端点/路径在预算内
   shown ⇔ 在 ≤hop 的 E_relation(A) 路径上 ∧ 方向符合 ∧ 预算内
   suppressed: rule_id dim.direction/hop.budget/node.budget
   unknown: source.unavailable/dim.unresolved
共同：R-3 expand_data_edges(VM) ⊆ DataSource.edges；shown(default)⊆shown(full)；
    类型/标签不因维度改变（U-27）；维度 fail-closed 时整体构建失败
```
**机检条件**：
```
- H 派生边 data_edge_ids 非空且 expand_data_edges(H_vm) ⊆ DataSource.edges（R-3/R-S1-4）
- data_edge_ids 对应边 type=contain ∧ contain_kind=structural
- H 不产生 E_relation 邻居边；A 的 shown 元素 hop ≤ budget
- presence==shown 集合 == 渲染集合；suppressed/unknown 有 rule_id
- 维度切换只改 presence，不改变 type/contain_kind/label（U-27）
```
**反例**：H 边映射不到 contain(structural)；H 出现关系邻居；A 改写 reference→semantic；无 rule_id 静默丢边；维度过滤删 DataSource 边。**边界**：H 折叠多 contain 边→data_edge_ids 多条；A 同 pair 多类型；hop 截断；unknown 不渲染。**U 映射**：U-10、U-16、U-17、U-27、U-30。**建议裁决**：采纳 present 集成；H 派生边 data_edge_ids 强制；A 关系候选；类型不变。**证据等级**：A（R-S1-1/4 `S1-RULINGS.md:23-47`；S0-6/R-3；`schema.json` contain_kind）；**本项目假设**（H/A 的 rule_id 枚举）。

---

## 13. S1-13 维度与 UI/导航契约（R-S1-2/D-4）

**定义/规则（一句话）**：维度切换属 Presentation/S5（新 VIEW_FRAME）；H 的下钻是**导航动作**（一次一层，无 hop），A 切换后 hop 重置 default；ViewModel 只含 `dimension_id` 标签，不含控件/列表/历史/模式。

**形式化**：Presentation 控件→S5 `switch_dimension(target)`；S5 更新 nav state、新 frame、H drill 由 `push_nav_frame`（一次一层）、A hop=default；ViewModel 字段仅 dimension_id/level_id/view_family_id；Renderer 只吃 VM、事件 nodeClick/edgeClick/backgroundClick；维度切换失败（reserved/deprecated/unknown）显式错误。**机检条件**：
```
- ViewModel 无 mode/nav/breadcrumb/capabilities（D-4）
- Renderer 事件仅 nodeClick/edgeClick/backgroundClick；无维度切换事件
- 维度切换只改 VIEW_FRAME.dimension_id；H 下钻由 S5 新 frame（无 hop）；A 切换后 hop=default
```
**反例**：VM 带维度列表/历史；渲染器内切换；H 用 hop 表达下钻；静默丢 focus。**边界**：H→A 保持 level/family；A→H 清挂接；reserved 切换失败提示；全展开与维度正交。**U 映射**：U-7、U-8、U-9、U-25、U-33、U-34。**建议裁决**：采纳。**证据等级**：A（R-S1-2；S0-9/D-4；`ENGINEERING-PLAN.md:217,276`）；**本项目假设**（switch_dimension 签名）。

---

## 14. S1-14 维度与 agent（R-S1-6/8）

**定义/规则（一句话）**：agent 只能请求确定性取景服务并指定 active `dimension_id`；fallback 必须**显式**并带审计（`fallback_reason`），registry 可配置**禁止 fallback**（则 fail-closed）；agent 不得写 registry/ViewModel/渲染状态。

**形式化**：
```
frame(DataSource, frame_spec) -> ViewModel | FailClosed
错误：DIM_UNKNOWN / DIM_NOT_ACTIVE / DIM_COMBINATION_UNSUPPORTED
fallback：默认允许显式 fallback 到 H，需带 fallback_reason 审计；
          registry.fallback_policy ∈ {allow_explicit, forbidden}；forbidden ⇒ 直接错误
agent 禁止：写 registry/status/history；写 VM/presence；改渲染/导航；注册维度
确定性：同 (DataSource, frame_spec, registry_sha) ⇒ 同 VM
审计：{dimension_id, hop, focus, registry_sha, status, fallback_reason?}
```
**机检条件**：
```
- frame() 纯函数：同 (DataSource, frame_spec, registry_sha) 输出相同
- 请求维度必须 active；reserved/deprecated/unknown ⇒ 错误码
- fallback：仅 allow_explicit 时允许且带 fallback_reason 审计；forbidden 时直接错误
- agent 无可写 registry/ViewModel/presence 接口（allowlist）
```
**反例**：静默 fallback；fallback 不审计；forbidden 时仍 fallback；agent 写 registry；未知维度猜测。**边界**：A hop=2 需显式请求；H 深层由 S5/连续 frame；registry 坏→错误；跨 KB 拒绝。**U 映射**：U-2、U-29、U-32、U-35。**建议裁决**：采纳显式 fallback+审计+可禁止；agent 只读服务。**证据等级**：A（R-S1-6 `S1-RULINGS.md:49-52`；S0-10；`ENGINEERING-PLAN.md:301-303`）；**本项目假设**（frame 签名/审计字段）。

---

## 15. S1-15 其他维度候选清单（R-S1-7）

**定义/规则（一句话）**：v1 只登记 7 个候选为 reserved（time/evidence/task/controversy/authorship/similarity/path）；`density` 归 S2 非维度；v1 不晋升；similarity 作派生源须走 S1-6。

| id | 一句话定义 | 草案 basis | 草案关系源 | 为何 v1 不做 |
|---|---|---|---|---|
| `time` | 按 KP/边有效时间取景 | time_axis | 现有边+时间字段 | `valid_from/to` 只存不用（ontology §2.2）；无覆盖率/判定口径 |
| `evidence` | 按证据强度/类型取景 | provenance_evidence | edge provenance | 与 semantic/structural 标签重叠；T3 准入未定（S7/S8） |
| `task` | 按 agent 任务上下文取景 | task_context | session/task 派生 | 任务上下文非持久事实、隐私、不可复算 |
| `controversy` | 按 L2/G2 争议/裁决取景 | research_dispute | 研究判定产物 | 研究侧产物不得成为产品事实 |
| `authorship` | 按作者/标注者取景 | authorship | 审计身份字段 | 身份覆盖不全、隐私、无 v1 消费 |
| `similarity` | 按向量/共引相似度取景 | similarity_neighborhood | `derived:embedding_neighbor`/co-citation | 派生判断；须 S1-6 分类（derived 不得进 active）；无评测 |
| `path` | 按两节点间路径取景（链/路径视图） | path_traversal | E_relation 组合 | 与 A 的 hop 关系、路径枚举复杂度/去重未定义（S4/S9） |
- **规则**：全部 reserved（definition+draft+why_not_v1）；不得有可执行 basis/hop/relation_sources（除草案）；不得进渲染分支；v1 不晋升。`density` 不登记（S2 簇算法参数，非维度）。similarity 若未来晋升：必须先作为 `derived` 关系源过 S1-6 分类与 E1–E7，再作为维度晋升（两步都需 S1 修订）。
**机检条件**：
```
- reserved ids 集合 == {time, evidence, task, controversy, authorship, similarity, path}
- active 集合 == {hierarchy, association}；reserved/deprecated 无渲染分支
- density 不出现为 dimension_id（归 S2）
- similarity 若出现在 relation_sources 必须是 derived 且 status 非 active
- v1 无 reserved→active 晋升记录（history 未新增）
```
**反例**：实现 time 维度；把 evidence 当第二套 semantic；用 similarity 派生源进 active；把 density 登记为维度；path 维度直接复用 A hop 却不定义去重。**边界**：reserved 可无关系源；晋升两步；槽位数量不限。**U 映射**：U-9、U-12、U-25、U-30。**建议裁决**：采纳 7 槽位；v1 不晋升；density→S2；similarity 走 S1-6。**证据等级**：A（R-S1-7 `S1-RULINGS.md:54-57`；U-25；ontology §2.2）；**本项目假设**（候选草案/why_not_v1）。

---

## 16. 覆盖矩阵（U + S0 条款）

### 16.1 U 覆盖

| U# | 要点 | S1 落点 |
|---|---|---|
| U-8 | 层次维度 | S1-1/S1-2/S1-4 |
| U-9 | 其他维度 | S1-2/S1-3/S1-15 |
| U-10 | 关联维度（包含/引用/语义关联） | S1-5/S1-6 |
| U-11 | 跳数 | S1-5/S1-7 |
| U-12 | 更多维度 | S1-3/S1-15 |
| U-25 | 开放槽位 | S1-3/S1-15 |
| U-30 | 关联维度具体定义 | S1-5 |
| U-32 | 规模/后端检索 | S1-9/S1-14 |
| U-33 | 2D/3D 不分家 | S1-1/S1-13 |
| U-34 | 逐议项/不设上限 | 本文逐项 + S1-9 预算说明 |

### 16.2 S0 条款一致性

| S0 条款 | S1 落实 | 检查 |
|---|---|---|
| S0-2 层次/partition | S1-4（H） | H 不改 partition；一次一层 |
| S0-3 维度/E_relation/R-1 | S1-2/S1-5/S1-6 | R-1 只约束 relation_expansion（A）；H relation_sources=[] |
| S0-5 一跳/方向 | S1-5/S1-7/S1-8 | 一跳只约束 A；H 无 hop（R-S1-2） |
| S0-6 present/R-3 | S1-12 | H 派生边 data_edge_ids；A 关系候选 |
| S0-7 多归属 | S1-3/S1-5 | 维度不定义 membership/不写事实 |
| S0-8 默认/全展开 | S1-13 | 模式属 Presentation |
| S0-9 VM 纯度/kind | S1-13 | VM 只含 dimension_id |
| S0-10 agent | S1-14 | 显式 fallback+审计/可禁止 |
| S0-11 v1 范围外 | S1-6/S1-15 | 不加类型/不晋升 reserved |
| R-1/R-2/R-3 | S1-2/S1-6/S1-12 | 跨版本只增 + H data_edge_ids |
| D-4/D-5 | S1-13/S1-10 | VM 纯度/单维度 |

---

## 17. A-v2 变更表（逐条旧→新，含 v1 行号）

> 旧文件：`S1-dimensions-proposal-A.md`（v1 sha `58d6d4f6…`）；行号可 grep 复核。

| # | 旧（v1） | 新（v2） | 裁决 |
|---|---|---|---|
| 1 | S1-1（v1 L34）未分维度类别；H/A 都按 relation_sources 描述 | 新增 `kind ∈ {hierarchy_navigation, relation_expansion}`；H 不参与关系扩展（§1/§2） | R-S1-1 |
| 2 | S1-2（L76）schema 缺 history；H 要求 ⊇min | schema v2 + `history`；H `relation_sources=[]`；R-1 断言改为"active 的 relation_expansion ⊇ min"（§2） | R-S1-1/3 |
| 3 | S1-2/L88-110 示例 H relation_sources=min | H `relation_sources=[]`、hop n/a/null；A 保持 min+hop=edge（§2） | R-S1-1/2 |
| 4 | S1-2 validator 只查当前 ⊇min（v1 L161-200） | 加跨版本 `source_union(new) ⊇ old`、history 链、`S0_REOPEN_REQUIRED`（§2） | R-S1-3 |
| 5 | S1-3（L213）5 个候选、无 similarity/path、density 未排除 | 7 个候选；density→S2；similarity 走 S1-6；v1 不晋升（§3/§15） | R-S1-7 |
| 6 | S1-4（L270）H 有 relation_sources⊇min、hop=level | H relation_sources=[]、hop_unit=n/a、一次一层；派生边带 `data_edge_ids`（§4） | R-S1-1/2/4 |
| 7 | S1-5（L319）hop_max=2 未写"仅显式新一跳" | 明确 hop_default=1/hop_max=2、2 仅显式「新一跳」；最短+去重+重置（§5） | R-S1-5 |
| 8 | S1-6（L377）无跨版本/删除硬失败 | 加 E7 跨版本断言、`S0_REOPEN_REQUIRED`、similarity 归 derived（§6） | R-S1-3/7 |
| 9 | S1-7（L426）H 有 level-hop | H 无 hop（n/a）；A 口径写死；max_nodes 数值 S8（§7） | R-S1-2/5 |
| 10 | S1-8（L469）方向未变 | 保持枚举；H=down/A=both（可配 out/in）（§8） | R-S1-5 |
| 11 | S1-9（L516）H 用 hop 终止 | H 终止=叶子/无子/取消；max_nodes 字段存在、数值 S8（§9） | R-S1-2/5 |
| 12 | S1-10（L561）组合未统一错误码 | 统一 `DIM_COMBINATION_UNSUPPORTED` 与切换语义（§10） | R-S1-8 |
| 13 | S1-11（L607）deprecated→active 未写只能重开 | 写死只经 S1 重开+version+history；插件禁注册；registry_history（§11） | R-S1-6 |
| 14 | S1-12（L652）H 边未要求 data_edge_ids、H 可能出关系邻居 | H 派生边 data_edge_ids 强制；H 不出关系邻居；A 候选明确（§12） | R-S1-1/4 |
| 15 | S1-13（L706）H 下钻表示为 hop | H 下钻=导航动作（S5 连续 frame），无 hop；A hop 重置（§13） | R-S1-2 |
| 16 | S1-14（L747）fallback 未规定审计/可禁止 | 显式 fallback+`fallback_reason`；registry `fallback_policy` 可 forbidden（§14） | R-S1-6 |
| 17 | S1-15（L798）候选清单 | 7 槽位；density/similarity 归属（§15） | R-S1-7 |
| 18 | 覆盖矩阵 §16（L835） | 更新 U/S0 与 H/A 分工（§16） | 本轮 |

---

## 18. 仍存争议 / 待 Lead·SE 裁决

1. **H 派生边是否允许 label=structural 之外显示类型**：本提案 H 派生边仅 structural；SE 可能要求显示 `data_edge_ids` 计数/类型映射（S3/S4）。
2. **A hop_max=2 的"用户显式新一跳"入口**：S5 状态机需定义该动作（D-ST/ST 系列），本提案只定数据语义。
3. **registry_history 的存储位置/签名**：设计期文件 vs S6 配置；是否需要决策 id 签名（本提案只要求字段）。
4. **deprecated 的读取兼容**：旧 frame 用旧 registry edition 解释，还是重建？（倾向旧 edition，需 S6）。
5. **similarity/path 若未来晋升**：两步（先关系源 S1-6，再维度 S1 修订）是否足够，需 S9 评测介入。

---

## 19. 证据锚索引

```text
裁决：docs/design/multilevel-graph/S1-RULINGS.md:10-18（复核）、:21-62（R-S1-1..8）、:64-74（修订轮/门禁）
上游：S0-terms-v1.md:35-41（S0-3/R-1）、:49-54（S0-5）、:56-61（S0-6/R-3）、:75-79（S0-9/D-4）、:81-85（S0-10）、:87-90（S0-11）、:98-107（R/D）
原话：multilevel-graph-vision.md:25-29（U-8..U-12）、:64（U-25）、:69（U-30）、:71（U-32）、:72（U-33）、:73（U-34）
工程：ENGINEERING-PLAN.md:149-153（DIMENSION）、:154-163（VIEW_FRAME）、:164-173（VIEW_MODEL）、:217/:276（单 dimension_id/D-5）、:229-247（data_edge_ids/VM 字段）、:290（C-5 status）、:301-303（取景服务）、:343-345（registry CFG）
代码：graph-view-2d.js:617、graph-settings.js:38（graphStyle 非维度）；graph-engine.js:167-181（全量 payload）；app.js:1845（单数据入口）；edge_types.py:9-17；edge_derivation.py:787-793（canonical id）；plugins.py:1-35（插件声明面）
```

**复跑机检**：`S1-evidence-A.md` §19 命令可直接复跑；A-v2 的 registry validator 伪代码可作为 S6a 单测输入（H relation_sources=[]、跨版本只增、`S0_REOPEN_REQUIRED`、hop 1..2、data_edge_ids 映射）。
```
