# S1 提案 A：维度体系（层次维 H / 关联维 A / 开放槽位）

> **提案方**：主办研究（`gm-seminar-researcher`）｜**票**：task-295｜**日期**：2026-11-03（Asia/Shanghai）
> **最高依据**：`docs/design/multilevel-graph-vision.md`（U-1..U-35 原话逐字存档）。
> **上游冻结**：`docs/design/multilevel-graph/S0-terms-v1.md`（sha `241b1e1e…`）+ `S0-FREEZE-RECORD.md`（**不得违反**）。
> **本场章程**：`docs/design/multilevel-graph/S1-charter.md`（S1-1..S1-15，逐项裁决）。
> **工程输入**：`ENGINEERING-PLAN.md` v0（ER/DFD/状态图 v0）、`S0-engineering-review.md`。
> **独立性**：本提案独立撰写；**未阅读** S1 独立复核方草稿（S1-dimensions-proposal-B / S1-objections），不引用其结论。
> **纪律**：只写设计；不改产品代码/契约/schema/用户库；未 commit。本提案只关闭 S1 议项，不夹带 S2/S9 算法。

---

## 0. 总口径（与 S0 冻结的关系）

```
维度 = 在给定层次坐标 (level, view_family) 下，决定「取哪些关系源、沿什么方向、扩展几跳、何时停」的
       取景规则；它是视图坐标的一部分，不是粒度、不是视觉风格、不是全展开模式。
视图 = frame(DataSource, ctx=(level, view_family, dimension_id, focus, hop_budget, mode))
      → ViewModel（纯）→ Renderer（2D/3D 后端）
```

**S0 冻结约束（本提案不得违反）**：
- **R-1**：`E_relation_min = {contain(structural), contain(semantic), reference, extend}`，**只能加不能删**；`semantic/structural` 只是标签，不是关系源过滤条件。
- **R-2**：`view_family = ⟨family_id, basis, dimension_id, level_chain⟩`；partition 断言对象 = `(level, view_family)`。
- **R-3**：聚合/折叠边必须带 `data_edge_ids`；`shown(default) ⊆ shown(full)`。
- **D-4**：ViewModel 不含导航状态/模式开关/capabilities（维度切换属 Presentation）。
- **D-5**：v1 同一视图只激活一个维度。
- **S0-3/S0-5/S0-6**：维度进入 `present(e,ctx)`；一跳=恰好一条 `E_relation(D)` 边、不闭包、跨维重置、不带背后子图。

**证据等级**：A（原话/冻结契约/决策/可复跑代码事实）；B（单源实测产物）；C（单源推理）；**本项目假设**（无独立证据的显式约定）。

---

## 1. S1-1 维度定义与边界

**定义/规则（一句话）**：维度是**取景规则**：给定同一 `(level, view_family)` 与同一 DataSource，它决定关系源、方向、跳数与终止，从而唯一确定视图集合；它不改变节点粒度、不改变事实源、不改变视觉样式。

**判定条件（维度必须同时满足）**：
```
M1 可计算：给定 (DataSource, frame_spec) 能唯一计算 ViewModel（同输入同输出）
M2 非粒度：不改变 level 划分/最小粒度（那是 S0-2 的层次坐标）
M3 非风格：不改变渲染 token（颜色/大小/布局）；graphStyle、2D/3D 后端不是维度
M4 非模式：全展开是 Presentation 正交开关（S0-8），不是维度
M5 有注册项：必须有 registry entry（id/status/version），未知 id fail-closed
M6 不改事实：维度参数只影响视图投影（presence/selection），不得写 DataSource/sidecar
```
**最小字段集**（一个"取景规则"至少含）：`dimension_id`、`basis`、`relation_sources`、`direction`、`hop_default/hop_max`（含 hop 单位）、`termination`、`status`、`version`（完整 schema 见 S1-2）。

**机检条件**：
```
- 每个取景规则都有 registry entry（id/status/version），未知 id fail-closed
- ViewModel.dimension_id ∈ active 集合；graphStyle/2D/3D/mode 不出现在 dimension_id 取值
- 同一 (DataSource, frame_spec) 两次计算结果字节一致（M1）
- 维度只改 presence/selection，不改 DataSource/edge type（M3/M4/M6）
```
**反例**：
- ✗ 把 `graphStyle`（force/galaxy）当维度：它只改视觉布局，不改取景集合（现有 `graph-view-2d.js:617`、`graph-settings.js:38` 均为视觉风格，A 级）。
- ✗ 把 2D/3D 当两个维度（U-33：它们是同一渲染契约的两个后端）。
- ✗ 把"全展开"当维度（S0-8：正交模式）。
- ✗ 把 `level` 本身当维度：level 是层次坐标（选择哪个划分），维度是取景规则；`H` 才是维度（见 S1-4）。
- ✗ 把搜索过滤/临时高亮当维度：无 registry、无稳定取景语义。

**边界用例**：
- H 与 A 都满足 M1–M6；H 的 `basis=level_partition`（S1-4），A 的 `basis=relation_neighborhood`（S1-5）。
- 未来 `time` 维度可满足 M1/M2/M4/M5/M6，但缺数据与准入（S1-15 仅 reserved）。
- 维度参数非法（如 direction 不在枚举）⇒ fail-closed，不得静默降级。

**U 映射**：U-8（层次维度）、U-9（其他维度）、U-10（关联维度）、U-12（更多维度）、U-25（槽位）。

**建议裁决**：采纳 M1–M6 作为维度判定条件；最小字段集如上；`graphStyle/2D/3D/全展开/level` 明确排除。

**证据等级**：A（U-8/U-9/U-10/U-12/U-25 原话；`graph-view-2d.js:617`、`graph-settings.js:38` 视觉风格事实；S0-3/S0-8）；**本项目假设**（M1–M6 的判定清单）。

---

## 2. S1-2 维度注册表 schema（含 fail-closed）

**定义/规则（一句话）**：维度注册表是**版本化配置**（非事实源），每个条目用固定字段声明一个维度的取景规则；注册表整体有 `schema`+`registry_version`+内容 sha，**未知/保留/弃用维度一律 fail-closed**。

**Schema（v1 建议，JSON）**：
```jsonc
{
  "schema": "multilevel-dimension-registry/v1",
  "registry_version": "1.0.0",
  "registry_sha256": "<canonical JSON 的 sha256>",
  "dimensions": [
    {
      "dimension_id": "hierarchy",            // kebab-case，唯一，不可变
      "name": "层次维",
      "basis": {                              // 取景基座
        "kind": "level_partition",            // enum: level_partition | relation_neighborhood | reserved
        "descent_sources": ["contain(structural)"]  // H 专用：只沿结构包含下降
      },
      "relation_sources": [                   // 本维度允许的关系源；active 必须 ⊇ E_relation_min
        "contain(structural)", "contain(semantic)", "reference", "extend"
      ],
      "direction": "down",                    // enum: down|up|both|out|in（H=down）
      "hop_unit": "level",                    // enum: level|edge（H=level，A=edge）
      "hop_default": 1,
      "hop_max": 1,                           // v1 必须有穷
      "termination": {                        // 终止条件（可机检）
        "max_nodes": 200,                     // 显示节点预算（>0）
        "leaf_required": true,                // H=true：到 KP 叶子终止
        "stop_on_no_new": true
      },
      "status": "active",                     // enum: active|reserved|deprecated
      "priority": 10,                         // active 内唯一
      "version": "1.0.0",                     // semver；active 改动=新版本+重开 S1
      "definition": "沿层次划分逐层下钻，到 KP 叶子终止（U-8/U-28）"
    },
    {
      "dimension_id": "association",
      "name": "关联维",
      "basis": { "kind": "relation_neighborhood" },
      "relation_sources": [
        "contain(structural)", "contain(semantic)", "reference", "extend"
      ],
      "direction": "both",
      "hop_unit": "edge",
      "hop_default": 1,
      "hop_max": 2,
      "termination": { "max_nodes": 200, "leaf_required": false, "stop_on_no_new": true },
      "status": "active",
      "priority": 20,
      "version": "1.0.0",
      "definition": "沿 E_relation_min 关系边挂接 ≤hop_max 跳的关联节点（U-10/U-11/U-15）"
    },
    {
      "dimension_id": "time",
      "name": "时间维",
      "basis": { "kind": "reserved" },
      "status": "reserved",
      "version": "0.0.0-reserved",
      "definition": "按 valid_from/valid_to 取景（U-25；v1 不实现）"
    }
  ]
}
```

**字段类型/默认值/失败语义**：

| 字段 | 类型 | 默认 | 失败语义 |
|---|---|---|---|
| `dimension_id` | string(kebab,唯一) | 无 | 缺失/重复/非法格式 ⇒ registry invalid（fail-closed） |
| `name` | string | =id | 非阻塞 |
| `basis` | object `{kind, descent_sources?}` | 无 | kind 不在枚举 ⇒ invalid；level_partition 必须给 descent_sources |
| `relation_sources` | string[]（关系源 id） | 无 | active 时 `⊇ E_relation_min`，否则 invalid（R-1） |
| `direction` | enum `down/up/both/out/in` | 无 | 非法/与 basis 不匹配 ⇒ invalid |
| `hop_unit` | enum `level/edge` | 按 basis | level_partition⇒level；relation_neighborhood⇒edge；否则 invalid |
| `hop_default` | int ≥0 | 无 | >hop_max ⇒ invalid |
| `hop_max` | int ≥0 | 无 | v1 必须有限（null/∞ ⇒ invalid）；H=1、A≥1 |
| `termination` | object | 无 | 缺 max_nodes/leaf_required/stop_on_no_new ⇒ invalid；max_nodes≤0 ⇒ invalid |
| `status` | enum `active/reserved/deprecated` | 无 | 其它值 ⇒ invalid |
| `priority` | int | 无 | active 内非唯一 ⇒ invalid |
| `version` | semver string | 无 | active 改动必须 version+1 并重开 S1；否则 invalid |

**校验伪代码（可被另一人复算）**：
```python
MIN = {"contain(structural)", "contain(semantic)", "reference", "extend"}  # R-1 冻结

def validate_registry(reg):
    assert reg["schema"] == "multilevel-dimension-registry/v1"
    ids = [d["dimension_id"] for d in reg["dimensions"]]
    assert len(ids) == len(set(ids)), "DIM_DUPLICATE"
    for d in reg["dimensions"]:
        assert re.fullmatch(r"[a-z][a-z0-9-]*", d["dimension_id"]), "DIM_ID"
        assert d["status"] in {"active", "reserved", "deprecated"}, "DIM_STATUS"
        if d["status"] == "reserved":
            # reserved 只需 id/name/status/version/definition；不得带可执行取景字段
            assert d["basis"]["kind"] == "reserved", "DIM_RESERVED_INVALID"
            continue
        assert MIN <= set(d["relation_sources"]), "DIM_MISSING_MIN"        # R-1
        assert 0 <= d["hop_default"] <= d["hop_max"] < 10**6, "DIM_HOP"
        assert d["termination"]["max_nodes"] > 0, "DIM_BUDGET"
        if d["basis"]["kind"] == "level_partition":
            assert d["direction"] == "down", "DIM_H_DIRECTION"
            assert d["hop_unit"] == "level", "DIM_H_UNIT"
            assert d["termination"]["leaf_required"] is True, "DIM_H_LEAF"
            assert set(d["basis"]["descent_sources"]) <= {"contain(structural)"}, "DIM_H_DESCENT"
        if d["basis"]["kind"] == "relation_neighborhood":
            assert d["direction"] in {"both", "out", "in"}, "DIM_A_DIRECTION"
            assert d["hop_unit"] == "edge", "DIM_A_UNIT"
    actives = [d for d in reg["dimensions"] if d["status"] == "active"]
    assert len({d["priority"] for d in actives}) == len(actives), "DIM_PRIORITY"
    assert {d["dimension_id"] for d in actives} == {"hierarchy", "association"}, "DIM_ACTIVE_SET"
    return {"ok": True, "sha256": sha256(canonical_json(reg))}

def resolve_dimension(reg, dimension_id):
    d = next((x for x in reg["dimensions"] if x["dimension_id"] == dimension_id), None)
    if d is None: raise FailClosed("DIM_UNKNOWN", dimension_id)
    if d["status"] != "active": raise FailClosed("DIM_NOT_ACTIVE", dimension_id)
    return d
```

**fail-closed 反例（≥3，全部必须拒绝）**：
1. **未知维度**：`ctx.dimension_id="temporal"` 不在注册表 ⇒ `DIM_UNKNOWN`，不得回退到 H/A 默认。
2. **保留维度被引用**：`ctx.dimension_id="time"`（reserved）⇒ `DIM_NOT_ACTIVE`，不得尝试实现。
3. **active 条目缺最小关系源**：某维度 `relation_sources=["contain(structural)"]` ⇒ `DIM_MISSING_MIN`（违反 R-1）。
4. **H 方向/终止非法**：H `direction=both` 或 `leaf_required=false` ⇒ `DIM_H_DIRECTION`/`DIM_H_LEAF`。
5. **hop 非法**：`hop_default=3, hop_max=1` ⇒ `DIM_HOP`；`hop_max=null` ⇒ invalid。
6. **弃用维度**：`deprecated` 被 ctx 引用 ⇒ `DIM_NOT_ACTIVE`（只能读取旧 frame 作历史展示，不能新取景）。

**反例（设计层面）**：用运行时配置文件覆盖 registry 而不升版本；把 reserved 条目的 `basis` 写成 `relation_neighborhood` 偷偷可用；允许插件在运行时注册维度。**边界用例**：注册表为空/缺 registry_sha ⇒ invalid；reserved 条目只登记定义、不参与渲染；registry 版本升级不改已冻结条目字段（只加新条目/状态流转）。

**U 映射**：U-8、U-9、U-10、U-12、U-25。

**建议裁决**：采纳上述 schema 与校验；`active` 集合 v1 固定为 `{hierarchy, association}`；registry 是**版本化配置**（非事实源），未知/保留/弃用 fail-closed；schema 由 S6a 落成实体 `DIMENSION`（与 `ENGINEERING-PLAN.md:149-153` 对齐并补字段）。

**证据等级**：A（S0-3/R-1 冻结；`ENGINEERING-PLAN.md:149-153,216,290` 的 DIMENSION 实体与 C-5 状态枚举待补；现实现无维度注册表，`graph-engine.js:167-181` 只吃 payload）；**本项目假设**（字段默认值、`basis` 对象结构、v1 active 集合）。

---

## 3. S1-3 开放槽位登记（U-25）

**定义/规则（一句话）**：开放槽位 = registry 中 `status=reserved` 的维度条目：**只登记定义与取景草案，不得进入任何渲染分支/取景服务**；晋升 `active` 必须走 S1 修订 + 决策 + 版本升级。

**登记格式（最小）**：
```jsonc
{
  "dimension_id": "time",
  "name": "时间维",
  "basis": { "kind": "reserved" },
  "status": "reserved",
  "version": "0.0.0-reserved",
  "definition": "一句话定义",
  "draft": {                                  // 允许草案，但不可执行
    "relation_sources_draft": ["..."],
    "direction_draft": "...",
    "hop_draft": "...",
    "termination_draft": "...",
    "evidence_needed": ["..."],
    "why_not_v1": "..."
  }
}
```
**规则**：
```
R1 reserved 不得被 ctx/frame/ViewModel 引用（resolve_dimension 抛 DIM_NOT_ACTIVE）
R2 reserved 不得有可执行 branch：代码/配置中不得出现 "if dimension_id==<reserved> …"
R3 reserved 的 draft 字段只作文档，不参与校验/取景
R4 晋升条件（全部满足才 active）：
   a) 定义/机检/反例/边界/证据等级齐全（S1 章程 §3 要素）
   b) 有真实关系源与可复算取景函数（M1 通过）
   c) 有消费/评测需求与失败关闭测试（S7/S8/S4 接口）
   d) S1 修订提案 + Lead 裁决（涉契约/字段变更需人批）
   e) registry version 升 minor，旧版本保留（回滚=回旧 version）
R5 晋升后只能加不能删（加源/加维度）；删除维度/删关系源必须重开 S1（S0 R-1 同理）
```

**反例**：
- ✗ 设置面板暴露 `time` 维度开关（reserved 进渲染分支）。
- ✗ 在取景服务里 `if dim=="time": …` 占位实现。
- ✗ 把 reserved 当作默认 fallback（未知时静默用 H 可以，但用 reserved 不行）。
- ✗ 未升 registry version 就改 reserved→active。

**边界用例**：
- reserved 条目可以列出 draft 关系源，但 draft 不参与 `E_relation` 校验。
- deprecated 与 reserved 都不可新取景；deprecated 允许读取历史 ViewModel（S5 回放，不重算）。
- 槽位数量不设上限（U-25/U-31 思路），但每个必须有 definition/why_not_v1。
- v1 结束前不得晋升任何 reserved（S1 冻结门禁）。

**U 映射**：U-9、U-12、U-25、U-30。

**建议裁决**：采纳登记格式与晋升条件；v1 reserved 清单见 S1-15；reserved 不实现、不进渲染。

**证据等级**：A（U-25 原话；S0-3 reserved 规则；`S0-terms-v1.md:37`）；**本项目假设**（晋升审批链细节）。

---

## 4. S1-4 H（层次维度）精确定义

**定义/规则（一句话）**：H 是**沿层次划分向下取景**的维度：基座为当前 `(level, view_family)` 的划分块，方向 `down`，只沿 `contain(structural)` 下降，终止于 KP 叶子；它不挂接跨层关系邻居。

**形式化**：
```
H.basis = {kind: level_partition, descent_sources: ["contain(structural)"]}
H 输入：frame=(level ℓ, view_family f, focus block b_ℓ, hop)
H 节点：
  hop=0 ⇒ {b_ℓ}（当前块自身）
  hop≥1 ⇒ children(b_ℓ) = { b_{ℓ+1} ∈ Π_{ℓ+1,f} | b_{ℓ+1} ⊆ b_ℓ }
           （v1 hop_max=1；多次下钻由导航动作推进 focus/level，不是一次 hop）
H 边：{contain(structural): (b_ℓ → b_{ℓ+1})}，方向 down；不显示反方向
H 终止：children 为空（到达 Π_L=单 KP）或 hop 达到 hop_max
H.relation_sources ⊇ E_relation_min（R-1 强制）；
  但只有 contain(structural) 参与下降/加节点；其余源若 endpoints 均已在可见块内，
  可作为「层内上下文边」显示并标 label（不新增节点、不触发下一跳）
```
**机检条件**：
```
- H.registry.direction == "down"；hop_unit == "level"；leaf_required == true
- 每个 H 视图节点：要么=focus block，要么是 focus block 的下层子块（contains 关系）
- 不出现 up 方向边；不出现非 contain 源带来的新节点（只可能端点都可见的上下文边）
- 到达 Π_L 后不再有 cluster 节点（S0-2 V4/V6）
- 若 hop>hop_max ⇒ fail-closed；若 focus 不是该 level/family 的块 ⇒ fail-closed
```
**与 S0-2 的关系**：H 使用 `(level, view_family)` 的划分 `Π_{ℓ,f}`；同一视图只显示一个 level 的块（v1），因此 partition 断言直接复用 `validate_level_view`（S0-2 V1–V6）。H 不下钻跨 view_family（跨族进入由 S5 导航/多归属处理）。

**反例**：
- ✗ H 直接显示 KP 的句子子节点（S0-11 第 1 条）。
- ✗ H 向上（up）显示父块并叫层次视图（方向应 down；返回是导航）。
- ✗ H 一次 hop 展开两层（破坏单层划分视图；应通过导航逐层）。
- ✗ H 用 reference/extend 源把跨层节点拉进来（那是 A 的职责）。
- ✗ H 视图混两个 `view_family`（违反 R-2/partition）。

**边界用例**：
- focus 是单 KP（叶层）：H 视图只有该 KP（到叶子终止）。
- focus 无子块（空？S0-2 无空簇；若数据缺失 ⇒ fail-closed/unknown，不伪造）。
- H hop=0：显示当前块自身（导航/概览用）。
- H 与 A 切换：level/family 不变，节点集合由 A 扩展（S1-13 属 Presentation）。

**U 映射**：U-4、U-5、U-7、U-8、U-28。

**建议裁决**：采纳 H 定义；v1 `hop_default=1, hop_max=1`（一次一层）；H 只沿 `contain(structural)` 下降；其余关系源仅作可见上下文边。

**证据等级**：A（U-4/U-5/U-8/U-28；S0-2/S0-3）；**本项目假设**（H 的 hop=层偏移、v1 max=1 的取值；S5 可调整导航动作）。

---

## 5. S1-5 A（关联维度）精确定义（U-10/U-30）

**定义/规则（一句话）**：A 是**沿关系边扩展取景**的维度：从当前视图节点出发，按 `E_relation(A) ⊇ E_relation_min` 沿方向 `dir` 挂接 ≤hop 跳的关联节点，让"平时不显示的关联节点"出现（U-10）；每跳=一条关系边，不分包含/引用/语义关联。

**形式化**：
```
A.basis = {kind: relation_neighborhood}
E_relation(A) = 由 registry relation_sources 解析出的 DataSource 边集合（v1 = E_relation_min）
输入：base view V0（当前 level/family 的 H 视图）、focus F、dir(A)、hop_budget
候选节点：BFS(A) 从 F 出发、沿 E_relation(A)、按 dir、边数 ≤ hop_budget 到达的节点（∉V0）
显示节点：V0 ∪ 候选节点（去重，取最小 hop）
显示边：E_relation(A) 中两端点均显示、且处于 BFS 路径/邻接的边（每条边带 hop）
一跳（S0-5）：hop=1 时只显示「端点+这条边」，不展开端点的背后邻域（U-17）
hop>1：仅在显式 hop_budget 下允许（U-11/U-22，S5 决定细粒度），仍不闭包——
        每增加一跳都由预算显式驱动，不默认递归
标签：边 label(semantic/structural/navigation) 只用于显示/消费准入，不影响挂接/计跳
边界：A 不改变 V0 的层次基座；只做「可见集合的扩展」
```
**关系源覆盖（U-10）**：
| U-10 类别 | v1 关系源（E_relation_min） | 计跳规则 |
|---|---|---|
| 包含关系 | `contain(structural)`、`contain(semantic)` | 每条 contain 边=1 跳（无论 structural/semantic） |
| 引用 | `reference`（link 投影边） | 每条 reference 边=1 跳 |
| 语义关联 | `extend`（作者断言时 label=semantic） | 每条 extend 边=1 跳 |
- 之后新增关系源（S1-6）同样"一条边=1 跳"，不按类型加权。

**与 S0-5 的关系**：S0-5 的"一跳"是 A 在 `hop_budget=1` 时的默认行为；S0-5 全部约束（不闭包、方向、跨维重置、不带背后图、bridge 是 role）继续适用。

**机检条件**：
```
- A.relation_sources ⊇ E_relation_min（R-1）
- 每个 shown 节点/边 hop ≤ hop_max；节点 id 唯一；边 canonical id 唯一
- 不存在由 A 带来的非 E_relation(A) 边
- 不闭包：hop=1 时无第 2 跳边（S0-5）
- A 不改变 level/view_family 基座（frame 的 level/family 与进入前一致）
```
**反例**：
- ✗ 只走 semantic 边（漏 U-10 的包含/引用）——S0 P0-1 已禁止。
- ✗ 把结构 contain 挂接后当语义前提（label 只是标签，消费者不得升级）。
- ✗ 自动 2 跳/闭包（U-18；须显式预算）。
- ✗ 把 A 的节点写回 membership/DataSource（D-3/S0-7）。
- ✗ A 改变 level/family 基座（A 只扩可见集合）。

**边界用例**：
- reference 边挂接：节点显示，label=navigation；不改变语义边集。
- 同一目标多路径：只显示一次，hop=最小距离；多条不同类型边分别显示（每条 canonical id）。
- 目标是 cluster 节点：只显示该 cluster（及其边），不展开其成员（U-17）；点击进入由 S5。
- hop_budget=0：A 视图 = H 基座（无扩展）。
- 无新节点的 frontier：提前终止（S1-9 stop_on_no_new）。

**U 映射**：U-10、U-11、U-15、U-17、U-18、U-19、U-30。

**建议裁决**：采纳 A 形式化；`E_relation(A)=E_relation_min`（v1）；hop_default=1、hop_max=2（可配）；关系源只增不删（S1-6）；A 不改变层次基座。

**证据等级**：A（U-10/U-11/U-15/U-18/U-30；S0-3/S0-5）；**本项目假设**（hop_max=2 的 v1 取值、A 的 BFS 边界细节——S4 可细化但不得破 S0-5）。

---

## 6. S1-6 E_relation 扩展规则（R-1 只能加）

**定义/规则（一句话）**：`E_relation` 是 DataSource 中可用于取景的关系源集合；**冻结下界 `E_relation_min` 只增不删**；新增关系源必须通过准入分类/验证器/版本升级，删除必须重开 S0。

**分类（新增关系源只能落入三类之一）**：
| 类别 | 例子 | v1 可用 | 落地要求 |
|---|---|---|---|
| `edge_type`（现有产品边类型） | contain(structural/semantic)/reference/extend | ✅ 已在 min | 不能新增产品类型（S0-11 #6）；仅能在维度注册表选用 |
| `projection`（同一事实的另一种投影） | 未来把 raw `links[]` 直接投影为关系（目前 collector 已投 reference） | 条件 | 只读投影、有 canonical id、不写产品事实；需 validator + S1 修订 |
| `derived`（派生相似/研究判断） | co-citation、embedding 近邻、L2 判据 | ❌ v1 | 研究侧/派生物；若产品化须过 G2/G5 证据与 S9/S2 冻结；不得冒充 semantic |
**新增准入（全部满足）**：
```
E1 有稳定 canonical 标识（映射到 DataSource 边 id 或可复算 id）
E2 只读：不得写 sidecar/正文/新事实源；只作为视图取景输入
E3 分类明确（上表）；derived 必须标 research_only，且不得进 v1 active 维度
E4 标签映射：semantic/structural/navigation 的判定沿用 S0-1（不得用新源绕过 G_sem）
E5 validator + 测试夹具（正/反例）与 registry 校验同步
E6 S1 修订提案 + Lead 裁决（涉契约/人批）；registry version 升 minor，旧版保留
E7 加入后：A/B 的 E_relation(D) ⊇ min；新增源对所有使用该维度的取景生效，不得只对某场景生效
```
**删除规则**：任何从 `E_relation_min` 删除关系源 = **重开 S0**（R-1 写在冻结稿）；删除原因/影响/回滚必须记录（U-10 覆盖、历史视图兼容、G4/G5 研究基线）。

**机检条件**：
```
- validate_registry: active 维度 relation_sources ⊇ E_relation_min（删除即 FAIL）
- 新增关系源必须携带分类（edge_type/projection/derived）与验证器测试
- derived 源不得出现在 v1 active 维度（runtime fail-closed）
- 删除 E_relation_min 任一项 ⇒ S0 reopen 检查（不是 S1 内配置可改）
```
**反例**：
- ✗ 新增 `prerequisite` 边类型当关系源（S0-11 #6：v1 不加语义类型）。
- ✗ 把 embedding 近邻直接加入 active A（derived 未过证据/契约）。
- ✗ 只在某 UI 场景加关系源（应通过注册表对维度统一生效）。
- ✗ 删除 `reference` 以"简化图"（违反 U-10/R-1）。

**边界用例**：
- `projection` 源与已有 edge 重叠：按 canonical id 去重，hop 仍按边计；不得重复加节点。
- `derived` 源只能在 reserved/研究视图中试跑（S9 评估），不得进 v1 active。
- 新源加入后 hop 语义不变（一条边=1 跳），避免历史 hop 口径漂移。
- 源版本变更：registry version+1；旧 frame 用旧 registry 解释（S6 保存 edition）。

**U 映射**：U-9、U-10、U-12、U-25、U-30、U-32。

**建议裁决**：采纳三类分类与 E1–E7；v1 不新增关系源；删除重开 S0；新增源必须由 registry version + 决策记录。

**证据等级**：A（S0 R-1 冻结；S0-11 #6；ontology v0 §4 类型不做清单；`edge_types.py:9-17` 类型枚举）；**本项目假设**（三类分类与 E1–E7 的准入清单）。

---

## 7. S1-7 跳数语义（U-11）

**定义/规则（一句话）**：跳数按**遍历单位**计：A 沿**关系边**计（每过一条边 = 1 跳），H 沿**层次层**计（每下一层 = 1 level-hop）；节点去重不减少已走边数，跨维度切换重置为 `hop_default`，不得闭包。

**形式化**：
```
hop 单位由 hop_unit 决定：
  H: hop = |Δlevel|（从 focus 块到目标块的层数）；v1 每视图只显示 focus 的下一层 ⇒ hop_default=hop_max=1
  A: hop = BFS 边数（沿 E_relation(A) 按 dir）从 F 到目标的最短路径边数
计数规则：
  C1 沿边：hop(v) = min{ |p| | p 是从 F 到 v 的路径，每条边∈E_relation(D)，方向符合 dir }
  C2 去重：同一节点多路径只算最小 hop，只显示一次；同一对节点不同类型边可分别存在（边 id 不同）
  C3 不按节点累加：访问 N 个节点不等于 N 跳；hop 是路径长度
  C4 不闭包：hop 达到上限即终止；不得把邻居的邻居自动加入（除非 hop_budget 显式更大，且逐跳预算驱动）
  C5 跨维：切换 dimension ⇒ hop 重置为新维度 hop_default（S0-5）；不继承旧 hop
  C6 预算：hop_max 与 max_nodes 同时生效；超预算节点/边 presence=suppressed, rule_id=hop.budget/node.budget
机检：
  - 每个 shown 节点/边 hop ≤ hop_max
  - shown 节点 id 唯一；边 canonical id 唯一
  - 不存在 hop>hop_max 的 shown 元素
  - 维度切换后新 frame.hop == registry.hop_default
```
**反例**：
- ✗ 按节点数计跳（两个直接边到同一节点算 2 跳、或展开 10 个节点就叫 10 跳）。
- ✗ 多路径到同一节点显示两次（应去重、取最小 hop）。
- ✗ 跨维度保留 hop=2（应重置默认 1）。
- ✗ 默认闭包自动 2 跳（U-18）。
- ✗ hop_max=∞/未记录截断（S1-9 fail）。

**边界用例**：
- 同一对节点有 reference + extend 两条边：两个边 id 均按 1 跳候选，显示两条（类型不同）；目标节点只显示一次。
- hop=0（A）：无扩展，视图=H 基座。
- H 的 hop 与导航层数：连续两次下钻 = 两个 frame（每次 hop=1），不是一个 frame hop=2。
- 折叠簇：`underlying_hop_count` 记录内部穿越（S4/S5 细化，不改变 hop 计法）。

**U 映射**：U-10、U-11、U-15、U-18、U-22。

**建议裁决**：采纳"边/层为单位 + 最小距离 + 节点去重 + 跨维重置 + 预算截断可解释"；v1 H hop=1（level），A hop_default=1 / hop_max=2（edge）。

**证据等级**：A（U-11/U-18；S0-5/S0-6）；**本项目假设**（H/A 的 v1 具体 hop 值，S5/S4 可调但须保持单位语义）。

---

## 8. S1-8 方向 `dir(D)`

**定义/规则（一句话）**：方向枚举 `{down, up, both, out, in}` 决定取景时沿关系边的哪一端扩展；方向只影响**可见集合/遍历**，不改变边的事实方向、类型或 label。

**枚举语义**：
| 值 | 语义 | 允许维度 | 渲染/遍历 |
|---|---|---|---|
| `down` | 外层→内层（父块→子块） | H（唯一） | H 视图只显示 `contain(structural)` 父→子；反方向不展开 |
| `up` | 内层→外层 | 保留（v1 无 active 用） | 逆 contain 遍历（未来/导航用） |
| `both` | 双向 | A 默认 | 无向 BFS（out+in 并集） |
| `out` | source→target | A 可配 | 只沿边正向 |
| `in` | target→source | A 可配 | 只沿边反向 |
```
dir(D) 约束：
  H: 必须 down（否则 registry invalid）
  A: both|out|in（默认 both；v1 只 active A=both）
  其它 active 维度：由 S1 修订指定，v1 无
方向与一跳：每次 hop 都按 dir 走一条边；反向边仍显示原始 source/target（不翻转事实），
            由 S5/渲染标记方向（S3 定视觉）
方向与标签：方向不改变 label；reference/contain 等类型不变
```
**机检条件**：
```
- direction ∈ {down,up,both,out,in}；H=down、A∈{both,out,in}；非法 fail-closed
- 方向只影响选择：同一 (DataSource, 同一 focus) 下边 type/source/target 字段不变
- H 视图不存在 up 方向边；A out/in 视图反向邻居不可见
```
**反例**：
- ✗ H 使用 `both`（会向上/横向拉节点，破坏层次视图）。
- ✗ `out`/`in` 反转边的事实方向并写回数据（只影响选择，不改 source/target）。
- ✗ 方向非法值静默默认 both（应 fail-closed）。
- ✗ 用方向过滤把 semantic/structural 标签当开关。

**边界用例**：
- A `both` 下同一对节点可能有 out/in 两条同一事实边：仍是一条边（不重复）；仅方向不同不产生新边。
- A `out` 时反向邻居不可见（即使是一跳）；用户要双向需切回 both（S5 动作）。
- H 到达叶层：无子可下，方向 down 终止（leaf）。
- 未知方向/与 basis 不匹配：registry invalid（DIM_DIRECTION）。

**U 映射**：U-10、U-11、U-15、U-30。

**建议裁决**：采纳枚举与 per-dimension 约束；v1 H=down，A=both；方向只影响取景不影响事实；非法方向 fail-closed。

**证据等级**：A（S0-5 已冻结 H=down/A=both 可配；`edge_derivation.py` 边有 source/target 事实）；**本项目假设**（up 留 reserved 的语义、方向视觉标记 S3）。

---

## 9. S1-9 终止条件（可机检）

**定义/规则（一句话）**：取景必须**有限且可机检地终止**：终止条件取 `{层叶、hop_max、max_nodes、frontier 为空、显式取消}` 的并集；任何截断必须写 `presence=suppressed + rule_id`，不得静默丢边/无限遍历。

**形式化**：
```
terminate(D, ctx, state) ⇔
    leaf_reached(H ∧ focus 在 Π_L) ∨ hop ≥ hop_max
  ∨ nodes_shown ≥ max_nodes ∨ frontier = ∅ ∨ cancelled
运行：
  while not terminate:
      frontier = expand_one_hop(frontier)    # H: children; A: BFS 一层
      apply node/edge budget; mark overflow candidates suppressed
  输出：ViewModel{shown, suppressed(rule_id), unknown(rule_id)}
机检：
  - 算法必然停机：visited 集合 + 有限 hop_max + 有限 max_nodes（不允许 null/∞）
  - 输出节点数 ≤ max_nodes；每个 shown 的 hop ≤ hop_max
  - 每条被排除的候选边有 presence∈{suppressed,unknown} 且 rule_id 可枚举
    （rule_id 例：level.leaf / hop.budget / node.budget / direction.filter / source.unavailable）
  - 相同输入两次运行输出相同（确定性；无时间/随机依赖）
```
**「不设上限」与预算共存**：U-32 说规模不是问题、关键在后端检索；本提案解释为**后端可扩展**，但**显示预算必须有**（`max_nodes`/`hop_max` 由 S8 定值，S1 冻结结构）；不允许"先全算再截断"成为无界遍历（visited+budget 保证停机）。

**反例**：
- ✗ 无 hop/节点上限的 BFS（毛球图可无限/极慢）。
- ✗ "看起来够了"就停（不可机检、不可复现）。
- ✗ 静默丢弃 frontier 且不标 suppressed（视图缺席被当数据缺席）。
- ✗ 同输入不同输出（依赖时间/随机/会话状态）。
- ✗ H 到叶层仍尝试展开（应 leaf_reached）。

**边界用例**：
- `max_nodes` 恰好等于 frontier 大小时：全部 shown，无截断 rule_id。
- frontier 为空：自然终止（比预算早），不标截断。
- H 的 `leaf_required=true`：到 Π_L 必须停；若数据缺失导致无法判定叶子 ⇒ presence=unknown + rule_id，不伪造。
- A 的 hop_max=1：frontier 扩展一层后立即 hop.budget 终止。
- 取消（用户切换维度/关闭面板）：presence=unknown + rule_id=cancelled；不写事实。

**U 映射**：U-11、U-18、U-22、U-32。

**建议裁决**：采纳终止并集 + 有限预算 + 截断 rule_id + 确定性；`max_nodes`/`hop_max` 数值由 S8 定，S1 冻结"必须有穷"。

**证据等级**：A（U-32 原话；S0-6 presence/rule_id；SE 的 M-5/M-6）；**本项目假设**（终止规则清单与预算结构）。

---

## 10. S1-10 维度组合（D-5）

**定义/规则（一句话）**：**v1 同一视图只激活一个维度**；多维组合只作为开放槽位登记（格式/顺序/优先级），不实现、不进入 ctx/ViewModel。

**形式化**：
```
VIEW_FRAME.dimension_id : single active id（D-5）
组合槽位（reserved）格式：
{
  "combination_id": "multi.time+evidence",
  "dimension_ids": ["time", "evidence"],
  "order": ["time", "evidence"],           // 只登记
  "composition_rule": "reserved",          // 不实现
  "priority_policy": "reserved",
  "conflict_policy": "reserved",
  "status": "reserved"
}
v1 校验：ctx 出现 combination_id/dimension_list ⇒ DIM_COMBINATION_UNSUPPORTED（fail-closed）
切换语义：切换维度 = 新 frame（S5），hop 重置；组合切换不在 v1
```
**机检条件**：
```
- VIEW_FRAME/ctx 只允许单个 dimension_id；出现 dimension_list/combination_id ⇒ fail-closed
- active 集合 == {hierarchy, association}（v1）
- ViewModel 无 dimension 列表/组合规则字段（D-4）
- 组合槽位 status=reserved 且无渲染分支
```
**反例**：
- ✗ 同时激活 H+A 却只用一个 `dimension_id` 字段（非法）。
- ✗ 用组合优先级偷偷叠加预算/跳数。
- ✗ ViewModel 携带 dimension 列表/组合规则（违反 D-4）。
- ✗ 组合槽位进入渲染分支。

**边界用例**：
- 用户想"H 的层次 + A 的关联"：v1 用两次视图切换（H view ↔ A view），不是组合（S5）。
- 组合需求登记后，晋升需 S1 修订 + S6a 字段扩展（dimension_id→有序列表）+ 新决策。
- 组合顺序/优先级在 reserved 中只作设计输入，不参与校验。

**U 映射**：U-8、U-9、U-12、U-25、U-30。

**建议裁决**：采纳 v1 单维度；组合槽位格式如上；ctx 拒绝组合参数；切换属 S5/Presentation。

**证据等级**：A（S0 D-5；`ENGINEERING-PLAN.md:217,276` VIEW_FRAME 单 dimension_id）；**本项目假设**（组合槽位字段）。

---

## 11. S1-11 维度状态机与能力闸（含 plugins）

**定义/规则（一句话）**：维度条目有状态机 `reserved → active → deprecated`（可经审批回 active）；只有 `active` 可被 ctx 使用；**未知/保留/弃用一律 fail-closed**；插件不得自注册/自激活维度。

**状态机**：
```
states: reserved | active | deprecated
transitions:
  reserved --promote(定义完整+机检+需求+审批+registry version bump)--> active
  active   --deprecate(替代方案/版本升级决策)--> deprecated
  deprecated --reopen(新 S1 修订+审批+version bump)--> active
  active   --(不允许直接 delete)--> 只能 deprecate（S1 变更控制）
未知状态/非法转移 ⇒ registry invalid（fail-closed）
```
**与 plugins 能力面的关系**：
```
- 维度注册表是**版本化配置**，不是插件，不是事实源；插件不能写 registry。
- v1 插件能力面不含"维度提供者"：插件声明（agent-plugin-design 契约：声明 JSON、无可执行代码）
  不得新增/激活维度；未知 dimension_id 在插件/配置中出现 ⇒ fail-closed。
- 未来若允许插件贡献维度：必须走 S1 修订 + registry active 条目 + capability 白名单；
  仍禁止插件直接改渲染状态/写 ViewModel（S0-10）。
- capability 命名建议（reserved，不实现）：graph.dimension.use / graph.dimension.provide
```
**持久化位置**：registry 是**设计/配置产物**（版本化文件，非事实源，见 `ENGINEERING-PLAN.md:343-345` CFG 区）；runtime 只读加载 + 内容 sha 校验；变更记录在决策/注册表历史，不写 Knowledge Base sidecar。

**反例**：
- ✗ 插件加载时 `status=active`（自激活）。
- ✗ 未知 dimension_id 回退默认（应 fail-closed）。
- ✗ deprecated 维度被新 frame 使用（只允许历史 ViewModel 展示）。
- ✗ 把 registry 状态写进产品事实源（应配置/版本文件）。

**边界用例**：
- registry 文件缺失/损坏/版本不匹配 ⇒ 全局 fail-closed（不渲染图谱并报错）。
- active 条目版本号提升：旧 frame 用旧 registry（edition 键）解释（S6）。
- `frozen` 概念：S0 A-v2 曾用 `specified/frozen`；S1 映射为 active 的 `version` + `version_frozen_at` 属性，不新增状态（解决 C-5 枚举不一致）。
- reserved 与 deprecated 都不可新取景；区别：reserved 未实现，deprecated 已实现但停用。

**U 映射**：U-9、U-12、U-25、U-33（插件/能力面）。

**建议裁决**：采纳三状态 + 映射表（A 的 specified/frozen→active+版本冻结；B 的 active→active）；v1 无插件维度；registry 只读配置 + fail-closed。

**证据等级**：A（S0-11 #6/#15；`ENGINEERING-PLAN.md:216,290` 的 C-5 待补；`plugins.py:1-35` 插件声明/校验/无可执行代码）；**本项目假设**（状态转移审批链、capability 命名）。

---

## 12. S1-12 维度与选择性渲染/边存无（present）

**定义/规则（一句话）**：维度通过 `ctx.dimension_id` 进入 **`present(e,ctx)` 唯一判据**：它决定关系源/方向/跳数预算，从而决定每条候选边的 `presence∈{shown,suppressed,unknown}`；**维度只改变 presence，不改变边的类型/标签/事实**（U-27）。

**形式化**：
```
present(e, ctx) = admit(D, level, view_family, focus, hop, e) 的求值结果
  D = resolve_dimension(registry, ctx.dimension_id)   # active else fail-closed
  candidate(e) ⇔ e.type ∈ relation_sources(D)（且端点/路径在取景范围）
  H: shown(e) ⇔ e.type=contain(structural) ∧ e.source=可见父块 ∧ e.target=其子块
                   （方向 down；其余源仅当两端均可见作上下文边）
  A: shown(e) ⇔ 端点在某条 ≤hop 的 E_relation(A) 路径上 ∧ 方向符合 dir(A) ∧ 在节点预算内
  suppressed(e) ⇔ candidate(e) 但规则不允许（rule_id:
       dim.direction / hop.budget / node.budget / level.not_visible / cluster.folded）
  unknown(e) ⇔ 关系源不可解析/未计算（rule_id: source.unavailable / dim.unresolved）
输出：
  edges[] 携带 presence/rule_id/hop/effective_type（类型映射不变）
  渲染集合 = {e | presence==shown}（S0-6 恒等式）
```
**U-27「存无/类型」在维度下的表述**：
- **存无**：同一对节点在 H 中 shown（contain 结构边）、在 A 中可能 suppressed（hop/方向/预算）或 shown（一跳）——这是**视图相对**，DataSource 不变。
- **类型**：维度**不改变** type/contain_kind/label；`effective_type` 只做显示映射（如 contain structural 显示"结构包含"），不得把 structural 当 semantic。
- **缺席**：`suppressed/unknown` 必须带 rule_id；视图缺席 ≠ 数据缺席（U-27）；不得因切换维度推断"无关系"。

**机检条件**：
```
- 对候选边 e∈E_relation(D)：presence(e,ctx) 必须有值（shown/suppressed/unknown）
- presence!=shown ⇒ rule_id 非空且可枚举
- 同一 e 在不同维度下 type/contain_kind/label 不变，仅 presence 可变（U-27）
- 渲染集合 == {e | presence==shown}（S0-6 恒等式）
- 维度 fail-closed 时整个 ViewModel 构建失败，不部分渲染
```
**反例**：
- ✗ A 维度把 reference 边显示成 semantic（类型/标签被改写）。
- ✗ 切换维度后 ViewModel 的边类型集合变化（应只 presence 变化）。
- ✗ 维度决定"哪些边存在"，但不给 rule_id（静默丢边）。
- ✗ 用维度过滤删除 DataSource 边（事实不变）。
- ✗ 全展开绕过 present（S0-6/P1-2 已冻结）。

**边界用例**：
- 同 pair 同时 contain/reference/extend：H 显示 contain（层次），A 可显示其余（一跳）；同一视图不同维度 presence 不同。
- 折叠进簇的边：presence=suppressed + rule_id=cluster.folded；`data_edge_ids` 映射回 DataSource（R-3）。
- hop 预算耗尽：候选边 suppressed + rule_id=hop.budget（不 unknown）。
- 关系源未加载：unknown + rule_id=source.unavailable（不 shown）。
- 维度 fail-closed：整个 ViewModel 构建失败（错误码），不得部分渲染。

**U 映射**：U-10、U-16、U-17、U-27、U-30。

**建议裁决**：采纳 present 集成规则；维度只改 presence/selection；类型/标签不变；rule_id 可枚举；全展开也经 present。

**证据等级**：A（S0-6 冻结 present/presence/rule_id；S0-3 维度定义；SE M-6）；**本项目假设**（rule_id 具体枚举由 S4 冻结）。

---

## 13. S1-13 维度与 UI/导航契约

**定义/规则（一句话）**：维度切换是 **Presentation/导航层动作**（S5 状态机），生成新 `VIEW_FRAME`；ViewModel 只携带 `dimension_id`（渲染所需），**不含切换控件、维度列表、导航历史或模式**（D-4）。

**形式化**：
```
Presentation：维度选择控件（toolbar/settings）→ 调 S5 switch_dimension(target_id)
S5：nav_state.dimension_id 更新；新 frame=(level, view_family, dimension_id, focus, hop_budget, mode)
    hop 重置为目标维度 hop_default；focus 若在目标维度可表示则保持，否则映射（S5 规则）
ViewModel：含 dimension_id/level_id/view_family_id（渲染标签）；不含 mode/nav/capabilities
Renderer：只吃 ViewModel，事件仅 nodeClick/edgeClick/backgroundClick；不处理维度切换
UI 标签：维度名/说明来自 registry（Presentation 读取），不写进 ViewModel
回退：切回上一维度 = S5 历史栈动作（不是 ViewModel 字段）
```
**机检条件**：
```
- ViewModel 字段无 mode/nav/breadcrumb/capabilities（D-4）
- Renderer 事件仅 nodeClick/edgeClick/backgroundClick；无维度切换/模式事件
- 维度切换只改 VIEW_FRAME.dimension_id；ViewModel 只读 dimension_id 标签
- 切换后 frame.hop == target_registry.hop_default（重置）
```
**反例**：
- ✗ ViewModel 携带 `dimension_list` / `mode` / 导航历史（D-4）。
- ✗ 渲染器内部处理维度切换（应 Presentation/S5）。
- ✗ 切换维度时静默丢 focus 且不提示（S5 需映射/提示）。
- ✗ 维度名/说明写进产品事实源。

**边界用例**：
- H→A：level/family 不变，视图节点扩展；返回 H 时 focus 若仍是块则保持。
- A→H：hop 重置 1（level）；A 挂接节点不进入 H 视图（视图不同）。
- 目标维度 reserved：S5 收到 fail-closed 错误并提示，不切换。
- 全展开（Presentation 模式）与维度正交：先切模式再切维度，两者互不写入 ViewModel。

**U 映射**：U-7、U-8、U-9、U-25、U-33、U-34（逐项）。

**建议裁决**：采纳"切换属 Presentation/S5，ViewModel 只含 dimension_id 标签"；接口 `switch_dimension(target_id) → new frame` 由 S5 定细节。

**证据等级**：A（S0-9/D-4 冻结 ViewModel 纯度；`ENGINEERING-PLAN.md:217,276` VIEW_FRAME 单 dimension_id + mode 在 frame；现无维度 UI，`graph-settings.js:38` 仅风格）；**本项目假设**（S5 切换接口签名）。

---

## 14. S1-14 维度与 agent

**定义/规则（一句话）**：agent 只能**请求确定性取景服务**并指定 active `dimension_id` 与参数；服务用 registry 校验并返回 ViewModel/错误；agent 不得注册维度、不得改渲染状态、不得拼装 ViewModel。

**形式化**：
```
服务签名（设计，S9/S7 冻结实现）：frame(DataSource, frame_spec) -> ViewModel | FailClosed
  frame_spec = {level_id, view_family_id, dimension_id, focus_id, hop_budget, mode?}
agent 允许：
  - 读 DataSource/registry（只读）
  - 调用 frame()，传 active dimension_id + 参数
  - 提议 frame_spec（S7 策略）
agent 禁止：
  - 写 registry / status / version
  - 写 ViewModel/presence/rule_id
  - 改渲染状态/布局/导航
  - 使用 reserved/deprecated/unknown 维度
错误语义：
  DIM_UNKNOWN / DIM_NOT_ACTIVE ⇒ fail-closed 返回错误；调用方可显式改请求 H（fallback=true 审计），
  但服务不得静默替换维度
确定性：同 DataSource+frame_spec+registry edition ⇒ 同 ViewModel；无会话态/随机
审计：每次 frame 请求记录 {dimension_id, hop, focus, registry_sha, status=ok/fail}（不记正文）
```
**机检条件**：
```
- frame() 为纯函数：同 (DataSource, frame_spec, registry edition) 输出相同
- 请求 dimension_id 必须 active；reserved/deprecated/unknown ⇒ 错误码，不静默替换
- agent 侧无可写 ViewModel/presence/registry 的接口（allowlist 检查）
- frame 请求审计字段：dimension_id/hop/focus/registry_sha/status
```
**反例**：
- ✗ agent 在代码里拼装 ViewModel/自己写 presence。
- ✗ agent 使用 reserved `time` 请求时间视图。
- ✗ 未知维度静默 fallback H 且不审计。
- ✗ agent 写 registry 添加新维度。
- ✗ 同一请求两次结果不同（取景非确定）。

**边界用例**：
- agent 请求 A hop=2：服务按 registry hop_max 截断为 2 或不支持时 fail-closed（不可自行扩大）。
- agent 请求 H 到深层：服务返回当前层；深层通过多次 frame（focus 更新）或 S5，不由 agent 直接改导航。
- registry 不可用：服务 fail-closed，agent 显式降级（不返回猜测图）。
- 跨 KB：DataSource 单 kb（S0-8），拒绝。

**U 映射**：U-2、U-29、U-32、U-35（S9 接口）。

**建议裁决**：采纳"只读取景服务 + active 维度白名单 + fail-closed + 审计 + 确定性"；agent 不得改渲染状态（S0-10）。

**证据等级**：A（S0-10 冻结；S0-8 单 DataSource；`ENGINEERING-PLAN.md:301-303` P9 只读、取景服务端）；**本项目假设**（frame 签名/审计字段）。

---

## 15. S1-15 其他维度候选清单（仅 reserved）

**定义/规则（一句话）**：v1 只登记候选维度为 `reserved`（一句话定义 + 草案 + 为何 v1 不做），不实现、不进 ctx/渲染；晋升须 S1 修订 + 证据 + 审批（S1-3）。

| id | 一句话定义 | basis 草案 | 关系源草案 | 为何 v1 不做（理由） |
|---|---|---|---|---|
| `time` | 按 KP/边的有效时间（valid_from/valid_to）取景 | time_axis | 现有边 + 时间字段 | 字段"只存不用"（ontology §2.2）；无覆盖率/无机器可判定口径；U-25 槽位 |
| `evidence` | 按断言证据强度/证据类型取景（asserted/inferred/missing、锚点质量） | provenance_evidence | edge provenance | 与 semantic/structural 标签重叠；T3 消费者准入未定（S7/S8）；无评测 |
| `task` | 按 agent 任务上下文/目标取景（任务相关子图） | task_context | agent session/task 派生 | 任务上下文非持久事实；隐私/不可复算；S7/S9 才定 |
| `controversy` | 按 L2/G2 争议/裁决状态取景（有争议/已裁） | research_dispute | 研究判定产物 | 研究侧产物不得成为产品事实；无产品消费需求；等 S8 |
| `authorship` | 按作者/标注者取景 | authorship | 审计身份字段 | 身份字段覆盖不全、隐私；无 v1 消费场景 |

**规则/机检**：
```
- 每条 reserved：id/name/status=reserved/version=0.0.0-reserved/definition/why_not_v1/draft；
- 不得有可执行 basis.kind（reserved 专用）；不得出现在 active 集合/ctx；
- 机检：registry active 集合 == {hierarchy, association}；reserved ids 集合 ⊇ 上表；reserved 不进渲染分支（grep/CI）。
```
**反例**：
- ✗ v1 实现 `time` 维度并用 invalid 字段（valid_from 未实现）。
- ✗ 把 evidence 当第二套 semantic 标签。
- ✗ 用 task 维度把 agent 会话状态写进产品图。
- ✗ 把研究争议图（L2/G2）物化为产品维度。

**边界用例**：
- 候选可只登记一句话 + why_not_v1（不要求完整 schema）。
- 同一候选未来可作为 non-dimension filter（如 UI 过滤）而非维度——需另行评审，不得借 reserved 实现。
- 晋升顺序由 S1 修订；v1 不晋升任何 reserved。

**U 映射**：U-9、U-12、U-25、U-30。

**建议裁决**：采纳 5 个 reserved 槽位与"v1 不晋升"；后续按 S1-3 晋升条件评审。

**证据等级**：A（U-25/U-9/U-12；ontology §2.2 T 轴只存不用 `:74-75`）；**本项目假设**（候选清单/草案字段）。

---

## 16. 覆盖矩阵（U + S0 条款）

### 16.1 U 覆盖（S1 相关）

| U# | 要点 | S1 落点 |
|---|---|---|
| U-8 | 层次维度 | S1-1/S1-2/S1-4 |
| U-9 | 其他维度 | S1-2/S1-3/S1-15 |
| U-10 | 关联维度（包含/引用/语义关联） | S1-5（E_relation_min）/S1-6 |
| U-11 | 跳数 | S1-7 |
| U-12 | 更多维度 | S1-3/S1-15 |
| U-25 | 开放槽位 | S1-3/S1-15 |
| U-30 | 关联维度具体定义 | S1-5 |
| U-32 | 规模/后端检索 | S1-9/S1-14 |
| U-33 | 2D/3D 不分家 | S1-1/S1-13 |
| U-34 | 逐议项/不设上限 | 本文逐项结构 + S1-9 预算说明 |

> 其余 U（U-1..U-7/U-13..U-24/U-26..U-29/U-31/U-35）由 S0/S2/S4/S5/S7/S9/S10 覆盖，S1 不扩范围；S0 冻结覆盖矩阵已登记全 35 条（`S0-terms-v1.md:114-155`）。

### 16.2 S0 条款一致性

| S0 条款 | S1 落实 | 冲突检查 |
|---|---|---|
| S0-2 层次/partition | H 复用 `(level, view_family)` 划分（S1-4） | 无：H 不改 partition 规则 |
| S0-3 维度/E_relation/R-1 | S1-2 schema、S1-6 只增不删 | 无：E_relation(D) ⊇ min |
| S0-5 一跳/dir/跨维重置 | S1-7/S1-8 | 无：A 默认 hop=1；H 用 level-hop 不破一跳语义 |
| S0-6 present/presence/rule_id | S1-12 | 无：维度只改 presence |
| S0-7 多归属 | S1-3/S1-5 不写 membership；跨族重叠允许 | 无：维度不定义 membership |
| S0-8 默认/全展开 | S1-13 模式属 Presentation；维度正交 | 无：ViewModel 无 mode |
| S0-9 VM 纯度/kind | S1-13 只给 dimension_id；无 nav/mode | 无 |
| S0-10 agent 边界 | S1-14 只请求确定性服务 | 无 |
| S0-11 v1 范围外 | S1-15 不实现候选；S1-6 不新增类型 | 无 |
| R-1/R-2/R-3 | S1-2/S1-5/S1-12 | 无 |
| D-4/D-5 | S1-13/S1-10 | 无 |

---

## 17. 仍存争议 / 待 Lead·SE 裁决

1. **H 的 hop 语义**：本提案把 H hop 定义为"层偏移"（v1 max=1，逐层导航）；另一种观点是 H 不设 hop，只有导航。需 Lead 裁决 H 是否算 hop（影响 S1-7 与 S0-5 表述）。
2. **A 的 hop_max=2**：v1 是否允许两跳（U-22 的"更深"）；本提案默认 2、可配；保守方案是 v1 max=1（严格一跳）。需 Lead 决定。
3. **H 的 relation_sources**：R-1 要求 active 维度 `E_relation(D) ⊇ min`，但 H 只用 contain 下降；本提案把其余源作为"可见端点上下文边"处理（不新增节点）。SE/Lead 需确认 H 是否允许上下文边，或 H 只显示 contain。
4. **status 枚举**：本提案 `{reserved, active, deprecated}` + 版本冻结属性；需确认与 A-v2 `{reserved,specified,frozen,deprecated}`/B active 的映射（ENGINEERING C-5）。
5. **registry 持久化位置/格式**：设计期注册表放设计产物还是 S6 配置；S6a 定存储（非事实源）。

---

## 18. 证据锚索引（详见 `S1-evidence-A.md`）

```text
原话：docs/design/multilevel-graph-vision.md:25-29（U-8..U-12）、:64（U-25）、:69（U-30）、:71（U-32）、:72（U-33）、:73（U-34）
冻结：docs/design/multilevel-graph/S0-terms-v1.md:35-41（S0-3/R-1/R-2）、:49-54（S0-5）、:56-61（S0-6/R-3）、:75-79（S0-9/D-4）、:81-85（S0-10）、:87-90（S0-11）、:98-107（R/D）
冻结记录：S0-FREEZE-RECORD.md:13（sha）、:37-46（冻结摘要）、:48-53（未关闭项）
议程/章程：multilevel-graph-seminar-agenda.md:26-28,51-57；S1-charter.md:25-41,43-51
工程：ENGINEERING-PLAN.md:149-153（DIMENSION）、154-163（VIEW_FRAME）、164-173（VIEW_MODEL）、:216/:290（C-5 status 待补）、:229-247（VM 字段）、:301-303（取景服务/P9）、:343-345（registry CFG）
代码：graph-view-2d.js:617（graphStyle 视觉风格）、graph-settings.js:38（graphStyle）、graph-engine.js:167-181（loadPayload 全量 payload）、edge_types.py:9-17（EDGE_TYPES 枚举）、document.py:2124（get_graph_data）、collector.py:46-99（DataSource）
```
**复跑机检**：见 S1-evidence-A.md §5（12 议项完整性、U 覆盖、代码锚、fail-closed 反例清单）。
