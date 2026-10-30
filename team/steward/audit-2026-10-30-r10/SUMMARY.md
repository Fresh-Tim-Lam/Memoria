# steward 第十轮审计（r10）—— refreeze §V-frontend-1/2 后重签

> **触发**：Lead 在 `lead-dispatch-rules.md` 追加 **§V-frontend-1**（前端效果验证强制）/ **§V-frontend-2**（三次回归即停手），
> rules sha 变化 ⇒ 冻结收据与 r9 收据同时过期（`dq5` + `steward_self_audit` FAIL，设计行为）。
> **处置**：① 按 Lead 委托 **refreeze**（人工更新 freeze-v2，追加 `standards_updated[5]`，因 `--apply` 仍待 L12）；② 重读 5 标准并签 r10。
> **审计者**：steward；**时间**：2026-10-30T11:3x+08:00；**git base**：`112a70cb`（rules 的改动 **仍在工作区、未提交**）

## 1. 重读标准（sha256 = LF 归一化内容 sha）

| # | 标准 | sha256 |
|---|---|---|
| 1 | AGENTS.md | `6c87fe55077c4a73…`（未变） |
| 2 | **docs/guides/lead-dispatch-rules.md** | **`3df918b12349a204…`（新增 §V-frontend-1/2）** |
| 3 | docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…`（未变） |
| 4 | scripts/agent/team_audit.py | `4874493dfac350a8…`（未变；SF-052 已提交） |
| 5 | scripts/agent/prompt_drift_check.py | `75a2563c40e44728…`（未变） |

## 2. Refreeze 记录（freeze-v2）

- `standards[1].sha256_lf`：`61cb2169d2bd…` → **`3df918b12349a204…`**
- `standards_updated` 追加第 6 条（index 5）：`by=steward`、`reason=Lead 追加 §V-frontend-1/2`、`commit=null`（工作区未提交）、
  `changed=[{path, from, to}]`、`rule_ref=lead-dispatch-rules §V-frontend-1/§V-frontend-2`，
  `note` 写明"提交字节不变时 r10 有效；若提交前再改需 r11；`--apply` 仍待 L12"。
- `freeze_refreeze.py --check`：rules **MATCH**；仅 `team_audit.py` tooling DRIFT（记录 beec3c71 → 当前 4874493d），dq5 只 WARN。
- `deliberation_quality dq5`：**PASS**。

## 3. 门禁结果（r10 实跑）

- `team_audit.py --json`：**FAIL=9**（WARN=57 / INFO=30）——**均为已知存量，非本票引入**（见 §4）。
- `steward_self_audit`：**INFO（5/5 匹配）**。
- `--determinism`：**PASS**（sha `db46777e…`，compared_findings=96）。
- `prompt_drift_check.py`：exit=0 / status=ok / FAIL=0 / NOT_RUN=0 / INFO=6。
- `check_ui_contract.py`：exit=1（**new_fail=20**，外部 UI 改动所致；仍观察期、不纳入 STEWARD_STANDARDS）。
- `test_guard_check.py`：exit=0（WARN=6）。
- pytest：见报告（1524 基线；本票未改产品代码）。

## 4. FAIL=9 分类（全部为已知存量，按 Lead 裁定不塞进本票）

| 检查 | 条数 | 说明/处置 |
|---|---|---|
| `l1_task_before_spawn` | 1 条（含 11 个 spawn） | SF-052 检查上线前的历史存量（样本 retrieval-researcher）；**保持 FAIL、不回填**；已写入 `team-protocols.md` P-06 + 附录 D；清洗另开票 |
| `silent_failure S2` | 7 条 | done 记录引用产物不存在（历史路径迁移）；另开票清理 |
| `deliberation_quality dq6` | 1 条 | 1 个 pycache 产物未 git 跟踪；另开票清理 |

> `dq5` 与 `steward_self_audit` 已由本轮解决，不在上表。

## 5. 配套文档改动（本票后续第 2/3 件）

- `docs/guides/README.md`：Guides 索引新增 `team-protocols.md` 一行（登记类，Lead 授权）。
- `docs/guides/team-protocols.md`：
  - 附录 A「发版三查」行补 **2026-10-30 Lead 裁定**：等 `release-manager` 有活跃任务时再评估能否机检，现在不升格；
  - P-06 增加「已知存量（不回填）」；
  - P-08 依据行对齐 §V-frontend-1/2 的**实际小节标题**（`V-frontend-1 前端效果验证（2026-10-29，强制）` / `V-frontend-2 三次回归即停止打补丁（2026-10-29，强制）`）；
  - 新增附录 D「已知存量（FAIL 保持、不回填；清洗另开票）」。

## 6. r9 → r10 有效性

r9 对 `team_audit.py`/`prompt_drift`/`AGENTS`/`lessons` 四项仍匹配，但 **rules 由 61cb2169→3df918b1 ⇒ r9 整体失效，r10 取代**。
**注意**：rules 的 §V-frontend-1/2 改动仍是**工作区未提交**（Lead 的改动）；r10 绑定其 worktree sha，提交字节不变则持续有效。

## blind_spots

1. rules 改动未提交：若 Lead 提交前再改，需 r11；
2. `check_ui_contract` 当前 new_fail=20（外部 UI 改动），观察期结束后需重新评估纳管；
3. 未审 §V-frontend-1/2 内容本身（Lead 条款，本轮只做 refreeze/重签；如需审计另开）；
4. org.md §13 台账未逐条复核；产品代码/性能不在 steward 域。

## 复跑

```powershell
python scripts/agent/team_audit.py --json
python scripts/agent/team_audit.py --determinism
python scripts/agent/freeze_refreeze.py --check
python scripts/agent/prompt_drift_check.py --json
```
