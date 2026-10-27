# -*- coding: utf-8 -*-
"""verify_q1_independent.py — Q1 复核：独立复算（不复用研究员脚本逻辑）。

复核对象：round2/Q1-research.md（研究员材料）+ round2/data/q1-research.json
快照：round2/frozen/数字通信原理（26 md / 11 sidecar，sha256 见 round2/frozen/MANIFEST.json）

独立性约定：
  · 侧车用 PyYAML 解析（研究员用自写正则解析器）
  · range 解析用产品真值 memoria.range.locator.resolve_range / kp_resolver（研究员自己重写了 locate）
  · 标题结构用产品唯一实现 memoria.services.heading_proposals.scan_headings
  · 孤儿/链接/图谱用产品函数（build_kp_index / collect_graph_data / derive_*）
  · 只读；不写活动库、不建索引库

输出：round2/scripts-verify/out/q1-independent.json（无时间戳，可两次比对 sha256）
Run: python artifacts/agent/verify/debate/kg-retrieval/round2/scripts-verify/verify_q1_independent.py
"""
import os
import re
import sys
import json
import hashlib
import collections

REPO = r"D:\AAA_Jupyter\Memoria"
ROOT = os.path.join(REPO, "artifacts", "agent", "verify", "debate", "kg-retrieval")
FROZEN = os.path.join(ROOT, "round2", "frozen", "数字通信原理")
MANIFEST = os.path.join(ROOT, "round2", "frozen", "MANIFEST.json")
CORPUS_SNAPSHOT = os.path.join(ROOT, "data", "corpus-snapshot.json")
OUTDIR = os.path.join(ROOT, "round2", "scripts-verify", "out")
LIVE = r"D:\AAA_Courses\数字通信原理"

sys.path.insert(0, os.path.join(REPO, "src"))
import yaml  # noqa: E402
from memoria.range.locator import resolve_range  # noqa: E402
from memoria.range.constants import SNIPPET_MAX_LEN, HINT_WINDOW  # noqa: E402
from memoria.services.heading_proposals import scan_headings  # noqa: E402
from memoria.storage.markdown import strip_frontmatter  # noqa: E402


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pctl(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def dist(vals):
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "p50": pctl(vals, 50), "p90": pctl(vals, 90),
            "max": max(vals), "mean": round(sum(vals) / len(vals), 2),
            "min": min(vals)}


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def line_chars(lines, a, b):
    """1-based inclusive，与产品 read_kp 返回的 join('\\n') 字符数同口径。"""
    if b < a or a < 1 or a > len(lines):
        return 0
    b = min(b, len(lines))
    seg = lines[a - 1:b]
    return sum(len(x) for x in seg) + max(0, len(seg) - 1)


def norm_snip(s):
    return re.sub(r"\s+", " ", s or "").strip()


def occ_lines_of(lines, snippet):
    """产品 locate_snippet 的匹配口径：needle=snippet.strip()[:80]，逐行 strip 后子串匹配。"""
    needle = norm_snip(snippet)[:SNIPPET_MAX_LEN]
    if not needle:
        return needle, []
    return needle, [i + 1 for i, ln in enumerate(lines) if needle in ln.strip()]


def owner_section(heads, line):
    """返回 (owner heading, section end line)。与产品 heading 提案口径一致：下一同级标题前。"""
    owner, oi = None, -1
    for k, h in enumerate(heads):
        if h.line_no <= line:
            owner, oi = h, k
        else:
            break
    if owner is None:
        return None, (heads[0].line_no - 1 if heads else None)
    end = None
    for h in heads[oi + 1:]:
        if h.level <= owner.level:
            end = h.line_no - 1
            break
    return owner, end


def ctx_sig(lines, line):
    """前文上下文签名：取该行之前最多 2 个非空行 + 该行前 20 字，规范化后 sha1 前 12 位。"""
    prev = []
    i = line - 2
    while i >= 0 and len(prev) < 2:
        t = lines[i].strip()
        if t:
            prev.append(t)
        i -= 1
    cur = lines[line - 1].strip()[:20] if 0 <= line - 1 < len(lines) else ""
    return hashlib.sha1(("␟".join(prev) + "␟" + cur).encode("utf-8")).hexdigest()[:12]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    man = json.load(open(MANIFEST, encoding="utf-8"))
    files = {f["path"]: f for f in man["files"]}
    md_files = sorted(p for p in files if p.endswith(".md"))
    side_files = sorted(p for p in files if p.endswith(".memoria.yaml"))

    # ---------- A. 快照自检（frozen / live / corpus-snapshot 三方）
    frozen_bad, live_bad = [], []
    for p, meta in files.items():
        fp = os.path.join(FROZEN, *p.split("/"))
        lp = os.path.join(LIVE, *p.split("/"))
        if not os.path.isfile(fp) or sha_file(fp) != meta["sha256"]:
            frozen_bad.append(p)
        if not os.path.isfile(lp) or sha_file(lp) != meta["sha256"]:
            live_bad.append(p)
    snap_cmp = {"snapshot_md": 0, "snapshot_sidecar": 0, "manifest_vs_snapshot_mismatch": []}
    if os.path.isfile(CORPUS_SNAPSHOT):
        cs = json.load(open(CORPUS_SNAPSHOT, encoding="utf-8"))
        cs_kb = cs["kbs"]["数字通信原理"]
        snap_cmp["snapshot_md"] = len(cs_kb["md"])
        snap_cmp["snapshot_sidecar"] = len(cs_kb["sidecars"])
        in_snap = {e["path"]: e["sha256"] for e in cs_kb["md"] + cs_kb["sidecars"]}
        for p, meta in files.items():
            if p not in in_snap:
                snap_cmp["manifest_vs_snapshot_mismatch"].append({"path": p, "why": "not_in_snapshot"})
            elif in_snap[p] != meta["sha256"]:
                snap_cmp["manifest_vs_snapshot_mismatch"].append(
                    {"path": p, "why": "sha_differs", "snapshot": in_snap[p][:12],
                     "manifest": meta["sha256"][:12]})

    # ---------- B/C. 语料 + 产品解析
    texts, lines_by, heads_by = {}, {}, {}
    for rel in md_files:
        raw = open(os.path.join(FROZEN, *rel.split("/")), encoding="utf-8").read()
        body, _ = strip_frontmatter(raw)
        texts[rel] = body
        lines_by[rel] = body.splitlines()
        heads_by[rel] = scan_headings(body)

    kps = []
    sidecar_files_seen = []
    for rel in side_files:
        data = yaml.safe_load(open(os.path.join(FROZEN, *rel.split("/")), encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        sidecar_files_seen.append(rel)
        rel_md = data.get("file")
        if rel_md not in texts:
            continue
        lines, heads = lines_by[rel_md], heads_by[rel_md]
        for kp in data.get("knowledge_points") or []:
            rng = kp.get("range") or {}
            ss, es = rng.get("start") or {}, rng.get("end") or {}
            rr = resolve_range(lines, ss, es)
            kps.append({"id": kp.get("id"), "name": kp.get("name"), "file": rel_md,
                        "sidecar": rel, "ss": ss, "es": es, "rr": rr,
                        "role": ("教材" if rel_md.startswith("教材/") else
                                 ("slides" if rel_md.startswith("img/") else "notes")) })

    # 产品解析状态
    err = collections.Counter()
    for k in kps:
        if not k["rr"].get("ok"):
            err[str(k["rr"].get("error"))] += 1
    prod_ok = [k for k in kps if k["rr"].get("ok")]
    prod_fail = [k for k in kps if not k["rr"].get("ok")]

    # KP 角色计数 / start 是否标题行
    roles = collections.Counter(k["role"] for k in kps)
    for k in kps:
        st = k["rr"].get("start_line")
        k["start_is_heading"] = bool(st and any(h.line_no == st for h in heads_by[k["file"]]))

    # ---------- D. 锚点 gate（R1 三判据的忠实实现 vs 研究员四档）
    def gate_variants(k):
        lines, heads = lines_by[k["file"]], heads_by[k["file"]]
        rr = k["rr"]
        ok = bool(rr.get("ok"))
        out = {"ok": ok}
        if not ok:
            out.update({"strict": False, "section": False, "context": False,
                        "lenient": False, "hint_verified": False, "occ": 0,
                        "line": None, "in_section": 0, "ctx_unique": False})
            # 失败时也尽可能识别 start 位置，供 end 分析
            needle, occ = occ_lines_of(lines, k["ss"].get("snippet"))
            hint = k["ss"].get("line_hint")
            out["occ"] = len(occ)
            out["line"] = min(occ, key=lambda x: abs(x - hint)) if (occ and hint) else (occ[0] if occ else None)
            out["hint_verified"] = bool(hint and hint in occ)
            return out
        s = rr["start_line"]
        needle, occ = occ_lines_of(lines, k["ss"].get("snippet"))
        hint = k["ss"].get("line_hint")
        hint_ok = bool(hint and hint in occ)
        owner, sec_end = owner_section(heads, s)
        lo = owner.line_no if owner else 1
        hi = sec_end if sec_end is not None else len(lines)
        in_sec = [x for x in occ if lo <= x <= hi]
        # 取离 hint 最近 / 离已解析 start 最近的 occurrence 作为"被选中的那一次"
        chosen = s
        ctxs = [ctx_sig(lines, x) for x in occ]
        chosen_ctx = ctx_sig(lines, chosen)
        ctx_unique = (ctxs.count(chosen_ctx) == 1)
        out.update({
            "occ": len(occ), "hint_verified": hint_ok, "line": s,
            "in_section": len(set(in_sec)), "ctx_unique": ctx_unique,
            "strict": len(occ) == 1,
            "section": (len(occ) == 1 or len(set(in_sec)) == 1),
            "context": (len(occ) == 1 or len(set(in_sec)) == 1 or ctx_unique),
            "lenient": (len(occ) == 1 or len(set(in_sec)) == 1 or ctx_unique or hint_ok),
        })
        return out

    for k in kps:
        k["gate"] = gate_variants(k)

    def gate_box(rs):
        n = len(rs)
        return {"n": n, "ok": sum(1 for k in rs if k["gate"]["ok"]),
                "ok_pct": pct(sum(1 for k in rs if k["gate"]["ok"]), n),
                "strict": sum(1 for k in rs if k["gate"]["strict"]),
                "strict_pct": pct(sum(1 for k in rs if k["gate"]["strict"]), n),
                "section": sum(1 for k in rs if k["gate"]["section"]),
                "section_pct": pct(sum(1 for k in rs if k["gate"]["section"]), n),
                "context": sum(1 for k in rs if k["gate"]["context"]),
                "context_pct": pct(sum(1 for k in rs if k["gate"]["context"]), n),
                "lenient": sum(1 for k in rs if k["gate"]["lenient"]),
                "lenient_pct": pct(sum(1 for k in rs if k["gate"]["lenient"]), n),
                "snippet_multi": sum(1 for k in rs if k["gate"]["occ"] > 1),
                "snippet_multi_pct": pct(sum(1 for k in rs if k["gate"]["occ"] > 1), n),
                "unresolved_ids": [k["id"] for k in rs if not k["gate"]["ok"]],
                "ambiguous_strict_ids": [k["id"] for k in rs if k["gate"]["ok"] and not k["gate"]["section"]][:12],
                }

    gate = {r: gate_box(kps if r == "all" else [k for k in kps if k["role"] == r])
            for r in ("all", "教材", "slides", "notes")}

    # ---------- E. KP 尺寸：四种口径
    def sizes(k, which):
        lines, heads = lines_by[k["file"]], heads_by[k["file"]]
        rr = k["rr"]
        start = rr.get("start_line") if rr.get("ok") else k["gate"]["line"]
        if start is None:
            start = k["ss"].get("line_hint") or 1
        owner, sec_end = owner_section(heads, start)
        boundary = sec_end if sec_end is not None else len(lines)
        boundary = max(boundary, start)
        end_hint = k["es"].get("line_hint") or start
        end_raw = rr.get("end_line") if rr.get("ok") else None
        if which == "hint":
            return line_chars(lines, start, end_hint)
        if which == "resolved_raw":
            return line_chars(lines, start, end_raw if end_raw else start)
        if which == "clamped":  # 研究员 v2 size_resolved 口径：min(resolved_end, boundary)
            return line_chars(lines, start, min(end_raw, boundary) if end_raw else boundary)
        if which == "heading":  # 语义边界：end = 下一同级标题前
            return line_chars(lines, start, boundary)
        raise ValueError(which)

    def size_box(rs, which):
        vals = [sizes(k, which) for k in rs]
        gt = sum(1 for v in vals if v > 1200)
        return dict(dist(vals), gt1200=gt, gt1200_pct=pct(gt, len(vals)),
                    gt3000_pct=pct(sum(1 for v in vals if v > 3000), len(vals)))

    size = {}
    for which in ("hint", "resolved_raw", "clamped", "heading"):
        size[which] = {"all": size_box(kps, which),
                       "textbook": size_box([k for k in kps if k["role"] == "教材"], which)}

    # end 修复需求（R1 ③）
    end_stats = {"end_beyond_boundary": 0, "end_multi": 0, "end_missing": 0,
                 "inverted": 0, "span_zero": 0, "need_repair": 0, "ids_need_repair": []}
    for k in kps:
        lines, heads = lines_by[k["file"]], heads_by[k["file"]]
        rr = k["rr"]
        blocks = []
        if rr.get("error") == "end_snippet_not_found":
            blocks.append("end_missing")
        elif rr.get("error") == "end_before_start":
            blocks.append("inverted")
        if rr.get("ok"):
            start, end = rr["start_line"], rr["end_line"]
            owner, sec_end = owner_section(heads, start)
            boundary = max(sec_end if sec_end is not None else len(lines), start)
            if end > boundary:
                blocks.append("end_beyond_boundary")
            if end == start:
                blocks.append("span_zero")
            _, eocc = occ_lines_of(lines, k["es"].get("snippet"))
            if len(eocc) > 1:
                blocks.append("end_multi")
        else:
            if rr.get("error") == "end_snippet_not_found":
                _, eocc = occ_lines_of(lines, k["es"].get("snippet"))
                if len(eocc) > 1:
                    blocks.append("end_multi")
        for b in blocks:
            end_stats[b] += 1
        if blocks:
            end_stats["need_repair"] += 1
            if len(end_stats["ids_need_repair"]) < 20:
                end_stats["ids_need_repair"].append({"id": k["id"], "why": blocks})
    end_stats["need_repair_pct"] = pct(end_stats["need_repair"], len(kps))
    end_stats.pop("ids_need_repair")  # 只保留计数，避免输出膨胀

    # ---------- F. 同名碰撞（口径对照）
    def dup_box(rs, keyfn):
        g = collections.defaultdict(list)
        for k in rs:
            g[keyfn(k)].append(k)
        coll = {kk: v for kk, v in g.items() if len(v) > 1}
        units = sum(len(v) for v in coll.values())
        cols = sorted(coll.values(), key=len, reverse=True)
        top15 = cols[:15]
        return {"groups": len(coll), "units": units,
                "units_pct": pct(units, len(rs)),
                "mean_wrong_rate_all_groups": round(
                    sum((len(v) - 1) / len(v) for v in coll.values()) / len(coll), 4) if coll else 0,
                "mean_wrong_rate_top15": round(
                    sum((len(v) - 1) / len(v) for v in top15) / len(top15), 4) if top15 else 0,
                "unit_weighted_wrong_rate": round(units and (1 - len(coll) / units), 4) if units else 0,
                }

    names = lambda k: norm_snip(k["name"])
    dup = {"same_file": dup_box(kps, lambda k: (names(k), k["file"])),
           "global": dup_box(kps, names),
           "same_file_start": dup_box(kps, lambda k: (names(k), k["file"], k["gate"]["line"]))}

    # ---------- G. 用户数据：sidecar links / edges（YAML 真值）
    links, edges = [], []
    for rel in sidecar_files_seen:
        data = yaml.safe_load(open(os.path.join(FROZEN, *rel.split("/")), encoding="utf-8")) or {}
        for l in data.get("links") or []:
            links.append(dict(l, sidecar=rel))
        for e in data.get("edges") or []:
            edges.append(dict(e, sidecar=rel))
    kp_ids = {k["id"] for k in kps}
    link_targets = [t for l in links for t in (l.get("targets") or [])]
    link_sources = [l.get("source_id") for l in links if l.get("source_id")]
    edge_pairs = [(e.get("source_id"), t) for e in edges for t in (e.get("targets") or [])]
    userdata = {
        "links": len(links), "link_instances": sum(len(l.get("instances") or []) for l in links),
        "link_targets": len(link_targets),
        "link_target_orphans": sorted({t for t in link_targets if t not in kp_ids}),
        "link_source_orphans": sorted({s for s in link_sources if s not in kp_ids}),
        "edges": len(edges), "edge_pairs": len(edge_pairs),
        "edge_source_orphans": sorted({s for s, _ in edge_pairs if s not in kp_ids}),
        "edge_target_orphans": sorted({t for _, t in edge_pairs if t not in kp_ids}),
        "links_with_instances": sum(1 for l in links if l.get("instances")),
    }

    # 产品图谱（真值）
    from memoria.graph.collector import collect_graph_data
    gd = collect_graph_data(FROZEN)
    graph = {"nodes": len(gd["nodes"]), "edges": len(gd["edges"]),
             "by_type": dict(collections.Counter(e.get("type") for e in gd["edges"]))}
    # A2（end=下一同级标题）下的图谱 churn：monkeypatch kp_resolver.resolve_range
    import memoria.services.kp_resolver as kr
    orig_resolve_range = kr.resolve_range
    a2_cache = {}

    def patched(lines, start_spec, end_spec):
        rr = orig_resolve_range(lines, start_spec, end_spec)
        if not rr.get("ok"):
            return rr
        body = "\n".join(lines)
        key = id(lines)
        heads = a2_cache.get(key)
        if heads is None:
            heads = scan_headings(body)
            a2_cache[key] = heads
        start = rr["start_line"]
        owner, sec_end = owner_section(heads, start)
        boundary = sec_end if sec_end is not None else len(lines)
        return {"ok": True, "start_line": start, "end_line": max(boundary, start),
                "start_candidates": rr.get("start_candidates") or [],
                "end_candidates": rr.get("end_candidates") or []}

    try:
        from memoria.services import kp_resolver as kr2
        kr2.resolve_range = patched
        gd_a2 = collect_graph_data(FROZEN)
    finally:
        kr.resolve_range = orig_resolve_range
    old_edges = {(e.get("type"), e.get("source_id"), tuple(e.get("targets") or [])) for e in gd["edges"]}
    new_edges = {(e.get("type"), e.get("source_id"), tuple(e.get("targets") or [])) for e in gd_a2["edges"]}
    graph["a2_churn"] = {"edges_before": len(old_edges), "edges_after": len(new_edges),
                         "added": len(new_edges - old_edges), "removed": len(old_edges - new_edges)}

    # ---------- H. 孤儿率：方向 × scope（独立口径：leaf-section 分段 + 行覆盖率）
    def kp_spans(rs):
        out = {}
        for k in rs:
            lines, heads = lines_by[k["file"]], heads_by[k["file"]]
            rr = k["rr"]
            start = rr.get("start_line") if rr.get("ok") else k["gate"]["line"]
            if start is None:
                start = k["ss"].get("line_hint") or 1
            owner, sec_end = owner_section(heads, start)
            boundary = max(sec_end if sec_end is not None else len(lines), start)
            out[k["id"]] = (k["file"], start, boundary)
        return out

    spans = kp_spans(kps)

    def coverage_table(rel, slices):
        """slices: list[(start,end)]，返回 (orphan_any, orphan_lt50, n, chars)"""
        n = len(slices)
        no_kp = lt50 = 0
        covered_chars = 0
        total = 0
        for (a, b) in slices:
            ch = line_chars(lines_by[rel], a, b)
            total += ch
            cov = 0
            for (f, s, e) in spans.values():
                if f != rel:
                    continue
                if e < a or s > b:
                    continue
                cov += line_chars(lines_by[rel], max(a, s), min(b, e))
            covered_chars += min(cov, ch)
            if cov == 0:
                no_kp += 1
                lt50 += 1
            elif cov < 0.5 * ch:
                lt50 += 1
        return {"slices": n, "orphan_any": no_kp, "orphan_any_pct": pct(no_kp, n),
                "orphan_lt50": lt50, "orphan_lt50_pct": pct(lt50, n),
                "char_coverage_pct": pct(covered_chars, total)}

    def leaf_partition(rel):
        lines, heads = lines_by[rel], heads_by[rel]
        if not heads:
            return [(1, len(lines))]
        out = []
        if heads[0].line_no > 1:
            out.append((1, heads[0].line_no - 1))
        for i, h in enumerate(heads):
            end = heads[i + 1].line_no - 1 if i + 1 < len(heads) else len(lines)
            if end >= h.line_no:
                out.append((h.line_no, end))
        return out

    kp_files = sorted({k["file"] for k in kps})
    orphan = {
        "rule": "独立口径：leaf section（每个 heading 到下一个 heading 前）作为切片；"
                "折叠空白行不切；不看 200-1200 打包",
        "scope_kp_files": {"files": len(kp_files),
                           "slices": sum(len(leaf_partition(f)) for f in kp_files)},
        "per_file_kp_files": {},
        "kp_to_slice_zero": 0,
    }
    # 逐文件统计 + 汇总（kp_files scope）
    agg = {"slices": 0, "orphan_any": 0, "orphan_lt50": 0}
    chars_all, covered_all = 0, 0
    for rel in kp_files:
        t = coverage_table(rel, leaf_partition(rel))
        chars_total = line_chars(lines_by[rel], 1, len(lines_by[rel]))
        covered = 0
        for (a, b) in leaf_partition(rel):
            ch = line_chars(lines_by[rel], a, b)
            cov = 0
            for (f, s, e) in spans.values():
                if f != rel:
                    continue
                if e < a or s > b:
                    continue
                cov += line_chars(lines_by[rel], max(a, s), min(b, e))
            covered += min(cov, ch)
        chars_all += chars_total
        covered_all += covered
        orphan["per_file_kp_files"][rel] = {
            **t, "char_coverage_pct": pct(covered, chars_total)}
        agg["slices"] += t["slices"]
        agg["orphan_any"] += t["orphan_any"]
        agg["orphan_lt50"] += t["orphan_lt50"]
    orphan["scope_kp_files"].update({
        "slices": agg["slices"], "orphan_any_pct": pct(agg["orphan_any"], agg["slices"]),
        "orphan_lt50_pct": pct(agg["orphan_lt50"], agg["slices"]),
        "char_coverage_pct": pct(covered_all, chars_all),
    })
    # all 26 scope
    all_slices = 0
    all_orph = 0
    for rel in md_files:
        t = coverage_table(rel, leaf_partition(rel))
        all_slices += t["slices"]
        all_orph += t["orphan_any"]
    orphan["scope_all_26"] = {"files": len(md_files), "slices": all_slices,
                             "orphan_any_pct": pct(all_orph, all_slices)}
    # KP→切片：每个 KP 至少落在自己的 span 里 ⇒ 0（构造性）；给出计数以说明该方向恒可满足
    orphan["kp_to_slice_zero"] = 0

    # ---------- I. 备份/回滚机制（代码事实 + 目录事实）
    backups_root = os.path.join(LIVE, ".memoria", "agent", "backups")
    rollback = {"backups_root_exists": os.path.isdir(backups_root), "sessions": []}
    if os.path.isdir(backups_root):
        for sid in sorted(os.listdir(backups_root)):
            sdir = os.path.join(backups_root, sid)
            if not os.path.isdir(sdir):
                continue
            batches = []
            for tx in sorted(os.listdir(sdir)):
                tdir = os.path.join(sdir, tx)
                if not os.path.isdir(tdir):
                    continue
                batches.append({"txid": tx,
                                "journal": os.path.isfile(os.path.join(tdir, "journal.json")),
                                "post": os.path.isfile(os.path.join(tdir, "post.json"))})
            rollback["sessions"].append({"session": sid, "batches": batches[-3:],
                                         "n_batches": len(batches)})
    rollback["code_facts"] = {
        "restore_batch": "src/memoria/services/agent/backup.py:529（逐字节写回；默认 fail-closed：无 post.json 拒绝撤销）",
        "undo_step": "src/memoria/services/agent/backup.py:1148（走会话栈 txids/cursor）",
        "backup_scope": "只覆盖经 agent 计划管线写入的文件集（snapshot_pre_images 显式传入 rels）",
        "retention": "KEEP_BATCHES_PER_SESSION / trim_backups 会按 FIFO 淘汰旧批次",
    }
    # sidecar schema：未知字段是否被保留（代码事实）
    schema_facts = {
        "normalize_sidecar_data": "src/memoria/storage/sidecar.py:42 只规整 range，不白名单字段",
        "save_sidecar": "src/memoria/storage/sidecar.py:116 atomic_write_yaml(path, data) 原样落盘",
        "sidecar_kp_fields_observed": None,
    }
    # 现网 sidecar 里 KP 实际字段（判断 R1 复合 anchor 是否可验证）
    field_counter = collections.Counter()
    for rel in sidecar_files_seen:
        data = yaml.safe_load(open(os.path.join(FROZEN, *rel.split("/")), encoding="utf-8")) or {}
        for kp in data.get("knowledge_points") or []:
            for f in kp.keys():
                field_counter[f] += 1
            rng = kp.get("range") or {}
            for endname, ep in rng.items():
                for f in (ep or {}).keys():
                    field_counter[f"range.{endname}.{f}"] += 1
    schema_facts["sidecar_kp_fields_observed"] = dict(field_counter)

    # ---------- J. 会话文件（活动对象；Q1 若引用会话锚必须绑快照）
    sess_dir = os.path.join(LIVE, ".memoria", "agent", "sessions")
    sessions = []
    if os.path.isdir(sess_dir):
        for f in sorted(os.listdir(sess_dir)):
            fp = os.path.join(sess_dir, f)
            if os.path.isfile(fp):
                sessions.append({"file": f, "bytes": os.path.getsize(fp)})
    live_moving = {"frozen_snapshot_contains_agent_dir": os.path.isdir(
        os.path.join(FROZEN, ".memoria", "agent")), "live_sessions": sessions}

    out = {
        "A_snapshot": {
            "manifest": os.path.relpath(MANIFEST, ROOT).replace("\\", "/"),
            "frozen_at": man.get("frozen_at"),
            "md": len(md_files), "sidecars": len(side_files),
            "frozen_sha_mismatch": frozen_bad,
            "live_sha_mismatch": live_bad,
            "corpus_snapshot": snap_cmp,
        },
        "B_inventory": {"kps": len(kps), "roles": dict(roles),
                        "sidecar_kp_md_pairs": len(sidecar_files_seen),
                        "start_is_heading_pct_all": pct(sum(1 for k in kps if k["start_is_heading"]), len(kps)),
                        "start_is_heading_pct_textbook": pct(
                            sum(1 for k in kps if k["role"] == "教材" and k["start_is_heading"]),
                            roles.get("教材", 0))},
        "C_product_resolution": {
            "ok": len(prod_ok), "ok_pct": pct(len(prod_ok), len(kps)),
            "fail": len(prod_fail), "fail_by_error": dict(err),
            "fail_ids": [{"id": k["id"], "file": k["file"], "error": k["rr"].get("error")}
                         for k in prod_fail],
            "fresh_meaning": "产品 resolve_range.ok=True 的比例（read_kp 实际依赖该值）",
        },
        "D_anchor_gate": gate,
        "E_size": size,
        "F_end_repair": end_stats,
        "G_duplicates": dup,
        "H_userdata": userdata,
        "I_graph": graph,
        "J_orphan": orphan,
        "K_rollback": rollback,
        "L_schema": schema_facts,
        "M_live_moving": live_moving,
    }
    json.dump(out, open(os.path.join(OUTDIR, "q1-independent.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, sort_keys=True)

    # ---------- 打印摘要
    print("# Q1 独立复核 — 产品真值复算（frozen 2026-10-27T14:09:46）")
    a = out["A_snapshot"]
    print(f"\nA 快照: md={a['md']} sidecar={a['sidecars']} frozen_bad={len(a['frozen_sha_mismatch'])} "
          f"live_bad={len(a['live_sha_mismatch'])} "
          f"manifest_vs_snapshot_mismatch={len(a['corpus_snapshot']['manifest_vs_snapshot_mismatch'])}")
    b = out["B_inventory"]
    print(f"B 盘点: kps={b['kps']} roles={b['roles']} start=标题行 {b['start_is_heading_pct_all']}% / "
          f"教材 {b['start_is_heading_pct_textbook']}%")
    c = out["C_product_resolution"]
    print(f"C 产品 range 解析: ok={c['ok']} ({c['ok_pct']}%) fail={c['fail']} {c['fail_by_error']}")
    for k in c["fail_ids"]:
        print("   FAIL", k)
    print("\nD 锚点 gate（产品 ok 为前提）:")
    for r, v in gate.items():
        print(f"  [{r}] n={v['n']} ok={v['ok_pct']}% strict={v['strict_pct']}% "
              f"section={v['section_pct']}% context={v['context_pct']}% lenient={v['lenient_pct']}% "
              f"snippet_multi={v['snippet_multi_pct']}%")
    print("\nE 尺寸四口径（all p50/p90/>1200% | textbook p50/p90/>1200%）:")
    for w, v in size.items():
        x, y = v["all"], v["textbook"]
        print(f"  {w:13s} all {x['p50']}/{x['p90']}/{x['gt1200_pct']}%  "
              f"教材 {y['p50']}/{y['p90']}/{y['gt1200_pct']}%")
    print("\nF end 修复需求:", end_stats)
    print("\nG 同名碰撞:", json.dumps(dup, ensure_ascii=False))
    print("\nH 用户数据 links/edges:", {k: v for k, v in userdata.items() if not k.endswith("orphans")})
    print("   link_target_orphans:", userdata["link_target_orphans"],
          " edge orphans:", userdata["edge_source_orphans"], userdata["edge_target_orphans"])
    print("\nI 图谱(产品 collect_graph_data):", graph)
    print("\nJ 孤儿率(独立 leaf-section 口径):")
    print("   kp_files:", {k: v for k, v in orphan["scope_kp_files"].items() if k != "per_file"})
    print("   all_26  :", orphan["scope_all_26"])
    for f, v in orphan["per_file_kp_files"].items():
        print(f"   {f}: slices={v['slices']} orphan={v['orphan_any_pct']}% char_cov={v['char_coverage_pct']}%")
    print("\nK 回滚目录事实:", json.dumps(rollback, ensure_ascii=False)[:600])
    print("\nL sidecar 字段:", json.dumps(schema_facts["sidecar_kp_fields_observed"], ensure_ascii=False))
    print("\nM 活动对象:", live_moving)
    print("\nwrote", os.path.relpath(os.path.join(OUTDIR, "q1-independent.json"), REPO))


if __name__ == "__main__":
    main()
