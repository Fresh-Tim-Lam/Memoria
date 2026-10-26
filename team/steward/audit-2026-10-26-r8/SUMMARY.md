# steward 第八轮审计（r8）—— B-danger-1 v2 落盘后重签

> **触发**：Lead `56aa1256` 落 B-danger-1 v2（rules sha 716712d4→**169c15ed**）⇒ r7 收据过期（`steward_self_audit` FAIL=1，设计行为）。
> **处置**：重读 5 标准 → r8 新收据（历史 r2–r7 原样不动）；同时审 v2 条款语义 + 给出"强制力标注"的机检化设计。
> **审计者**：steward；**时间**：2026-10-26T19:2x+08:00；**git base**：`56aa1256`

## 1. 重读标准（sha256 = LF 归一化内容 sha）

| # | 标准 | sha256 |
|---|---|---|
| 1 | AGENTS.md | `6c87fe55077c4a73…`（未变） |
| 2 | **docs/guides/lead-dispatch-rules.md** | **`169c15ed1f43f0e4…`（B-danger-1 v2）** |
| 3 | docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…`（未变） |
| 4 | **scripts/agent/team_audit.py** | **`4874493dfac350a8…`（SF-052：新增 l1_task_before_spawn；未提交工作区）** |
| 5 | scripts/agent/prompt_drift_check.py | `75a2563c40e44728…`（未变） |

## 2. v2 条款审计（Lead 问：落成条款后语义有没有变坏 / 独占条件(a)是否太严）

**总体：语义没有变坏，v1 的 5 条问题基本补齐**（共享定义/10 类禁止命令/对照实验/留证格式/R1 例外/强制力标注）。
以下 4 点需修或澄清（已记 SF-20261026-056）：
1. **"worktree 天然独占"过强**：linked worktree 只是一个目录，仍可能被两人共用 ⇒ 应写
   「独立 worktree **默认**独占，但路径必须唯一（成员+任务命名）；共享 worktree 不构成独占」。
   这同时影响工具拦截器：guard 应要求 worktree 路径带成员名，否则 deny 判定会放行"共享 worktree 内"的破坏性操作。
2. **独占条件 (a) 的双重条件**：**不算太严，但当前实际不可用**——`git status --porcelain -- <path>` 无法区分"谁"的改动，
   也看不到**编辑器里未保存的 buffer**；且 `exclusive_paths` 在 dispatch-log **尚无字段/校验**。
   ⇒ 建议明确写「(a) 在 dispatch-log 支持 `exclusive_paths` 前不可用，一律走 worktree」；
   **不要放宽条件**（放松=重新引入风险），正确做法是承认 (a) 暂不可用 + 用 worktree 兜底。
3. **§5 R1 例外未写"谁可执行"**：按 L2 应写「仅 Lead 执行或 Lead 在场批准」，并补「事后把差集核对结论写回 dispatch-log」。
4. **位置仍在"变更记录"之后**（line 250，v1 提案 ⑤ 未落）：可发现性差；建议移到 §1 附近或新增 §7.5。
另：v2 把"看起来没人改不构成独占"写进去了 👍（这是 v1 最容易被人绕的一句）。

## 3. "强制力诚实标注"是否足够 + 机检设计（Lead 问）

**足够作为条款，但不够作为长期保障**：散文标注容易被人跳过，也容易在拦截器落地后忘记更新（条款里写了"落地后应更新"，但没人会检查）。
建议升级为**结构 marker + 门禁交叉核对**（已记 SF-20261026-057，proposal）：
```
在 B-danger-1 节写：
<!-- enforcement-status: not-enforced -->
或
<!-- enforcement-status: enforced@<interceptor-version> -->
```
新检查 `danger1_enforcement`（team_audit）：
- marker 缺失 ⇒ **FAIL**（防止悄悄删掉诚实标注）；
- `not-enforced` 且检测到拦截器存在（配置/env/版本文件，如 `.dsh/team/workspace-guard.json`）⇒ **WARN**「拦截器已存在但条款仍称未保护（可能过期）」；
- `enforced@v` ⇒ 要求拦截器版本一致 + guard selftest 证据（如 `artifacts/agent/verify/workspace-guard/selftest.json` 且 pass），否则 **FAIL**。
这样"不得宣称已有机检保护"从散文变成**可机检的声明**；校验的是 marker↔现实一致性，不是措辞（避免脆弱的自然语言检查）。
**实现成本**：一个检查 + 必红 fixture（marker 缺失/版本不符/证据缺失/拦截器已存在但标未保护）。
**注意**：改 `team_audit.py` 会再触发一次重签（r9）⇒ 建议**随拦截器 v1 一起落**，一次重签。

## 4. 当前门禁状态（r8 实跑）

- `team_audit.py --json`：**FAIL=0**（WARN=56 / INFO=30）。
- `steward_self_audit`：**INFO（5/5 匹配）**——r8 已重签。
- `deliberation_quality dq5`：**PASS**（Lead 已在 `f03bbd44` 重签 freeze：rules=169c15ed 与磁盘一致；只剩 `team_audit.py` 的 **tooling WARN**，属 R-R6 裁决的预期行为）。
- `--determinism`：**PASS**（sha `ee6b389d…`，compared_findings=86）。
- `prompt_drift_check.py`：exit=0 / status=ok / FAIL=0 / NOT_RUN=0 / INFO=6。
- `check_ui_contract.py`：exit=0（new_fail=0；仍不纳入标准，观察期计时中）。
- `test_guard_check.py`：exit=0（FAIL=0 / WARN=6）。
- `freeze_refreeze.py --check`：exit=1，DRIFT=1（`team_audit.py`，tooling）—— 预期；`--apply` 仍待 L12。

## 5. r8 的一个特殊之处：绑定了 SF-052 的**未提交工作区**字节

签名时 `team_audit.py` 正处于 SF-052 实现（`l1_task_before_spawn`）的未提交状态：
- `scripts/agent/team_audit.py` = `4874493d…`（新增 21 类检查 + 3 条必红 fixture，已注册 run_checks，`--selftest` PASS）；
- `scripts/agent/dispatch_log.py` = `87d4eb03…`（`--task` 相关实现）。
我等到文件 **60s+ 稳定** + 实现完整（selftest 含 SF-052 fixture）后才签；若实现者提交时字节不变，r8 持续有效；
若提交前再改，按 B3 需要 r9（届时我会看到 disk sha 变化并重签，不会假装 r8 还有效）。
## blind_spots

1. 未验证"拦截器"实现细节（`exclusive_paths` 字段、worktree 归属判定）——属 DSH 插件侧；
2. 未审 `docs/conventions/ui-contract.md` C1–C7 判据语义；
3. v2 的"10 类命令"按文本核对了覆盖，但实现层正则是否等价需在 guard 实现时用 fixtures 验证；
4. org.md §13 台账未逐条复核；产品代码/性能不在 steward 域。

## 复跑

```powershell
python scripts/agent/team_audit.py --json
python scripts/agent/team_audit.py --determinism
python scripts/agent/prompt_drift_check.py --json
python scripts/agent/freeze_refreeze.py --check
```
