
## Memoria 样例知识库设计提示词

```markdown
# 任务

为 Memoria M1 设计一套**全新样例知识库**，主题：**[主题，例如：贝叶斯网络与概率图模型]**。

目标不是写百科全书，而是做一个**能展示 Memoria 能力**、且**侧车校验通过**的小型精品库。

---

# 背景：Memoria 数据模型（必须遵守）

## 1. 最小单元是「知识点（KP）」，不是文件

- 每个 KP 有**全局唯一 id**（slug，如 `bayes-rule`、`d-separation`）
- 一个 `.md` 文件可含多个 KP，每个 KP 在侧车里有独立 **range**（起点行/终点行 + snippet）
- 文件本身没有 id，用文件名标识（如 `bayes-network.md`）

## 2. 两层配置

**Markdown frontmatter**（用户可读、辅助搜索）：
```yaml
---
description: 一句话说明本文件主题
concepts:
  - id: bayes-rule
    name: 贝叶斯公式
    weight: 1.0
    tags: [probability, inference]
  - name: 条件独立          # 无 id = 纯 tag
    weight: 0.5
---
```

**侧车 `.memoria/sidecars/<mirror>.memoria.yaml`**（机器维护）：
```yaml
schema_version: 1
file: bayes-network.md
knowledge_points:
  - id: bayes-rule
    name: 贝叶斯公式
    range:
      start: { snippet: "## 贝叶斯公式", line_hint: 12 }
      end:   { snippet: "后验正比于先验乘以似然。", line_hint: 18 }
links:
  - anchor_text: 马尔可夫毯
    targets: [markov-blanket]
    edge_type: reference
    instances: [{ line: 25, wrapped: true }]
    source_id: bayes-rule
```

规则要点：
- range 的 **start/end snippet 必须能在正文对应行里子串匹配**；终点行必须是**非空行**
- 链接用 `[[显示文字]]` 或 `[[kp-id]]`；sidecar `links[].anchor_text` 与正文匹配文本一致
- `edge_type`: `reference`（引用）或 `extend`（扩展/下游）
- 虚链：`targets: []` 用于演示「待绑定」

## 3. 知识库目录结构

```
my-kb/
  topic-a.md
  topic-b.md
  subdir/topic-c.md          # 侧车镜像：.memoria/sidecars/subdir/topic-c.memoria.yaml
  .memoria/
    sidecars/*.memoria.yaml
    manifest.yaml            # 构建后生成，设计阶段可省略
```

---

# 设计目标（必须覆盖的演示场景）

请在设计说明里逐项标注如何覆盖：

| 能力 | 要求 |
|------|------|
| 多文件多 KP | ≥4 个 md，≥12 个 KP，至少 1 个文件含 ≥3 个 KP |
| 跨文件链接 | ≥5 条跨文件 `[[...]]`，形成可导航的小图谱 |
| 多目标链接 | 至少 1 处 `[[A]]` 绑定 2+ 个 target KP |
| 多跳路径 | 设计 A→B→C 三跳阅读路径（用于导航栈演示） |
| 同义/口语 | 至少 1 个 KP 名称与正文用词不完全一致（测搜索） |
| 数学/公式 | 至少 2 处 `$...$` 或 `$$...$$`（测预览与 range） |
| 虚链 | 至少 1 个 frontmatter concept 有 id 但尚未绑定 KP |
| 子目录 | 至少 1 个 md 放在子文件夹 |
| 搜索友好 | 为 KP 配置 tags；正文含可检索关键词与 alias 变体 |
| 边界样例 | 1 个「Nothing 占位」式短文件 + 1 个「hub 概览」式索引页 |

---

# 主题内知识结构（围绕 [主题]）

先输出**概念地图**（再写正文）：

1. **Hub 页**（1 个）：定义领域边界、学习路径、指向各子主题的链接  
2. **核心机制**（2–3 个文件）：每个文件 2–4 个 KP，讲清定义→公式/算法→直觉  
3. **应用/案例**（1 个文件）：把前面 KP 串起来  
4. **对照/易混**（1 个文件或一节）：专门写「A vs B」「常见误解」  

KP 划分原则：
- 一级标题 `##` 通常对应 1 个 KP（除非太短可合并）
- 每个 KP range 覆盖**完整语义段**（含必要公式块），不要截在空行上
- id 用英文 slug；name 用中文（或中英并存于 name）

---

# 链接与图谱设计

1. 画一张简图（mermaid 或 bullet 列表）说明 KP 之间 reference / extend 边  
2. Hub 页至少链出 3 个下游 KP  
3. 叶子 KP 至少 1 条回链或 extend 到相关 KP  
4. 预留 1–2 个「待确认链接」（虚链或 pending 友好表述）

---

# 输出格式（按顺序交付）

## A. 设计摘要（200 字内）
- 主题、受众、与现有 examples（RL/NLP）的差异

## B. 文件清单表
| 文件 | 用途 | KP 数量 | 主要链接出去 |

## C. KP 登记表
| id | name | 文件 | 起点标题 | 终点锚点句（snippet 预览） |

## D. 链接登记表
| anchor_text | source KP | targets | edge_type | 所在行意图 |

## E. 正文草稿
- 每个 md 文件完整内容（含 frontmatter）
- 行号可在侧车阶段再填；但 **snippet 必须来自真实句子**

## F. 侧车 YAML
- 每个文件一份 `.memoria.yaml`
- 确保 `validate_sidecar` 无 error（range 可解析、无重复 id）

## G. 自测清单
- [ ] 每个 KP 的 end 行非空且 snippet 在正文中可找到  
- [ ] 无「文件行号 vs 正文行号」混淆（frontmatter 不计入正文行号）  
- [ ] 搜索词设计：精确名、模糊拼写、口语 alias 各至少 1 例  
- [ ] 打开 Memoria 后：图谱连通、导航栈可回退、搜索能命中 top3  

---

# 约束与风格

- 语言：中文为主，术语保留英文缩写（MDP、BERT 风格）
- 单文件建议 40–120 行正文；整库控制在「10 分钟能读完一遍」
- 不要复制现有 `examples/mdp.md` 结构；必须围绕 **[主题]** 原创
- 避免无意义占位正文；幽默测试文件可 1 个，但不超过总文件数 20%
- snippet 长度 ≤80 字符，选**稳定不会改写的句子**（不要选空行、单独 `$$`）

---

# 可选：若主题定为「贝叶斯网络」时的 KP 种子（可删改）

- `probability-review` / 概率论回顾  
- `bayes-rule` / 贝叶斯公式  
- `conditional-independence` / 条件独立  
- `dag-model` / 有向图模型  
- `d-separation` / d-分离  
- `variable-elimination` / 变量消元  
- `belief-propagation` / 信念传播  
- `bayes-net-hub` / 概率图模型概览（hub）

---

# 开始

请先输出 **A + B + C**（设计摘要、文件清单、KP 登记），等我确认后再写 **E + F** 全文与侧车。
```

---

## 使用建议

1. **先定主题**：把 `[主题]` 换成一个你有把握、且和现有 RL/NLP 样例不重复的领域。  
2. **分两轮生成**：先审 KP 划分和链接表，再写正文，可避免 range snippet 对不上。  
3. **入库位置**：成品可放在 `examples/` 或单独 `examples-<主题>/`，侧车进 `.memoria/sidecars/`。  
4. **验收**：对照 `tests/unit/examples/test_m0_examples.py`——每个 md 有侧车、`validate_kb` 零 error、KP range 全部 `ok`。

如果你已经定了主题（例如「编译原理」「CRISPR」「SQL 索引」），告诉我主题名，我可以按这份提示词直接帮你产出 **A+B+C** 或整套 md + sidecar 草稿。