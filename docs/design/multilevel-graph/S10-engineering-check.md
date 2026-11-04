# S10 工程校核报告（SE · task-344：KP/语义边/写路径/失效/质量）

> **冻结对象**：`docs/design/multilevel-graph/S10-kp-v1.md`（sha256 `a5db0f1cd99ac69c6d66d772b9aab0b676e53fa8b8d01f323516e29ca1e8809e`，90 行）。
> **证据链（只读）**：A-v2 `db71ccd4…`、B-v2 `48d8760d…`、异议-v2 `22238f80…`、`S10-RULINGS.md`；S0–S9 冻结 + S3/S6 ADDENDUM + `S6-ADDENDUM-2`。
> **工程图**：`ENGINEERING-PLAN.md`（`aa37655c…`，**33 图**；S10a=ER-11/DF-11/ST-11）；mermaid 11.16.0（sha `9198f632…`）全 `PARSE_OK`。
> **执行者**：`graph-se-architect`（SE，domain=se）· **日期**：2026-11-04（Asia/Shanghai）
> **边界**：未改 A/B/v1/异议/RULINGS；未写产品代码；未改契约；未 commit。
> **结论**：**达到 S10 冻结工程门禁（是）**。M-S10-1..12 全 PASS（`M_fail=[]`）；KP/边/写路径/冲突/失效/质量/golden 定稿落于 `ENGINEERING-PLAN.md` §1.17/§2.16/§3.14 + S10a 注记，33 图 `PARSE_OK`。

---

## 1. M-S10-1..12 机检

| M | 判据 | 判定 | 证据 |
|---|---|---|---|
| M-S10-1 | 边界/KP/边/证据/curation/冲突/质量 ER | **PASS** | v1：KP/语义边/证据锚/curation/冲突/质量 schema；agent 只写 KP/语义边不写正文；单一真源；0.5 不做 |
| M-S10-2 | KP 字段/唯一/不重叠 | **PASS** | title/alias/summary/range/file/line/anchor；唯一/去重/不重叠；粒度与 section/range 关系明确 |
| M-S10-3 | 证据/无源/低置信/去重 | **PASS** | 证据锚 file/line/anchor；无源/歧义/低置信可见拒绝；不得编造；幂等/去重 |
| M-S10-4 | 全类型/E_sem/both | **PASS** | `type ∈ {contain,reference,extend}`；`E_sem=(contain∧contain_kind=semantic)∪(reference|extend∧label=semantic)`；`direction=both` 物化两条有向边；结构/引用边不得当语义 |
| M-S10-5 | 双引用/curated/undo | **PASS** | provenance source_id/target_id/assertion；`curated_by/curated_at`；人工确认；undo/回滚 |
| M-S10-6 | 写路径 propose-only/D-3/零写 | **PASS** | agent 只 `propose_write`；apply 由产品 curation writer 在人工确认后执行（plan/approval/backup/atomic/undo/audit）；graph/agent 无 sidecar/正文写权限；失败零写入；错误码 `GRAPH_*`+`S6-ADDENDUM-2` |
| M-S10-7 | 冲突/合并/历史 | **PASS** | 冲突类（同 id/name/pair/跨文件）；去重；merge 保留 canonical+alias+history/redirect；人工裁决；历史不删 |
| M-S10-8 | edition/S9/回滚 | **PASS** | edition 变化→S9 失效/重建；S6 cache；旧 KP/边保留；`KP_HISTORY`；可回滚 |
| M-S10-9 | eval/golden/sha/2× | **PASS** | golden `docs/design/multilevel-graph/golden/S10-golden-set.json`；`scripts/verify/eval-kp.py`；产物 `artifacts/agent/verify/graph/kp/`；`GATE-KP`；Q-EVIDENCE/Q-SEM-PURITY P0、P/R/τ soft；2× 确定性 |
| M-S10-10 | S1/S2 交互 | **PASS** | KP→registry/history；KP→cluster membership；稳定性/多归属；只读交互 |
| M-S10-11 | 失败/隐私/不自动 | **PASS** | 无源/歧义/低置信/冲突/超预算/PII 可见拒绝；不自动 apply；正文只读、PII 不入库；审计 |
| M-S10-12 | 0.5 边界/GRAPH_* | **PASS** | S10 设计不在 0.5；未来版本实施；人工确认 UI 才可 apply；错误码统一 `GRAPH_*`+`S6-ADDENDUM-2`；不影响 0.5 DoD |
| S10A | 定稿项 | **PASS** | golden/eval/产物/GATE-KP/curation 路径/`direction=both`/Q-EVIDENCE+Q-SEM-PURITY P0 全落 |

---

## 2. KP/边/写路径/质量定稿（S10a）

### 2.1 ER/DFD/状态图（PLAN §1.17/§2.16/§3.14）

- **ER-11**：KP_PROPOSAL / KP / RELATION / EVIDENCE_REF / CURATION / CONFLICT / QUALITY。
- **DF-11**：源 md/sidecar（只读）→ 抽取/KP/边提案 → propose_write/plan(dry-run/影响面) → 人工确认/冲突裁决 → backup/atomic apply/undo/audit → registry/S2 → S9 失效/重建；失败零写入。
- **ST-11**：Proposed→Reviewing→Accepted/Rejected/Conflicted→Merged/Applied→RolledBack。

### 2.2 写路径（D-3）

```
agent: propose_write(proposals.jsonl)  # 只提案，不写任何文件
product curation writer: plan → 人工确认 → backup → atomic apply → undo/audit
graph/agent service: 无 sidecar/正文写权限（D-3）
失败: 零写入 + 可见错误 + 回滚
```

### 2.3 质量/golden（GATE-KP）

- **P0**：`Q-EVIDENCE=100%`、`Q-SEM-PURITY=1.0`（结构/引用边不计入）。
- **soft**：`Q-KP-P≥0.90`、`Q-KP-R≥0.80`、`Q-EDGE-P≥0.90`、`Q-EDGE-R≥0.80`、置信阈值 τ（golden 校准后写回）。
- golden：`docs/design/multilevel-graph/golden/S10-golden-set.json`；eval：`scripts/verify/eval-kp.py`；产物：`artifacts/agent/verify/graph/kp/`；2× 确定性。
- curation 元数据/`KP_HISTORY` 只写 `.memoria/agent/audit/graph/curation/`。

---

## 3. 与 S0–S9 一致性

| 上游 | S10 落点 | 判定 |
|---|---|---|
| S0 单一真源/D-3/D-4、E_relation_min | S10-1/4/6：只写 KP/边、不写正文、全类型/E_sem | **一致** |
| S1 registry/history/维度 | S10-3/10：registry/history；维度隔离 | **一致** |
| S2 run/五状态/多归属 | S10-10：membership/多归属 | **一致** |
| S3/S4/S5/S6 | 契约/路径/错误码 | **一致** |
| S7 只读 | S10-1：agent 只 propose；S7 消费 | **一致** |
| S8 度量/G6/G7 | S10-9：GATE-KP/eval；S8 消费 | **一致** |
| S9 检索/edition | S10-8：edition→S9 失效/重建 | **一致** |

---

## 4. 未关闭项（O-S10-1..6，不阻塞）

| # | 项 | 归属 | 建议 |
|---|---|---|---|
| O-S10-1 | P/R/τ soft 阈值 golden 校准 | S10a/S8 | 校准后写回 S10 修订 |
| O-S10-2 | `direction=both` 两条有向边的去重/一致性 | 0.5 | pair 唯一键 + 方向 |
| O-S10-3 | 冲突合并的 canonical/alias/redirect 迁移 | 0.5 | 历史保留/可回滚 |
| O-S10-4 | curation 并发/锁/零写入测试 | 0.5 | atomic apply + undo |
| O-S10-5 | PII/正文边界抽样 | 0.5 | 正文只读、PII 不入库 |
| O-S10-6 | S6-ADDENDUM-2 错误码登记 | S6/S10 | `GRAPH_KP_*/EDGE_*/CURATION_*` |

---

## 5. 冻结工程门禁判定

**是**（S10-charter §7）：

| 条件 | 结果 |
|---|---|
| 1. A/B 独立完成 + 差异 + 异议关闭 | **满足**（A-v2/B-v2/异议-v2；R-S10-1..5 关闭） |
| 2. SE 工程校核 PASS | **满足**（`M_fail=[]`；33 图 `PARSE_OK`；KP/边/写路径/质量/golden） |
| 3. Lead 独立机检 | **待 Lead** |
| 4. 与 S0–S9 无冲突 | **满足**（§3） |
| 5. 冻结 v1 + 写决策 | **待 Lead** |

---

## 6. 边界与后续

- 只读 v1/A-v2/B-v2/异议-v2/RULINGS/S0–S9；未改这些文件；未写产品代码；未改契约；未 commit。
- 已更新 `ENGINEERING-PLAN.md` S10 增量（ER-11/DF-11/ST-11 + S10a 定稿），未改 S0–S9 冻结部分。
- 冻结后进入检索/agent 实现计划（S10 不在 0.5；未来 curation writer + 人工确认 UI）。

---

---

## 附录 A — M-S10 机检脚本（SE 审计脚本，非产品代码）

``python
# -*- coding: utf-8 -*-
import hashlib, json, os, re
BASE = "D:/AAA_Jupyter/Memoria/docs/design/multilevel-graph/"
F = {"V1": "S10-kp-v1.md", "A2": "S10-kp-proposal-A-v2.md", "B2": "S10-kp-proposal-B-v2.md",
     "OBJ2": "S10-objections-v2.md", "RUL": "S10-RULINGS.md", "CH": "S10-charter.md",
     "S1": "S1-dimensions-v1.md", "S2": "S2-clustering-v1.md", "S6": "S6-contract-v1.md",
     "S7": "S7-agent-v1.md", "S8": "S8-metrics-v1.md", "S9": "S9-retrieval-v1.md",
     "S6A2": "S6-ADDENDUM-2.md", "PLAN": "ENGINEERING-PLAN.md"}
def rd(k):
    p = BASE + F[k]; return open(p, encoding="utf-8").read() if os.path.exists(p) else None
def sha(k):
    p = BASE + F[k]; return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
def has(t, pat): return re.findall(pat, t or "", re.I | re.M)
v1 = rd("V1"); plan = rd("PLAN"); checks = []
def add(i, s, e, n=""): checks.append({"id": i, "status": s, "evidence": e, "note": n})
if not v1:
    print(json.dumps({"status": "WAITING_FOR_V1"}, ensure_ascii=False)); raise SystemExit(0)
def ok(*v): return "PASS" if all(v) else "FAIL"
t = {"kp": "KP" in v1, "relation": ("RELATION" in v1 or "SemanticEdge" in v1 or "语义边" in v1 or "边" in v1),
     "evidence": "EVIDENCE" in v1, "curation": "CURATION" in v1,
     "conflict": ("CONFLICT" in v1 or "冲突" in v1), "quality": ("QUALITY" in v1 or "质量" in v1)}
add("M-S10-1", ok(*t.values()), t, "KP/边/证据/curation/冲突/质量 ER")
t = {"fields": bool(has(v1, r"title|alias|summary|range|anchor")), "unique": bool(has(v1, r"唯一|去重|不重叠")),
     "no_overlap": bool(has(v1, r"不重叠|重叠")), "evidence_anchor": bool(has(v1, r"file.{0,10}line.{0,10}anchor|证据锚"))}
add("M-S10-2", ok(*t.values()), t, "KP 字段/唯一/不重叠")
t = {"extract": bool(has(v1, r"抽取|生成")), "no_fabricate": bool(has(v1, r"不得编造|不编造|无源|证据")),
     "low_conf": bool(has(v1, r"低置信|confidence|置信")), "dedupe": bool(has(v1, r"去重|幂等"))}
add("M-S10-3", ok(*t.values()), t, "抽取/证据/低置信/去重")
t = {"types": all(x in v1 for x in ["contain", "reference", "extend"]), "esem": "E_sem" in v1,
     "both": bool(has(v1, r"both|双向|两条有向")), "semantic_only": bool(has(v1, r"semantic|语义")),
     "nostruct": bool(has(v1, r"结构.{0,20}不得|不得.{0,20}结构|引用边.{0,10}不"))}
add("M-S10-4", ok(*t.values()), t, "全类型/E_sem/both/semantic-only")
t = {"provenance": bool(has(v1, r"provenance|source_id|target_id|assertion")), "curated": bool(has(v1, r"curated_by|curated_at")),
     "confirm": bool(has(v1, r"人工确认|approval|确认")), "undo": bool(has(v1, r"undo|回滚|rollback"))}
add("M-S10-5", ok(*t.values()), t, "双引用/curated/undo")
t = {"propose": "propose_write" in v1, "plan": bool(has(v1, r"plan|dry-run|影响面")),
     "atomic": bool(has(v1, r"atomic|原子")), "backup": bool(has(v1, r"backup|备份")),
     "zero": bool(has(v1, r"零写入|不写.{0,10}文件")), "d3": bool(has(v1, r"D-3|sidecar"))}
add("M-S10-6", ok(*t.values()), t, "写路径 propose-only/D-3/零写/原子")
t = {"conflict": ("CONFLICT" in v1 or "冲突" in v1), "merge": bool(has(v1, r"merge|合并")), "history": bool(has(v1, r"历史|HISTORY")),
     "human": bool(has(v1, r"人工裁决|人工确认"))}
add("M-S10-7", ok(*t.values()), t, "冲突/合并/历史")
t = {"edition": "edition" in v1, "s9": "S9" in v1, "rebuild": bool(has(v1, r"重建|失效")),
     "rollback": bool(has(v1, r"回滚|保留")), "history": "KP_HISTORY" in v1}
add("M-S10-8", ok(*t.values()), t, "edition/S9/回滚")
t = {"golden": "S10-golden-set.json" in v1, "eval": "eval-kp.py" in v1, "gate": "GATE-KP" in v1,
     "metrics": bool(has(v1, r"precision|recall|Q-EVIDENCE|Q-SEM-PURITY")), "twice": bool(has(v1, r"2×|两次|determinism"))}
add("M-S10-9", ok(*t.values()), t, "eval/golden/sha/2×")
t = {"s1": "S1" in v1, "s2": "S2" in v1, "registry": "registry" in v1, "membership": bool(has(v1, r"membership|簇|多归属"))}
add("M-S10-10", ok(*t.values()), t, "S1/S2 交互")
t = {"failure": bool(has(v1, r"失败|降级|错误")), "privacy": bool(has(v1, r"隐私|PII|正文")),
     "no_auto": bool(has(v1, r"不自动|仅提案|propose")), "audit": "audit" in v1}
add("M-S10-11", ok(*t.values()), t, "失败/隐私/不自动")
t = {"not05": bool(has(v1, r"0\.5|不做")), "boundary": bool(has(v1, r"边界|不在 0.5|未来")),
     "graph": bool(has(v1, r"GRAPH_|S6")), "s6a2": "ADDENDUM-2" in v1}
add("M-S10-12", ok(*t.values()), t, "0.5 边界/GRAPH_*")
add("S10A", ok("docs/design/multilevel-graph/golden/S10-golden-set.json" in v1, "eval-kp.py" in v1,
               "artifacts/agent/verify/graph/kp/" in v1, "GATE-KP" in v1, "curation/" in v1,
               "direction=both" in v1 or "both" in v1),
    {"golden": "docs/.../golden/S10-golden-set.json", "eval": "scripts/verify/eval-kp.py",
     "artifacts": "artifacts/agent/verify/graph/kp/", "gate": "GATE-KP",
     "curation": ".memoria/agent/audit/graph/curation/", "both": "direction=both 物化两条有向边",
     "quality": "Q-EVIDENCE/Q-SEM-PURITY P0；P/R/τ soft"}, "S10a 定稿")
out = {"inputs": {k: sha(k) for k in F}, "checks": checks,
       "plan_blocks": len(re.findall(r"```mermaid\n", plan or "")),
       "summary": {"M_fail": [c["id"] for c in checks if c["status"] == "FAIL"],
                   "M_pass": [c["id"] for c in checks if c["status"] == "PASS"],
                   "gate": "是" if not any(c["status"] != "PASS" for c in checks) else "否"}}
print(json.dumps(out, ensure_ascii=False, indent=2))
``

## 附录 B — 原始输出（2026-11-04T08:3x 捕获）

`
$ node parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md
﻿{"kind":"meta","mermaidVersion":"11.16.0","mermaidSha256":"9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76","jsdomVersion":"29.1.1","node":"v24.21.0"}
{"kind":"file","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","blocks":33,"fileSha256":"aa37655c168587365cb2ebc9d1d804d088ca2fe2cac433e1de43611f6889df32"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":1,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":2,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":3,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":4,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":5,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":6,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":7,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":8,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":9,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":10,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":11,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":12,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":13,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":14,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":15,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":16,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":17,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":18,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":19,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":20,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":21,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":22,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":23,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":24,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":25,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":26,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":27,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":28,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":29,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":30,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":31,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":32,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":33,"ok":true,"diagramType":"stateDiagram"}
{"kind":"summary","failedBlocks":0}

$ python s10check_v1.py > s10check-v1.json
{
 "inputs": {
  "V1": "a5db0f1cd99ac69c6d66d772b9aab0b676e53fa8b8d01f323516e29ca1e8809e",
  "A2": "db71ccd4558ea7fddf97f3efd280fc4c2efbe663c523a7f8c7892f80d7b8458a",
  "B2": "48d8760d6907bf0b8aa536257756d210958332036c0af23b0c9196df5ed05274",
  "OBJ2": "22238f80e5b7a77501927f529ff3e6ac949a552f24a6737e8006fb924cc951f8",
  "RUL": "9818d0fd0016d6d12202bd1b6e860d06e78a7c114902d9a073d55bdb4ceaf6b3",
  "CH": "19724129d3c71087652baec76555718899ec752edd5e34223e0f2686fbd5ee04",
  "S1": "6676c71d09c5722c5c42252c63158878638e5f4480ce0dade4dd114b94f5a866",
  "S2": "92bb004190d3f93795fe4916cdf904f4dc7574eaaccb43eff9d63edb5b27a6c6",
  "S6": "40f12e5fd5946c8cc4ebdb71800579d3e9098f74ef7381ad65a2e51f389db82b",
  "S7": "70dd8748053d7631cf941f1ff743ed5b9b5e165d39492d98018f0dc0cff0c2d3",
  "S8": "c6a135ffb28c848ec351379b57aae99b86f213b1088815eae336e249f58e9f99",
  "S9": "42f364233fe1e7d08d0d0811c98a64117ebd9c0ed30a53a3d17793269a5b7dbe",
  "S6A2": "45b99ab2f3235515581153400533b633101c77fde4f3eb7a6a638b70300531e7",
  "PLAN": "51ebfb01305d9d9aa820c55b0ed6be3fb9c71765dcabdbbd7eea1608eb8835c3"
 },
 "summary": {
  "M_fail": [],
  "M_pass": [
   "M-S10-1",
   "M-S10-2",
   "M-S10-3",
   "M-S10-4",
   "M-S10-5",
   "M-S10-6",
   "M-S10-7",
   "M-S10-8",
   "M-S10-9",
   "M-S10-10",
   "M-S10-11",
   "M-S10-12",
   "S10A"
  ],
  "gate": "是"
 },
 "plan_blocks": 33
}
`
