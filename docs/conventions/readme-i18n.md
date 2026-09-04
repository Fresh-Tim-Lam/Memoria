# README 与项目截图中英描述维护规范

> **用途**：定义仓库 README（`README.md` 英文 / `README.cn.md` 中文）与演示截图（`resources/screenshots/`）的**双语一致性契约**——两份 README 的对照关系与「推荐语言匹配读者」约定、功能/配图描述如何双语同步、截图如何收录与维护、维护后可自动核验的规则；使人机在增删截图、改功能描述时不会造成两份 README 漂移或截图失效。
> **目标读者**：项目负责人 / AI Agent（凡增删项目功能介绍、更换或新增界面演示截图、整理仓库展示文案者必读）。
> **关联文档**：[meta-rules.md](./meta-rules.md)（规范书写元规则）；[docs-management.md](./docs-management.md)（docs 组织规则）；[directory-organization.md](./directory-organization.md)（顶层目录职责）；[resources/README.md](../../resources/README.md)（截图目录使用说明）；[i18n.md](./i18n.md)（应用内语言系统，**不含** README）。
> **状态**：生效中。`screenshots/` 已于 2026-09-03 从 `docs/` 迁至 `resources/screenshots/`（`git mv` 保留历史，README 引用同步）。
> 制定日期：2026-09-03。

---

## 1. 总则

1. **两份 README 并存**：仓库根只维护 `README.md`（英文，面向国际读者/GitHub 默认展示）与 `README.cn.md`（中文，面向中文读者），**不维护第三份**（如 `README.en.md`）。
2. **语言与读者对齐**：英文 README 内的跨语言提示应指向中文版（英文句 + 指向 `README.cn.md`）；中文 README 内的提示指向英文版（英文句 + 指向 `README.md`）。提示语必须与目标读者语言一致（中文读者给出英文句、英文读者给出中文句——读者可顺畅跳转，见 §4 自查）。
3. **同一仓库、同一版本**：版本徽章、示例库路径、功能清单不得只改一边；新增功能段落必须英文/中文成对补充，可先以简洁译文占位但**不得只有一侧**。
4. **截图只为配图**：`resources/screenshots/` 存放演示截图（`demo-*.png`），仅由两份 README 通过相对路径引用；它是仓库级展示资源，**不进入应用发布包、不属于 docs 文档内容**。

## 2. 双语对照结构

| 项 | 英文 README.md | 中文 README.cn.md |
|----|----------------|-------------------|
| 语言切换入口 | 顶部 badge「中文」→ `README.cn.md`；简述后附中文句提示 | 顶部 badge「English」→ `README.md`；简述后附英文句提示 |
| 正文语言 | English | 简体中文 |
| 术语 | 保留 Memoria/`KP`/`snippet-range`/Markdown 原生词 | 术语括号注英文（如 知识点 Knowledge Points） |
| 功能小节 | §Features | §核心功能 |
| 截图小节 | §Screenshots（配 `resources/screenshots/`） | §界面预览（配同一 `resources/screenshots/`） |
| 其余小节 | Getting Started / Tech Stack / Layout / Roadmap / License | 快速开始 / 技术架构 / 项目结构 / 路线图 / License |

**功能描述级对齐建议**：中英文两版按「节」镜像即可（`Why → 为什么用`、`Features → 核心功能`…），不强求逐句等长。

## 3. 截图维护规则

### 3.1 收录

- 截图必须是**真实界面捕获**（自动化/手动均可），统一命名 `demo-<场景>.png`（当前：workspace / graph-3d / split / preview / math / settings / check），分辨率尽量一致（当前 1680×1000）。
- 新增截图流程：
  1. 文件放入 `resources/screenshots/`；
  2. 英文 README §Screenshots **与** 中文 README §界面预览 **各加一张**（`<img src="resources/screenshots/demo-x.png" …>`，配一句各自语言的说明）；需要先说明再贴图；
  3. 同步登记：更新 [resources/README.md](../../resources/README.md) 内容表说明、[docs-management.md](./docs-management.md) 修订记录；
  4. 自检：见 §4。
- 截图 alt 文本用**各自语言**撰写（英文 README 用英文 alt，中文 README 用中文 alt）。

### 3.2 存放与禁止

- 截图**唯一存放地**为 `resources/screenshots/`；`docs/` 只放文档、不放截图等二进制资源。
- 若发现 `docs/` 或仓库其它位置出现截图类二进制并被 README 引用，应迁移并同步引用（参照本次 `docs/screenshots/` → `resources/screenshots/` 的处理：`git mv` 保历史、改 README 引用、登记 docs-management.md）。
- 删除截图 = 同时删除/替换两份 README 中对应 `<img>`，避免坏链。

## 4. 维护后自查清单

- [ ] 两份 README 的截图**路径前缀一致**：`resources/screenshots/demo-*.png`（禁 `docs/screenshots/`）；
- [ ] 引用的每个 `demo-*.png` 在 `resources/screenshots/` 中**真实存在**（反向：目录中每个 png 都被至少一份 README 引用或声明为备用）；
- [ ] 语言切换链接正确：英文版→中文 badge 指向 `README.cn.md`、中文版→英文 badge 指向 `README.md`；顶部提示语为目标读者语言；
- [ ] 新增功能/术语在**英文与中文两版都出现**（可英文先行、中文随后，但不可只改一边）；
- [ ] 版本徽章/示例库路径等「仓库级事实」两版一致；
- [ ] 截图登记与修订记录已同步（resources/README.md、docs-management.md）。
- [ ] 可用快速核验：`git ls-files 'resources/screenshots/*'` 与两份 README 中 `resources/screenshots/` 出现次数比照。

## 5. 修订记录

| 日期 | 修订内容 |
|------|---------|
| 2026-09-03 | 初版：README 双语对照结构、截图收录/存放规则、维护后自查清单 |
