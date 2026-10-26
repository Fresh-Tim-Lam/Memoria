# Memoria Claims — 断言—证据表（README 的地基）

> **用途**：README / Release / 仓库描述里**每一条能力性断言**都必须先在本表登记，并指到
> 可核验的证据（代码 `file:line` / 冻结设计文档 / 实测产物）。**没有证据的断言只能进 Roadmap。**
> **状态**：生效中（2026-10-26，task-182）。**维护者**：README / 宣传文案的改动者。
> **关联**：[README.md](../../README.md)、[README.cn.md](../../README.cn.md)、
> [repo-metadata.md](./repo-metadata.md)、[tag-release-spec.md](./tag-release-spec.md)；
> 证据校验脚本：[artifacts/agent/verify/marketing/check_claims.py](../../artifacts/agent/verify/marketing/check_claims.py)。

---

## 0. 状态词表（只能四选一）

| 状态 | 含义 | 允许出现在 README 的位置 |
|---|---|---|
| **implemented** | 已交付，有代码 / 可运行命令 / 实测产物作依据 | 正文「能力/功能」章节 |
| **bounded** | 已交付，但**有前提或边界**（必须把条件一起写出来） | 正文，且**必须带条件**（例：语义检索需先装可选依赖并缓存模型） |
| **design-intent** | 有意为之的**设计理念**，有冻结设计文档支撑，但**尚未作为能力交付** | 只允许在「设计理念 / Design philosophy」语境；不得写成"已实现" |
| **roadmap** | 计划中，无交付证据 | 只允许在 Roadmap 章节 |

> 额外有**禁止词条**（§9）：任何情况下不写（防篡改 / 安全 / 已签名 / 图谱已赋能 agent 检索 …）。

**登记规则**

1. README 里每个**能力性**句子/要点，必须能在 §1–§7 找到对应行（按 `CLM-xx` 编号引用）。
2. 新增断言 = 先补本表 + 证据命令能跑通，再改 README；**顺序不能反**。
3. 证据是 `file:line` 的，**被引文件一改就要回来复核**（漂移风险：行号会变；README 改版时跑一遍 `check_claims.py`）。
4. 「实测」类断言必须写清：**测的是哪版 / 什么口径 / 原始产物在哪**；本轮**没有复跑的**必须标"历史实测"。

---

## 1. 定位与差异化（README 顶部 / Why Memoria）

| 编号 | 断言（EN / 中文要点） | 状态 | 证据类型 | 依据 / 命令 | 边界与 README 写法 |
|---|---|---|---|---|---|
| CLM-01 | Notes are plain Markdown + a sidecar YAML; a KB is just a folder (`.md` + `.memoria/`) — EN: "Plain files on your disk; a knowledge base is an ordinary folder." | implemented | code + 文档 | `docs/conventions/directory-organization.md`；`AGENTS.md` §1「产品状态」行；`src/memoria/storage/sidecar.py`（`save_sidecar_for_md`） | 说"普通文件夹 + 纯文本"，不说"任何编辑器都能完整编辑"（`.memoria/` 是应用管理目录） |
| CLM-02 | Knowledge points (KPs) are first-class: snippet-range bidirectional links point at the **exact line range**, not just a page | implemented | code | `README.md` 既有功能 + `src/memoria/services/link_resolver.py`（`resolve_link_target`）；边/锚点模型见 `docs/design/kg-ontology-v0.md:33-46`（Link=正文锚点，带 instances 行号） | 写"snippet-range links"，不写"任意块级嵌入" |
| CLM-03 | Local-first / no account / no cloud sync; data stays on your machine | implemented | code（absence）+ 文档 | `git grep -ni "login\|sign in\|account" src` → 无账号体系；网络调用面见 CLM-13；`docs/design/system-design.md`（存储层=文件系统） | **不要写"零网络"**：出网开关默认开（见 CLM-13）；写"无账号、无云同步、文件在本地" |
| CLM-04 | Bilingual UI (Chinese / English) | implemented | code | `src/memoria/ui/static/app/i18n/{zh-CN.js,en.js}`；`docs/conventions/i18n.md` | 只写 UI 双语，不写"文档全量双语" |

## 2. 知识图谱：定位是「索引」，不是装饰（★ 本轮核心）

> **写法总纲（Lead 2026-10-26 转述人裁定）**：图谱可以写，但必须在 **design-intent / 设计理念** 语境；
> **不得**写成"图谱赋能 agent 检索"或"提高 agent 交互效率"这类**已实现**能力。

| 编号 | 断言 | 状态 | 证据类型 | 依据 / 命令 | 边界与 README 写法 |
|---|---|---|---|---|---|
| CLM-10 | The graph is designed as an **index**, not decoration — a stable, typed structure an agent framework could reason over. (Design intent; retrieval-side graph access is roadmap.) | **design-intent** | 冻结设计 + 本体辩论 | `docs/design/kg-ontology-v0.md:9-14`（"链接图不是关系图"、agent 侧从不读边）；`:25-29`（"边服务的是人看的图 + 写质量诊断，不是 agent 推理"；"任何为 agent 加边能力的设计，必须先证明它能改变一个 agent 决策"）；**13 条裁决**：`docs/design/kg-ontology-v0.md:2` + `artifacts/agent/verify/debate/kg/ruling/rulings-kg.jsonl` | **必须带括号说明**："design intent — retrieval-side graph access is roadmap"。不得写成已交付 |
| CLM-11 | The graph's **visual design is frozen after a multi-party design review**, with two explicit human rulings (node-size range 75%–165%; no size *buckets* — continuous mapping). | implemented | 冻结设计 + 裁决记录 | `docs/design/kg-visualization-v0.md:1-9`（FROZEN + 人裁决）；`:35-42`（人裁决①范围 75%–165%）；`:49-53`（人裁决②连续、不设挡位）；`:348-354`（变更记录：两轮人裁决） | 只写"经过研讨会 + 冻结 + 人裁决"，**不宣称"设计最好/最科学"**（主观）；"科学设计"必须落到"每条视觉决定都有依据与被否决的备选" |
| CLM-12 | The **ontology freezes its own boundary**: edges are typed `reference` / `contain` / `extend`, `contain` is derived from heading hierarchy, and the project explicitly states edges do **not** yet serve agent reasoning. | implemented | 冻结设计 | `docs/design/kg-ontology-v0.md:31-46`（三种类型 + link/edge 解耦）；`:75-83`（v0 不做：不加新语义类型等）；`:190-199`（登记未知 U-1「边对 agent 的价值」） | "敢写边界"是本条的可信度来源；不得暗示边类型可被 agent 用于推理 |
| CLM-13 | 2D / 3D graph views; click a node to jump back to its source; layout stability commitments (deterministic seed; no global reheat on hover/zoom) | implemented | code + 冻结设计 | 视图：`src/memoria/ui/static/app/js/graph-view-2d.js`、`graph-view-3d.js`；稳定性承诺 `docs/design/kg-visualization-v0.md:182-193`；节点大小映射 `graph-engine.js::MemoriaGraphSizing`（见该文档 `:111-112`） | 3D 里**不**用大小编码重要性（`:133-158`，D-KGV-04）；README 不要写"3D 可以看重要性" |
| CLM-14 | Agent **can create and maintain KP links**; all writes go through one plan-based path, are pre-image backed up, audited, and undone in one step. Approval is a **per-session preset**: default `auto-approval` auto-applies routine writes and asks once for deletions/renames; `manual-approval` asks for every write. | implemented | code | 写计划原语：`src/memoria/services/agent/plan.py:71-72`（`attach_links`/`detach_links`）；落地：`apply.py:22-23`；纯边原语 `kb.link.create`：`apply.py:184` + `plugins.py:150`；写管线设计：`docs/design/agent-capabilities.md:79-95`；**默认档 = 自动审批**：`src/memoria/services/agent/permission_presets.py:93`（`DEFAULT_PRESET`）、`:125-128`（三档语义）；风险 op 才问：`approvals.py` `RISKY_OPS`（`rename_file`/`delete_file`/`move_file`/`delete_kp`/`rename_kp`） | 必须写「单一路径 + 备份 + 审计 + 可撤销 + 分档」；**不得**写"每次写入都要你点确认"（默认档不是 manual）；要逐条确认请写"切到 manual-approval" |
| CLM-15 | Agent has **graph/structural audit** capability (`validate_kb` returns sidecar / manifest / path-drift / graph-link issues; `kb_overview` gives an overview) | implemented | code | `src/memoria/services/agent/tools/kb.py:625`（`kb_overview`）、同文件 `validate_kb`（描述含 "sidecar、manifest、路径漂移、图链接"）；`src/memoria/graph/kb_build.py:325-343`（`graph_audit.json` 产物） | 说"能审计图谱建边问题"，**不是**"agent 利用图谱推理" |
| CLM-16 | Roadmap: make graph topology usable **inside agent retrieval** — gated on proving it changes an agent decision | **roadmap** | 冻结设计的先决条件 | `docs/design/kg-ontology-v0.md:171-177`（"反向邻接"是唯一值得建的，但**必须先 A/B 证明它改善回答质量**）；`:190-192`（U-1 边对 agent 的价值未测） | 只进 Roadmap；写法必须含"需先证明" |

## 3. 学习闭环：复习 + 调度（Obsidian 不做的事）

| 编号 | 断言 | 状态 | 证据类型 | 依据 / 命令 | 边界与 README 写法 |
|---|---|---|---|---|---|
| CLM-20 | Built-in **FSRS** spaced-repetition scheduler: per-card state, due queue, grade 1–4, deterministic CLI (`fsrs.py due/init/grade`) | implemented | code（可运行） | `resources/agent-prompts/fsrs.py`（`compute_next_state`；子命令 `due`/`init`/`grade`）；`docs/design/review-cards-handoff.md:120-124`（调度只由 fsrs.py 算 / grade 幂等 / 不校验 due） | 写"FSRS 调度"，不写"掌握程度分数"（后者未实现，见 CLM-22） |
| CLM-21 | Review cards are **agent-operable but approval-gated**; answers are hidden from the UI until reveal; attempts log is append-only | implemented | code + 设计 | 7 把复习工具：`docs/design/review-cards-handoff.md:84-96`（`review_cards_upsert`/`review_due_list`/`review_grade`/`review_feedback_add`…）；答案隔离：同文档 `:107-118`；`attempts.jsonl` append-only：同文档 `:71` | 写"agent 可以帮你出卡/判分（逐条审批）"；不写"agent 自动批改一切"（主观题需 agent 回判才闭环，`:135`） |
| CLM-22 | A single **"mastery score" dashboard** for every knowledge point | **roadmap** | —— | 全仓 `git grep -n "掌握\|mastery" src` → 0 命中；调度状态（stability/difficulty/due）可由 `review_due_list` JSON 读出（`tools/kb.py:5165` 描述） | **禁止**写"掌握程度可视化/评分"；可说"每张卡保留调度状态（stability/difficulty/due）" |
| CLM-23 | Knowledge-point granularity: cards can be bound to a KP (`kp_id`) and a source file; review is at KP granularity, not just whole documents | implemented | code | `docs/design/review-cards-handoff.md:68`（card 字段含 `kp_id`/`file`/`source`）；`review_due_list` 返回字段（`tools/kb.py:5165`） | 写"卡可绑定知识点与来源"，不写"自动生成全部知识点卡片" |

## 4. AI + 笔记一体（agent 能读写知识库）

| 编号 | 断言 | 状态 | 证据类型 | 依据 / 命令 | 边界与 README 写法 |
|---|---|---|---|---|---|
| CLM-30 | AI agent lives **inside** the app and can **read** the KB: `read_document` (paginated), `kb_overview`, `outline` / `section` / `snippet` (granular read), `search_kb` | implemented | code | `src/memoria/services/agent/tools/kb.py:586`（`read_document`）、`:625`（`kb_overview`）、`:909`（`outline`）；完整工具面见 `check_claims.py` 的 `tool_surface` 检查；三级粒度设计：`docs/reference/agent-guide/`（粒度读） | 写"agent 可读/查库、可按三级粒度读"；不写"agent 已理解你的全部笔记"（模型能力属外部依赖） |
| CLM-31 | Agent can **write** the KB through a single plan-based path (dry-run diff → apply under the session's approval level → audit → one-step undo). Approval levels: `auto-approval`（**默认**：常规写自动放行，删除/重命名类问一次）/ `manual-approval`（每次写都问）/ `all-access`（全放行，仍备份可撤销） | implemented | 代码 + 设计 | `docs/design/agent-capabilities.md:79-95`（写管线 + 四条不变口径）；三档：`src/memoria/services/agent/permission_presets.py:93,125-128`；风险 op：`approvals.py` `RISKY_OPS`；写工具过审批判定：`tools/registry.py`（`read_only=False`）| README 必须写清**默认档是自动审批**、删除类会问；**禁止**写"每次都要你逐条确认"作为默认体验 |
| CLM-31b | 写前备份 + 整批撤销 + 审计事件（`capability/proposal` / `capability/apply` / `capability/reject`）对所有写路径生效，**与审批档无关** | implemented | 代码 + 设计 | `docs/design/agent-capabilities.md:107-118`（pre-image 时机/粒度）；`src/memoria/services/agent/backup.py`；审计事件：`agent-capabilities.md:87`；`all-access` 档描述明确"仍写前备份、可整批撤销"（`permission_presets.py:128`） | 这是"放开写"后真正的安全兜底，README 应主推这条而不是"审批弹窗" |
| CLM-32 | Writes are backed up before applying and can be rolled back as a batch (pre-image snapshot) | implemented | 代码 + 设计 | `docs/design/agent-capabilities.md:107-118`（pre-image 时机/粒度/新建文件）；`src/memoria/services/agent/backup.py` | 写"写前备份 + 批次回滚"；不写"数据永不出错"（有已知欠账，见 `review-cards-handoff.md:128-139`） |
| CLM-33 | An **MCP server** exposes a minimal read/write subset (4 tools, 544 tok schema) so external MCP clients can read and propose writes | bounded | 代码 + 设计 | `src/memoria/services/agent/mcp_server.py:147-189`（`outline`/`section`/`snippet`/`propose_write`）；`docs/design/agent-mcp-binding.md:35-45`（schema 实测 544 tok；上限 1,450） | **条件**：面向 MCP 客户端的只读+提议子集，不是完整工具面；写仍需审批（`:47-56`） |
| CLM-34 | Capability plugins / skills / extension points for extending agent behavior | implemented | 文档 | `docs/design/agent-capabilities.md`（§2 能力插件契约、§4 skill 机制）；`src/memoria/services/agent/plugins.py` | 只在「Extensibility」小节简述；不写"插件市场" |

## 5. 渲染与性能（有数字的必须有 benchmark）

| 编号 | 断言 | 状态 | 证据类型 | 依据 / 命令 | 边界与 README 写法 |
|---|---|---|---|---|---|
| CLM-40 | Rich rendering: LaTeX (MathJax), Mermaid, highlighters/font colors, images with local/remote/lightbox, mixed nesting | implemented | code + 文档 | `src/memoria/ui/static/app/js/render-core.js`；`docs/reference/preview-formats.md`（渲染格式权威）；`docs/conventions/markdown-form-std.md`（语法） | 写"支持这些写法"；不写"渲染比谁快" |
| CLM-41 | **Measured** graph performance: 5,000-node star graph frame 9108 ms → 41.5 ms (≈212×, ~23 fps), load 136 s → 0.35 s — measured at v0.3.4 with the repo's own benchmark harness | bounded（实测·历史） | 实测产物 + 设计文档 | 基线 `docs/design/graph-benchmark.md:191`；结果/结论 `:318-319`；原始产物 `scripts/benchmark/graph/results/render-*.{json,md}`；同一数字登记于 `docs/conventions/version.md:219` | **必须写**"measured at v0.3.4；复现步骤/口径见 `docs/design/graph-benchmark.md`；**本轮未复跑**"。禁止写"当前版本最快"或跨设备比较 |
| CLM-42 | **Measured** cold start: 15.4 s → 2.4 s (−84%) at v0.4.6 | bounded（实测·历史） | 版本文档 | `docs/conventions/version.md:212`（0.4.6 行）；测量协议 `docs/design/benchmark-measurement-protocol.md`、`docs/design/realapp-measurement-protocol.md` | 同上：写"measured at v0.4.6, historical; protocol in docs/…"。不许写成"启动只要 2.4 秒"（无条件断言） |
| CLM-43 | "Faster than <other editor>" / "fastest" | **禁止** | —— | 无跨产品同口径 benchmark | 不出现；只允许"我们在自己的口径下有实测，并把口径公开" |

## 6. 数据、隐私与联网（诚实边界）

| 编号 | 断言 | 状态 | 证据类型 | 依据 / 命令 | 边界与 README 写法 |
|---|---|---|---|---|---|
| CLM-50 | No account, no cloud sync, no telemetry upload | implemented | code（absence） | `git grep -ni "login\|sign in\|account" src` → 无账号体系；`git grep -ni "telemetry-send\|analytics\|sentry" src` → 无外发遥测；本地图谱埋点明确"本地、append-only、不上传"：`src/memoria/storage/graph_telemetry.py`（模块头三条硬要求） | 写"不需要账号、不同步到云、没有上传遥测"；**不要说"完全不联网"** |
| CLM-51 | Network is used only for features you enable/configure: LLM provider, optional web search/fetch, optional update check. There is a single outbound switch. | bounded | code | 出网开关：`src/memoria/services/agent/llm/config.py:83-84`、`:426-431`；更新检查"出网关闭 ⇒ 零请求"：`src/memoria/services/update.py:1-10`；自动检查默认**开**（`update.py:328-329`），可在设置里关闭 | **条件**：自动更新检查默认开启 + 出网开关默认开。README 必须写"可在 Settings 关闭出网（关闭后零请求）"，不得暗示默认零网络 |
| CLM-52 | Update check sends only a standard GET + User-Agent (no local data); release archive integrity is checked against `release-manifest.json` — **no digital signature** | bounded | code + 文档 | `src/memoria/services/update.py:1-18`（三条硬纪律 + 完整性校验边界）；`docs/design/release-format.md`（清单口径） | **禁止**写"防篡改 / 安全 / 已签名"；只能写"校验包结构与完整性（不含数字签名）" |
| CLM-53 | Local graph interaction counters (nodeRadius / graphStyle changes) are stored locally under `%LOCALAPPDATA%` and never uploaded | implemented | code | `src/memoria/storage/graph_telemetry.py`（本地 append-only JSONL；无网络调用）；`docs/design/kg-visualization-v0.md:204-221`（只采拓扑/事件事实） | 该条可只在 claims 表保留，README 不必展开 |

## 7. 工程可信度（可选展示，但必须真）

| 编号 | 断言 | 状态 | 证据类型 | 依据 / 命令 | 边界与 README 写法 |
|---|---|---|---|---|---|
| CLM-60 | **1,600+ automated tests** in the pytest suite (point-in-time: **1,624 passed** on 2026-10-26); run `pytest -q tests` for the current count | bounded（≥1,600；数字随时间增长） | 实测 | `python -m pytest -q tests`；产物：`artifacts/agent/verify/marketing/evidence/pytest.txt` | 写"1,600+ tests passing (pytest)"并给命令；**不写精确到个位的固定数字**（每次提交会漂）也不写"覆盖率 100%" |
| CLM-61 | Documentation-as-contract: conventions/design docs are the single source of truth, with machine gates for releases | implemented | 文档 + 脚本 | `docs/conventions/version.md:230-300`（Release 三条硬规则 + 机检）；`scripts/agent/release_preflight.py` | 只说"有门禁与规范"；不写"零缺陷" |
| CLM-62 | MIT license | implemented | LICENSE | `LICENSE`（MIT, © 2026 FreshTim） | 写 MIT |

## 8. 与 Obsidian 的关系（对比要克制）

| 编号 | 断言 | 状态 | 说明 |
|---|---|---|---|
| CLM-70 | Memoria's center of gravity is **knowledge points + built-in learning loop**, not a plugin ecosystem; Obsidian's strength is its mature plugin ecosystem and cross-platform presence. | editorial（设计取舍） | 只写"不同的取舍与适用场景"，**不贬低**；不声称"Obsidian 图谱中看不中用"（那是人的内部判断，不进公开文案） |
| CLM-71 | Obsidian = proprietary freemium; Memoria = MIT | **不在 README 使用** | 竞品许可与定价会变化，且公开文案只需说明自身 MIT；README 对比表**不含许可行**（2026-10-26 决定）。若将来要写，必须附官方来源链接并标"as of 日期" |
| CLM-72 | "Obsidian doesn't do spaced repetition" | **禁止** | Obsidian 有社区插件可做复习；写"内置、开箱即用"（ours is built in），不写"对方没有" |

## 9. 禁止词条（出现即返工）

| 禁止写法 | 原因 |
|---|---|
| 「图谱赋能 agent 检索 / 提高 agent 交互效率」 | 当前 agent 检索/读取路径**完全不读边**（`kg-ontology-v0.md:20`）；只能写 design-intent + roadmap |
| 「掌握程度评分 / mastery dashboard」 | 全仓无实现（CLM-22） |
| 「防篡改 / 安全 / 已签名 / 端到端加密」 | 发布包只做格式与完整性校验，不做数字签名（CLM-52）；人已明确放弃签名 |
| 「比 X 快 / 最快 / 性能第一」 | 无跨产品同口径 benchmark（CLM-43） |
| 「完全离线 / 零网络」 | 出网开关默认开、自动更新检查默认开（CLM-51） |
| 「AI 自动整理/自动改你的笔记」（暗示"静默、无备份、不可撤销"） | 默认档确实会自动放行常规写（CLM-31）；**可写**的是"分档 + 写前备份 + 可整批撤销 + 审计"；**禁止**写成"无痕自动改" |
| 「支持手机 / macOS / Linux」 | 当前发布形态 Windows 10/11 x64（`README.md` 前置条件；`docs/guides/operations.md`） |

---

## 10. 校验（先证红）

```powershell
# 一键校验本表里可机检的断言（代码/文档/实测数字/截图/版本/测试数）
python artifacts/agent/verify/marketing/check_claims.py
```

- 该脚本对每条**可机检**断言做"证据存在性 + 关键字符串/行号"检查；任一失败即 exit 1。
- 不可机检的（如"设计取舍是否克制"）标注为 `manual`，由审阅者按本表逐条对照。
- **本轮实测结果**与命令输出见 `artifacts/agent/verify/marketing/promo-rewrite.md`。

## 11. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-10-26 | 初版（task-182）：状态词表、1 定位 / 2 图谱 / 3 学习闭环 / 4 AI+笔记 / 5 性能 / 6 隐私 / 7 工程 / 8 竞品 / 9 禁止词条 + check_claims.py |
