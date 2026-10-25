# task-109 交付报告：P1 机检收口（determinism / write_scope 分级 / mode_policy）+ 第二轮审计 r2

> **执行者**：steward2；**日期**：2026-10-24；**任务**：task-109（**自建**，Lead 事后批准，已在任务描述与本报告中披露）
> **依据**：Lead commit `d95712e3` 落地的 §5.4 / §1.2b / §1.3b + lessons L9.6/L9.7
> **写域**：`scripts/agent/team_audit.py`、`team/steward/`、`artifacts/agent/verify/steward/`

---

## 0. 一句话

三个机检收口已落地并各自红/绿自证；**r2 审计把 `steward_self_audit` 从 FAIL=3 转 INFO**（重读标准新 sha，
未改首轮收据）；`team_audit.py` 现 **FAIL=0**，`--determinism` **PASS**。

---

## 1. 三个实现

### 1.1 `team_audit.py --determinism`（§5.4）
- 子进程连跑两次 `--json` → 归一化 `generatedAt` → 规范 JSON 字节比较；
- 一致：exit 0，打印两次 sha + `compared_findings`；不一致：exit 1 + 打印首个差异（`findings[i]` 字段级）。
- **不做成 run_checks 检查类**（避免自我递归 + 每次审计翻倍耗时）；selftest 有归一化/差异定位红绿 fixture。
- 实跑：`PASS … sha256=6ded0c4c… compared_findings=68`（`determinism.txt`）。

### 1.2 `write_scope` 分级（§1.2b）
- 新增共享产出根白名单 `artifacts/agent/verify` / `docs/design` / `team` / `scripts/benchmark`；
- 共享根 vs 其子路径 ⇒ **INFO**（假重叠）；同文件/同子目录/非共享根父目录重叠 ⇒ **WARN**；
- **前后实测**（`audit-before.txt` vs `audit-after.txt`）：
  ```
  before: 11 findings, 11 WARN, 0 INFO
  after : 12 findings,  6 WARN, 6 INFO
  ```
  残余 6 WARN = 2 同文件（task-85↔91）+ 1 services 子树（task-85↔92）+ **3 条两个任务都直接声明同一共享根**
  （task-86/94/107 均以 `artifacts/agent/verify` 根作 writeScope ⇒ 按 §1.2b 是真违规候选，保留 WARN，记为 SF-024）。
  > 与 Lead 预期「11→3」的差异已如实说明：共享根 vs 子路径只有 5 条，不是 8 条；"根=根"不能证明不冲突。

### 1.3 `mode_policy` 分离「显式未决定」（§1.3b）
- `modeExplicit=false` 单列 `WARN「显式未决定（合法留痕，但 L9 仍应尽量选）」`；
- 历史 14 条 spawn（无 mode 字段）仍如实报「不可判定」，**未伪造 mode**；
- selftest 三类 fixture：缺字段 WARN / 显式未决定 WARN / 带 mode 合法行不报。

---

## 2. r2 审计（`team/steward/audit-2026-10-24-r2/`）

- **重读 4 标准，新 sha 4/4 MATCH**（lead-dispatch-rules `488d7ebd…`、lessons `f2f86b09…`、team_audit.py `e6f16ef1…`、AGENTS.md `6c87fe55…`）；
- findings 累计 **24 条**（首轮 16 + 本轮 8：SF-017…024），机制/闭环/自证都有：
  - SF-017/018/019：三条条款 → 机检的 **mechanization 记录**
  - SF-020：SF-002 归档 `f5c3fcbb` → fixed（旧引用失效属历史不可逆）
  - SF-021：重复 §6 修复闭环（`4bbd7685`，依据我 proposal）
  - SF-022：**D2 首次真实使用** `dec-20261024-d7a3e0eb`（A2 强制 reconstructed）
  - SF-023：「标准变 ⇒ 重审计」自证：FAIL=3 → INFO，首轮收据未改
  - SF-024：open —— 3 条共享根直声明（建议 Lead 收窄 task-86/94/107 写域）
- `steward_self_audit`：**INFO**（4/4 sha、24 条 rule_ref/或 proposal、blind_spots 已写）
- 另追加 proposal **SF-025**（收据 sha 未定义 LF/CRLF 归一化口径，重新 checkout 会假红）——只进累积台账，下一轮纳入。

---

## 3. 关闭条件逐条对照

| # | 条件 | 结果 |
|---|---|---|
| 1 | `--selftest` PASS + 三处新 fixture 必红 | ✅（`selftest.txt`；determinism 4 断言 / write_scope 3 断言 / mode_policy 3 断言） |
| 2 | `--determinism` PASS | ✅（`determinism.txt`） |
| 3 | FAIL=0；write_scope 由 WARN 降级 | ✅ **FAIL=0**；WARN 11→6、INFO 0→6（5 advisory + 1 统计） |
| 4 | `--determinism` 不改 schema；14 条历史仍不可判定 | ✅（determinism 是独立 CLI 输出；mode_policy 仍 WARN 14） |
| 5 | r2 收据存在、steward_self_audit INFO、sha 可复算 | ✅（`standards-sha.txt` 4/4 MATCH） |
| 6 | 删除<插入；报告落 artifacts | ✅（numstat 见提交；本目录） |

---

## 4. 诚实边界

1. **determinism 是 CLI 自证，不是每条审计都跑**：收据里的 determinism 字段表示"当时跑过并通过"，
   不是"每次审计都被强制"。若要强制，需把它接入收据校验（属新条款，未做）。
2. **write_scope 仍只看声明**：两个任务实际写同文件但声明不同 ⇒ 检查看不见（P2 的 `git show --name-only` 反查未实现，SF-015 part ③）。
3. **mode_policy 的 14 条历史 spawn 永久不可判定**（append-only 不回改）；只能证明今后可判定。
4. **3 条根=根 WARN 保留**（不为了让数字好看而降级）——它们恰好是 §1.2b 想禁止的"共享根直接作写域"。
5. **自建任务**：Lead 未在等待窗口内响应，条款 commit = 批准，事后已获追认；本报告与任务描述均披露。

## 5. 复跑

```powershell
python scripts/agent/team_audit.py --selftest
python scripts/agent/team_audit.py --determinism
python scripts/agent/team_audit.py          # FAIL=0, steward_self_audit=INFO
python scripts/agent/work_record.py doctor
python scripts/agent/decide.py check
```
