#!/usr/bin/env python
"""Q1（KP 边界重算）· metrics-baseline 角度：**怎么验"没退化"**

## 本脚本回答的问题（不是门禁实现，是"可验收性探测"）
问题 1 的核心：三个迁移选项（①只重算 end ②全面重切+迁移 kp_id ③不动 KP 另建视图层）
各自怎么验"没退化"？
  · 现有 M4（锚点健康）/ M5（陈旧）够不够？
  · 重切后已有 FSRS 卡 / 链接 / 图谱锚的完整性怎么机检？

## 语料口径（严格按任务要求）
真库 `D:\\AAA_Courses\\数字通信原理`，**排除 .memoria/ 后 26 md / 11 sidecar**
快照：`data/corpus-snapshot.json` taken_at=2026-10-27T14:09:46

## 产出
对每个"完整性维度"给出：**能不能机检 / 用什么算 / 现在实测值**

用法:
    python q1_degradation_probe.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime

REPO = r"D:\AAA_Jupyter\Memoria"
KB = r"D:\AAA_Courses\数字通信原理"
SNAPSHOT = os.path.join(REPO, "artifacts", "agent", "verify", "debate", "kg-retrieval",
                        "data", "corpus-snapshot.json")

os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-q1-"))
sys.path.insert(0, os.path.join(REPO, "src"))


def corpus_mds() -> list[str]:
    """真库中排除 .memoria/ 的 md（= 快照定义的语料）"""
    out = []
    for dp, dn, fn in os.walk(KB):
        dn[:] = [d for d in dn if d not in (".git", "__pycache__", ".memoria")]
        for f in fn:
            if f.endswith(".md"):
                out.append(os.path.relpath(os.path.join(dp, f), KB).replace("\\", "/"))
    return sorted(out)


def probe_kp_inventory() -> dict:
    """用 DocumentService.load_document 拿每个 KP 的真实结构"""
    from memoria.services.document import DocumentService
    t0 = time.perf_counter()
    svc = DocumentService(KB)
    mds = corpus_mds()
    kps = []
    doc_errors = []
    for rel in mds:
        try:
            doc = svc.load_document(rel)
        except Exception as e:
            doc_errors.append({"file": rel, "error": f"{type(e).__name__}: {e}"})
            continue
        if not isinstance(doc, dict):
            doc_errors.append({"file": rel, "error": f"unexpected type {type(doc).__name__}"})
            continue
        for kp in (doc.get("knowledge_points") or []):
            if not isinstance(kp, dict):
                continue
            # ⚠️ 2026-10-27 实测结构（初版读扁平字段导致 snippet 全 None）：
            # "range": {"start": {"snippet","line_hint"}, "end": {"snippet","line_hint"}}
            rng = kp.get("range") or {}
            r_start = rng.get("start") if isinstance(rng, dict) else None
            r_end = rng.get("end") if isinstance(rng, dict) else None
            rr = kp.get("range_resolved") or {}
            kps.append({
                "file": rel,
                "id": kp.get("id"),
                "name": kp.get("name"),
                "start_hint": r_start.get("line_hint") if isinstance(r_start, dict) else None,
                "end_hint": r_end.get("line_hint") if isinstance(r_end, dict) else None,
                "snippet": r_start.get("snippet") if isinstance(r_start, dict) else None,
                "end_snippet": r_end.get("snippet") if isinstance(r_end, dict) else None,
                "range_ok": rr.get("ok") if isinstance(rr, dict) else None,
                "start_line": rr.get("start_line") if isinstance(rr, dict) else None,
                "end_line": rr.get("end_line") if isinstance(rr, dict) else None,
                # 消歧信息：candidates 长度 >1 说明该端不唯一
                "start_candidates": rr.get("start_candidates") if isinstance(rr, dict) else None,
                "end_candidates": rr.get("end_candidates") if isinstance(rr, dict) else None,
                "tags": kp.get("tags"),
            })
    elapsed = time.perf_counter() - t0
    return {"elapsed_ms": round(elapsed * 1000, 1), "docs": len(mds),
            "docs_ok": len(mds) - len(doc_errors), "doc_errors": doc_errors[:5],
            "kp_total": len(kps), "kps": kps}


def analyze_kp_health(kps: list[dict]) -> dict:
    """M4 需要的四个判据 + M2 同名碰撞 + anchor 可用性"""
    total = len(kps)
    if not total:
        return {"error": "no kp"}

    range_ok_false = [k for k in kps if k["range_ok"] is False]
    range_ok_none = [k for k in kps if k["range_ok"] is None]
    inverted = [k for k in kps
                if isinstance(k["start_line"], int) and isinstance(k["end_line"], int)
                and k["end_line"] < k["start_line"]]
    span_zero = [k for k in kps
                 if isinstance(k["start_line"], int) and isinstance(k["end_line"], int)
                 and k["end_line"] == k["start_line"]]
    no_snippet = [k for k in kps if not k["snippet"]]
    no_end_snippet = [k for k in kps if not k["end_snippet"]]

    # snippet 唯一性（M4 判据②的输入）
    sn_counter = Counter(k["snippet"] for k in kps if k["snippet"])
    dup_snippets = {s: n for s, n in sn_counter.items() if n > 1}
    kp_in_dup_snippet = sum(n for n in dup_snippets.values())

    # ★ 端点候选数 >1 == 该端点不唯一（"边界不可靠"的直接机检指标）
    ambiguous_start = [k for k in kps
                       if isinstance(k.get("start_candidates"), list)
                       and len(k["start_candidates"]) > 1]
    ambiguous_end = [k for k in kps
                     if isinstance(k.get("end_candidates"), list)
                     and len(k["end_candidates"]) > 1]
    end_missing = [k for k in kps
                   if isinstance(k.get("end_candidates"), list)
                   and len(k["end_candidates"]) == 0]

    # M2 同名碰撞
    name_by_file = {}
    for k in kps:
        name_by_file.setdefault(k["file"], []).append(k["name"] or k["id"])
    collisions = []
    for f, names in name_by_file.items():
        c = Counter(names)
        for nm, n in c.items():
            if n > 1:
                collisions.append({"file": f, "name": nm, "count": n})
    collide_kp = sum(x["count"] for x in collisions)

    # anchor_verified 的**上界**估计：range_ok 为 True 且 snippet 唯一 且 端点候选唯一
    anchor_ok_candidate = [
        k for k in kps
        if k["range_ok"] is True
        and k["snippet"]
        and sn_counter.get(k["snippet"], 0) == 1
        and not (isinstance(k.get("start_candidates"), list) and len(k["start_candidates"]) > 1)
        and not (isinstance(k.get("end_candidates"), list) and len(k["end_candidates"]) > 1)
    ]

    return {
        "kp_total": total,
        "M4": {
            "range_ok_false": len(range_ok_false),
            "range_ok_none": len(range_ok_none),
            "fresh_ratio": round((total - len(range_ok_false)) / total, 4),
            "inverted": len(inverted),
            "span_zero": len(span_zero),
            "no_snippet": len(no_snippet),
            "no_end_snippet": len(no_end_snippet),
            "dup_snippet_groups": len(dup_snippets),
            "kp_in_dup_snippet": kp_in_dup_snippet,
            "dup_snippet_ratio": round(kp_in_dup_snippet / total, 4),
            "ambiguous_start": len(ambiguous_start),
            "ambiguous_end": len(ambiguous_end),
            "end_candidates_empty": len(end_missing),
            "ambiguous_start_ratio": round(len(ambiguous_start) / total, 4),
            "ambiguous_end_ratio": round(len(ambiguous_end) / total, 4),
        },
        "M2": {
            "collision_groups": len(collisions),
            "collision_kp_total": collide_kp,
            "risk_ratio": round(collide_kp / total, 4),
            "top": sorted(collisions, key=lambda x: -x["count"])[:5],
        },
        "anchor_verified_upper_bound": {
            "count": len(anchor_ok_candidate),
            "ratio": round(len(anchor_ok_candidate) / total, 4),
            "note": ("这是上界：range_ok=True 且 snippet 全局唯一。"
                     "真实 anchor_verified 还要判 end 边界可靠性（需下一级标题信息）"),
        },
        "samples": {
            "range_ok_false": [{"file": k["file"], "id": k["id"]} for k in range_ok_false[:5]],
            "inverted": [{"file": k["file"], "id": k["id"],
                          "start": k["start_line"], "end": k["end_line"]} for k in inverted[:5]],
            "span_zero": [{"file": k["file"], "id": k["id"],
                           "line": k["start_line"]} for k in span_zero[:5]],
        },
    }


def analyze_data_integrity(kps: list[dict]) -> dict:
    """★ 本题核心：重切后已有 FSRS / 链接 / 图谱锚的完整性怎么机检？

    思路：把"锚定关系"分成三类，分别给可机检的判据
      1. FSRS 卡 → kp_id    （cards.json / progress.json）
      2. 链接 → kp_id       （sidecar links[]）
      3. 图谱节点 → kp_id   （collect_graph_data 的 nodes[].kp_id）
    """
    out = {}
    kp_ids = set(k["id"] for k in kps if k["id"])

    # ── 1. FSRS 卡 ──
    review_dir = os.path.join(KB, ".memoria", "agent", "review")
    cards_path = os.path.join(review_dir, "cards.json")
    progress_path = os.path.join(review_dir, "progress.json")
    fsrs = {"cards_file_exists": os.path.exists(cards_path),
            "progress_file_exists": os.path.exists(progress_path)}
    if os.path.exists(cards_path):
        try:
            cards = json.load(open(cards_path, encoding="utf-8"))
            if isinstance(cards, dict):
                cards = cards.get("cards") or list(cards.values())
            n = len(cards) if isinstance(cards, list) else 0
            with_kp = [c for c in cards if isinstance(c, dict) and c.get("kp_id")]
            kp_set = [c for c in with_kp if c.get("kp_id") in kp_ids]
            fsrs.update({
                "cards_total": n,
                "cards_with_kp_id": len(with_kp),
                "cards_kp_id_resolvable": len(kp_set),
                "orphan_rate": round(1 - len(kp_set) / len(with_kp), 4) if with_kp else None,
            })
        except Exception as e:
            fsrs["error"] = f"{type(e).__name__}: {e}"
    out["FSRS_cards"] = fsrs

    # ── 2. 链接（sidecar links[] 指向的 kp）──
    # ⚠️ 2026-10-27 实测结构：link = {anchor_text, occurrence, targets[], edge_type,
    #     target_edges{}, pool[], source_id, instances[], excluded[]}
    #     kp 引用在 targets[] 和 source_id，不是 target/kp_id（初版读错 ⇒ "无 target" 是假的）
    side_dir = os.path.join(KB, ".memoria", "sidecars")
    link_stats = {"sidecar_dir_exists": os.path.isdir(side_dir)}
    if os.path.isdir(side_dir):
        try:
            import yaml
            n_side = 0
            n_links = 0
            src_total = src_ok = 0
            tgt_total = tgt_ok = 0
            inst_total = 0
            bad_links = []
            for dp, dn, fn in os.walk(side_dir):
                for f in fn:
                    if not f.endswith(".yaml"):
                        continue
                    n_side += 1
                    try:
                        sc = yaml.safe_load(open(os.path.join(dp, f), encoding="utf-8"))
                    except Exception:
                        continue
                    if not isinstance(sc, dict):
                        continue
                    for l in (sc.get("links") or []):
                        if not isinstance(l, dict):
                            continue
                        n_links += 1
                        inst_total += len(l.get("instances") or [])
                        sid = l.get("source_id")
                        if sid:
                            src_total += 1
                            if sid in kp_ids:
                                src_ok += 1
                        for t in (l.get("targets") or []):
                            tgt_total += 1
                            if t in kp_ids:
                                tgt_ok += 1
                            else:
                                bad_links.append({"file": f, "target": t})
            link_stats.update({
                "sidecars": n_side,
                "links": n_links,
                "link_instances": inst_total,
                "source_id_total": src_total,
                "source_id_resolvable": src_ok,
                "targets_total": tgt_total,
                "targets_resolvable": tgt_ok,
                "source_orphan_rate": round(1 - src_ok / src_total, 4) if src_total else None,
                "target_orphan_rate": round(1 - tgt_ok / tgt_total, 4) if tgt_total else None,
                "unresolved_sample": bad_links[:5],
            })
        except Exception as e:
            link_stats["error"] = f"{type(e).__name__}: {e}"
    out["links"] = link_stats

    # ── 3. 图谱节点 ──
    try:
        from memoria.graph.collector import collect_graph_data
        gd = collect_graph_data(KB)
        nodes = gd.get("nodes", []) if isinstance(gd, dict) else []
        with_kp = [n for n in nodes if n.get("kp_id")]
        resolvable = [n for n in with_kp if n.get("kp_id") in kp_ids]
        out["graph_nodes"] = {
            "nodes": len(nodes),
            "nodes_with_kp_id": len(with_kp),
            "kp_id_resolvable": len(resolvable),
            "orphan_rate": round(1 - len(resolvable) / len(with_kp), 4) if with_kp else None,
        }
    except Exception as e:
        out["graph_nodes"] = {"error": f"{type(e).__name__}: {e}"}

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    print("=" * 78)
    print("Q1 · KP 边界重算：可验收性探测（metrics-baseline 角度）")
    print("=" * 78)

    snap_meta = {}
    if os.path.exists(SNAPSHOT):
        snap = json.load(open(SNAPSHOT, encoding="utf-8"))
        tgt = snap["kbs"].get("数字通信原理", {})
        snap_meta = {"taken_at": snap["taken_at"],
                     "md_in_snapshot": len(tgt.get("md", [])),
                     "sidecar_in_snapshot": len(tgt.get("sidecars", []))}
    print(f"快照: {snap_meta}")

    mds = corpus_mds()
    print(f"当前语料 md（排除 .memoria/）: {len(mds)}")
    print()

    t0 = time.perf_counter()
    inv = probe_kp_inventory()
    print(f"── KP 清单采集 ──")
    print(f"  耗时 {inv['elapsed_ms']} ms  docs={inv['docs']} 成功={inv['docs_ok']} "
          f"KP={inv['kp_total']}")
    if inv["doc_errors"]:
        print(f"  文档错误 {len(inv['doc_errors'])}: {inv['doc_errors'][:2]}")
    print()

    if inv["kp_total"] == 0:
        print("❌ 未采集到 KP，后续分析无法进行")
        return 1

    health = analyze_kp_health(inv["kps"])
    print("── M4 锚点健康（现在能算吗）──")
    m4 = health["M4"]
    print(f"  KP 总数: {health['kp_total']}")
    print(f"  range_ok=False: {m4['range_ok_false']}   (fresh={m4['fresh_ratio']:.2%})")
    print(f"  range_ok=None : {m4['range_ok_none']}")
    print(f"  反转: {m4['inverted']}   span=0: {m4['span_zero']}")
    print(f"  snippet 缺失: {m4['no_snippet']}  end_snippet 缺失: {m4['no_end_snippet']}")
    print(f"  snippet 重复组: {m4['dup_snippet_groups']}  "
          f"涉及 KP: {m4['kp_in_dup_snippet']} ({m4['dup_snippet_ratio']:.2%})")
    print(f"  ★ 端点不唯一: start {m4['ambiguous_start']} ({m4['ambiguous_start_ratio']:.2%})  "
          f"end {m4['ambiguous_end']} ({m4['ambiguous_end_ratio']:.2%})")
    print(f"  end 候选为空: {m4['end_candidates_empty']}")
    print()

    print("── M2 同名碰撞 ──")
    m2 = health["M2"]
    print(f"  碰撞组: {m2['collision_groups']}  涉及 KP: {m2['collision_kp_total']} "
          f"({m2['risk_ratio']:.2%})")
    for t in m2["top"][:3]:
        print(f"    {t['file']}: '{t['name']}' ×{t['count']}")
    print()

    ab = health["anchor_verified_upper_bound"]
    print("── anchor_verified 上界（R1 falsifier 阈值 50%）──")
    print(f"  可用: {ab['count']}/{health['kp_total']} = {ab['ratio']:.2%}  "
          f"{'✅ 过 50%' if ab['ratio'] >= 0.5 else '❌ 不足 50%'}")
    print(f"  说明: {ab['note']}")
    print()

    print("── ★ 已有数据的锚定完整性（本题核心）──")
    integ = analyze_data_integrity(inv["kps"])
    for cat, d in integ.items():
        print(f"  [{cat}]")
        for k, v in d.items():
            if k in ("error",):
                print(f"    ❌ {v}")
            else:
                print(f"    {k:<28} {v}")
    print()

    elapsed = time.perf_counter() - t0
    payload = {
        "schema": "q1-degradation-probe/v1",
        "measured_at": datetime.now().astimezone().isoformat(),
        "head": os.popen(f'git -C "{REPO}" rev-parse HEAD').read().strip(),
        "kb": KB,
        "snapshot": snap_meta,
        "corpus_md_now": len(mds),
        "inventory": {"elapsed_ms": inv["elapsed_ms"], "docs": inv["docs"],
                      "docs_ok": inv["docs_ok"], "kp_total": inv["kp_total"],
                      "doc_errors": inv["doc_errors"]},
        "M4_anchor_health": health["M4"],
        "M2_collision": health["M2"],
        "anchor_verified_upper_bound": health["anchor_verified_upper_bound"],
        "data_integrity": integ,
        "samples": health["samples"],
        "total_elapsed_s": round(elapsed, 2),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifact_sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print(f"总耗时: {elapsed:.1f}s")
    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
        print(f"sha256: {payload['artifact_sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
