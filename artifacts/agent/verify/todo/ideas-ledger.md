# task-184 报告：人提出的想法/需求台账（ideas.md）

> 2026-10-27｜todo-owner｜写域：`docs/todo/ideas.md`（新建）、`docs/todo/README.md`（索引行）、`docs/todo.md`（§19 指针）、本报告。
> 纪律：不 commit；未动 `src/**`、`docs/design/**`、`docs/conventions/version.md`、`docs/example/**`。

## 0. 一句话结果

`docs/todo/ideas.md` 已建立并被索引（`docs/todo/README.md` + `docs/todo.md §19`）：**28 条人提出需求/想法 + 1 条补充裁决（I-29）**逐条落盘，每条含「编号 | 人原话/概括 | 提出时间 | 状态 | 去向」。
**状态分布**：已落地 **23** / 待排期 **4** / 已否决或已缩范围 **1** / 待澄清 **1**（合计 29）。
**33 个 commit sha 全部经 `git cat-file -e` 核对存在**（无编造、无凭记忆）；`pytest 1655 passed` / `team_audit FAIL=0` / `check_todo_size.py PASS`（24,556 B / 326 行，0 死链）。

## 1. 验收对照

| 条件 | 结果 |
| --- | --- |
| 1. `docs/todo/ideas.md` 建立并被索引 | ✅ README 现役文件表新增行；`todo.md §19` 指针（`todo/ideas.md`） |
| 2. 28 条逐条落盘（不许挑） | ✅ I-01…I-28 全量 + I-29 补充裁决；表内 29 行 |
| 3. 每条有状态 + 去向（sha/task id/理由） | ✅ 见 idea.md 表；无空状态、无空去向 |
| 4. 抽查 3 条已落地核对 sha | ✅ 见 §2（实际**全量 33 个**都核对） |
| 5. `check_todo_size.py` PASS；0 死链 | ✅ PASS（24,556 B / 326 行；WARN=0） |
| 6. 报告 | ✅ 本文件 |

## 2. commit sha 核对（全量，样例 3 条加粗）

`git cat-file -e` + `git log -1 --format='%h|%ad|%s'` 逐条核对 33 个 sha，全部存在；提交时间已写入台账去向列。

| sha | 提交时间 | 标题 |
| --- | --- | --- |
| **`f2a415c5`**（I-01 剪切） | 2026-10-25 23:46 | fix(editor): task-150 源码区剪切（Ctrl+X）不可用 |
| **`90fad3e9`**（I-14 KG 可视化冻结） | 2026-10-26 20:17 | feat(kg): KG 可视化 v0 冻结 —— Phase 3/4/5 走完 |
| **`8218a4bb`**（I-19 README 双语） | 2026-10-26 23:52 | docs(marketing): README 双语重写 + 断言—证据表 + 仓库元数据 + tag 规范 |
| `a0c7dfd9` | 2026-10-26 00:39 | KG v0 五项落地 + 引用块内列表一期 |
| `ae858b8c` / `193cc112` | 2026-10-26 09:07 / 09:20 | task-156 Step2 / Step3 |
| `1da0b50b` / `08ed38b9` | 2026-10-26 15:35 | 控制台闪窗修复 / 用户态移出安装目录 |
| `f21307ac` | 2026-10-26 17:54 | task-164 stale_write 真因 + task-168 小窗 8 方向缩放 |
| `df0479b6` / `5e7bd526` | 2026-10-26 16:06 / 16:41 | 链接小窗优先 / 链接面板 v2 |
| `f539589f` / `d658a395` | 2026-10-26 17:36 / 18:24 | 选择题卡片 / 输入框把手+圆环 |
| `1fa994dc` / `5e8e4d88` / `e2b81998` | 2026-10-26 | mermaid 抢滚动 / 顶栏文案 / 保底下限 |
| `be4e9dec` / `c940a21c` / `81175b9b` / `a2b9879c` | 2026-10-26/27 | 更新机制 / 发布包格式 / FORMAT-GATE / zip 校验 |
| `37c94edc` / `121a82a4` / `5442b228` / `4089d914` | 2026-10-26 | per-key 迁移 / UI 立岗 / r7 修 FAIL / C4 双源 |
| `bac1b286` / `61689413` / `0337954e` | 2026-10-26/27 | 缓存命中率移动 / 启动蒙层+星河+音效 / 蒙层 v2 |
| `d1e2e910` / `313a9802` / `b514a36c` / `80e31797` | 2026-10-26/27 | todo 索引化 A+B / KG §6+§8 / 文档索引 / 控制台编码假红 |

## 3. 补充事实（Lead 2026-10-27 补录，已入台账 §2）

- KG §6 毛球态判定 + §8 T-double 已落地 ⇒ `313a9802`（I-14 原"未实现"已改已落地）。
- 文档索引登记 ⇒ `b514a36c`；控制台编码假红修复 ⇒ `80e31797`；启动蒙层 v2 ⇒ `0337954e`（I-28）。
- 门禁基线：`pytest 1655 passed`；`team_audit FAIL=0`（本轮实测复跑一致）。
- U-KGV-5 三项真人判读（T-size-1 / T-label / T-depth）仍**未做** ⇒ I-27 待排期（需人参与）。

## 4. 时间/溯源口径（避免"编时间"）

- **提出时间**：无法从对话精确到分钟 ⇒ 一律写「约 2026-10-25/26/27」（按功能与提交时间倒推），**不冒充足迹**。
- **去向时间**：统一用 `git log` 的提交时间（精确到分钟），已逐条写入去向列。
- 需要人补充的（I-26 L12 条款文本、I-27 判读实验、I-29 规则落章、I-22 排期）均已标「待澄清/待排期」并写明缺什么。

## 5. 新增/变更文件

| 文件 | 变更 |
| --- | --- |
| `docs/todo/ideas.md` | **新建**：29 行台账 + 补充事实 + 维护规则 |
| `docs/todo/README.md` | 现役文件表新增 `ideas.md` 行 |
| `docs/todo.md` | 新增 **§19** 指针（一行） |
| 本报告 | 新建 |

## 6. 复跑

```powershell
python scripts/check_todo_size.py            # PASS 24,556 B / 326 行；0 死链
$env:PYTHONIOENCODING='utf-8'; python scripts/agent/team_audit.py   # FAIL=0
python -m pytest -q tests                    # 1655 passed
Select-String -Path docs/todo/ideas.md -Pattern '^\| \*\*I-\d+'      # 29 行
```
