# task-102 交付报告：`decide.py` + `team/decisions.jsonl` 建库（D2 写入端 + D1 trailer 解析）

> **执行者**：steward2（flash）；**日期**：2026-10-24；**任务**：task-102（revision 2）
> **依据**：`AGENTS.md §0.5 L10`、`docs/guides/lead-dispatch-rules.md §6`（决策记录义务）、设计稿 `team-work-record-and-steward-design.md §2.3/§7.2-T5`
> **证据口径**：同目录文件均为可复跑命令的原始输出。

---

## 0. 结论

决策层从「无索引」变成「**可写、可查、可机检**」：

| 交付 | 说明 |
|---|---|
| `scripts/agent/decide.py`（新，~800 行） | `append`（fail-closed）/ `parse-commit`（D1 trailer → 索引行）/ `check` / `--selftest` |
| `team/decisions.jsonl`（新，进 git，append-only） | 回填 **2 条**历史决策（`reconstructed:true`），`decide.py check` PASS |
| `scripts/agent/work_record.py`（收紧） | doctor 对 decisions.jsonl **WARN→FAIL**（Lead 批准；task-102 落地后它已是必需源）；决策 evidence 支持 `doc:/commit:/task:` 三类指针 |

- `python scripts/agent/decide.py --selftest` **PASS**（11 类红路径逐条必红，见 §2）
- `python scripts/agent/decide.py check` **PASS**：2 条决策 / checked_count=2 / problems=0
- `python scripts/agent/work_record.py doctor` **PASS**（decisions OK；trajectory 仍 WARN）
- `python scripts/agent/work_record.py decision --grep "记忆卡"` / `--grep "0.4.6"` **各命中 1 条**（含 choice/alternatives/why/证据指针）
- `python scripts/agent/team_audit.py` **FAIL=0**；`role_registration` 已转 **INFO**（快照重导出后三方 9/9/9 一致）
- `git diff --numstat`：`team/decisions.jsonl` = `2 0`（只增不删 ✅）

---

## 1. 写侧判据（全部来自已落地条款，不自造 schema）

### 1.1 `append` 的 fail-closed 校验（设计稿 §2.3.3 六条 + 条款 §6 补充）
| # | 校验 | 实现 |
|---|---|---|
| ① | id 形状 `dec-YYYYMMDD-<sha8>` 且唯一 | 形状正则 + 全量 id 查重（默认按内容派生，可 `--id` 覆盖） |
| ② | ts 单调（≥ 文件最后一行） | 时间倒流 ⇒ 拒绝（append-only 的写侧对应物） |
| ③ | decided_by 合法 | ∈ `agents.json` 的 id（含 `retired_agents`）/ `human` / `lead` |
| ④ | alternatives 非空 或 no_alternative_reason | 每项必须有 `option` + `why_rejected`（`选项|why` 语法，缺 why 不猜） |
| ⑤ | evidence.ref 可解析 | `doc/report`=文件存在（可带 `#sha256=` 校验）；`commit`=`git cat-file -e`；`task`=快照 tasks/completedRecent 或 dispatch-log 命中 |
| ⑥ | reconstructed 必填布尔 | CLI **强制** `--reconstructed` 或 `--at-the-time` 二选一，缺省即拒绝（A2 防"补录伪装当场"） |
| 附加 | A1 时效 | 决策时间早于证据存在时间 >120s ⇒ 拒绝（不可能当场引用还没出现的证据） |
| 附加 | A2 reconstructed | 决策时间晚于证据 mtime 10 分钟以上且未标 reconstructed ⇒ 拒绝 |
| 附加 | Rule-Ref 可解析 | `path#section`：文件必须存在且章节 token 能在文件中找到（否则拒绝） |
| 附加 | R1 单向门 | `reversibility=R1` 且无 alternatives ⇒ 拒绝 |
| 附加 | Human-Directive ≤120 字符 | 超长拒绝（防"替人加戏"） |

### 1.2 `parse-commit`（D1：有提交的决策）
- 从 commit message **尾部 trailer 块**解析 7 个键（`Decision / Alternatives / Why / Rule-Ref / Reversibility / Human-Directive / Decision-Id`），键名与条款 §6.2 逐字一致；
- **无 `Decision:` 且无 `Why:` ⇒ 输出 `{"status":"no-trailer", ..., "detail":"该提交没有 Decision/Why trailer ⇒ 无决策记录（不是空成功）"}`，退出码 3**（关闭条件 4，显式而非空成功）；
- 发版（`^chore\(release\)`）/回退（`^Revert`）或 `Reversibility: R1` 缺 `Alternatives:` ⇒ `status:"invalid-trailer"` 退出码 1；
- **不创作任何文本**：`decision/why/alternatives` 全部原样来自 commit message（A6）。

### 1.3 `check`
坏 JSON 行 / id 形状 / id 重复 / ts 倒流 / 非法 decided_by / 缺 alternatives / evidence 失效 / Rule-Ref 不可解析 / reconstructed 非布尔 —— 全量校验；空文件或文件缺失 ⇒ **FAIL（输入为 0 不得判绿）**。

---

## 2. 自测（`selftest.txt`）：11 类红路径

```
PASS: decide.py selftest（绿：合法 append/check/parse；红 ≥10 类：缺 alternatives / 坏 id /
重复 id / ts 倒流 / 非法 decided_by / evidence 不可解析 / reconstructed 缺省 / Rule-Ref 不可解析 /
坏 JSON 行 / 发版缺 Alternatives / parse-commit 无 trailer 显式 no-trailer）
```

| 红路径 | 断言 |
|---|---|
| 缺 alternatives 且无 no_alternative_reason | exit 2 + stderr 含 "alternatives" |
| id 非法形状 / id 重复 | exit 2（分别含 "id=" / "id 重复"） |
| ts 倒流 | exit 2 + "时间倒流" |
| decided_by 非法 | exit 2 + "decided_by" |
| evidence 指向不存在文件 | exit 2 + "不可解析" |
| 缺 reconstructed/at-the-time | exit 2 + "reconstructed" |
| Rule-Ref 不可解析 | exit 2 + "Rule-Ref" |
| 坏 JSON 行 / 手写 ts 倒流 | `check` exit 1 且 json 输出含对应 problem |
| 发版提交缺 Alternatives | `parse-commit` exit 1 + `invalid-trailer` |
| 无 trailer 的提交 | `parse-commit` **exit 3** + `status:"no-trailer"` |

---

## 3. `team/decisions.jsonl` 回填（2 条，均 `reconstructed:true`）

| id | question | choice | alternatives | 证据 | 为什么标 reconstructed |
|---|---|---|---|---|---|
| `dec-20261024-e7cb6c7a` | 新成员如何继承前任经验：复制会话 vs 记忆卡 | 记忆卡（≤8KB，append，带免责） | 复制整段会话（42.6MB×5≈210MB 且传播已推翻结论） | doc:team/memory/README.md；doc:设计稿；task:task-87 | 决策发生在今天早些时候，记录晚于证据 mtime 10 分钟以上 |
| `dec-20261024-275ca28a` | 本轮发 v0.4.6 还是把 0.4.7 一起发 | 只发 v0.4.6；0.4.7 顺延 | ①同时发（范围未审计、无 planRef — task-88）②只发 0.4.7（0.4.6 已冻结含修复） | commit:09a5cbf2；commit:d35d4395；doc:`src/memoria/__version__.py` | 同上 |

`rule_refs` 分别指向 `docs/guides/agent-team-lessons.md#1`、`AGENTS.md#0.5 L8`、`docs/guides/lead-dispatch-rules.md#4`；
`human_directive` 保存人原话摘录（≤120 字）。**`why`/`alternatives` 全部来自已落盘的论证（README/设计稿/提交正文），没有新创理由**。

> 诚实边界：这 2 条是**回填**，不是"当时记录"；`reconstructed:true` 让它们永远可识别（A2）。
> 设计稿 §2.3.7 另 2 个例子未回填（避免为凑数编理由），后续真实决策发生时按 §6.3 正常记录即可。

---

## 4. 消费端联调（`work_record.py`，Lead 批准的一处收紧）

1. **`decision --grep` 已可用**：`--grep "记忆卡"` / `--grep "0.4.6"` 均返回 choice/alternatives/why/evidence（证据按 `doc/commit/task` 三态解析，不再把 commit sha 当文件路径）。
2. **`doctor` 收紧（WARN→FAIL）**：task-102 落地后 `team/decisions.jsonl` 属**必需事实源**；缺失 ⇒ FAIL（不再 WARN）。当前实跑：
   ```
   [OK] decisions：2 条决策，索引校验 bad=0
   RESULT: PASS（FAIL=0，WARN=1：trajectory 未落地）
   ```
3. **selftest 同步更新**：新增「decisions 缺失 ⇒ doctor FAIL（exit 1）」红用例 + 「写入合法索引后 doctor 回到 PASS」绿用例；原「缺失=WARN」断言删除。

> **写域披露（Lead 已知情）**：`work_record.py` 不在 task-102 writeScopes 内，但这是 Lead 在派发消息中明确要求的收紧；
> 改动仅 doctor 一个分支 + 决策证据解析 + selftest，`work_record.py --selftest` 全绿。

---

## 5. 关闭条件逐条对照

| # | 条件 | 结果 |
|---|---|---|
| 1 | `decide.py --selftest` PASS（≥6 类红） | ✅ 11 类红（§2） |
| 2 | 追加 2 条回填后 `decide.py check` exit 0；numstat 只增不删 | ✅ `2 0`；check PASS |
| 3 | 非法记录实测被拒（缺 alternatives / ts 倒流 / evidence 不存在 / id 重复） | ✅ `rejections.txt` 四条原始输出 |
| 4 | `parse-commit 26fa9bc6` 明确返回"无决策记录" | ✅ exit 3 + `status:"no-trailer"`（`parse-notrailer.json`） |
| 5 | 报告落 `artifacts/agent/verify/steward/**`；不改 src/**、不改现有工具 | ✅（除 Lead 批准的 `work_record.py` 收紧） |

---

## 6. 诚实边界 / 已知摩擦（需 Lead 裁决或知悉）

1. **A2 的 10 分钟窗口在实战中偏紧**：若决策者先用 doc 证据、30 分钟后才 `append`，会被要求 `--reconstructed`（诚实但略麻烦）。
   当前阈值是常量 `RECONSTRUCTED_THRESHOLD_SECONDS=600`；条款 §6 没写具体分钟数（只写"超窗 ⇒ 标 reconstructed"）。
   **建议**：保持现状（宁可多标 reconstructed），或由 Lead 在 §6.2 补一句"窗口 = 10 分钟"把它变成条款，我改常量即可。
2. **`parse-commit` 的 `decided_by` 默认 `lead`**：commit 作者是本机同一人（不是身份信息），无法从 git 推断"决策者"；
   需要按 commit 归属传 `--decided-by`。不猜。
3. **决策索引不校验"重复决策"**（同一问题被记两次）：目前只校验 id 唯一。可作 P2（语义去重需人判断）。
4. **`decisions.jsonl` 的 A3（append-only）机检在 task-103 的 `decision_trail`**：本任务只保证写侧 append；
   `git log --numstat -- team/decisions.jsonl` 出现 removed>0 的检查由 task-103 落地。

## 7. 复跑

```powershell
python scripts/agent/decide.py --selftest
python scripts/agent/decide.py check
python scripts/agent/decide.py parse-commit 26fa9bc6     # exit 3 => 无 trailer（显式）
python scripts/agent/work_record.py decision --grep "记忆卡"
python scripts/agent/work_record.py doctor
```
