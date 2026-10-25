# task-110 证据：r4 重签现场（2026-10-26）

> 本文件是 task-110（SF-025：收据 sha 跨平台不可移植）的**现场证据**，由 Lead 在 2026-10-26 要求
> "把这次重签与 task-110 的关系记进证据"。**本轮不修 task-110**，只留证。

## 1. 现场事实

- r4 收据：`team/steward/audit-2026-10-26-r4/standards_read.json`（round=r4，git_base=f2a415c5）。
- 触发：`prompt-owner` 在 task-152 改 `scripts/agent/team_audit.py`（+88/−1）+ `prompt_drift_check.py`（+281/−14），
  r3 收据中 `team_audit.py` 的 sha 过期 ⇒ `steward_self_audit` FAIL=1（设计行为）。
- 重签后：`team_audit.py --json` **FAIL=0**（WARN 53 / INFO 28），`--determinism` PASS（compared_findings=81）。
- 两个标准文件本轮是**未提交工作区修改**（`git status: M`），r4 绑定 worktree sha：
  - `scripts/agent/team_audit.py` = `4c697128255fc6ed…`
  - `scripts/agent/prompt_drift_check.py` = `6cbc9f8687e3a4d8…`

## 2. task-110/SF-025 的复核结论（**问题仍在**）

`steward_self_audit` 当前读取校验代码是：

```python
current = hashlib.sha256(path.read_bytes()).hexdigest()   # 工作区原始字节
```

⇒ **收据口径仍然是"工作区原始字节 sha"，不是 LF 归一化**。本轮之所以没红，是因为本机工作树文件恰好是 LF
（`raw == LF`，五个标准均相同），**不是问题被修复**。

**跨平台推论**（沿用 SF-025 定性）：Linux CI 或 `core.autocrlf=false` 的克隆 checkout 出 LF，
下列标准（历史上是 `agent-team-lessons.md`，本轮全部标准均为 LF）在收货为 CRLF 的工作区上会是 raw≠LF ⇒
收据 MISMATCH ⇒ 假红，而标准其实没变。

**修复要求（写进 task-110，不要本轮做）**：
1. `team_audit.py` 增加 `content_sha256(path)`（`\r\n → \n` 后算 sha256，BOM 处理写进注释）；
2. **写入端与读取端同时改**：`steward_self_audit` 的比对用它，新收据的写入也用它；
3. 旧收据（r2/r3/r4）**不手工改**；修复后跑 **r5** 新收据；
4. `--sha-explain <path>` 输出原始 / LF 归一化 / git blob 三个 sha（便于现场对账）。

## 3. 本轮附带发现（SF-031，已入台账）

`prompt_drift_check.py` 已成为 `team_audit` 门禁的一部分（第 12 类检查 `prompt_drift` 子进程调用它），
但 `STEWARD_STANDARDS` 仍只有 4 项 ⇒ 该脚本单独变更时**收据不会过期**（覆盖缺口）。
r4 我**手工**把它作为第 5 项写进收据并记录真实 sha（`6cbc9f86…`），但机检不校验它。
建议（需 Lead 批，改 `team_audit.py` 写域）：把 `STEWARD_STANDARDS` 扩为 5 项，并同步 org.md §2.6 B3 的标准清单。

## 4. 复跑

```powershell
python scripts/agent/team_audit.py --json            # 期望 FAIL=0
python scripts/agent/team_audit.py --determinism     # 期望 PASS
python scripts/agent/prompt_drift_check.py --json    # 期望 exit=0 FAIL=0
```
