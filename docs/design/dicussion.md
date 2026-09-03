# Memoria 设计讨论记录

> 本文件记录 Memoria 项目的关键设计决策和讨论结论。

---

## 技术选型 ✅

- **框架**: Tauri（Rust + Web 前端）
- **理由**: 
  - 需要独立桌面程序而非浏览器页面
  - Markdown + LaTeX 数学公式 + D3.js 图谱在前端生态有成熟方案
  - Qt 渲染数学公式和图谱需内嵌 WebEngine，绕弯路
  - Tauri 打包体积小（~5-10MB），性能好
  - Rust 后端可处理文件扫描、SQLite、向量检索等重活
- **记录日期**: 2026-06-28

## 项目定位 ✅

- **IDE只是内容生产端**：用户在 Trae/VSCode 中编写 Markdown 文件
- **Memoria是独立的知识库浏览器**：负责渲染、跳转、检索、图谱展示
- **存储与展示彻底分离**：`.md` 文件是唯一真相来源，程序只是阅读器

## 核心交互机制 ✅

- **引用语法**: `[[知识点id]]` 在 Markdown 中标记知识链接
- **点击行为**: 点击 `[[id]]` → 在标签栏新增标签页，切换主视图渲染目标知识点
  - 不覆盖原视图，原标签保留可随时切回
- **锚点定位**: 点击 `[[id]]` 可附带锚点，定位到文件内的具体章节或公式位置
  - 三个定位层级：
    - P0 文件级：打开目标文件
    - P1 标题级：打开文件并滚动到指定章节标题位置
    - P2 公式级：打开文件并定位到具体公式/代码块，支持高亮
  - 语法示例：`[[adam#update-rule]]` 定位到 adam 知识点下的 update-rule 锚点

## 多值索引：一个文件可含多个知识点 ✅

- **核心设计**：打破"1个文件 = 1个知识点"的假设，一个 `.md` 文件可注册多个 id
- **声明方式**：在 Frontmatter 中使用 `provides` 字段声明本文件提供的所有知识点
- **P0 文件级定位**：点击 id 打开文件
- **P1 标题级定位**：声明 `anchor` 字段，指定章节标题，编译器验证其存在性
- **P2 公式/代码级定位**：在正文中使用内联锚点标记 `[:anchor:xxx]`，渲染器插入 HTML 锚点元素
- **LLM 精炼辅助（P2 阶段）**：调用本地小模型自动从长文中提取知识点结构，建议 `provides` 列表

### 锚点语法设计（P2）

```markdown
在正文中插入锚点：

Adam 优化器由 Kingma 等人于 2014 年提出。[:anchor:adam-intro]
它结合了动量和自适应学习率...

更新规则如下：

$$w_{t+1} = w_t - \frac{\eta}{\sqrt{\hat{v}_t} + \epsilon}$$ [:anchor:adam-update-rule]
```

点击 `[[adam#adam-update-rule]]` 定位到该公式，并自动高亮。

## 搜索策略（MVP阶段）✅

- 第一层：精确匹配 id / 标题 / 别名
- 第二层：模糊匹配（SQLite FTS5）
- 第三层：编辑距离容错（拼写错误修正）
- 暂不依赖大模型

## 编译器架构 ✅

### 四张表

1. **nodes**（知识节点表）
2. **anchors**（锚点表——锚点 id → 文件路径 + 行号/字符偏移）
3. **relations**（关系表——强/弱关联边）
4. **citations**（引用表——正文中提及的其他知识点）

### 编译器工作流

1. 扫描 `data/nodes/` 下所有 `.md` 文件
2. 解析 Frontmatter（结构化元数据）和正文
3. 提取 `provides` 列表，注册多 id
4. 提取内联锚点 `[:anchor:xxx]`，构建锚点索引
5. 提取 `[[id]]` 引用，验证完整性（id + 锚点双重验证）
6. 检测循环依赖
7. 构建索引（id→路径、别名→id、锚点→位置、全文索引、图谱数据）

## Frontmatter Schema（初步定稿）✅

```yaml
---
id: "paper-name"                    # 文件的主 id（手动指定，简短英文）
alias: ["别名A", "别名B"]           # 可选的别名列表
title: "论文标题/知识点标题"         # 显示用标题，支持中文
provides:                           # 本文件提供的所有知识点（多值索引）
  - id: "sgd"
    title: "随机梯度下降"
    anchor: "## SGD"                # 标题级锚点（P1）
  - id: "adam"
    title: "Adam优化器"
    anchor: "## Adam"
prerequisite:                       # 强关联：前置依赖
  - "attention-mechanism"
  - "gradient-descent"
extend:                             # 强关联：后续延伸
  - "bert"
  - "gpt"
analogy:                            # 弱关联：方法论类比
  - "database-index"
tags: [深度学习, NLP, 数学]
created: 2026-06-28
updated: 2026-06-28
---
```

### 字段说明

| 字段 | 必需 | 说明 |
|------|------|------|
| `id` | 是 | 文件主 id，手动指定，全局唯一。引用语法 `[[id]]` |
| `alias` | 否 | 别名列表，搜索时匹配 |
| `title` | 是 | 显示用标题，支持中文 |
| `provides` | 否 | 多值索引声明。一个文件可提供多个知识点 |
| `prerequisite` | 否 | 强关联前置依赖。构成有向边，参与循环检测 |
| `extend` | 否 | 强关联后续延伸。构成有向边 |
| `analogy` | 否 | 弱关联方法论类比。构成无向虚线边 |
| `tags` | 否 | 分类标签 |
| `created/updated` | 推荐 | 时间戳，用于复习优先级排序 |

### id 生成策略

1. 优先读取 Frontmatter 中的 `id` 字段
2. 若无，回退使用文件名（不含扩展名，字母数字小写）
3. 若文件名也为中文，则编译时报错，要求手动指定 id
4. `provides` 中的子 id 仅在该文件范围内唯一即可

## 程序定位（场景驱动）

> 以下通过场景描述来定义 Memoria 是什么、为谁服务、具体做什么、不做什么。

### 用户画像

| 属性 | 值 |
|------|-----|
| 身份 | AI/ML 领域的研究者、学者、资深学习者 |
| 编程能力 | 会 Python，懂命令行，会用 IDE（Trae/VSCode） |
| 核心痛点 | 知识点之间关联复杂，学完易忘，回顾成本高 |
| 使用习惯 | 用 Markdown 写笔记和论文精炼，习惯用 IDE 编辑文本 |
| 不需要的 | 笔记软件的花哨排版、协作分享、移动端同步 |

### 场景 1：日常学习阅读（核心场景）

**触发条件**：用户打开 Memoria，开始复习或深入阅读某个知识点。

**用户操作流**：
```
1. 启动 Memoria → 看到首页（上一次关闭时打开的标签页组，或知识图谱总览）
2. 在搜索框输入 "ddpg" → 结果列表显示匹配的知识点
3. 点击 "ddpg" 结果 → 标签栏新增 "DDPG" 标签，主视图渲染 ddpg.md 内容
4. 阅读中看到 [[policy-gradient]] → 鼠标点击 → 标签栏新增 "Policy Gradient" 标签，跳转过去
5. 阅读 Policy Gradient 时想对比 DDPG → 点击标签栏的 "DDPG" 标签 → 切回 DDPG 视图
6. 看到数学公式 ∇J(θ) ≈ ∇log π(a|s)Q(s,a) → KaTeX 渲染为正规数学公式
7. 文中提到 "详细推导见 [[pg-theorem#proof-step-3]]" → 点击跳转并定位到第三步证明位置
```

**涉及的 Memoria 功能**：
- 搜索（精确匹配 + 模糊匹配）
- Markdown 渲染 + KaTeX 数学公式
- [[id]] 链接跳转 + 锚点定位
- 多标签页管理

**不包含**：
- 在 Memoria 中编辑 Markdown（用户在 IDE 中编辑）
- 拖拽图谱节点来建立关系（关系在 Frontmatter 中声明）

---

### 场景 2：知识库构建（内容导入）

**触发条件**：用户在 Trae 中写完一批新的知识点 `.md` 文件，需要导入 Memoria。

**用户操作流**：
```
1. 用户在 Trae 中创建了 3 个新文件：
   - nodes/深度强化学习概述.md  (id: drl-overview)
   - nodes/策略梯度方法.md      (id: policy-gradient)
   - nodes/DDPG算法详解.md      (id: ddpg)
2. 用户在文件头部写好了 Frontmatter（id、prerequisite、extend 等字段）
3. 回到 Memoria，点击菜单 "重建索引" 或快捷键
4. Memoria 扫描 nodes/ 目录，解析所有 .md 文件
5. 编译器输出报告（终端或弹出面板）：
   ✅ 解析成功 3 个文件
   ✅ 注册 4 个知识点（ddpg 额外 provides: ["ddpg", "actor-critic"]）
   ✅ 验证 [[policy-gradient]] 引用有效
   ❌ 警告: [[monte-carlo]] 引用了不存在的 id
   ✅ 循环依赖检测: 无异常
6. 图谱视图自动刷新，新增节点出现在正确位置
```

**涉及的 Memoria 功能**：
- 文件扫描器（扫描 nodes/ 目录）
- Frontmatter 解析器（YAML→结构化数据）
- 引用完整性验证
- 循环依赖检测
- 索引重建（增量或全量）

**不包含**：
- 自动从 PDF/网页爬取内容（用户自行撰写或复制）
- 版本管理（用 Git 处理）
- 从 Obsidian/Notion 迁移工具

---

### 场景 3：知识探知与联想（高级检索）

**触发条件**：用户面对一个复杂问题，想从知识库中找出所有相关的知识点。

**用户操作流**：
```
1. 用户在搜索框输入 "off-policy"
2. 搜索结果分三块返回：
   ┌─────────────────────────────────────┐
   │ 精确匹配（1 个）                      │
   │ → off-policy-learning  [id匹配]     │
   ├─────────────────────────────────────┤
   │ 模糊匹配（3 个）                      │
   │ → q-learning          [标题含 off-policy]│
   │ → ddpg                [标签含 off-policy]│
   │ → sarsa               [正文含 off-policy]│
   ├─────────────────────────────────────┤
   │ 关联推荐（2 个）                      │
   │ → policy-gradient     [被 ddpg 引用为前置]│
   │ → importance-sampling [同标签: off-policy]│
   └─────────────────────────────────────┘
3. 用户点击 "ddpg" → 打开知识点
4. 点击右侧面板的 "图谱视图" → 看到 ddpg 为中心，辐射出 policy-gradient（前置）、
   td3（延伸）、actor-critic（组件）的关系图
5. 在图谱上点击 policy-gradient 节点 → 跳转到该知识点
```

**涉及的 Memoria 功能**：
- 分层搜索结果展示（精确→模糊→关联）
- 标签筛选
- 力导向知识图谱（D3.js）
- 关系边类型区分（强关联实线、弱关联虚线）

---

### 场景 4：知识库维护与诊断（主动管理）

**触发条件**：运行一段时间后，知识库出现废弃引用、循环依赖、或需要批量更新。

**用户操作流**：
```
1. 用户在课堂上学习了新内容，更新了几篇旧笔记的 Frontmatter
2. 运行 "完整性检查" → 编译器输出：
   ⚠️ 循环依赖检测: 
      ddpg → policy-gradient → ddpg  (一般性循环，建议引入外部基础节点破环)
   ❌ 断裂引用: 
      [[attention]] 被 3 个文件引用，但 attention.md 已不存在
   ℹ️ 孤立节点: 
      auto-encoder (没有被任何节点引用)
3. 用户根据报告修复问题：
   - 删掉对 attention 的引用，改为引用 [[transformer]]
   - 为 auto-encoder 添加 prerequisite/extend 关系
   - 对 ddpg 的循环依赖选择 "暂不处理，已知有环但不影响阅读"
4. 重建索引 → 报告变绿 ✅
```

**涉及的 Memoria 功能**：
- 完整性检查器
- 循环依赖检测（有向图环路分析）
- 断裂引用报告
- 孤立节点报告

**不包含**：
- 自动修复引用（用户决策，程序仅报告）

---

### 场景 5：每日回顾（防遗忘）

**触发条件**：用户每天打开 Memoria 时，希望快速回顾。

**用户操作流**：
```
1. 打开 Memoria → 首页展示 "今日回顾" 面板
2. 面板列出 3-5 个知识点，排序依据：
   - 优先级：前置依赖被其他节点引用最多的（重要性高）
   - 时效性：距离上次阅读时间最长的（容易遗忘）
   - 关联性：与你当前打开标签的 prerequisite 有关的
3. 用户逐个点击回顾，看到不清晰的点击 [[id]] 跳转深入
4. 回顾完成后，关闭面板
```

**涉及的 Memoria 功能**：
- 上次访问时间记录
- 复习优先级排序
- 推荐阅读列表

---

### 功能优先级总览

| 场景 | 优先级 | 复杂度 | 说明 |
|------|--------|--------|------|
| 场景1：日常阅读 | **P0** | 中 | MVP 核心，必须优先打通 |
| 场景2：内容导入 | **P0** | 低 | 编译器是第一块砖 |
| 场景3：搜索检索 | **P0** | 中 | 分层搜索 + 图谱展示 |
| 场景4：维护诊断 | P1 | 中 | 知识库积累一段时间后才需要 |
| 场景5：每日回顾 | P2 | 低 | 基于已有数据做排序 |

### 程序一句话定位

> **Memoria 是一个以 AI 为核心的学术知识库——你提供素材，LLM 帮你提炼知识点、建立连接、维护图谱；你通过桌面窗口阅读、跳转、探索。编译器是确定性的地基，AI 是智能化的上层。**

---

## 技术架构（四层）✅

```
┌──────────────────────────────────────────────────────────────────┐
│  窗口壳 (pywebview)                                                │
│  语言: Python                                                     │
│  职责: 创建原生桌面窗口，管理知识库目录，协调各层通信               │
│  打包: PyInstaller → 单个 Memoria.exe                             │
├──────────────────────────────────────────────────────────────────┤
│  编译器 (C++ CLI)                                                  │
│  语言: C++                                                        │
│  职责: 纯确定性逻辑——扫描 nodes/ → 解析 Frontmatter + [[id]]       │
│       验证引用完整性 → 检测循环依赖 → 输出 build/*.json             │
│  特性: 不调用 AI，不依赖网络，同一份 .md 永远产出同 JSON            │
├──────────────────────────────────────────────────────────────────┤
│  LLM 智能层 (Python)                                                │
│  语言: Python + LLM API (DeepSeek / OpenAI / 本地 Ollama)          │
│  职责: 在知识图谱之上做推理——智能检索、链接建议、知识点提取、              │
│        图谱缺口分析、维护预警                                       │
│  特性: 所有输出是"建议"，用户确认后生效，不自动修改 .md               │
├──────────────────────────────────────────────────────────────────┤
│  阅读器 (WebView 内嵌)                                              │
│  技术: 静态 HTML + JS (我为你写) + marked.js + KaTeX + D3.js      │
│  职责: 标签页阅读 + 图谱可视化 + 搜索面板 + AI 建议面板             │
│  输入: build/index.json + build/content/*.md + LLM 返回结果         │
└──────────────────────────────────────────────────────────────────┘
```

### 核心设计原则

| 原则 | 说明 |
|------|------|
| **编译器是确定的** | C++ 部分不调用 AI，不联网。同一份 .md 永远产出同一份 JSON |
| **LLM 可叠加但不依赖** | AI 功能全部在 Python 层，是插件式的，不依赖 AI 也能完整使用阅读器 |
| **建议不自动执行** | LLM 的输出永远是"建议面板"，用户决定是否采纳 |
| **手动优先，AI 辅助** | 用户可以完全手动写 Frontmatter、写 [[id]] 引用、定义关系。AI 只是让这些操作更便捷、更智能，但永远不取代用户的手动能力 |

---

### 启动流程（用户视角）

```
1. 双击 Memoria.exe
2. 弹出原生桌面窗口
3. 首次使用: 选择"我的知识库"目录
4. 主界面:
   ┌────────────────────────────────────────────────┐
   │  工具栏: [构建] [AI 精炼] [AI 分析] [设置]     │
   ├────────────────────────────────────────────────┤
   │  ┌─────────┐  ┌────────────────────────────┐  │
   │  │ 图谱面板  │  │ 标签页阅读区               │  │
   │  │ (D3.js)  │  │ 渲染 markdown + latex     │  │
   │  └─────────┘  └────────────────────────────┘  │
   │  ┌────────────────────────────────────────┐   │
   │  │ AI 建议面板 (LLM 输出)                  │   │
   │  │ "检测到知识点 sgdm 可能的前置: sgd"     │   │
   │  │ "建议为 transformer 添加 extend: bert" │   │
   │  └────────────────────────────────────────┘   │
   └────────────────────────────────────────────────┘
5. 之后每次打开自动恢复上次标签页
```

---

### Python ←→ JS 桥接（pywebview）

```python
# Python 侧 - app.py
class Api:
    # === 确定性功能（调用 C++ 编译器） ===
    def build_index(self, directory: str) -> dict:
        result = subprocess.run(["memoria", "build", "--dir", directory],
                                capture_output=True, text=True)
        return json.loads(result.stdout)

    def build_embeddings(self, directory: str) -> dict:
        """构建向量索引（调用 Python 智能层）"""
        from memoria.intelligence import embeddings
        return embeddings.build(directory)

    # === 智能功能（本地 Embedding 模型，不依赖 LLM API） ===
    def ai_search(self, query: str) -> list:
        """语义检索：自然语言 → 向量相似度匹配"""
        from memoria.intelligence import search
        return search.semantic_search(query, self.kb_path)

    def ai_suggest_links(self, node_id: str) -> list:
        """链接建议：基于向量相似度推荐关联节点"""
        from memoria.intelligence import linker
        return linker.suggest_links(node_id, self.kb_path)

    def ai_graph_analysis(self) -> dict:
        """图谱分析：纯图算法，找缺口、孤岛、密度"""
        from memoria.intelligence import analyzer
        return analyzer.analyze(self.kb_path)
```

```javascript
// JS 侧
// 构建
const stats = await pywebview.api.build_index(kbPath);

// 构建向量索引
await pywebview.api.build_embeddings(kbPath);

// AI 语义搜索
const results = await pywebview.api.ai_search("有哪些算法是 actor-critic 方法？");

// AI 链接建议
const suggestions = await pywebview.api.ai_suggest_links("td3");

// AI 图谱分析
const analysis = await pywebview.api.ai_graph_analysis();
```

---

### 编译器工作流（C++，确定性）

```
1. 扫描 nodes/ 目录下所有 .md 文件
2. 解析 Frontmatter → 提取 id, title, provides, prerequisite 等
3. 解析正文 → 提取 [[id]] 引用和 [:anchor:xxx] 锚点
4. 验证引用完整性（所有 [[id]] 是否都有对应的文件提供）
5. 检测循环依赖（prerequisite 有向图 DFS）
6. 输出 build/index.json + build/content/{id}.md
```

### 智能层工作流（Python，本地 Embedding + 图算法）

```
核心模型: all-MiniLM-L6-v2 (80MB，本地运行，零网络请求)

构建向量索引 (build_embeddings):
  读取 build/index.json + build/content/*.md
  → 每个节点的 title + 正文前 2000 字 → 编码为 384 维向量
  → 保存 build/embeddings.npy + build/embeddings_index.json

智能检索 (ai_search):
  用户自然语言问题 → 编码为向量
  → 与所有节点向量做余弦相似度
  → 返回 top-5 结果 + 相关度分数

链接建议 (ai_suggest_links):
  指定节点 → 取其向量 → 与其他所有节点计算相似度
  → 排除已有连接 → 返回 top-3 建议 + 推断关系类型

图谱分析 (ai_graph_analysis):
  纯图算法，不需要模型:
  - 领域聚类: 基于连通子图 + 向量聚类
  - 孤岛检测: 找零度节点
  - 缺口检测: 找被引用但未定义的 id
  - 密度统计: 各子图的节点数/边数
```

---

### 智能层技术选型对比

| 维度 | LLM API (DeepSeek/OpenAI) | 本地 Embedding (MiniLM) |
|------|--------------------------|------------------------|
| 成本 | 每请求付费 | **零成本** |
| 速度 | 2-10 秒 | **毫秒级** |
| 离线 | ❌ 需联网 | ✅ 完全离线 |
| 模型大小 | — | **80MB** |
| 部署 | 需 API Key | `pip install sentence-transformers` |
| 适合场景 | 复杂推理、问答 | **语义匹配、检索、建议** |

**结论: Memoria 的核心智能需求（检索、匹配、建议）用 Embedding 即可满足。
LLM API 作为 P2 扩展，用于文档精炼和知识问答。**

---

### 智能层预期使用效果（场景示例）

#### 场景 1：智能搜索

```
知识库中已有: rl-overview, q-learning, ddpg, transformer

用户在搜索框输入:
  "有哪些算法是 actor-critic 方法？"

传统关键词搜索: ❌ 搜不到，没文件包含 "actor-critic" 这个词

Embedding 语义搜索: ✅
  ┌──────────────────────────────────────────────────────────────┐
  │  结果 (按相关度排序):                                        │
  │                                                              │
  │  1. DDPG (score: 0.87)                                       │
  │     正文: "DDPG 是一种用于连续动作空间的 actor-critic 方法"    │
  │     └ 匹配原因: 正文直接包含 actor-critic 相关内容             │
  │                                                              │
  │  2. Q-Learning (score: 0.62)                                 │
  │     正文: "Q-learning 是一种 off-policy 的时序差分控制算法"     │
  │     └ 匹配原因: Q-learning 是 actor-critic 方法的前置基础      │
  │                                                              │
  │  3. 强化学习基础概念 (score: 0.45)                            │
  │     正文: "强化学习是智能体通过与环境交互来学习..."             │
  │     └ 匹配原因: 更宏观的 RL 概念，actor-critic 属于 RL 子类   │
  └──────────────────────────────────────────────────────────────┘
```

#### 场景 2：链接建议

```
用户刚写完 nodes/td3.md（TD3 算法），构建完成后点击"AI 建议链接"

Embedding 分析:
  TD3 正文含: "双Q网络"、"延迟更新"、"基于 DDPG 的改进"
  ↓ 向量相似度比对

  ┌──────────────────────────────────────────────────────────────┐
  │  🤖 建议的关联链接:                                          │
  │                                                              │
  │  prerequisite → DDPG (score: 0.91)                          │
  │    "TD3 明确提到基于 DDPG 改进，强烈建议建立前置关系"          │
  │                                                              │
  │  prerequisite → Q-Learning (score: 0.67)                    │
  │    "与 DDPG 一样，Q-learning 也是 TD3 的理论基础"             │
  │                                                              │
  │  ─────────────────────────────────────                       │
  │  [采纳全部]  [只采纳 DDPG]  [忽略]                           │
  └──────────────────────────────────────────────────────────────┘

  用户点击 [只采纳 DDPG]，Frontmatter 自动更新:
    prerequisite: [policy-gradient, q-learning, ddpg]
```

#### 场景 3：图谱分析

```
用户点击 "AI 分析图谱"

  ┌──────────────────────────────────────────────────────────────┐
  │  🤖 图谱结构分析报告:                                        │
  │                                                              │
  │  📊 领域分布:                                                │
  │    强化学习: 4 个节点（rl, q-learning, ddpg, policy-gradient）│
  │    NLP:      1 个节点（transformer）                         │
  │                                                              │
  │  ⚠️ 检测到 1 个孤立领域:                                     │
  │    transformer 与强化学习集群没有任何连接                     │
  │    但内容上两者都涉及序列决策，建议探索关联                    │
  │                                                              │
  │  💡 建议:                                                     │
  │    可以建立: transformer → extend: [decision-transformer]    │
  │    或在 rl-overview 中提及序列建模与 RL 的关系               │
  └──────────────────────────────────────────────────────────────┘
```

#### 场景 4：新节点自动检测

```
用户写了一篇 D4PG 论文精炼，保存到 nodes/d4pg.md 后构建。

AI 自动检测到新节点，建议:
  ┌──────────────────────────────────────────────────────────────┐
  │  🤖 检测到新知识点 D4PG                                      │
  │                                                              │
  │  根据内容分析，建议自动添加以下链接:                          │
  │  prerequisite → DDPG (score: 0.94) ← 强相关                 │
  │  prerequisite → distributional-rl (score: 0.72)             │
  │  extend → 暂无                                               │
  │                                                              │
  │  你的知识库中还没有 "distributional-rl" 节点                  │
  │  是否自动创建占位文件? [是] [否]                              │
  └──────────────────────────────────────────────────────────────┘
```

---

### LLM 接入方案（渐进式）

```
MVP (阶段1):  本地 Embedding 模型 (all-MiniLM-L6-v2, 80MB)
              ✅ 智能搜索、链接建议、图谱分析
              零网络依赖，零 API 费用，毫秒级响应
              用户手动写 Frontmatter（可选借助 Trae AI）

阶段2 (P2):   集成 LLM API (DeepSeek/OpenAI)
              ✅ 文档精炼（论文→Frontmatter）、知识问答
              用户可选配置 API Key

阶段3 (P3):   可选本地大模型 (Ollama/llama.cpp)
              离线可用但精度较低
```

## 功能板块划分

Memoria 分为两个子系统共 **7 个功能板块**：

### 板块 1：项目管理 (memoria init / memoria build / memoria check)

> 编译器入口，C++ CLI

| 命令 | 功能 | 说明 |
|------|------|------|
| `memoria init` | 初始化项目 | 创建 nodes/、output/、示例 .md 文件 |
| `memoria build` | 构建/重建索引 | 扫描 nodes/，解析，验证，输出 build/ |
| `memoria check` | 完整性检查 | 只做验证，不输出 build/ |
| `memoria --help` | 帮助 | 列出所有命令 |

**依赖**：无第三方库（纯 Python 标准库实现，或仅 pyyaml）

---

### 板块 2：文件扫描器 (Scanner)

> 读取 nodes/ 目录，发现所有 .md 文件

```
输入: nodes/ 目录路径
处理: 递归遍历，过滤 .md 文件
输出: .md 文件路径列表
边界: 忽略以 _ 或 . 开头的文件/目录
```

---

### 板块 3：解析器 (Parser)

> 解析单个 .md 文件，提取结构化信息

#### 子模块 3a：Frontmatter 解析

```
输入: .md 文件原始内容
处理: 提取 --- 之间的 YAML 块
输出: 结构化元数据 (id, title, provides, prerequisite, etc.)
错误: Frontmatter 格式错误 → 报错 + 行号
```

#### 子模块 3b：正文引用提取

```
输入: .md 文件正文（去掉 Frontmatter 后的部分）
处理: 正则提取所有 [[id]] 和 [[id#anchor]] 模式
输出: 引用列表 + 锚点列表
      同时记录每个引用出现的上下文（前后各 20 字符）
```

#### 子模块 3c：锚点标记提取

```
输入: .md 文件正文
处理: 正则提取所有 [:anchor:xxx] 标记
输出: 锚点列表 (id, 所在行号)
```

---

### 板块 4：验证器 (Validator)

> 检查整个知识库的完整性

#### 子模块 4a：引用完整性验证

```
输入: 所有文件解析后的引用列表 + nodes 列表
处理: 检查每个 [[id]] 是否都有对应的节点存在
输出: ℹ️ 有效引用计数 / ❌ 断裂引用列表
```

#### 子模块 4b：循环依赖检测

```
输入: 所有节点的 prerequisite 关系（有向图）
处理: DFS 拓扑排序，检测环
输出: ✅ 无环 或 ⚠️ 环路路径列表
```

#### 子模块 4c：孤立节点检测

```
输入: 所有节点 + 引用关系
处理: 找出没有被任何 [[id]] 引用且没有 prerequisite/extend 的节点
输出: ℹ️ 孤立节点列表
```

---

### 板块 5：构建器 (Builder)

> 汇编所有数据，输出最终产物

```
输入: 解析后的所有节点数据 + 验证结果
处理:
  1. 构建 nodes 表（所有文件的 provides 展开为独立节点）
  2. 构建 relations 表（prerequisite/extend/analogy → 有向/无向边）
  3. 构建 citations 表（所有 [[id]] 出现位置 + 上下文）
  4. 构建 anchors 表（所有 [:anchor:] 的位置映射）
  5. 构建 graph.json（D3.js 专用的简化格式）
  6. 将每个节点的原始正文复制到 build/content/{id}.md
输出: build/ 目录下的 JSON + content 文件
```

---

### 板块 6：阅读器 (Viewer)

> Web 前端，静态 HTML/JS/CSS，我为你写

| 组件 | 职责 | 关键技术 |
|------|------|----------|
| 标签页管理器 | 打开/关闭/切换标签，记录历史 | 纯 JS，~80 行 |
| 内容渲染器 | 加载 .md → Markdown+LaTeX 渲染 | marked.js + KaTeX |
| 链接处理器 | 监听点击 → 解析 data-node-id → 新增标签 | 事件委托 |
| 锚点定位器 | 打开标签后滚动到锚点位置 | scrollIntoView() |
| 搜索面板 | 输入关键词 → 精确/模糊/关联检索 | index.json 本地检索 |
| 图谱面板 | 力导向图 → 点击跳转 | D3.js force layout |

**阅读器不做什么**：
- 不直接读取 .md 文件（只消费 build/ 产物）
- 不做编辑、保存、同步
- 不依赖后端服务（纯静态）

---

### 板块 7：LLM 智能层 (Intelligence)

> Python 层，在确定性图谱之上做推理

#### 子模块 7a：智能检索 (AI Search)

```
触发: 用户在搜索框输入自然语言问题
输入: 问题文本 + build/index.json（节点 + 正文）
处理: LLM 理解意图 → 在知识库中定位相关知识点
      (RAG: 将用户问题 + 相关知识库片段送入 LLM)
输出: 结果列表 + 每项的相关度说明
示例: "什么是 off-policy？" → [ddpg, q-learning, importance-sampling]
```

#### 子模块 7b：链接建议 (Link Suggestion)

```
触发: 用户选中一个节点，点击"AI 建议链接"
输入: 节点正文 + Frontmatter + 当前图谱结构
处理: LLM 分析该节点内容，对比图谱中已有节点
输出: 建议的 prerequisite / extend / analogy 列表
      每条建议附带理由
示例: 选中 ddpg →
      建议 prerequisite: policy-gradient (内容强相关)
      建议 extend: td3 (同领域变体)
      建议 analogy: 无
```

#### 子模块 7c：文档精炼 (Document Refining)

```
触发: 用户拖入或粘贴一篇新文档/论文
输入: 原始文本（Markdown 格式）
处理: LLM 提取知识点结构
输出: 建议的 YAML Frontmatter:
      id, title, provides[], prerequisite[], extend[], tags[]
      用户确认后自动写入文件
```

#### 子模块 7d：图谱分析 (Graph Analysis)

```
触发: 用户点击"AI 分析图谱"
输入: build/graph.json
处理: LLM 分析图结构
输出: 分析报告:
      - 缺口: "你引用了 [[attention]] 但还没有 attention 节点"
      - 孤岛: "以下节点没有与任何节点连接"
      - 密度: "各个领域的节点分布统计"
      - 建议: "可以考虑建立 xxx 连接以连接两个领域"
```

#### 子模块 7e：知识问答 (Q&A on Knowledge Base)

```
触发: 用户在问答面板输入问题
输入: 问题 + 整个知识库内容
处理: LLM 基于知识库内容回答问题，标注引用来源
输出: 回答 + 引用的知识点列表 + 置信度
示例: "DDPG 和 TD3 有什么区别？"
      → LLM 对比两个节点内容，输出差异表
```

---

## 项目目录结构（最终定稿）

### 开发态（源码仓库）

```
memoria/
│
├── app.py                          # [Python] pywebview 入口，python app.py 启动窗口
├── memoria.py                      # [Python] CLI 入口，终端调试编译器
├── requirements.txt                # [Python] pywebview, sentence-transformers, numpy
│
├── memoria/                        # [Python] 编译器 + 智能层
│   ├── __init__.py
│   ├── cli.py                      # 命令路由 (build/check/init)
│   ├── compiler/                   # C++ 编译器包装（subprocess 调用）
│   │   ├── __init__.py
│   │   └── bridge.py              # 调用 C++ 编译器并解析输出
│   └── intelligence/              # 智能层（板块 7）
│       ├── __init__.py
│       ├── embeddings.py          # 构建 + 管理向量索引 (all-MiniLM-L6-v2)
│       ├── search.py              # 7a: 语义检索
│       ├── linker.py              # 7b: 链接建议
│       ├── analyzer.py            # 7d: 图谱分析（纯图算法）
│       └── engine.py              # 统一入口
│
├── src/                            # [C++] 编译器核心
│   ├── main.cpp                    # CLI 入口
│   ├── scanner.cpp / scanner.h     # 文件扫描
│   ├── parser.cpp / parser.h       # Frontmatter + [[id]] 解析
│   ├── validator.cpp / validator.h # 引用验证 + 循环检测
│   └── builder.cpp / builder.h     # 输出 JSON
├── CMakeLists.txt                  # C++ 构建
│
├── viewer/                         # [静态文件] 阅读器（我为你写）
│   ├── index.html                  # 入口页面
│   ├── css/
│   │   └── memoria.css
│   ├── js/
│   │   ├── app.js                  # 主逻辑 + 标签页管理层
│   │   ├── search.js               # 搜索面板（含 AI 搜索入口）
│   │   ├── graph.js                # D3.js 图谱
│   │   └── ai_panel.js             # AI 建议面板
│   └── lib/                        # 第三方 JS 库
│       ├── marked.min.js
│       ├── katex.min.js
│       ├── katex.min.css
│       └── d3.min.js
│
├── examples/                       # 示例知识库（供测试）
│   ├── nodes/
│   │   ├── transformer.md
│   │   └── optimizer-overview.md
│   └── memoria.config.json
│
├── docs/
│   └── design/
│       └── dicussion.md
│
└── .gitignore
```

### 运行态（用户电脑上）

```
Memoria.exe 安装目录/
├── Memoria.exe                     # 打包好的程序
├── _internal/                      # PyInstaller 内部运行库
│   ├── memoria/                    # Python 编译器模块
│   └── viewer/                     # 阅读器静态文件
└── (用户的知识库目录在别处，由用户自己管理)
```

### 用户的知识库目录

```
我的AI知识库/                       # 用户自己创建/选择的目录
├── nodes/                          # [用户管理] .md 知识文件
│   ├── transformer.md
│   ├── optimizer-overview.md
│   └── ...
├── build/                          # [程序生成] 编译器输出
│   ├── index.json
│   ├── graph.json
│   ├── embeddings.npy              # [程序生成] 向量索引（智能层）
│   ├── embeddings_index.json       # [程序生成] 向量→节点映射
│   └── content/
│       ├── transformer.md
│       ├── sgd.md
│       └── adam.md
├── memoria.config.json             # [程序生成] 窗口状态、上次打开时间等
└── last_session.json               # [程序生成] 上次打开的标签页
```

### 关键设计决策

- **程序与数据分离**：.exe 和知识库目录完全独立，重装程序不影响数据
- **开发态 CLI 保留**：`python memoria.py build --dir examples/nodes` 可在终端调试，不依赖窗口
- **viewer/ 被双重使用**：开发时 pywebview 直接加载 viewer/index.html；打包后嵌入 .exe 内部

## MVP 第一版迭代范围

| 板块 | MVP 包含 | MVP 不含 |
|------|----------|----------|
| C++ 编译器 | scanner, parser, validator, builder 全部 | 增量构建、大文件流式解析 |
| CLI | `build`, `check`, `init` 三个命令 | `serve` 实时监控 |
| 窗口壳 | pywebview 基本窗口 + 目录选择 + 构建按钮 | 窗口状态记忆、多窗口 |
| 阅读器 | 标签页、MD+LaTeX渲染、图谱、搜索 | 锚点高亮、主题切换 |
| 智能层 | **Embedding 搜索 + 链接建议 + 图谱分析** | 文档精炼、知识问答（P2） |
| JS 库 | 嵌入本地 lib/ 文件，不依赖 CDN | — |

## 后续扩展路线图

> **2026-07-10 讨论整理**。结构化条目见 `designV0.md` §16；检索/维护细则见 `search-and-maintenance-decisions.md`。
> 标记：`[✅]` 已完成 / `[🔄]` 进行中 / `[⏳]` 已采纳待做 / `[💡]` 方向性，需再规格化

### 总览：怎么排期

| 波段 | 主题 | 与现有里程碑关系 |
|------|------|------------------|
| **壳 & 发布** | PyQt6 桌面壳、打包 | **M5** `[🔄]` 主体已实现，收尾图标/安装体验 |
| **V1 闭环** | Lexical 检索、配置维护 | **M3–M4** 当前主战场 |
| **导入 & 安全** | 根目录标记、HTML/约定格式导入 | M4 后并行 **Should** |
| **智能增强** | 模糊搜索、LLM 建议、公式检索、图谱推理、反馈学习 | **M4+ / V1.1** |
| **体验 & 传播** | 新手引导、语言切换、静态 HTML 导出 | V1 末或 V1.1 |
| **V2 学习产品** | 沿路拼接、IDE 式编辑、遗忘曲线、富媒体 | **V2+**（§5.2 已有雏形） |

**合并/去重**：原列表「换壳到支持 window 窗口的架构」与 **M5** 同义，不再单列。

---

### 逐项讨论摘要

#### 1. M5 桌面壳 `[🔄]`

- **目标**：pywebview → **PyQt6 + Win32 hidden chrome**；任务栏/DWM 行为正确；**复用 m0 前端**（QWebEngine + QWebChannel）。
- **现状**：发布入口 `Package/Memoria.exe`、hidden chrome、边沿缩放/最大化还原、图标与顶栏品牌已落地；开发态仍可用 `MEMORIA_SHELL=pywebview`。
- **剩余**：安装器/更新通道、非 Windows 壳（若有需求再议）、与 M4 并行的回归清单。
- **结论**：不算「未来换壳」，而是 **收尾 M5**；不阻塞 M4 功能交付。

#### 2. 知识库根目录安全标记 `[⏳]`

- **问题**：用户把子目录（如 `examples/knowledge/`）当 KB 根打开 → 侧车/索引路径错乱、体验像「坏了」。
- **方案**：在 KB 根写入 `.memoria/manifest.yaml`（或等价 **sentinel**）；子目录若检测到「上层已有 manifest」则弹窗：**当前不是知识库根** + 一键打开正确根目录。
- **优先级**：**Should**，实现成本低、减少支持成本。
- **非目标**：只读防误删；那是另一类「安全」。

#### 3. HTML 文档导入 `[⬇️ 最低优先级]`

- **用户在想的两种路径**：
  - **A. 直接渲染 HTML**：保留原排版，但与 KP/range/链接/sidecar 模型 **几乎不兼容**（难以挂接现有检索、图谱、跳转）。
  - **B. HTML → Markdown**：可纳入 md 管线，但 **解析/清洗难度高**（表格、公式、内联样式、嵌套 div），丢失信息风险大。
- **拍板（2026-07-10）**：**任务优先级全局最低**；V1 仍以 md 为主；HTML 仅作远期选项，**暂不选定 A/B**，待 md 闭环与 M4 检索稳定后再开专项讨论。
- **若将来做**：无论哪条路径都需 **导入报告 + validate**，且 **不** 阻塞 M4/M5。

#### 4. 智能链接推荐（本地小参数 LLM）`[💡]`

- **定位**：在现有 **规则 + Lexical**（`suggest_tags` / `suggest_description` / 链接 audit）之上的 **提议层**；输出仍须 **用户确认** 才写 sidecar。
- **依赖**：M4 Lexical 闭环；可选本地推理运行时（与 Embedding 插件共用「本地模型」基础设施）。
- **结论**：**M4+ / V1.1**；LLM 辅助而非替代显式配置。

#### 5. 公式级语义检索（LaTeX AST）`[💡]`

- **动机**：纯文本 token 对公式同义（符号写法、等价变形）弱。
- **做法**：range 内 LaTeX → AST/规范化串 → 单独 posting 或向量字段；检索 API 仍返回 **kp_id**。
- **结论**：**V1.1+**；数学/ML 类 KB 的高价值项，工作量大于 Lexical 字段扩展。

#### 6. 遗忘曲线 · 主动复习 `[💡]`

- **产品形态**：基于 KP 访问/自评记录调度复习；通知或「今日待复习」面板。
- **存储**：进度进 `.memoria/`（可 gitignore），不污染 md 正文。
- **结论**：**V2+ 学习产品**；与「浏览器/IDE」主定位并列，不进入 V1 Must。

#### 7. 知识图谱推理（新路径发现）`[💡]` `[⏳ 待专章讨论]`

- **示例**：`<奥巴马, 出生地, 夏威夷>` + `<夏威夷, 属于, 美国>` ⇒ 提议 `<奥巴马, 国籍, 美国>`。
- **用户对边系统的要求（2026-07-10）**：图谱推理对 **边的属性系统** 要求很高；当前仅有 **contain / reference / extend + relevance** 等最基础类型，**不足以支撑可靠推理** → 需 **后期专章** 扩展边属性、关系模板、置信度来源。
- **产品边界** `[✅]`：**建议边不自动写入** sidecar；全部进入「建议边」列表，**由用户逐条采纳或忽略**（与 link/tag 提议同一铁律）。
- **依赖**：M2/M3 边模型定稿 + 边属性专章；算法可从 **有类型约束的传递闭包 / 规则模板** 起步，不必先上 GNN。
- **结论**：**探索项**；在边属性讨论完成前 **不进入实现排期**。

#### 8. 图片与图表（曲线图、柱状图等）`[⏳]`

- **分层**：① 图片资源引用 + 预览（相对路径 / `assets/`）；② Mermaid/图表块渲染；③ 从数据生图（更远）。
- **结论**：**V1 Should 只做 ①+② 基础**；与 md 预览管线同一迭代。

#### 9. 强化模糊搜索 / 智能检索内核 `[⏳]` → 见 §17

- **现状**：当前引擎偏 **静态倒排 + 字段加权**（见 `search-and-maintenance-decisions.md` §8），用户体感 **不够智能**。
- **近期（R09）**：拼音/ typo、query 推荐、分档置信度 — 仍在 Lexical 层增强。
- **目标形态（用户设想，§17）**：**双向生长** — 查询侧扩展语义 + 知识库侧沿图谱/标签「分析生长」，两棵搜索树向中间汇合，按 **路径** 计分输出 KP。
- **结论**：R09 为过渡；**SearchKernel v2（双向 BFS / 汇合打分）** 单独立项规划，与 R16 反馈循环协同。

#### 10. 新手引导 `[⏳]`

- **内容**：首次打开 KB、空文件树、无 KP 时的 **引导流**；示例库（如 `example-boonie/`）一键打开。
- **结论**：**V1 Should**；可与安全标记（正确根目录）串联。

#### 11. 约定文本格式的知识库导入（AI 生成包）`[⏳]`

- **目标**：定义 **Memoria Import Bundle**（md + sidecar + manifest 清单）；AI 或脚本按约定产出 → 应用内 **导入向导 + validate_kb**。
- **结论**：**V1.1**；降低「AI 帮建库」摩擦（HTML 导入 R03 为最低优先级，见 §3）。

#### 12. 全库静态离线 HTML 导出 `[💡]`

- **目标**：导出可双击打开的静态站点，保留跳转/图谱/搜索的 **只读子集**（非完整 IDE）。
- **难点**：体积、MathJax、图谱 JS、相对路径；与「单文件 html 导出」不同。
- **结论**：**V2+ 或 V1.1 可选**；适合分享/归档，非日常编辑路径。

#### 13. 语言切换 `[⏳]`

- **范围**：UI 字符串 i18n（壳 + m0 前端）；**不**自动翻译用户 md 正文。
- **结论**：**V1 Should**（§4.5 设置已预留）；可与新手引导一起做。

#### 14. 知识点沿路提取 · 拼接新文档并导出 `[⏳]`

- **与 V2 关系**：即 `designV0.md` §5.2「智能拼接」的具体化：在图谱/导航栈上选路径 → 按序抽取 KP range → 生成新 md + sidecar 草稿。
- **结论**：**V2 Must 候选**；M1 导航栈与 M2 图谱是前置。

#### 15. 富文本 Markdown 编辑（R15）`[⏳]` `[✅ 方向确认]`

- **用户澄清（2026-07-10）**：不是「隐藏 md 的 WYSIWYG」，而是 **完整使用 Markdown 所支持的能力** 进行编辑，包括：
  - 标题等级、待办 `- [ ]`、**加粗/斜体**、列表、引用、代码块
  - **公式与数学符号**（与现有 MathJax 预览一致）
  - **插入图片**（走 md 语法 + 资源路径）
  - 前端增强：**荧光笔**（高亮标记，需约定语法或 sidecar 注解，不破坏 plain md 互操作）
  - **Undo / Redo** 编辑栈
- **原则**：正文仍 **只穿衣**（`[[…]]`）；KP / link / range 仍走 sidecar；编辑器产出合法 md 源码（可切换源码视图）。
- **结论**：**V2**；当前源码/预览分栏为过渡；R15 对标「IDE 式写作体验」而非「用户不懂 md」。

#### 16. 检索用户反馈循环 · 库内持久化模型 `[✅]` `[⏳ 待实现]`

- **行为**：对搜索点击、显式「有用/无用」学习；调整 **该 KB** 下的权重或小模型；状态存 `.memoria/search_feedback/`（或等价），可重建/可清除。
- **原则**：**本地、离线、可删**；与 Embedding 插件并列，不默认上传。
- **拍板（2026-07-10）**：方案 **可行** `[✅]`；在 Lexical 基线 + SearchKernel v2 路线清晰后实现（R16）。

---

### §17 检索引擎：现状全流程 vs 双向生长目标

#### 17.1 当前实现（M4 Lexical · 静态匹配）

**索引构建**（打开 KB / 侧车变更时，`lexical_index.rebuild`）：

1. 扫描库内全部 `.md` + 侧车 `knowledge_points[]`（**仅已确认 KP**）。
2. 每条 KP 生成一条 **扁平记录**：`kp_id`、`name`、`tags[]`、`kp_description`、文件级 `description`、`body_excerpt`（range 正文摘录）。
3. 对 id / name / tag / description / body 分字段 **分词**（jieba + 标识符切分 + **拼音紧凑串**），写入 **倒排表** `token → [(记录下标, 字段)]`。
4. 缓存到 `.memoria/cache/lexical/index.json`。
5. （可选）Embedding：把 name+tags+description+正文拼成文本 → 本地句向量 → `.memoria/cache/embedding/`。

**一次工具栏搜索**（`search_kernel.search` → UI 下拉）：

```
用户输入 q + 范围(全库|当前文件)
    → 查询分词 + 全串小写 + 查询拼音
    → 倒排表召回候选 KP（无候选则全表扫描打分）
    → 逐条字段加权打分（id 精确 > name 包含 > tag > description > 正文…）
    → 按 score 排序取 Top-N
    → [若开启 semantic/both] 向量相似度合并 (约 0.65·Lexical + 0.35·Semantic)
    → [若开启 body_locate] 另起一线性扫描 md 行（非 KP 结果，分级展示）
    → 返回 kp_id 列表 + sources + 可选正文定位
```

**特点**：**无图谱遍历**、**无查询语义扩张树**、**无多跳路径分**；本质是 **「字段倒排 + 可选向量最近邻」**。

#### 17.2 用户目标：双向 BFS「向中间生长」

```
        [查询侧 front]                    [知识库侧 front]
              q                               全库 KP 子图
              │                                    │
    扩展：拼音纠正、同义、                    扩展：沿 edges 走 reference/extend、
          tag 别名、LLM 改写                         tag 共现、description 相似…
              │                                    │
              ▼                                    ▼
         查询概念树                             分析/激活树
              │                                    │
              └──────────► 汇合层 ◄────────────────┘
                    高度匹配的 KP / tag / 中间概念
                              │
                    按路径证据计分（经过哪些边、tag、字段）
                              │
                         输出排序 kp_id
```

| 维度 | 现状 | 目标 |
|------|------|------|
| 查询理解 | 分词 + 拼音 | **语义扩张**（纠错、同义、推荐 query） |
| KB 侧 | 静态 KP 记录 | **沿图谱/标签主动「生长」候选** |
| 汇合 | 单点字段分 | **双向前沿相遇 + 路径打分** |
| 图谱 | 不参与检索 | **边类型与属性**参与推理与权重（→ 与 R07 边系统专章绑定） |
| 反馈 | 无 | **R16** 调路径权重 / 库内小模型 |

**演进建议**：R09 补齐 Lexical 体验 → **SearchKernel v2** 实现双向汇合（可先做 tag+edge 1-hop，再扩 BFS 深度）→ R16 反馈闭环。

---

### 建议执行顺序（拍板草案）

1. **M4** Lexical + 强化模糊搜索（R09 近期层）  
2. **M5 收尾** + 根目录安全标记（R02）+ 新手引导（R10）  
3. **R18 SearchKernel v1.5**（aux、proposals、多模型、R16）  
4. **SearchKernel v2 规格**（§17 双向生长，R17）+ 边系统专章 + R07  
5. **V2** 沿路拼接（R14）、富文本 md 编辑（R15）、遗忘曲线（R06）  
6. **导入/媒体** 约定包（R11）、图片图表（R08）  
7. **最低优先级** HTML 导入（R03）；探索：公式 AST（R05）、全库静态导出（R12）

---

### 待办索引表（供跟踪）

| ID | 条目 | 阶段 | 状态 |
|----|------|------|------|
| R01 | PyQt6 + Win32 桌面壳（M5） | M5 | `[🔄]` |
| R02 | KB 根目录安全标记 | V1 | `[✅]` |
| R03 | HTML 导入（渲染 vs 转 md 未定） | 最低 | `[⬇️]` |
| R04 | 智能链接推荐（本地 LLM） | M4+ | `[💡]` |
| R05 | 公式级语义检索（LaTeX AST） | V1.1+ | `[💡]` |
| R06 | 遗忘曲线复习提醒 | V2+ | `[💡]` |
| R07 | 图谱推理 · 新边提议（需边属性专章） | 探索 | `[⏳]` |
| R08 | 图片 / 图表渲染 | V1 Should | `[⏳]` |
| R09 | Lexical 强化 + query 推荐（→ v2 过渡） | M4 | `[✅]` |
| R10 | 新手引导 | V1 Should | `[⏳]` |
| R11 | 约定格式 KB 导入包 （平面单文件导入变成整个结构化知识库文件）| V1.1 | `[⏳]` |
| R12 | 全库静态 HTML 导出 | V2+ | `[💡]` |
| R13 | UI 语言切换 | V1 Should | `[⏳]` |
| R14 | 知识点沿路拼接导出 | V2 | `[⏳]` |
| R15 | 富文本 Markdown 编辑（公式/荧光笔/undo） | V2 | `[⏳]` |
| R16 | 检索反馈循环 · 库内模型 | M4+ | `[⏳]` |
| R17 | SearchKernel v2 · 双向生长汇合检索 | M4+ | `[💡]` |
| R18 | SearchKernel v1.5 · aux+多模型+统一建议 | M4+ | `[✅]` |

*原「换壳到 Windows 窗口架构」已并入 R01。*

### 检索量化基准（2026-07-10）

- **痛点**：KP 刻画不完善 → Recall 低、Noise@k 高（无关 KP 进 Top-k）
- **方案**：BEIR **SciFact** → Memoria KB（`gold` / `minimal` / `skeleton` 三档 profile）+ qrels
- **文档**：`docs/design/search-retrieval-benchmark.md`；脚本 `scripts/benchmark/`；CI fixture `tests/fixtures/benchmark_retrieval_tiny/`

### SearchKernel v1.5（2026-07-10）`[⏳]`

- **规格**：[`docs/design/search-kernel-v1.5.md`](search-kernel-v1.5.md)（路线图 **R18**）
- **隐式 aux**：持久化 `search_aux/`；**全系统 proposals** 管理（同 tag 候选/已选/忽略），非独立 AI 面板
- **多模型**：Embed-Recall / Embed-Rerank / MT-Bridge / LLM-aux / LTR 分阶段；跨语言 **中间语言桥（默认 en）**
- **检索**：显式+隐式四通道 RRF → 精排 → R16 反馈 → 置信分档
- **闭环**：aux 同时驱动 search 与 tag/link/merge/query 建议

---




### 待整理条目归档（2026-07-11）

> 从原始记录分类整理，供后续排期。检索引擎核心（P0/P1/P3 + R16/R18）已落地并经 benchmark 验证，下列条目不再涉及检索引擎本身缺陷。

#### 🔴 Bug（需修复）

| ID | 条目 | 模块 | 优先级 |
|----|------|------|--------|
| B01 | 检索栏按文本内容搜索跳转定位，预览位置对应错误 | 检索/预览 | ✅ 已修复 |
| B02 | 知识点嵌套连边错误：a 含 b、b 含 c 时，图谱不应直接 a→c 连边（需传递性处理，仅保留直接父子 contain 边） | 图谱 | ✅ 已修复 |
| B03 | 重命名知识点时被别的报错并阻止配置 | 知识点编辑 | ✅ 已修复 |
| B04 | `$行内公式$` 的 '$' 有时被异常转换成 `$$` 等 | Markdown 渲染 | ✅ 已修复 |
| B05 | 创建完知识点后高亮位置相对于设置的范围行号更小 | 知识点/编辑器 | ✅ 已修复 |
| B06 | 创建链接对选中文本限制异常（如「完整性 （integrity）」无法匹配） | 链接/匹配 | ✅ 已修复 |
| B07 | 切换文件触发奇怪跳转，切换文件不应触发跳转，切换文件竟然不是在上次查看的位置；切换预览和源码未定位到相应查看位置，添加设置项或者开关控制预览源码”位置同步“ | 文件树/导航 | ✅ 已修复 |
| B08 | 程序界面内右键偶尔触发 Qt 默认菜单 | UI/右键菜单 | ✅ 已修复 |

#### 🟡 UI/UX 优化

| ID | 条目 | 模块 |
|----|------|------|
| U01 | 检索结果要排序 | 检索结果展示 | ✅ 已修复 |
| U02 | 编辑链接页面文本匹配每次选择一项匹配都跳转到“瀑布”开头；缺少取消勾选“全选”与否的功能 | 链接编辑 | ✅ 已修复 |
| U03 | 新建知识点应复用编辑知识点界面（统一交互） | 知识点编辑 | ✅ 已修复 |
| U04 | 预览/源码切换应定位到对应位置（非首个位置）；分栏可配置是否自动定位 | 编辑器 |
| U05 | 别名编辑栏回车应等同「加入候选」；候选区缺全选按钮 | 候选/别名 |
| U06 | 左栏知识点列表按起始行排序，存储也按此序便于维护 | 知识点列表 | ✅ 已修复 |
| U07 | 知识点跳转与范围调整跳转区分：跳转后起始行应在显示区顶端 | 跳转/定位 | ✅ 已修复 |
| U08 | 设置内部数值范围过小，需扩大 | 设置 |
| U09 | 右键创建知识点时自动识别并剔除「3.3.4.2」类前缀 | 知识点创建 |
| U10 | 源码/预览中选中文本允许右键复制内容（markdown） | 编辑器 | ✅ 已修复 |
| U11 | 扩大知识图谱缩放范围 | 图谱 | ✅ 已修复 |
| U12 | 知识点配置页加「边」页签，允许管理边、创建 extend 等非链接类型类型边，还可以进入该知识点范围内的链接的配置页面 | 知识点配置 | ✅ 已修复 |

#### 🔵 新功能（待规划）

| ID | 条目 | 阶段 |
|----|------|------|
| F01 | 接入大语言模型 API，结构化处理接口，交互中认为有意义的内容智能导入知识库 | M4+ |
| F02 | 「一键应用推荐配置」：自动应用 KP 名称/id/标签/描述、智能添加链接；效果由 benchmark 衡量（召回/准确/F1） | M4+（依赖 R18 aux） |
| F03 | 增加新的力场范式方便图谱观看 | 图谱 |
| F04 | IDE 放缩功能 | UI |

-----
检索的内容有些内容意外地偏高，即使和搜索无关，检索引擎对负样本的测试基准有建立吗，召回率和精准率，错误率能够完善地测试吗，每一个知识点，除了隐式tag，有没有智能地写隐式描述？

<button id="btn-nav-back" class="m0-nav-btn" title="后退 (Alt+←)">←</button>前进后退的功能和一些新的设计没有对应好，一些跳转没有能够返回；
编辑连接页面选择文本的时候主窗口的正文会跟着跳转，用户编辑完连接该怎么回到原来的位置，请你描述出你的交互方案给我检查



打开要老半天,配置完成等待一会；（任务排队在后台进程继续工作不阻塞前端交互，进度条？锁？）




-----
将来加入导出为pdf的设计
从电脑端开发到andriod端
[[**aaa**]]这种链接的预览错误，**aaa**无法选中创建链接
发现memoria竟然可以点击http链接，后续完善这一点
