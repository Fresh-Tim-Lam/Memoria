# AS-SECTION-RANGE 检验报告：md heading / KP range 能否稳定解析为可寻址区间

> **任务**：task-118（裁决 R-R5）。**检验者**：arch-contract（发现该依赖倒挂的评审者）。
> **性质**：对**自家方案地基假设**的证伪检查。判据在执行前锁定，不许事后放宽。
> **状态**：完成，未改 `src/**`，未 commit。
> **HEAD**：`b6e4ee6c`（R-R5 裁决所在）

---

## 0. 结论（三选一，先给答案）

# **`AS-SECTION-RANGE` = 有条件成立**

**条件（可执行，逐条可判红）**：

| # | 条件 | 若不满足的后果 |
|---|---|---|
| **C1** | **解析器必须先剔除围栏代码块与 frontmatter**，再做 heading 匹配 | 现有两个解析器都用 `^` 行首匹配、**不判围栏** ⇒ 实测 **92/3517（2.62%）** 误判（把代码块里的 `# xxx` 当 heading） |
| **C2** | **重复 heading 文本必须靠「父级路径 + 行号」双重锚定**，不得只用文本匹配 | 同级重复占重复样本的 **93.9%** ⇒ 纯文本匹配会**静默取错节** |
| **C3** | **无法唯一定位时必须报错**（`AMBIGUOUS_SECTION`），不得默认取首个 | 默认取首个 = 静默改错地方（写侧数据风险） |
| **C4** | **`#L<行号>` 锚点必须作为一等回退**：每个 section 返回时附带其行区间，调用方可直接按行号二次寻址 | 若只有文本锚，重名/改名后调用方无补救路径 |
| **C5** | 级别范围**必须显式声明**：产品里现有两个正则不一致（`{1,6}` vs `{2,6}`），新接口必须二选一并写死 | 现在 `heading_proposals` 漏掉 h1（实测 h1 有 **279** 个） |

**自评：为什么不是"成立"也不是"不成立"**
- **不是"不成立"**：98.25% 的文档有 heading，91.70% 的文档完全可寻址，heading 结构本身是可靠的（层级分布合理、无 frontmatter 误判、解析 <1ms）。
- **不是"成立"（无条件）**：5.54% 的 heading 会被现有/朴素实现处理错，而**这 5.54% 是结构性的**（围栏 + 重名），不是边角噪声——且**93.9% 的重名是同级的**，闭着眼睛按文本匹配一定出错。

---

## 1. A. 读侧可寻址性

### 1.1 现有解析能力清点（file:line）

| # | 位置 | 正则/能力 | 判围栏？ | 级别范围 |
|---|---|---|---|---|
| **P1** | `src/memoria/services/document.py#L420` | `_HEADING_RE = re.compile(r"^(#{1,6})\s+")` | ❌ **否** | h1–h6 |
| **P2** | `src/memoria/services/heading_proposals.py#L9` | `_HEADING_RE = re.compile(r"^(#{2,6})\s+")` | ❌ **否** | **h2–h6（漏 h1）** |
| **P3** | `src/memoria/services/import_engine.py#L578` | `_find_headings(body)` + `#L590 _match_heading` | 需细查（导入专用） | — |
| **P4** | `plan.py#L152-158` `BODY_EDIT_OPS` | 行号/块索引锚（`replace_lines`/`upsert_block`…），**无 heading 语义** | — | — |
| **P5** | `plan.py#L161` `LINE_ANCHORED_OPS` | 行号锚（`upsert_kp`/`attach_links`/`detach_links`） | — | — |

**关键发现 1：两个 heading 正则不一致** —— `{1,6}` vs `{2,6}`。`heading_proposals` 会**漏掉所有 h1**。实测本语料 h1 有 **279 个**（占 7.9%）。这是**同一仓库里两套 heading 语义**，正是"禁止并行事实源"的反例。

**关键发现 2：两者都不判围栏代码块**。`^` 行首匹配对 ```` ``` ```` 内的行一视同仁。

**关键发现 3：写侧无 section 锚点 op**（我在 task-117 评审 Q-3 已指出）——`BODY_EDIT_OPS` 五项全是行号/块索引，没有 section 语义。

### 1.2 真实语料实测（4 个真实 KB，229 篇，35,039 行，2.59 MB）

**产物**：`artifacts/agent/verify/debate/assumptions/as-section-range-measure.json`
**artifactSha256**：`71fee97861bd4f20ae55a555dbf9bc5a335b812d976cd9d004b0fd4eaed06768`
（覆盖**确定性统计部分**；`timing` 与 `measuredAt` 已剔除，见下方自查记录）

> **⚠️ 自查记录（本测量自身的一次假通过，已修）**
> 初版脚本把 `maxFileMs`（墙钟计时）混进了 `totals` ⇒ **两次跑的 sha 不同**（`0.98ms` vs `1.453ms`），
> 按 E4 这意味着"产物不可复现 ⇒ 结论不可用"。逐键 diff 后确认**只有计时字段抖动，所有统计数字完全一致**。
> 修法：把计时隔离到 `timing` 段并从 sha 计算中剔除 ⇒ 现连续两次 sha 均为 `71fee978…`。
> 记此一笔：**我自己的测量也差点因为"混入非确定性"而成为不可复现的产物** —— 这正是 E4/E5 要抓的东西。
**复跑**：
```bash
node scripts/benchmark/maintenance/as_section_range/heading_addressability.js \
  --kb docs/example/AAA_KnowledgeBase --kb docs/example/人工智能导论知识点汇总 \
  --kb docs/example/行政法 --kb docs/example/AAA_Vocab \
  --out artifacts/agent/verify/debate/assumptions/as-section-range-measure.json
```

#### 总体

| 指标 | 数值 | 占比 |
|---|---|---|
| 文档数 | 229 | — |
| 有 heading 的文档 | **225** | **98.25%** |
| 无 heading（纯文本） | 4 | 1.75% |
| 真 heading 总数（围栏感知口径） | **3517** | — |
| 朴素口径 heading 总数 | 3609 | 比真值多 **92** |
| **完全可寻址文档**（无重名+无围栏误判） | **210** | **91.70%** |

#### 层级分布（围栏感知口径）

| h1 | h2 | h3 | h4 | h5 | h6 |
|---|---|---|---|---|---|
| 279 | **1574** | **1545** | 118 | 1 | 0 |

⇒ 结构以 h2/h3 为主（88.7%），h1 也确有 279 个（打脸 `{2,6}` 那个正则）。

#### 关键风险 1：围栏代码块误判 = **92 / 3517 = 2.62%**

现有朴素实现会把代码块内的 `# 注释` 当成 heading。受影响文档示例：

| 文档 | 误判数 / 围栏块数 |
|---|---|
| `AAA_Vocab/docs/essay_review_format.md` | **21** / 3 |
| `AAA_Vocab/docs/IELTS vocab.md` | **15** / 1 |
| `AAA_KnowledgeBase/Mathemetical_Modeling/1_A/modeling_solutions.md` | 6 / 5 |
| `AAA_KnowledgeBase/MachineLearning/SHAP.md` | 3 / 1 |

⇒ **单篇最多 21 个误判**。若不修，`kb_section(path, "#...")` 会在一篇文档里凭空多出 21 个"节"。

#### 关键风险 2：重复 heading 文本 = **33 组 / 影响 103 heading = 2.93%**

| 文档 | 重复组数 | 样本 |
|---|---|---|
| `AAA_Vocab/ielts-academic-writing-sample-tasks-2023.extracted.md` | **7** | `writing task 1` ×3、`writing task 2` ×2 |
| `AAA_KnowledgeBase/Mathemetical_Modeling/1_A/modeling_solutions.md` | 5 | `1. 问题重述与建模目标` ×4 (全 h3)、`2. 可行技术路径` ×4 (全 h3) |
| `AAA_KnowledgeBase/ReinforcementLearning/BellmanFunc.md` | 2 | `定义` ×3 (全 h3)、`推导` ×2 (全 h3) |
| `AAA_Vocab/docs/ref/ppt/ocr.md` | 2 | `best situation` ×3、`example` ×3 |
| `AAA_KnowledgeBase/Mathemetical_Modeling/FFT-appendix.md` | 2 | `证明` ×2、`一句话记忆` ×2 |

⇒ **10 篇文档有重名 heading**，共 33 组。

#### ★ 关键风险 2b：**93.9% 的重名是「同级重复」**

采样 33 组中：**同级重复 31 组 / 跨级重复 2 组**。

这决定了消歧策略：**同级重复无法靠"层级"消歧**（`### 定义` ×3 都在 h3），**只能靠父级路径或行号**。示例：
```
1_A/modeling_solutions.md
  ## 案例 1
    ### 1. 问题重述与建模目标     ← 第 1 次
  ## 案例 2
    ### 1. 问题重述与建模目标     ← 第 2 次（同文本、同层级，只有父级不同）
```
⇒ 若只用 `heading text` 匹配，`kb_section(path, "1. 问题重述与建模目标")` **必然歧义**。

#### 大文件耗时

| 指标 | 值 |
|---|---|
| 最大文件 | 46,801 B（`AAA_KnowledgeBase/Mathemetical_Modeling/1_A/modeling_solutions.md`） |
| 最大解析耗时 | **0.98 ms**（`DeepLearning/ELU.md`） |

⇒ **性能不是问题**（即使 407KB 级别也远低于 1 个数量级）。任务描述提到的"407 KB 单文件"在本语料里不存在（最大 46KB），如需更大样本可另测——**如实标注：未覆盖 407KB 级样本**。

### 1.3 边界案例

| 边界 | 实测结论 |
|---|---|
| 同名 heading 出现两次 | ✅ 实测存在（33 组），**93.9% 同级** ⇒ 必须父级路径/行号消歧 |
| emoji / 全角 / 尾随空格 | ⚠️ **本轮未专测**（诚实标注）。但归一化（trim + 空白折叠 + 小写）在样本上有效 |
| 无 heading 的纯文本 md | ✅ 存在 4 篇（1.75%）⇒ 必须有降级策略（整篇作为单一 section 或报 `NO_HEADINGS`） |
| frontmatter 里的 `#` | ✅ **0 误判**（现有解析器恰好不受影响，因为 frontmatter 的 `#` 通常不在行首 + `\s+`，但不保证） |
| 大文件耗时 | ✅ 0.98ms 最大，**不是瓶颈** |

---

## 2. B. 写侧可寻址性

| 问题 | 结论 | 依据 |
|---|---|---|
| `replace_section(path, heading, content)` 的风险 | **高：静默改错地方** | 同级重名 + 围栏误判 ⇒ 定位到错节，且改错后**没有任何报错**（因为"找到了"） |
| 现有 `expect` 逐字校验能否用于 section 边界 | **部分可以**：`expect` 能校验"该行内容没变"，但**不能校验"这个 heading 是我要的那个"** | `plan.py` 的 `replace_lines` 有 `expect`；但它是行号锚，section 边界需**额外**的 heading 身份校验 |
| heading 改名后旧 section 锚会不会静默失效 | **会**（若锚是文本） | 文本锚 ⇒ 改名即找不到 ⇒ 若实现"找不到就取首个"则更糟：**改到别的节上** |

**写侧最小安全要求**（必须在实现 `replace_section` 时满足）：
1. 解析必须给出**行号区间**，写操作**以行区间为准**（`replace_lines` 语义），而非"按文本找节再改"；
2. `expect` 要**双锚**：既校验起始行文本，也校验 heading 层级与父级路径；
3. 歧义时必须 `AMBIGUOUS_SECTION` 失败，**绝不默认取首个**。

---

## 3. C. 三选一结论

### `AS-SECTION-RANGE` = **有条件成立**

**C1–C5 五条条件见 §0**。用数据说话：

| 支持"成立" | 支持"不成立/有条件" |
|---|---|
| 98.25% 文档有 heading | 2.62% heading 被围栏误判 |
| 91.70% 文档完全可寻址 | 2.93% heading 重名，其中 **93.9% 同级** |
| 层级分布健康（h2/h3 为主） | 写侧**静默改错**风险（无 second factor） |
| 解析 0.98ms，性能无碍 | 现有**两套不一致正则**（{1,6} vs {2,6}） |
| frontmatter 0 误判 | 4 篇无 heading 需降级 |

⇒ **heading 作为定位手段是可行的，但不能"裸用"**。条件 C1–C5 逐条可判红，且都已给实现落点。

**Falsifiers（什么证据出现则本结论撤回）**：
- 若在更大规模真实语料（>1000 篇）上，完整可寻址文档比例跌破 80% ⇒ 从"有条件成立"降为"不成立"；
- 若实现 C1–C5 后，`AMBIGUOUS_SECTION` 在真实 agent 任务里的触发率 >20% ⇒ 说明文本锚不可用，需改用显式 `{#id}` 锚（本报告的 D.4）；
- 若引入 `{#sec-id}` 后发现用户实际写库时几乎不写锚 ⇒ 说明该方案不适用真实工作流。

---

## 4. D. 最小可行解析契约（因结论为"有条件成立"，给出）

### D.1 匹配算法（归一化后精确匹配）

```
1. 取 body（去掉 frontmatter：首个 --- 到第二个 ---）
2. 逐行扫描，维护围栏状态（``` / ~~~，同字符且长度≥开启者才闭合）
3. 围栏内 / frontmatter 内 ⇒ 跳过（**C1**）
4. 行首匹配 ^(#{1,6})\s+(.+)$  ⇒ (level, rawTitle, lineNo)
5. 归一化 key = normalize(rawTitle)：
     - trim 首尾空白
     - 内部连续空白折叠为单空格
     - 去尾随 # （ATX 闭合：'## 标题 ##' → '标题'）
     - **不做**大小写折叠（中文无意义，英文可能有意区分）—— 但提供 mode: 'ci' 可选
6. 建索引：{normTitle -> [{level, lineNo, parentPath}]}
```

### D.2 消歧规则（按优先级）

```
请求: section(path, title, opts?)
  ① 归一化 title ⇒ 候选集
  ② 若候选 size == 1  ⇒ 命中
  ③ 若 size > 1:
       a) 若调用方给了 opts.path（父级标题链，如 ["案例2"]）⇒ 按 parentPath 过滤
       b) 若调用方给了 opts.lineNo  ⇒ 取该行所在/之前的最近同名
       c) 仍 > 1 ⇒ **失败 AMBIGUOUS_SECTION**（附全部候选的 lineNo + parentPath，供调用方重试）
  ④ 若 size == 0 ⇒ **失败 SECTION_NOT_FOUND**（附最接近的 3 个标题作为建议）
```

### D.3 失败语义（错误码，符合 PROTOCOL E4 可复现）

| 码 | 触发 | 附带信息 |
|---|---|---|
| `SECTION_NOT_FOUND` | 归一化后无匹配 | `suggestions[]`（编辑距离最近 3 个）+ `availableCount` |
| `AMBIGUOUS_SECTION` | 匹配多个且无法按 path/lineNo 消歧 | `candidates[]`（每项 `{lineNo, level, parentPath}`） |
| `NO_HEADINGS` | 该文档 0 heading | `suggestion: "整篇读取，或按行号区间引用"` |
| `INVALID_LEVEL` | 请求的 level 超出文档实际范围（如请求 h5 但文档只有 h1-h3） | `actualLevels[]` |

### D.4 是否需要显式锚 `{#sec-id}`？

**建议：第一阶段不需要，但必须预留。**

| 维度 | 评估 |
|---|---|
| 现有语料是否已有 `{#...}` | **0**（本语料未见，Memoria 也不解析它） |
| 引入代价 | 用户要手动写、渲染器要支持、sidecar 要记 |
| 不引入的补偿 | C2/C3 的「父级路径 + 行号 + 歧义报错」已能覆盖 93.9% 的同级重名场景 |
| 何时需要 | 若 falsifier 触发（歧义率 >20%），或用户开始抱怨"改错节" |

⇒ **第一阶段用「归一化文本 + 父级路径 + 行号」三重锚**；`{#sec-id}` 作为**已登记的演进选项**，不阻塞。

### D.5 级别范围声明（C5）

必须二选一写死（不能像现在这样两套并存）：
- **推荐 `h1–h6`**：与 `document.py` 一致，且实测 h1 有 279 个（漏掉可惜）；`heading_proposals` 的 `{2,6}` 应作为**上一级语义**（"可提议 range 的级别"）单独命名，不要复用同名常量。

---

## 5. 对提案者方案的影响（诚实评估）

| # | 影响 | 严重度 |
|---|---|---|
| 1 | **L1 `kb_section` 可以进第一阶段**，但必须按 D.1–D.3 实现，**不能裸用文本匹配** | 中（增加实现工作量，不阻断） |
| 2 | **必须先修两个现有解析器的不一致**（`{1,6}` vs `{2,6}`），否则新接口会与产品既有行为冲突 | 中（是前置清理） |
| 3 | **写侧 `replace_section` 必须新增 op**（task-117 评审 Q-3 已指出），且必须双锚 + 歧义报错 | 中 |
| 4 | **89% 的 token 收益仍然成立**——因为 91.7% 文档完全可寻址，剩 8.3% 走降级（行号区间）即可 | **低（结论对方案有利）** |

**我没有为了让方案看起来可行而放宽判据**：5.54% 的受影响比例是**实测**的，四条条件是从数据反推的，falsifiers 也写明了降级条件。若有人要求"无条件成立"，那需要先修掉围栏误判与同级重名——那正是 C1/C2。

---

## 6. 方法学说明与局限（如实）

1. **判据先锁定**：本报告的 C1–C5 是从实测数据反推的**事后**条件，但**"三选一"的口径在测量前就定了**（task 描述要求），且 5.54% 这个数字在写报告前已生成（artifact sha 可验）。
2. **未覆盖 407KB 单文件**：语料最大 46KB。task 提到 407KB，本语料不存在该量级文件。**如实标注，不外推**。
3. **未专测 emoji/全角/尾随空格**：样本上归一化有效，但未做专项用例。这是已知盲区。
4. **`import_engine.py` 的 `_find_headings` 未细查**：它属导入路径，与本假设关系较弱，标注为未细查。
5. **语料来源**：4 个 `docs/example/*` 目录，是仓库随附的真实知识库（229 篇），非用户私有库。若用户库写法更不规整，比例可能更差——**falsifier 已覆盖此风险**。

---

## 7. 复现

```bash
cd D:/AAA_Jupyter/Memoria
# 测量（产物 sha 见 §1.2）
node scripts/benchmark/maintenance/as_section_range/heading_addressability.js \
  --kb docs/example/AAA_KnowledgeBase --kb docs/example/人工智能导论知识点汇总 \
  --kb docs/example/行政法 --kb docs/example/AAA_Vocab \
  --out artifacts/agent/verify/debate/assumptions/as-section-range-measure.json
# 统计摘要
node scripts/benchmark/maintenance/as_section_range/report_stats.js
```
