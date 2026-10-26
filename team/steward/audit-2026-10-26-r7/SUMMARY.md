# steward 第七轮审计（r7）—— B-danger-1 后重签 + 新增机检脚本纳管评估

> **触发**：Lead 在 `d658a395`/冻结重签 `69544f44` 中给 `docs/guides/lead-dispatch-rules.md` 新增 **B-danger-1**
> （禁止对共享工作区做 `git checkout --` / `git reset --hard`），rules 的 sha 变化 ⇒ r6 收据过期（`steward_self_audit` FAIL=1，设计行为）。
> **处置**：重读 5 标准 → r7 新收据（历史 r2–r6 原样不动）；同时审 B-danger-1 本身 + 两份新机检脚本的纳管问题。
> **审计者**：steward；**时间**：2026-10-26T18:5x+08:00；**git base**：`69544f44`

## 1. 重读标准（sha256 = LF 归一化内容 sha）

| # | 标准 | sha256 |
|---|---|---|
| 1 | AGENTS.md | `6c87fe55077c4a73…`（未变） |
| 2 | **docs/guides/lead-dispatch-rules.md** | **`716712d40314276f…`（新增 B-danger-1）** |
| 3 | docs/guides/agent-team-lessons.md | `f2f86b090d6e088a…`（未变） |
| 4 | scripts/agent/team_audit.py | `beec3c714c8440ee…`（未变） |
| 5 | scripts/agent/prompt_drift_check.py | `75a2563c40e44728…`（未变） |

## 2. B-danger-1 审计结论（我的规范，欢迎挑错）

**不重复、不冲突**：L2 管「R1 操作 Lead 亲跑」，L5 管「不可逆操作先给回滚方案」；B-danger-1 管「共享工作区的未提交改动」，
更严且同向，**没有与 L2/L5 矛盾**。方向正确（render-perf 事件确实是 R1 风险已实现）。
**但作为可执行规范有 5 个问题**（已记 SF-048）：
1. **命令清单不全**：只列 `git checkout -- <file>` / `git reset --hard`，未覆盖 `git restore`（现代等价）、
   `git clean -fd`、`git checkout .`、`git stash drop/clear`、`git apply -R` 等同样丢未提交改动的操作；
2. **无强制力**：`git checkout -- <file>` **不写 reflog**（只有 reset --hard 有），事后无法取证；team_audit 也无对应检查
   ⇒ 目前是"靠自觉"，与 L6/L10「工具强制 > 记忆」的立场不一致；
3. **"他人可见的共享工作区"未定义**（DSH 下全员共享 cwd；何时可视为独占？）；
4. **"留证据"未定义形式**（%TEMP% 副本的 file list/sha？%TEMP% 会被清理）；
5. **文档位置**：追加在"变更记录"之后（line 250），不在派发主流程/风险分级附近，可发现性差。
**建议**：扩命令清单 + 工具层拦截（agent-team 工具对 checkout/reset/restore/clean 做 deny 或要求 worktree 参数）+
定义共享工作区默认与 worktree 登记 + 规定"留证据"格式（worktree 路径 + 文件 sha 清单）+ 并入 §1/新增 §B 并更新变更记录。

## 3. 两份新机检脚本：**暂不纳入 STEWARD_STANDARDS，先独立跑一段**（SF-049）

| 脚本 | 当前基线（r7 实测） | 判断 |
|---|---|---|
| `scripts/check_ui_contract.py`（C1–C7） | **exit=1**：new_fail=2（`app.css:7904` 硬编码颜色、`app.css:7866` 圆角越档）、new_warn=3；baseline 210F/61W，fixed=2 | **不纳入**（现在接入会立刻让 team_audit 红） |
| `scripts/agent/test_guard_check.py`（测试断言粒度） | exit=0：FAIL=0、WARN=6（`over_symbol_count=6`、`long_count=13`、总 source asserts=404） | **不纳入**（尚未接入、且见下） |

理由：
1. **org B3-c 判据**是「被 team_audit 调用、且其变更会改变门禁结论」——两者当前都未被 team_audit 调用 ⇒ **不在必须纳入的范围**；
2. 接入前必须先满足 **B3-e 退出码契约**（见 §4）——现在两脚本都**不合规**；
3. `check_ui_contract` **当前是红的**（2 个 new FAIL）⇒ 现在接 team_audit 会立刻制造红；
4. `--update-baseline --force` 可放宽基线且无审计要求（SF-051）⇒ 先补"求改基线必须留 Decision/审计"。
**建议的纳管过渡**：独立跑 ≥2 周或 `new_fail` 归零 → 修 B3-e → 与 team_audit 接线 **同一次提交**里加入 `STEWARD_STANDARDS`（B3-c）→ 跑 rN 重签。
r7 收据的 `external_checks` 已记录两者当前基线结果（exit/counts/json 路径），作为纳入前的可审计证据（不此刻扩标准）。

## 4. 退出码契约（B3-e）不合规实证（SF-050）

```
python scripts/check_ui_contract.py --no-such-flag   → exit=2   （B3-e：2 应保留给 NOT_RUN；usage 应为 3）
python scripts/agent/test_guard_check.py --no-such-flag → exit=2（同上）
test_guard_check.py:337  return 0 if all_ok else 2     （selftest 失败也复用 2 ⇒ fails 语义错位）
两者 --json 均无 summary.status∈{ok,fail,not_run} 与 not_run[]（check_ui_contract 只有 counts/rows/fixed）
```
⇒ 若直接接入 team_audit，调用方无法区分"没跑"与"用法错误"，会重演 PD-1。**接入前必修**。

## 5. 其它事实登记（Lead 提供 + 我核实）

- **SF-052（open，AGENTS L1）**：Lead 自报 2 次 L1（spawn 前未先建任务；1 次导致成员干完发现板上无任务）。
  根因可机检：dispatch-log 的 `--task` 是**可选**参数（`REQUIRED_FIELDS=("ts","actor","phase")`）⇒ L1 目前抓不到。
  建议 spawn 行必填 task + team_audit 校验 task 存在/先建后派。
- **SF-053（open，org B4）**：S4「派发未闭环」5 条 WARN 长期存在（spawn `p0-selection`×1、`team-plugin-creator`×4，>6h 无 done/retire）
  ⇒ 按 B4 要么补 done/retire、要么显式豁免留痕，不要长期挂 WARN 让门禁噪声化（本次审计还观察了 S5 1 处倒序、S1-exempt 2 条、S6 1 条 1s 补记）。

## 6. 门禁结果

- `team_audit.py --json`：**FAIL=0**（r6 的 FAIL 已由 r7 消除），`steward_self_audit=INFO`（5/5 匹配）。
- `--determinism`：PASS（sha `0b8268ed…`，compared_findings=80）。
- `prompt_drift_check.py --json`：exit=0 / status=ok / FAIL=0 / NOT_RUN=0 / INFO=6。
- pytest：见报告（1524 基线，我复跑记录在报告里）。
- `freeze_refreeze.py --check`：Lead 已重签 freeze（rules 488d7ebd→716712d4），dq5 已 PASS；`--apply` 仍待 L12（exit 4）。

## blind_spots

1. 未审 `check_ui_contract.py` 的 C1–C7 判据语义（只审接口/基线/退出码与当前红项），未审 `docs/conventions/ui-contract.md` 全文；
2. B-danger-1 无历史实例可回放（render-perf 事件未丢改动，属"差点出事"），强制力建议为设计推断；
3. 未在真实 DSH 工具层验证"拦截 checkout/reset"的可行性（需 DSH 插件侧改动）；
4. org.md §13 台账未逐条复核；产品代码/性能不在 steward 域。
