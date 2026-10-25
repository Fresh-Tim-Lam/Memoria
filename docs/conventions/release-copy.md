# GitHub Release 宣传口径基线（Release Copy Baseline）

> **用途**：定义 Memoria 每次 GitHub Release 的**标题、双语正文、造价段**的固定写法与术语译法，
> 使「对外宣传」可复制、可核对、不随写作者变化。规则本身见
> [version.md「GitHub Release 规范」](./version.md)，本文档补充**为什么**、**模板**、**反例**与**术语表**。
> **目标读者**：项目负责人（人）、`release-manager`（常驻 release Owner）、任何代写 release notes 的 Agent。
> **关联文档**：[version.md](./version.md)（三条硬规则与 §6 发版流程）、
> `scripts/agent/release_preflight.py`（机器检查，缺一条即 exit 1）、
> [operations.md §5.1](../guides/operations.md)（发布资产命名）。
> **状态**：生效中（2026-10-25，人再次强调「亘古不变」；由 release-manager 维护）。
> **单一事实源声明**：规则冲突时以 [version.md](./version.md) 为准；本文档不新增硬规则，
> 只解释、示例与统一译法。若本文与机器检查冲突，以机器检查为准并修本文。

---

## 0. 一句话

> **标题只写 `Memoria vX.Y.Z`；正文英语在前、中文在后、两段都完整；必须带中英双份造价段。**
> 发版前跑机检，**exit 1 不得继续**；发版后再跑一次「实际发出去的东西」审计。

---

## 1. `[发版]` 规则 1：标题严格等于版本号

**唯一允许的标题**（与 tag 严格字符串相等）：

```
Memoria v0.5.0
```

**为什么不能带副标题**（不是审美偏好，是三个具体故障）：

1. **标题是机器键**：`title == "Memoria " + tag` 是唯一可判定式。一旦写成
   `Memoria v0.4.7 —— 收摊`，任何按标题解析版本号/生成下载链接/做升级公告的脚本都失去稳定输入。
2. **版本号必须唯一标识一次发布**：副标题里的亮点会变（改一版文案就变），而版本号不会。
   把亮点写进标题 = 让「发布身份」随文案漂移。
3. **亮点属于正文**：标题是索引，正文才是内容。把亮点放标题不会让人多看一眼，只会让索引失效。

**违规成本有实证**：`v0.4.7` / `v0.4.8` / `v0.5.0` **连续三版**都写了副标题，
而这条规则**早已写在 version.md**——说明「写在文档里靠记住」遵守率是随机数。
现在由 `release_preflight.py` 的 `TITLE-EXACT` 检查拦截（严格相等；`startswith`/包含/宽松正则都算错）。

---

## 2. `[发版]` 规则 2：正文双语，英语在前、中文在后，两段都完整

**结构约束**（顺序不可反，缺一不可）：

```
## English
<英文正文 —— 完整内容，不是中文的摘要>

## Cost (Agent compute)
<英文造价段>

---

## 中文
<中文正文 —— 完整内容，不是英文摘要的翻译占位>

## 造价（Agent 算力）
<中文造价段>
```

**判定口径**（与机器检查一致）：

- 必须找到 `## English` 与 `## 中文` 两个二级标题，且 English 的**行号更小**；
- 两段「语言主内容」（剔除标题行、分隔线、空行、**造价段**后的正文）都必须 **> 200 字符**；
  ≤200 判 stub；
- 代码、文件名、`file:line`、commit sha、命令、配置键在两种语言里**保持原样**，不翻译；
- 中文段不是英文段的逐句翻译腔：允许信息密度不同，但**不能是英文的摘要**；
  反之亦然（英文段也不能只写一句 "See Chinese below"）。

**可直接复制的最小骨架**：

```markdown
# Memoria vX.Y.Z

## English

### Theme

<one paragraph: what changed and why it matters>

### Highlights

- **<feature>** — <what it does, with measured evidence if available>
- **<feature>** — <...>

### Known debts

- <registered limitation, explicitly not closed>

## Cost (Agent compute)

- **Magnitude**: roughly **CNY XXX-XXX** (estimate; not itemised).
- **Accounting basis**: <which versions are merged into this figure, or why it cannot be split>.
- **Cost structure (one line)**: <where the spend actually went>.

---

## 中文

### 主题

<一段话：改了什么、为什么重要>

### 版本亮点

- **<功能>** —— <做什么；有实测数字就写实测数字>
- **<功能>** —— <...>

### 已知债务

- <已登记、不假装关闭的限制>

## 造价（Agent 算力）

- **量级**：约 **XXX–XXX 元人民币**（估算，非逐项计量）。
- **统计口径**：<合并统计了哪几版；为什么不能诚实切分；是否为计量值>。
- **成本结构（一句话）**：<钱主要花在哪>。
```

**为什么强调「每次翻译都一样」**：双语最大的失败不是语法，而是**同一概念每次译法不同**，
导致英文读者与中文读者以为在看两个不同功能。所有固定译法见 §5 术语对照表；
新增概念必须**先补术语表再发版**。

---

## 3. `[发版]` 规则 3：必须带造价段（量级 + 统计口径 + 成本结构）

**硬要求**：

| 要素 | 中文段 | 英文段 |
|---|---|---|
| 标题 | `## 造价（Agent 算力）`（**全角**括号） | `## Cost (Agent compute)`（**半角**括号） |
| 量级 | 元 / 人民币 / CNY / USD / RMB / 花费 任一 | CNY / USD / RMB / 元 / 人民币 / 花费 任一 |
| 统计口径 | 含「统计口径」或「合并统计」 | 建议 "Accounting basis"（机器只硬判中文段，英文段须含量级） |
| 成本结构 | 一句话（建议以「成本结构」开头；缺失仅告警） | "Cost structure (one line)" |

**禁止**：只写「优化了多少」而不写「花了多少」。**造价与收益必须成对出现**。

**合并统计的标准写法**（多版共享一条工作线时，不要假装能切分）：

```
- **统计口径**：vX.Y.Z ~ vX.Y.Z 合并统计。这几版共享同一条连续工作线、
  同一条验收链、同一个团队会话；token 级台账未记录，故按会话轮次与团队规模估算，不是计量值。
```

英文对应：

```
- **Accounting basis**: vX.Y.Z ~ vX.Y.Z counted as one block. These releases share one
  continuous effort, one acceptance chain, and one team session; token-level accounting was
  never recorded, so the figure is estimated from session rounds and team size, not metered.
```

---

## 4. `[发版]` 规则 4：三步机检，一步都不能省

> 权威步骤见 [version.md §6 第 0 步](./version.md)；这里只给可直接复制的命令。

```powershell
# 0a) tag push 之前：远端 tag 必须【不存在】（防覆盖已发布版本）
python scripts/agent/release_preflight.py --tag vX.Y.Z --phase pre `
    --title "Memoria vX.Y.Z" --body-file artifacts/release-body-vX.Y.Z.md

# 0b) tag push 之后、建 Release 之前：标题/双语/造价/版本三查
python scripts/agent/release_preflight.py --tag vX.Y.Z --phase post `
    --title "Memoria vX.Y.Z" --body-file artifacts/release-body-vX.Y.Z.md

# 0c) 建完 Release + 传完资产之后：核对 GitHub 上「实际发出去的」name/body/assets
python scripts/agent/release_preflight.py --tag vX.Y.Z --verify-published
```

- **exit 1 = 不得继续发布**（缺哪条看输出，`FAIL` 项逐条阻断）。
- `SKIP`（离线/网络不可达）**不算通过**，必须在报告里写明并人工确认。
- 0c 不是可选项：它防的是「本地 body 改好了，但 PATCH/GitHub 上还是旧的」这种假绿。
  历史教训：v0.4.7 / v0.4.8 / v0.5.0 三次发布都是「建完没有核对实际 name」。

---

## 5. `[发版]` 常见错误清单（用真实违规做反例）

| # | 错误写法（真实反例） | 错在哪 | 机检怎么拦 |
|---|---|---|---|
| 1 | 标题 `Memoria v0.4.7 —— 收摊` | 标题变成「版本号 + 一段话」；版本身份随文案漂移；解析脚本失去稳定键 | `TITLE-EXACT` FAIL（严格相等） |
| 2 | 标题 `Memoria v0.4.8 —— 修 P1 + 知识图谱调研` | 同上；亮点应在 body | `TITLE-EXACT` FAIL |
| 3 | 标题 `Memoria v0.5.0 —— agent 能力架构（S1–S5…）` | 同上；副标题还会被截断 | `TITLE-EXACT` FAIL |
| 4 | 正文只有中文（旧 v0.4.7 body） | 违反「双语、英语在前」；英文读者无内容 | `BODY-BILINGUAL` FAIL（缺 `## English`） |
| 5 | 英文段只写一句 "See Chinese below" | 英文段是 stub，不是完整内容 | `BODY-BILINGUAL` FAIL（主内容 ≤200） |
| 6 | `## 中文` 放在 `## English` 之前 | 顺序反了，违反固定结构 | `BODY-BILINGUAL` FAIL（行号顺序） |
| 7 | 有 `## 造价` 但无量级（旧 v0.4.8 body） | 只说收益不说成本；「造价」不可核对 | `COST-SECTION` FAIL（无 元/人民币/CNY…） |
| 8 | 造价段只写「省了 77% token」 | 收益 ≠ 造价；必须成对 | `COST-SECTION` FAIL（缺量级/口径） |
| 9 | 写成 `## 造价(Agent 算力)` 半角括号 | 标题不是规范规定的全角括号，机检与目录锚点对不上 | `COST-SECTION` FAIL（标题精确匹配） |
| 10 | 写成 `## Cost（Agent compute）` 全角括号 | 英文标题必须半角括号 | `COST-SECTION` FAIL |
| 11 | 造价只写「约几百元」不写口径 | 无法判断是单版还是合并、是估算还是计量 | `COST-SECTION` FAIL（无统计口径/合并统计） |
| 12 | 资产名 `Memoria-vX.Y.Z-lite.zip`（缺 `win64-` 平台段） | canonical 是 operations.md §5.1 的 `-win64-lite.zip`；v0.3.x–v0.4.6 均正确，**v0.4.7–v0.5.0 三版漂移**。**根因：Lead 在 0.4.7 只看最近自己的命名习惯就照抄，连文档都没人回头对照**（比标题违规更隐蔽：标题违规是「文档写了没遵守」，命名漂移是「连文档都没看」） | `ASSETS-COUNT` WARN（不阻断；已发布资产不改名，新发布必须 canonical） |
| 13 | 只传 1 个 zip / 两个包不同版本 | 用户无法按网络条件选择；版本错配 | `ASSETS-COUNT` FAIL（数量≠2 或不成对） |
| 14 | `__version__.py` = 0.5.1 但 `version.md §1` = 0.5.0 | 版本三查不一致，构建与文档各说各话 | `VERSION-THREE-WAY` FAIL |
| 15 | 本地 body 修好了，但 GitHub 上还是旧 body | 「改对本地 ≠ 改对外」的假绿 | 发布后 `--verify-published` 直接读 GitHub 实际状态 |
| 16 | 双语文案里同一概念两种译法 | 读者以为是两个功能（见 §6 术语表） | 机器不判，**人/审阅者按术语表核对** |

> 第 1–3、4、7 号就是本仓库真实发生过的违规，已被 `run_must_red.py` 用真实 body 做成了必红夹具。

---

## 6. `[发版]` 中英术语对照表（**固定译法，不得每次重译**）

> 本节不是「翻译表」，是**防止同一概念在不同版本被翻成不同英文**的可判定清单：
> 每行给出 **中文 → 固定英文（唯一） → 禁用变体 → 为什么禁**。
> 代码名 / 文件名 / `file:line` / commit sha / 命令**不翻译**；新增对外概念**先在此登记**再写 release notes。
> 审阅者检查法：同一概念在英文段与中文段各 grep 一次；出现禁用变体或第二种译法即返工。

| 中文 | 固定英文（唯一） | 禁用变体（出现即返工） | 为什么禁 |
|---|---|---|---|
| 知识库 | knowledge base（KB） | library / repository / knowledge repo | library 是代码库，repository 是 git 仓库；混用会让读者以为在讲代码 |
| 知识库 Agent | knowledge-base agent | intelligent agent / AI assistant / chatbot | 同一产品面三种叫法 = 读者以为是三个功能 |
| 粒度读（三级：`outline` / `section` / `snippet`） | granular read（three levels: `outline` / `section` / `snippet`） | fine-grained reading / hierarchical read / scoped read | 三种译法都会被读者当成不同机制；且丢掉三级枚举与代码名锚点 |
| 写安全四道闸（W1–W4） | four write-safety gates（W1–W4） | four locks / safety doors / four checkpoints | "locks/doors/checkpoints" 暗示不同机制；W1–W4 才是可核对编号 |
| 读后写守卫（W2） | read-before-write guard | write-after-read check / read-write guard | 顺序说反（read-before-write），读者会理解成相反策略 |
| 写前备份（W3） | pre-write backup | backup-before-save / auto-save backup | "save" 不是本产品原语（写 = write）；口径漂移 |
| 分发前审批（W4） | pre-dispatch approval | confirm dialog / permission popup | 把「审批档位机制」误写成「一个弹窗」 |
| 入口唯一（W1） | single entry point | unified entry / one gate | "unified" 暗示合并而非唯一；签名级 fail-closed 语义丢失 |
| 扩展点 | extension points | plugins / hooks / add-ons | 扩展点是机制总称，插件只是其中一种实现；混用会夸大范围 |
| 能力 / 技能 / 插件 | capability / skill / plugin | ability / feature / extension / addon | **三者不可互译**；这是 0.4.7 已统一的三层术语（能力 ≠ 技能 ≠ 插件） |
| 能力插件 | capability plugin | power plugin / ability extension | 历史 UI 文案固定为「能力插件」，英文侧必须一一对应 |
| trace（追踪） | trace | tracking / log / trajectory | 产品字段/表名就叫 `trace`；tracking 是行为分析、log 是日志、trajectory 是轨迹 |
| `trace_cost_summary` | `trace_cost_summary`（原样） | cost summary / trace summary | 代码名必须原样，否则英文读者搜不到对应实现 |
| 压缩可观测 | compression observability | compaction visibility / compression log | visibility 是「能否看见」，observability 是「可测量/可核对」；语义不同 |
| 造价 | cost（Agent compute） | price / expense / budget / dev cost | 固定标题 `## Cost (Agent compute)`；"dev cost" 只指开发人力，漏掉 Agent 算力口径 |
| 统计口径 | accounting basis | statistics / metrics / scope | 它是「哪些版本合并统计、是估算还是计量」的口径，不是指标 |
| 成本结构 | cost structure | cost breakdown / spending detail | "breakdown" 承诺逐项明细，而实际只给一句话；过度承诺 |
| 门禁 | gate（gates） | checkpoint / guardrail / barrier | checkpoint 是过程快照，不是「不过就拒绝」的放行闸 |
| 必红夹具 | deliberately-broken fixture | negative test / red test / failure case | negative test 是输入非法，不是「把实现改坏验证守卫生效」 |
| 真机验证 | real-machine verification | real device test / manual test / field test | 本语境指在 Windows 真机跑产品，不是移动设备或人工点点 |
| 验收 | acceptance | validation / QA / sign-off | 与项目既有「独立验收 / R1 级验收」体系绑定，换词即对不上台账 |
| 版本三查 | three-way version consistency check | version triple check / version sync | 需明确是 `__version__.py` / `version.md §1` / `Package/VERSION` 三处（+ tag） |
| 发布资产 | release assets | release files / attachments / downloads | GitHub 术语是 assets；downloads 指下载行为而非文件 |
| 完整包 / 轻量包 | win64 full package / lite package | complete/standard package、slim/mini/small package | 资产名固定 `-win64.zip` / `-win64-lite.zip`；slim/mini 与文件名对不上 |
| 回滚 | rollback | revert / undo | revert 是 git 操作，undo 是文档撤销；发布回滚是独立流程 |
| 已知债务 | known debts | tech debt / known issues / TODO | tech debt 只含技术债；known issues 是缺陷清单；本词含产品/流程债 |
| 证据（产物） | evidence（artifact） | proof / log / screenshot | 指可核验的磁盘产物路径；proof 是数学证明、log 只是其中一种 |
| 预览 | preview | render view / preview panel | preview 固定；"render view" 是内部实现，不是用户概念（预览区 = preview pane） |
| 选区 | selection | highlight / range / pick | highlight 是视觉高亮，range 是编辑器内部模型；本产品能力叫 selection |
| 冷启动 | cold start | startup / boot / first launch | 度量的是「首次启动耗时」这一特定口径，换词会和热启动/打开文档混淆 |
| 默认路径逐字节不变 | default path unchanged byte-for-byte | no behavior change / backward compatible | 后者是兼容性承诺（可含行为变化），前者是可核对的字节级声明 |
| 更正声明 | correction notice | update notice / errata / clarification | 它是对已发布事实的追认/纠错，不是普通更新说明 |

**为什么这节必须存在**：双语最大的失败不是语法，而是**同一功能被翻成不同英文**——
中文读者与英文读者会以为是两个功能；而且下一版作者会照抄上一版的错译，形成「翻译漂移」。
（本仓库已实证：资产命名 `-win64-lite.zip` 只因 v0.4.7 照抄最近自己的习惯就漂成 `-lite.zip`，
与本表同类的「照抄最近样本」错误。）

---

## 7. 维护

- 本文件由 `release-manager` 维护；规则变更**必须同步** `release_preflight.py` 的检查与 selftest fixture，
  否则「文档说变了、机器还按旧的拦」= 新的随机数。
- 每次发版后若出现新的违规形态，**先加必红 fixture，再补本文档反例清单**（顺序不能反：
  先让机器能拦，再写给人看）。
- 本文档需登记进 `docs/README.md` 约定文档索引（由 registrar 维护）。
