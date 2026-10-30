# steward 第十一轮审计（r11）—— task-251 s2_cross_repo 实现后重签

> **触发**：task-251 改 `scripts/agent/team_audit.py`（`silent_failure` 支持跨仓解析 + selftest），
> 该文件属 `STEWARD_STANDARDS` 且 freeze 有 tooling 记录 ⇒ 收据/冻结同时过期（设计行为）。
> **处置**：① refreeze 更新 tooling sha（顺带消 dq5 tooling WARN）；② 重读 5 标准并签 r11。
> **审计者**：steward；**时间**：2026-10-30T11:4x+08:00；**git base**：`e3e9e8dc`（本票改动尚未提交）

## 1. 重读标准（sha256 = LF 归一化内容 sha）

| # | 标准 | sha256 |
|---|---|---|
| 1 | AGENTS.md | `6c87fe55077c4a73…`（未变） |
| 2 | docs/guides/lead-dispatch-rules.md | `3df918b12349a204…`（未变） |
| 3 | docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…`（未变） |
| 4 | **scripts/agent/team_audit.py** | **`8bb64e31649f7078…`（task-251 改动后）** |
| 5 | scripts/agent/prompt_drift_check.py | `75a2563c40e44728…`（未变） |

## 2. Refreeze（tooling 项，消 dq5 WARN）

- 前：`4874493dfac350a8…` → 后：**`8bb64e31649f7078…`**
- `standards_updated` 追加第 7 条（index 6）：`by=steward`、`reason=task-251 s2_cross_repo 机检实现`、
  `changed=[{path: scripts/agent/team_audit.py, from, to, role: 机检实现, tooling: true}]`、`commit=null`（尚未提交）。
- `freeze_refreeze.py --check`：**5/5 MATCH（exit=0）** ⇒ **dq5 无 tooling WARN**（满足 Lead 条件 c）。

## 3. task-251 实现摘要（详细见 task-251 证据）

- `team_audit.py::_cross_repo_target()`：`dsh:<rel>` → `$env:DSH_TEAM_CROSS_REPO_ROOT/<rel>`（默认 `D:\deepseek-harness`）；
  绝对路径仅 fallback；解析顺序：Memoria 相对路径 → `dsh:` → 绝对路径。
- `check_silent_failure`：S2 与 `corrects.new` 都接跨仓；跨仓存在 ⇒ PASS + **INFO（cross_repo=<dsh|absolute>）**；
  汇总给 **INFO `cross_repo_passes=N`**（可见，不静默）；两者皆无 ⇒ FAIL。
- selftest 三条 fixture（先证红/白/回归）：
  - a：跨仓根指空 ⇒ `dsh:` 行 **FAIL**；根指向真实 ⇒ **PASS + INFO cross_repo_passes=1**（先证红再绿）；
  - b：`dsh:` 与本地皆无 ⇒ **FAIL**；
  - c：本地路径存在 ⇒ PASS 且无 cross INFO（回归）。
- 原始输出：`artifacts/agent/verify/steward/task-251/{selftest.txt,probe-output.txt}`。

## 4. 门禁结果（r11 实跑）

- `team_audit.py --json`：**FAIL=1**（WARN=56 / INFO=31）——**仅 `l1_task_before_spawn`**（历史存量，按裁定保持）。
- `steward_self_audit`：**INFO（5/5 匹配）**。
- `--determinism`：**PASS**（sha `6f20b4a8…`，compared_findings=88）。
- `prompt_drift_check.py`：exit=0 / status=ok / FAIL=0 / NOT_RUN=0。
- `freeze_refreeze.py --check`：**exit=0（全 MATCH）**。
- `team_audit.py --selftest`：**PASS**（含 task-251 三条 fixture）。
- 回归：`dispatch_log.py --selftest` PASS；pytest 见报告（1524 基线，本票未改产品代码）。

## 5. r10 → r11 有效性

r10 对 AGENTS/rules/lessons/prompt_drift 仍匹配，但 `team_audit.py` 由 `4874493d…`→`8bb64e31…` ⇒ **r10 按 B3 失效，r11 取代**。
本票改动尚未提交；提交字节不变则 r11 持续有效。

## blind_spots

1. 跨仓解析只验证"文件存在"，不验证内容/生成时间（跨仓证据的强验证仍需人工/清单 sha256 对照）；
2. 绝对路径 fallback 不可移植（已在 INFO 文案标注；本仓当前 8 条更正记录均指向本地清单，未触发 absolute 分支）；
3. DSH 根默认硬编码在常量（可用 env 覆盖），若未来 DSH 仓迁移需更新默认值/文档；
4. 未纳入其它跨仓证据类型（evidence[] 字段）——本票只覆盖 `report`/`corrects.new`。

## 复跑

```powershell
python scripts/agent/team_audit.py --json
python scripts/agent/team_audit.py --selftest
python scripts/agent/team_audit.py --determinism
python scripts/agent/freeze_refreeze.py --check
```
