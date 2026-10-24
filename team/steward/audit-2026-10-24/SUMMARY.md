# steward 首轮真实审计（2026-10-24）

> **审计者**：steward2（flash，实例三）；**审计时间**：2026-10-24 20:1x +08
> **收据**：同目录 `standards_read.json`（四标准 sha256）/ `findings.jsonl`（13 条，append-only）
> **本报告口径**：只报能指到现行条款的事实；指不到的只能标 `proposal`。**steward 不阻断**（阻断权在机检/人）。

---

## 1. 八步执行记录（设计稿 §6.1）

| 步 | 动作 | 产物/结果 |
|---|---|---|
| 1 | 新鲜度：确认快照 `exportedAt=2026-10-24T12:06:52Z` 晚于 agents.json/org.md mtime | ✅（`role_registration` = INFO，三方 9/9/9） |
| 2 | 重读标准（记 sha256，禁缓存） | `standards_read.json`：AGENTS.md §0.5 `6c87fe55…` / lead-dispatch-rules `df3580bb…` / lessons `fb8ca896…` / team_audit.py `cedd8309…`（**本报告提交时**） |
| 3 | 跑机检 `python scripts/agent/team_audit.py` | FAIL=0（steward_self_audit 首轮自审通过）；WARN/INFO 见 §3 |
| 4 | 跑工作记录投影 `work_record.py doctor` + 四条查询 | doctor PASS（decisions OK；trajectory WARN）；`task-87/95/96/97`、`member steward2`、`decision --grep`、`risk --since 7d` 全部有产物（见 `artifacts/agent/verify/steward/task-101/`、`task-102/`） |
| 5 | 产出三件收据 | `standards_read.json` / `SUMMARY.md`（本文件）/ `findings.jsonl`（13 条）+ 累积 `team/steward/findings.jsonl` |
| 6 | finding 处置 | FAIL 级 0 条（本轮无 FAIL）；WARN 已分级：`mechanized` 3 / `fixed` 5 / `open` 2 / `proposal` 3（见 §2） |
| 7 | 转换：可机检的固化成新检查 | 本轮新增 3 个 P1 检查：`decision_trail`（task-103）/ `model_policy`（task-103）/ `steward_self_audit`（task-103）；另有 task-100 四类已上线 |
| 8 | 自审 `steward_self_audit` | 首轮真实数据 = INFO；两个负例（改 sha / 非法 rule_ref）均实测 FAIL（见 `artifacts/agent/verify/steward/task-103/negative-proofs.txt`） |

---

## 2. findings（13 条，完整结构化记录见 `findings.jsonl`）

| id | 严重度 | 问题 | rule_ref | disposition |
|---|---|---|---|---|
| SF-001 | WARN | 0.4.7 实施提交早于台账计划落盘（a68ab655 10-23 13:19 < 计划 10-23 22:52） | `AGENTS.md#0.5 L8` | **mechanized**（`team_audit.py::plan_consulted`） |
| SF-002 | WARN | 近 7 天 12 个改动文件全仓无外部引用（benchmark 一次性探针） | `agent-team-lessons.md#L0.3` | open（待 Lead/人三选一） |
| SF-003 | WARN | dispatch-log 14 条 spawn 全缺 mode 字段，模式决策无法判定 | `AGENTS.md#0.5 L9` | open（task-107） |
| SF-004 | WARN | 近 14 天 39 个 T1/T3 触发提交中 37 个缺 Decision/Why（宽限期内） | `lead-dispatch-rules.md#6.5` | open（宽限至 2026-11-07） |
| SF-005 | — | task-98 前快照早于 org.md 修改 | `agent-team-org.md#2.3` | fixed（快照已重导出） |
| SF-006 | — | G1 决策理由不可查询 | `AGENTS.md#0.5 L10` | fixed（decide.py + decisions.jsonl + work_record） |
| SF-007 | — | G2 任务档案缺 description/evidence/时间戳 | `agent-team-org.md#2.6 B1` | fixed（work_record task） |
| SF-008 | — | G3 快照时效无审计前门禁 | `agent-team-org.md#2.3` | **mechanized**（doctor + role_registration） |
| SF-009 | — | G4 动作层缺失（无 trajectory） | `agent-team-org.md#2.6 B2` | open（task-95） |
| SF-010 | — | G5 角色注册非原子（实测三处不同步 FAIL=3） | `agent-team-org.md#2.3` | **mechanized**（role_registration） |
| SF-011 | WARN | lead-dispatch-rules 两个 §6 重号 | **无现行条款** | **proposal**（Lead 已修，4bbd7685） |
| SF-012 | WARN | A2 时效窗口精确值未写进条款 | **无现行条款** | **proposal**（Lead 裁决保留为实现常量） |
| SF-013 | — | steward 无 standards_read 收据机制 | `agent-team-org.md#2.6 B3` | fixed（本轮首次产出） |

**转换率（本轮）**：WARN 级 finding 6 条中 **2 条已固化为机检**（SF-001/SF-008；SF-010 的检查在 task-100 上线，本轮登记）。
**"同一个问题只应发生一次"** 的当前证据：G5（注册漂移）与 G3（快照时效）现在都由 `role_registration` 自动捕获，不再依赖人抓。

---

## 3. 机检现状（本轮跑出，非转述）

- `team_audit.py` **FAIL=0**；WARN 48 / INFO 13（其中 4 条 WARN 是 §2 的 open/proposal finding，其余为既有基线）。
- 新检查实跑：
  - `decision_trail`：39 个触发提交 / 37 个缺 trailer（**宽限期 WARN**，非 FAIL）；**抽取到 2 个合规决策提交**（`4bbd7685`、`eb803b1c` —— Lead 从条款落地起就在写 trailer）。
  - `model_policy`：10 名成员全部 `deepseek-flash`（INFO）。
  - `steward_self_audit`：本收据自审 **INFO**。
- `work_record.py doctor`：PASS（decisions 2 条校验通过；trajectory 缺失 WARN 已作为 SF-009）。
- `decide.py check`：PASS（2 条决策 / bad=0）。

---

## blind_spots（本轮**没有**审计什么，以及为什么）

1. **动作层（trajectory）不存在** ⇒ 「写文件前没读」「门禁失败后继续」「重试次数」这三类过程问题**完全不可见**（task-95 未落地）。这是本轮最大的盲区，已登记 SF-009。
2. **session 正文未读**（42MB，按设计不读；只允许在报告中引用 `session:<id>#turn=N`），因此「Lead 当时怎么想的」只能靠决策索引，索引没记的就是盲区。
3. **`decision_trail` 口径是条款的可判定子集**：只机检 T3（版本/Package/发布/回退）与 T1（组织资产/规范）；**T2 判断类（有备选被否）无法机检**，普通 `src/**` 提交不计触发（否则几乎每提交都要 trailer = 假红灾难）。这是口径声明，不是"已全覆盖"。
4. **`dead_path_edit` 的引用检索含文档引用**（设计字面口径）；"文档提过但代码无入口"的文件不会报出。收紧为代码引用会报 35 个（噪声大），需先补 `@entry` 清单 ⇒ 列为后续提案，不擅自改判据。
5. **未审计产品代码质量/性能**（`src/**` 只读且不属于 steward 职责）；`docs/todo.md §13` 台账本轮只抽读，未逐条复核。
6. **`role_registration` 只覆盖三方全等与快照时效**；「同名重生/代次解析」这类插件层问题不在文件比对范围内（已由 team-plugin-creator 的插件测试覆盖）。
7. **R0/R1 对抗复核（A5）尚无机检**：依赖 `decision_trail` 后续扩展 + 非决策者轮值，本轮未跑。

---

## 4. 本轮新增的"被批准条款 → 新机检"对照（"真正的产品"）

| 条款（已落地） | 新机检 | 状态 |
|---|---|---|
| `AGENTS.md §0.5 L10` + `lead-dispatch-rules §6`（决策记录义务、宽限期） | `decision_trail` | ✅ 本轮上线（WARN 宽限至 2026-11-07） |
| `org.md §2.1 维护纪律 6`（统一 flash + model_exemption） | `model_policy` | ✅ 本轮上线（当前 INFO 全绿） |
| `org.md §2.6 B3/B4`（standards_read 收据 + finding 生命周期） | `steward_self_audit` | ✅ 本轮上线（自审 INFO；两个负例必红） |
| `org.md §2.3 执行纪律 1`（注册 = 改 3 处 + 重导出快照） | `role_registration` | ✅ task-100 已上线（本轮实测 INFO） |
| `AGENTS.md §0.5 L8`（规划先于实施） | `plan_consulted` | ✅ task-100 已上线（本轮报出 0.4.7，SF-001） |

规则：**新检查必须挂在已批准条款上**；本轮 3 个检查的 rule_ref 均已在文档中可解析（见 findings.jsonl）。

---

## 5. 复跑与自证

```powershell
python scripts/agent/team_audit.py --json            # 含 steward_self_audit
python scripts/agent/team_audit.py --selftest        # 三个 P1 检查各有必红 fixture
python scripts/agent/work_record.py doctor
python scripts/agent/decide.py check
```

- 负例自证（`artifacts/agent/verify/steward/task-103/negative-proofs.txt`）：
  ① 篡改 `standards_read.json` 的 sha256 ⇒ `steward_self_audit` **FAIL**（用缓存标准）；
  ② 插入 `rule_ref` 不可解析且非 proposal 的 finding ⇒ **FAIL**（把偏好当规范）。
