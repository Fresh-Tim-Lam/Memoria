# S10 冻结记录（Freeze Record）

> **冻结对象**：`docs/design/multilevel-graph/S10-kp-v1.md`（12 条规范 + R-S10-1..5 + S10a）。
> **冻结时间**：2026-11-04T08:26+08:00（Asia/Shanghai）。
> **决策**：`dec-20261104-542c2dd4`（Lead；S0–S9 已冻结）。
> **状态**：**已冻结**。**S0–S10 全部冻结**；0.5 实现可全面启动；S10 本体不在 0.5。

## 1. 冻结产物与身份

| 产物 | 角色 | sha256 |
|---|---|---|
| `S10-kp-v1.md`（**冻结稿最终态**） | S10 唯一规范来源 | `a5db0f1cd99ac69c6d66d772b9aab0b676e53fa8b8d01f323516e29ca1e8809e` |
| `S10-engineering-check.md` | SE 工程校核 + S10a | `856359a6…` |
| `S10-kp-proposal-A-v2.md` | 证据链（主办研究） | `db71ccd4…` |
| `S10-kp-proposal-B-v2.md` | 证据链（独立复核） | `48d8760d…` |
| `S10-objections-v2.md` | 差异/异议 | `22238f80…` |
| `S10-RULINGS.md` | Lead 裁决（R-S10-1..5） | `9818d0fd…` |
| `S6-ADDENDUM-2.md` | 错误码扩展（KP/边/curation） | `—` |
| `ENGINEERING-PLAN.md`（S10a） | 33 图（ER-11/DF-11/ST-11） | `aa37655c…` |

**冻结轮次**：两版无 P0；第一轮 3 条 P1（语义边缺 contain(semantic)、`S10_*` 命名空间、D-3 写路径）裁决后 v2 全关闭；SE M-S10-1..12 全 PASS、33 图 `PARSE_OK`；Lead 独立机检 PASS。

## 2. S10 冻结了什么（一句话版）

1. **边界**：agent 只写 KP/语义边/curation **提案**；不写事实正文/文件/sidecar；人工确认；`propose_write` 唯一入口；**0.5 不做**；
2. **KP**：定义/粒度/字段（kp_id/title/alias/summary/file/range/section_ref/tags/evidence/confidence/status）；`kp_id` 全局唯一；默认单 section/不重叠；嵌套 future；
3. **抽取**：只读 md/sidecar；证据锚；无源不生成；低置信不 apply；幂等/去重；
4. **语义边**：`type∈{contain,reference,extend}`；`contain_kind∈{structural,semantic}`；`E_sem=(contain∧semantic)∪(reference|extend∧label=semantic)`；结构/引用不冒充；`direction∈{source_to_target,both}`，`both` 物化两条有向边；证据/置信/理由；
5. **双引用/curation**：`Provenance{source,target,assertion_source,evidence_refs,curated_by/at,decision_id}`；人工确认；undo；审计；
6. **写路径（D-3）**：agent 只 `propose_write`（plan/evidence/dry-run/影响面）；apply 由**产品 curation writer** 人工确认后执行 `plan→approval→backup→atomic apply→undo/audit`；graph/agent 无 sidecar/正文写；失败零写入；批处理回滚；
7. **冲突/合并**：冲突类/去重/合并保留 canonical+alias+history/redirect；人工裁决；历史不删；
8. **版本/失效**：写后 edition 变化 ⇒ S9 失效/重建、S2 新 run；旧 KP/边/审计保留；`expected_edition` CAS；backup 回滚；
9. **质量**：`Q-EVIDENCE=100%`、`Q-SEM-PURITY=1.0` P0；`Q-KP-P/R`、`Q-EDGE-P/R`、`τ=0.6` 为 soft；golden `docs/design/multilevel-graph/golden/S10-golden-set.json`；`scripts/verify/eval-kp.py`；`GATE-KP`；2× 确定性；人工抽检；
10. **S1/S2**：KP 目录/KP_HISTORY 独立于 S1 维度 registry（只读）；写语义边后 S2 重算；多归属合法；
11. **失败/隐私**：无源/歧义/低置信/冲突/超预算/PII 可见拒绝；不自动 apply；正文只读；错误码统一 `GRAPH_*` + `S6-ADDENDUM-2`；
12. **0.5 边界**：S10 不在 0.5；无写工具/自动 semantic；未来版本 + 人工确认 UI 才 apply。

## 3. 机检与证据

- SE M-S10-1..12 全 PASS（`M_fail=[]`）；S10a：ER-11/DF-11/ST-11，mermaid 11.16.0（`9198f632…`）**33 图 `PARSE_OK`**；
- 与 S0–S9 一致性：S0 E_relation_min/D-3、S1 registry、S2 五状态/多归属、S3–S6、S7 只读、S8 G6/G7、S9 edition/检索 — 全 PASS；
- Lead 独立机检 PASS。

## 4. 未关闭项（不阻塞冻结）

- O-S10-1..6：P/R/τ 校准、both 去重、合并迁移、curation 并发、PII 抽样、ADDENDUM-2 登记补齐。

## 5. 变更控制

- 加字段/指标/阈值：S10 修订 + 决策；删/改 KP 定义/语义边语义/写边界：重开 S10；阈值校准写回修订（不重开）。

## 6. 下一步

- **S0–S10 全部冻结** ⇒ 0.5 实现按 S6a I-01..I-13 + S8 DoD + S9 检索契约；
- S10 进入未来版本 roadmap（人工确认 UI 才 apply），不在 0.5。
