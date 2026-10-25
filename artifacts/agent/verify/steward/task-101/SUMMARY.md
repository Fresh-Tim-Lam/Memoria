# task-101 交付报告：`work_record.py` 五命令只读投影

> **执行者**：steward2（flash）；**日期**：2026-10-24；**任务**：task-101（revision 3）
> **设计依据**：[team-work-record-and-steward-design.md](../../../../docs/guides/team-work-record-and-steward-design.md) §2.2 / §2.4 / §7.2-T4
> **证据口径**：本文件所有命令输出均落在同目录（可复跑），不是转述。

---

## 0. 结论

`scripts/agent/work_record.py`（1667 行，新增文件）已实现五条子命令
`task` / `member` / `decision` / `risk` / `doctor`，**只读投影、不新增事实源、不写 `team/**`、不写任务板**。
文件头 docstring 明写「**投影不是事实源，删除可重建**」及数据源所有权表。

**状态**：关闭条件 1–5 全部满足（逐条证据见 §2）。

---

## 1. 五命令与设计映射

| 命令 | 设计稿落点 | 输出 | 关键机制 |
|---|---|---|---|
| `task --id task-XX [--json] [--full]` | §2.2 / §2.4 | Markdown（默认 ≤8 KB）+ JSON | join：任务板快照 × dispatch-log × `git log --grep` × evidence 路径解析 × decisions × memory 卡；超预算自动收缩并**显式标 truncated** |
| `member --id <m> --since 7d` | §2.4 | Markdown + JSON | 身份（agents.json→快照回退）× 派发/生命周期 × 提交 × 名下任务 × 记忆卡 |
| `decision --grep kw [--limit 5] [--doctor]` | §2.3 / §2.4；通道③完成判据 | Markdown（≤4 KB）+ JSON | 索引未建立 ⇒ **NOT_ESTABLISHED**（不是「无决策」）；`--doctor` 按设计 §2.3.3 六条校验（id 形状/唯一、ts 单调、decided_by、alternatives、reconstructed 布尔、evidence.ref 可解析） |
| `risk --since 7d` | §2.1(c) Phase 0 + §2.3.6 | Markdown + JSON | git 可观测子集：R0（reflog reset/checkout/restore）、R1（Package/**、版本文件、pyproject）、T2 删除≥20 行候选、T3 回退/自修候选；**覆盖盲区显式列出** |
| `doctor [--json]` | §6.1 数据源前置 | Markdown + JSON；**FAIL ⇒ 退出码 1** | 快照（缺失/坏 JSON/过旧/早于 agents.json mtime/早于最新派发）、dispatch-log、agents.json、decisions、memory、trajectory、git |

**退出码**：0 数据源可读（可带 WARN/NOT_ESTABLISHED）；1 FAIL；2 用法错误。

**自测**：`python scripts/agent/work_record.py --selftest`（临时 git 仓库 fixture，绿/红路径都断言）。

---

## 2. 关闭条件逐条证据

### 条件 1｜用 task-87/95/96/97 跑 `task`，输出 owner/evidence/相关提交；至少 1 条显示 evidence 不存在或 gitignored

| 任务 | owner/status | 证据解析 | 相关提交 | 产物 |
|---|---|---|---|---|
| task-87 | team-plugin-creator / completed | **5 条全 `[missing]`**（`packages/experimental/...` 属 DSH 仓库，非本仓库） | 1 条 | `task-87.md` |
| task-95 | team-plugin-creator / pending | 0 条（未声明 evidence ⇒ 显式标注"无产物可验，本身是 finding 素材"） | 1 条 | `task-95.md` |
| task-96 | **快照中已删**（显式 data_gap，不静默空） | 0 条 | 1 条 | `task-96.md` |
| task-97 | steward / completed | `[exists] docs/guides/team-work-record-and-steward-design.md`（57 KB） | 2 条 | `task-97.md` |

`gitignored` 三态由 selftest 的 `artifacts/agent/verify/x.md` 断言（`artifacts/` 在 `.gitignore:15`）。
注：task-87 的 `packages/**` 与 task-101 的 `artifacts/**` 属于**两种不同**的"不在库"：
前者不在本仓库（DSH checkout），后者被 gitignore（不入库≠缺失）——工具分别标注。

### 条件 2｜doctor 数据源缺失返回非 0；正常返回 0

- 正常（本仓库实跑，`doctor.txt`）：`RESULT: PASS（FAIL=0，WARN=2）`，退出码 0；2 个 WARN 分别是
  `decisions.jsonl 未建立`（task-102 未落地）与 `team/trajectory 未建立`（task-95 未落地）——**显式**，不静默空。
- 缺失/损坏（selftest 自动断言，全部必红，退出码 1）：
  `doctor-missing-snapshot-fails` / `doctor-corrupt-snapshot-fails` / `doctor-invalid-decisions-fails` /
  `doctor-stale-snapshot-fails`。

### 条件 3｜单任务输出实测 ≤8 KB

`python scripts/agent/work_record.py task --id <id>` 的 **stdout 原始字节数**（`sizes.txt`，不是字符数）：

```
  5047 bytes  task-7        ← 仓库内 101 个任务中最大（30 条相关提交，含截断标记）
  3874 bytes  task-78
  2525 bytes  task-87
  1659 bytes  task-95
  1482 bytes  task-96
  1897 bytes  task-97
  1821 bytes  task-101
all <= 8192: True
```

另：对快照内**全部 101 个任务**逐一渲染，最大 4994 B，全部 ≤8192（口径同上）。
`--full` 不受预算限制（selftest 断言 `task-full-larger-than-default`）；被 section 上限截过的源数据即使未超预算也标 `truncated:true`。

### 条件 4｜docstring 写明「投影不是事实源，删除可重建」

文件第 3–7 行：`**投影不是事实源，删除可重建。**`，并列出五层数据源的唯一写入者与已知边界（快照缺 description/G2、artifacts gitignore、Phase 0 只覆盖 git 子集、决策索引未建立）。

### 条件 5｜不改任务板、不写 `team/`（只读）；报告落 `artifacts/agent/verify/steward/**`

- 脚本内无任何写入调用（`open(..., "w")`/`.write_text` 只出现在 `selftest()` 的临时目录内）；`team/**` 只读。
- 本报告与全部原始输出：`artifacts/agent/verify/steward/task-101/`（`artifacts/` 被 gitignore，与既有 verify 报告同口径）。
- 改动文件：仅新增 `scripts/agent/work_record.py`；`git diff --numstat` = `1667 0`（删除 0 < 插入）。

---

## 3. 自测（红/绿都验，`selftest.txt`）

```
PASS: work_record.py selftest（绿：task join/证据三态/预算≤8KB/member/decision/risk/doctor；
红：未知任务显式缺口、决策未建立、非法决策、缺快照、坏 JSON、快照过旧）
```

红路径清单（每条都断言退出码/状态，不做"跑通即绿"）：
缺快照 / 坏 JSON 快照 / 快照过旧（48h）/ 非法决策（id 形状 + 缺 choice + reconstructed 缺失）/
未知任务（显式 data_gap）/ 决策索引未建立（NOT_ESTABLISHED）。

---

## 4. 与设计稿的三处偏差（需 Lead 知晓，均为"更保守"方向）

1. **`decisions.jsonl` 缺失 = WARN 而非 FAIL**。
   设计 §6.1 把"缺文件"一律列 FAIL；但决策索引由 task-102（blocked_by task-99）才建立，
   若判 FAIL，则本任务之后每次 `doctor` 都红，会变成"长期已知假红"（lessons L1.2）。
   处理：**必需源**（snapshot/dispatch-log/git）缺失或损坏 ⇒ FAIL；**计划中源**（decisions/trajectory）缺失 ⇒
   WARN + **显式说明"查询不可用，不是没有数据"**；存在但损坏/非法 ⇒ FAIL。等 task-102 落地后可收紧为 FAIL
   （一行改动，在 `collect_doctor` 的 decisions 分支）。
2. **`risk` 命令把"删除 ≥20 行"与"R0/R1 风险动作"分开**。
   实测 7 天窗口：若按原口径全部标 R1，则 55/58 条都是"删除≥20行"（正常重构也删行），清单会被噪声淹没
   （正是设计 §4-Q6 "报太多"失败模式）。现拆为：
   - §1 R0/R1（9 条：Package/版本文件/pyproject/reflog reset）；
   - §2 T2 **决策记录义务候选**（删除≥20 行，按删除量降序，附 `removed>added` = 陈旧缓冲区覆盖信号，lessons §7）；
   - §3 T3 回退/自修候选（6 条）。
   三者都输出，但**不把"删除行数"冒充风险判决**；每类都带 rule_ref 与"需人工/对抗复核"。
3. **`risk` 的 reflog 证据来自本地 reflog**（非版本库、会过期）。已在输出里标为 R0 候选并写明
   "可能是无害切换，需人工确认是否作用于 src/** 或未提交工作"；force push / 无提交的 checkout 明确列入覆盖盲区。

---

## 5. 已知限制 / 下一个人从哪开始

- `task` 的任务板半边来自**快照**（`tasks[]` 无 description/createdAt/updatedAt，设计 G2）。
  **审计前必须重导出快照**（`doctor` 已把"过旧/早于 agents.json/早于最新派发"判 FAIL）——本工具不替你导出。
- 决策层在 task-102 落地前始终 `NOT_ESTABLISHED`；`decision --doctor` 已就绪，届时只需建库即可用。
- 动作层只有 git 可观测子集；`write_without_read` / `gate_fail_continue` 等轨迹类检查待 task-95。
- `member` 的"提交"口径 = **提交信息含成员名**（不是 git author；本仓库 author 是同一人）。这是近似口径，
  已在输出中写明；后续可用 trailer `Agent: <member>` 替代（属 task-99/task-102 范围）。
- 下一步（task-100）：`plan_consulted` / `role_registration` / `dead_path_edit` 写进 `team_audit.py`。
  注意 `work_record.py` 与 `team_audit.py` **无写域重叠**；但 task-103 与 task-100 都写 `team_audit.py`，必须串行（已由 Lead 排序）。

---

## 6. 复跑命令

```powershell
python scripts/agent/work_record.py --selftest
python scripts/agent/work_record.py doctor
python scripts/agent/work_record.py task --id task-87 --json
python scripts/agent/work_record.py member --id steward2 --since 7d
python scripts/agent/work_record.py decision --grep "0.4.6"        # 当前 ⇒ NOT_ESTABLISHED
python scripts/agent/work_record.py risk --since 7d
```
