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

## 2. 常驻成员与领域所有权（当前 7 个，上限已提升到 16）

| Agent | 领域所有权 | 对应对象认知 |
|---|---|---|
| `render-perf` | **渲染性能域**：首开/切页签/打字时延、内存预算、性能回归守卫 | `agent-guide/04-preview-and-rendering.md` + `design/benchmark-measurement-protocol.md` |
| `sync-mapper` | **编辑-预览同步域**：锚点映射准确度、选区与光标映射、双向同步 | `agent-guide/03-editor-and-formatting.md` + `design/edit-syntax-and-mapping.md` |
| `arch-contract` | **架构与契约域**：显示子系统契约 C1–C12、重构总纲与阶段裁决、`agent-guide/01`+`10` | `architecture.md` + `design/view-surface-contract.md` |
| `doc-consistency` | **文档一致性域**：文档↔代码审计、文档债、`agent-guide/06`+`07`+`08` | `docs/conventions/**` + 各 design 稿 |
| `metrics-baseline` | **度量与基准域**：真机/无头度量协议、基线与预算、交互金标准回归 | `design/realapp-measurement-protocol.md` + `design/benchmark-measurement-protocol.md` |
| `kp-owner` | **知识点域**：KP 面板、图谱联动、KP 抽取与存储、`agent-guide/05` | `agent-guide/05-*` + KP 前后端实现 |
| `settings-owner` | **设置/i18n/快捷键域**：设置键事实源、i18n 键、快捷键、`agent-guide/09` | `agent-guide/09-*` + 设置/文案实现 |

> **名额现状**：上限 16（含 Lead），当前 7 名 teammate ⇒ **还有 8 个空位**。
> 空缺领域（如 06 图谱本体、08 导入导出）默认走 L2 subagent；**只有出现长期、跨任务的领域责任时才升格为 Owner**。

### 2.1 动态维护能力（2026-10-20 起具备）

DSH 的 `agent-team` 插件此前**不能退役、不能改名**（roster 只有 `spawn`），导致团队一旦建立就被历史包袱锁死。我们在 DSH 侧补齐了三项能力（DSH 仓库提交 `468b01b5b2`）：

| 能力 | 工具 | 语义 |
|---|---|---|
| **退役** | `retire_teammate {target}` | 从花名册移除、释放会话、**释放名额**；journal 历史保留（只追加不删） |
| **改名/改描述** | `update_teammate {target, name?, description?}` | 新名成为 `send_message`/任务板 owner 的新 target |
| **提额** | `maxMembers: 8 → 16` | `agent-team-profile/cordis.patch.yml` |

**维护纪律**（必须遵守，否则又会退化成"历史包袱锁死"）：
1. **任务闭环即退役**：单点任务型 teammate（「修 X bug」「落地 Y」）完成后**当轮退役**，不留着占位；
2. **Owner 用领域命名**，不用「fix 型」命名（`jump-fix` 这类名字会让人误以为它只干过一次活）；
3. 退役前先确认它的产出已落到**磁盘报告/提交**（会话记忆不保留，退役即丢上下文）；
4. 改名后**同步更新本表与任务板 owner**（ownerName 由 roster 快照派生，改名会自动跟随，但本表要人改）。

## 3. 领域覆盖与缺口（对照 agent-guide 10 篇）

| agent-guide 篇 | Owner | 状态 |
|---|---|---|
| 01 shell-and-layout | `arch-contract` | 兼任 |
| 02 file-tree-and-nav | `arch-contract` | 原 `jump-fix` 已退役（R4 已修 `c33c9353`） |
| 03 editor-and-formatting | `sync-mapper` | 原 `mapper-fix` 已退役（R3 已修 `79865b1d`） |
| 04 preview-and-rendering | `render-perf` | 原 `render-impl` 已退役（CHTML→SVG 已落地 `4a3e5a7d`） |
| 05 knowledge-points | `kp-owner` | ✅ 已补 |
| 06 links-and-graph | `doc-consistency` | 文档侧兼任；图谱本体重构范围外 |
| 07 search-and-images | `doc-consistency` | 文档侧兼任 |
| 08 import-export-and-check | `doc-consistency` | 文档侧兼任 |
| 09 settings-i18n-and-shortcuts | `settings-owner` | ✅ 已补 |
| 10 data-layout-and-host-embedding | `arch-contract` | 兼任 |

**下次扩编的判断标准**：只有当某领域出现**跨任务、反复出现**的工作（≥3 次派发）时，才从 subagent 升格为 Owner；否则一律 subagent。

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
| 2026-10-20 | **团队重整（首次动态维护）**：退役 3 个任务已闭环的单点 agent（`render-impl`/`mapper-fix`/`jump-fix`）；3 个含糊命名改为领域名（`arch-agent`→`arch-contract`、`detail-agent`→`doc-consistency`、`metrics-agent`→`metrics-baseline`）；补 2 个缺口 Owner（`kp-owner` 知识点域、`settings-owner` 设置/i18n/快捷键域）；名额上限 8→16。前提是 DSH 侧补齐了 `retire_teammate`/`update_teammate`（DSH 提交 `468b01b5b2`），维护纪律见 §2.1 |

## 8. 首轮全员回报（2026-10-19，各 Owner 自述 · **历史快照**）

> **阅读须知**：本表是 2026-10-19 的**原始快照，保留不删**（追溯用）。
> 其中 `render-impl` / `mapper-fix` / `jump-fix` 已于 2026-10-20 **退役**（任务闭环），
> `arch-agent` / `detail-agent` / `metrics-agent` 已改名为 `arch-contract` / `doc-consistency` / `metrics-baseline`。
> **当前名册以 §2 为准。**

| Owner | 确认领域 | 自报的最大未解决问题 | 建议下一工作单元 |
|---|---|---|---|
| `render-perf` | 渲染性能 | **预览缓存命中率 0%**：`_previewCacheStash` 早退条件（`app.js:13134` 的 `!state.doc.preview_body`、`:13133` 的 `_dirty`）让正在编辑的大文件永远进不了预览池 ⇒ 整篇解析 ~1s 纯亏 | 改早退为按 `fp` 指纹判失效，并用度量协议验命中率上升 |
| ~~`render-impl`~~（已退役） | 渲染实现 | CHTML→SVG 切换**已完成**（含 mapper/app/edit-handler 复核：`_isAtomElement` 用非结构化信号，SVG 下无需改动）。真实未收口仅剩 1 项：`app.js:11751` 导出路径 `svg.fontCache="local"` + `typesetClear` 可能致 `<defs>` 未重建、导出公式空（待真机验证）。另一条同批待验风险：SVG 用 `ex` 度量替代 `matchFontHeight`，字高/基线可能有细微差异 | 真机验证导出公式 + 公式行高抽查（该项需人在真机执行，非 agent 可闭环） |
| `sync-mapper` | 编辑-预览同步 | **R1 是单点放大器**：`app.js:1872` 末块判据全有或全无，一旦失效全文退回与 parser 平行的第二套启发式，R2/R5/R6 全在此时显形 | R1 改逐块守卫（`block.srcLineEnd <= srcLines.length`）+ 退化时打 `log("STAMP","fallback")` |
| ~~`mapper-fix`~~（已退役） | 映射实现 | `srcToAst` 的 LIST/BLOCKQUOTE 无专用分支（走单行 inline 口径、`nodePath` 可越界）；rawMarker 残余降 P2 | 补 LIST/BLOCKQUOTE 专用分支 + 纯 Node 验证（与 R3 同族） |
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

## 9.1 第二例纠错：**测量工具的错误会伪装成产品回归**（2026-10-20，Lead 自身事故）

**经过**：`render-perf` 完成 task-19（消除每键 148 次空操作）后，我（Lead）跑 11 条交互金标准 → **11/11 全红、520s**。
我做了 A/B：撤掉它的改动 → 11/11 绿；装回 → 全红 ⇒ **据此判定「它的改动有害」**。

**真相**：错的是**我的测量工具**。`scripts/benchmark/surface/interaction.mjs` 里 CDP 端口用
`9222 + Math.random()*3000` **猜**端口；两个 benchmark 并发时可能撞同一端口 ⇒ 后启动的 Edge 绑不上调试端口，
CDP 客户端于是**连到了另一个正在跑的页面**。症状恰好是 `window.MemoriaApp` 存在、
`window.MemoriaParser` 却 `undefined`、`#preview` 停在「预览模块未加载」静态占位。

**为什么 A/B 会骗人**：两次结果不同纯粹是**端口竞争运气**不同——A/B 只有在"唯一变量被隔离"时才成立，
而我的两次运行**环境本身不是隔离的**。

**修复**（`f6d08c20`）：`freeTcpPort()` 绑定 0 取真空闲端口 + **启动后断言 parser/lexer/mapper/renderer 四模块齐全**，
缺失即明确报「CDP 可能连到别的页面」，不再伪装成 45s 超时。修复后同一份代码 **11/11 绿、24.7s**。

**教训（写入度量纪律）**：
1. **先证明测量工具可信，再测产品**——工具故障的症状往往与产品缺陷一模一样；
2. **A/B 的前提是环境隔离**：并发跑同一套 harness 时，端口/临时目录/浏览器用户目录**都必须唯一**；
3. 出现「全红且每条都等满超时」时，**优先怀疑环境与工具**，不要先归因到被测代码；
4. **跨域结论（Lead 判定某 Owner 的改动有害）必须给出可复现的因果链**，仅凭一次 A/B 不够。

## 9.2 第三例：**"假通过"比 bug 更危险**（2026-10-20，`render-perf` 自我纠错）

它的等价性测试脚本初版报告「命中集合恒为 0 处差异」，看起来是完美通过。实际是：
`compareBoundaryPoints` 里用了裸标识符 `END_TO_START`（正确写法是 `Range.END_TO_START`），
在类方法里被解析成全局变量 → `ReferenceError` → **被既有 `try/catch` 吞掉** → `isCovered` 永远 `false`
⇒ 改造前后"永远一致"。

**它自己发现并留档**，修正后得到真实结论（14/14 场景 + 20,910 组端点穷举逐元素一致）。

**教训**：
1. **"全部一致"和"全部为 0"要先证伪**：结果过于完美时，先构造一个**必须失败**的用例；
2. 既有 `try/catch` 是**假通过的温床**：断言型代码绝不能放在会被静默吞掉的 try 里；
3. 报告里必须写**"我如何证明这个测试会红"**，而不是只写"测试通过"。


