# Phase 5 冻结审计收据（steward，过程审计）

> **审计对象**：`artifacts/agent/verify/debate/` 冻结产物（commit `48ca704e`，worktree clean）
> **审计者**：steward；**时间**：2026-10-25T00:5x+08:00
> **口径**：只验"过程是否可审计、可复算、可申诉"；不评架构内容。
> **结论**：**冻结基本成立**（pinned sha 9/9 一致、26 条裁决全部可追、辩论产物已进 git）；
> 有 **7 条 finding**（2 条建议在架构辩论开始前修掉，其余进入 `deliberation_quality` v0 的输入）。

---

## 1. 检查表

| # | 检查 | 结果 | 证据 |
|---|---|---|---|
| C1 | `PINNED-PROPOSALS.json` 9 个 sha256 与磁盘一致 | **PASS 9/9 MATCH** | 复算 sha（proposals ×4 + objections ×4 + protocol-v1） |
| C2 | 冻结物满足 F1（question / acceptance_criteria / standards / expected_categories） | **FAIL**：`standards: []` 为空 | `freeze-v2.json:14` |
| C3 | 26 条裁决均带 `falsifiers` | **PASS**（26/26 非空） | `ruling/rulings.jsonl` |
| C4 | 被驳回立场带 `unique_evidence_handled` | **PASS（语义）**：仅 R-C7 有 rejected，2 条均 `unique_evidence_handled:true`；其余 25 条 `rejected: []` | R-C7 |
| C5 | 每方异议都有对应裁决 | **PASS（计数）**：agent-arch 11 / arch-contract 7 / metrics 6 / steward 12（含联合）；与 PROTOCOL §11 的 19 异议 + 4 CONFLICT + N1 对得上 | `rulings.jsonl` |
| C6 | PROTOCOL 规则可溯源、Lead 自创 = 0 | **PASS（抽检 5/5）**：E1'/E4.2/E4.3/B6/§7 override 均能指到提案或 ruling | `PROTOCOL.md §9/§11` |
| C7 | 裁决的 `supporting_evidence` 可解析 | **1 处畸形**：R-C21 的 `ev:file:.gitignore（含 artifacts/）` 不是合法 source_identity | R-C21 |
| C8 | 辩论产物进 git（J6'） | **PASS**：15/15 文件 tracked，worktree clean（commit `48ca704e`） | `git ls-files` |
| C9 | 任务板 task-113 关闭条件 5：`debate/SUMMARY.md` | **FAIL**：该文件不存在 | 目录仅 15 文件，无 SUMMARY.md |
| C10 | J4 少数意见单独建档 | **PASS（可接受）**：rejected 原文在 objections 中（pinned + git）+ R-C7 内嵌；无独立 `rejected-objections/` 文件，但原文未丢 | 目录结构 |

---

## 2. findings（按影响排序）

| id | 严重度 | finding | 修法（建议） |
|---|---|---|---|
| **F-1** | **高** | **F1 仍有缺口**：`freeze-v2.json` 的 `standards` 为空数组 ⇒「冻结标准版本 sha256」没做到。后续裁决若引用标准（如 L9/L10、lessons L9.6）无法证明"按哪一版判" | Phase 6 前补 5 个标准的 **LF 归一化 sha256**：AGENTS.md `6c87fe55…`、rules `488d7ebd…`、lessons `f2f86b09…`、org `fd91c21f…`、team_audit.py `e6f16ef1…`（命令：`python -c "hashlib.sha256(open(p,'rb').read().replace(b'\r\n',b'\n'))"`） |
| **F-2** | 中 | **`unique_evidence_handled` 的 schema 未定**：只有 R-C7 有（作为 `rejected[]` 内 per-item bool）；其余 25 条没有该键。机器无法区分"无需处理"与"漏写" | 冻结协议补一句：**每条 ruling 必须有 `unique_evidence_handled`（无 rejected 时为 `[]`）**；或 `deliberation_quality` 只对 `rejected` 非空时要求 per-item 字段（并在协议里写死"per-item"还是"top-level"） |
| **F-3** | 中 | **异议→裁决 的映射是隐式的**：objection 文件里没有 `object_id`，ruling 里没有 `objection_ids` ⇒ "每条 object 都有裁决"目前靠人核对，无法机检 | 异议文件每条加 `object_id: OBJ-<member>-<n>`；rulings 加 `objection_ids: [...]`；或生成 `ruling-index.json {object_id → ruling_id}` |
| **F-4** | 中 | **PROTOCOL 规则索引是 markdown 表格**：45 条规则的 `source_refs` 无法机读，"Lead 自创=0"只能人工抽检 | Phase 5 产物补 `rules-index.json`：`[{rule_id, text_sha, source_refs[]}]`，`deliberation_quality` 可核对 |
| **F-5** | 低 | 裁决内 1 条证据身份畸形（R-C21 的 `ev:file:.gitignore（含 artifacts/）`）——违反 E1 自己的"身份必须可解析" | 改为 `ev:file:.gitignore#L15`（把说明移到 note 字段） |
| **F-6** | 低 | **J6' 提到 `evidence_ledger`，但本轮未产出**（协议辩论本身未建台账；PROTOCOL §0 的 5 类配套文件也不含它） | 在 PROTOCOL 写明「`evidence_ledger` 自**架构辩论**起强制」；或本轮补一份（把 26 条裁决的 supporting_evidence 汇总成 ledger 即满足） |
| **F-7** | 低 | task-113 关闭条件 5 的 `debate/SUMMARY.md` 缺失（PROTOCOL.md 事实上承担了报告角色，但条件写的是 SUMMARY） | 补一份短 `SUMMARY.md`（指向 PROTOCOL + rulings + pinned），或由 Lead 在任务完成说明里显式豁免该文件名 |

---

## 3. 对 `deliberation_quality` v0 的建议判据（下一任务用，先条款后检查）

> 原则沿用 task-103/109：每条判据先有条款、每个检查先有必红 fixture；**只查结构，不判语义**。

| 候选检查 | 依据 | 初始级别 |
|---|---|---|
| dq1 `ev:` 身份可解析（kind 合法 + `doc/file/commit` 目标存在 + 无中文括号等畸形） | E1 | WARN（首周）→ FAIL |
| dq2 `rejected` 非空时，每条必须有 `unique_evidence_handled`（且值 ∈ accepted/rejected/deferred+理由） | J2' | **FAIL** |
| dq3 每条 ruling 有非空 `falsifiers` | J3 | **FAIL** |
| dq4 每条 claim 有 `supporting_evidence_ids` 且可解析 | J1 | **FAIL** |
| dq5 `freeze.standards` 非空且 sha 与磁盘 LF 归一化一致；`PINNED-PROPOSALS` sha 一致 | F1/F2'/O3/O4 | **FAIL** |
| dq6 `artifacts/agent/verify/debate/**` 必须被 git tracked（J6'） | J6' | **FAIL** |
| dq7 异议 object_id ↔ ruling objection_ids 全覆盖 | F-3 | WARN（schema 未落地前） |
| dq8 同一 `independent_group` 的证据引用超过 1 份却报"多方一致/多票" | E2/M2 | WARN |
| dq9 `unknowns/not_doing` 每条有 `if_true_then`；`checked/not_examined/out_of_scope` 并集 = `expected_categories` 且两两不相交 | P2/P4 | WARN |
| dq10 状态：`deferred` 超期未处理 | J2' | WARN |

**不可机检（写进盲区）**：`unique_evidence` 是否真 unique、共享假设是否"合理"、"证据是否足以支撑结论"——语义判断，交评审/人。

---

## 4. 复跑命令

```powershell
# pinned sha 复算
python -c "import json,hashlib,pathlib; b=pathlib.Path('artifacts/agent/verify/debate'); p=json.loads((b/'PINNED-PROPOSALS.json').read_text(encoding='utf-8')); [print('MATCH' if hashlib.sha256((b/k).read_bytes()).hexdigest()==v['sha256'] else 'MISMATCH', k) for k,v in p['files'].items()]"
# 裁决完整性
python -c "import json; rows=[json.loads(l) for l in open('artifacts/agent/verify/debate/ruling/rulings.jsonl',encoding='utf-8') if l.strip()]; print(len(rows), 'missing falsifiers:', [r['ruling_id'] for r in rows if not r.get('falsifiers')])"
# git 追踪
git ls-files artifacts/agent/verify/debate | wc -l
```
