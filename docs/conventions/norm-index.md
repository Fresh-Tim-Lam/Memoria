# 元规范索引（Meta-Norm Index）

> **用途**：给"规范体系本身"建立唯一入口。它不重复条款，只回答三件事：哪条规范是最高约束、什么时候必须读哪一份、上下文压缩/换 Agent 后按什么顺序恢复。
> **目标读者**：项目负责人、Lead、所有 teammate、后续接手的 Agent。
> **关联文档**：[AGENTS.md](../../AGENTS.md) §0.5 / §1 / §4；[meta-rules.md](./meta-rules.md)；[lead-dispatch-rules.md](../guides/lead-dispatch-rules.md)；[docs-management.md](./docs-management.md)。

---

## 0. 先读顺序（强制）

任何非平凡工作开始前，按顺序确认：

1. 用户当前指令（最高优先级，但不能覆盖安全/权限红线）；
2. 本索引 `M0–M7`；
3. 与本次工作触发条件对应的**原文**（本索引只做索引，不替代原文）；
4. 共享任务板 + `team_snapshot`（不凭记忆回答"还剩什么"）。

**上下文压缩后**：先重读本索引 → `AGENTS.md §0.5` → `docs/guides/lead-dispatch-rules.md §0` → 任务板。禁止凭压缩摘要直接派发、改代码或宣称完成。

---

## 1. 规范层级（M0–M7）

| 层 | 名称 | 唯一权威 | 约束什么 |
|---|---|---|---|
| **M0** | 平台与安全硬约束 | `AGENTS.md` §0；`docs/conventions/**` 红线 | 用户库不可覆盖、权限隔离、不可逆操作、发布边界 |
| **M1** | 元规范（如何讨论/写规范） | [meta-rules.md](./meta-rules.md) | 即时落盘、结论标记、规则依附场景、文档首行释用途 |
| **M2** | 单一事实源与登记 | `AGENTS.md` §1、§4；[docs-management.md](./docs-management.md) | 唯一来源、写权限矩阵、登记/索引、禁止并行事实源 |
| **M3** | Lead 派发不变量 | `AGENTS.md` §0.5 L1–L10；[lead-dispatch-rules.md](../guides/lead-dispatch-rules.md) | 任务先行、写域、验证阶梯、收口、压缩恢复 |
| **M4** | Agent 组织与协作 | [agent-team-org.md](../guides/agent-team-org.md)；[dsh-agent-teams-contract.md](../guides/dsh-agent-teams-contract.md) | Owner 域、任务板、消息、证据交接、退役 |
| **M5** | 验证与证据 | `AGENTS.md` §2.2；[test-assertion-granularity.md](./test-assertion-granularity.md) | 不采信自报 PASS、机器门禁、断言粒度、证据落盘 |
| **M6** | 版本、发布与文案 | [version.md](./version.md)；[release-copy.md](./release-copy.md)；`scripts/agent/release_preflight.py` | 版本单一来源、tag/发布、双语与格式门禁 |
| **M7** | 上下文与认知恢复 | 本索引；[lead-dispatch-rules.md §0](../guides/lead-dispatch-rules.md) | 压缩后重载顺序、不凭记忆、AOCI/任务板重查 |

**冲突裁决**：用户明确指令 > M0 安全/权限红线 > M1 元规范 > M2 单一事实源 > M3 派发不变量 > 具体 guide/任务描述。低层规范不得覆盖高层；冲突必须上报，不得静默选择。

---

## 2. 触发索引

| 触发 | 必读 | 不可省略的动作 |
|---|---|---|
| 新建/派发任何任务 | M3 L1/L8/L9；M4 | 先建任务并声明 writeScope，再 spawn；不并行写域 |
| 设计/规格/语义讨论 | M1；M2 | 保留用户原话；不得 Lead 单方定稿；结论标记采纳/否决/暂缓 |
| 重构/架构调整 | M2、M3、M5 | 先证现状与失败基线；统一事实源；不在旧分支上打补丁；独立验收 |
| 多 Agent 协作 | M4 | Lead 只裁决/验收；Owner 负责写域；磁盘报告交接，不靠对话记忆 |
| 改用户知识库/发布 | M0、M6 | 先回滚方案；版本/tag/发布前核对；用户库不覆盖 |
| 上下文压缩/换会话/换 Agent | M7 | 重读本索引 + §0.5 + 任务板；不凭摘要直接开工 |
| 自称"完成/通过" | M5 | 给可复现命令与产物；Lead 亲跑；自报 PASS 不算验收 |

---

## 3. 规范变更流程

1. 先判断是否真的新增"规则"：规则必须依附具体场景（M1 规则 3），纯抽象不落盘。
2. 规则写入其**唯一权威文档**，不得在多个文档复制同一规则。
3. 同一变更内更新本索引的层级/触发条目；索引与原文不一致时，以原文为准并立即修索引。
4. 登记类文件（README/索引/台账）的写入权限按 `AGENTS.md` §4；非 registrar 只提议，不擅自改登记。
5. 规范变更本身也要有证据：链接、条款位置、生效日期；重大变更需人确认。

---

## 4. 失效信号（看到就停）

- 任务板满 256 仍强行创建，或绕过任务直接 spawn；
- 写域重叠仍并行改同一文件；
- 只改代码不跑基线，或把"自测通过"当验收；
- 设计与用户原话不一致，却由 Lead 自行解释；
- 上下文压缩后凭记忆列"剩余工作"；
- 为通过检查而改指标/改断言，而不是改行为；
- 同一规则在多个文档出现不同版本。

> 以上任一出现：停止推进，回到本索引第 0 节重读，再决定下一步。
