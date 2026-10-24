# steward 第二轮真实审计（2026-10-24 · r2）

> **审计者**：steward2（flash，实例三）；**轮次**：r2（标准变更后重审计）
> **触发**：Lead 提交 `d95712e3`（§5.4 机检确定性 / §1.2b 写域到产物级 / §1.3b 显式未决定）
> 后，首轮收据（`audit-2026-10-24/standards_read.json`）的 4 个 sha 中 3 个已过期 ⇒
> `steward_self_audit` 按设计 FAIL=3。**处置：不动首轮收据（append-only），重读标准写 r2。**
> **收据**：同目录 `standards_read.json`（新 sha，含 determinism 结果）/ `findings.jsonl`（累计 24 条）
> **本报告口径**：只报能指到现行条款的事实；指不到的只能标 `proposal`。**steward 不阻断**。

---

## 1. 八步执行记录（设计稿 §6.1）

| 步 | 动作 | 产物/结果 |
|---|---|---|
| 1 | 新鲜度 | 快照 `exportedAt` 晚于 agents/org mtime；`role_registration` = INFO（三方一致） |
| 2 | 重读标准（记 sha256） | 新收据：AGENTS.md `6c87fe55…` / rules `488d7ebd…` / lessons `f2f86b09…` / team_audit.py `e6f16ef1…`（**4/4 与磁盘一致**） |
| 3 | 跑机检 | `team_audit.py` FAIL=0；`--determinism` **PASS**（两次运行除 `generatedAt` 外逐字节一致，sha `126140b4…`） |
| 4 | 工作记录投影 | `work_record.py doctor` PASS；`decide.py check` PASS（3 条决策；新增 `dec-20261024-d7a3e0eb`） |
| 5 | 产出三件收据 | `standards_read.json` / `SUMMARY.md` / `findings.jsonl`（累计 24 条）+ 追加 `team/steward/findings.jsonl` |
| 6 | finding 处置 | 24 条：mechanized 6 / fixed 10 / open 5 / proposal 3（0 条 FAIL 级） |
| 7 | 转换：可机检的固化成新检查 | 本轮 3 条：`--determinism`（§5.4）、`write_scope` 分级（§1.2b）、`mode_policy` 显式未决定（§1.3b） |
| 8 | 自审 `steward_self_audit` | FAIL=3 → **INFO**（重读标准后自然转绿，未改首轮收据） |

---

## 2. 本轮新增 finding（SF-017…SF-024，完整见 `findings.jsonl`）

| id | 严重度 | 结论 | rule_ref | disposition |
|---|---|---|---|---|
| SF-017 | WARN | §5.4 落地：`--determinism` 连跑两次归一化后逐字节一致 | `rules#5.4` | **mechanized** |
| SF-018 | WARN | §1.2b 落地：write_scope 分级；WARN 11→6、INFO 5（共享根 vs 子路径） | `rules#1.2b` | **mechanized** |
| SF-019 | WARN | §1.3b 落地：`modeExplicit=false` 单列「显式未决定」，历史 14 条仍如实报不可判定 | `rules#1.3b` | **mechanized** |
| SF-020 | WARN | SF-002 处置：12 探针已归档（`f5c3fcbb`）；旧引用失效属历史不可逆，不修 | `lessons#L0.3` | fixed |
| SF-021 | WARN | SF-011 闭环：重复 §6 已修（`4bbd7685`，依据我的 proposal） | `rules#6` | fixed |
| SF-022 | WARN | D2 决策层首次真实使用：`dec-20261024-d7a3e0eb`（A2 强制 reconstructed；evidence=commit） | `AGENTS.md#0.5 L10` | fixed |
| SF-023 | WARN | 「标准变 ⇒ 重审计」机制自证：FAIL=3 → INFO，未改首轮收据 | `org.md#2.6 B3` | fixed |
| SF-024 | WARN | 3 条残余 WARN：task-86/94/107 **直接声明共享根** `artifacts/agent/verify`（§1.2b 应写到子目录或写理由） | `rules#1.2b` | open |

---

## 3. 机械化的证据（"真正的产品 = 条款 → 新机检"）

| 条款（已 commit） | 机检 | 自证 |
|---|---|---|
| `rules §5.4` 机检确定性 | `team_audit.py --determinism` | `--selftest` 归一化/差异定位红绿 fixture + 真跑 PASS |
| `rules §1.2b` 写域到产物级 | `write_scope` 分级 | fixture：共享根 vs 子路径 ⇒ INFO；同文件 ⇒ WARN；真实数据 11 WARN → 6 WARN + 5 INFO |
| `rules §1.3b` 显式未决定 | `mode_policy` 分离 | fixture：缺字段/显式未决定/带 mode 三类分别断言；真实历史 14 条仍 WARN |

**write_scope 前后实测**（`audit-before.txt` vs `audit-after.txt`）：
```
before: 11 findings, 11 WARN, 0 INFO
after : 12 findings, 6 WARN, 6 INFO（5 条 §1.2b advisory + 1 条统计）
残余 WARN 6 = 2 同文件（task-85↔91）+ 1 services 子树（task-85↔92）+ 3「两个任务都声明同一共享根」（SF-024）
```
> 与 Lead 预期「11→3 WARN + 8 INFO」的差异已如实说明：不是 8 条共享根 vs 子路径，而是 **5 条**（其余 3 条是"根 = 根"，按 §1.2b 是真违规候选，保留 WARN）。

---

## 4. 当前机检基线（本轮亲跑）

- `team_audit.py`：**FAIL=0**，WARN 47 / INFO 21（含 `mode_policy` 历史 14 条不可判定 WARN）
- `team_audit.py --determinism`：**PASS**（sha256 `6ded0c4c…`，compared_findings=68）
- `work_record.py doctor`：PASS（decisions 3 条；trajectory 仍 WARN）
- `decide.py check`：PASS

> 注：r2 收据写入后，又追加了一条 proposal `SF-20261024-025`（收据 sha 的 LF/CRLF 归一化口径缺失，
> 会在重新 checkout 时制造假红）——它只进累积 `team/steward/findings.jsonl`（24→25 行），
> r2 目录内的 findings 快照按 append-only 保持 24 条，**下一轮审计**再纳入。

---

## blind_spots（本轮没审计什么，以及为什么）

1. **动作层（trajectory）仍是盲区**：task-95 已交付但未部署（需重建 DSH），三类过程问题不可见。
2. **T2 判断类不可机检**：`decision_trail` 只覆盖 T1/T3 可判定子集；"有备选被否"的决策无法从提交结构判定。
3. **`--determinism` 是 CLI 自证，不是每条审计都跑**：确定性只在显式调用时被证明（避免每次审计翻倍耗时）；若有人绕过不跑，收据里的 determinism 字段只是"当时跑过"。
4. **write_scope 仍只看"声明"**：两个任务实际写同一文件但声明不同 ⇒ 检查看不见；P2 建议用 `git show --name-only` 反查（proposal SF-015 的 part ③，尚未机检）。
5. **session 正文未读**：决策理由只能来自 decisions.jsonl/commit trailer，索引没记的就是盲区。
6. **`mode_policy` 的 14 条历史 spawn 不可判定**：append-only 不能回改；只能证明"今后可判定"。
7. **未审计产品代码质量/性能**（`src/**` 只读，不属本角色）；`§13` 台账仅抽读。

---

## 5. 与首轮的关系（append-only 证明）

- 首轮目录 `audit-2026-10-24/` **未修改**（standards_read.json 旧 sha 保留，作为"过期收据"证据）；
- 新 finding 追加到 `team/steward/findings.jsonl`（16 → 24 行，只增不删）；
- 机检取**最新** audit 目录（按名称排序，r2 在其后）⇒ 自审转 INFO。

## 6. 复跑

```powershell
python scripts/agent/team_audit.py --selftest
python scripts/agent/team_audit.py --determinism
python scripts/agent/team_audit.py
python scripts/agent/work_record.py doctor
python scripts/agent/decide.py check
```
