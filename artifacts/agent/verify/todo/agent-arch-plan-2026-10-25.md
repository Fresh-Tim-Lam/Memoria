# 0.5.0 架构重构长期计划（2026-10-25，todo-owner；依据辩论裁决）

> 产出人：`todo-owner`（L8：版本级规划由 todo-owner 产出，Lead 不得凭记忆排期）。
> 依据：`artifacts/agent/verify/debate/PROTOCOL.md`（commit `48ca704e`，FROZEN）+ 26 条协议裁决 + `rulings-lead.jsonl`（R-L1..L3）+ `rulings-review.jsonl`（R-R1..R7）+ `rulings-debate-close.jsonl`（R-D1..D3）。
> 本文件回答三问：**① 阶段怎么切** / **② 与 §14 的关系（合并还是拆版本）** / **③ 任务复用/新建**；并给阶段表、关闭条件、写域、风险。**不改 `src/**`**（纯规划）。

---

## 0. 三问结论（先看）

### ① 阶段切法：**保持 5 阶段，不合并 S2/S3**
- 阶段：S1 粒度化（读+写+R-D2 正则统一）→ S2 进程内契约层 → S3 MCP 薄绑定 → S4 扩展点 → S5 trace 跨边界。
- **为什么不合 S2/S3**：MCP 薄绑定=最小工具集+schema 上限+无状态 server+边界复跑 W1–W4 + 文档，估 **2–4 人日**（不是 <1 人日）；合并会失去「写安全边界」独立验收门（§3 W1–W4 是硬约束，缺一否决）。**拆开不增加发布次数**——5 阶段同属 0.5.0，阶段只是内部验收门。
- **为什么把 R-D2 从 S5 移到 S1**：`document.py:420 ^(#{1,6})` 与 `heading_proposals.py:9 ^(#{2,6})` 是并行事实源（后者漏全部 h1，实测 279 个）；S1 的 C5 要求「级别范围写死」——若不先统一，新接口会**继承不一致**。放 S5 会产生「先不一致实现、再回头改」的返工。
- S4（扩展点）可在 S2 后与 S3 并行**规划**，但 `src/memoria/services/agent/**` 单写者 ⇒ **S3 与 S4 串行**（同写 `kb.py`/`registry.py`/`plugins.py`）。

### ② 与 §14 的关系：**拆两个版本**（0.4.7 收摊先发；0.5.0 架构重构独立）
- **0.4.7 = `docs/todo.md §14` 收摊 6 项**（task-90~94 + task-112）：低风险、用户可见修复/验证（台账校准、上下文占用/压缩、命名+AG21、响应式、0.4.6 已知问题收尾、K2 批量审计），预估 8–13 人日。
- **0.5.0 = 本计划 5 阶段**（task-120~124）：R1 级变更（内部服务契约 + MCP 对外交付面 + 写安全边界），预估 **17–27 人日**（≈4–6 周单写者）。
- **理由（不是"看情况"）**：
  1. **风险等级不同**：0.4.7 是兼容性修复/验证；0.5.0 改内部契约为外部交付形态（MCP）并触及唯一写者链（W1–W4）——R1 级，需要独立 soak 与对抗复核。
  2. **回滚粒度**：混发时一旦架构重构出问题（如 MCP 写边界漏洞），无法单独回滚，会把用户可见修复一起拖回；拆开后 0.4.7 可独立发布/回滚。
  3. **发布说明可写性**：0.4.7 能写「可测改善/收口」；0.5.0 写「架构重构 + MCP 交付 + token 粒度收益」。混在一起两类口径互相稀释。
  4. **串行成本低**：0.5.0 是纯后端 `services/agent/**`；0.4.7 的前端项（app.js/agent-panel.js/app.css）与 0.5.0 无写域重叠，**拆开反而可并行推进**（各自单写者），合并则同一发布窗口排队。
- 版本号：0.5.0 依据 `version.md §2`「0.x 阶段 MINOR 可用于较大功能里程碑」。

### ③ 任务板：复用/新建/作废
| 类别 | 处理 |
| --- | --- |
| **复用（0.4.7）** | task-90~94 + task-112 **原样保留**（§14 未动），不并入 0.5.0 |
| **新建（0.5.0）** | **task-120..124**（每阶段 1 条，含可验证关闭条件/写域到产物级/依赖） |
| **作为输入（已完成）** | task-118（AS-SECTION-RANGE 检验）→ 结论 3 的 C1–C5 输入 S1；task-119 本任务 |
| **不并入（历史 open）** | task-85（图谱审计 3×，P2 性能）、task-86（KG 调研，0.4.8）、task-110（团队基础设施债，steward）——均与 0.5.0 主题无关 |
| **作废** | 无（本次不删除任何任务；0.4.7 的 §14 计划不受影响） |

---

## 1. 五阶段明细（任务板 id / 关闭条件 / 预估 / 依赖 / 写域）

| 序 | 阶段 | 任务板 | 核心范围（依据裁决） | 可验证关闭条件（摘要） | 预估 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | 粒度化（读+写+R-D2） | `task-120` | `outline/section/snippet` 三级 + **C1–C5**（C1 剔围栏/frontmatter、C2 父级路径+行号双锚、C3 `AMBIGUOUS_SECTION`、C4 `#L` 回退、C5 级别写死）；`replace_section`（R-R3：17 KNOWN_OPS/16 COMPILED_OPS 全行号锚，能力缺失非包装）；R-D2 正则统一 | 真实语料 C1 误判=0、C2/C3 无静默取错节；预算+总账 A/B（省≥70% 且完成率不降>10%）；`replace_section` 期望不符即拒+单撤销；h1 提案 0→279；全门禁绿 | 5–8 天 | 无（R-D2 前置并入本段） |
| S2 | 进程内契约层 | `task-121` | T1–T4 facade + **写安全 W1–W4 可测断言**（W1 唯一写者/txid、W2 读后写守卫、W3 写前备份可恢复、W4 审批在分发前） | 契约测试 T1–T4 各 ≥3 用例；W1–W4 各 1 条必红 fixture；35 工具经 facade 回归；契约文档落盘 | 4–6 天 | S1 |
| S3 | MCP 薄绑定 | `task-122` | 最小工具集+schema 上限+无状态（MCP `2026-07-28`）；只暴露"产 plan"（W1）；边界复跑 W1–W4；6 个月复盘口径（X-1） | server 可启动+schema 字节落盘；W1–W4 边界必红；真实跨进程 outline→section→propose_write→apply（txid/undo）；无状态重启一致 | 2–4 天 | S2（不合并，见 §0-①） |
| S4 | 扩展点（第三层） | `task-123` | `ActivePlugins → build_kb_tools()` 工具面投影消费者（**R-R1：gate 当前 dead**——`kb_has_sidecar` 2 命中、`op_available()` 不读、`build_kb_tools()` 零命中）；三字段（`tool_schema_ref`/`budget`/`lifecycle.dispose`）**移出 v1**（R-R2 零消费者） | gate 投影断言（或按裁决移除）；>50% 非恒 always 或撤回方向；声明式样例插件不改 registry 本体即可加工具；三字段拒绝/迁移；35 工具行为不变 | 3–5 天 | S2；与 S3 串行 |
| S5 | trace 跨边界 | `task-124` | 调用级成本字段（`est_tokens`/`truncated`/`approval`/`write{backup_txid}`，正文只存 digest+长度）+ `trace_cost_summary` 聚合 + 容量淘汰（5000/会话、错误与写路径不淘汰）+ MCP `_meta` 回传 | 字段可回放；聚合与原始条目误差 0；6000 条淘汰后错误/写路径 100% 保留；MCP `_meta` 串起两侧；索引可重建 ≤5s/会话 | 3–4 天 | S3（进程内成本字段可 S2 后先行） |

**合计 17–27 人日**；串行口径 ≈4–6 周。

## 2. 推荐顺序与理由
```
S1 → S2 → S3 → S4 → S5
（S4 与 S3 同写 services/agent/** ⇒ 串行；前端 0.4.7 与本线无写域重叠 ⇒ 可并行两条线）
```
- **粒度化先行（P-1）**：否则 MCP 会把"整文件读"（N1 的 89% 浪费）**固化进外部契约**，之后改契约代价远高于改进程内函数。
- **契约层先于 MCP**：R-L2「有封装有接口」是硬需求；MCP 是交付形态之一，不是省 token 手段（N1 已证伪）。
- **扩展点后于契约层**：工具面投影消费点必须在 facade 定型后才有收口处（R-R1 的教训：先有消费者才谈 gate）。
- **trace 最后**：跨边界 `_meta` 只有 S3 之后才有增量；内部 trace 已存在，不造新系统。

## 3. 本版做什么 / 不做什么
**做**：三级读粒度 + `replace_section` + C1–C5；进程内契约层；MCP 最小集薄绑定；工具面投影消费者（gate 复活或三字段移出）；trace 成本字段与跨边界 `_meta`。
**不做**（结论 7 + 裁决）：
- 不移植 **Cordis 宿主运行时**（scoped layers / 服务注册 / bundle+preset 分层）；
- 不移植 DSH 的 **17 个 `dsh-*` 自用技能内容**（只补装载协议）；
- 不追 `skill-office` / `tool-workspace-dependencies`（推后评估）；
- **不以省 token 作为 MCP 立项理由**（N1：组 0 无 MCP 省 82.9–89.3%，组 B 恒比组 0 贵 11.10/18.49/14.24%）；
- 不把"工具不出现=省 schema"当既成事实（R-R1）；
- 不在 v1 新增/保留无消费者字段（R-R2）；
- 不改前端 UI（本版本纯后端契约；如需 MCP 设置入口另立小任务，与 0.4.7 前端串行）。

## 4. 需人裁决
**无人裁决项**（人 2026-10-25：「不需要问我」；技术方案以辩论裁决为准，本计划只排期/拆解）。
**唯一升级条件**：若执行中出现**影响外部契约的新分支**（例如「MCP 是否暴露写工具」「是否引入显式 `{#id}` 锚」），按 §5 风险升级给人，不自行拍板。

## 5. 风险与未测项（如实）
1. **`AS-STYLE-COST` 未检验**：MCP 额外成本构成未分测 ⇒ S3 schema 上限按 N1 实测 4,349 token/会话固定成本设，实施时须 E4 复测（8 项溯源）。
2. **粒度可能反升总账**（position U3）⇒ S1 验收必须「完成率 + 完整往返总账」双指标，不能只报省。
3. **`AS-SECTION-RANGE` 有条件成立**：91.70% 可寻址 / 2.62% 围栏误判 / 2.93% 重名（93.9% 同级）⇒ C1–C5 是实测反推条件；C3 歧义率 >20% 需改用显式 `{#id}` 锚（as-section-range D.4）。
4. **写侧数据风险**：`replace_section` 必须 `expect` 逐字校验 + 单撤销；W1–W4 缺一条即否决。
5. **N1 口径**：tokenizer 为静态估算假设（3.5 字符/token、1.5 中文字/token），非真机 usage。
6. **S3 交付义务不依赖需求证据**（R-L2），但 6 个月复盘（X-1）只决定优化/文档/工具集，不决定做不做。
7. **`gate` 复活的风险**：投影消费者落地后若工具集天然恒全量（无法裁剪 >50%）⇒ 动态裁剪方向本身不成立，改「静态最小集 + 场景包」（position falsifier）。

## 6. 证据索引（可复跑）
| 判断 | 证据 |
| --- | --- |
| 结论 1 token 与 MCP 正交 | `artifacts/agent/verify/debate/n1-a1-token-hypothesis.md#§4`（组 0 −82.9/−89.3/−86.0%；组 B 比组 0 贵 11.10/18.49/14.24%，Lead 复核数字） |
| 结论 2 MCP 定位/顺序 | `ruling/rulings-lead.jsonl` R-L2；`ruling/rulings-review.jsonl` R-R4；`position/agent-arch-position.md §2-Q2`（P-1/D-1/X-1 表） |
| 结论 3 C1–C5 | `artifacts/agent/verify/debate/assumptions/as-section-range.md`（D 节 + 实测 229 篇/91.70%/2.62%/2.93%） |
| 结论 4 写侧缺 1 op | `src/memoria/services/agent/plan.py:152-158`（BODY_EDIT_OPS 五项）+ R-R3 |
| 结论 5 gate dead | `rulings-review.jsonl` R-R1；`src/memoria/services/agent/plugins.py:27/66/247-258/536-541`；`tools/kb.py:486` |
| 结论 6 三字段零消费者 | `rulings-review.jsonl` R-R2；`docs/design/agent-plugin-design.md#L15` |
| 结论 7 不做范围 | `position/agent-arch-position.md §2-Q1`（①②③ 分类）+ task-119 描述「不做」 |
| 结论 8 R-D2 | `rulings-debate-close.jsonl` R-D2；`services/document.py:420` vs `services/heading_proposals.py:9` |
| 阶段/顺序判断 | `position/agent-arch-position.md` §2-Q3/Q4/Q5 + §3（W1–W4） |
| 版本拆分 | `docs/conventions/version.md` §2（0.x MINOR 用于较大功能里程碑） |

## 7. 复跑命令
```powershell
# 裁决产物完整性
Get-ChildItem artifacts/agent/verify/debate/ruling/*.jsonl | ForEach-Object { $_.Name + " " + (Get-Content $_.FullName).Count + " 条" }
# 结论 5/6/8 代码复核
Select-String -Path src/memoria/services/agent/plugins.py -Pattern 'GATE_VALUES|kb_has_sidecar|def op_available'
Select-String -Path src/memoria/services/agent/tools/kb.py -Pattern 'def build_kb_tools'
Select-String -Path src/memoria/services/document.py -Pattern '#{1,6}'; Select-String -Path src/memoria/services/heading_proposals.py -Pattern '#{2,6}'
# 写侧 op 清单
Select-String -Path src/memoria/services/agent/plan.py -Pattern 'BODY_EDIT_OPS|KNOWN_OPS|COMPILED_OPS'
# N1 数字
Select-String -Path artifacts/agent/verify/debate/n1-a1-token-hypothesis.md -Pattern '82\.9|89\.3|11\.10|18\.4|14\.24'
# 台账守卫
python scripts/check_todo_size.py
```
