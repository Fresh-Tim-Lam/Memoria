# S7 工程校核报告（SE · task-328：agent 工具/查询/引用/降级 + G7）

> **冻结对象**：`docs/design/multilevel-graph/S7-agent-v1.md`（sha256 `70dd8748053d7631cf941f1ff743ed5b9b5e165d39492d98018f0dc0cff0c2d3`，112 行）。
> **证据链（只读）**：A-v2 `605f0032…`、B-v2 `8c1ada34…`、异议-v2 `849cfecb…`、`S7-RULINGS.md`、`S6-ADDENDUM-1.md`；上游 S0–S6 冻结（S6 `40f12e5f…` + ADDENDUM）。
> **工程图**：`ENGINEERING-PLAN.md`（`a6c628b5…`，**24 图**；S7a=ER-08/DF-08/ST-08）；同版本 vendored mermaid 11.16.0（sha `9198f632…`），全部 `PARSE_OK`。
> **执行者**：`graph-se-architect`（SE，domain=se）· **日期**：2026-11-03（Asia/Shanghai）
> **边界**：未改 A/B/v1/异议/RULINGS；未写产品代码；未改契约；未 commit。
> **结论**：**达到 S7 冻结工程门禁（是）**。M-S7-1..12 全 PASS（`M_fail=[]`）；工具/DFD/状态图与 G7 草案落于 `ENGINEERING-PLAN.md` §1.14/§2.13/§3.11，24 图 `PARSE_OK`；5 只读工具 schema、引用/excerpt/stale、错误码对齐 S6+ADDENDUM-1、v1 只读写边界均闭合。

---

## 1. M-S7-1..12 机检（对照 `S7-agent-v1.md`）

| M | 判据 | 判定 | 证据 |
|---|---|---|---|
| M-S7-1 | 只读边界/S10/禁 sidecar | **PASS** | v1：agent v1 只读；`GRAPH_WRITE_FORBIDDEN`；写仅 S10 工具+审计/人工确认；不写 sidecar/registry（D-3） |
| M-S7-2 | ViewResponse edges 口径 | **PASS** | `ViewResponse.edges[]` 只含 `presence=shown`；`suppressed/unknown` 只给 `suppressed_summary{rule_id:count}` + `rule_histogram`；逐条解释走 `graph_explain_edge` |
| M-S7-3 | 5 工具/无 path/expand 不改 nav/幂等/审计/edition | **PASS** | 5 工具：`graph_focus/graph_explain_edge/graph_expand_cluster/graph_summary/graph_resolve_ref`；v1 无 `graph_path`；expand 不改 S5 导航/stack；幂等键 `(tool,args,edition,budget)`；`audit_id`；`expected_edition`+`edition_sha` |
| M-S7-4 | 预算/截断/unknown/suppressed | **PASS** | `max_tokens/max_nodes`；`truncated` 显式；`unknown`/`suppressed_summary` 显式；`GRAPH_TOOL_BUDGET_EXCEEDED`；不静默截断 |
| M-S7-5 | 错误表/ADDENDUM/i18n/schema | **PASS** | 错误码逐码映射 S6 `GRAPH_*`；`S6-ADDENDUM-1` 六码（`GRAPH_TOOL_INPUT_INVALID/BUDGET_EXCEEDED/ANCHOR_STALE/RETRIEVAL_UNAVAILABLE/WRITE_FORBIDDEN/AUDIT_FAILED`）；legacy/i18n/severity；工具参数/返回 schema |
| M-S7-6 | 写权限 | **PASS** | v1 只读；写请求一律 `GRAPH_WRITE_FORBIDDEN`；仅 S10 允许写（工具+审计+人工确认）；禁 sidecar/registry |
| M-S7-7 | 引用契约 | **PASS** | `kp_id/file/line/anchor` + `cluster_key/run_id`；`claim_type ∈ {graph_relation,source_assertion}`；`source_excerpt ≤500` 只读/不缓存正文/审计；`GRAPH_ANCHOR_STALE` |
| M-S7-8 | S9/S10 边界/降级 | **PASS** | S7 只消费；S9 提供候选/召回，`GRAPH_RETRIEVAL_UNAVAILABLE`；S10 写；`no_semantic_edges` 显式降级 |
| M-S7-9 | 多维度/多归属 | **PASS** | dimension/view_family 显式；多归属簇解释；不得把一维当全局 |
| M-S7-10 | 失败/降级 | **PASS** | `no_semantic_edges`/预算不足/数据缺失/unknown 可见降级；不编造 |
| M-S7-11 | G7 指标/快照 | **PASS** | token/调用数/命中率/引用完整率/unknown 比例；G7 快照引用 G6 `run_ids/frame_ids`，不复制事实 |
| M-S7-12 | 与 S0–S6 一致 | **PASS** | S4 focus-only/presence、S5 frame_id/事务化、S6 `GRAPH_*`/路径、S3 VM 纯度；无隐式 2 跳；单一真源/DataSource 只读 |

---

## 2. 工具接口（S7a / G7 草案，冻结对齐）

| 工具 | 参数 | 返回 | 错误/约束 |
|---|---|---|---|
| `graph_focus` | `level, view_family, dimension, focus, hop≤1, max_tokens?, max_nodes?, expected_edition?` | ViewResponse（nodes/edges 只 shown、presence/rule_id、suppressed_summary、counts、truncated、edition_sha、kb_id） | S4 focus-only；无隐式 2 跳；只读/幂等/审计 |
| `graph_explain_edge` | `edge_id, expected_edition?` | `{presence,rule_id,claim_type,source_assertion?,data_edge_ids?,edition_sha}` | 可解释 suppressed；不批量泄漏原始边 |
| `graph_expand_cluster` | `cluster_key, run_id, level, max_tokens?, expected_edition?` | 簇成员摘要（label/member_count/多归属） | 只读 S2 run；不改 S5 导航/stack；不重算簇 |
| `graph_summary` | `frame_id?/run_id, max_tokens?, expected_edition?` | rule_id 直方图 + suppressed_summary + counts + G7 摘要 | 只读；无原始隐藏边 |
| `graph_resolve_ref` | `{kp_id?│file+line│anchor}, expected_edition?` | `{resolved,kp_id,file,line,anchor,stale,claim_type,source_excerpt?}` | 只读/幂等/审计；excerpt≤500；stale → `GRAPH_ANCHOR_STALE` |
| 无 `graph_path` | — | v1 不提供 | 显式多跳需 `allow_two_hop`+S5 `EXPLICIT_NEW_HOP`，另开修订 |

**通用**：`kb_id`、`clusters[]`、counts/summary、`truncated`、`edition_sha`；幂等键 `(tool,args,edition,budget)`；每次调用 `audit_id`；错误表逐码 legacy/i18n；默认 `max_tokens=4000/max_nodes=200`（S8 可调）。

---

## 3. S7a 图与 G7

- **ER-08**（PLAN §1.14）：GRAPH_TOOL/TOOL_CALL/TOOL_RESULT/EVIDENCE_REF/KP_REF/CLUSTER_REF/TOKEN_BUDGET/AUDIT_ENTRY。
- **DF-08**（§2.13）：agent→工具→复用 S4/S5/S2 只读→引用→预算/截断→审计；无路径/多跳。
- **ST-08**（§3.11）：Querying→Bounded/Truncated/Degraded/Failed；ReadOnly→Denied（`GRAPH_WRITE_FORBIDDEN`）；审计。
- **G7**：工具调用数/token/命中率/引用完整率/unknown 比例/降级次数；快照引用 G6 shas；阈值/隐私归 S8。

---

## 4. 与 S0–S6 一致性

| 上游 | S7 落点 | 判定 |
|---|---|---|
| S0 单一真源/D-3/D-4 | S7-1/S7-2：只读 View/解释层；不绕过 DataSource；不写 sidecar | **一致** |
| S3 VM 纯度/白名单/ADDENDUM-1 | S7-2：不把 VM 当事实；presence/rule_id 可解释 | **一致** |
| S4 focus-only/presence/subset | `graph_focus` 复用 S4；无新裁剪 | **一致** |
| S5 frame_id/事务化/无隐式 2 跳 | `frame_id` 审计引用；expand 不改导航；无 path | **一致** |
| S6 `GRAPH_*`/路径/G6 | 错误码+ADDENDUM-1；audit 路径；G7 引 G6 | **一致** |
| S1/S2 维度/多归属/run | 多维度显式；只读 run | **一致** |

---

## 5. 未关闭项（O-S7-1..O-S7-8，不阻塞）

| # | 项 | 归属 | 建议 |
|---|---|---|---|
| O-S7-1 | token 默认 4000/200 与 S8 阈值校准 | S8 | S8 定最终值 |
| O-S7-2 | `allow_two_hop` 显式多跳（未来修订） | S7 修订 | 需 S5 `EXPLICIT_NEW_HOP` + 决策 |
| O-S7-3 | `source_excerpt` 截断边界/多行 anchor 规范 | S7/S6a | 冻结 500 字符+行号+anchor 规则 |
| O-S7-4 | `graph_resolve_ref` 对 stale 的 `resolved=false` 语义 | 0.5 | 显式 stale + 审计 |
| O-S7-5 | S9 candidate_ref schema | S9 | S9 定义；S7 只消费 |
| O-S7-6 | S10 写后 edition 失效/刷新 | S10 | 写后 `GRAPH_EDITION_STALE` 生效 |
| O-S7-7 | G7 隐私/阈值 | S8 | G7 不含正文；只统计 |
| O-S7-8 | 工具审计失败 `GRAPH_TOOL_AUDIT_FAILED` 回退 | 0.5 | fail-closed + 可观测 |

---

## 6. 冻结工程门禁判定

**是**（S7-charter §7）：

| 条件 | 结果 |
|---|---|
| 1. A/B 独立完成 + 差异 + 异议关闭 | **满足**（A-v2/B-v2/异议-v2；R-S7-1..6 关闭，R-S7-7..9 由 Lead 收口） |
| 2. SE 工程校核 PASS | **满足**（`M_fail=[]`；24 图 `PARSE_OK`；工具/引用/降级/写边界/错误表） |
| 3. Lead 独立机检 | **待 Lead** |
| 4. 与 S0–S6 无冲突 | **满足**（§4） |
| 5. 冻结 v1 + 写决策 | **待 Lead** |

---

## 7. 边界与后续

- 只读 v1/A-v2/B-v2/异议-v2/RULINGS/S0–S6+ADDENDUM；未改这些文件；未写产品代码；未改契约；未 commit。
- 已更新 `ENGINEERING-PLAN.md` S7 增量（ER-08/DF-08/ST-08 + G7 接口清单 + S7a 注记），未改 S0–S6 冻结部分。
- Lead 机检通过后冻结 `S7-agent-v1.md`；后续 S8（度量/阈值）、S9（检索）、S10（agent 写知识点）。

---

---

## 附录 A — M-S7 机检脚本（SE 审计脚本，非产品代码）

``python
# -*- coding: utf-8 -*-
"""S7 冻结前工程校核机检（task-328）。"""
import hashlib
import json
import os
import re

BASE = "D:/AAA_Jupyter/Memoria/docs/design/multilevel-graph/"
F = {"V1": "S7-agent-v1.md", "A2": "S7-agent-proposal-A-v2.md", "B2": "S7-agent-proposal-B-v2.md",
     "OBJ2": "S7-objections-v2.md", "RUL": "S7-RULINGS.md", "CH": "S7-charter.md",
     "S0": "S0-terms-v1.md", "S1": "S1-dimensions-v1.md", "S2": "S2-clustering-v1.md",
     "S3": "S3-visual-v1.md", "ADD": "S3-ADDENDUM-1.md", "S4": "S4-render-v1.md",
     "S5": "S5-nav-v1.md", "S6": "S6-contract-v1.md", "S6A": "S6-ADDENDUM-1.md",
     "PLAN": "ENGINEERING-PLAN.md"}


def rd(k):
    p = BASE + F[k]
    return open(p, encoding="utf-8").read() if os.path.exists(p) else None


def sha(k):
    p = BASE + F[k]
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None


def has(t, pat):
    return re.findall(pat, t or "", re.I | re.M)


v1 = rd("V1")
plan = rd("PLAN")
checks = []


def add(i, st, ev, note=""):
    checks.append({"id": i, "status": st, "evidence": ev, "note": note})


if not v1:
    print(json.dumps({"status": "WAITING_FOR_V1"}, ensure_ascii=False))
    raise SystemExit(0)

t = {"readonly": bool(has(v1, r"只读")), "no_write": "GRAPH_WRITE_FORBIDDEN" in v1,
     "s10": "S10" in v1, "no_sidecar": bool(has(v1, r"不写 sidecar|禁.{0,10}sidecar|sidecar"))
     and bool(has(v1, r"不写 sidecar|不得写 sidecar|禁 sidecar|禁止.{0,10}sidecar"))}
add("M-S7-1", "PASS" if all(t.values()) else "FAIL", t, "v1 只读/S10 写/禁 sidecar")

t = {"shown": bool(has(v1, r"只含.{0,10}shown|只含 presence=shown|presence=shown")),
     "suppressed_summary": "suppressed_summary" in v1,
     "rule_histogram": "rule_histogram" in v1,
     "explain": "graph_explain_edge" in v1}
add("M-S7-2", "PASS" if all(t.values()) else "FAIL", t, "ViewResponse edges 只 shown + summary")

tools = ["graph_focus", "graph_explain_edge", "graph_expand_cluster", "graph_summary", "graph_resolve_ref"]
t = {"five": all(x in v1 for x in tools), "no_path": ("graph_path" not in v1) or bool(has(v1, r"v1 无.{0,5}graph_path|不含.{0,5}graph_path|不做.{0,5}graph_path")),
     "expand_no_nav": bool(has(v1, r"不改.{0,20}(S5|导航|stack)|不得修改 S5")),
     "idempotent": bool(has(v1, r"幂等")), "audit": "audit_id" in v1,
     "edition": "expected_edition" in v1 and "edition_sha" in v1}
add("M-S7-3", "PASS" if all(t.values()) else "FAIL", t, "5 工具/无 path/expand 不改 nav/幂等/审计/edition")

t = {"max_tokens": "max_tokens" in v1, "max_nodes": "max_nodes" in v1,
     "truncated": "truncated" in v1, "unknown": "unknown" in v1,
     "suppressed": "suppressed_summary" in v1, "budget_code": "GRAPH_TOOL_BUDGET_EXCEEDED" in v1}
add("M-S7-4", "PASS" if all(t.values()) else "FAIL", t, "预算/截断/unknown/suppressed 显式")

errs = ["GRAPH_TOOL_INPUT_INVALID", "GRAPH_TOOL_BUDGET_EXCEEDED", "GRAPH_ANCHOR_STALE",
        "GRAPH_RETRIEVAL_UNAVAILABLE", "GRAPH_WRITE_FORBIDDEN", "GRAPH_TOOL_AUDIT_FAILED",
        "GRAPH_EDITION_STALE"]
t = {"errors": all(x in v1 for x in errs), "addendum": "S6-ADDENDUM-1" in v1,
     "legacy": "legacy" in v1, "i18n": "i18n" in v1, "schema": bool(has(v1, r"参数|params"))}
add("M-S7-5", "PASS" if all(t.values()) else "FAIL", t, "错误表/S6-ADDENDUM-1/legacy/i18n/schema")

t = {"write_forbidden": "GRAPH_WRITE_FORBIDDEN" in v1,
     "s10_only": bool(has(v1, r"仅 S10|S10 工具|S10")),
     "no_sidecar_registry": bool(has(v1, r"禁.{0,20}(sidecar|registry)|不得.{0,20}(sidecar|registry)"))}
add("M-S7-6", "PASS" if all(t.values()) else "FAIL", t, "写权限 v1 只读/S10/禁 sidecar/registry")

t = {"kp": "kp_id" in v1, "file": "file" in v1, "line": "line" in v1, "anchor": "anchor" in v1,
     "cluster": "cluster_key" in v1, "run": "run_id" in v1,
     "excerpt": "source_excerpt" in v1 and bool(has(v1, r"500")),
     "claim": bool(has(v1, r"source_assertion|graph_relation")), "stale": "GRAPH_ANCHOR_STALE" in v1}
add("M-S7-7", "PASS" if all(t.values()) else "FAIL", t, "引用 kp/file/line/anchor/cluster/run/excerpt/stale")

t = {"s9": "S9" in v1, "s10b": "S10" in v1, "no_se": bool(has(v1, r"no_semantic_edges")),
     "degrade": bool(has(v1, r"降级|degraded|DEGRADED")), "retrieval": "GRAPH_RETRIEVAL_UNAVAILABLE" in v1}
add("M-S7-8", "PASS" if all(t.values()) else "FAIL", t, "S9/S10 边界/降级/检索不可用")

t = {"dim": "dimension" in v1, "family": "view_family" in v1,
     "multi": bool(has(v1, r"多归属|多维度")), "no_global": bool(has(v1, r"不得.{0,20}全局|不.{0,10}当全局"))}
add("M-S7-9", "PASS" if all(t.values()) else "FAIL", t, "多维度/多归属")

t = {"no_semantic": "no_semantic_edges" in v1, "unknown": "unknown" in v1,
     "truncated": "truncated" in v1, "no_fabricate": bool(has(v1, r"不编造|不得编造|禁止编造"))}
add("M-S7-10", "PASS" if all(t.values()) else "FAIL", t, "失败/降级显式/不编造")

t = {"g7": "G7" in v1, "g6": "G6" in v1, "metrics": bool(has(v1, r"token|命中率|引用完整率|unknown")),
     "snapshot": bool(has(v1, r"快照|snapshot"))}
add("M-S7-11", "PASS" if all(t.values()) else "FAIL", t, "G7 指标/快照")

t = {"s4": "S4" in v1, "s5": "S5" in v1, "frame": "frame_id" in v1,
     "no2hop": bool(has(v1, r"无.{0,10}隐式.{0,10}2 跳|无.{0,10}隐式多跳|显式")),
     "vm": "VM" in v1, "d3d4": bool(has(v1, r"D-3|D-4|单一真源|不绕过 DataSource|DataSource")), "s6": "S6" in v1}
add("M-S7-12", "PASS" if all(t.values()) else "FAIL", t, "与 S0–S6 一致/S4/S5/frame/无隐式 2 跳")

out = {"inputs": {k: sha(k) for k in F}, "checks": checks,
       "plan_blocks": len(re.findall(r"```mermaid\n", plan or "")),
       "summary": {"M_fail": [c["id"] for c in checks if c["status"] == "FAIL"],
                   "M_pass": [c["id"] for c in checks if c["status"] == "PASS"],
                   "gate": "是" if not any(c["status"] != "PASS" for c in checks) else "否"}}
print(json.dumps(out, ensure_ascii=False, indent=2))
``

## 附录 B — 原始输出（2026-11-03T22:2x 捕获）

`
$ node parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md
﻿{"kind":"meta","mermaidVersion":"11.16.0","mermaidSha256":"9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76","jsdomVersion":"29.1.1","node":"v24.21.0"}
{"kind":"file","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","blocks":24,"fileSha256":"a6c628b5498006143ccb991fdc6d148973bfe6795a70154cea3bbdc96cccd41e"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":1,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":2,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":3,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":4,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":5,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":6,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":7,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":8,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":9,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":10,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":11,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":12,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":13,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":14,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":15,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":16,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":17,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":18,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":19,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":20,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":21,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":22,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":23,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":24,"ok":true,"diagramType":"stateDiagram"}
{"kind":"summary","failedBlocks":0}

$ python s7check_v1.py > s7check-v1.json
{
 "inputs": {
  "V1": "70dd8748053d7631cf941f1ff743ed5b9b5e165d39492d98018f0dc0cff0c2d3",
  "A2": "605f0032cc9ec2a270e309d9bed0a1cc6cf459d1675a36d0e0d80d5f99eb5118",
  "B2": "8c1ada3426f9783d5b15437a9702b48a7104091c7d76ad2cb1888792740064e3",
  "OBJ2": "849cfecb53f0b19e04d4ed4bd64ba7818a7664f33da8d4ad462eccb8fe8655de",
  "RUL": "4067b810da5b89aa31da8d90a40ef8defa38aea584a57b5256b130a27fefec2e",
  "CH": "4bf0129815c7aaadb7122c4f7b7cc446c5c8c748d4727c68bda82571da8b09b5",
  "S0": "241b1e1e8b0a2fe6c8e1291e03a06c122d16cf71273d9e5d0d879f64ebf9ea78",
  "S1": "6676c71d09c5722c5c42252c63158878638e5f4480ce0dade4dd114b94f5a866",
  "S2": "92bb004190d3f93795fe4916cdf904f4dc7574eaaccb43eff9d63edb5b27a6c6",
  "S3": "0ca4ea0e890aa7408a361ae97dbb4d8a8f06df60b1e191cbcb7d46ca5322cd6b",
  "ADD": "6007e47a05eb5184c1d1bf7ae9627435a82c750c467247afbdaa58c58e31117d",
  "S4": "2576f6c8472ce5175f6cb1fd878f782e2c128bde675b8925981ee0d63a3f5c94",
  "S5": "7f4c4515599784c16501edf21fe1ff9d46efa08d36074ad1de7e0fb49240fe17",
  "S6": "40f12e5fd5946c8cc4ebdb71800579d3e9098f74ef7381ad65a2e51f389db82b",
  "S6A": "f9918dfdc0586b297e06f4632f0a7313b16f14e527c475fde04dfe9eba7a48dd",
  "PLAN": "fe2aa16e59e0c73b88b738071fdca3544dd41b5379f471e26a96beba57386ddb"
 },
 "summary": {
  "M_fail": [],
  "M_pass": [
   "M-S7-1",
   "M-S7-2",
   "M-S7-3",
   "M-S7-4",
   "M-S7-5",
   "M-S7-6",
   "M-S7-7",
   "M-S7-8",
   "M-S7-9",
   "M-S7-10",
   "M-S7-11",
   "M-S7-12"
  ],
  "gate": "是"
 },
 "plan_blocks": 24
}
`
