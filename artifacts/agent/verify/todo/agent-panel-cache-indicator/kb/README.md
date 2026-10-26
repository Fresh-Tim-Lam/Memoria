# tests/probe-kb/ —— 预览 / 显示子系统「探针语料库」

> 用途：为「显示子系统接口化 + 两个插头（`LegacySurface` / `NewSurface`）一致性」提供**可复现的语料 + 操作脚本**。
> 需求来源：[docs/design/preview-render-refactor.md](../../docs/design/preview-render-refactor.md) §1.8 / §1.10 C；
> 断言清单：[docs/design/view-surface-contract.md](../../docs/design/view-surface-contract.md) §5（C1–C12）。
> 状态：**纯数据 + 脚本**，不改产品代码；语料与脚本最终入 `git`（R21/R22 已由人拍板）。

## 三段结构

| 目录 | 是什么 | 怎么用 |
|---|---|---|
| `corpus/` | **构造覆盖**：7 个文件，每个专打一类易碎构造（IME/中文、inline 边界、块边界、不可编辑块、图片、wikilink/KP、极端项） | 人工在预览区逐条交互复测；也可被脚本按 `cases.json` 消费 |
| `scale/` | **规模档位**：`gen_scale.py` + 三档产物 `scale-1k/5k/10k.md` | 压力测试与性能预算（C9）；三档由脚本**确定性**生成 |
| `cases/` | **操作脚本**：`cases.json`，14 条可复现序列，覆盖契约 C1–C12 | pytest / 浏览器脚本读它驱动回放，比对「真源逐字 + 落点行号 + 读数」 |

## 怎么用

1. **当知识库打开**：在应用里把 `tests/probe-kb/` 这个目录选为知识库（首次打开时应用会初始化 `.memoria/`）。
2. **消费 `cases.json`（可选）**：
   - 每条 `case` = `{ id, covers, target, steps[], expect{} }`，`steps[]` 是可复现序列，`expect{}` 是行为断言；
   - **坐标一律是文本坐标**（块 = 语义匹配，见文件头 `coordinate` 字段；块内 = `{block,path,offset}`；整篇 = `{line}`）——**不含像素 / DOM 节点**，因为块 `id` 由实现生成、无法预先写死；
   - 每条应在 `legacy` 与 `new` 两套插头上各跑一遍（C11），**期望值来自「真源文本 + 行为契约」，不来自「与 legacy 一致」**。

## 确定性声明

- `scale/scale-1k.md`、`scale-5k.md`、`scale-10k.md` **由 `scale/gen_scale.py` 生成，可逐字节重现**：
  脚本不用随机数、不用时间，固定 UTF-8 + LF；重复执行输出 sha256 不变。
  重新生成：`python tests/probe-kb/scale/gen_scale.py`（会同时打印三档的行数与字节数）。
- 目标行数分别为 1000 / 5000 / 10000（**精确命中**，非近似）。
- 模板内嵌于脚本、混合多种块（标题 / 段落 / 有序·无序列表 / 表格 / python 围栏 / 行内公式 / `$$` 公式块 / mermaid / 图片 / wikilink）。

## 为什么不创建 `.memoria/`

- 本目录**只放语料与脚本**，不预先内置 `.memoria/`：
  - `.memoria/**` 是**产品状态**（manifest/sidecars/pending/images…），由**应用代码**在首次打开该目录时初始化，不应由 Agent 手造（会与产品写入纪律冲突）；
  - 语料里的图片均为**占位相对路径**（`./.memoria/images/probe-0N.png`），**没有真实图片二进制**，因此也无需预置图片资产。
- 若应用**不接受**没有 `.memoria/` 的目录，则按 [docs/reference/agent-guide/10-data-layout-and-host-embedding.md](../../docs/reference/agent-guide/10-data-layout-and-host-embedding.md) §1.1 的清单补齐（`manifest.yaml` 等），该清单以该文档为准，本 README 不复制。

## 如实（已知 / 待验证）

- **体量**：`scale-10k.md` 单文件约 **182 KB**（三档合计约 297 KB），会让仓库变大 —— **已由人拍板三档全部入库**（R22），建议**单独一次提交**，并在 `docs/conventions/directory-organization.md` 登记时把这条代价一并写明（**登记尚未做**）。
- `corpus/04-non-editable.md` 的 **frontmatter 必须落在文件首行**（`strip_frontmatter` 以 `text.startswith('---')` 判定），因此该文件的 probe 注释位于 frontmatter 之后，而非文件第一行 —— 这是与「每个 corpus 文件开头写 probe 注释」的**有意偏差**。
- 图片为占位、**无真实文件**，用于测懒加载 0 高场景；不保证能渲染出真实图片。
- `corpus/07-extremes.md`：1000 字不换行段落与约 2000 字符单行为**近似字数**；「连续 200 个空行」为**精确 200 行**。
- 本目录**未登记**进 `docs/conventions/directory-organization.md` / `docs-management.md §4.1`（登记属 `registrar` 职责，需另行处理）。
