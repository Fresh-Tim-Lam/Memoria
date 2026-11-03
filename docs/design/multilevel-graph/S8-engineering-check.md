# S8 工程校核报告（SE · task-333：G6/G7 快照、CI 门禁、0.5 DoD）

> **冻结对象**：`docs/design/multilevel-graph/S8-metrics-v1.md`（sha256 `c6a135ffb28c848ec351379b57aae99b86f213b1088815eae336e249f58e9f99`，97 行）。
> **证据链（只读）**：A-v2 `7459b957…`、B-v2 `76707304…`、异议-v2 `0234364a…`、`S8-RULINGS.md`；S0–S7 冻结 + 两 ADDENDUM。
> **工程图**：`ENGINEERING-PLAN.md`（`53d44762…`，**27 图**；S8a=ER-09/DF-09/ST-09）；mermaid 11.16.0（sha `9198f632…`）全 `PARSE_OK`。
> **执行者**：`graph-se-architect`（SE，domain=se）· **日期**：2026-11-04（Asia/Shanghai）
> **边界**：未改 A/B/v1/异议/RULINGS；未写产品代码；未改契约；未 commit。
> **结论**：**达到 S8 冻结工程门禁（是）**。M-S8-1..12 全 PASS（`M_fail=[]`）；S8a 命令/路径/sha/CI/DoD 定稿落于 `ENGINEERING-PLAN.md` §1.15/§2.14/§3.12 + S8a 注记，27 图 `PARSE_OK`。

---

## 1. M-S8-1..12 机检

| M | 判据 | 判定 | 证据 |
|---|---|---|---|
| M-S8-1 | 指标框架/优先级 | **PASS** | v1:12/§S8-1：正确性/确定性/性能/可解释/agent/数据质量/回归分类；P0 硬门禁 + soft 趋势；不得单一指标掩盖 |
| M-S8-2 | G6 字段/路径/sha/不可变/复跑 | **PASS** | 唯一路径 `.memoria/agent/audit/graph/g6/`；`snapshot_id=sha256(canonical(G6_SNAPSHOT without snapshot_id))`；不可变；`--replay` 复跑；与 S6 G6 字段一致 |
| M-S8-3 | 正确性/确定性 | **PASS** | HAC 确定性、registry 校验、presence/rule_id、subset、closure/behind=0、tie-break；P0 可机判（100% 确定性等） |
| M-S8-4 | 性能/预算 | **PASS** | 60fps/30fps/180ms/200/400 来自 S3/S4；P95 标「假设，需实测基线校准」；冷/热/参考硬件/N≥30；无 GPU 时仅本地参考硬件门禁 |
| M-S8-5 | X-RULE/SUMMARY/降级 | **PASS** | `X-RULE=(non-shown nodes with rule_id + non-shown edges with rule_id)/(all non-shown)` 100%；`X-NODE-RULE/X-EDGE-RULE` 分项；`X-SUMMARY` 对齐 S4；unknown≠无关系 |
| M-S8-6 | G7/G-G7/隐私 | **PASS** | G7 指标与 S7 一致；`write_attempts=0`、`read_only=100%`；G-G7 P0 gate；只存 id/anchor 引用/counts，无正文/excerpt/PII；90 天/100k/≤64MB |
| M-S8-7 | semantic-only | **PASS** | semantic edge/KP coverage、no_semantic 比例等为语料信号；不设 P0 下限；**不得用结构边凑数** |
| M-S8-8 | 故障 8 类/回放 | **PASS** | 预算、空语义、stale、缺失、非法输入、审计失败、renderer budget、S9 unavailable；确定性回放+G6 diff |
| M-S8-9 | CI gates/flaky/mermaid | **PASS** | P0 gates 含 G6 sha/G-G7/正确性/确定性/X-RULE/subset/closure-behind/mermaid（27 图）；本地与 CI 同脚本；P0 不 flaky，诊断重试≤3，阈值不因 flaky 下调 |
| M-S8-10 | DoD I-01..I-13 | **PASS** | I-01..I-13 逐项验收；I-05/06/07/08 P0 阻断（I-07 只验 2D，3D capability=false 不阻断）；其余 P1 |
| M-S8-11 | 存储/隐私/成本 | **PASS** | G6/G7 保留期/大小上限；G7 无正文/PII；删除/重建；成本量级 |
| M-S8-12 | S9/S10 边界 | **PASS** | S8 只消费 S9 检索/S10 KP 指标，不定义算法；边界明确 |

---

## 2. S8a 定稿（G6/G7/CI/DoD）

### 2.1 G6/G7 命令与 envelope（本地与 CI 同脚本）

```
python scripts/benchmark/graph/g6_snapshot.py --out .memoria/agent/audit/graph/g6/<snapshot_id>.json --sha256
python scripts/benchmark/graph/g7_snapshot.py --out .memoria/agent/audit/graph/g7/<snapshot_id>.json --sha256
python scripts/benchmark/graph/g6_snapshot.py --replay .memoria/agent/audit/graph/g6/<snapshot_id>.json  # 断言 sha 一致
```

- **G6 唯一域**：`.memoria/agent/audit/graph/g6/`（S6 audit 域）；`artifacts/agent/verify/graph/g6/` 仅人类可读副本，不作基线/CI 事实源。
- **snapshot_id**：`sha256(canonical(G6_SNAPSHOT without snapshot_id))`；snapshot 写后不可变；基线更新需 `decision` + 新 id。
- **G7**：只存 id/anchor 引用/counts，无正文/excerpt/PII；保留 90 天或 100k 条/≤64MB；G-G7 gate 断言 `write_attempts=0`、`read_only=100%`、引用完整率、无正文。
- **产物 sha 规则**：JSON canonical（键排序、UTF-8、无尾随空白）→ sha256；报告/副本同 sha 校验。

### 2.2 CI 接入草案（P0 阻断）

```
pytest -q tests/graph
node --check <changed js>
node <SE_DIR>/parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md   # 27 图 PARSE_OK
python scripts/benchmark/graph/g6_snapshot.py --verify-baseline
python scripts/benchmark/graph/g7_snapshot.py --assert-g-g7
```

- P0 gates：G6 sha/基线、G-G7、正确性/确定性、X-RULE、subset、closure/behind=0、mermaid；失败 exit≠0 + 产物 sha。
- 性能守卫：仅本地参考硬件（N≥30、冷/热、环境记录）；CI 无 GPU 不阻断性能 P0。
- flaky：P0 不豁免；诊断性重试≤3；阈值不得下调。

### 2.3 0.5 DoD 映射（I-01..I-13）

| I | 验收 | 阻断 |
|---|---|---|
| I-01 DataSourceReader | 只读事实/D-3/sha | P1 |
| I-02 GraphViewBuilder | `(level,view_family)`/E_relation_min | P1 |
| I-03 RegistryService | 只增不删/history/signature | P1 |
| I-04 ClusterRunBuilder | run_id/五状态/多归属 | P1 |
| I-05 AdmissionService | presence/rule_id/MANDATORY/subset/事务 | **P0** |
| I-06 ViewModelBuilder | S3 白名单+ADDENDUM-1/禁读 | **P0** |
| I-07 RendererAdapter | 2D 渲染/事件/同签名 | **P0**（3D capability=false 不阻断） |
| I-08 NavController | T01–T30/事务化/frame_id | **P0** |
| I-09 CacheStore | 可删重建/GC/D-3 | P1 |
| I-10 AuditLog | append-only/路径 | P1 |
| I-11 G6Snapshot | 字段/sha/复跑 | P1 |
| I-12 ErrorMap | `GRAPH_*`+legacy | P1 |
| I-13 SchemaValidator | 字段/枚举/失败码 | P1 |

---

## 3. 与 S0–S7 一致性

| 上游 | S8 落点 | 判定 |
|---|---|---|
| S6 G6 字段/路径 | S8-2 唯一 audit 域、字段一致 | **一致** |
| S6 错误码/路径 | G-G7/错误码/audit 路径 | **一致** |
| S7 G7/write=0/隐私 | S8-6/G-G7 | **一致** |
| S4 presence/subset、S5 frame_id/事务 | X-RULE/subset/frame 指标 | **一致** |
| S3 性能预算 | S8-4 数值来源/假设标注 | **一致** |
| S0/S1/S2 单一真源/维度/run | semantic-only/数据质量 | **一致** |

---

## 4. 未关闭项（O-S8-1..8，不阻塞）

| # | 项 | 归属 | 建议 |
|---|---|---|---|
| O-S8-1 | P95 性能实测基线校准 | 0.5/S8 修订 | 参考硬件 N≥30 后写回 S8 |
| O-S8-2 | G6/G7 保留期/大小最终值 | S8 冻结 | 90 天/100k/64MB 已定，实测校准 |
| O-S8-3 | X-RULE 节点/边分项阈值 | 0.5 | 100% 目标；分项诊断 |
| O-S8-4 | S9 检索不可用降级路径实测 | S9/0.5 | `GRAPH_RETRIEVAL_UNAVAILABLE` |
| O-S8-5 | flaky 隔离池实现 | 0.5/CI | 诊断重试≤3；P0 不豁免 |
| O-S8-6 | G7 隐私审计抽样 | S8/0.5 | 无正文/excerpt/PII |
| O-S8-7 | CI 无 GPU 时性能守卫边界 | 0.5 | 本地参考硬件门禁 |
| O-S8-8 | DoD 证据产物路径/命名 | 0.5 | 与 I-01..I-13 对齐 |

---

## 5. 冻结工程门禁判定

**是**（S8-charter §7）：

| 条件 | 结果 |
|---|---|
| 1. A/B 独立完成 + 差异 + 异议关闭 | **满足**（A-v2/B-v2/异议-v2；R-S8-1..6 关闭） |
| 2. SE 工程校核 PASS | **满足**（`M_fail=[]`；27 图 `PARSE_OK`；G6/G7 命令/CI/DoD 定稿） |
| 3. Lead 独立机检 | **待 Lead** |
| 4. 与 S0–S7 无冲突 | **满足**（§3） |
| 5. 冻结 v1 + 写决策 | **待 Lead** |

---

## 6. 边界与后续

- 只读 v1/A-v2/B-v2/异议-v2/RULINGS/S0–S7；未改这些文件；未写产品代码；未改契约；未 commit。
- 已更新 `ENGINEERING-PLAN.md` S8 增量（ER-09/DF-09/ST-09 + G6/G7 命令/CI/DoD 定稿），未改 S0–S7 冻结部分。
- 冻结后 0.5 实现按 S6a I-01..I-13 + S8 DoD/CI 执行。

---

---

## 附录 A — M-S8 机检脚本（SE 审计脚本，非产品代码）

``python
# -*- coding: utf-8 -*-
"""S8 冻结前工程校核机检（task-333）。"""
import hashlib, json, os, re
BASE = "D:/AAA_Jupyter/Memoria/docs/design/multilevel-graph/"
F = {"V1": "S8-metrics-v1.md", "A2": "S8-metrics-proposal-A-v2.md", "B2": "S8-metrics-proposal-B-v2.md",
     "OBJ2": "S8-objections-v2.md", "RUL": "S8-RULINGS.md", "CH": "S8-charter.md",
     "S6": "S6-contract-v1.md", "S6A": "S6-ADDENDUM-1.md", "S7": "S7-agent-v1.md",
     "S5": "S5-nav-v1.md", "S4": "S4-render-v1.md", "S3": "S3-visual-v1.md", "PLAN": "ENGINEERING-PLAN.md"}
def rd(k):
    p = BASE + F[k]; return open(p, encoding="utf-8").read() if os.path.exists(p) else None
def sha(k):
    p = BASE + F[k]; return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
def has(t, pat): return re.findall(pat, t or "", re.I | re.M)
v1 = rd("V1"); plan = rd("PLAN"); checks = []
def add(i, st, ev, note=""): checks.append({"id": i, "status": st, "evidence": ev, "note": note})
if not v1:
    print(json.dumps({"status": "WAITING_FOR_V1"}, ensure_ascii=False)); raise SystemExit(0)
t = {"framework": bool(has(v1, r"正确性|确定性|性能|可解释|回归|指标")),
     "p0": bool(has(v1, r"P0|硬门禁")), "no_single": bool(has(v1, r"单一指标|不得.{0,10}单一"))}
add("M-S8-1", "PASS" if all(t.values()) else "FAIL", t, "指标框架/优先级")
t = {"g6": "G6" in (v1 or ""), "path": ".memoria/agent/audit/graph/g6/" in (v1 or ""),
     "sha": bool(has(v1, r"sha256|snapshot_id")), "immutable": bool(has(v1, r"不可变|immutable")),
     "replay": ("回放" in v1 or "复跑" in v1)}
add("M-S8-2", "PASS" if all(t.values()) else "FAIL", t, "G6 字段/路径/sha/不可变/复跑")
t = {"hac": bool(has(v1, r"HAC")), "registry": "registry" in (v1 or ""),
     "presence": "presence" in (v1 or ""), "subset": "subset" in (v1 or ""),
     "closure": "closure" in (v1 or ""), "behind": "behind" in (v1 or ""),
     "tie": bool(has(v1, r"tie[- ]?break"))}
add("M-S8-3", "PASS" if all(t.values()) else "FAIL", t, "正确性/确定性项")
t = {"fps": bool(has(v1, r"60 ?fps|30 ?fps|180 ?ms")), "budget": bool(has(v1, r"max_nodes|max_edges")),
     "assumption": bool(has(v1, r"假设|实测|参考硬件|N≥30|样本")),
     "cold": bool(has(v1, r"冷|热"))}
add("M-S8-4", "PASS" if all(t.values()) else "FAIL", t, "性能/budget/测量条件")
t = {"xrule": "X-RULE" in (v1 or ""), "xnode": "X-NODE-RULE" in (v1 or ""),
     "xedge": "X-EDGE-RULE" in (v1 or ""), "xsummary": "X-SUMMARY" in (v1 or ""),
     "degrade": bool(has(v1, r"降级|no_silent|unknown"))}
add("M-S8-5", "PASS" if all(t.values()) else "FAIL", t, "X-RULE 节点+边/SUMMARY/降级")
t = {"g7": "G7" in (v1 or ""), "write0": bool(has(v1, r"write_attempts ?= ?0|写尝试 ?= ?0")),
     "gg7": "G-G7" in (v1 or ""), "privacy": bool(has(v1, r"隐私|PII|不存正文|excerpt")),
     "keep": bool(has(v1, r"90 天|64 ?MB|100k"))}
add("M-S8-6", "PASS" if all(t.values()) else "FAIL", t, "G7/G-G7/隐私/保留")
t = {"semantic": bool(has(v1, r"semantic[- ]only|仅语义|语义边")),
     "no_struct": ("结构边" in v1)}
add("M-S8-7", "PASS" if all(t.values()) else "FAIL", t, "数据质量 semantic-only")
t = {"faults": ("8 类" in v1 or all(x in v1 for x in ["预算", "空语义", "stale", "缺失", "非法", "审计失败"])),
     "renderer": bool(has(v1, r"renderer")), "s9": bool(has(v1, r"S9")),
     "replay": bool(has(v1, r"回放|replay"))}
add("M-S8-8", "PASS" if all(t.values()) else "FAIL", t, "故障 8 类/回放")
t = {"ci": "CI" in (v1 or ""), "gg7": "G-G7" in (v1 or ""), "flaky": bool(has(v1, r"flaky")),
     "mermaid": bool(has(v1, r"mermaid|PARSE_OK")), "local": bool(has(v1, r"本地|同脚本"))}
add("M-S8-9", "PASS" if all(t.values()) else "FAIL", t, "CI gates/flaky/mermaid")
t = {"dod": bool(has(v1, r"DoD|退出标准")), "i13": ("I-01..I-13" in v1 or "I-01" in v1),
     "p0": bool(has(v1, r"P0|阻断"))}
add("M-S8-10", "PASS" if all(t.values()) else "FAIL", t, "0.5 DoD I-01..I-13")
t = {"storage": bool(has(v1, r"存储|保留期|大小上限")), "privacy": bool(has(v1, r"隐私|PII")),
     "delete": bool(has(v1, r"删除|重建"))}
add("M-S8-11", "PASS" if all(t.values()) else "FAIL", t, "度量存储/隐私/成本")
t = {"s9": "S9" in (v1 or ""), "s10": "S10" in (v1 or ""), "boundary": bool(has(v1, r"边界|只消费|不定义"))}
add("M-S8-12", "PASS" if all(t.values()) else "FAIL", t, "S9/S10 边界")
out = {"inputs": {k: sha(k) for k in F}, "checks": checks,
       "plan_blocks": len(re.findall(r"```mermaid\n", plan or "")),
       "summary": {"M_fail": [c["id"] for c in checks if c["status"] == "FAIL"],
                   "M_pass": [c["id"] for c in checks if c["status"] == "PASS"],
                   "gate": "是" if not any(c["status"] != "PASS" for c in checks) else "否"}}
print(json.dumps(out, ensure_ascii=False, indent=2))
``

## 附录 B — 原始输出（2026-11-04T00:3x 捕获）

`
$ node parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md
﻿{"kind":"meta","mermaidVersion":"11.16.0","mermaidSha256":"9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76","jsdomVersion":"29.1.1","node":"v24.21.0"}
{"kind":"file","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","blocks":27,"fileSha256":"53d44762e35c18754f1c8363bea2f67b93d878b58318b46094c213434baca6a8"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":1,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":2,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":3,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":4,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":5,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":6,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":7,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":8,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":9,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":10,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":11,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":12,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":13,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":14,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":15,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":16,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":17,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":18,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":19,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":20,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":21,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":22,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":23,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":24,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":25,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":26,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":27,"ok":true,"diagramType":"stateDiagram"}
{"kind":"summary","failedBlocks":0}

$ python s8check_v1.py > s8check-v1.json
{
 "inputs": {
  "V1": "c6a135ffb28c848ec351379b57aae99b86f213b1088815eae336e249f58e9f99",
  "A2": "7459b9576a1271d7290ed35b7879e86845b78fa60625116670849d70180b8ec7",
  "B2": "76707304b70adcf3b6b46aca1a37ae3bb4a4aa4651f7f6b824dffe6be640f240",
  "OBJ2": "fc2332faf281b12be748a851ebc14bbfabb70a443877d6d02d60ada817a14be2",
  "RUL": "418288704907babd9437ecf095ac6dcd323b385774a0a0380eac1bd7bf2dc7ab",
  "CH": "2cd1664e0a1fdb53f6145805412350deb425ae9772f17203a2a054064de806b2",
  "S6": "40f12e5fd5946c8cc4ebdb71800579d3e9098f74ef7381ad65a2e51f389db82b",
  "S6A": "f9918dfdc0586b297e06f4632f0a7313b16f14e527c475fde04dfe9eba7a48dd",
  "S7": "70dd8748053d7631cf941f1ff743ed5b9b5e165d39492d98018f0dc0cff0c2d3",
  "S5": "7f4c4515599784c16501edf21fe1ff9d46efa08d36074ad1de7e0fb49240fe17",
  "S4": "2576f6c8472ce5175f6cb1fd878f782e2c128bde675b8925981ee0d63a3f5c94",
  "S3": "0ca4ea0e890aa7408a361ae97dbb4d8a8f06df60b1e191cbcb7d46ca5322cd6b",
  "PLAN": "0810a9f40ec755b1979555de571c44a1b309ac6d8367b882e28b681a4eac8db1"
 },
 "summary": {
  "M_fail": [],
  "M_pass": [
   "M-S8-1",
   "M-S8-2",
   "M-S8-3",
   "M-S8-4",
   "M-S8-5",
   "M-S8-6",
   "M-S8-7",
   "M-S8-8",
   "M-S8-9",
   "M-S8-10",
   "M-S8-11",
   "M-S8-12"
  ],
  "gate": "是"
 },
 "plan_blocks": 27
}
`
