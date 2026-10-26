# steward 第六轮审计（r6）—— task-158 后重签

> **触发**：prompt-owner 在 task-158 修复了我审计出的 PD-1..PD-5，改了 `STEWARD_STANDARDS` 里两项：
> `scripts/agent/team_audit.py`（d8f6a7d7→beec3c71）、`scripts/agent/prompt_drift_check.py`（6cbc9f86→75a2563c）
> ⇒ r5 收据过期（`steward_self_audit` FAIL=2，设计行为）。
> **处置**：重读 5 标准 → 写 r6 新收据（历史 r2/r3/r4/r5 原样不动）。
> **审计者**：steward；**时间**：2026-10-26T09:1x+08:00；**git base**：`270e4796`
> **注意**：两个标准文件是**未提交工作区修改**（task-158），r6 收据绑定 worktree sha。

## 1. 重读标准（sha256 = LF 归一化内容 sha）

| # | 标准 | sha256 |
|---|---|---|
| 1 | AGENTS.md | `6c87fe55077c4a73…`（未变） |
| 2 | docs/guides/lead-dispatch-rules.md | `488d7ebd78c917e2…`（未变） |
| 3 | docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…`（未变） |
| 4 | **scripts/agent/team_audit.py** | `beec3c714c8440ee…`（**task-158**：NOT_RUN 接入门禁） |
| 5 | **scripts/agent/prompt_drift_check.py** | `75a2563c40e44728…`（**task-158**：NOT_RUN 语义 + exit 0/1/2/3 + PD 修复） |

## 2. 本次重读确认到的语义变化（不是走过场）

### 2.1 `prompt_drift_check.py`
- **NOT_RUN 语义**：新增 `Ctx.not_run()`；所有"输入不可读/依赖缺失/检查自身异常"路径产出 `severity=NOT_RUN`
  finding（不再 WARN/静默）；`_SEV_ORDER = FAIL < NOT_RUN < WARN < INFO`。
- **退出码**：0=全部执行且无 FAIL；1=有 FAIL；**2=有检查未执行（NOT_RUN）**；3=用法错误；
  `--json` 的 `summary.status ∈ {ok,fail,not_run}` 与退出码一一对应。
- **PD-1..PD-5 修复实现**（逐条核对）：
  - PD-1：NOT_RUN + exit 2 + team_audit 判 FAIL（见 §2.2）；
  - PD-2：C2 点分字段改为**每段**校验；
  - PD-3：隐藏分发扫描不再跳过 `kb_agent/ui.py/build.py`，改扫 `src/memoria/packaging/scripts` 的 py/js/mjs，命中 `HIDDEN_SCAN_REVIEWED` 只记 INFO（含理由）；
  - PD-4：孤儿检测 `rglob` 递归（排除 `__pycache__/.pyc/隐藏项`）；
  - PD-5：`_qualifier_near`（PROXIMITY_CHARS=24，中间不得夹句读分隔）替代"同行 includes"。

### 2.2 `team_audit.py::check_prompt_drift`
- 接受 `returncode ∈ {0,1,2}`；`summary.status` 必须 ∈ {ok,fail,not_run} 且 **status↔exit 一致**；
- `status=not_run` 或 `not_run_count>0` ⇒ **FAIL**（"跳过 ≠ 通过"）；
- `findings[].severity=NOT_RUN` ⇒ FAIL；
- `summary.FAIL` 必须与 findings 中 FAIL 计数一致（防门禁自相矛盾）。
- 我实测：`prompt_drift_check.py --json` → **exit 0 / status=ok / FAIL=0 / NOT_RUN=0 / INFO=6**；
  `--selftest` → **exit 0（19 fixtures，prompt-owner 报告）**。

## 3. r6 运行结果

- `team_audit.py --json`：**FAIL=0**（r5 收据过期的两条 FAIL 已消除），`steward_self_audit=INFO`（5/5 匹配）。
- `--determinism`：PASS（sha `bb76a1a7…`，compared_findings=83）。
- `freeze_refreeze.py --check`：exit=1（DRIFT 1：`team_audit.py` [机检实现]，记录 @d8f6a7d7… → 当前 @beec3c71…），
  属 **tooling 项**（dq5 只 WARN）；`--apply` exit=4（待 L12 批准，不写盘）——本轮已把该输出记入收据 `freeze_refreeze_check` 字段。
- pytest 复跑 **1485 passed**（68s）；prompt_drift exit 0 / status=ok / NOT_RUN=0；node/i18n 由 prompt-owner 报告全 PASS。

## 4. 本轮 findings 处理

- **PD-1..PD-5 已 mechanized**：SF-042..046（supersede SF-037..041，disposition=mechanized，cite 实现位置）；
- **SF-047（裁定）**：`scripts/agent/freeze_refreeze.py` **暂不纳入** `STEWARD_STANDARDS`：
  它是冻结物维护工具（非审计标准/门禁），且 `--apply` 未实现、现在纳入需改 team_audit.py 再触发一次重签（自指循环）；
  待 L12 批准 + `--apply` 落地后，与「freeze 更新流程」一起纳入（届时 6 项）。当前以收据 `freeze_refreeze_check` 字段留痕即可。

## blind_spots

1. **未提交工作区**：task-158 两文件仍 `M`（未 commit），r6 绑定 worktree sha；若 commit 前再改，r6 会按设计过期。
2. **只重读接口/语义**，未逐行复核 `prompt_drift_check.py` 全部 C1–C5 判据（PD 修复已用探针复核，其余沿用上一轮审计结论）。
3. **freeze 漂移属 tooling**：dq5 对 `team_audit.py` 只 WARN（R-R6 裁决），不是 FAIL；真正 refreeze 待 L12。
4. org.md 只读 §2.3/§2.6，§13 台账未逐条复核。
5. 产品代码/性能不在 steward 域。

## 复跑

```powershell
python scripts/agent/team_audit.py --json
python scripts/agent/team_audit.py --determinism
python scripts/agent/prompt_drift_check.py --json
python scripts/agent/freeze_refreeze.py --check
```
