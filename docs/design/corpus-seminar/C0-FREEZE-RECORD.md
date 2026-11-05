# C0 冻结记录（Corpus Design Freeze）

> **冻结对象**：`docs/design/corpus-seminar/C0-corpus-v1.md`（C1–C12 + R-C0-1..6 + C0a）。
> **时间**：2026-11-05（Asia/Shanghai）。
> **决策**：`dec-20261105-2fcf4d1d`（Lead）。
> **状态**：**C 系列已冻结**；**0.5 仍 HOLD**；下一步 pilot。

## 1. 冻结产物

| 产物 | 角色 | sha256 |
|---|---|---|
| `C0-corpus-v1.md` | C0 唯一规范来源 | `080d08609d14b4dcf07cac3bf24f96caf59335edf819ea24afad8c9f608e4e08` |
| `C0-RULINGS.md` | Lead 裁决 R-C0-1..6 | — |
| `C0-proposal-A-v2.md` | 证据链（主办研究） | `fc9a927a…` |
| `C0-proposal-B-v2.md` | 证据链（复核） | `125429dc…` |
| `C0-objections-v2.md` | 差异/异议 | `ee01ef16…` |
| `C0-engineering-check.md` | SE 工程校核 | — |
| `C0-URL-VERIFY.json` | URL 核验（30 PASS/5 FAIL/3 BLOCKED） | `851a6fe2…` |
| `C0-URL-DISPOSITION.md` | 失败项处置 | — |
| `C0-LEAD-CHECK.md` | Lead 独立机检 | — |
| `ENGINEERING-PLAN.md` | 36 图（ER-12/DF-12/ST-12） | `a032c67a…` |

## 2. C0 冻结了什么

1. **C1**：学习者/教师+agent；开放许可教材 1 章 pilot；三层成功标准；
2. **C2**：Tier A 可发布 / Tier B 仅内部评测隔离 / Tier C 禁用；逐文档 license/SPDX/redistribution/DB-right/fair-use/PII；Presidio+人工；Tier B 不进发布包/golden；
3. **C3**：Document/Section/KP/Cluster；关系仅 S0 `E_relation_min`；SKOS 仅注释；E_sem 门槛；
4. **C4**：KP=单文件连续 span；概念+1–3句/单 section/不重叠；pilot 试命题级；
5. **C5**：先 KP 后边；30+正/30+负/20+边界；A/B/C 裁决；培训+试标；
6. **C6**：S0 三类型；direction 默认 source→target、both 物化两条；双端证据 span；置信三档；负例；
7. **C7**：pilot 1章/50 KP/30 边/20 query；主集 10章/500/300/100；按章隔离；edition；32 人时上限；
8. **C8**：100% 双人；span unitizing α/boundary F1，类型/方向 κ，边 tuple F1+裁决一致率；α/κ≥0.67、边 F1≥0.70（目标 0.8）；分指标报告；
9. **C9**：检索/链路/任务三层；GATE-RET 分型；graph 仅 semantic>0 适用；NA 不算通过；消融；禁聚合；
10. **C10**：隔离副本；INCEpTION/brat；JSONL/standoff/CoNLL-U/Croissant；schema/锚/许可/UTF-8；版本审计；不写用户 sidecar；
11. **C11**：S10 propose-only+人工确认+产品 writer apply；写后 edition→S9 失效；0.5 重跑五条件；
12. **C12**：语料快照+golden+手册+许可+数据卡+评测脚本+变更日志；owner/节奏/edition/废弃。

## 3. 机检

- SE M-C0-1..11 PASS；M-C0-12 按核心证据政策 PASS（30 核心 URL 核验；8 失败/阻断项删除/降级，不冒充 200）；
- unitizing α 6 tests、GATE-RET 契约、36 图 `PARSE_OK`；
- Lead 独立机检 PASS（见 `C0-LEAD-CHECK.md`）。

## 4. 未关闭（pilot 验证，不阻塞冻结）

O-C0-1 被删 URL 若需要再验；O-C0-2 真实 IAA/INCEpTION UTF-8；O-C0-3 教材许可锁定；O-C0-4 实际工时≤32 人时；O-C0-5 graph soft→hard。

## 5. 下一步

1. **pilot**：1 章 / 50 KP / 30 边 / 20 query，双人标注 + IAA + 裁决；
2. 达线后：0.5 重跑 GATE-RET（graph 分型适用且 recall@5≥0.80）→ 再讨论 0.5 发布；
3. 未达线：修订 C 系列/pilot 设计，0.5 继续 HOLD。

## 6. 修订：C0-AMENDMENT-1（evaluation-first，2026-11-05）

- C4/C5/C8/C9/C11 已由 `C0-AMENDMENT-1.md`（sha `1fc31cdc…`）替代；C0 v1 其余条款继续有效。
- 原因：人裁定人类 KP 切分不可靠/培训成本巨大；改为候选生成 + 问题证据 judge + 呈现/任务指标；不再要求 gold KP/人类 IAA。
- 语义边：仅在隔离 Tier-A 副本用 pilot-only harness；不写用户库/产品路径；0.5 仍 HOLD。
- 记录：`C0-AMENDMENT-1-FREEZE-RECORD.md`、`C0-AMENDMENT-1-RULINGS.md`、决策 `dec-20261105-d3030e4c`。

