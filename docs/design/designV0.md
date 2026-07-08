# Memoria 设计文档 v0（全新起点）

> **状态**：讨论稿，与旧代码/旧 design.md 脱钩  
> **来源**：仅基于产品愿景，不含历史实现约束  
> **目的**：结构化记录想法，标注待决项，用 MVP 验证后再写技术规格

---

## 1. 产品定位

Memoria 是一个**带本地智能检索内核的知识图谱 IDE**。

用户在一个类似 IDE 的界面里管理个人知识库：左侧导航（文件树 + 知识图谱），中间阅读/编辑文档，底层由离线检索引擎驱动「识别知识点 → 建立跳转 → 图谱导航 → 合并去重」。

**第一版目标**：把「读文档 + 看图谱 + 智能跳转 + 配置维护」做成可用闭环。  
**远期目标**：智能拼接学习路径、完整编辑模式——不在 V1 范围。

---

## 2. 设计原则

| 原则 | 含义 |
|------|------|
| 知识点优先 | 最小控制单元是**知识点**，不是文件 |
| 本地智能 | 检索/推荐必须离线可用，不依赖联网 |
| 正文与配置分离 | 正文只做可识别标记；跳转目标、多选、虚链等完整记录在配置/元数据中 |
| 链接只穿衣 | 链接语法给正文「穿衣服」——插入可识别标记，**不改变原文语义**；渲染时识别，无需预处理改写正文 |
| 人机协作 | AI 负责建议，用户负责确认；所有智能结果可编辑、可撤销 |
| 鲁棒导入 | 用户手动拖入的 md/html 文件，系统应能解析、提示问题、协助纳入知识库 |
| 配置可校验 | 元数据写入前校验、写入后验收；损坏可检测、可修复、不 silent 丢数据 |
| MVP 驱动 | 先做出可验证的小切片，再定数据格式与实现栈 |

---

## 3. 核心概念

### 3.1 知识点（Knowledge Point）

系统中**最小的语义与控制单元**。

| 属性 | 是否必需 | 说明 |
|------|----------|------|
| `id` | 是（正式知识点） | 全局唯一，内链与图谱节点的锚点 |
| `name` | 是 | 展示名；用于文件内定位与高亮 |
| `tags` | 否 | 描述性关键词，辅助检索 |
| `description` | 否 | 较长说明，辅助检索与悬停展示 |
| `range` | 是 | 在所属文件中的覆盖范围（见 §3.4） |

**嵌套**：知识点可包含子知识点（树形结构）。  
**状态**：

- **正式知识点**：有 id，出现在图谱中
- **候选知识点**：系统从正文识别出、尚未分配 id
- **虚跳转**：正文有跳转标记，但尚未绑定任何目标 id

### 3.2 文件（File）

知识点的**容器**，不是组织单元。

| 属性 | 说明 |
|------|------|
| 路径 | 文件在知识库中的标识（V1 暂不设文件级 id） |
| `description` | 可选，整文件摘要，供检索初筛 |
| 格式 | V1：Markdown；可扩展 HTML；是否自定义格式 ⏳ 待定 |

一个文件包含多个知识点；知识点 id 全局唯一，跨文件不重复。

### 3.3 跳转（Link）与边（Edge）分离 `[✅]`

**跳转**和**边**是两套东西：

| | **跳转 Link** | **边 Edge** |
|---|---------------|-------------|
| 回答 | 点这里**去哪**（导航） | 两个 KP **什么关系**（语义） |
| 正文 | 有 `[[]]` 标记 | **无**文本实体（contain 更无） |
| 侧车 | `links[]` | `edges[]` |
| 删 `[[]]` | 删对应 **link** | **不**自动删 edge |

```yaml
links:                            # 正文导航
  - anchor_text: "策略梯度"
    occurrence: 0
    source_id: ddpg               # 含该 anchor 的 KP
    targets: [policy-gradient]    # [] = 虚链

edges:                            # 语义关系（图谱 / 拼接）
  - type: contain
    source_id: rl-overview
    targets: [ddpg]
  - type: reference
    source_id: ddpg               # 引用方 / 依赖方
    targets: [policy-gradient]    # 被引用 / 被参考的 KP
    relevance: 0.85               # 越高越「硬」；V2 主链取高 relevance
  - type: extend
    source_id: ddpg
    targets: [policy-gradient]
    relevance: 0.75
```

**跳转目标不限边类型**：点正文 link 可跳到任意 KP——无论是否已配 reference/extend 边。  
**图谱上沿边导航**（点 reference 线等）同样跳转，高亮规则见 §3.4。

| targets 数量 | 左键行为 |
|--------------|----------|
| `[]` | 虚链 → 搜索绑定 |
| 1 | 直接跳转 |
| 多个 | 多选；队列首项 = 跳转目标 |

**删 `[[]]` = 删 link**，不删 `edges` 里的 reference/extend。

#### link 与 edge「reference」同名不同层

| 层 | 叫什么 | 含义 |
|----|--------|------|
| **links** | 正文链接 | 导航：点文字去哪 |
| **edges.type = reference** | 语义参考边 | 图谱：A 参考/依赖 B；**比原 prerequisite 更宽** |

**reference 边**涵盖：引用、参照、学习依赖、背景知识等；**不再单独设 prerequisite** `[✅]`。

| 语义强度 | 怎么表达 |
|----------|----------|
| 弱参考（提一下） | reference 边 + **低 relevance** |
| 强依赖（必须先学） | reference 边 + **高 relevance** |
| 延伸/进阶 | **extend** 边（与 reference 正交） |

正文 link 仍只是导航；是否在图谱中体现为 reference 边，由用户在配置中另配（或 M4 建议）。

### 3.4 跳转高亮 `[✅]`

**高亮对象永远是「跳转目标 KP」的 range**——与 range 是否交叉无关，**不需要 priority**。

```
任意跳转（正文 link / 图谱节点 / 边导航）
  → 解析 target KP id
  → 打开其文件，滚到 target.range.start
  → 高亮 target.range 全文
  → 淡出
```

交叉区只影响校验与配置预览，**不影响**跳转高亮。

### 3.5 链接标记（正文穿衣）`[✅]`

1. **不改动原文语义**——只外套可解析标记，显示字与用户写的一致  
2. **渲染零预处理**——读标记即渲染  
3. **定位键 = 显示字符串**——`links[]` 用 `anchor_text` + `occurrence`

> 链接语法（如 `[[]]`）已在 M1 验证 `[✅]`。

### 3.6 知识点范围 `[✅]` 显式记录，标题仅作辅助

**已定**：标题可作为**辅助识别规则**（推荐候选区域），但**不能**作为范围的唯一依据。哪些文本区间是正式知识点，必须在元数据中**显式标明并记录 range**。

```
标题扫描 → 生成「候选范围」→ 用户确认 / 配置写入 → 正式知识点
                              ↑
                         唯一真相来源
```

#### 为什么不采用「同级标题法」作为最终方案

| 问题 | 说明 |
|------|------|
| 结构 ≠ 语义 | `#` 层级是排版结构，不等于「一个可跳转的知识单元」 |
| 一改全崩 | 改标题文字、升降级，范围 silently 漂移 |
| 粒度失控 | 一个 `##` 下 3000 字 vs 三个词，系统无法区分 |
| 图谱污染 | 凡有标题就进图谱，用户无法精确控制节点集合 |

#### 范围划分方案（比同级标题法更可控）

以下均可与「标题辅助扫描」组合；**推荐方案 1 为 V1 默认**。

**方案 1：显式双端范围 `[✅]` 推荐**

配置中为每个知识点记录 `{ start, end }`，指向文件内稳定位置。

| 定位方式 | 说明 | 采用 |
|----------|------|------|
| **双端 snippet + line_hint** | 起止各存可识别文本行 + 行号缓存 | **`[✅]` M0 起** |
| 隐藏边界注释 | `<!-- @kp:id:start/end -->` | 极乱文本可选兜底 |

标题辅助：扫描 `#`/`##`/`###` → 为每个标题**提议** `{ start=标题行, end=下一同级标题前一行 }` → 用户确认后才写入配置。

**方案 2：显式起点 + 结束规则**

只记录 `start_anchor` + `end_rule`：

| end_rule | 含义 |
|----------|------|
| `until_next_sibling` | 到下一个同级知识点起点前 |
| `until_parent_close` | 到父知识点范围末 |
| `explicit_end` | 配 explicit end 锚点 |

比纯标题法多一层显式声明；适合层级笔记，但 end 仍部分推导，**不如方案 1 精确**。

**方案 3：UI 选区持久化**

用户在阅读器拖选文字 →「设为知识点」→ 系统写入 range。最精确、零歧义；**适合配置窗口**，可与方案 1 并存（选区结果写入显式 range）。

**方案 4：轻量区域标记（可选扩展）**

正文插入成对标记（渲染时隐藏），如 `<!-- kp:ddpg:start -->` … `<!-- kp:ddpg:end -->`。range 由标记界定，元数据存 id/name/tags。比标题法稳定，但仍比方案 1 更侵入正文——**非 V1 默认，作备选**。

#### 嵌套与包含

父子关系由**显式 range 的几何包含**推导（内层 range ⊂ 外层 range），或由配置显式声明 `parent_id`；不依赖标题层级自动推断为图谱边。

#### range 交叉：现实允许，分级处理 `[✅]`

散乱文本里两个 KP 范围**可能交叉**——不一律报 error，按几何关系分级：

| 关系 | 条件 | 级别 | 行为 |
|------|------|------|------|
| **包含** | A 完全包住 B | 正常 | 自动 `contain` 边 |
| **不相交** | 无重叠 | 正常 | — |
| **部分交叉** | 重叠但不包含 | **警告** | 允许入库；检查面板列出 |
| **等同** | range 完全相同 | 警告 | 提示合并 KP |

交叉不影响跳转高亮（见 §3.4）。可选字段 `priority` **取消**——不需要。

智能导入产生的交叉候选：进 pending，确认时提示即可。

#### 待验证

- M0 即实现 **snippet + line_hint** range（见 §10 Q12）

#### 智能提议 range：检测 ≠ 划界

检索内核识别「这里有个知识点」时，**检测**（是什么）与**划界**（范围到哪）是两步。显式双端是存储格式；智能划界是**提议算法**，结果必须经用户确认才写入元数据。

```
检测候选 → 多策略提议 range（1～3 个）→ 用户确认 / 微调 → 写入显式双端
```

**业界常见方案**（可组合，按场景选用）：

| 策略 | 做法 | 现成参考 | 适合 |
|------|------|----------|------|
| **S1 结构包络** | 候选词落在某标题下 → 提议 `{标题行 … 下一同级标题前}` | LangChain `MarkdownHeaderTextSplitter` | 结构清晰的笔记 |
| **S2  mention 扩展** | 定位首次/定义性出现 → 先取段落，不够再扩到 enclosing 标题段 | RAG 段落 chunker 常见启发式 | 术语散布在段落中 |
| **S3 主题分割** | TextTiling / C99 按词汇衔接切分为干段，选与候选最相关的段 | 经典 NLP（1997 TextTiling） | 少标题、长叙述文 |
| **S4 语义边界** | 逐段 embedding，取与候选名/定义句高相似度的**连续段落块**，边界在相似度骤降处 | LlamaIndex `SemanticSplitter`、semantic-text-splitter | 需本地向量模型 |
| **S5 定义句模式** | 匹配「X 是…」「所谓 X…」「X (English)」等 → 范围 = 该段 ± 后续例证段 | 规则 + 小模型 NER | 教材型定义 |
| **S6 本地 LLM 抽取** | 输入段落索引，输出 start/end 引用句 | 通用但需校验 | 兜底，成本高 |

**Memoria 建议的分层实现**（与 MVP 对齐）：

| 阶段 | 启用的提议策略 | 说明 |
|------|----------------|------|
| M0–M3 | **S1 + S2** | 无 AI 也能跑：标题包络 + 段落扩展 |
| M4 初版 | + **S5** | 定义句规则，提升「检测到术语就有合理默认范围」 |
| M4+ | + **S3 或 S4** | 长文、弱结构时再上；S4 依赖 embedding |

**多策略合并**：各策略产出候选 range + 置信度，配置 UI 展示 top 1～3（可预览高亮），用户一键确认或拖选微调。**禁止静默写入**。

**同一候选多段出现**：默认提议**定义性最强**的一段（标题下 first mention + 定义句模式优先）；其余 occurrence 可建议「同文件引用」或「建链接」而非新建 KP。

**无现成「一键完美」方案**——Obsidian/Notion 等也不自动划 KP 范围；RAG 切 chunk 是近似问题，但目标是检索块而非用户语义单元。Memoria 的差异是：**提议 + 人工确认 + 显式双端持久化**。

### 3.7 边（Edge）

语义关系三类：**contain** / **reference** / **extend**；与正文 **links** 分离（§3.3）。均用 `relevance` 0～1（§9.5）。

### 3.8 检索内核（Search Kernel）

整个系统的智能中枢，**不仅用于搜索**。

| 能力 | 说明 |
|------|------|
| 模糊匹配 | 字面 + 语义相似 |
| 知识点检测 | 正文中识别「可能是知识点」的文本 |
| 跳转建议 | 为虚跳转或新文本推荐目标 id |
| id 分配建议 | 新建知识点时推荐 id |
| tag / description 生成 | 辅助配置，用户确认后写入 |
| 冗余识别与合并 | 发现重复知识点，推荐合并 |
| 作用域 | 当前文件 / 整个知识库 |

**约束**：本地、离线。V1 分层方案见 **§11 Q9**。

---

## 4. 界面与交互

### 4.1 布局

```
┌─────────────────┬──────────────────────────────────────────┐
├     顶栏：文件标签页 + 导航 ← →  ；各种类似ide的入口            │
│───────────────────────────────────────────────────────────┤
│    文件树        │  主区域：文档预览（支持数学公式）           │
│  2D / 3D 图谱   │  - 智能渲染跳转链接                       │
│   （可切换）     │  - 悬停链接 → 图谱次要高亮                 │
├─────────────────┴──────────────────────────────────────────┤
│ 状态栏                                                    │
└──────────────────────────────────────────────────────────┘

独立窗口：配置（知识点、跳转、tag 等）
独立窗口：设置（主题、语言等）；图谱参数 → 图谱区域角落
```

### 4.2 图谱交互

| 操作 | 行为 |
|------|------|
| 悬停节点 | 高亮该节点 + 其出边 + 出边目标节点，并对该节点描述 |
| 点击节点 | 打开所在文件，滚动到知识点范围开头，高亮淡出 |
| 2D/3D 切换 | 同一套节点/边数据，不同渲染；**V1 必须包含 3D** |
| **节点群** | 并查集闭包分量（出边目标均在群内）；侧栏第二行页签：`全部` + 各群；`全部` 为横向瀑布流布局；页签名默认取 Hub 节点（连边最多），可配置；M4 预留 `suggestGroupLabel` |

#### 4.2.0 节点群（Union-Find 闭包）

**定义**：对图谱每条语义边 `(source → target)` 做并查集 `union`；同一连通分量内，任意节点的出边目标均落在该分量内（闭包）。无连边的单节点自成一群。

**UI**（M0 已实现）：

| 元素 | 行为 |
|------|------|
| 页签行 | 位于侧栏 `文件 \| 2D \| 3D` 下方，样式与主编辑区 `#tabs` 一致 |
| `全部` | 第一页签；画布内各群独立局部布局 + 网格偏移（瀑布流）；群间无斥力 |
| 单群页签 | 仅渲染该群节点/边；Hub 命名（id/名称/最大字数在图谱设置中配置） |
| 横向滚动 | 页签过多时，在页签行滚轮横向滚动 |

**API 占位（M4）**：`MemoriaGraphGroups.suggestGroupLabel(group, nodes, links, opts)` → `{ suggested: null, reason: 'search_kernel_not_available', default: hubLabel }`

### 4.2.1 图谱引擎（独立板块）`[✅]`

大量节点场景下，图谱渲染与布局计算必须与 UI、文档预览**解耦**，单独作为「图谱引擎」板块：

```
GraphEngine（核心）
├── 数据层：nodes / edges / **groups**（Union-Find 闭包；与 UI 无关的纯数据）
├── 布局层：`MemoriaGraphLayout2D` / `MemoriaGraphLayout3D`（各自原生维数；参数配置共用，坐标独立）
├── 渲染层：2D Canvas / 3D WebGL（可插拔）
└── 交互层：拾取、悬停、拖拽、相机（输出事件给 Shell）

Shell（IDE 外壳）只订阅 GraphEngine 事件，负责跳转、高亮、文件打开。
```

V1 要求：2D 与 3D **交互语义一致**（悬停/点击/高亮）；布局各自独立（2D 仅 xy，3D 完整 xyz），切换 tab 不强制坐标一致。性能目标在 M2 用大规模 synthetic 图压测后再定指标。

### 4.3 跳转交互

| 操作 | 行为 |
|------|------|
| 左键跳转 | 见 §3.3 多目标规则 |
| 右键跳转 | 编辑目标列表、删除跳转、虚链定向 |
| 导航历史 | 见 §12 Q10：`←` `→` 回溯；KP 跳转入栈；KB 切换清空 |
| 悬停链接 | 图谱次要高亮涉及的知识点节点 |

### 4.4 配置功能

合并「维护知识点元数据」与「维护跳转绑定」的统一入口。

| 区域 | 内容 |
|------|------|
| 左 | 文件树（文件夹可展开） |
| 右 | 文件 description；知识点列表（id / name / tags / description）；跳转列表（文本 ↔ 目标 id）；解析按钮（触发检索内核推荐） |

配置负责**非正文内**的编辑；正文内仍可标记跳转位置。

### 4.5 设置

主题、语言等全局项。图谱力导向参数放在图谱面板角落，不进全局设置。

### 4.6 桌面窗口壳（Shell）`[⏳]`

**现状（M0–M4）**：`pywebview`（Windows 上为 WinForms + WebView2）+ 可选无边框自绘顶栏（`MEMORIA_FRAMELESS`）。业务 UI 仍为静态 HTML/CSS/JS；Python 经 `M0API` 桥接。

**痛点**：纯 `frameless` 去掉系统装饰后，与 Windows 窗口生态（任务栏二次点击最小化、DWM 最大化/还原动画、Snap 布局等）集成弱；手搓 Win32 补丁成本高且难与 VS Code / Electron 同级体验对齐。

**未来方向（M5）**：**换壳为 PyQt6 + Win32「隐藏 chrome」**，而非继续堆 pywebview frameless 补丁。

| 层级 | 策略 |
|------|------|
| **视图** | `QWebEngineView` 加载现有 `m0/` 前端（HTML/CSS/JS **尽量复用**） |
| **桥接** | `QWebChannel`（或等价）替代 `pywebview.api`；`M0API` 逻辑下沉为与 UI 框架无关的 Python 服务层 |
| **窗口** | 保留正常顶层 HWND（`WS_CAPTION` / `WS_THICKFRAME` / 最小化最大化盒）；用 Win32 **`WM_NCCALCSIZE` + `WM_NCHITTEST`** 隐藏可见系统标题栏，客户区自绘 Memoria 顶栏（`.pywebview-drag-region` 等价物改为 Qt 侧声明 drag 区或继续 CSS `-webkit-app-region`） |
| **行为** | 最大化/还原/最小化走 **`ShowWindow` + `WM_GETMINMAXINFO`（工作区）**，融入 DWM；自绘 −□× 调用 Qt/`QWindow` 原生槽，必要时 Win32 兜底 |
| **迁移** | 分阶段：① PyQt6 壳 + API  parity；② Win32 hidden chrome；③ 弃用 pywebview 默认入口；过渡期可用 `MEMORIA_SHELL=pywebview\|pyqt6` |

**非目标（M5）**：重写图谱/预览前端；改为 Electron/Tauri（PyQt6 为当前选型，除非 Benchmark 否决）。

**验收**：任务栏点击切换有系统级动画；Win11 Snap 可用；自绘顶栏视觉与现版一致；现有 pytest + 手工 KB 流程无回归。

---

## 5. 功能范围

### 5.1 V1（第一版）

| 优先级 | 功能 |
|--------|------|
| Must | IDE 式布局；md 预览 + 公式；文件树 |
| Must | **2D + 3D 知识图谱**（缺 3D 则 V1 不成立）；节点跳转 + 高亮 |
| Must | **图谱引擎独立板块**（布局/渲染/交互与 Shell 解耦，支撑大规模节点） |
| Must | 跳转（含虚跳转、多目标、配置编辑；链接标记与跳转记录分离） |
| Must | 配置窗口（知识点显式 range、id/tag、跳转绑定） |
| Must | 检索内核 **Lexical 层**（M4）：模糊匹配、多字段排序、虚链定向 |
| Should | 检索内核 **Embedding 层**（可选插件，可关闭） |
| Must | 手动导入 md 文件的解析与问题提示 |
| Should | **导航历史栈**（§12）；冗余 KP 提示；标题辅助扫描 range |
| Won't | 完整 md 编辑模式；智能路径拼接；自定义文件格式 |

### 5.2 V2+（后续）

1. **智能拼接**：搜索目标知识点 → 自动组装前置链路 → 生成新文件 → 可导出  
2. **完整 IDE 编辑**：预览/源码切换；防格式混乱的安全编辑辅助  
3. **知识点智能拆分/拼接**（维护层面）

### 5.3 基础设施（与功能 MVP 并行）`[⏳]`

| 阶段 | 内容 | 说明 |
|------|------|------|
| **M5** | **PyQt6 + Win32 桌面壳** | 见 §4.6；M4 Lexical 闭环稳定后启动；不阻塞 V1 知识库功能交付 |
| M5+ | 打包 / 安装器 | PyInstaller 或等价；替换现有 `app_m0.py` 启动路径 |

## 6. 数据模型与存储（Q8 讨论）

### 6.1 概念层：存什么

```
KnowledgeBase
├── files[]
│   ├── path
│   ├── description?
│   └── knowledge_points[]      # 本文件内的 KP 声明
│       ├── id, name, tags[], description?
│       └── range { start, end }  # snippet + line_hint；§10
├── links[]                     # 正文导航：anchor_text, targets, source_id
└── edges[]                     # 语义：contain / reference / extend + relevance
└── index/                      # 检索内核构建，可重建
    ├── embeddings?
    └── inverted_index?
```

### 6.2 Q8：元数据存哪？

三类方案对比如下（讨论稿，待拍板）：

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **A. frontmatter** | KP、range、jump、edges 全写 md 头部 | 单文件自包含、拷贝即走 | 污染正文；range 行号频繁变；jump 记录臃肿；违背「正文只穿衣」 |
| **B. 纯侧车** | 正文 md 仅链接标记；`<同名>.memoria.yaml` 存全部元数据 | 正文最干净；导入旧 md 零侵入；diff 分离 | 两文件同步；移动/重命名需联动 |
| **C. 混合** | 正文仅链接标记；侧车存 KP/range/jump/edges；可选 frontmatter 只留 `description` | 兼顾干净与可读摘要 | 需约定哪些字段可进 frontmatter |

**与已定原则的对齐**：

| 原则 | frontmatter | 纯侧车 | 混合 |
|------|-------------|--------|------|
| 链接只穿衣 | ⚠️ jump 易塞进 fm | ✅ | ✅ |
| 显式双端 range | ❌ 行号脏 fm | ✅ | ✅ |
| 鲁棒导入外部 md | ❌ 需改文件才有元数据 | ✅ 首次扫描生成侧车 | ✅ |
| Git 友好 | 单文件 | md 与 meta 分开提交 | 同左 |

**推荐：方案 C（混合，偏侧车）** `[✅]` 已采纳

**术语**：侧车英文 **sidecar (file)**，也写作 **companion metadata file**——与主文件（`rl.md`）并列、存结构化元数据的伴生文件。本项目侧车扩展名：`.memoria.yaml`。

目录约定（草案）：

```
my-knowledge-base/
├── notes/
│   ├── rl.md                    # 用户正文：内容 + 链接标记 only
│   └── rl.memoria.yaml          # 侧车：本文件全部结构化元数据
└── .memoria/                    # 知识库级（可整体 .gitignore 后重建部分）
    ├── manifest.yaml            # kb 根路径、版本、文件清单
    ├── index.json               # 编译产物（图谱/检索），可重建
    ├── pending.yaml             # 待确认候选 KP、待选 tag（工作区状态）
    └── cache/                   # embedding、分词等索引缓存
```

**侧车 `rl.memoria.yaml` 存什么**（单文件真相源）：

侧车顶层字段 = **文件级**；`knowledge_points[]` 内字段 = **知识点级**。

```yaml
schema_version: 1
file: notes/rl.md

# ── 文件级 ─────────────────────────────────────
description: "强化学习笔记摘要"   # 整篇文档摘要，供检索初筛；非某个 KP 的说明

# ── 知识点级 ───────────────────────────────────
knowledge_points:
  - id: q-learning
    name: Q-Learning
    description: "无模型、表格型 RL 算法"   # 可选；单个 KP 的说明，供精排/悬停
    range:
      start: { snippet: "## Q-Learning", line_hint: 42 }
      end:   { snippet: "ε-greedy 小结", line_hint: 87 }
    tags: [rl, tabular]

links:
  - anchor_text: "策略梯度"
    occurrence: 0
    source_id: ddpg
    targets: [policy-gradient]

edges:
  - type: reference
    source_id: ddpg
    targets: [policy-gradient]
    relevance: 0.85
  - type: extend
    source_id: ddpg
    targets: [policy-gradient]
    relevance: 0.75
```

**description 两层分工**：

| 字段 | 层级 | 用途 |
|------|------|------|
| 侧车顶层 `description` | **文件级** | 概括整篇文档；文件级向量初筛 |
| `knowledge_points[].description` | **知识点级** | 单个 KP 说明；精排、图谱悬停、后续拼接 |

若采用 **C2 轻 frontmatter** `[✅]`：仅把**文件级** `description` 镜像进 md 头部供外部预览；**系统以侧车为准**，KP 级 description 不进 frontmatter。

**C2 同步规则**：

| 操作 | 行为 |
|------|------|
| 配置里改 description | 写侧车 → 同步写 frontmatter |
| 仅 frontmatter 有 description（旧导入） | 首次扫描迁入侧车，可选回写 fm |
| 侧车与 fm 冲突 | **侧车优先**；检查功能提示「同步 frontmatter」 |
| 用户手改 fm 的 description | 下次打开检测 mtime → 提示合并或覆盖侧车 |

### 6.3 index.json：编译缓存是什么？

**类比**：md + sidecar = 源代码；`index.json` = 编译产物（类似 `.o` / `dist/`）。

| | 用户手改？ | 删了会怎样？ |
|---|-----------|-------------|
| `rl.md` | ✅ 正文 | 丢内容 |
| `rl.memoria.yaml` | ✅ 配置 | 丢 KP / 边 / range |
| `.memoria/index.json` | ❌ 不改 | 下次打开**自动重建**（扫描 md + sidecar） |
| `.memoria/cache/` | ❌ 不改 | 下次检索**重新算 embedding**（慢一点） |

图谱渲染、全局 KP 列表、边集合——运行时读 `index.json`，避免每次启动全库 parse。  
**真相源只有 md + sidecar**；index 里不存「只在 index 里、sidecar 没有」的用户数据。

`[✅]` **index.json 定为可删可重建的编译缓存**（pending 工作区状态除外，见 §6.4）。

### 6.4 文件 / 文件夹变更的级联更新 `[✅]`

知识库内 rename / move / delete 必须联动 sidecar、manifest、index，避免路径漂移。

**配对约定**：`notes/rl.md` ↔ `notes/rl.memoria.yaml`（同目录、同 stem，扩展名不同）。

| 操作 | 级联行为 |
|------|----------|
| **重命名 md** | 同步重命名 sidecar；更新 sidecar 内 `file:`；更新 manifest；标记 index 过期 |
| **移动 md 到其他文件夹** | 同步移动 sidecar；更新 `file:` 为 new path；更新 manifest |
| **重命名文件夹** | 批量更新该目录下所有 sidecar 的 `file:` 前缀；更新 manifest |
| **删除 md** | 检测 orphan sidecar → 提示「一并删除 / 保留备查」 |
| **删除 sidecar** | md 变为「未配置」→ 扫描时生成空 sidecar 或进入 pending |
| **外部改文件系统**（资源管理器） | 打开知识库时 rescan：manifest 与磁盘 diff → 报 missing/orphan → 引导修复 |
| **仅改 md 内容** | rescan：links 的 anchor_text；KP range snippet 重定位 |

**不随文件移动而变**：知识点 `id`、边的 `targets`（全局 id）——移动文件只改 `file:` 路径。

**manifest 职责**：记录 `{ path, md_mtime, sidecar_mtime }` 清单；rescan 时对比，决定增量 rebuild 还是全量 rebuild。

**pending.yaml**：存未确认候选 KP / 待选 tag；若 sidecar 已删但 pending 仍引用旧 path → rescan 时清理或提示。

### 6.5 Q8 决策记录（完整）

| 子问题 | 状态 | 决策 |
|--------|------|------|
| 主存储 | `[✅]` | **Sidecar** `<stem>.memoria.yaml`，与 md 同目录 |
| description 层级 | `[✅]` | 侧车顶层 = **文件级**；`knowledge_points[].description` = **KP 级**（可选） |
| frontmatter | `[✅]` | **C2**：仅镜像文件级 `description`；侧车为真相源 |
| 侧车格式 | `[✅]` | **YAML** |
| 知识库级目录 | `[✅]` | `.memoria/`：`manifest.yaml` + `index.json` + `pending.yaml` + `cache/` |
| index.json | `[✅]` | **可删可重建**的编译缓存；见 §6.3 |
| 路径级联 | `[✅]` | rename/move/delete 联动 sidecar + manifest；见 §6.4 |
| pending.yaml | `[✅]` | **必需**；存未确认候选 KP / 待选 tag；不可由 index 重建 |

### 6.6 配置完整性保障方案 `[✅]` 原则已定，实现随 M3+

侧车、manifest、pending 属于**高价值用户数据**，index/cache 可重建。保障分五层：

```
┌─────────────────────────────────────────────────────────┐
│ L5 修复入口：检查面板 / 一键修复 / 用户确认               │
├─────────────────────────────────────────────────────────┤
│ L4 启动验收：打开知识库 → 全量校验 → 报告分级             │
├─────────────────────────────────────────────────────────┤
│ L3 交叉引用：id 唯一、target 存在、mark 对齐、range 合法  │
├─────────────────────────────────────────────────────────┤
│ L2 写入安全：schema 校验 + 原子写 + 可选备份              │
├─────────────────────────────────────────────────────────┤
│ L1  schema 版本：schema_version + 迁移器                │
└─────────────────────────────────────────────────────────┘
```

#### L1 Schema 版本与迁移

- 每个 sidecar / manifest / pending 带 `schema_version: 1`
- 启动时：版本低于当前 → 运行**迁移脚本**（可逆迁移优先）；无法迁移 → 阻塞并提示，**不静默改**
- V1 提供 JSON Schema（或等价 YAML schema）描述 sidecar 结构，写入前必过校验

#### L2 写入安全（防半截文件 / 手滑损坏）

| 机制 | 做法 |
|------|------|
| **原子写** | 写 `*.memoria.yaml.tmp` → fsync → rename 覆盖；Windows 用同卷 replace |
| **写入前校验** | 不符合 schema / 引用不存在 → **拒绝保存**，UI 报错 |
| **写入后备份** | 同目录保留 `.memoria.bak`（仅最新一版）或 `.memoria/backups/<timestamp>/`（可配置） |
| **单写者** | 运行时侧车由 Memoria 独占写；检测外部并发改 mtime → 提示「文件已被外部修改，重新加载？」 |

#### L3 交叉引用校验（打开知识库 / 保存时）

| 检查项 | 严重级 | 行为 |
|--------|--------|------|
| KP `id` 全局重复 | 错误 | 阻塞 rebuild；检查面板列出冲突 |
| `links.targets` 指向不存在 id | 错误 | 虚链或引导修复 |
| link 的 `anchor_text` 在 md 中找不到 | 警告 | 删 `[[]]` 即删 link 记录 |
| edges.targets 指向不存在 id | 错误 | 引导修复 |
| KP range 部分交叉 | 警告 | 见 §3.5；不阻塞打开 |
| KP range snippet 无法重定位 | 警告 | 建议 UI 重划或加边界注释 |
| sidecar `file:` 与磁盘路径不一致 | 错误 | 提供「修复 path」 |
| orphan sidecar / orphan md | 警告 | 见 §6.4 |
| frontmatter description ≠ 侧车 | 信息 | C2 同步提示 |

#### L4 启动验收流程

```
打开 KB
  → 读 manifest
  → 扫描磁盘 vs manifest diff
  → 逐文件 parse sidecar（schema）
  → 交叉引用校验
  → 编译 index（或增量）
  → 汇总 issues → 状态栏徽章 + 检查面板
```

- **错误**（errors）：影响正确性，功能受限直到修复或用户显式忽略
- **警告**（warnings）：可继续使用，检查面板可见
- **禁止 silent fix**：自动修复仅能在用户点「应用修复」后执行

#### L5 修复与 pending 特护

**pending.yaml**（用户已确认必需）：

| 规则 | 说明 |
|------|------|
| 不可重建 | 未确认候选状态**只**在 pending；删 index 不能恢复 pending |
| 同等写入安全 | 原子写 + schema + 备份，与 sidecar 同级 |
| 路径引用 | 条目含 `file:` + 稳定 `pending_id`；文件移动时级联改 `file:` |
| 过期清理 | sidecar 已确认写入的候选 → 自动从 pending 移除；删文件 → 提示清理 orphan pending |

**manifest.yaml**：记录 `{ path, md_mtime, sidecar_mtime, sidecar_sha256 }`；sha256 变化但 mtime 未变 → 提示外部编辑。

**index.json / cache/**：校验失败**直接删了重建**；不尝试 repair index。

#### 可选增强（V1 Should，M3+ 实现）

| 增强 | 价值 |
|------|------|
| 知识库级 `integrity check` 命令 | 离线全量体检，CI/打开前可跑 |
| 操作日志 `.memoria/oplog.jsonl` | 配置变更可审计、可回滚（V2） |
| Git 友好 | sidecar YAML 人类可读；建议 `.memoria/cache/` 进 `.gitignore`，sidecar 进版本库 |

---

## 7. 鲁棒性与边界情况

| 场景 | 期望行为 |
|------|----------|
| 用户删除正文中的链接标记 | 对应 **link** 删除（rescan）；**edges 保留** |
| 目标 id 不存在 | 虚跳转或报错，引导重定向 |
| 同一文本多个可能目标 | 多目标跳转 + 用户选择 |
| 外部修改 md 文件 | 重新扫描；校验 link_mark；index 增量/全量 rebuild |
| 重命名/移动/删除文件或文件夹 | 级联 sidecar + manifest；见 §6.4 |
| 重复 id / 重复知识点 | 检测 + 推荐合并 |
| 仅有标题、无元数据的文件 | 标题扫描 → 候选 range 提议 → 引导用户确认写入 |

| 仅有标题、无元数据的文件 | 标题扫描 → 候选 range 提议 → 引导用户确认写入 |
| sidecar / pending 写入失败 | 保留 .tmp / .bak；不覆盖原文件 |
| schema 校验失败 | 拒绝加载该文件配置；检查面板给出字段级错误 |
| 外部手改 sidecar 语法错误 | parse 失败 → 用 .bak 恢复或进入「只读 md」模式 |

---

## 8. Q5：tag 与 description 分工（讨论）

### 8.1 问题重述

| 子问题 | 含义 |
|--------|------|
| tag 是否够用？ | 检索/推荐是否还需其它描述字段 |
| 每层都要 description 吗？ | 文件级、KP 级是否强制长描述 |
| 文件级 description 是否必需？ | 无摘要时检索初筛怎么办 |

### 8.2 字段语义（建议定义）

| 字段 | 层级 | 形态 | 语义 | 检索权重（建议） |
|------|------|------|------|------------------|
| `name` | KP | 短文本 | 知识点叫什么；展示 + 精排主键 | 高 |
| `tags` | KP | 词列表 | 主题/领域关键词；快速过滤 | 中高 |
| `description` | KP | 1～3 句 | 这个 KP **是什么**；悬停 + 语义精排 | 中 |
| `description` | 文件 | 1～3 句 | 这篇文档**讲什么**；文件级初筛 | 中 |

**tag vs description 分工**：

- **tag** = 离散关键词，适合「找同类、过滤、自动推荐」；短、可多个、可枚举
- **description** = 自然语言摘要，适合「语义相似、悬停解释、给人看」；长一点、可选

二者**不互相替代**：tag 搜「RL」；description 搜「连续动作空间的 actor-critic 算法」。

### 8.3 是否每层都要 description？

| 层级 | 建议 | 理由 |
|------|------|------|
| **文件级 description** | **推荐有，非强制** | 无则初筛退化为「所有 KP name/tags 拼接」；大库会变慢 |
| **KP 级 description** | **可选** | 有 id + name + tags 已可检索；description 在悬停/精排时加分 |
| **KP 级 tags** | **推荐有，非强制** | 零 tag 时检索仍可用 name；但推荐/分组质量下降 |

**结论倾向**：不是每层都**必需** description；**name 必需，tags 强烈推荐，description 可选增强**。

### 8.4 检索如何用这些字段（与检索内核对齐）

```
用户查询
  → 文件级：description + 该文件所有 KP 的 name/tags  → 初筛 top-N 文件
  → KP 级：name + tags + description? + 正文 range 片段  → 精排 top-K 知识点
```

| 阶段 | 缺 file description | 缺 KP description | 缺 KP tags |
|------|---------------------|-------------------|------------|
| 初筛 | 仍可用，略降精度 | — | — |
| 精排 | — | 仍可用 name + 正文 | 仍可用 name + 正文 |

智能功能分工：

| 能力 | 主要依据 |
|------|----------|
| 模糊匹配 / 推荐 id | name、tags |
| 语义相似 | description（若有）+ 正文片段 |
| 自动生成 tag | name + range 正文 |
| 自动生成 description | range 正文摘要（用户确认后写入） |

### 8.5 Q5 决策记录

| 子问题 | 状态 | 决策 |
|--------|------|------|
| tag 是否够用 | `[✅]` | **不够单独用**；与 description **分工并存**（见 §8.6） |
| 文件级 description | `[✅]` | **推荐有，非强制**；C2 可镜像 fm |
| KP 级 description | `[✅]` | **可选** |
| KP 级 tags | `[✅]` | **推荐有，非强制**；允许 0 个 |
| 配置 UI | `[✅]` | name 必填；tags 多值输入；description 折叠区可选 |

### 8.6 为何 tag + description 并存（而非二选一）

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **A. tag + description 并存** | 关键词过滤 + 自然语言语义各擅其职；UI 清晰 | 字段多一个 | **`[✅]` 采纳** |
| B. 只要 tag | 简单；枚举友好 | 搜「连续动作空间算法」类自然语言问句弱；悬停无解释 | ❌ |
| C. 只要 description | 语义强 | 难做精确过滤/分组；AI 自动生成不稳定时检索漂移 | ❌ |

**具体分工**：

```
tag          →  「属于哪几类」   →  过滤、分组、推荐、图谱聚类
description  →  「是什么/讲什么」→  语义相似、悬停、精排、智能生成摘要
name         →  「叫什么」       →  精确匹配、展示、跳转定位
```

**V1 检索最低输入集**（字段都可选时的降级链）：

1. 有 tags → 初筛/过滤优先 tags  
2. 有 description → 语义排序加权  
3. 都没有 → 退化为 name + 正文 range 片段（仍可用，质量下降）

**不强制填 description 的原因**：用户快速记笔记时只有标题/name；强制 description 会增负担，与「人机协作、AI 后补」原则一致——M4 可「一键生成 description 建议」，用户确认再写入。

---

## 9. Q6：边类型（定稿）

### 9.1 links 与 edges 分离

见 §3.3。V1：**3 种语义边** + **links 导航**。

### 9.2 V1 边类型 `[✅]`

| 类型 | 含义 | 正文实体 | 来源 |
|------|------|----------|------|
| **contain** | 父包含子 | 无 | range 几何包含自动 |
| **reference** | 参考/引用/依赖（**含原 prerequisite 语义**） | 无 | 配置 / AI 建议 |
| **extend** | source 是 targets 的延伸/进阶 | 无 | 配置 / AI 建议 |

~~prerequisite~~ → 并入 **reference**；强弱用 **relevance** 区分。

### 9.3 reference 与 extend

| | reference | extend |
|---|-----------|--------|
| 语义 | 参考、引用、依赖（广） | 延伸、进阶、深入 |
| 强度 | **relevance** 0～1 | relevance + 类型 |
| V2 拼接 | 高 relevance → 主链 | 可选附录 |

### 9.4 方向约定

| type | 方向 | 读法 |
|------|------|------|
| contain | parent → child | 父包含子 |
| reference | source → targets | 「A 参考/依赖 B」 |
| extend | source → targets | 「A 是 B 的延伸」 |

互指 = 两条有向边；渲染可显双箭头。

### 9.5 relevance（0～1）

驱动图谱拉力与 V2 拼接权重。类型默认初值：contain 0.9、reference 0.7、extend 0.6；用户可覆盖。

### 9.6 Q6 / Q7 决策记录

| 子问题 | 状态 | 决策 |
|--------|------|------|
| 语义边 | `[✅]` | contain、**reference**、extend |
| prerequisite | `[✅]` | **改名合并入 reference** |
| links vs edges | `[✅]` | 分离；删 link ≠ 删 edge |
| relevance | `[✅]` | 0～1，表达 reference 强弱 |
| 有向边 | `[✅]` | 互指 = 双有向边 |

---

## 10. Q12：range 与 link 如何持久化（续）

### 10.1 两类定位

| 对象 | 定位键 | 从何时 |
|------|--------|--------|
| **links** | `anchor_text` + `occurrence` | M1 |
| **KP range** | `start/end.snippet` + `line_hint` | **M0 起** |

**M0 即落实 KP range 的 snippet 方案**，不用临时纯行号，避免后面改规格。

### 10.2 KP range：双端 snippet `[✅]`

```yaml
range:
  start: { snippet: "## Q-Learning", line_hint: 42 }
  end:   { snippet: "ε-greedy 小结", line_hint: 87 }
```

**snippet 选取规则** `[✅]`：

| 规则 | 说明 |
|------|------|
| **S1** | start = range 第一行 trim；end = 最后一行 trim |
| **S2** | 单行超 80 字截断 |
| **重定位** | `line_hint ± N` 窗口搜 → 失败则全文搜 → 更新 hint |
| **end 方向** | 从 start 匹配位置**向后**搜 end |

**snippet 重复**：start 定位后用 `line_hint` 消歧；仍歧义 → 进入**用户辅助**（下节）。

### 10.3 用户辅助 `[✅]`

自动重定位不够时，必须有人机协作入口（M0 就要有最小版）：

| 场景 | 用户辅助 |
|------|----------|
| snippet 匹配到多处 | 弹列表展示候选行 + 预览，用户点选正确行 |
| 自动重定位失败 | 检查面板警告；配置里「重新锚定」→ 用户拖选 range → 重写 snippet |
| 标题扫描提议 range | 预览高亮 + **确认/微调** 后才写入侧车 |
| 编辑 md 后 | 提示「range 可能漂移」→ 一键尝试重定位 或 手动重锚定 |
| links 的 anchor 歧义 | 同 `occurrence` 列表，用户选第几处 |

原则：**机器提议，用户确认**；辅助操作重写 snippet + line_hint，不 silent 改。

### 10.4 links 定位（M1）`[✅]`

`anchor_text` + `occurrence`；歧义时同上表用户辅助。

### 10.5 可选兜底

极乱文本：用户确认后插入 `<!-- @kp:id:start/end -->`。`[⏳]` 非 M0 默认。

### 10.6 Q12 决策记录

| 子问题 | 状态 | 决策 |
|--------|------|------|
| KP range M0 | `[✅]` | snippet + line_hint |
| snippet 规则 | `[✅]` | S1 + S2；end 向后搜 |
| 用户辅助 | `[✅]` | 歧义/失败时 UI 选行、拖选重锚定、提议确认 |
| links 定位 | `[✅]` | anchor_text + occurrence（M1） |
| 隐藏注释 | `[⏳]` | 可选兜底 |

---

## 11. Q9：检索内核 V1 最低能力

### 11.1 内核负责什么

检索内核**不只是搜索框**，统一支撑：

| 能力 | 场景 |
|------|------|
| **search** | 配置里搜 KP、虚链定向、全局查找 |
| **suggest_links** | 为虚链 / 正文术语推荐 targets |
| **suggest_kp** | 检测候选 KP + 提议 range（配合 §3.5 S1–S5） |
| **suggest_tags / description** | 从 range 正文提议 metadata |
| **suggest_merge** | 冗余 KP 合并建议 |
| **suggest_edges** | reference/extend 关系建议 |

所有结果 **提议 → 用户确认**，禁止 silent 写入。

### 11.2 分层架构（推荐）

```
SearchKernel
├── LexicalProvider（V1 Must）   ← 倒排 + 模糊 + 多字段加权
└── EmbeddingProvider（V1 Should，可选） ← 本地向量，可关、可 lazy load
         ↑
    统一 search() 合并排序后返回
```

**一条 API 进、多源出**：

```
search(query, scope: file|kb, limit, modes?: lexical | semantic | both)
→ [{ kp_id, score, sources: ['id-exact','name-fuzzy', ...] }]
```

### 11.3 Lexical 层（V1 Must）`[✅]`

**不依赖 embedding 即可 ship 的最低集**：

| 机制 | 说明 |
|------|------|
| **倒排索引** | 对 id、name、tags、description、file.description 建 token 索引 |
| **中文分词** | jieba（或等价）进 Lexical；分词结果缓存于 `.memoria/cache/` |
| **模糊匹配** | 子串 + 编辑距离；id/name 优先 |
| **多字段加权** | 见下表 |
| **scope** | `file`（当前文件）/ `kb`（全库） |

**字段权重（Lexical 初排）**：

| 信号 | 权重 | 来源 |
|------|------|------|
| id 精确 / 前缀 | 最高 | sidecar |
| name 精确 / 模糊 | 高 | sidecar |
| tags 命中 | 中高 | sidecar |
| description token | 中 | file / KP |
| range 正文 token（可选） | 低 | md + snippet 定位 |

**V1 Lexical 能 cover 的场景**：

- 搜索框找 KP  
- 虚链定向（按 name/tag 模糊）  
- 正文已有 KP 名 → 建议 wrap 为 link  
- 冗余检测（name 高度相似）  
- tag 提议（jieba 抽关键词 ∩ 库内高频）

**做不到 / 质量差**： paraphrase（「连续动作 RL」→ DDPG）、语义近重复（attention vs 注意力机制）。

### 11.4 Embedding 层（V1 Should，可选）`[✅]`

| 项 | 决策 |
|----|------|
| V1 是否必须 | **否**——Lexical 不够用时再开，不阻塞 M4 闭环 |
| 架构 | **Must 预留** EmbeddingProvider 接口；实现可 M4 末或 V1.1 |
| 模型 | 本地小模型（如 multilingual-MiniLM 级）；具体型号 M4 Benchmark |
| 存储 | `.memoria/cache/embeddings/`；**可删可重建** |
| 加载 | **lazy**：首次 semantic 搜索或设置里开启后才加载；后台预热可选 |
| 用途 | 语义 search、近重复合并、虚链 paraphrase 定向、S4 range 提议 |

**合并排序**：Lexical top-50 → Embedding rerank top-10；或双路召回 merge（modes=both）。

### 11.5 生成类能力（tag / description / id）

| 能力 | V1 做法 |
|------|---------|
| tag 提议 | jieba + 库内词表 + 共现；**非 LLM** |
| description 提议 | range 首句 / 首段截取（规则）；**非 LLM** |
| id 提议 | name .slug 化 + 冲突检测 |
| LLM 生成 | **V1 Won't**；V1.1+ 可选本地小 LLM |

### 11.6 索引与性能

| 索引 | 存哪 | 重建 |
|------|------|------|
| Lexical 倒排 | `.memoria/cache/lexical/` | md + sidecar 变更后增量/全量 |
| Embedding | `.memoria/cache/embeddings/` | 同上，可选延迟 |
| 运行时 | 合并进 `index.json` 或独立读 cache | index.json 可删；cache 可删 |

**冷启动**：打开 KB → 重建/加载 lexical（快）→ UI 可用 → embedding 后台（若开启）。

### 11.7 与 MVP 对齐

| 阶段 | 检索 |
|------|------|
| M0–M3 | **无检索**；手动维护 |
| **M4** | 接入 **Lexical SearchKernel**；embedding 接口 stub |
| M4+ / V1.1 | 实现 EmbeddingProvider；Benchmark 后默认开或关 |

### 11.8 Q9 决策记录

| 子问题 | 状态 | 决策 |
|--------|------|------|
| V1 最低 | `[✅]` | **Lexical 层 Must**（倒排 + 模糊 + jieba + 多字段加权） |
| Embedding | `[✅]` | **Should，可选**；接口预留；lazy load；不阻塞 V1 闭环 |
| 统一 API | `[✅]` | `search()` 聚合；各 suggest_* 复用内核 |
| LLM 生成 | `[✅]` | V1 Won't；规则/jieba 提议 |
| 离线 | `[✅]` | 全部本地；无联网 |

**检索与维护产品决策（2026-07-07）**：见 [`search-and-maintenance-decisions.md`](search-and-maintenance-decisions.md)（KP 命中字段、无结果降级 B、tag 候选/已选、links⊂edges、引导维护板块、正文定位选项、merge 夹具）。

---

## 12. Q10：导航历史栈

### 12.1 栈里存什么

一条记录 = **一次阅读焦点**：

```
NavFrame = { file, kp_id, source? }
```

- `kp_id`：高亮目标 KP（§3.4）；无 KP 时 `null`（文首）

### 12.2 带 cursor 的时间线（非纯双栈顶）

导航历史是一条**时间线** + **cursor**（当前位置），不是永远停在物理栈顶：

```
stack:  [ F0, F1, F2, F3, F4 ]
              ↑
           cursor（当前阅读焦点）

filePointer[file] → 该文件最近一次对应的 stack 下标（文件指针）
```

- **← / →**：只移动 `cursor`，不删帧  
- **forward** 语义：cursor 右侧的帧即「前进」方向；截断后不存在

每个打开过的 `file` 维护 **`filePointer[file]`** = 该文件在 stack 上的最近下标。

### 12.3 KP 跳转（link / 图谱 / 搜索）→ **append + 截断**

正文 link、图谱节点、沿边导航、搜索「转到 KP」：

1. 若 cursor 不在物理末尾 → **删除 cursor 之后所有帧**（放弃已抛弃的分支）  
2. **append** 新帧 `{ target.file, target.kp_id }`  
3. `cursor` ← 新末尾  
4. 更新 `filePointer[target.file]` ← cursor  

同帧去重：新帧与 `stack[cursor]` 相同则跳过 append。

**多目标 link**：仅队列**首项**走上述 append；其余进顶栏文件列表，不入 stack。

### 12.4 文件树点**其他文件** → **移到文件指针 + 截断** `[✅]`

用户从文件树（或等价「换文件」入口）打开**另一个**文件，**不是 append**：

1. 查 `filePointer[targetFile]`  
   - **有记录**（该文件曾出现在时间线）：  
     - `cursor` ← 该下标  
     - **删除** `stack[cursor + 1 .. 末尾]`（从该文件指针到原栈顶的全部清空）  
     - 恢复到 `stack[cursor]` 的 `{ file, kp_id }` 并高亮  
   - **无记录**（首次打开该文件）：  
     - 若 cursor 不在末尾 → 先删 cursor 之后帧  
     - append `{ targetFile, kp_id: null }`  
     - `cursor` ← 新末尾  
     - `filePointer[targetFile]` ← cursor  

**当前文件**若与 target 相同（点树里已在看的文件）：不动 stack，仅恢复滚动/高亮。

效果等价于：**把有效栈顶收到该文件的 filePointer，抛弃右侧 abandoned 分支**。

```
例：
stack: [ A@kp1, B@kp2, C@kp3, A@kp4 ]   cursor=3（正在看 A）
filePointer: A→3, B→1, C→2

文件树点击 B：
  cursor ← 1，删除下标 2..3 → stack 变为 [ A@kp1, B@kp2 ]
  打开 B，高亮 kp2
```

### 12.5 哪些操作 **不动 stack**

| 操作 | 行为 |
|------|------|
| 切换**已打开**标签页（同一 tab 集内） | 走 **§12.4** 文件指针规则（换文件 = 截断/恢复） |
| 同文件内滚动 | 仅更新视图；可选延迟写回 `stack[cursor].scroll`（V1 可不做） |
| 悬停高亮 | 不影响 |
| 配置 / 设置 / 2D↔3D | 不影响 |

### 12.6 哪些操作 **整栈清空**

| 操作 | 行为 |
|------|------|
| 打开/切换**知识库** | 清空 stack + 所有 filePointer |
| 用户「清空导航历史」 | 同上 |
| 关闭知识库 | 同上 |

### 12.7 快捷键与 UI

| 操作 | 绑定 |
|------|------|
| 后退 | `Alt+←`：`cursor--`，恢复 `stack[cursor]` |
| 前进 | `Alt+→`：`cursor++`（若右侧有帧） |
| 不可达 | 按钮置灰 |

### 12.8 与标签页 / 文件列表

| 结构 | 作用 |
|------|------|
| **NavStack + cursor** | 阅读时间线；← → |
| **filePointer** | 文件树换文件时截断/恢复 |
| **Tabs** | 哪些文件还开着 |
| **LinkQueue** | 多目标 link 的待打开文件 |

### 12.9 Q10 决策记录

| 子问题 | 状态 | 决策 |
|--------|------|------|
| 栈条目 | `[✅]` | `{ file, kp_id }` + **cursor** |
| KP 跳转 | `[✅]` | append；截断 cursor 右侧 |
| **文件树换文件** | `[✅]` | **cursor ← filePointer[file]**；删指针到原栈顶；非 append |
| 首次打开文件 | `[✅]` | append + 登记 filePointer |
| 换 KB | `[✅]` | 整栈清空 |
| 多目标 link | `[✅]` | 仅首 target append |
| V1 | `[✅]` | 随 M1 |

---

## 13. 开放问题（其余）

按影响面排序：

| # | 问题 | 状态 |
|---|------|------|
| Q1 | 知识点范围怎么定？ | `[✅]` 显式 range；标题仅辅助提议；V1 默认方案 1（双端范围） |
| Q2 | 正文链接？ | `[✅]` 只穿衣；`links[]` 导航，与 edges 分离；M1 试语法 |
| Q3 | V1 是否要 3D？ | `[✅]` 必须；独立图谱引擎板块 |
| Q4 | M0 从哪开始？ | `[✅]` snippet range + 标题辅助 + 跳转目标 KP 高亮 |
| Q5 | tag 与 description 分工？ | `[✅]` tag+description 并存；file/KP description 可选；KP tags 推荐可选 |
| Q6 | 边类型？ | `[✅]` contain + **reference** + extend；prerequisite 已合并；§9 |
| Q7 | 有向边是否足够？ | `[✅]` 是；互指 = 双有向边；§9.4 |
| Q8 | 元数据存储格式？ | `[✅]` C2 混合偏 sidecar YAML；`.memoria/` 全结构；index 可重建；§6.4 级联 |
| Q9 | 检索内核 V1？ | `[✅]` Lexical Must + Embedding 可选；§11 |
| Q10 | 导航栈？ | `[✅]` cursor+filePointer；换文件=截断分支；§12 |
| Q11 | html 是否进 V1？ | `[⏳]` 还是先只做 md |
| Q12 | range / link 定位？ | `[✅]` snippet+用户辅助；§10 |
| Q13 | 桌面壳选型？ | `[⏳]` 现 pywebview；**M5 计划迁 PyQt6 + Win32 hidden chrome**（§4.6）；Electron/Tauri 暂不采纳 |

---

## 14. MVP 切片（建议验证顺序）

不做完整系统，用最小实验验证最大不确定性：

| 阶段 | 验证目标 | 产出 |
|------|----------|------|
| **M0** `[✅]` | KP snippet range + 用户辅助 + 目标高亮 | S1/S2 snippet；歧义 UI；标题提议需确认 |
| **M1** `[✅]` | links + 导航栈 | `[[]]` + `links[]`；← → 栈 + filePointer；多目标跳转；右键建链/编辑；虚链 |
| **M2** `[部分]` | 图谱引擎 + 2D/3D | 独立 2D/3D 布局；Canvas + Three.js；节点群页签；**压测** `scripts/graph_layout_benchmark.py` + `test_graph_stress.py`；**Worker 布局**（≥60 节点）+ **3D 八叉树拾取**（≥40 节点）；**待办**：布局模式、M4 智能群命名 |
| **M3** | 配置 + 手动维护 | 无 AI 也能建库、改 id、绑跳转 |
| **M4** | Lexical 检索内核 | SearchKernel + 虚链定向 + suggest；Embedding 接口 stub |
| **M5** `[⏳]` | **PyQt6 + Win32 桌面壳** | QWebEngine 复用 m0 前端；hidden chrome；任务栏/DWM 行为；见 §4.6 |

每个 MVP 可独立重做，不背负上一阶段的错误选型。

---

## 15. 协作方式（轻量，替代原 standards）

| 规则 | 说明 |
|------|------|
| 本文档为主 | 愿景 + 开放问题；定稿后另写 `design-spec.md` 技术规格 |
| 决策标记 | `[✅]` 采纳 / `[❌]` 否决 / `[⏳]` 待定 |
| 只记录结构性决策 | 实现细节不进本文档 |
| 讨论即更新 | 你拍板后我改对应章节，不另起冗长规范 |

---

## 附录 A：原始意识流（归档）

<details>
<summary>点击展开 — 未改动的初始描述</summary>

这是一个带智能检索内核的知识图谱系统。IDE 式界面，预览/编辑知识点文档（md、html，是否自定义格式未定）。知识点为最小单元，文件是容器，知识点可嵌套。左侧：文件树 + 2D/3D 图谱；悬停高亮节点及出边目标；点击定位到知识点范围开头。范围划分：标题方案有争议。主区域：公式预览 + 智能识别知识点并建跳转。跳转可多目标；队列首项为跳转目标，其余进文件列表；需文件内定位与高亮。检索内核：本地、离线；id/tag/description；虚跳转；配置功能；设置；鲁棒导入。V2：智能拼接学习路径、完整编辑模式。开发宜 MVP 迭代，避免纸上谈兵。

</details>
