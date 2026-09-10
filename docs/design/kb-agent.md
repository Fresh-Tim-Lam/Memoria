# 知识库 Agent（Trae 智能体）设计与契约

> **用途**：定义"把知识库目录变成可被 Trae 智能体直接学习/维护/复习"的设计——知识库侧契约、状态布局、FSRS 确定性调度、三条工作流，以及 Memoria 产品需内置的资源与入口。
> **目标读者**：项目负责人（评审范围与取舍）；实施 Agent（按 §7 落地产品侧改动）；使用者（按 §8 在 Trae 中创建智能体）。
> **关联文档**：[usage-agent-workflow.md](../guides/usage-agent-workflow.md)（导入流水线角色 A/B）、[import-format.md](../conventions/import-format.md)（平面格式）、[markdown-form-std.md](../conventions/markdown-form-std.md)（`[[]]` 语法）、[context-key.md](../conventions/context-key.md)（上下文防火墙）、[AGENT.md](../../AGENT.md)（边界与 Ask First）、[to-dolist.md](../to-dolist.md)（V02 遗忘曲线·主动复习）。
> **状态**：草稿（待评审），2026-09-10。

---

## 1. 目标与范围

**目标**：用户在 **Trae** 中直接打开知识库目录，即可使用一个智能体完成三件事：
1. **答疑解惑**：基于本库内容讲解、追问、补链，帮助收获知识；
2. **撰写与整理**：把用户想写入的知识**撰写**成合规 KP 入库，或把原始材料**整理**入库，并维护 KP 元数据与链接（跳转 / 边类型 / 别名 / 标签）；
3. **间隔重复复习**：以 KP 为卡，按 FSRS 调度复习，帮助长期记忆。

**非目标**：不把 LLM 内嵌进 Memoria 应用运行时；不替代产品既有的导入/构建/校验链路。注意：**"不修改原文语义"只约束「整理」模式**；「撰写」模式是**新增内容**，须遵守来源纪律（§4.2A）——两者不可混用。

**适用范围**：**一个 Trae 工作区 = 一个知识库**（Q5 ✅）——契约与 `review/` 都在该库 `.memoria/agent/` 下；多库各自开工作区，语言跟随该库正文语言。

**已锁定决策（用户 2026-09-10 拍板）**

| 项 | 决策 |
|---|---|
| 载体 | **Trae 智能体**（知识库侧契约 + 产品内置可复制文档） |
| 契约落点 | 知识库 `.memoria/agent/` 之下；产品内置**同源**资源 |
| 写入面 | 仅知识库内容：`*.md` 与 `.memoria/*`（`manifest.yaml` **不手写**） |
| 复习算法 | **FSRS** |
| 调度执行 | 产品内置 `fsrs.py`，由 agent 运行（**确定性**） |
| 卡片粒度 | **一 KP 多卡** |
| 卡片生成 | **首次复习时生成并落盘**，后续复用 |
| 评分口径 | **FSRS 四级**（Again / Hard / Good / Easy） |

## 2. 目录与文件布局

```
<知识库>/
├── *.md                          ← 知识内容（事实源之一）
└── .memoria/                      ← 扫描器跳过（SKIP_DIR_NAMES），不进文件树、不参与构建
    ├── sidecars/**                ← KP 索引：id/name/tags/aliases/range（事实源之二）
    ├── pending.json               ← 待确认提议（产品维护）
    ├── manifest.yaml              ← ⚠ 产品「构建」生成，agent 不手写
    ├── cache/**                   ← 可再生缓存
    └── agent/                     ← 【新增】用途明确：供 Trae 智能体使用
        ├── README.md              ← 契约总纲（首行声明"本目录供 Trae 智能体使用"）
        ├── prompt.zh-CN.md        ← ① Trae 智能体**指令**（创建时粘贴一次；稳定）
        ├── kb-spec.zh-CN.md       ← ② 知识库**编撰/维护规范**（agent 按需读；随版本更新）
        ├── fsrs.py                ← 确定性调度（产品内置）
        └── review/
            ├── cards.json         ← 卡片定义（一 KP 多卡）
            └── progress.json      ← 卡片状态（FSRS）+ 复习日志
```

> **为什么拆两份**：①是"智能体人格 + 工作流 + 红线"，创建 Trae 智能体时粘贴一次、内容稳定；②是编撰细则，由 Memoria 随版本升级——**规则更新只需替换 ②，无需用户重建智能体**。

| 仓库源（唯一维护点） | 知识库落点（产品复制分发） |
|---|---|
| `resources/agent-prompts/kb-agent.zh-CN.md` | `.memoria/agent/prompt.zh-CN.md` |
| `resources/agent-prompts/kb-spec.zh-CN.md` | `.memoria/agent/kb-spec.zh-CN.md` |
| （内置模板） | `.memoria/agent/README.md` |

| 文件 | 由谁生成 | 由谁写 |
|---|---|---|
| `README.md` / `prompt.zh-CN.md` / `kb-spec.zh-CN.md` / `preview-formats.md` / `fsrs.py` | 产品（内置资源） | 仅产品（升级时覆盖） |
| `review/cards.json` | agent（首次复习） | agent |
| `review/progress.json` | `fsrs.py` | `fsrs.py`（agent 只调用） |

## 3. 事实源与红线

**三个事实源**：`*.md`（知识正文）＋ `.memoria/sidecars/**`（KP 元数据）＋ `.memoria/agent/review/**`（学习状态）。三者职责分离，学习状态**不得**写进 sidecar。

**红线（不可让渡）**
1. **不覆盖原文**：整理只做排版/划分/标注，不改知识语义（同 [organize.zh-CN.md](../../resources/agent-prompts/organize.zh-CN.md) 规则）。
2. **md 与 sidecar 双写一致**：改 KP 必须同时改 sidecar，且符合 sidecar schema。
3. **`manifest.yaml` 不手写**：由产品「构建」生成（同 [role B 规则](../guides/usage-agent-workflow.md)）。
4. **答疑零幻觉**：每个结论必须能指到 `[[kp-id]]`；检索不到就明说"库中没有"。
5. **调度必须确定性**：间隔/到期日一律由 `fsrs.py` 计算，**LLM 不做日期算术**。

## 4. 三条工作流

| 工作流 | 触发 | 读 | 写 | 收尾校验 |
|---|---|---|---|---|
| 答疑/讲解 | 用户提问 | sidecar 索引 → 目标 md 的 `range` | 不写 | —— |
| 撰写/整理/维护 | 用户请求（要写入的新知识 / 原始材料） | sidecar 索引（先查重）→ 相关 md + sidecar | md + sidecar（双写） | `校验/构建`（无错误） |
| 复习（FSRS） | "开始复习" | cards + progress | cards + progress | `fsrs.py` 幂等 |

### 4.1 答疑/讲解 — 检索协议
1. **先索引后展开**：读 `.memoria/sidecars/**` 的 KP 索引（id/name/tags/aliases）定位候选，**只展开**目标 KP 在 md 中的 `range`（避免整库入上下文）。
2. **引用规范**：每条结论给出 `[[kp-id]]` + 关键 snippet；跨 KP 关系用既有边类型（reference/extend）。
3. **拒答**：索引与正文均无支撑 → 明确说"当前知识库没有相关内容"，可建议补充新 KP，但**不得编造**。

### 4.2 撰写 / 整理 / 维护

> **元数据权威**：KP 完全来自 sidecar `knowledge_points[]`（[kp_resolver.py](../../src/memoria/services/kp_resolver.py)：`resolve_knowledge_points(body, sidecar)` 只读 sidecar）。md 的 frontmatter 是导入期遗留，**不参与** KP 解析——维护 KP 必须写 sidecar；新建文件的 frontmatter 可写可不写。

**4.2A 撰写（用户要写入的新知识）**

用户给主题/要点/口述，由 agent **撰写**为可入库的 KP。三条纪律：

1. **来源可溯（防幻觉污染）**：内容必须能对应到用户提供的要点、指定资料或库内既有 KP。agent 自行补充的一般性内容，须在正文用 HTML 注释标注（沿用 [organize 标注体系](../../resources/agent-prompts/organize.zh-CN.md)）：
   `<!-- ⚠ 来源待核实：<说明> -->`。
2. **先查重再落笔**：先按 sidecar 索引检查是否已有同概念 KP → 有则**扩写/合并**，不重复新建。
3. **必须挂链**：新 KP 至少一条 `[[已有-kp-id]]`（reference/extend），并在相关已有 KP 处补反向链接，避免孤岛。

**4.2B 整理（原始材料 → KP，不改语义）**

材料→KP 的转换严格遵循 [organize.zh-CN.md](../../resources/agent-prompts/organize.zh-CN.md)（保留原文、只做排版/划分/标注）。

**4.2C 维护（KP 与链接的日常维护）**

- **KP 建立**：`id`（英文 slug，全局唯一）、`name`（与正文标题一致）、`tags`、`aliases`（如「强哥」→「光头强」）、`description`、`range{start,end}`（snippet 必须能在正文**精确匹配**，`end` 非空行）。
- **跳转与链接**：正文写 `[[id]]` / `[[id|显示文本]]` / `[[id#extend]]`；`contain` 边由标题层级自动生成，**不手标**；悬空链接按虚链保留（不建空文件）。
- **边与关系**：`reference`（引用）／`extend`（下游）写在正文或 sidecar `edges[]`；改完由 Memoria「构建」同步 sidecar `links[]`。
- **文件组织**：按主题规划目录与文件名（英文 kebab-case，正文标题中文）；避免根目录散落。

**Ask First 清单**（停下问用户）：新建 md 文件、改 KP id / 重命名文件（全库级联）、删除文件或 KP、跨目录移动、批量重组、任何影响 `.memoria` 语义一致性的操作。

**收尾自检**（缺一不可）：每个 KP 的 `name` 能在正文找到标题；每个 sidecar `range` snippet 可精确匹配且 `end` 非空；所有 `[[id]]` 的目标存在（或有意为虚链）；提示用户在 Memoria「构建」「检查」无错误后交付（同 [§4.8 交付前验证](../guides/usage-agent-workflow.md)）。

### 4.3 复习 — FSRS 闭环
1. `due` 取到期卡 → 逐卡提问（题面来自 `cards.json`）；
2. 用户自评 **Again/Hard/Good/Easy**；
3. 运行 `fsrs.py grade` 计算新状态（stability/difficulty/due）并写 `progress.json`；
4. 若某 KP **尚无卡**，先由 agent 生成该 KP 的候选卡（问答/填空/反向）→ **按 KP 批量列出清单请用户过目** → 落盘 `cards.json`，再进入调度（Q2 ✅）。

## 5. 数据模型

### 5.1 `review/cards.json`
```jsonc
{
  "schema_version": 1,
  "updated_at": "2026-09-10T00:00:00Z",
  "cards": [
    {
      "card_id": "bayes-rule",          // 一 KP 首卡 = kp_id
      "kp_id": "bayes-rule",
      "file": "probability/bayes.md",   // KB 相对路径（用于回跳）
      "type": "basic",                  // basic | cloze | reverse
      "front": "什么是贝叶斯公式？",
      "back": "P(A|B)=P(B|A)P(A)/P(B)",
      "source": "agent",                // agent | user
      "created_at": "2026-09-10T00:00:00Z"
    },
    {
      "card_id": "bayes-rule#2",        // 派生卡 = kp_id + "#" + 序号
      "kp_id": "bayes-rule",
      "file": "probability/bayes.md",
      "type": "cloze",
      "front": "P(A|B) = [ ] · P(A) / P(B)",
      "back": "P(B|A)",
      "source": "agent",
      "created_at": "2026-09-10T00:00:00Z"
    }
  ]
}
```

### 5.2 `review/progress.json`
```jsonc
{
  "schema_version": 1,
  "algorithm": "fsrs",
  "fsrs_version": "5",
  "params": [ /* 19 个默认权重 */ ],
  "request_retention": 0.9,
  "updated_at": "2026-09-10T00:00:00Z",
  "cards": {
    "bayes-rule": {
      "state": "review",              // new | learning | review | relearning
      "due": "2026-09-13",
      "stability": 3.12,
      "difficulty": 5.4,
      "elapsed_days": 3,
      "scheduled_days": 3,
      "reps": 4,
      "lapses": 1,
      "last_review": "2026-09-10"
    }
  },
  "log": [                            // 只追加
    { "ts": "2026-09-10T12:00:00Z", "card_id": "bayes-rule", "grade": 3,
      "elapsed_days": 3, "scheduled_days": 3, "next_due": "2026-09-16" }
  ]
}
```

## 6. `fsrs.py` 规格

**CLI**
```
python .memoria/agent/fsrs.py due   [--date YYYY-MM-DD]           # 输出到期 card_id 列表
python .memoria/agent/fsrs.py grade --card <id> --grade 1..4 [--date YYYY-MM-DD]
python .memoria/agent/fsrs.py init  --card <id> [--date YYYY-MM-DD]
```
- **输入/输出**：读写 `.memoria/agent/review/progress.json`；`due` 亦读 `cards.json` 以对齐卡全集。
- **幂等**：同一 `(card, date, grade)` 重复执行结果一致；重复 `grade` 以 `log` 已有记录为准不叠加。
- **确定性**：默认权重与 `request_retention` 固定写入 `progress.json`，可审计、可复算。
- **降级**：若 `fsrs.py` 缺失（旧库未初始化），agent **只**往 `log` 追加评分记录、**不更新** `due`，并提示用户到 Memoria 执行「为知识库创建 Trae 智能体」。
- **不含 LLM**：纯计算，无网络访问。
- **参数固定**：采用 **FSRS-5 官方默认 19 权重** + `request_retention = 0.9`，写入 `progress.json` 的 `params`；**不提供训练/界面调参**（Q1 ✅）。

## 7. 实施指示（给开发/实施 Agent）

> **性质**：新增 `.memoria/agent/` 相关逻辑，属 [AGENT.md](../../AGENT.md) **Ask First**（影响 `.memoria/` 一致性）——开工前需用户授权。
> **产出目标**：用户在 Memoria 点一下，即可在知识库内生成"可复制到 Trae 的智能体包"，且不污染知识内容、可随版本升级。

### 7.1 任务分解

| # | 任务 | 交付物 | 验收标准 |
|---|---|---|---|
| T1a | 内置**指令** | `resources/agent-prompts/kb-agent.zh-CN.md`（**已起草**） | 稳定、自包含：角色 + 三条工作流 + 红线；要求 agent 先读 `kb-spec.zh-CN.md` |
| T1b | 内置**规范** | `resources/agent-prompts/kb-spec.zh-CN.md`（**已起草**） | 自包含（不依赖仓库 `docs/` 路径）：KP/sidecar/链接/目录/图片/撰写/整理/自检 |
| T2 | 内置调度脚本 | `resources/agent-prompts/fsrs.py`（FSRS，纯计算、无网络） | `python fsrs.py --selftest` PASS；`due/grade/init` 三子命令可用；同 `(card,date,grade)` 重复执行结果一致（幂等） |
| T3 | 分发 RPC | `install_kb_agent() -> {written[], skipped[], prompt}` | 写入 `<kb>/.memoria/agent/{README.md,prompt.zh-CN.md,fsrs.py}` 与 `review/` 目录；**幂等**：二次调用 `written=[]`；**永不覆盖** `review/**` |
| T4 | UI 入口 | 「为知识库创建 Trae 智能体」按钮 + 可复制提示词面板（复用 [get_agent_prompt](../../src/memoria/presentation/api/ui.py) 模式） | 点击后文件齐备；面板内容 = `prompt.zh-CN.md`；文案走 i18n（`t()`），中英同补 |
| T5 | 兼容性验证 | 一份验证记录（`scripts/benchmark/maintenance/results/` 或 `artifacts/`） | `validate_kb` errors=0；`audit_kb_integrity` / 构建 / 文件扫描**不受** `.memoria/agent/` 影响；导入/导出行为不变 |
| T6 | 登记 | 索引同步 | `resources/README.md`（`agent-prompts/` 行，双语）与 [docs-management §4.2](docs-management.md) 已登记；to-dolist 登记本阶段项 |

**状态（2026-09-10）**：T1a/T1b/T2/T3/T4/T5 与 T6（登记）**已实现**；自动验证见 §7.4；**真机验收待做**。

### 7.2 接口与约定

- **kit 版本**：写入 `.memoria/agent/.kit.json` → `{ "schema_version": 1, "agent_kit": "<semver>", "spec": "<semver>" }`；升级时按版本覆盖 `README/prompt/kb-spec/preview-formats/fsrs.py`，**`review/` 一律保留**。
- **规范独立升级**：`kb-spec.zh-CN.md` 与 `prompt.zh-CN.md` **分别记版本**——规范可单独更新（用户无需重建 Trae 智能体），指令保持稳定。
- **RPC 命名**：`install_kb_agent`（与既有 `get_agent_prompt` 同族）；无 KB 打开时返回 `{status:"error"}`。
- **写盘原子性**：沿用既有 `tmp + os.replace`。
- **降级**：`fsrs.py` 缺失时，指令已定义"只记评分、不改 due"，不得报错中断复习。

### 7.3 非目标（本期不做）
- 不在应用内调用 LLM；不在产品 UI 展示复习到期（Q3 ✅ 已排除）。
- 不改动导入引擎、构建、校验的既有语义。
- 不新建"知识库编撰规则"文档——格式权威仍为 [import-format.md](../conventions/import-format.md) / [markdown-form-std.md](../conventions/markdown-form-std.md)，提示词仅作自包含摘要。

### 7.4 验收与门禁
- **自动**：T2 `--selftest`；`python -m py_compile` / `node --check`（涉及前端时）；T3 幂等断言；T5 兼容性断言。
- **真机**：打开示例库 → 点按钮 → 核对 `.memoria/agent/` 齐备且二次点击不覆盖 `review/`；在 Trae 粘贴提示词后跑通"讲解 / 撰写 / 复习"各一条。
- **A/B 对照**：本项为**新能力**（非"改善"），依 [to-dolist §12](../to-dolist.md) 铁律**不强制** A/B；但 T5 须留验证记录。

**已执行（2026-09-10）**

| 项 | 结果 |
|---|---|
| `fsrs.py --selftest` | **PASS (16/16)**：确定性 / 幂等 / 单调性（Hard≤Good≤Easy、Again<Good）/ 结构合法 / 原子写 / due 过滤 |
| 真装（基准语料 200 文件） | 首次 `written=[README.md, prompt.zh-CN.md, kb-spec.zh-CN.md, fsrs.py]`；**二次 `written=[]`（幂等）**；对 `review/progress.json` 写探针后再装，**review 未被覆盖** |
| 无副作用差分 | `.memoria/agent/` 存在与否，`validate_kb` 输出**完全一致**（errors=0 / warnings=622 / files=200） |
| 静态检查 | `py_compile`（kb_agent.py / ui.py / build.py / fsrs.py）、`node --check`（kb-agent.js 等）、`scan_ui_strings.py`（无新增未登记文案）均通过 |
| 待真机 | UI 点击全流程 + Trae 侧跑通"讲解 / 撰写 / 复习"各一条 |

### 7.5 风险与回滚
- **污染知识库**：`.memoria/` 已被扫描器跳过；若发现任何入库/构建副作用 → 立即停手按 T5 上报。
- **升级覆盖用户改过的提示词**：用户可能改过本地 `prompt.zh-CN.md`；覆盖前对比 `.kit.json` 版本，冲突时**先备份再覆盖**并在界面提示。
- **回滚**：删除 `.memoria/agent/` 即可完全还原（不影响 `sidecars/manifest/pending`）。
- **双份自包含文本漂移**：`organize.zh-CN.md`（导入/整理侧）与 `kb-spec.zh-CN.md`（库内维护侧）都各自内联了格式规则；**格式变更时须同时更新两者**（上游权威仍是 [import-format.md](../conventions/import-format.md) / [markdown-form-std.md](../conventions/markdown-form-std.md) / [preview-formats.md](../reference/preview-formats.md)）。三者分工见 kb-spec 头部「与支持格式说明的分工」。

## 8. 用户操作指示（在 Trae 创建智能体）

1. 执行「**文件 → 创建 Trae 智能体**」（**打开知识库时会自动补齐/刷新工具包**，此入口用于手动重建与查看/复制指令）——未打开知识库时会先唤起「打开知识库」目录选择（取消则中止）；确认后生成 `<kb>/.memoria/agent/`（含 `prompt.zh-CN.md`）。
2. **Trae 打开该知识库目录** → 新建自定义智能体（Agent）。
3. 把 `.memoria/agent/prompt.zh-CN.md` 内容粘贴为**指令**；工作目录设为知识库根。
4. 之后直接对话：`讲解 <主题>` / `整理 <材料>` / `开始复习`。
5. 智能体按契约读写 `*.md`、`.memoria/sidecars/**`、`.memoria/agent/review/**`；收尾跑校验。

## 9. 评审项与结论（全部已拍板）

- **Q1 ✅（2026-09-10）FSRS 参数**：**固定采用 FSRS-5 官方默认权重**（写入每库 `progress.json` 的 `params`，可审计可复算）；**不提供**训练/界面调参。
- **Q2 ✅（2026-09-10）卡片审查**：新卡题面**按 KP 批量确认**——一次生成该 KP 的全部候选卡，列清单让用户一次过目后再落盘 `cards.json`（与 Q7「批量授权 + 清单汇总」一致）。
- **Q3 ✅（2026-09-10）到期可见性**：**不进产品 UI**——本期只在 Trae 智能体侧查看"今天该复习什么"；`progress.json` schema 保持稳定，日后若要接入产品无需改动契约。
- **Q4 ✅（2026-09-10）复习日志**：保持 **append-only 数组** `log`（`ts/card_id/grade/review_date/elapsed_days/scheduled_days/next_due`）；不改为事件溯源。
- **Q5 ✅（2026-09-10）多库/多语言**：**一个 Trae 工作区 = 一个知识库**（契约与 `review/` 均在该库 `.memoria/agent/` 下）；多库各自开工作区。语言跟随该库正文语言。
- **Q6 ✅（2026-09-10）撰写来源纪律**：**强制来源标注**——撰写内容须对应用户要点/指定资料；agent 自行补充的一般性内容必须在正文标注 `<!-- ⚠ 来源待核实：… -->`（§4.2A）。
- **Q7 ✅（2026-09-10）新建文件权限**：**批量授权 + 清单汇总**——用户给定范围后 agent 自主创建，不逐文件确认；落盘前出完整写入清单，收尾汇总新建文件（§4.2）。

## 10. 变更记录

| 日期 | 修订 |
|------|------|
| 2026-09-10 | 初版：锁定载体/落点/写入面/FSRS/一KP多卡/四级评分；给出目录布局、三条工作流、数据模型、`fsrs.py` 规格、产品改动清单与用户操作指示 |
| 2026-09-10 | 评审结论：Q3 ✅ 不进产品 UI（schema 稳定预留）；Q1/Q2/Q4/Q5 ⏳ 待定 |
| 2026-09-10 | 新增「撰写」能力（§4.2A）：明确 KP 元数据权威=sidecar（frontmatter 不参与解析）；撰写三纪律（来源可溯/先查重/必挂链）+ 维护细则（KP 建立、跳转与链接、边、文件组织）；新增待评审 Q6（来源纪律）/Q7（新建文件权限） |
| 2026-09-10 | 评审结论：Q6 ✅ 强制来源标注；Q7 ✅ 批量授权 + 清单汇总（新建文件不逐文件确认，落盘前出完整写入清单、收尾汇总） |
| 2026-09-10 | §7 由"改动清单"扩写为**实施指示**：T1–T6 任务分解（含验收标准）、kit 版本与 RPC 命名（`install_kb_agent`）、非目标、自动/真机验收与门禁（新能力不强制 A/B）、风险与回滚；明确**文档份数**：仓库维护 2 份（本 ADR + 内置提示词），知识库侧为产品复制分发；**不新建"编撰规则"文档** |
| 2026-09-10 | 指令/规范**拆两份**（用户拍板）：`kb-agent.zh-CN.md`=①Trae 智能体**指令**（创建时粘贴一次、稳定）；新增 `resources/agent-prompts/kb-spec.zh-CN.md`=②知识库**编撰/维护规范**（agent 按需读、随版本更新）。理由：规范可独立升级而**无需用户重建智能体**。KB 落点 `.memoria/agent/{prompt,kb-spec}.zh-CN.md`；`.kit.json` 分别记 `agent_kit`/`spec` 版本 |
| 2026-09-10 | **落地 T1–T6**：资源 `kb-agent.zh-CN.md` / `kb-spec.zh-CN.md` / `kb-agent-readme.md` / `fsrs.py`；后端 `services/kb_agent.py` + RPC `install_kb_agent`/`get_kb_agent_prompt`；前端「文件 → 创建 Trae 智能体」（`js/kb-agent.js` + 弹窗 + i18n 中英）；打包登记；验证结果见 §7.4（fsrs 16/16、幂等、review 不覆盖、validate 差分一致）。**剩余：真机验收**；Q1/Q2/Q4/Q5 仍 ⏳ |
| 2026-09-10 | 交互修正（用户拍板）：菜单项**不再禁用**——未打开知识库时点击**先唤起「打开知识库」目录选择**（复用 `MemoriaApp.openKb`），取消则中止；打开后继续生成。改动：`index.html` 去掉 `disabled`、`kb-agent.js` 移除 `syncMenuState` 并新增 `closeFileMenu`、`app.js` 门面导出 `openKb`；§8 用户指示同步 |
| 2026-09-10 | 补分发**支持格式说明**（用户指出 KB 内 agent 读不到）：`install_kb_agent` 新增 `REFERENCE_DOCS`，把 `docs/reference/preview-formats.md`（发布态 `resources/docs/`）一并复制为 `.memoria/agent/preview-formats.md`；kb-spec/指令/README 改为指向同目录该文件（渲染写法权威、按需读）。验证：真装 5 文件且仍幂等 |
| 2026-09-10 | **打开知识库自动补写/刷新**（用户拍板）：`initKb`/`openKb` 成功后调用前端 `MemoriaKbAgent.ensure()`（幂等、不阻塞、不弹窗；实际写入时提示 `kbAgent.autoUpdated`）。旧库首次打开补齐、Kit/Spec 升级后再开即刷新。**有意例外于"禁止 silent 写入"**，缓解见 §7.5 |
| 2026-09-10 | **评审项收口（Q1/Q2/Q4/Q5 全部 ✅）**：Q1 固定 FSRS-5 默认权重（不训练/不调参）；Q2 新卡按 KP **批量确认**后落盘；Q4 `log` 保持 append-only 数组；Q5 **一 Trae 工作区 = 一知识库**。同步 §1 适用范围、§4.3、§6、提示词「工作流三」 |
