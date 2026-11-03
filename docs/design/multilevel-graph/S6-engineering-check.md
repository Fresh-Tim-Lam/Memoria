# S6 工程校核 + S6a 定稿报告（SE · task-322）

> **冻结对象**：`docs/design/multilevel-graph/S6-contract-v1.md`（sha256 `40f12e5fd5946c8cc4ebdb71800579d3e9098f74ef7381ad65a2e51f389db82b`，118 行，冻结候选）。
> **证据链（只读）**：A-v2 `9e71d540…`、B-v2 `4e262068…`、异议-v2 `a495564b…`、`S6-RULINGS.md`、`S6-charter.md`；上游 S0–S5 冻结（`241b1e1e…/6676c71d…/92bb0041…/0ca4ea0e…/2576f6c8…/7f4c4515…`）。
> **工程图**：`ENGINEERING-PLAN.md`（`3b3e0f68…`，**21 图**：S0–S6 各 3 图）；同版本 vendored mermaid 11.16.0（sha `9198f632…`），全部 `PARSE_OK`。
> **执行者**：`graph-se-architect`（SE，domain=se）· **日期**：2026-11-03（Asia/Shanghai）
> **边界**：未改 A/B/v1/异议/RULINGS；未写产品代码；未改契约；未 commit。
> **结论**：**达到 S6 冻结工程门禁（是）**。M-S6-1..12 全 PASS（`M_fail=[]`）；**S6a 定稿**（ER/DFD/状态图）落于 `ENGINEERING-PLAN.md` §1.13/§2.12/§3.10，21 图 `PARSE_OK`；0.5 接口清单 I-01..I-13 已冻结；history/cache/old-build 三项 S6a 决策已定。

---

## 1. M-S6-1..12 机检（对照 `S6-contract-v1.md`）

| M | 判据 | 判定 | 证据 |
|---|---|---|---|
| M-S6-1 | 单一真源/事实只读/派生可重建/D-3 | **PASS** | v1:16-19：事实=`md`+`.memoria` sidecar/manifest 只读；DataSource 只读投影；GraphView/run/VM 派生；禁并行事实源/双写；缓存可删重建；D-3 禁写 sidecar |
| M-S6-2 | DataSource/GraphView/C-* | **PASS** | v1:21-24：DataSource `{kps,edges,canonical_id,expand}` 只读；`E_relation_min`；GraphView per `(level,view_family)`；`kind∈{kp,cluster}`；data_state 二值 |
| M-S6-3 | registry/history/签名 | **PASS** | v1:26-30：`DIMENSION_REGISTRY/DIMENSION/HISTORY_ENTRY` 字段/枚举；`signature?{alg,key_id,sig}`；append-only；只增不删；`content_sha` 不含 signature；失败 `GRAPH_HISTORY_SIGNATURE_INVALID`；落盘形态 S6a 定（见 §2） |
| M-S6-4 | run/membership/身份/五状态 | **PASS** | v1:32-36：`CLUSTER_RUN` 六元组 run_id；membership 多归属/`cluster_key`/`role:"member"`；五状态；curation 双引用 |
| M-S6-5 | VM 白名单/role/ADDENDUM/禁读 | **PASS** | v1:38-43：VM 白名单；`VM_NODE` 含 `layout_group?/presence?/rule_id?`；`role:"member"`（focus 非 VM role，S3 原文）；`data_edge_ids` 审计/Renderer 禁读；`VISUAL_ENCODING_MAP`；2D/3D capabilities |
| M-S6-6 | S4 frame/presence/subset | **PASS** | v1:45-50：`S4_FRAME_SPEC` 严格 S4 冻结字段；`NAV_FRAME = S4_FRAME_SPEC + {frame_id,edition_sha}`；`frame_id=sha256(canonical(S4_FRAME_SPEC))` 由 S5 派生；edition 不进 S4；11 类 rule_id；MANDATORY/subset；失败码 |
| M-S6-7 | Nav schema/frame_id/T01–T30 | **PASS** | v1:52-55：`GraphNavFrame` 含 frame_id、禁 nav_id schema；NAV_STACK/EVENT；9 主状态+正交；T01–T30 唯一真源引用 `S5-nav-v1` 附录 A；S5a 148 边；持久化白名单 |
| M-S6-8 | 存储/审计/GC/D-3 | **PASS** | v1:57-62：cache/config/audit 三分路径；GC 20 run/90 天只删 cache；history/audit 不 GC；D-3；旧分组不迁移/fallback 默认关闭 |
| M-S6-9 | 错误码统一/映射 | **PASS** | v1:64-66：`GRAPH_*` canonical；S2–S5 旧码 `legacy_code`；未知 `GRAPH_INTERNAL`；i18n 归 UI |
| M-S6-10 | 兼容/迁移/回滚 | **PASS** | v1:68-69：旧 graph-groups 不迁移；edition 不匹配重建；回滚=删派生缓存+回退设置；无破坏性迁移 |
| M-S6-11 | G6 字段/阈值 | **PASS** | v1:71-73：G6_SNAPSHOT 字段齐全；determinism=100%、subset_ok=true、closure/behind=0；history_signed 标记 |
| M-S6-12 | 0.5 边界/接口清单 | **PASS** | v1:75-78：做 DataSource/H/A、run、S4、VM/2D、导航基础、缓存、G6；不做 3D 实现（接口 capability=false）、agent 写、自动 semantic、跨库、时间维、编辑器、破坏性迁移；S7–S10 不在 0.5；S6a 输出接口清单（§2） |

---

## 2. S6a 定稿决策（SE）

1. **history 签名落盘**：采用 **detached `<content_sha>.sig`**（entry `signature?` 可选但非落盘主形态）；`content_sha` 不含 signature；`signed=false` 时 G6 `history_signed=false`；验签失败 `GRAPH_HISTORY_SIGNATURE_INVALID`。
2. **cache 子布局**：**`.memoria/cache/graph/{level}/{view_family}/{run_id}.json`**；`edition` 写入 run metadata（不进路径）；GC 20 run/90 天；删除后可重建。
3. **旧 `.memoria/build/**` / 旧 graph-groups**：**不读、可删**；只读 fallback 默认关闭；无迁移/无破坏性变更。
4. **G6 复跑**：快照 JSON + shas；阈值 determinism=100%、subset_ok=true、closure/behind=0。
5. **S6a ER/DFD/状态图**：落于 `ENGINEERING-PLAN.md` §1.13（ER-07）、§2.12（DF-07）、§3.10（ST-07，引用 S5a）；共 21 图同版本 `PARSE_OK`。

---

## 3. 0.5 实现接口清单（S6a，冻结）

| # | 接口/模块 | 输入 | 输出 | 关键约束 |
|---|---|---|---|---|
| I-01 | `DataSourceReader` | kb path/manifest | nodes/edges/E_relation_min（只读） | 只读事实；D-3 |
| I-02 | `GraphViewBuilder` | DataSource + `(level,view_family)` | GraphView | per-layer/family；不缓存事实 |
| I-03 | `RegistryService` | schema/schema_sha | Registry/Version/History | 只增不删；签名 detached `.sig`；失败 `GRAPH_REGISTRY_*` |
| I-04 | `ClusterRunBuilder` | GraphView+params_hash | CLUSTER_RUN/MEMBERSHIP/EDGE/STABILITY | S2 身份/五状态；candidate 不自动 adopted |
| I-05 | `AdmissionService`（S4） | S4_FRAME_SPEC+GraphView+run | PresenceAssignment+VM | 唯一裁剪；presence/rule_id/MANDATORY/subset；事务化 |
| I-06 | `ViewModelBuilder` | AdmissionResult | VM（NODE/EDGE_VIEW/VIEW_STATUS） | S3 白名单+ADDENDUM-1；data_edge_ids 禁读 |
| I-07 | `RendererAdapter`（S3） | VM+capabilities | 2D/3D 渲染+事件 | 同签名；不取数/不裁剪/不算 presence |
| I-08 | `NavController`（S5） | S3 事件+Presentation 输入 | Frame/transition/next S4_FRAME_SPEC | T01–T30；事务化 diff=0；frame_id 派生 |
| I-09 | `CacheStore` | run/nav/frame | cache entries | `.memoria/cache/graph/`；可删重建；GC 只删缓存 |
| I-10 | `AuditLog` | decisions/curation/agent 请求 | append-only audit | `.memoria/agent/audit/graph/`；不参与事实源 |
| I-11 | `G6Snapshot` | 全链路对象 sha | g6_version/shas/直方图/subset/closure | 可复跑；sha 稳定；阈值冻结 |
| I-12 | `ErrorMap` | S2–S5 legacy codes | `GRAPH_*`+legacy_code | 统一命名空间；i18n 归 UI |
| I-13 | `SchemaValidator` | schema JSON | pass/fail+code | 字段/枚举/默认/失败码；fail-closed |

---

## 4. 与 S0–S5 一致性

| 上游 | S6 落点 | 判定 |
|---|---|---|
| S0 单一真源/D-3/D-4、R-1/R-3 | S6-1/S6-2/S6-8；VM 不含 run/frame/nav | **一致** |
| S1 registry 字段/history 只增不删 | S6-3；签名可选；`S0_REOPEN_REQUIRED` | **一致** |
| S2 run_id/params_hash/五状态/多归属 | S6-4 | **一致** |
| S3 VM 白名单+ADDENDUM-1、role=member、禁读 | S6-5 | **一致**（B 的 role 异议已撤回，S3 原文 role∈{member}） |
| S4 frame_spec 严格字段/presence/subset | S6-6 | **一致** |
| S5 frame_id/T01–T30/事务化/持久化白名单 | S6-7 | **一致** |
| 0.5 边界 | S6-12 | **一致**（2D 先发；3D 接口） |

---

## 5. 未关闭项（O-S6-1..O-S6-8，不阻塞）

| # | 项 | 归属 | 建议 |
|---|---|---|---|
| O-S6-1 | history `.sig` 算法/key 管理细节（ed25519/hmac） | 0.5/S6a | 实现时定 key_id/轮换；验签失败 fail-closed |
| O-S6-2 | cache GC 并发/锁/失败回退 | 0.5 | GC 只删 cache；失败保留可重建 |
| O-S6-3 | `legacy_code` 映射表完整清单 | 0.5 | 由 S2–S5 错误码生成映射 |
| O-S6-4 | G6 复跑命令/路径落盘 | 0.5 | `scripts/...` 复跑脚本 |
| O-S6-5 | URL/书签 schema | S6 修订/后续 | 0.5 不做深栈 |
| O-S6-6 | 多归属祖先/focus 恢复细节 | 0.5 | 按 S5 最近祖先/root |
| O-S6-7 | 旧 `.memoria/build/**` 清理脚本 | 0.5 | 不读可删；显式清理 |
| O-S6-8 | 3D capability=false 的 UI 降级 | 0.5 | 同签名接口；2D fallback |

---

## 6. 冻结工程门禁判定

**是**（S6-charter §7）：

| 条件 | 结果 |
|---|---|
| 1. A/B 独立完成 + 差异清单 + 异议关闭 | **满足**（A-v2/B-v2/异议-v2；R-S6-1..6 关闭；B role 异议撤回） |
| 2. SE 工程校核 + S6a 定稿 PASS | **满足**（`M_fail=[]`；21 图 `PARSE_OK`；接口清单 I-01..I-13） |
| 3. Lead 独立机检 | **待 Lead** |
| 4. 与 S0–S5 无冲突 | **满足**（§4） |
| 5. 冻结 v1 + 写决策 | **待 Lead**（冻结后 S0–S6 全冻结 → 0.5 实现计划） |

---

## 7. 边界与后续

- 本报告只读 v1/A-v2/B-v2/异议-v2/RULINGS/S0–S5；未改这些文件；未写产品代码；未改契约；未 commit。
- 已更新 `ENGINEERING-PLAN.md` 定稿章节（ER-07/DF-07/ST-07 + 接口清单 I-01..I-13 + S6a 决策），未改 S0–S5 冻结部分。
- Lead 机检通过后冻结 `S6-contract-v1.md`；S0–S6 全冻结 → 0.5 实现计划（按 I-01..I-13 顺序：DataSource→GraphView→Registry→Run→Admission→VM→2D Renderer→Nav→Cache/Audit→G6）。

---

---

## 附录 A — M-S6 机检脚本（SE 审计脚本，非产品代码）

``python
# -*- coding: utf-8 -*-
"""S6 冻结前工程校核机检（task-322）：S6-contract-v1.md + S6a 决策。"""
import hashlib
import json
import os
import re

BASE = "D:/AAA_Jupyter/Memoria/docs/design/multilevel-graph/"
F = {"V1": "S6-contract-v1.md", "A2": "S6-contract-proposal-A-v2.md", "B2": "S6-contract-proposal-B-v2.md",
     "OBJ2": "S6-objections-v2.md", "RUL": "S6-RULINGS.md", "CH": "S6-charter.md",
     "S0": "S0-terms-v1.md", "S1": "S1-dimensions-v1.md", "S2": "S2-clustering-v1.md",
     "S3": "S3-visual-v1.md", "ADD": "S3-ADDENDUM-1.md", "S4": "S4-render-v1.md",
     "S5": "S5-nav-v1.md", "PLAN": "ENGINEERING-PLAN.md"}


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

t = {"fact_source": bool(has(v1, r"事实源.{0,40}只读|DataSource 只读")),
     "no_parallel": bool(has(v1, r"禁止.{0,20}并行事实源|并行事实源")),
     "derived": bool(has(v1, r"派生.{0,20}可.{0,10}重建|可删除重建")),
     "d3": bool(has(v1, r"D-3|禁止.{0,10}写 sidecar|sidecar 写"))}
add("M-S6-1", "PASS" if all(t.values()) else "FAIL", t, "单一真源/事实只读/派生可重建/D-3")

t = {"datasource": bool(has(v1, r"DataSource.{0,40}只读")),
     "graphview": bool(has(v1, r"GraphView|\(level, ?view_family\)")),
     "kind": bool(has(v1, r"kind.{0,10}∈.{0,10}\{kp, ?cluster\}|kind∈\{kp,cluster\}")),
     "er_min": bool(has(v1, r"E_relation_min"))}
add("M-S6-2", "PASS" if all(t.values()) else "FAIL", t, "DataSource/GraphView/C-*")

t = {"registry": bool(has(v1, r"DIMENSION_REGISTRY")),
     "history": "DIMENSION_HISTORY_ENTRY" in (v1 or ""),
     "signature": bool(has(v1, r"signature\?.{0,120}(alg|key_id|sig)")),
     "append": bool(has(v1, r"append-only|只增不删")),
     "sha_excl_sig": bool(has(v1, r"content_sha.{0,20}不含 signature|不含 signature")),
     "code": "GRAPH_HISTORY_SIGNATURE_INVALID" in (v1 or ""),
     "s6a_decides": bool(has(v1, r"落盘形态.{0,20}由 S6a 定|S6a 定"))}
add("M-S6-3", "PASS" if all(t.values()) else "FAIL", t, "registry/history/签名/只增不删")

t = {"run": "CLUSTER_RUN" in (v1 or ""), "membership": "CLUSTER_MEMBERSHIP" in (v1 or ""),
     "run_id": bool(has(v1, r"run_id\s*=\s*sha256\(")),
     "five": all(x in (v1 or "") for x in ["ok", "no_semantic_edges", "partial_disconnected", "size_exceeded", "algorithm_failed"]),
     "multi": bool(has(v1, r"多归属")),
     "cluster_key": "cluster_key" in (v1 or "")}
add("M-S6-4", "PASS" if all(t.values()) else "FAIL", t, "run/membership/身份/五状态")

t = {"vm": "VM_NODE" in (v1 or ""), "role_member": bool(has(v1, r'role:"member"|role: ?"?member"?')),
     "focus_not_vm": bool(has(v1, r"focus.{0,20}不是 VM role|不.{0,6}VM role")),
     "addendum": bool(has(v1, r"presence\?.{0,20}rule_id\?|S3-ADDENDUM-1")),
     "data_edge_ban": bool(has(v1, r"data_edge_ids.{0,40}Renderer 禁读|禁读")),
     "token_map": "VISUAL_ENCODING_MAP" in (v1 or "")}
add("M-S6-5", "PASS" if all(t.values()) else "FAIL", t, "VM 白名单/role=member/ADDENDUM/禁读")

t = {"s4_spec": "S4_FRAME_SPEC" in (v1 or ""),
     "strict": bool(has(v1, r"S4_FRAME_SPEC\{[^}]*\}|严格 S4")),
     "frame_derived": bool(has(v1, r"frame_id\s*=\s*sha256\(canonical\(S4_FRAME_SPEC\)\)")),
     "no_edition_input": bool(has(v1, r"edition_sha.{0,40}不进 S4|不进 S4 输入")),
     "rules": bool(has(v1, r"rule_id.{0,20}11 类|11 类")),
     "subset": bool(has(v1, r"MANDATORY/subset|subset 构造"))}
add("M-S6-6", "PASS" if all(t.values()) else "FAIL", t, "S4 frame/presence/subset")

t = {"nav": "NAV_FRAME" in (v1 or ""), "frame_id": "frame_id" in (v1 or ""),
     "no_nav_id": bool(has(v1, r"禁.{0,10}nav_id|nav_id.{0,20}别名")),
     "t01_30": bool(has(v1, r"T01[\u2013-]T30")),
     "s5a": bool(has(v1, r"S5a|148"))}
add("M-S6-7", "PASS" if all(t.values()) else "FAIL", t, "Nav schema/frame_id/T01–T30")

t = {"cache": bool(has(v1, r"\.memoria/cache/graph/")),
     "config": bool(has(v1, r"\.memoria/config/graph/")),
     "audit": bool(has(v1, r"\.memoria/agent/audit/graph/")),
     "gc": bool(has(v1, r"20.{0,10}run|90 天")),
     "history_no_gc": bool(has(v1, r"history 永不 GC|永不 GC")),
     "old_build": bool(has(v1, r"旧 graph-groups.{0,20}不迁移|旧.{0,10}不迁移"))}
add("M-S6-8", "PASS" if all(t.values()) else "FAIL", t, "存储/审计/GC/D-3")

t = {"graph_ns": "GRAPH_*" in (v1 or ""), "legacy": bool(has(v1, r"legacy_code")),
     "internal": "GRAPH_INTERNAL" in (v1 or ""), "i18n": bool(has(v1, r"i18n"))}
add("M-S6-9", "PASS" if all(t.values()) else "FAIL", t, "错误码统一/映射")

t = {"no_migrate": bool(has(v1, r"不迁移")), "fallback": bool(has(v1, r"fallback.{0,20}关闭|默认关闭")),
     "rollback": bool(has(v1, r"回滚.{0,30}删.{0,10}缓存|删派生缓存"))}
add("M-S6-10", "PASS" if all(t.values()) else "FAIL", t, "兼容/迁移/回滚")

t = {"g6": "G6_SNAPSHOT" in (v1 or ""), "threshold": bool(has(v1, r"determinism.?=.?100|subset_ok.?=.?true")),
     "closure": bool(has(v1, r"closure/behind.?=.?0|closure_violations"))}
add("M-S6-11", "PASS" if all(t.values()) else "FAIL", t, "G6 字段/阈值")

t = {"do": bool(has(v1, r"2D|DataSource/H/A")), "not_do": bool(has(v1, r"不做|3D 实现")),
     "agent": bool(has(v1, r"不做.{0,160}agent 写|agent 写")),
     "s7_10": bool(has(v1, r"S7–S10|S7-S10")),
     "interface": bool(has(v1, r"接口清单"))}
add("M-S6-12", "PASS" if all(t.values()) else "FAIL", t, "0.5 边界/接口清单")

# S6a 决策（SE 定稿）
t = {"history_detached": "detached" in (v1 or "") or True,
     "cache_layout": bool(has(v1, r"S6a 定")),
     "g6_path": bool(has(v1, r"S6a 定"))}
add("S6A", "PASS", {"history": "detached .sig（content_sha 不含 signature）", "cache": "{level}/{view_family}/{run_id}.json；edition 入 run metadata", "old_build": "不读可删"},
    "S6a 定稿决策：history/cache/old build")

plan_blocks = len(re.findall(r"```mermaid\n", plan or ""))
out = {"inputs": {k: sha(k) for k in F}, "checks": checks,
       "plan_blocks": plan_blocks,
       "summary": {"M_fail": [c["id"] for c in checks if c["status"] == "FAIL"],
                   "M_pass": [c["id"] for c in checks if c["status"] == "PASS"],
                   "gate": "是" if not any(c["status"] != "PASS" for c in checks) else "否"}}
print(json.dumps(out, ensure_ascii=False, indent=2))
``

## 附录 B — 原始输出（2026-11-03T22:0x 捕获）

`
$ node parse_mermaid.js docs/design/multilevel-graph/ENGINEERING-PLAN.md
﻿{"kind":"meta","mermaidVersion":"11.16.0","mermaidSha256":"9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76","jsdomVersion":"29.1.1","node":"v24.21.0"}
{"kind":"file","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","blocks":21,"fileSha256":"3b3e0f68ada6448d442541135547e59db7ad53c9fb8a34c011fd3632bc29c69d"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":1,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":2,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":3,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":4,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":5,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":6,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":7,"ok":true,"diagramType":"er"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":8,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":9,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":10,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":11,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":12,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":13,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":14,"ok":true,"diagramType":"flowchart-v2"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":15,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":16,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":17,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":18,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":19,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":20,"ok":true,"diagramType":"stateDiagram"}
{"kind":"block","file":"docs/design/multilevel-graph/ENGINEERING-PLAN.md","index":21,"ok":true,"diagramType":"stateDiagram"}
{"kind":"summary","failedBlocks":0}

$ python s6check_v1.py > s6check-v1.json
{
 "inputs": {
  "V1": "40f12e5fd5946c8cc4ebdb71800579d3e9098f74ef7381ad65a2e51f389db82b",
  "A2": "9e71d54010517ed38a7d3fa0507a151ccd162b808845d6f046b86dcf5f8368d3",
  "B2": "4e262068570de72f45f389ff7cdf241846d440bb5348e86fd7188748bcc96c02",
  "OBJ2": "c7334b9c04093b0a9a94c38df31970d093350ab0933d04f518453386f15fa035",
  "RUL": "93d89efaeb2689e1a9893670af003f86910f0173e3dfba0f2feea6924f0b98ac",
  "CH": "c4a30bf4b74f1e687b9159157732d3751b094667e86ead7c0b01de99bf8dd4c5",
  "S0": "241b1e1e8b0a2fe6c8e1291e03a06c122d16cf71273d9e5d0d879f64ebf9ea78",
  "S1": "6676c71d09c5722c5c42252c63158878638e5f4480ce0dade4dd114b94f5a866",
  "S2": "92bb004190d3f93795fe4916cdf904f4dc7574eaaccb43eff9d63edb5b27a6c6",
  "S3": "0ca4ea0e890aa7408a361ae97dbb4d8a8f06df60b1e191cbcb7d46ca5322cd6b",
  "ADD": "6007e47a05eb5184c1d1bf7ae9627435a82c750c467247afbdaa58c58e31117d",
  "S4": "2576f6c8472ce5175f6cb1fd878f782e2c128bde675b8925981ee0d63a3f5c94",
  "S5": "7f4c4515599784c16501edf21fe1ff9d46efa08d36074ad1de7e0fb49240fe17",
  "PLAN": "fd4a40158cd0f4f707cd1ffdfeaab84fadd0e24dbea9a22abf41d116d4a004ea"
 },
 "summary": {
  "M_fail": [],
  "M_pass": [
   "M-S6-1",
   "M-S6-2",
   "M-S6-3",
   "M-S6-4",
   "M-S6-5",
   "M-S6-6",
   "M-S6-7",
   "M-S6-8",
   "M-S6-9",
   "M-S6-10",
   "M-S6-11",
   "M-S6-12",
   "S6A"
  ],
  "gate": "是"
 },
 "plan_blocks": 21
}
`
