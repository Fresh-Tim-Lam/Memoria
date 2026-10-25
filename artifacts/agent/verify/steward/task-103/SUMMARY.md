# task-103 交付报告：P1 机检三类 + `findings.jsonl` + steward 首轮真实审计

> **执行者**：steward2（flash）；**日期**：2026-10-24；**任务**：task-103（rev 2）
> **依据**：设计稿 `team-work-record-and-steward-design.md §5.1/§5.3/§6/§7.2`；`org.md §2.6`（章程）；`lead-dispatch-rules §6`
> **证据口径**：同目录原始输出；审计收据本体在 `team/steward/audit-2026-10-24/`（进 git）。

---

## 0. 结论

三通道（组织 / 过程 / 决策）**全部打通并可被机器复验**：

| 交付 | 结果 |
|---|---|
| `team_audit.py` +3 P1 检查 | `decision_trail` / `model_policy` / `steward_self_audit`，各有**必红 fixture**、已注册 `run_checks`（selftest PASS） |
| `team/steward/findings.jsonl`（进 git，append-only） | **13 条** finding，每条带 `disposition`；非 proposal 的 `rule_ref` 全部可解析 |
| `team/steward/audit-2026-10-24/{standards_read.json, SUMMARY.md, findings.jsonl}` | 首轮审计收据：4 个标准 sha256 MATCH、8 步执行记录、blind_spots 已写 |
| 自证 | `steward_self_audit` 两个负例（改 sha / 非法 rule_ref）**实测 FAIL**；恢复后 **INFO** |
| 机检基线 | `team_audit.py` **FAIL=0**（WARN 49 / INFO 14）；`work_record doctor` PASS；`decide check` PASS |

---

## 1. 三个 P1 检查（判据 = 已批准条款，不新增 schema）

### 1.1 `decision_trail`（`lead-dispatch-rules §6.5` + `AGENTS.md §0.5 L10`）
- **机检口径 = 条款的可判定子集**（诚实声明，不是全量）：
  - **T3 不可回退（R0/R1）**：改 `src/memoria/__version__.py` / `pyproject.toml` / `Package/**` / `chore(release)` / `Revert`；
  - **T1 影响后续走向**：改**组织资产/团队规范**（`AGENTS.md`、`lead-dispatch-rules`、`org.md`、`agents.json`、快照）；
  - **T2 判断类不可机检** ⇒ 写入 blind_spots，不假装检查；
  - 普通 `src/**` 提交**不计触发**（否则几乎每提交都要 trailer = 假红灾难，lessons L1.2）。
- 触发提交必须有 `Decision:`+`Why:`；T3/R1 另需 `Alternatives:`（每项含 `rejected:`）。
- **宽限**：§6.5「首两周 WARN、之后 FAIL」→ 常量 `DECISION_TRAIL_GRACE_UNTIL=2026-11-07`。
- **抽取**：把带合规 trailer 的提交抽成索引行（只读报告；**不写 decisions.jsonl**，A3/A6）。
- 实跑：**39 个触发提交 / 37 个缺 trailer（WARN 宽限）**；抽取到 **2 个合规决策提交**（`4bbd7685`、`eb803b1c` —— Lead 自条款落地起就在写 trailer）。

### 1.2 `model_policy`（`org.md §2.1 维护纪律 6`，人裁决"统一 flash"）
- `snapshot.members[].model` 必须 `deepseek-flash`；
- 例外：`agents.json` 该成员有 `model_exemption{reason, approved_at, approved_by}` 三字段齐全；
- 快照缺 `model` 字段 ⇒ **WARN 无法核对**（不静默绿）。
- 实跑：**10 名成员全部 deepseek-flash（INFO）**。

### 1.3 `steward_self_audit`（`org.md §2.6 B3/B4`）
- ① `standards_read.json` 必须覆盖 4 个标准（AGENTS.md §0.5 / lead-dispatch-rules / lessons / team_audit.py 检查清单），
  且 **sha256 必须等于磁盘当前文件** ⇒ 不一致 FAIL「用缓存标准审计」；
- ② 每条 finding：`rule_ref` 可解析 **或** `disposition=proposal` ⇒ 否则 FAIL「把偏好当规范」；
- ③ `disposition=open` 超 14 天 ⇒ WARN；
- ④ `SUMMARY.md` 缺 `blind_spots` ⇒ WARN。
- 实跑：首轮真实审计 **INFO**；两个负例 **FAIL**（见 §3）。

---

## 2. 首轮真实审计（8 步，产物体现在 `team/steward/audit-2026-10-24/`）

| 设计稿 §6.1 步 | 结果 |
|---|---|
| 1 新鲜度 | 快照 `exportedAt=12:06:52Z` 晚于 agents/org mtime；`role_registration`=INFO（三方 9/9/9） |
| 2 重读标准 + sha256 | `standards_read.json`：4/4 MATCH（`standards-sha.txt` 可复算） |
| 3 跑机检 | FAIL=0（WARN 49 / INFO 14） |
| 4 跑工作记录投影 | `doctor` PASS；`task/member/decision/risk` 均有产物（task-101/102 报告） |
| 5 产出三件收据 | `standards_read.json` / `SUMMARY.md` / `findings.jsonl`（+ 累积 `team/steward/findings.jsonl`） |
| 6 finding 处置 | 13 条：`mechanized`=3、`fixed`=5、`open`=2、`proposal`=3（0 条 FAIL 级） |
| 7 转换率 | 本轮上线 3 个新检查；WARN 级 finding 6 条中 2 条已固化为机检 |
| 8 自审 | INFO；负例必红 |

**关键 finding（完整 13 条见 findings.jsonl）**：
- SF-001（WARN→**mechanized**）：0.4.7 实施早于计划落盘（`AGENTS.md §0.5 L8`）→ `plan_consulted`
- SF-004（WARN/open）：39 个 T1/T3 触发提交 37 个缺 trailer（宽限期，2026-11-07 后转 FAIL）
- SF-003（WARN/open，task-107）：dispatch-log 14 条 spawn 全缺 `mode`，模式决策无法判定
- SF-002（WARN/open）：12 个 benchmark 文件全仓无入口（待 Lead/人三选一）
- SF-008 / SF-010（**mechanized**）：G3 快照时效门禁、G5 注册原子性 → `doctor`/`role_registration`
- SF-011 / SF-012（**proposal**）：① 两个 §6 重号（已由 Lead 按 proposal 修复 `4bbd7685`）；② A2 窗口精确值未写条款（Lead裁决保留为实现常量）
- SF-013（fixed）：本轮首次产出 `standards_read` 收据

**blind_spots（本轮没审计什么）**：trajectory 未落地（动作层三类问题不可见）/ 未读 session 正文 / T2 判断类不可机检 /
dead_path 含文档引用口径 / 产品代码质量与性能不在范围 / `§13` 台账未逐条复核 / R0-R1 对抗复核（A5）暂无机检。

---

## 3. 自证（`negative-proofs.txt`，可复跑 `negative_proof.py`）

```
负例1：篡改 standards_read 的 AGENTS.md sha256
  audit exit=1 → [FAIL] 标准已变而收据未更新（用缓存标准审计）：AGENTS.md 磁盘 6c87fe55… vs 收据 000000…
负例2：插入 rule_ref 不可解析且非 proposal 的 finding
  audit exit=1 → [FAIL] finding #14 的 rule_ref 不可解析（docs/guides/not-exist.md）—— 把偏好当规范
恢复后：audit exit=0 → [INFO] 最近审计 audit-2026-10-24 可机审通过（standards 4/4 sha256 匹配；findings 13 条；blind_spots 已写）
```

---

## 4. 关闭条件逐条对照

| # | 条件 | 结果 |
|---|---|---|
| 1 | 三个检查 + 原有检查 `--selftest` PASS，每个新检查有必红 fixture | ✅（`selftest.txt`；红 fixture 见 task-103 段：缺 trailer / v4-pro 无豁免 / 缓存标准 + 非法 rule_ref + 缺 blind_spots） |
| 2 | 首轮审计报告存在，8 步有产物，standards_read 可复算 sha256 | ✅（`team/steward/audit-2026-10-24/`；`standards-sha.txt` 4/4 MATCH） |
| 3 | `steward_self_audit` 两个负例必红、真实审计绿 | ✅（§3） |
| 4 | findings.jsonl 每条有 disposition，FAIL 级映射任务 | ✅（13 条；本轮 0 条 FAIL 级；open 的 3 条分别映射 task-95/task-107/待 Lead 裁决） |
| 5 | `team_audit.py` 当前 FAIL=0 | ✅（WARN 49 / INFO 14；WARN 中 4 条为本轮 open/proposal finding，其余既有基线） |

---

## 5. 诚实边界 / 未做

1. **`decision_trail` 不是全量决策机检**：T2 判断类无法机检；普通 `src/**` 提交不计触发。若 Lead 想把 T1 扩到"所有代码提交"，
   必须先改条款并接受 WARN 洪峰（当前 14 天约 300 提交）—— 我没有擅自扩口径。
2. **历史 37 条缺 trailer 的提交不回改**（A3 append-only / 不改写历史）；宽限 2026-11-07 后新提交才会转 FAIL。
3. **`steward_self_audit` 只校验最近一轮审计**；不审计"审计间隔是否过长"（缺调度事实源，属插件周期触发 R6）。
4. `findings.jsonl` 里 SF-002/003/004/009 是 `open`：分别等 人裁决 / task-107 / 宽限期 / task-95，不是遗漏。
5. 本轮 **没有**读 session、没有改任何标准文件（只有 `team_audit.py` 与 `team/steward/**` 是本任务写域）。

## 6. 复跑

```powershell
python scripts/agent/team_audit.py --selftest
python scripts/agent/team_audit.py --json
python artifacts/agent/verify/steward/task-103/negative_proof.py     # 负例自证（会临时改/恢复收据）
```
