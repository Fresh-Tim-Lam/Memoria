# task-165 报告：todo.md 索引化（Batch A 完成；Batch B/C 待做）

> 2026-10-26｜todo-owner｜写域：`docs/todo.md`、`docs/todo/**`、`scripts/check_todo_size.py`、`docs/conventions/docs-management.md`（仅登记/规则）、3 处引用修正（Lead 授权）、本报告。
> 纪律：不 commit；未动 `docs/example/**`、`src/**`、`version.md`。

## 0. 一句话结果（Batch A = §13 应用内对话）

§13 已迁移：**`docs/todo.md` 65,445 → 54,382 B（−11,063 B，−16.9%）**，530 → 469 行；详情逐字进 `docs/todo/13-agent-panel.md`（21,069 B，106 行原文 + 109 个行级锚点）。
新机检 `check_todo_size.py` 已落地（死链 FAIL / 孤儿 WARN / 未索引化 WARN / `--selftest` PASS），实际跑 **PASS（0 死链，9 个未索引化 WARN = 尚未迁移的 §0/§1/§2/§3/§6/§7/§9/§11/§15，属预期）**。

## 1. 实测体积

| 指标 | 前 | 后 | 差 |
| --- | --- | --- | --- |
| `docs/todo.md` | 65,445 B / 530 行 | **54,382 B / 469 行** | **−11,063 B / −61 行** |
| §13 块 | 18,630 B | 7,267 B | −11,363 B |
| 附件 `docs/todo/13-agent-panel.md` | — | 21,069 B | 新增（含原文逐字 + 锚点） |
| 预算 | 64 KB | 64 KB（**Batch A+B 实测后按人批准改 56 KB**） | 余量 9,436 B |

`git diff --numstat`：todo **+? / −?**（见报告末复跑）；附件新增；docs-management +7 行；3 处 design 引用修改。

## 2. 迁移做法（机械搬迁，不丢内容）

1. 解析原 §13：标题/引言注记/107 行表（实际 **106 行**：AG01–AG108，缺号正常）/表后注记；
2. **原文逐字**写入附件 `## 原文（逐字，自 docs/todo.md §13 搬迁）`，前部加 109 个 `<a id="agXX">` 行级锚点（+`#archived/#voided/#notes`）；
3. todo §13 重写为索引：标题 + 统计摘要 + **52 条活跃行**（ID/主题/状态/`[详](todo/13-agent-panel.md#agxx)`）+ **2 条合并行**（27 条 ✅→§10.5、27 条 ⛔）+ 注记指针；
4. **校验**（脚本断言，迁移脚本内置）：
   - 原文每一非空行都能在附件中**逐字找到**（106 行/全部段落通过）；
   - 原文**长行（>80B）不再出现在 todo**（无双事实源）；
   - 所有 55 个详情链接的锚点在附件中存在（0 缺失）。

## 3. 新机检（`scripts/check_todo_size.py`）

保留原检查（体积/≥20 空格/单元格 ≤200B+基线）并新增：

| 检查 | 级别 | 实现 |
| --- | --- | --- |
| 相对链接必须存在（支持 `docs/` 与仓库根双基解析） | **FAIL** | 33+ 链接实测 0 死链；并修掉一处**存量坏链** `../../AGENTS.md` → `../AGENTS.md` |
| 附件锚点存在（`docs/todo/**.md#anchor` 须有 `<a id>`） | **FAIL** | 55 链接 / 109 锚点，0 缺失 |
| `docs/todo/*.md` 必须被 todo 引用 | **WARN** | 当前 1 个附件（README 除外），0 孤儿 |
| 某节无链接且 >400B（疑似未索引化） | **WARN** | 当前 9 个（待 Batch C） |
| `--selftest`：正常/死链/孤儿 三 fixture | 必红/必绿 | **SELFTEST PASS**（死链→FAIL、孤儿→WARN、正常→PASS） |

## 4. 文档同步

- **`docs/conventions/docs-management.md`**：
  1. §1 原则 2 补充：`todo.md` 详情附件统一放 `docs/todo/`；
  2. §4.1 目录登记表新增 `docs/todo/`（2026-10-26）；
  3. §4.2 新增规则 5（索引化/禁双事实源）与规则 6（死链 FAIL/孤儿 WARN/**引用禁止行号，用 §-锚点或任务 ID**）；
  4. 预算记录追加：Batch A 实测数字 + **Batch A+B 后 64→56 KB（人批准）**。
- **`docs/todo/README.md`** 新建：目录用途 + 6 条规则 + 现役文件表。
- **todo.md 顶部**新增索引化声明（索引只留 标题/状态/摘要/链接；引用禁行号）。

## 5. 3 处（实际 4 处）`todo.md:<行号>` 引用修正（Lead 授权）

| 文件:行 | 改前 | 改后 |
| --- | --- | --- |
| `design/deepseek-harness-integration.md:44` | `[todo.md:152](../todo.md)` | `[todo.md §11](../todo.md)` |
| `design/deepseek-harness-integration.md:48` | `[todo.md:151](../todo.md) V06` | `[todo.md §9 V06](../todo.md)` |
| `design/deepseek-harness-integration.md:203` | 表格「满足 `todo.md:152`」 | 「满足 `todo.md §11`」（同类，顺手修） |
| `design/dsh-agent-port.md:1156` | `docs/todo.md:265` | `docs/todo.md §13 AG07` |
| `design/export-html-draft.md:9` | `todo.md:203 原始需求` | `todo.md §11 原始需求` |

> 全仓复扫：仅剩 `design/documentation-changelog.md:213` 一处历史变更记录里的行号（**历史记录不改写**，已登记）。

## 6. 残留与预期

- **9 个"未索引化" WARN**：§0/§1/§2/§3/§6/§7/§9/§11/§15 尚未迁移（Batch B/C 处理），不是死链。
- **预算仍 64 KB**：Batch B 完成后再按实测改 56 KB（人已批 A+B 后调整）。
- §13 附件内保留原 `## 13.` 标题（逐字迁移的副作用；阅读无碍）。

## 7. 复核/复跑

```powershell
python scripts/check_todo_size.py --selftest     # SELFTEST PASS
python scripts/check_todo_size.py                # PASS 54,382 B / 469 行；0 死链；WARN=9
$env:PYTHONIOENCODING='utf-8'; python scripts/agent/team_audit.py   # FAIL=0
node scripts/i18n_selftest.js                    # PASS
python -m pytest -q tests                        # 1516 passed
git diff --numstat -- docs/todo.md docs/todo docs/conventions/docs-management.md
```

---

## 8. Batch B（§12 施工总表）—— 已完成

- 迁移对象：§12 知识库与维护机制·施工总表（原文 6,349 B / 61 行；表格活跃行 7：B2/B3/B6/B7/B8/C4/E3）。
- 附件：`docs/todo/12-build-table.md` = **7,322 B**（原文逐字 + 7 个行级锚点 + 8 个节区锚点 `#intro/#a/#d/#f/#g/#h/#verify/#residual`）。
- todo §12 索引：标题 + 摘要 + 7 行索引表 + 节区注记指针行（A/D/F 收口、G 归档、H 待裁决、验证机制外移 → 仍指向原 design 文档，不复制）。
- **实测**：`todo.md` 54,557 → **50,066 B**（−4,491 B，−8.2%），469 → 426 行。
- **A+B 累计**：65,445 → **50,066 B**（**−15,379 B，−23.5%**）。
- 不丢内容校验：原文每非空行在附件逐字可定位（通过）；原文长行（>80B）已不在 todo（通过）；7 个行级锚点全部存在。
- **预算调整**：`scripts/check_todo_size.py` `MAX_BYTES 64 KB → 56 KB` 已生效（A+B 实测 50,066 B，余量 7,270 B；2026-10-26 人批准，记录已写入 docs-management §4.2）。
- 同步：`docs/todo/README.md` 现役文件表新增 §12 附件行。

## 9. 关闭条件对照（task-165）

| 条件 | 状态 |
| --- | --- |
| 方案先报 Lead 批准 | ✅ 2026-10-26 批准（方案 A + 行级锚点混合；附 4 项裁决） |
| 试点迁移 ≥2 大项 + 实测字节下降 | ✅ §13（−11,063 B）+ §12（−4,491 B），合计 −15,379 B |
| 新机检可跑 + 必红 fixture | ✅ `--selftest` PASS（死链→FAIL、孤儿→WARN、正常→PASS） |
| `check_todo_size.py` 调整后 PASS | ✅ 56 KB 预算，PASS 50,066 B / 426 行 |
| 文档索引同步 | ✅ docs-management（目录登记 + §4.2 规则 5/6 + 预算记录）+ docs/todo/README |
| pytest / i18n / audit | ✅ pytest 1516 passed；i18n PASS；audit FAIL=0 |
| 报告 | ✅ 本文件 |
