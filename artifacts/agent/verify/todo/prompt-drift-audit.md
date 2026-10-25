# 知识库 Agent 提示词漂移审计（task-151）

> **审计者**：prompt-owner（常驻）｜**日期**：2026-10-25｜**状态**：第一批交付完成（未 commit，由 Lead 统一提交）
> **对象**：`resources/agent-prompts/**`（随包分发到 `<知识库>/.memoria/agent/`）+ `src/memoria/services/kb_agent.py` 分发链路 + `scripts/agent/prompt_drift_check.py`（新增机检）
> **一句话**：3 个分发提示词文件里发现 **3 类真实脱节**（教被代码剥离的语法、教不存在的图片属性、漏掉 2026-09-10 之后新增的知识库目录与 FSRS fail-closed 行为）；已全部修复，并建立**依赖指纹锁 + 符号校验 + 必红 selftest** 的机检，改前 exit 1（11 FAIL）、改后 exit 0，selftest 10/10 PASS。

---

## 0. 交付物与复跑命令

| # | 交付物 | 路径 |
|---|---|---|
| 1 | 本审计报告 | `artifacts/agent/verify/todo/prompt-drift-audit.md` |
| 2 | 修复后的分发提示词 | `resources/agent-prompts/{kb-agent-readme.md,kb-agent.zh-CN.md,kb-spec.zh-CN.md}` |
| 3 | 版本戳 bump（分发链路） | `src/memoria/services/kb_agent.py`（`KIT_VERSION/SPEC_VERSION` 1.0.0 → 1.1.0 + 语义注释） |
| 4 | 机检脚本（含 `--selftest`） | `scripts/agent/prompt_drift_check.py` |

```bash
# 机检本体（0=无 FAIL / 1=有 FAIL / 2=用法错误）
.venv/Scripts/python.exe scripts/agent/prompt_drift_check.py
# 自证尺子会红也会绿（10 个 fixture：绿基线 + 每类检查必红）
.venv/Scripts/python.exe scripts/agent/prompt_drift_check.py --selftest
# 维护头部依赖指纹
.venv/Scripts/python.exe scripts/agent/prompt_drift_check.py --print-deps <依赖路径...>
```

**改前实证（先证红，不是推断）**：修复前跑机检 `exit 1 / FAIL=11`，其中恰好包含本任务已知的脱节：

```
[FAIL] forbidden_syntax: 提示词把会被构建剥离的语法当推荐写法教：[[kp-id#extend]]  ← resources/agent-prompts/kb-spec.zh-CN.md:68
[FAIL] symbol_reference: 斜杠枚举里有代码中不存在的符号：enlarge（原文 width/enlarge/align）
[FAIL] version_stamp: …（3 个分发 md 均缺 spec-version / spec-deps / reviewed-on）
```

**改后**：`exit 0 / FAIL=0 / WARN=0`（3 条 INFO 是"未归类 token"清单，如实披露未校验项，不静默放过）。

---

## 1. 判定题：`[[kp-id#extend]]` 是"仍有锚点作用"还是"完全失效"？

### 结论：**A —— 仍会被读进 sidecar，但正文会被构建剥离并回写文件**（因此作为"推荐写法"是**有害误导**，不是完全失效）

**代码证据（读出来的，不是推的）**

1. 构建顺序 = **先同步、后剥离**（`src/memoria/graph/kb_build.py`）：
   - L289 `sync_file_sidecar_links(...)` 先跑；
   - L293 `body_stripped, hints_stripped = strip_known_wikilink_edge_hints(body)`；
   - L294–300 `if hints_stripped:` ⇒ **把剥离后的正文写回 `*.md` 文件**。
2. 同步函数确实读 hint：`kb_build.py:71-88 _apply_wikilink_edge_hint()` —— 只有 `extend` 会把 `links[].edge_type` 升为 `extend`；`reference/prerequisite/ref/analogy` 只会落到默认 `reference`。
3. 剥离实现：`src/memoria/services/link_md.py:27-49 strip_known_wikilink_edge_hints()` —— 命中 `is_wikilink_edge_type_fragment` 的 `#fragment` 被重写成 `[[target]]`。
4. 权威声明：`src/memoria/graph/edge_types.py:1-5` 文件头写明"sidecar `links[].edge_type` / `edges[].type`：唯一权威来源；正文 `[[target]]` 不含 `#类型`；遗留 `#prerequisite` 等仅在 kb 同步时读入 sidecar 并自正文剥离"。

**实测证据（用仓库内 venv 直接调这两个函数，2026-10-25）**

```text
输入正文: "前\n\n参见 [[d#extend]] 与 [[e#prerequisite]]、[[f#contain]]、[[g#ref]]、[[h#heading-anchor]]。"
sync 结果: links[d].edge_type="extend"（保住）；links[e].edge_type="reference"（降级）
strip 结果: "前\n\n参见 [[d]] 与 [[e]]、[[f]]、[[g]]、[[h#heading-anchor]]。"   # n=4
        ⇒ #extend/#prerequisite/#contain/#ref 全部被剥离；#heading-anchor 保留（非已注册边类型）
```

**为什么仍判为"有害误导"（三处实际伤害，均已写进修复后的规范 §4）**

| 伤害 | 证据 |
|---|---|
| ① 构建会**改用户的正文文件**（不是提示词里写的"声明一条边"这么无害） | `kb_build.py:294-300` 写回文件 |
| ② 预览期把 `#extend` 当目标名 ⇒ **断链**（渲染权威文档明说 `#type` 后缀不拆） | `docs/reference/preview-formats.md:62`；`preview-formats.md:154` |
| ③ 链接不在任何 KP `range` 内时，同步阶段被 `skipped_outside_kp` 跳过 ⇒ **边直接丢失，片段照样被剥** | `kb_build.py:142-146` + L293 |

**修法（已落地 `resources/agent-prompts/kb-spec.zh-CN.md:82`）**：从"推荐写法表"删除，改为**遗留写法警示**，并给出正确写法 = sidecar `edges[]`（`source_id/targets/type`，`sidecar_validate.py:283-325` 已支持，实测 `validate_sidecar` errors=[]）。同时修正 §7.3/§7.4/§8 中所有"教正文 #类型"的表述。

---

## 2. 逐文件审计（file:line 对照 + 严重度 + 修法）

> 行号：**旧** = 修复前 `resources/agent-prompts/**`；**新** = 修复后。证据行号为仓库当前文件。

### 2.1 `kb-spec.zh-CN.md`（6.8 KB，旧 mtime 2026-09-10，45 天）

| ID | 脱节（旧行） | 代码事实（file:line） | 严重度 | 修法（新行） |
|---|---|---|---|---|
| F1 | L68 表格推荐 `[[kp-id#extend]]`「声明 extend 边」；L70 同段把它与 reference 并列 | 构建迁移后**剥离并回写**（`kb_build.py:71-88,289-300`；`link_md.py:27-49`） | **高**（教用户被重写的语法） | 删除推荐；新增「遗留写法」警示 + sidecar `edges[]` 正确写法（新 L82） |
| F2 | L86 图片属性白名单写 `width/enlarge/align` | `enlarge` **不存在**；真实白名单 = `width/height/align/name-size/name`（`src/memoria/ui/static/app/js/surface/render-core.js:346` 明确 `console.warn(... 支持 width/height/align/name-size/name)`；`edit-handler.js:1701` 同集） | **中**（写了一个无效果属性） | 改为完整白名单 + "未知 key 被忽略并告警"（新 L98） |
| F3 | L118「图片路径带 `../` 或 `./` 前缀 → 渲染 404」 | `../` 确实非法；但 `./` 是**合法旧语义**（相对当前文件目录），不是 404（`docs/reference/preview-formats.md:110-114`） | **中**（把可用写法说成 404，且教不出"移动会断链"的真风险） | 拆开写：`../` 禁止；`./` 兼容但不推荐（新 L96/L131） |
| F4 | L71「同一处并列多个 `[[a]]`、`[[b]]` → 构建时合并为多目标」 | 实测：同一行两个不同锚点 → 生成 **2 个独立 links 条目**（`kb_build.py:142-201` `_find_link_index` 按 anchor 匹配，不按行合并） | **低**（语义描述失真，不影响写入） | 改为"各自成为独立链接/边"（新 L80） |
| F5 | §3 sidecar 样例只有 `links: []` / `edges: []`，未给边字段；而边类型自 2026-07 起就是 sidecar 权威（`edge_types.py:1-5`） | `sidecar_validate.py:283-325`（edges：type/source_id/targets/relevance）、`:327-412`（links：anchor_text/targets/edge_type/target_edges/instances） | **中**（agent 想标 extend 时无"正确写法"可依，只能退回 #extend） | §3 样例补 `edges[]` 实例与字段规则；明确 `links[]` 是构建产物、**不要手写**（新 L48-68） |
| F6 | 全篇无 **2026-10-10/11 之后**的 FSRS fail-closed 行为 | `resources/agent-prompts/fsrs.py:188-204`（cards.json 缺失/坏条目 → 抛错）、`:429-430`（grade 拒绝 cards.json 中不存在的 card_id；由 commit `d82e2cd2`/`1bbe6036` 引入） | **中**（agent 会按旧假设"空库=没到期"或先 grade 后落卡） | 新增 §9 复习调度（命令/数据/顺序/fail-closed/幂等/降级，新 L137+） |
| F7 | L11-18 事实源表与代码一致；`manifest.yaml` 禁手写等 | `kb_agent` 分发 + `storage/manifest.py`（构建生成） | — | 保留 |
| F8 | 无写入边界说明（本规范教"直接改文件"，但应用已有 W1–W4 写安全闸） | 闸门只覆盖应用内/MCP 写：`services/agent/apply.py:61-72`（origin 必填）、`:619`（写前备份）、`docs/design/agent-mcp-binding.md §4` | **低**（不是错，是边界未声明） | §1 顶部加"写入边界"（新 L11） |

### 2.2 `kb-agent.zh-CN.md`（5.1 KB，旧 mtime 2026-09-10）

| ID | 结论 | 证据/修法 |
|---|---|---|
| P1 | 三条工作流、红线、升级机制**与代码一致**（sidecar 权威、fsrs 命令、review 目录、Ask First 清单） | `fsrs.py` argparse（`--kb/--date/--card/--grade`）实测一致；`get_agent_prompt`/`install_kb_agent` 存在 |
| P2 | FSRS 工作流缺 fail-closed 提示 | 新增一句指向规范 §9（新 L60）；**把细则写进 kb-spec 而不是 prompt**，理由见 §6（prompt 是用户粘贴一次，不会随升级更新） |
| P3 | 缺版本戳/依赖指纹 | 头部补 `spec-version/spec-deps/reviewed-on`（新 L1-3，依赖 = `kb_agent.py` + `fsrs.py`） |

### 2.3 `kb-agent-readme.md`（1.5 KB，旧 mtime 2026-09-10）

| ID | 脱节（旧行） | 代码/真实库事实 | 严重度 | 修法（新行） |
|---|---|---|---|---|
| R1 | 文件表只列 5 个文件 + `review/`，**完全没提** `.memoria/agent/` 下新增的应用目录 | 真实库实测（`docs/example/AAA_Vocab/.memoria/agent/`，只读查看）：`capabilities.json`、`skills/`、`sessions/`、`backups/`、`scratch/`、`attachments/` 均已存在；代码出处：`services/agent/plugins.py:184,549-550`（capabilities.json）、`skills.py:97,528`（skills）、`session/store.py:56-58`（sessions）、`backup.py:80-82`（backups）、`scratch.py:1-10`（scratch）、`attachments.py:24-25`（attachments） | **高**（agent 可能手改会话/撤销点/能力开关；README 是 agent 唯一的目录契约） | 文件表扩为"文件与目录"，逐项给"谁维护 + 勿手改"（新 L8-23）；红线补 2 条（新 L32-33） |
| R2 | 旧「升级」只说"再次执行创建 Trae 智能体" | 真实行为：**打开知识库即自动 ensure**（`js/kb-agent.js:75-89` → `app.js:957,1118` 调用 `MemoriaKbAgent.ensure()`）；安装只覆盖 FILE_MAP + `.kit.json` | **中**（用户不知道何时会刷新） | 升级节写清自动刷新 + 覆盖范围（新 L35-40） |
| R3 | 未声明"直接编辑不经过写安全闸" | `apply.py:61-72,619`（W1 origin/W3 备份）；MCP 文档 §4（W2/W4） | **低** | 红线补 1 条（新 L33） |

### 2.4 `fsrs.py`（25.8 KB，mtime 2026-10-11，15 天）—— **代码文件，审计但未改**

- CLI：`due/init/grade/--selftest`、`--kb/--date/--card/--grade` 全部与提示词一致（`python resources/agent-prompts/fsrs.py --selftest` 实测 **PASS 16/16**）。
- 行为已 fail-closed（`fsrs.py:188-204,429-430`），提示词侧缺口按 F6 修在规范 §9；**fsrs.py 本身无需改**（改它属于代码改动，不在本任务范围，也无必要）。
- 版本戳不加在 `.py`：C4 只约束"提示词 md"；fsrs.py 自证靠 `--selftest` + 分发完整性（C1 会 `compile()` 它）。

### 2.5 `preview-formats.md`（来自 `docs/reference/`，旧 mtime 2026-09-20）—— **参考文档，审计但未改**

- 与代码一致：`#type` 不拆（L62/L154）、`./` 旧语义合法（L110-114）、图片属性白名单 = width/height/align/name-size/name（L87-93）、`../` 404（L111）。
- 本次它是**修 F2/F3 的权威依据**；kb-spec 头部已把 `docs/reference/preview-formats.md` 列为依赖指纹（它一变，机检红）。
- 未加 `spec-version` 戳：它是产品文档（`get_reference_doc` 也读它），不是"提示词"；用 C1（存在性/非空）+ C5（陈旧）覆盖。**理由写死在脚本 docstring**。

### 2.6 `organize.zh-CN.md`（9.1 KB，mtime 2026-09-08，47 天）—— 追加要求：A 死文件 还是 B 仍在使用？

**结论：B —— 仍在使用，但【不经 FILE_MAP 分发】**，不存在隐藏分发路径。

| 证据 | 内容 |
|---|---|
| 引用点 1（后端 RPC） | `src/memoria/presentation/api/ui.py:1085-1101 get_agent_prompt()`：候选名 `organize.{lang}.md` / `organize.zh-CN.md`，从 `resources_dir()/agent-prompts/` 读取 |
| 引用点 2（前端调用） | `src/memoria/ui/static/app/js/import-flow.js:139` `await a.call("get_agent_prompt", "zh-CN")`（整理弹窗取提示词） |
| 引用点 3（打包白名单） | `packaging/build.py:234 "agent-prompts/organize.zh-CN.md"` —— 随包但不进 `.memoria/agent/` |
| 反证：无目录扫描分发 | 全仓 `agent-prompts` 的代码引用只有：`kb_agent.py`（**按 FILE_MAP 白名单**遍历）、`ui.py`（两个按名读取的 RPC）、`build.py`（打包白名单）、`skills.py`（注释类比）。**没有任何** `iterdir()/glob()` 把该目录整体复制进知识库 |
| 反证：真实库未落地 | 只读检查 `docs/example/{AAA_KnowledgeBase,AAA_Vocab,rich-content-test,showcase,行政法}/.memoria/agent/`：**均只有** `README.md / prompt.zh-CN.md / kb-spec.zh-CN.md / preview-formats.md / fsrs.py / .kit.json`（+ 应用管理目录），**无 organize.zh-CN.md** |

**处理**：不删（删除属不可逆操作，交 Lead 裁决；且它确实仍被程序内 RPC 使用）。在机检里登记为**应用内部资源**（`APP_INTERNAL_ASSETS`，脚本会校验引用证据仍存在），这样：
- 若未来有人误删 → C1 报"引用证据失效"；
- 若未来目录里多出未归类文件 → C1 WARN"可能是隐藏分发路径或死文件"，**这正是追加要求里担心的漏检类别**。
- 机检覆盖口径：**分发完整性按 FILE_MAP 白名单**（因为真实分发就是白名单），**目录全量**只用于"孤儿/内部资源归类"告警（两者都做了）。

---

## 3. S1–S5 与提示词的映射（哪些该教、哪些不该教）

> 判断原则：`.memoria/agent/**` 的提示词是给**外部文件编辑型智能体**（Trae）用的；S1–S5 主要是**应用内 Agent / MCP 工具面**的能力。**不能把应用内能力写进知识库提示词**（知识库工作区里没有那套运行时），但**确实改变了知识库文件格式/目录布局**的部分必须同步。

| 项 | 是否影响 KB 提示词 | 证据与结论 |
|---|---|---|
| **S1 三级粒度读**（`outline`/`section`/`snippet`） | **否**（工具面专属） | 工具注册在 `tools/kb.py:908-951` 与 `mcp_server.py:143-209`（仅 4 把 MCP 工具）。KB 提示词教的是"先读 sidecar 索引、只展开目标 KP 的 range"（旧 kb-agent L34）——方向一致，无脱节。**不教**应用内工具名（工作区里不存在） |
| **S2 写安全四道闸**（W1 origin/W2 读后写/W3 备份/W4 审批） | **是（只教边界，不教机制）** | W1 `apply.py:61-72`；W3 `apply.py:619`；W2/W4 `docs/design/agent-mcp-binding.md §4`。这些闸**不覆盖直接文件编辑** ⇒ README/规范必须写明"直接编辑无闸门，自行备份"（已加：README L33、kb-spec L11）。**不教** `origin`/`read_handle` 等应用内字段（外部 agent 接触不到） |
| **S3 MCP 工具面** | **是（只教"如何被应用写"不存在）** → 结论：**不写进分发提示词** | MCP server 存在（`python -m memoria.services.agent.mcp_server --kb`，`mcp_server.py:692-696`），但它是**外部客户端接入形态**，且需 Memoria 的 Python 运行时；KB 工具包不随包分发 MCP 配置、冻结版无 `python -m memoria` 入口 ⇒ 教了也跑不动，属"教未实现/不可用能力"。已在 README 用"直接编辑 vs 写安全闸"边界替代说明（真实、用户可用） |
| **S4 扩展点**（能力插件 / 库级注册表 / skills） | **是**（新增了 `.memoria/agent/` 下的文件/目录） | `capabilities.json`（`plugins.py:184,549-550`）+ `skills/**`（`skills.py:97,528`）已补进 README（新 L20-21、L32、L39）。**不教**插件契约字段（`impl`/`ext.` 等属应用侧，用户用面板开关即可） |
| **S5 trace** | **是（只教"这些目录勿手改"）** | 会话/备份/scratch/attachments 落在 `.memoria/agent/`（`session/store.py:56-58`、`backup.py:80-82`、`scratch.py`、`attachments.py:24-25`）；README 已标"应用（勿手改）"。**不教** trace 工具/OTel（应用内能力） |
| **KG 本体 v0（已冻结、代码未实现）** | **必须不教** | `docs/design/kg-ontology-v0.md:79`：D-KG-05 **明确否决**新增语义类型（prerequisite/sequence/contrast/exemplify）；v0 类型空间仍是 reference/extend/contain。kb-spec 只教这 3 种（与 `edge_types.py:12-25` 一致）⇒ **未教未实现能力**（已核对） |

---

## 4. 机检设计：`scripts/agent/prompt_drift_check.py`

### 4.1 五类检查与"未来代码改了会不会红"

| 检查 | 抓什么 | 靠什么权威 | 未来代码改行为时是否红 |
|---|---|---|---|
| **C1 distribution_integrity** | 分发源缺失/空/不可解析；README 声明 ↔ FILE_MAP 双向；`.memoria/agent/<名>` 必须是真实落点；孤儿/隐藏分发路径；打包白名单漏登记 | `kb_agent.py` 的 `FILE_MAP/REFERENCE_DOCS/KIT_FILE/REVIEW_DIRNAME`（AST 解析，不 import） | 新增/删除分发文件、改落点名、打包漏带 ⇒ **FAIL** |
| **C2 symbol_reference** | 提示词反引号里的**工具名/RPC 名/字段名/代码路径/KB 路径/斜杠枚举**必须真实存在；fsrs 子命令与 flag 对齐 argparse；`§N.M` 章节引用必须存在；未归类 token 记 INFO（不静默） | `src/memoria/**` 源码字面量、`edge_types.py`、`mcp_server.py`/`tools/kb.py` 工具名、`fsrs.py` argparse、`render-core.js` 图片属性白名单、`docs/reference/preview-formats.md` | 工具改名/删除、字段改名、图片属性白名单变化、fsrs 子命令改名 ⇒ **FAIL**（本次已实证抓到 `enlarge`） |
| **C3 forbidden_syntax** | 把**会被代码 strip** 的 `[[id#type]]` 当推荐写法教（同行无"遗留/剥离/不要"限定词）；反向检查：代码不再 strip 而提示词还说会 strip ⇒ WARN | `edge_types.py`（`EDGE_TYPES` + `WIKILINK_HINT_ALIASES`）+ `kb_build.py` 是否调用 strip + `link_md.py` 是否有实现 | 本次已实证抓到 kb-spec L68；代码若取消 strip ⇒ WARN 提醒旧结论过期 |
| **C4 version_stamp + 依赖指纹锁** | 3 个提示词 md 头部必须有 `spec-version`（= `kb_agent.SPEC_VERSION`）、`reviewed-on`、`spec-deps: path@sha12`；**每个依赖当前 sha256 前 12 位必须与记录一致** | `kb_agent.py` 常量 + 文件 sha256 | **这是 KPI 的主锁**：依赖代码任何字节变化 ⇒ **FAIL**，强制"代码改了 ⇒ 提示词 owner 必须复核并重签指纹" |
| **C5 staleness** | `reviewed-on` 超过 90 天 ⇒ WARN；依赖的最近 git 提交/ mtime 比 reviewed-on 新 90 天以上 ⇒ WARN | git + 文件时间 | 长期无人维护 ⇒ WARN（不红，避免纯时间噪声；真正的"代码改了"由 C4 红） |

### 4.2 为什么不是"弱检查"（反自欺设计）

1. **先证红再修**：修复前 `exit 1` 且 FAIL 恰好命中 3 类真实脱节（C3 的 `#extend`、C2 的 `enlarge`、C4 的缺戳），不是"写完就绿"。
2. **必红 fixture**：`--selftest` 10 个用例——绿基线 + 每类检查至少一份红 fixture（删分发源、README 漏声明、编造符号、编造 fsrs 子命令、教剥语法、版本戳不一致、**依赖内容改了但指纹没重签**、陈旧阈值）；fixture 不红 ⇒ selftest 自己 `exit 1`（本次 10/10 PASS）。
3. **依赖指纹锁**：这是"下次代码改了行为"能被抓到的物理机制——不依赖 prompt-owner 记得去读 diff。
4. **未覆盖项显式披露**：未归类的反引号 token 输出为 INFO 清单（如 `range`/`log` 这类单字段名），不假装全绿。
5. **确定性**：无网络、无第三方依赖、AST 解析不 import 项目模块；`--json` 可被 team_audit 消费。

### 4.3 接入位置：建议挂 `team_audit.py`（不是只在发版前跑）

**理由**：C4 的价值是"代码一改就红"，而 `release_preflight.py` 只在**发版时**跑——一次发版周期内可能积累多轮行为变更，提示词会烂一整个周期才被发现；`team_audit.py` 是每轮团队自检（AGENTS.md §0.5 L7）的入口，跑得起（本脚本 ~1s、离线）。**不挂 release_preflight 的唯一场景**是"发版前才想起来"——正是本项目已反复失败的模式。

**为什么没直接改**：task-151 的写域是 `resources/agent-prompts/**` + `scripts/agent/prompt_drift_check.py`；`team_audit.py` 不在写域（避免与 Lead/owner 写冲突）。**请 Lead 应用下面这段补丁**（约 20 行，`subprocess/sys/json` 已在该文件 import）：

```python
# scripts/agent/team_audit.py：在 check_deliberation_quality 之后加一行调用
def check_prompt_drift(ctx: AuditContext) -> None:
    """知识库 Agent 提示词漂移（task-151 的机检投影）：子进程跑 prompt_drift_check.py。"""
    check = "prompt_drift"
    script = ctx.repo / "scripts" / "agent" / "prompt_drift_check.py"
    if not script.is_file():
        ctx.add(check, INFO, "未找到 prompt_drift_check.py，跳过", ctx.rel(script))
        return
    try:
        proc = subprocess.run([sys.executable, str(script), "--repo", str(ctx.repo), "--json"],
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        ctx.add(check, FAIL, f"提示词漂移机检无法执行：{exc}", ctx.rel(script))
        return
    if proc.returncode not in (0, 1):
        ctx.add(check, FAIL, f"提示词漂移机检执行错误（exit={proc.returncode}）", ctx.rel(script))
        return
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        ctx.add(check, FAIL, "提示词漂移机检输出不可解析", ctx.rel(script))
        return
    for item in payload.get("findings") or []:
        sev = str(item.get("severity"))
        ctx.add(check, sev if sev in (FAIL, WARN, INFO) else WARN,
                f"[{item.get('check')}] {item.get('message')}", str(item.get("evidence") or ""))

# run_checks() 末尾（ctx.findings.sort(...) 之前）：
#     check_prompt_drift(ctx)
```

---

## 5. 为什么不破坏分发幂等性（读代码后的结论，不是拍脑袋）

### 5.1 代码事实

- `install_kb_agent()`（`src/memoria/services/kb_agent.py:84-145`）：逐个 `FILE_MAP/REFERENCE_DOCS` 源读字节 → **与目标文件字节比较**：相同进 `skipped`，不同才 `_atomic_write`。**没有任何"按版本拒绝覆盖"的分支**；`KIT_VERSION/SPEC_VERSION` 只写进 `.kit.json` 并回给前端做提示。
- `review/**`：安装只 `mkdir(review)`，**从不写 `review/` 下任何文件**（`kb_agent.py:112-131`）。
- 自动刷新：打开知识库即 `MemoriaKbAgent.ensure()` → `install_kb_agent`（`js/kb-agent.js:75-89`；调用点 `app.js:957,1118`）。

### 5.2 本次 bump 的实测（临时目录模拟，不碰用户库）

```text
1st install: written=[README.md, prompt.zh-CN.md, kb-spec.zh-CN.md, fsrs.py, preview-formats.md]
             kit=1.1.0 spec=1.1.0；.kit.json 内容正确
2nd install: written=[]  skipped=5                      ← 幂等仍成立
review/progress.json 探针写入 {"probe": true}
3rd install（模拟老库 prompt 被改回旧版）: written=[prompt.zh-CN.md]（只补差异文件）
review preserved: True                                 ← review 未被覆盖
prompt refreshed: True（含 spec-version: 1.1.0）
```

**结论**：bump 版本**不会**让已分发库拒绝覆盖（没有这种代码）；它只是把"工具包版本"从 1.0.0 抬到 1.1.0，老库下次打开会自动补写差异文件。反过来说，**只 bump 不改进内容是无效的**——覆盖决策只看字节，所以必须改 `resources/agent-prompts/**`（本任务已改）。

### 5.3 一个必须说清的边界（不美化）

`prompt.zh-CN.md` 是**用户粘贴到 Trae 的一次性指令**，升级时文件会被刷新，但**用户 Trae 里的那份不会自动更新**。因此：
- 所有**新规则**都必须写进 `kb-spec.zh-CN.md`（每次会话先读、随升级自动覆盖）；
- `kb-agent.zh-CN.md` 只做版本戳 + 指向规范 §9 的最小改动（新规则不依赖它生效）。

---

## 6. 维护流程（留给下一任 prompt-owner / 未来自己）

1. 改代码或改提示词后：`python scripts/agent/prompt_drift_check.py`，看 FAIL。
2. 若 FAIL 是"依赖已变更"：逐条复核提示词相关断言 → 改提示词 → `--print-deps <依赖...>` 拿新 sha12 → 更新头部 `spec-deps` / `reviewed-on` / 必要时 bump `SPEC_VERSION` 与文件 `spec-version`。
3. `--selftest` 必须 PASS（防止有人把尺子改坏）。
4. 发版前由 `team_audit`（接入后）自动兜底；未接入前请 Lead 在收口前手动跑一次。

**版本语义**：`KIT_VERSION` = 工具包（分发内容整体）版本；`SPEC_VERSION` = 规范语义版本。两者当前同为 1.1.0；**只与"规则语义变更"一起 bump**（格式/错字修正也 bump，因为文件字节变了），并在 `kb_agent.py` 顶部注释里已写死"bump 不参与覆盖决策"这一事实，防止下一任误以为可以靠版本号推进升级。

---

## 7. 残余风险 / 未覆盖（如实登记，不装全绿）

1. **本轮修的是 `resources/agent-prompts/**`；仓库里还有 4 份文档仍在教 `[[id#type]]`**（不在我的写域，需 Lead 派给 doc-owner）：
   - `docs/conventions/markdown-form-std.md:17-19`（`[[]]` 语法**契约**）
   - `docs/prompts/role-a-content-agent.md:98-99`
   - `docs/guides/usage-agent-workflow.md:159`
   - `docs/design/kb-agent.md:112`（设计文档历史记录，可加"已废弃"注记而非改历史）
   风险：导入/整理链路的 agent 仍可能被这 4 份教成写 `#extend`（虽然构建会迁移+剥离，不会丢边，但会重写正文）。
2. **C2 的边界**：只校验"反引号里的符号"，**自然语言里的失实断言**（如"构建会合并为多目标"）机器抓不到；本轮是人工比对代码抓到的。缓解：C4 依赖指纹把相关代码文件锁住——相关文件一改就红，迫使人工复核。
3. **C5 阈值 90 天**：纯时间告警，不判对错；真正判"脱节"的是 C4 指纹与 C1–C3。
4. **`organize.zh-CN.md` 仍 47 天未维护**（它不在分发链，但仍是程序内 Agent 整理提示词的单一事实源；`preview-formats.md` 头部第 7 行明确要求"渲染行为变更后同步该提示词"）。**建议 Lead 单开一项**（属"程序内 Agent 整理提示词"维护，不在本任务写域；本轮未改，避免超范围）。
5. **team_audit 接线未落**（写域限制）：见 §4.3 补丁；接入前 KPI 只能靠"人记得跑脚本"——即本任务要消灭的那种依赖。**建议 Lead 本轮就接线**。
6. **本轮已跑的全量回归**（2026-10-25）：`pytest -q tests` = **1475 passed / 0 failed（85s）**；`node --check` × 全部 `src/memoria/ui/static/app/js/**/*.js` = **0 失败**；`node scripts/i18n_selftest.js` = **PASS**；`python scripts/agent/team_audit.py` = **FAIL=0**（WARN=53 为团队既有状态，与本任务无关）。

---

## 8. 验收对照（task-151 关闭条件）

| 条件 | 证据 |
|---|---|
| 审计报告（逐文件 × 逐条，file:line + 严重度 + 修法） | 本文 §1–§3 |
| 修复后的 `resources/agent-prompts/**` | 3 个 md 已改；`fsrs.py` 审计后判定无需改 |
| `prompt_drift_check.py`（含 `--selftest` + 必红） | 改前 exit 1（11 FAIL，含 3 类真实脱节）；改后 exit 0；selftest 10/10 PASS |
| 说明"为什么不破坏分发幂等性" | 本文 §5（代码路径 + 临时目录实测） |
| `organize.zh-CN.md` 归属结论 | 本文 §2.6（B：仍被 RPC 使用；无隐藏分发路径；真实库未落地） |
| 不 commit | 是（工作区改动待 Lead 统一提交） |
| 不碰 `docs/example/AAA_Vocab/**` | 只读查看；未写 |

**关键 KPI 自检**：下次若有人改了 `edge_types.py`/`kb_build.py`/`render-core.js`/`fsrs.py`/`kb_agent.py` 等被声明为依赖的文件而没复核提示词 ⇒ **C4 必红 exit 1**；若有人把提示词里的工具名改成不存在的 ⇒ **C2 必红**；若有人重新教 `#extend` ⇒ **C3 必红**。这三把尺子都已在当前仓库上**真跑红过**，不是推断。
