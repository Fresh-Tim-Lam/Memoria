# C0 Lead 独立机检（冻结前）

> 日期：2026-11-05；对象：`C0-corpus-v1.md`（候选）+ A-v2/B-v2 + C0a。
> **结论：C 系列允许冻结；M-C0-1..12 PASS（M-C0-12 按核心证据政策），0.5 仍 HOLD。**

## 1. 复核方式

- 读 `C0-proposal-A-v2.md`、`C0-proposal-B-v2.md`、`C0-objections-v2.md`、`C0-RULINGS.md`、`C0-engineering-check.md`、`C0-URL-VERIFY.json`、`C0-URL-DISPOSITION.md`；
- 抽查 P1 关闭：SemEval `W09-2415`（HTTP 200 标题核验）、IAA 分型、许可三层；
- 抽查 C0a：unitizing α 测试、GATE-RET 契约、PLAN 36 图 `PARSE_OK`；
- 复核 8 个 FAIL/BLOCKED URL 的处置（不冒充 200，删除/降级为未核验背景）。

## 2. M-C0 结论

| 项 | 结论 | 依据 |
|---|---|---|
| M-C0-1 许可/Tier/隐私 | PASS | C0a + C2 Tier A/B/C；Tier B 隔离；PII |
| M-C0-2 本体/关系 | PASS | ER-12；S0 `E_relation_min`/E_sem |
| M-C0-3 KP 粒度 | PASS | 概念+1–3句；pilot 命题级变体 |
| M-C0-4 标注协议 | PASS | 30+/30+/20+；A/B/C 裁决 |
| M-C0-5 边证据/方向/负例 | PASS | S0 三类型；both 物化；证据 span |
| M-C0-6 规模/edition/32 人时 | PASS（规划；pilot 实测待验） | C7 |
| M-C0-7 IAA | PASS（合成实现；真实标注待 pilot） | unitizing α 6 tests |
| M-C0-8 评测 | PASS（契约；graph soft 至 pilot） | C0-GATE-RET |
| M-C0-9 工具只读/审计/UTF-8 | PASS（设计） | C10 |
| M-C0-10 S10/0.5 门槛 | PASS | C11 五条件 |
| M-C0-11 交付/维护 | PASS | C12 |
| **M-C0-12 URL/图** | **PASS（核心证据政策）** | 30 PASS；8 FAIL/BLOCKED 已处置；36 图 `PARSE_OK` |

## 3. M-C0-12 裁决

- **不采用“提案中每个 URL 都必须 200”**：反爬/出版商/标准组织会 403/202，强求会诱导造假；
- **采用核心证据政策**（`C0-URL-DISPOSITION.md`）：每个 C 项 ≥2 条 PASS 核心证据；失败项删除或标“未核验背景”，不参与裁决；
- `C0-URL-VERIFY.json` 保留失败记录；`C0-URL-DISPOSITION.md` 逐项处置；无 403/202 被写成 200。

## 4. 冻结前仍需 pilot 验证（不阻塞 C 冻结）

- O-C0-1 被删 URL 若 pilot 需要，再在可联网环境重验；
- O-C0-2 真实标注 IAA/INCEpTION UTF-8；
- O-C0-3 教材许可锁定（pilot 选书）；
- O-C0-4 pilot 实际工时（≤32 人时）；
- O-C0-5 graph soft→hard 切换（pilot 达线后）。

## 5. 结论

**C 系列冻结工程门禁 = 是**（SE M-C0-1..11 PASS + Lead 复核 M-C0-12 按核心证据政策 PASS）。
**0.5 仍 HOLD**：C 冻结只解决“怎么设计语料”，下一步是 pilot；pilot 达线后才重跑 GATE-RET 并讨论 0.5。
