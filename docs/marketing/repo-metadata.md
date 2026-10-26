# GitHub 仓库元数据：description / topics / 社交预览 / 截图素材

> **用途**：GitHub 仓库页的「About」区、topics、社交预览卡、README 顶部素材的可复制文案与拍摄脚本。
> **状态**：生效中（2026-10-26，task-182）。**维护者**：发布/宣传 Owner。
> **关联**：[claims.md](./claims.md)（**每条文案的能力性断言先在那里登记**）、
> [README.md](../../README.md) / [README.cn.md](../../README.cn.md)、
> [tag-release-spec.md](./tag-release-spec.md)。

---

## 1. 仓库描述（About → Description）

GitHub 的 description 上限 **350 字符**（英文按 350 字符卡；中文按字符数同样 ≤350）。
下面两版都**只包含 claims.md 中 implemented / design-intent 的表述**，不含被禁止的断言（不写"图谱赋能 agent 检索"）。

### 1.1 英文（推荐，**当前为 328 字符**）

```text
Local-first knowledge IDE for Windows: Markdown notes with knowledge-point links at exact snippet range, a 2D/3D graph designed as an index (design intent), built-in FSRS spaced repetition, and an AI agent that reads and writes your knowledge base through a backed-up, undoable, approval-preset write path. Plain files, no account, MIT.
```

字符数校验：`python -c "print(len(open('docs/marketing/repo-metadata.md',encoding='utf-8').read()))"` 不能用于本段——
校对方式见 `artifacts/agent/verify/marketing/check_claims.py::check_repo_metadata`（会实测两版 description 字符数并断言 ≤350）。

### 1.2 中文（备用；GitHub About 只能放一条，若主语言用中文则替换）

```text
面向 Windows 的本地优先知识 IDE：Markdown 笔记 + 按精确片段范围链接的知识点 + 2D/3D 图谱（按"索引"设计，设计理念）+ 内置 FSRS 间隔复习 + AI Agent（单一写路径：写前备份、可撤销、按会话审批档位）。纯文件、无账号、MIT。
```

> **为什么不写「Obsidian 替代品」**：定位是"不同的取舍"，不是"替代"；写替代会立刻引发不成立的能力比较（见 claims.md §8）。

---

## 2. Topics（10–20 个，按重要度排序）

GitHub topics 全小写、用连字符；建议**取前 12–15 个**（过多会稀释主题信号）。

```text
local-first
markdown
knowledge-base
knowledge-graph
note-taking
spaced-repetition
fsrs
ai-agent
llm
mcp
python
desktop-app
windows
pkm
second-brain
```

**选择理由（与 claims 对应）**

| topic | 为什么成立（证据） |
|---|---|
| `local-first`, `markdown`, `knowledge-base` | CLM-01 / CLM-03：纯文件、普通文件夹 |
| `knowledge-graph`, `note-taking` | CLM-10/11/12：知识点级链接 + 冻结的图谱设计 |
| `spaced-repetition`, `fsrs` | CLM-20/21：内置 FSRS 调度（`resources/agent-prompts/fsrs.py`） |
| `ai-agent`, `llm`, `mcp` | CLM-30/31/33：应用内 agent + 审批写 + MCP 子集 |
| `python`, `desktop-app`, `windows` | 技术栈与发布形态（`README.md` 前置条件） |
| `pkm`, `second-brain` | 领域词（学习/知识管理受众） |

> 不用的 topic：`obsidian`（不蹭竞品名）、`security`/`encryption`（无此能力）、`free`（许可是 MIT，但"free"易与免费混淆）。

---

## 3. 社交预览（Social preview）建议

GitHub 社交预览图 **1280×640**（PNG/JPG，≤1MB）。建议用**真实界面截图 + 一句定位**，不要 P 假数据：

1. 底色：应用深色主题背景色（与 `resources/screenshots/demo-workspace.png` 同源，不新造视觉）。
2. 左侧 60%：`demo-workspace.png` 的 2D 图谱 + 编辑区（可裁切，不缩放变形）。
3. 右侧 40%：三行大字：
   - `Memoria`（产品名）
   - `The graph is an index, not decoration.`（设计理念，claims CLM-10 的 design-intent 表述）
   - `Local-first · Knowledge points · FSRS review · AI agent`（四个 implemented 能力点）
4. 右下角小字：`MIT · Windows · v<当前版本>`
5. **禁止**在预览图上放性能数字（预览图不会随版本更新，容易变旧账）。

> 若暂时不做图：GitHub 会抓 README 第一张图；当前 README 顶部是 logo，建议把 `demo-workspace.png` 放在
> README 叙述第一屏（见 README.md「Screenshots」的排布），让抓取结果至少是真实界面。

---

## 4. 截图 / GIF 素材脚本（用真实知识库，不造假数据）

### 4.1 必须遵守（与 `docs/conventions/readme-i18n.md` 对齐）

- 截图**唯一存放地**：`resources/screenshots/`，命名 `demo-<场景>.png`；README.md 与 README.cn.md 各引用一次。
- 必须是**真实界面捕获**；分辨率基线 **1536×816**（宽高比 1.88），README 展示宽 `820`。
- 采集工具：`scripts/screenshots/hotkey_capture.py`（F9 热键抓窗口客户区，重复帧不占号）。
- 用**仓库自带示例库**，不截入私人内容：
  - `docs/example/showcase/`（10 个内容页 / 36 个知识点 / 跨页链接 / 图片 / 样式画廊）
  - `docs/example/AAA_Vocab/`（真实规模的词库示例，188 个 sidecar）

### 4.2 现有 8 张（已满足 README；新增/重拍时替换同名文件）

| 文件 | 场景 | 一句话说明（EN / 中文） |
|---|---|---|
| `demo-workspace.png` | 2D 图谱 + 编辑区 | Workspace with 2D graph / 工作区与 2D 图谱 |
| `demo-graph-3d.png` | 3D 图谱 | 3D graph / 3D 知识图谱 |
| `demo-split.png` | 分栏编辑 | Split view / 分栏：源码 + 预览 |
| `demo-preview.png` | 富文本预览 | Rich preview / 富文本预览 |
| `demo-math.png` | LaTeX 公式 | Math rendering / 公式渲染 |
| `demo-settings.png` | 显示设置 | Display settings / 显示设置 |
| `demo-check.png` | 完整性检查 | Integrity check / 完整性检查 |
| `demo-check-report.png` | 检查报告复制 | Check report / 检查报告 |

### 4.3 GIF 选题（≤5 秒、≤5MB，录屏用 1536×816）

| # | 脚本（可复现步骤） | 展示的断言（claims） |
|---|---|---|
| G1 | 打开 `showcase` → 点 `overview` 的 `[[Transformer]]` 链接 → 源码高亮到目标行区间 → 后退 | CLM-02 snippet-range 链接 |
| G2 | 侧栏在 2D/3D 间切换 → 滚轮缩放 → 点节点跳回原文 | CLM-13 视图与跳转 |
| G3 | 顶栏「复习」→ 今日到期卡 → 评分 → 下一张 | CLM-20/21 FSRS 复习 |
| G4 | 打开设置 → 关闭「允许出网」→ 展示 agent 相关入口变灰/提示离线 | CLM-51 出网开关（**不**录成"完全离线"） |
| G5 | 让 agent 提议一次链接修改 → 出现逐条确认卡 → 确认 → 撤销一步 | CLM-31/32 审批写 + 撤销 |

> GIF 不做"性能数字动画"（数字会过期；数字只放 README 的 Measured 段并带口径）。

---

## 5. README 顶部素材顺序（建议）

1. logo（`resources/icons/Memoria.png`）
2. 标题 + 一句话定位
3. 三枚 badge（版本 / Windows / MIT）+ 语言切换
4. `demo-workspace.png`（第一屏图，社交预览抓取用）
5. Why it's different（3–4 条，全部 implemented 或 design-intent）
6. Graph-is-an-index 设计理念段（明确标注 design intent + roadmap）

---

## 6. 修订记录

| 日期 | 变更 |
|---|---|
| 2026-10-26 | 初版（task-182）：description 双语、topics、社交预览、8 张截图登记、5 条 GIF 脚本 |
