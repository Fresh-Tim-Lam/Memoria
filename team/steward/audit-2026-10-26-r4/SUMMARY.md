# steward 第四轮审计（r4）—— task-152 后重签收据

> **触发**：`prompt-owner` 在 task-152 接入 `prompt_drift` 门禁并修 cp1252 崩溃 bug，`team_audit.py` 变更 ⇒
> r3 收据的 `scripts/agent/team_audit.py` sha 过期 ⇒ `steward_self_audit` 按设计 FAIL=1。
> **处置**：**重读标准**（不是改旧收据），写 r4 新收据。**审计者**：steward；**时间**：2026-10-26T00:0x+08:00
> **git base**：`f2a415c5`；**注意**：本轮两个标准是**未提交工作区修改**（task-152），r4 收据绑定 worktree sha。

## 1. 重读清单（sha256 为**原始工作区字节** —— 当前机检口径）

| # | 标准 | sha256 | 说明 |
|---|---|---|---|
| 1 | AGENTS.md | `6c87fe55077c4a73…` | 未变 |
| 2 | docs/guides/lead-dispatch-rules.md | `488d7ebd78c917e2…` | 未变 |
| 3 | docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…` | 未变 |
| 4 | scripts/agent/team_audit.py | `4c697128255fc6ed…` | **task-152 变更（+88/−1）** |
| 5 | scripts/agent/prompt_drift_check.py | `6cbc9f8687e3a4d8…` | **本轮新增纳入重读**（它已成为门禁的一部分） |

> ⚠ 第 4/5 项是**未提交工作区修改**（`git status: M`），r4 绑定的是 worktree sha；Lead 提交后若字节不变则收据仍有效。

## 2. 本次重读的具体变化（不是走过场）

### 2.1 `team_audit.py`（+88/−1）
- **cp1252 崩溃修复**：`_git_head_commit_time` 与 selftest `_git_do` 的 `subprocess.run` 增加
  `encoding="utf-8", errors="replace"` —— 原症状：Windows 默认 cp1252 解码非 ASCII 输出 ⇒ `UnicodeDecodeError`
  ⇒ 上层拿到 `None` ⇒ 整道闸门进程死亡（"闸门自己崩了"比"检查失败"更糟）。
- **新增第 12 类检查 `check_prompt_drift`**（task-152）：子进程跑 `prompt_drift_check.py --json`，**fail-closed**：
  脚本缺失 / 子进程异常 / exit 不在 {0,1} / stdout 为空 / JSON 不可解析 / `summary.FAIL` 非整数 /
  `exit==0 但 summary.FAIL>0`（自相矛盾）/ 未知 severity ⇒ 一律 FAIL，**绝不静默跳过**；
  非 Memoria 仓库（无 `kb_agent.py`）⇒ INFO "不适用"（保护 selftest fixture）。
- 已注册进 `run_checks`，与既有检查同级排序。

### 2.2 `prompt_drift_check.py`（+281/−14）
- 检查本体仍是 C1–C5（distribution_integrity / symbol_reference / forbidden_syntax / version_stamp / staleness），**exit 语义**：
  0=无 FAIL、1=有 FAIL、2=用法错误；`--selftest` 每条检查必红 fixture。
- **新增重签流程**（本轮读到的关键变化）：`--recheck-deps`（只读清单：依赖记录值 vs 当前 sha12 + git 证据 + 要复核的小节 + 精确命令）、
  `--resign <文件> --dep ... --note ≥10字`（**拒绝跳过复核直接改指纹**；`--dep` 必须逐条列全，漏列拒绝重签；
  重签写 append-only `artifacts/agent/verify/todo/prompt-drift-recheck-log.jsonl`；重签后立即重跑检查）。
- cp1252 修复：`_git_commit_date` 同样加 `encoding="utf-8", errors="replace"`；
  `_write` 改 `newline="\n"`（防 Windows 把整份提示词换行改掉）。

### 2.3 独立核验 `prompt_drift_check.py`（作为标准的一部分）
```
python scripts/agent/prompt_drift_check.py --json
→ exit=0；summary={'findings': 4, 'FAIL': 0, 'WARN': 0, 'INFO': 4}
→ 4 条 INFO 均为 symbol_reference 的"未归类 token"（不静默放过、也不误红）
```
与 `team_audit` 的 `[INFO] prompt_drift` 输出一致（4 条），无自相矛盾。

## 3. r4 运行结果

- `team_audit.py --json`：**FAIL=0**（r4 前唯一 FAIL 是 steward_self_audit 的收据过期；重签后消除），
  基线 **WARN 53 / INFO 27**（含 prompt_drift 4 INFO、deliberation_quality 宽限 WARN 等，无新增 FAIL）。
- `--determinism`：**PASS**（sha `43c475c1…`，compared_findings=81）。
- `steward_self_audit`：r4 收据生效后 **INFO**（4/4 标准 sha 匹配；第 5 项 prompt_drift_check.py 已写入但**不被机检校验**，见 §4）。

## 4. 与 task-110（SF-025）的关系（Lead 特别问的）

1. **当前口径确认**：`steward_self_audit` 比对的是 `hashlib.sha256(path.read_bytes())` = **工作区原始字节**，
   不是 LF 归一化。**task-110/SF-025 的问题仍然存在**（跨平台 CRLF 克隆会假红），本轮只是因为本机工作树恰好是 LF，
   `raw == LF` 才没暴露差异。
2. **r4 收据记录的是 raw sha**（为通过当前机检不得不用旧口径）。task-110 修复时必须**同时改写入端与读取端**为
   `content_sha256`（LF 归一化），再跑 **r5** 新收据；**不得改 r4/历史收据**。
3. **本轮额外发现（SF-031）**：`prompt_drift_check.py` 已进门禁，但 `STEWARD_STANDARDS` 仍是 4 项 ⇒
   它单独变更时**收据不会过期**（覆盖缺口）。r4 我**手工**把它作为第 5 项写进收据并记录 sha，但机检不校验；
   建议把 `STEWARD_STANDARDS` 扩为 5 项（需 `team_audit.py` 写域审批，本轮不改）。
4. 以上两点已作为 **SF-031（proposal）** 与 **SF-032（open，task-110 证据）** 追加进 `team/steward/findings.jsonl`；
   r4 快照按 append-only 更正投影生成（31 条，修掉 r3 快照里 SF-030 重复的问题）。

## blind_spots（本轮未审计什么）

1. **未审计 task-152 的实现语义正确性**：我只确认"门禁接线 fail-closed + 独立跑 FAIL=0 + 收据 sha 真实"，
   没有逐条复核 `prompt_drift_check.py` 的 C1–C5 判据是否与提示词语义一致（属 prompt-owner/评审域）。
2. **未提交工作区状态**：r4 绑定 worktree sha；若 Lead 提交时还改这两个文件，r4 会按设计过期（需 r5）。
3. **工作树 LF 假象**：本机 raw==LF ⇒ 无法在本轮暴露 task-110 的 CRLF 不可移植性；该项以静态代码证据记录（SF-032）。
4. **其余标准未逐条复核**：org.md 只读 §2.3/§2.6，§13 台账未逐条。
5. **产品代码/性能**不在 steward 域（metrics-baseline / 各 Owner 负责）。

## 复跑

```powershell
python scripts/agent/team_audit.py --json
python scripts/agent/team_audit.py --determinism
python scripts/agent/prompt_drift_check.py --json
```
