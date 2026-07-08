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

## 后续扩展（待定）⏳

- **M5 桌面壳**：pywebview → **PyQt6 + Win32 hidden chrome**（详见 `designV0.md` §4.6、§14 M5）；融入任务栏/DWM，复用 m0 前端
- 安全标记，知识库根目录的子文件夹内添加标记文件，当用户以该文件作为根目录打开能够提示该目录不是知识库根目录，并且指引打开根目录
- 第二阶段：支持导入 HTML 文档，自动清洗并转换为 Markdown
- 智能链接推荐（可用本地小参数 LLM 辅助）
- 公式级语义检索（LaTeX AST 解析）
- 遗忘曲线主动复习提醒
- 知识图谱推理：应用这个技术辅助找到推理全新的推理路径，示例：从三元组 <奥巴马，出生地，夏威夷> 和 <夏威夷，属于，美国>，可推理得到 <奥巴马，国籍，美国>。
- 支持图片、图表（曲线图、柱状图etc）
- 换壳到支持window窗口的架构
- 强化模糊搜索：“嘛额看f” -> 检索到的有效内容很少-> "马尔可夫"置信度提高，推荐该选项，检索引擎增强
- 新手引导
- 约定文本格式的知识库导入（ai生成知识库，用户导入）
- 整个知识库静态离线导出为html，用户可以直接打开html网页交互同样的页面
- 语言切换
- 知识点沿路提取，拼接新文档并支持导出
- 支持ide编辑，不需要用户懂md和html
- 检索引擎加用户反馈循环增强该知识库的检索，模型持久化存储在该知识库文件