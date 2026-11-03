# S1 章程：维度体系（层次维度 + 关联维度 + 开放槽位）

> **依据（不可改写）**：`multilevel-graph-vision.md`（U-1..U-35，两轮原话）；
> **上游冻结**：`S0-terms-v1.md`（sha256 `241b1e1e…`，决策 `dec-20261102-a6af89e1`）+ `S0-FREEZE-RECORD.md`；
> 议程 V0.2；本场为 S0 之后第一场，**逐议项**（U-34）。
> **状态**：S1 章程 V1（Lead 起草）。本场冻结前不写产品代码。
> **日期**：2026-11-03（Asia/Shanghai）。

## 1. 目的

把 S0 的「维度 = 同一层次上的取景规则」落成**可机检的维度体系**：注册表、H/A 两个 v1 维度的精确定义、
`E_relation` 扩展规则、跳数/方向/终止条件、维度组合（v1 单维度）、开放槽位登记与失败关闭。
S1 必须**只增不删** S0 冻结的 `E_relation_min`（R-1）。

## 2. 不在范围

- 具体聚类算法（S2）、检索算法（S9）、视觉样式（S3）、导航状态机（S5）；
- 词/句级作为维度或层次（S0 已列为 v1 范围外）；
- 维度组合的完整实现（v1 单维度；组合只登记开放槽位）。

## 3. 议项清单（逐项裁决；一项未裁决不得跳下一项）

每项产出：**定义/规则**、**机检条件**、**反例**、**边界用例**、**U 映射**、**建议裁决**、**证据等级**。

| 编号 | 议项 | 必须回答 |
|---|---|---|
| S1-1 | 维度定义与边界 | 维度 ≠ 层次、≠ 视觉风格、≠ 全展开；维度的判定条件；一个「取景规则」最少包含哪些字段 |
| S1-2 | 维度注册表 schema | 字段（id/name/basis/relation_sources/direction/hop_default/hop_max/termination/status/priority）、版本、校验、未知维度 fail-closed |
| S1-3 | 开放槽位登记（U-25） | reserved 维度的登记格式；reserved 不得进渲染分支；如何从 reserved 晋升为 active（条件/评审/版本） |
| S1-4 | H（层次维度）精确定义 | basis=层次划分；取景范围；方向；终止（到 KP 叶子）；与 S0-2 划分/`view_family` 的关系 |
| S1-5 | A（关联维度）精确定义（U-10/U-30） | 「显示平时不显示的关联节点」如何判定；关系源 = `E_relation_min` + 扩展；包含/引用/语义关联如何计跳；与 S0-5 一跳的关系 |
| S1-6 | E_relation 扩展规则（R-1 只能加） | 新增关系源的准入条件、分类、验证器、示例；删除为何必须重开 S0；新增后对 A 的影响 |
| S1-7 | 跳数（U-11） | `hop_default/hop_max` 语义；沿边计数还是沿节点计数；去重；切维度是否重置（S0-5 已定跨维重置）；预算与选择性渲染的关系 |
| S1-8 | 方向 `dir(D)` | 枚举与语义（H=down；A=both/可配）；in/out/both 的渲染差异；方向与一跳的关系；边界用例 |
| S1-9 | 终止条件 | 何时停止（层深上限/跳数/节点预算/无新节点）；「不设上限」与性能预算如何共存（U-32 规模不是问题，但要有显示预算）；终止必须可机检 |
| S1-10 | 维度组合（D-5） | v1 单维度激活；多维组合的开放槽位格式；组合顺序/优先级只登记不实现；切换语义 |
| S1-11 | 维度状态机与能力闸 | active/reserved/deprecated 状态；未知/保留维度 fail-closed；与 plugins 能力面的关系；状态持久化位置 |
| S1-12 | 维度与选择性渲染/边存无 | 维度如何进入 `present(e,ctx)`；维度切换时边 presence/type 的差异（U-27）；视图缺席≠数据缺席在维度下的表述 |
| S1-13 | 维度与 UI/导航契约 | 切换入口属于哪一层（Presentation）；是否进 ViewModel（S0 已定不进）；与 S5 导航状态机的接口 |
| S1-14 | 维度与 agent | agent 如何请求按维度取景（确定性服务）；维度参数化；agent 不可改渲染状态；与 S7/S9 的接口 |
| S1-15 | 其他维度候选清单 | 时间/证据/任务/争议等候选如何登记为 reserved（U-25）；每个候选一句话定义 + 为何 v1 不做 |

## 4. 预注册判据（会前写死）

1. 每个 v1 维度必须**可机检**：给定 (图, 维度参数) 能算出唯一视图集合；
2. 每个维度字段有类型/枚举/默认值/失败语义；未知 id fail-closed；
3. A 维度必须覆盖 U-10 的「包含关系、引用、语义关联」且 `E_relation` **只增不删** R-1；
4. 两份独立提案（A 主办 / B 复核）差异逐条列出并裁决，不许静默合并；
5. 覆盖矩阵（U-8/9/10/11/12/25/30/32/33/34 及 S0 相关条款）无缺失；
6. SE 工程校核必须确认注册表/跳数/终止/状态机可落到实体/数据流/状态图，且与 S0 的 VM 纯度、fail-closed 不冲突；
7. 不写产品代码、不改契约、不 commit（本场）。

## 5. 输入与预读

- 原话：`multilevel-graph-vision.md`；
- 上游：`S0-terms-v1.md`、`S0-FREEZE-RECORD.md`、`S0-terms-proposal-A-v2.md`、`S0-terms-proposal-B-v2.md`、`S0-RULINGS.md`；
- 工程：`ENGINEERING-PLAN.md`（ER/DFD/状态图 v0）、`S0-engineering-review.md`；
- 只读代码锚：现有维度/样式读取点（`graphStyle`、`graph-engine.js`、`graph-view-2d.js`），仅作现状证据，不得当作设计结论。

## 6. 角色与交付

| 角色 | 成员 | 交付 |
|---|---|---|
| 主办研究（提案 A） | `gm-seminar-researcher` | `S1-dimensions-proposal-A.md` + 证据文件 |
| 独立复核（提案 B + 异议） | `gm-seminar-verifier` | `S1-dimensions-proposal-B.md` + `S1-objections.md` |
| 软件工程专家 | `graph-se-architect` | `S1-engineering-check.md`（注册表/DFD/状态图可工程性 + 与 S0 一致） |
| 并集与裁决 | Lead | `S1-RULINGS.md` → `S1-dimensions-v1.md`（冻结候选） |

## 7. 冻结门禁

1. A/B 独立完成 + 差异清单 + 异议关闭（P0/P1 逐条证据）；
2. SE 工程校核 PASS（注册表 schema、跳数/终止/状态机可工程化，三图增量一致）；
3. Lead 独立机检（注册表字段、未知维度 fail-closed、E_relation 只增、跳数/方向/终止可机检、覆盖矩阵无缺失）；
4. 与 S0 无冲突（VM 纯度、`E_relation_min`、present 判据、kind 约束）；
5. 满足后冻结 `S1-dimensions-v1.md` 并写决策；否则回修订轮。

## 8. 变更控制

- S1 冻结后只允许加维度/加关系源（走 S1 修订 + 决策）；删/改 H/A 核心规则必须重开 S1；
- 本场无产品代码；S0–S6 全部冻结前不开工实现。
