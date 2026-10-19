# Agent 团队组织（工程维护基石）

> **定位**：定义 DSH 会话内 agent 团队的**常驻结构、领域所有权、派发规则与成本模型**。
> 补充 [dsh-agent-teams-contract.md](dsh-agent-teams-contract.md)（实操契约）与 [AGENTS.md](../../AGENTS.md)（角色骨架）。
> **状态**：生效中，2026-10-19。

---

## 0. 为什么要有这份组织文档（团队的真实作用）

团队的作用**不是"把活并行"**，而是**把 context 切开**：
一个 100 轮的长会话会让每句话都为整段历史付费（实测单会话可达千万级 token）。
按领域拆成窄上下文的 agent，每个只带自己那片知识，是降低 token 的唯一结构性办法。

因此三条推论：
1. **跨域知识必须落盘**（`docs/reference/agent-guide/0X-*.md` + AOCI），不能留在某个 agent 的脑子里 —— 否则它一结束知识就没了；
2. **派发必须先给对象认知**（见 contract §0.5），agent 只读增量、不重 grep 全貌；
3. **简单任务 Lead 直接做**，不进团队 —— 派发的固定开销（briefing + 往返）常常大于任务本身。

## 1. 三层结构

| 层 | 谁 | 生命周期 | 用途 |
|---|---|---|---|
| **L0 调度** | Lead | 整个会话 | 派发、裁决、扩权原子操作（git/大文件/删除）、最终验收 |
| **L1 常驻领域 Owner** | 8 个 teammate | 跨多个工作单元常驻（inactive 时零成本） | 各自领域内的分析、实现、复核；**有领域记忆** |
| **L2 一次性子代理** | `subagent` | 用完即弃 | 只读盘点、单点机械活、并发分片；**不占名额、不留上下文** |

**判据**：
- 需要跨多轮 steer、需要领域累积 → **L1 Owner**；
- 一次性、只读、跑完即弃 → **L2 subagent**；
- 一两行改动能凭现有认知完成 → **Lead 自己做**。

## 2. 常驻成员与领域所有权（当前 8 个，名额已满）

| Agent | 领域所有权 | 对应对象认知 |
|---|---|---|
| `render-perf` | 渲染性能：首屏/增量/内存/耗时归因 | `agent-guide/04-preview-and-rendering.md` + `design/benchmark-measurement-protocol.md` |
| `render-impl` | 渲染实现：渲染管线落地、组件替换 | `agent-guide/04` + `design/preview-render-refactor.md` |
| `sync-mapper` | 编辑-预览同步：行号/列号/锚点映射准确度 | `agent-guide/03-editor-and-formatting.md` + `design/edit-syntax-and-mapping.md` |
| `mapper-fix` | 映射实现：parser/lexer/mapper 的具体修 | `agent-guide/03` + `mapper.js`/`lexer.js` |
| `jump-fix` | 导航与跳转：文件树、tab、前进后退、跳转落点 | `agent-guide/02-file-tree-and-nav.md` |
| `arch-agent` | 架构与契约：分层、单一事实源、设计稿权威性 | `architecture.md` + `design/view-surface-contract.md` |
| `detail-agent` | 文档一致性：文档 vs 代码核对、漂移取证 | `docs/conventions/**` + 各 design 稿 |
| `metrics-agent` | 度量与基准：探针、A/B、判据方法论 | `design/benchmark-measurement-protocol.md` |

> **8 个名额已满**（Lead + 8），且 DSH 无删除工具 ⇒ **本会话内不得再 spawn**。
> 空缺领域一律走 L2 subagent。

## 3. 领域覆盖与缺口（对照 agent-guide 10 篇）

| agent-guide 篇 | Owner | 缺口处理 |
|---|---|---|
| 01 shell-and-layout | （无专人） | `arch-agent` 兼任 |
| 02 file-tree-and-nav | `jump-fix` | — |
| 03 editor-and-formatting | `sync-mapper` / `mapper-fix` | — |
| 04 preview-and-rendering | `render-perf` / `render-impl` | — |
| 05 knowledge-points | **缺** | L2 subagent |
| 06 links-and-graph | **缺** | L2 subagent |
| 07 search-and-images | **缺** | L2 subagent |
| 08 import-export-and-check | **缺** | L2 subagent |
| 09 settings-i18n-and-shortcuts | **缺** | L2 subagent |
| 10 data-layout-and-host-embedding | **缺** | L2 subagent（或 `arch-agent` 兼任） |

**新会话重建团队时**，应按此表的缺口补 Owner（而不是继续堆渲染/映射类）。

## 4. 派发规则（Lead 每次派活前必须走这 5 步）

1. **查表**：这个任务属于哪个领域？§2 表里有 Owner 吗？
2. **有 Owner** → 派给它，briefing 只给「任务 + 验收 + 对象认知路径」，**不回灌历史对话**；
3. **无 Owner** → 派 `subagent`，同样只给对象认知路径；
4. **能自己做** → Lead 自己做（≤ 一两个文件的小改、纯查询、git 操作）；
5. **全程禁**：不整段回灌工具输出、不重复 grep 同一块、不为简单问题跑全量测试。

## 5. 知识存放（跨域复用的唯一载体）

| 知识类型 | 落点 | 不进哪 |
|---|---|---|
| 界面/交互现状 | `docs/reference/agent-guide/0X-*.md` | agent 上下文 |
| 设计决策与施工图 | `docs/design/*.md`（标明权威/过时） | 对话记忆 |
| 验证产物（一次性） | `artifacts/**`（不进 git） | docs |
| 代码结构认知 | AOCI 索引（正式认知层） | agent 记忆 |
| 团队自身规则 | 本文件 + contract | — |

**改完代码必须同步对应 agent-guide 章节** —— 否则下次派发又要重 grep，token 账会再涨回来。

## 6. 成本模型（为什么"简单对话"要便宜）

| 开销 | 量级 | 对策 |
|---|---|---|
| 会话历史累积 | **最大头**，每轮全量携带 | 长会话及时收口；简单对话开新会话 |
| 编辑 AGENTS.md | 每次 edit 触发全文重注入（25 KB） | 攒够一次改完 |
| 整段工具输出 | 单次可达数万 token | 一律 `Select-Object -Last N` |
| 全量 pytest | 1400+ 用例输出 | 只跑相关测试文件 |
| resumed 旧 agent | 携带其旧上下文 | 优先新建窄任务，不复用陈旧上下文 |

## 7. 演进记录

| 日期 | 变更 |
|---|---|
| 2026-10-19 | 初版：确立三层结构、8 个常驻 Owner 的领域表、10 篇 agent-guide 的覆盖缺口、5 步派发规则、知识落点与成本模型 |
| 2026-10-19 | 首轮全员激活：8 个 Owner 各确认领域并回报「最大未解决问题 + 建议下一单元」（见 §8） |

## 8. 首轮全员回报（2026-10-19，各 Owner 自述）

| Owner | 确认领域 | 自报的最大未解决问题 | 建议下一工作单元 |
|---|---|---|---|
| `render-perf` | 渲染性能 | **预览缓存命中率 0%**：`_previewCacheStash` 早退条件（`app.js:13134` 的 `!state.doc.preview_body`、`:13133` 的 `_dirty`）让正在编辑的大文件永远进不了预览池 ⇒ 整篇解析 ~1s 纯亏 | 改早退为按 `fp` 指纹判失效，并用度量协议验命中率上升 |
| `render-impl` | 渲染实现 | CHTML→SVG 切换**已完成**（含 mapper/app/edit-handler 复核：`_isAtomElement` 用非结构化信号，SVG 下无需改动）。真实未收口仅剩 1 项：`app.js:11751` 导出路径 `svg.fontCache="local"` + `typesetClear` 可能致 `<defs>` 未重建、导出公式空（待真机验证）。另一条同批待验风险：SVG 用 `ex` 度量替代 `matchFontHeight`，字高/基线可能有细微差异 | 真机验证导出公式 + 公式行高抽查（该项需人在真机执行，非 agent 可闭环） |
| `sync-mapper` | 编辑-预览同步 | **R1 是单点放大器**：`app.js:1872` 末块判据全有或全无，一旦失效全文退回与 parser 平行的第二套启发式，R2/R5/R6 全在此时显形 | R1 改逐块守卫（`block.srcLineEnd <= srcLines.length`）+ 退化时打 `log("STAMP","fallback")` |
| `mapper-fix` | 映射实现 | `srcToAst` 的 LIST/BLOCKQUOTE 无专用分支（走单行 inline 口径、`nodePath` 可越界）；rawMarker 残余降 P2 | 补 LIST/BLOCKQUOTE 专用分支 + 纯 Node 验证（与 R3 同族） |
| `jump-fix` | 导航与跳转 | 4 条已知不准：重命名不重映射导航栈（`file-tree.js:51-73`）、导航失败不回滚 cursor（`app.js:6228-6240`）、树内点击回卷丢尾（`nav-stack.js:38-46`）、文档锚点已 +27 漂移 | 重命名后重映射 `MemoriaNavStack` 帧路径（含 `filePointer`） |
| `arch-agent` | 架构与契约 | 8 条脱节仍在（D1/D2/D3/D5/D6/D8/D9/D10）；**最大风险是三份文档互相声明自己是/不是事实源** | 产出《契约权威性裁决单》+ D1/D10 修法清单 |
| `detail-agent` | 文档一致性 | 3 条：①`agent-guide/04`+P 稿通篇 `m0/js/*` 旧路径（`m0/` 已不存在，锚点全失效）；②真源口径冲突未裁；③`docs/todo.md §13` 悬空 | 只读核查 06/07/08 三篇锚点与交叉引用，产出 drift 报告 |
| `metrics-agent` | 度量与基准 | `logCursorContext` 每键跑仍属最高优先，**但未被 raw 证明因果**（机制假设） | 探针里给 `write_map_log` 挂计数，把假设变成「每键 RPC 调用数」硬读数 |

## 9. 自维护约定与首例纠错（重要）

**自维护规则**（agent 如何维护本文档）：
1. **单一写者**：本文档由 **Lead 单写**；各 Owner **不直接编辑**（8 个并行写同一文件必冲突）。
2. Owner 通过**回报**更新自己那一行：把「最大未解决问题 + 建议下一单元」发给 Lead，Lead 汇总落表。
3. Owner 可自行维护**自己领域的 artifacts 报告**（`artifacts/agent/verify/<owner>-*.md`），那是自由写区。

**首例纠错（2026-10-19，`render-impl`）**：
它回报「tex-svg.js 未落盘、刷新即 404、需 Lead 沙箱外复制」——**已证伪**：
`src/memoria/ui/static/vendor/mathjax/es5/tex-svg.js` 实际存在（2,108,580 字节，
SHA256 `D4295DC3…A882` 与源一致），探针残留已清，并已入 commit `4a3e5a7d`。

**根因**：它当年的复制失败留在了自己的上下文里，后续我在沙箱外完成的事实它无从得知
⇒ **陈旧上下文会把已解决的问题持续误报为待办**。

**教训（写入派发纪律）**：
- Owner 回报**未复核**的事实型结论时，Lead 必须**先验证再采信**（本次一验即破）；
- 给长期在岗的 Owner 派新活前，先下**上下文压缩指令**：让它保留「角色 + 已证实的结论 + 未解决问题」，
  **显式丢弃已被证伪/已由他人完成的旧结论**，避免用旧记忆否定新事实。

**压缩指令已实测有效（2026-10-19）**：对 `render-impl` 下达「作废旧结论 → 固化角色与已证实结论 → 重新回答未收口项」后，
它**自我纠错成功**并给出准确的剩余项（导出公式 `<defs>` 重建待验 + SVG `ex` 度量行高风险）。
⇒ **该指令应成为「Owner 长期在岗后接手新任务」的标准前置步骤。**

