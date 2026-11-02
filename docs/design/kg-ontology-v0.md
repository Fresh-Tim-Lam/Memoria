> **状态**：**v0.2 冻结**（2026-11-02T11:48+08:00；v0 → v0.1：仅加 edges[] 可选 provenance 字段；v0.1 → v0.2：再加可选 contain_kind，无新类型、不 bump schema_version）
> **v0.1 补丁记录**：`dec-20261101-p01reopen`（人批，2026-11-01T19:05:00+08:00，见 `team/decisions.jsonl`）；变更清单与回滚见 §11。
> **v0.2 补丁记录**：`dec-20261102-3b8e6eb6`（人批，2026-11-02T11:48:21+08:00，「落地方案B」）；只加可选 `contain_kind`，无新类型、不 bump `schema_version`。
> **来源**：4 份独立提案 → Lead 并集（0 自创）→ 4 份交叉异议 → 13 条裁决。
> **可复核**：`artifacts/agent/verify/debate/kg/`（PROPOSAL×4 / PHASE2-UNION / PHASE3-OBJECTION×4 / PHASE4-RULINGS / ruling/rulings-kg.jsonl）
> **协议**：`artifacts/agent/verify/debate/PROTOCOL.md`（FROZEN；M1 证据优先 / M2 独立根 >1 / M3 登记未知 / E1 证据身份）
> **本文件的权力**：它是 KG 设计在 v0 范围内的**单一事实源**；与 `kg-research-phase*.md`（task-86 调研）冲突时以本文件为准。

# 知识图谱设计 v0（辩论冻结版）

## 0. 一句话结论

> **本项目当前的"图谱"是"链接图"，不是"关系图"。**
> 边（edge）在代码里已经与链接（link）解耦，但契约没承认；边类型系统 100% 退化到单一默认值；
> **agent 侧从不读边**（两条独立证据链）；**"边有没有用"当前在实现上不可测**。
> ⇒ v0 不加任何新概念，只修契约缺陷 + 补埋点 + 冻结测量口径。

## 1. 四条经多根确认的事实（不是主张，是事实）

| 事实 | 独立根数 | 证据 |
|---|---|---|
| agent 的检索 / 选节 / 读取 / 写作 / 复习路径**完全不读边** | **2** | `get_graph_data()` 在 agent 侧无调用者；19 条读取点清单 + 零读取点表；35 个真实会话 `edge_type` 命中 0 |
| 类型系统当前**无信息量** | **4** | 全部快照 100% `reference`；`relevance` 100% 默认 0.7 |
| 让 agent/人填类型**不工作** | **3** | `EDGE_TYPES` 3 种 vs `PLAN_EDGE_TYPES` 2 种（不对称）；`contain` 禁手标；35 会话 0 次 `edge_type` |
| **图谱与 agent 检索是两套未打通的数据通路** | **2** | 上述两条独立到达 |

**推论（v0 的设计前提）**：
```
边服务的是【人看的图】+【写质量诊断】，不是 agent 推理。
任何"为 agent 加边能力"的设计，必须先证明它能改变一个 agent 决策（当前一个都没有）。
```

## 2. 概念模型（v0 定名）

```
Link（链接）   正文锚点：为什么这段文字能跳过去。带 instances 行号。
                不承诺语义关系。可以有、可以没有对应 edge。
                类型空间（v0）：reference（无断言跳转）/ extend（延伸）——【2 种】

Edge（边）     语义关系：两个知识点是什么关系。
                纯边无行号；由 link 投影时才带锚点。
                类型空间（v0）：contain（整体-部分，派生）/ reference（无断言）/ extend
                ——【3 种，但 agent 只能设 2 种】

二者关系       代码层【已解耦】（有 link 无 edge、有 edge 无 link 均可发生），
                但【共用一套枚举】且 contain 在 link 上被【静默改写成 reference】
                ⇒ 这是 v0 要修的契约缺陷，不是"要不要解耦"的问题
```

### 2.1 `reference` 的定名（重要，v0 的新裁）

```
reference 既不是"纯边"也不是"不是边" —— 它是【无断言跳转的内部投影值】。
· 语义上：不进语义边集（它不承诺任何关系）
· 数据上：保留字段值，不无条件降级为 link
  因为 HEAD/live 有 2–3 条【无正文锚点的纯 reference 边】无法降级
  且映射保真度测量（M-08/M-09）需要边侧类型
```

### 2.2 `edges[]` 可选 provenance 字段（v0.1 新增；不改变边/链接定义）

> 目的：让"边/链路是否被作者断言"可核（G4 C8），L2/L3 真值不再只依赖节点区间弱证据。
> 边界：**只加字段、不新类型、不改 link/edge 概念模型、不 bump `schema_version`（保持 1）**；旧数据无这些键时行为与 v0 完全一致。
> 字段语义与取值来源：`G5-board-design.md` §2.2（G5.1 冻结版）与 `g5-schema-fixtures/schema-edge-provenance.v0.1.json`（accepted-for-G5b）。

| # | 字段（G5 计 7 组） | JSON 键 | 类型/取值 | 必填 | 说明 |
|---|---|---|---|---|---|
| 1 | `derived_by` | `derived_by` | `author` \| `system_range` \| `system_link` | 否 | 谁产出了这条边；`derived` 布尔保持不动 |
| 2 | `provenance_state` | `provenance_state` | `asserted` \| `inferred` \| `missing` | 否 | 断言出处三态；旧数据缺省视为 `missing` |
| 3 | `assertion_source` | `assertion_source` | `{file, line_start, line_end, quote_sha256?}` | 否 | 作者断言出处；仅 `asserted` 时必填 |
| 4 | `instances` | `instances` | `[{file, line}, ...]` | 否 | 可多锚点，与 `links[].instances` 同构 |
| 5 | `generator_version` | `generator_version` | `contain-vN` \| `null` | 否 | 仅 `system_range` 边：派生算法版本（可复算） |
| 6 | `valid_from` + `valid_to` | `valid_from`, `valid_to` | date \| `null` | 否 | T 轴只存不用（G5 AS5，未实现） |
| 7 | `confidence` | `confidence` | 0–1 \| `null` | 否 | 仅 L2 判据过闸后允许写 |
| 8 | `contain_kind` | `contain_kind` | `structural` \| `semantic` | 否 | v0.2：contain 边的包含类型；缺省按 structural（语义未验证） |

```yaml
# sidecar edges[] 条目可选扩展（全部可选；不存在 = 旧行为）
edges:
  - type: extend|reference|contain      # 不变（3 类）
    source_id: <kp_id>                  # 不变
    targets: [<kp_id>]                  # 不变
    relevance: 0.0-1.0                  # 不变
    derived_by: author | system_range | system_link      # 可选
    provenance_state: asserted | inferred | missing      # 可选
    assertion_source:                                    # 可选（asserted 时必填）
      file: 教材/03_….md
      line_start: 5
      line_end: 5
      quote_sha256: <sha256?>
    instances: [{file: 教材/03_….md, line: 5}]           # 可选
    generator_version: contain-v1                        # 可选（仅 system_range）
    valid_from: null                                     # 可选（T 轴只存不用）
    valid_to: null
    confidence: null                                     # 可选（仅 L2 后）
    contain_kind: structural | semantic                   # 可选（v0.2，仅 contain 边）
```

规则（引自 G5.1 §2.2，写死）：
- 作者边（`origin=sidecar_edge`）目标 `provenance_state=asserted` + `assertion_source`；未回填前只能 `missing`/`inferred`，不得冒充断言。
- `contain` 派生边不写 `assertion_source`，写 `derived_by=system_range` + `generator_version`；出处由 KP `range` 复算。
- `confidence` 不得由作者手写，只能由 L2 判据过闸后写入。
- UI/既有代码**不读**新字段（`derived` 布尔冻结）；新字段消费者仅研究脚本与 G5b 透传路径。
- `contain_kind` 只用于 contain 边：系统派生边固定 `structural`；`semantic` 只能来自作者/人工 curation 且必须带 `assertion_source`；旧数据/缺字段按 `structural`（fail-safe，不假设语义成立）。



### 2.3 `contain` 的两种含义：结构包含 vs 语义整体-部分（v0.2 新增）

> 来源（人，2026-11-02）：「文本上的 contain 不一定真实具有 contain 的语义，所以有必要做一些区分，
> 别让程序自动一视同仁处理为 contain 边。」批准重开 v0.2：`dec-20261102-3b8e6eb6`。
> 研究证据：`artifacts/agent/verify/debate/graph-utility/CONTAIN-SEMANTICS.md`、
> `contain-evidence.json`（33/33 contain 仅由 KP range 几何包含生成；14 个消费读取点无一检查 derived_by）。

| 值 | 含义 | 来源 | 消费者必须怎么读 |
|---|---|---|---|
| `structural` | 仅"B 的知识点区间在 A 的区间内"这一结构事实；**不承诺**整体-部分语义 | 系统派生（`derive_contain_edges()`），派生层静态写入，不写 sidecar | 读作"结构包含候选，语义未验证"；不得作为语义链路 |
| `semantic` | 作者/人工 curation 明确断言的"整体-部分"关系 | 作者流程或人工 curation，**必须**同时有 `assertion_source` 作者证据 | 可作语义关系；缺证据即降级为 structural/unknown |

规则（写死）：
1. **禁止无消费通路的影子写**：`structural` 由派生层生成，不写 sidecar。`semantic` 允许以 sidecar `edges[]` 的 **curation overlay** 持久化，但必须同时满足（a）collector 在 dedupe 之后按 canonical id 合并（M8a，有真实消费通路）；（b）overlay 只覆盖 `contain_kind/derived_by/assertion_source` 三字段，几何字段不动、`generator_version` 移除；（c）**仅人确认可写**（`curate_contain` 要求 `confirmed_by`；agent 只能提议、不得落库）；（d）孤儿不造边、重复冲突拒绝、锚点 stale 拒绝。该修订由 `dec-20261102-2dcefd31`（人批）批准；D4 审计身份仍未决，最小切片复用 agent session 作审计，不宣称“纯人路径审计已满足”。
2. 旧数据/无字段 ⇒ 视为 `structural`（fail-safe：不假设语义成立，也不删除边）。
3. `semantic` 必须带 `assertion_source`（schema `allOf` 强制）；程序不得自动推断 `semantic`。
4. 不 bump `schema_version`（保持 1）；本补丁只加可选字段。
5. 消费侧：UI 文案必须区分两种含义；agent/G6 读边时 `contain_kind!="semantic"` 不得计入语义链路（G6 门禁，`dec-20261102-7b140e94`）。

## 3. v0 交付清单（6 件：5 件"修缺陷" + 1 件 v0.1 可选字段扩展）

| # | 事项 | 为什么必须做 | 依据裁决 |
|---|---|---|---|
| ① | **统一归一化器**（消除 link/edge 枚举不对称） | 去 agent 参数不消除不对称——不对称在 `PLAN_EDGE_TYPES` 常量（`plan.py:421` 用它做校验） | D-KG-04 |
| ② | **静默改写留痕 warn** | `contain` 在 link 上被静默改成 `reference`（`edge_types.py#L61-L66`），且 task-86 的 **D3(c) 已裁「回落留痕 warn」** ⇒ 当前实现**违反已裁规则** | D-KG-04 |
| ③ | **一致性断言测试** | 锁住"两端枚举不对称"这个事实，防回退 | D-KG-04 |
| ④ | **边使用埋点** | `nodeClick` 有事件但**零统计消费**，`edge_id` 从未被记录 ⇒ 不埋点则"边有没有用"永远不可测 | D-KG-07 |
| ⑤ | **语料冻结脚本入库 + 三元组规则** | 四家测出四个数字（479/454/408/429/404）⇒ 没有冻结口径就没有可比性 | D-KG-01 |
| ⑥ | **边 provenance 可选字段（v0.1）** | `edges[]` 无 provenance ⇒ "作者是否断言"不可核，L2/L3 真值只能靠节点区间弱证据（G4 C8） | dec-20261101-p01reopen |

### 埋点位置（D-KG-07 给定，三处）
```
src/memoria/ui/static/app/js/app.js:1438         onGraphNodeClick（来源标记已有，缺计数）
src/memoria/ui/static/app/js/graph-view-2d.js:521 _emit("nodeClick")（缺 edge_id）
src/memoria/ui/static/app/js/app.js:5575          （缺边级归属）
```

## 4. v0 明确**不做**（5 条，每条都有裁决依据）

| 不做 | 依据 |
|---|---|
| ❌ 加任何新语义类型（prerequisite / sequence / contrast / exemplify） | D-KG-05：三根独立收敛；`prerequisite` 全库 **1 条**、`sequence` **0 条**、`contains` **0 条**（词典型库不可产生） |
| ❌ 拆 `link.type` / `edge.type` 两个字段 | D-KG-04：数据为 0 时收益无法验证 |
| ❌ prerequisite 链视图 | D-KG-09：0.5 范围内 ego-only 成立（B 已自行撤回 v0 的 prerequisite） |
| ❌ 「6 场景 = 6 视图」 | D-KG-10：**单根主张**（A/C/D 未独立支持）⇒ 降级为待验证假设 |
| ❌ 反向邻接 agent 接口 | D-KG-10：C 自己要求先 A/B；且埋点不存在 ⇒ A/B 做不了 |

## 5. 测量规程（v0 强制）

### 5.1 语料冻结（D-KG-01，最高优先）
```
语料       git archive HEAD docs/example
语料身份   ⚠️ 旧「语料 sha 051deb78…/182 文件」【已失效，禁止再用】
           （2026-10-26 实测：该 sha 无法对应任何可从 git 复现的状态）
测量源     现场 collect_graph_data()
严禁       .memoria/build/graph.json（可再生缓存，非事实源）
排除       .memoria/{agent,build,cache}
live 引用  必须带 worktree manifest sha（如 52cc2ca0…）+ 时间
强制格式   (HEAD sha, manifest_sha256, 测量时间) 三元组 —— 缺一即 E1 无效
           ⚠️ 判「语料是否一致」看 manifest_sha256，不看 artifact_sha256（后者含时间戳）
           ⚠️ 当前语料【不可从 git 复现】：git archive HEAD docs/example = 61 节点/154 边，
              工作区 AAA_Vocab = 134 节点/404 边；方案1（构造可复现语料）实测不可行
              ⇒ manifest_sha256 是唯一身份；工作区一变即永久失效且无法回滚
              冻结值：HEAD d9341bd1（dirty）/ manifest a6866c46cab71c43… / 294 文件 / 134 节点 404 边
```

### 5.2 口径代号（D-KG-02，C4 结案；**2026-10-25 20:40 更正**）

> **⚠️ 更正（2026-10-25T20:40，来自 KGViz 研讨会 Phase 1 [arch-contract] 的发现，Lead 已核实）**
>
> 我原裁决把 404 vs 454 归因为"快照不同 / 口径不同"，**这是不完整的**。真实原因是**两条后端路径**：
> ```
> src/memoria/services/document.py#L2124-L2132  get_graph_data() → collect_graph_data()   ⇒ 404 边
> src/memoria/services/document.py#L2134-L2141  build_kb()       → build_knowledge_base() ⇒ 454 边
> ⇒ 【前端只走 get_graph_data / collect_graph_data 那条】
> ```
> Lead 已 independently 核实（`collector.py:44` 与 `document.py:2134` 是两个不同函数）。
> **「100% reference」在两条路径上都成立，所以原结论不变**；但**绝对数字的分歧根因要改**：
> 不是"时刻不同"，而是**"函数不同"**。
> **进一步推论**：若某设计依赖 454 那套边集，它与前端看到的 404 套**不是同一份数据** ——
> 这类"两条路径看不同世界"的问题，与 D-KG-12 的「图谱↔agent 未打通」是同一类架构缺陷。
>
> **⚠️ 残差 A（2026-10-26，D-KGV-10）：`kb_build` 是【破坏性迁移】，上面"两条只读路径"的说法低估了它**
> ```
> kb_build.py#L293-298  strip_known_wikilink_edge_hints 后 open(full,"w") 【真的写回源 md】
> kb_build.py#L312     save_sidecar_for_md 【真的写回 sidecar】
> 同一临时副本实测：build 前 collector 404 边 → build 后 collector 454 边
> ⇒ 「404 vs 454」含 build 对源数据的一次性迁移副作用，不只是"函数不同"
> ```
> ⇒ **任何边/degree 测量必须记录 build 状态（pre_build / post_build + build sha）**，否则数字不可比。

```
479        links 总数（task-86 快照）    ⚠️ 曾被误当 edges，不得再作边数引用
454        edges（kb_build 路径 / task-86 快照）  ⚠️ 前端看不到这套
408        edges（build cache 10-23）     ❌ 无效
429 / 404  links / edges（**collect_graph_data 路径**，前端实际用的）  ✅ 须带 manifest sha
160 / 154  links / edges（HEAD 冻结语料，口径待与上面两条对齐后再定）
```

### 5.2b 节点字段现状（KGViz 研讨会 Phase 1 实测，影响"节点大小"类设计）
```
collector.py#L61-L70 产出的 node 字段（经 entry_to_dict 展开）共 9 个：
  id / name / label / description / file / kp_id / start_line / end_line / range_ok
⇒ 【没有 degree，没有任何视觉驱动字段】
⇒ 度数现在由前端 _galaxyStats() 现算（graph-view-2d.js#L546-553），
   且【只在 graphStyle === "galaxy" 时使用】；默认风格是 force ⇒ 度数算了却没用
```

### 5.3 指标裁决（D-KG-07）
```
主验收       可视图元数 ≤10
negative gate 最大分组占比（【实测 >80% 触发】；不能当验收）
              ⚠️ 残差 B（D-KGV-11）：原写「99.2%」是【过期数字】（来源：更早语料），
                 当前可复现语料实测 HEAD 81.97% / live 89.55% ⇒ 99.2% 阈值【永远不会触发】
                 = gate 不存在 ⇒ 已改为 80%
撤回          M-05「边利用率 ≥15%」—— 无来源，撤回
替换          「只建基线，不设阈值，下版本比自身趋势」
token         【效率轴】，不是有效性轴
禁用判据     长度 / 行数 / 块数 —— 它们可相互抵消（本轮真 bug 就藏在净长度巧合里）
```

## 6. v1 前置条件（不满足就不做）

### 6.1 新语义类型的准入（三件缺一不可）
```
① 强制填写机制（让人能低成本标注，否则永远 0 数据）
② 三闸全过：区分度 ≥10 条或 ≥5% / relevance 异质度 std>0 / 决策绑定
③ ≥10 实例的人工确认
```
**v1 候选排序**：`contrast`（25 条 / 5.83%）> `exemplify`（14 条 / 3.26%）
**关键裁断**：不是"加不加"，而是「**先产生结构化候选，再过闸1**」——
B 的证据在**正文文本**里，不在**数据字段**里。

### 6.2 agent 边能力的前置
```
唯一值得建的是【反向邻接】（谁引用了我）
现状：只能扫全库 sidecar = AAA_Vocab 43,880 tok
接口化后 ~27–60 tok（平均入度 3.04 × ~9 tok/条）≈ 488×
但：必须先 A/B 证明它改善回答质量（token 省了 ≠ 更有用）
```

## 7. task-86 既有裁决的存废

| task-86 裁决 | 本文件结果 |
|---|---|
| **D1** 本体 4 类（contain/reference/prerequisite/exemplify） | ❌ **推翻**（D-KG-08，4 根独立） |
| **D2** 跨域边允许但默认过滤 | ✅ 保留（+ 约束：默认必须先过滤语义层） |
| **D3** 回落 + 机读留痕 | ✅ 保留；**且发现当前实现违反它** ⇒ v0 必修 |
| **D4** 0.5 只做域概览 + ego | ✅ 在 0.5 范围内保留（D-KG-09） |
| **D5** 默认 force + 毛球提示 | ✅ 保留 + 约束 + 判据（曝光→点击 <10% ⇒ 提示无效） |
| **D6** 不补外部对标 | ⚠️ **拆两半**：产品对标保留 / **设计阶段外部研究推翻** |

## 8. 登记的未知（不假装解决）

| # | 未知 | 为何仍未知 |
|---|---|---|
| U-1 | 边对 agent 的价值 | 埋点不存在 ⇒ A/B 做不了（C 自己要求先 A/B） |
| U-2 | 外部业界调研 | 未做（A 自承是真实缺口；D6 已推翻"设计阶段不做"） |
| U-3 | 2D/3D 方向可读性 | M-11 埋点未落 |
| U-4 | 用户库受"尾换行丢失"影响比例 | 与 KG 无关，另案 task-147（R0） |
| U-5 | `contrast`/`exemplify` 能否被低成本标注 | v1 前置条件之一 |

## 9. 本轮辩论自身的教训（写下来防重犯）

```
① 单 agent 研究（task-86）能产出"有报告、有数据、有指标"的结论，
   但它【不会自我质疑前提】—— D1 的 4 类是从"代码已有 3 类"反推的，
   不是从学习场景推的，而它当时没意识到这一点。
② 辩论的价值不在"多几个人"，在于【有人被要求去证伪别人的主张】。
   四份提案全部主动推翻了自己的核心主张（含 Lead 转述给我的 479）。
③ 绝对数字会骗人：四家测出 479/454/408/429/404，
   但"100% reference"在【四个快照上全成立】⇒ 结论稳、数字不稳。
④ 单根主张不能关闭争议（M2）：B 的「6 场景=6 视图」只有它一个根，
   所以即使它证据最多，也只能记"待验证假设"，不能记"成立"。
```

## 10. 复核方式

```bash
# 冻结语料重测（第三方可复跑）
python artifacts/agent/verify/debate/kg/evidence/kg_corpus_freeze.py --json /tmp/freeze.json

# 机读裁决
cat artifacts/agent/verify/debate/kg/ruling/rulings-kg.jsonl | python -m json.tool
```

## 11. 变更记录（v0.1）

| 版本 | 日期 | 变更 | 批准 |
|---|---|---|---|
| v0 | 2026-10-25 | 初版冻结（5 件交付清单） | — |
| v0.1 | 2026-11-01 | 仅新增 §2.2 `edges[]` 可选 provenance 字段（7 组/8 键）+ §3 交付项 ⑥；类型空间、link/edge 定义、`schema_version` 均不变 | `dec-20261101-p01reopen`（人批） |

**回滚**：v0.1 只改本文件文本、无数据迁移、未 bump `schema_version`；**已提交后**回滚用 `git revert <v0.1-commit>`（或 `git checkout <v0-commit> -- docs/design/kg-ontology-v0.md`）——不要用 `git checkout -- <path>`（提交后它恢复的是 v0.1）。回滚验证：文件 sha 回到 `84bfa8844ce79721c9602bf66ab2d2a4fee119d9c46129951ecdb0f919b4cf8b`，且 §2.2/§11 不存在。
