# task-100 交付报告：P0 机检四类（plan_consulted / role_registration / dead_path_edit / mode_policy）

> **执行者**：steward2（flash）；**日期**：2026-10-24；**任务**：task-100（revision 3）
> **改动**：仅 `scripts/agent/team_audit.py`（新增 4 个检查函数 + `run_checks` 注册 + 4 组红 fixture + 头部清单）；
> **不改**任何既有检查的判据/阈值/窗口。
> **证据口径**：同目录文件均为可复跑命令的原始输出。

---

## 0. 结论

四个检查已落地，**rule_ref 全部指向现行规范**（先有条款、后有检查）：

| 检查 | rule_ref | 严重度 | 当前仓库实跑结果 |
|---|---|---|---|
| `plan_consulted` | `AGENTS.md §0.5 L8` | WARN（首月宽限→FAIL） | **报出 0.4.7 违规** ✅（任务预期） |
| `role_registration` | `docs/guides/agent-team-org.md §2.3 执行纪律 1` | FAIL / WARN | 三方集合 **A==B==C=True（9/9/9）**；另报 WARN「快照早于 org.md 修改」（见 §3.2） |
| `dead_path_edit` | `docs/guides/agent-team-lessons.md §0 L0.3` | WARN | 报出 **12** 个「全仓无引用」文件（checked_count=121），抽样 3 条确认仅自引用 |
| `mode_policy` | `AGENTS.md §0.5 L9` | WARN | **12 条 spawn 记录全部缺 mode 字段** ⇒ 显式报「无法判定」，不静默判绿 ✅（任务预期） |

- `python scripts/agent/team_audit.py --selftest` **PASS**（4 个新检查各有必红 fixture；绿 fixture 无误报；且断言四者已注册进 `run_checks`）。
- `python scripts/agent/team_audit.py` **FAIL=0**，WARN 53（既有 49 + 新增 4），INFO 10；新增 check 名已出现在 `--json` 输出中。
- 机检总耗时 **15.0 s**（初版逐文件 `git grep` 为 63.6 s ⇒ 改为**一次批量 git grep**，见 §5.2）。
- `git diff --numstat`：`637 3`（删除 3 行 = selftest 绿 fixture 的 spawn 行改加 mode 字段；删除 < 插入 ✅）。

---

## 1. 四个检查的判据（与设计稿/条款对齐）

### 1.1 `plan_consulted`（设计稿 §5.2-①）
- 窗口 14 天；版本家族 = `src/memoria/__version__.py` 的 `X.Y.*`。
- `t_impl` = 最早「提交信息含 V 且改动含 `src/`|`scripts/` 且不含 `docs/`」的提交；
- `t_plan` = 最早「`docs/todo.md` diff 中出现 V」的提交（`git log -S<V> -- docs/todo.md`，全历史）；
- `t_impl` 存在且（`t_plan` 缺失 或 `t_plan > t_impl`）⇒ WARN。
- 输入保护：非 git ⇒ INFO 跳过；窗口内无提交 ⇒ WARN「输入为 0 不得视为通过」；**有提交但版本被家族过滤为 0 ⇒ FAIL**（解析失效）。

### 1.2 `role_registration`（org.md §2.3 执行纪律 1；设计稿 §5.2-②）
- A = `agents.json` 中 `status∈{active,standby}` 的 id（`roster_alias` 展开；**lead 除外**——lead 是 DSH 会话身份
  `scope=dsn-session`，不进 org §2 名册计数）；
- B = `org.md §2 + §2.2` 解析出的 owner；
- C = 快照 `members`（lead 除外）；
- 判据 1：A==B==C，任一侧差集 ⇒ FAIL 并打印差集；
- 判据 2：`snapshot.exportedAt` 必须晚于 `agents.json`/`org.md` mtime（差 >30s）⇒ WARN。
- 输入保护：agents/org/snapshot 任一不可用或解析为空 ⇒ FAIL「输入不足，输入为 0 不得判绿」。

### 1.3 `dead_path_edit`（lessons L0.3）
- 窗口 7 天；候选 = 改动过的 `src/**`、`scripts/**`（排除 tests/，后缀 .py/.js/.mjs/.ts）；
- 白名单 = 文件头 5 行内 `@entry` 标记（**从仓内实测生成**，不维护手工名单）；
- 引用检索 = `git grep` 全 HEAD（**含文档引用**，按设计字面口径）+ 排除「文件自己提到自己」；
- 无引用且非 `@entry` ⇒ WARN；非 git ⇒ INFO；有提交但候选为 0 或全不可检查 ⇒ FAIL。

### 1.4 `mode_policy`（AGENTS.md §0.5 L9；人 2026-10-24）
- 扫 dispatch-log `phase=spawn`（窗口 14 天）：
  - 有 `mode` 但 `modeExplicit` 缺失/False ⇒ WARN「无法证明是显式决策」；
  - `mode` 不在 DSH 四档 ⇒ WARN；
  - **整份日志无 mode 字段** ⇒ 显式 WARN「N 条全部缺 mode，无法判定」，并给 `checked_count`/`with_mode`，**不静默判绿**；
  - 有 mode 且部分记录缺 ⇒ 对缺失部分另报 WARN（防止「部分可判定」掩盖「部分没记」）；
  - 加分项：描述含只读/扫描类动词却用 standard/deep ⇒ WARN「可能该用 mechanical」。
- 输入保护：dispatch-log 不存在 / 无 spawn 记录 / 窗口内无 spawn ⇒ FAIL 或 WARN，均不静默。

---

## 2. 自测（`selftest.txt`）：四个检查各自"必红" fixture

```
SELFTEST PASS：红 fixture 报出 9 类检查（roster×2 / stall ×2 / write_scope ×2 / artifact_refs /
role_evidence / silent_failure ×6 / contract_drift ×5），commit_hygiene 在非 git fixture 上 INFO 跳过，
绿 fixture 全绿；task-100 四类新检查各自红 fixture 必红、绿 fixture 不误报、且都已注册进 run_checks。
```

| 检查 | 红 fixture（断言） | 绿 fixture（断言） |
|---|---|---|
| `plan_consulted` | 临时 git 仓：先 `feat: 0.9.9 实现`（touch src/）→ 后 `docs(todo): 0.9.9 计划` ⇒ 必报 WARN 含 "0.9.9" | 顺序反过来 ⇒ 无 FAIL/WARN |
| `role_registration` | agents={alpha,ghost} / org={alpha} / snapshot={alpha,beta} ⇒ 必报 FAIL 含 "ghost" 与 "beta"；FAIL 消息必须带 `checked_count` | 三方均 {alpha} + exportedAt 未来 ⇒ 无 FAIL/WARN |
| `dead_path_edit` | 临时 git 仓提交 `scripts/dead_probe_zz.py`（零引用）⇒ 必报 WARN 含文件名 | 同仓 `docs/ref.md` 引用 `used_probe_zz.py` ⇒ 无 FAIL/WARN |
| `mode_policy` | 3 条 spawn：无 mode / 有 mode 无 explicit / mode=turbo ⇒ 三类 WARN 全部命中（"缺 mode 字段"、"modeExplicit"、"不在 DSH 四档"） | spawn 显式 `mode=mechanical, modeExplicit=true` ⇒ 无 FAIL/WARN |

另：`run_checks` 注册断言（否则「单测绿、生产不跑」= 假绿）。

---

## 3. 当前仓库实跑（`audit-full.txt` / `audit.json`；FAIL=0 WARN=53 INFO=10）

### 3.1 `plan_consulted`（WARN）—— 报出 0.4.7 违规 ✅

```
版本 0.4.7 的实施提交 a68ab655（10-23 13:19）早于台账计划落盘 10-23 22:52（docs/todo.md）
—— 违反 AGENTS.md §0.5 L8（checked_count=1）
证据：git:a68ab655e7024148b1752304bc37c6fb65eb2217 vs docs/todo.md -S'0.4.7'
```

与任务描述里写的 `e374463f 13:31 / 18:00` 有细微差别，原因是**口径更严格/更早**：
- `t_impl` 取「最早的实施提交」⇒ `a68ab655`（10-23 13:19，`feat(dock): ...（0.4.7 任务 3）`，改 `src/`）比
  `e374463f`（13:31）更早；
- `t_plan` 取「`docs/todo.md` diff 中最早出现 0.4.7 的提交」⇒ 10-23 22:52（早于 §14 计划提交 10-24 18:00，
  说明 §13 状态表在 10-23 已提到 0.4.7）。
**结论一致：实施早于计划，违规成立**（且比原预期更早可发现）。
另：0.4.6 的 release 提交同 commit 带 docs 改动，按设计「不含 docs/」口径不计入实施提交——此边界已在
检查注释中写明（若 Lead 认为应改口径，属条款变更，不在本任务「不改既有判据」范围）。

### 3.2 `role_registration`（WARN，非 FAIL）—— 三方集合已全等；只剩「快照过期」WARN

```
A (agents active/standby, lead excluded) = 9  ['arch-contract','doc-consistency','metrics-baseline','render-perf','steward','steward2','sync-mapper','team-plugin-creator','todo-owner']
B (org §2+§2.2)                         = 9  同集合
C (snapshot members, lead excluded)     = 9  同集合
A==B==C: True
```

WARN 原因（`role-sets.txt` + audit 输出）：

```
快照 exportedAt=2026-10-24T11:34:19.214Z 早于 org.md mtime=2026-10-24T11:37:41.965063+00:00
⇒ 快照不可能反映注册修改，须重导出快照后再审计
```

**说明（为何不是 PASS）**：这是设计稿判据 2（快照必须晚于注册修改）在正常工作——Lead 正在执行 task-99
修改 `org.md`（mtime 11:37），而快照导出于 11:34。**处理办法：task-99 收口后由 Lead 重导出 `team_snapshot`**，
本检查随即可转 INFO（三方集合本来就一致，不是注册错误）。这不是本检查的缺陷，也**不应**为了变绿而放宽阈值。

### 3.3 `dead_path_edit`（WARN，12 个候选）

```
近 7 天改了 12 个「全仓无引用」文件（checked_count=121，扫描 121 个 basename，一次批量 git grep）：
scripts/benchmark/maintenance/executor_coalesce_assert.py
scripts/benchmark/maintenance/lexical_index_cache_bench.py
scripts/benchmark/surface/run_block_count.py
scripts/benchmark/maintenance/nested_list_edit_test.mjs
scripts/benchmark/maintenance/nested_list_test.mjs
scripts/benchmark/maintenance/_bugc_doc_check.js
scripts/benchmark/surface/perf_tail_ab.mjs
scripts/benchmark/surface/perf_tail_drift.mjs
scripts/benchmark/surface/perf_tail_edit_l5.mjs
scripts/benchmark/surface/selcol_ask_probe.mjs
scripts/benchmark/surface/make_link_fixture.py
scripts/benchmark/surface/realapp_humanlike.mjs
```

**抽样 3 条人工核对**（`dead-samples.txt`，口径：`git grep -l -F <basename> HEAD` 命中数、排除自身路径后外部引用数）：

```
executor_coalesce_assert.py -> total_refs=1, external_refs=0
run_block_count.py          -> total_refs=1, external_refs=0
nested_list_test.mjs        -> total_refs=1, external_refs=0
```

即：三条都只有「文件自己提到自己」（自述/usage），**没有任何外部代码/文档入口** ⇒ 人工确认"确实无入口"成立。
这 12 个多为一次性 benchmark 探针；**它们是否需要入口（或应归档/删除）需人/Lead 裁决**，本检查只报事实。
> 能力边界（诚实声明）：引用检索**包含文档引用**（设计字面口径），所以「文档提过但代码无入口」的文件不会报出；
> 若收紧为「只算代码引用」，本仓库当前窗口会报 35 个（噪声大），需先补 `@entry`/入口清单再收紧——属后续提案。

### 3.4 `mode_policy`（WARN，无法判定）—— 按 Lead 要求显式输出

```
12 条 spawn 记录全部缺 mode 字段（dispatch-log 尚未记录模式）⇒ 无法判定是否做过模式决策，不静默判绿。
修法：dispatch_log.py 增加 --mode 参数，spawn 时记录 mode（L9：不传 mode = 静默默认 standard）
（checked_count=12，with_mode=0）
```

字段实测：spawn 行现有字段 = `ts/actor/phase/target/task/desc/source`，**没有** `mode`/`modeExplicit`。

---

## 4. 关闭条件逐条对照

| # | 条件 | 结果 |
|---|---|---|
| 1 | `--selftest` PASS，四检查各有必红 fixture | ✅（§2） |
| 2 | 实跑：plan 报 0.4.7；role PASS 或说明；dead 抽样 3 条；mode 显式说明 | ✅（§3.1–3.4） |
| 3 | 带 `checked_count`；输入为 0 判 FAIL | ✅（每个 check 的消息/证据都带；非 git 为 INFO 跳过、窗口无输入为 WARN、解析失效为 FAIL） |
| 4 | `--json` 新增 check 名；报告落 `artifacts/agent/verify/steward/**` | ✅（`json-check.txt`：15 个 check 名含四个新项；本目录） |
| 5 | 不改既有判据/阈值；只新增函数 + 注册 + selftest 条目 | ✅（`637 3`；唯一改动既有 fixture 的 3 行是绿 fixture 补 `mode` 字段，否则 mode_policy 绿路径无法成立） |

---

## 5. 实现要点（给维护者）

### 5.1 为什么不直接复用 `existing check_roster / contract_drift`
- `roster` 做的是「org ↔ 快照」两两比对；`contract_drift D4` 只核对 active id 与快照/别名。
  设计要求的第 3 个来源（`org.md §2.2` 非领域常驻）与「三方全等 + 快照晚于注册修改」在旧实现里**没有单点**。
  新检查**只读同一批文件**、不改变任何既有 finding 的语义。

### 5.2 性能：逐文件 `git grep` → 一次批量 `git grep`
- 初版对每个改动文件调一次 `git grep -l`：121 文件 ⇒ 机检 **63.6 s**（不可接受）。
- 现版把全部 basename 作为 `-e` 参数一次检索，解析 `HEAD:path:lineno:content` 并排除「自引用」⇒ **15.0 s**
  （含其余 12 类检查）。代价：命令行变长（121×~35B ≈ 4KB，远低于 Windows 限制）。

### 5.3 输入为 0 的三种处理（防假绿，但不制造假红）
| 场景 | 处理 | 理由 |
|---|---|---|
| 非 git 仓库 | INFO 跳过 | 检查**不适用**，不是"没发现问题" |
| 窗口内无提交 / 无 spawn | WARN「输入为 0，不得视为通过」 | 可能只是安静期，但必须可见 |
| 有提交但解析出 0 个候选/版本 | **FAIL** | 这是解析失效（真 bug），必须红 |

---

## 6. 下一步（需 Lead / 人裁决，均不在本任务写域）

1. **`dispatch_log.py` 增加 `--mode` + `--mode-explicit`**（或 Lead 在 spawn 后手工补记），
   否则 `mode_policy` 会一直是「无法判定」的 WARN。建议登记为新任务（owner 建议 team-plugin-creator 或 Lead）。
2. **task-99 收口后重导出快照** ⇒ `role_registration` 的 WARN 自动转 INFO。
3. dead_path_edit 的 12 个候选：由 Lead 裁决「加 @entry / 归档 / 删除」，本检查不阻断。
4. 首月宽限后（设计 §5.1 #1）把 `plan_consulted` 从 WARN 升 FAIL 需 Lead 裁决；
   同时 `decision_trail`（task-103）上线后，`T2/T3` 的决策记录义务会与本检查互补。

## 7. 复跑

```powershell
python scripts/agent/team_audit.py --selftest
python scripts/agent/team_audit.py
python scripts/agent/team_audit.py --json
```
