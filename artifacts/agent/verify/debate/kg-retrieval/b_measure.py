# -*- coding: utf-8 -*-
"""B 方（知识组织/学习视角）Phase 1 证据测量：KP 粒度 / description / 索引体积。

只读，不修改任何知识库或仓库文件。
输出：artifacts/agent/verify/debate/kg-retrieval/b-measure.json + stdout 摘要
"""
import io
import json
import os
import re
import statistics

COURSE = r"D:\AAA_Courses\数字通信原理"
VOCAB = r"D:\AAA_Jupyter\Memoria\docs\example\AAA_Vocab"

HEAD = re.compile(r"^(#{1,6})\s+(.*)$")


def load_yaml_min(path):
    """极简 YAML：本测量只需要 knowledge_points[].id/name/description/tags/range(line_hint)。"""
    import yaml  # 仓库环境有 PyYAML（sidecar 用）

    return yaml.safe_load(io.open(path, encoding="utf-8"))


def headings(md_path):
    out = []
    for i, line in enumerate(io.open(md_path, encoding="utf-8", errors="ignore").read().splitlines(), 1):
        m = HEAD.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def analyze(label, kb_root, sc_subdir):
    md_files = []
    for dp, dns, fs in os.walk(kb_root):
        dns[:] = [d for d in dns if d != ".memoria"]
        for f in fs:
            if f.endswith(".md"):
                md_files.append(os.path.join(dp, f))
    sc_files = []
    for dp, _, fs in os.walk(os.path.join(kb_root, ".memoria", sc_subdir)):
        for f in fs:
            if f.endswith(".memoria.yaml"):
                sc_files.append(os.path.join(dp, f))

    kps = []
    per_file = []
    for sc_path in sc_files:
        try:
            doc = load_yaml_min(sc_path) or {}
        except Exception as exc:  # noqa: BLE001
            print("YAML_FAIL", sc_path, exc)
            continue
        md_rel = str(doc.get("file") or "")
        md_path = os.path.join(kb_root, md_rel)
        kp_list = [k for k in (doc.get("knowledge_points") or []) if isinstance(k, dict)]
        h = headings(md_path) if os.path.isfile(md_path) else []
        h_lines = {x[0] for x in h}
        h_titles = {x[2]: x[0] for x in h}
        spans = []
        desc_n = 0
        for kp in kp_list:
            rng = kp.get("range") or {}
            ls = int(((rng.get("start") or {}).get("line_hint") or 0))
            le = int(((rng.get("end") or {}).get("line_hint") or 0))
            desc = str(kp.get("description") or "").strip()
            if desc:
                desc_n += 1
            kp_span = max(0, le - ls + 1) if ls and le else 0
            spans.append(kp_span)
            kps.append({
                "file": md_rel, "id": str(kp.get("id") or ""), "name": str(kp.get("name") or ""),
                "line": ls, "span_lines": kp_span, "has_desc": bool(desc),
                "desc_chars": len(desc), "desc": desc,
                "tags": kp.get("tags") or [], "aliases": kp.get("aliases") or [],
        })
        per_file.append({
            "file": md_rel, "kps": len(kp_list), "desc": desc_n,
            "headings": len(h),
            "kp_starts_on_heading": sum(1 for kp in kp_list if int(((kp.get("range") or {}).get("start") or {}).get("line_hint") or 0) in h_lines),
            "md_chars": len(io.open(md_path, encoding="utf-8", errors="ignore").read()) if os.path.isfile(md_path) else 0,
            "kp_span_lines": spans,
        })

    spans_all = [k["span_lines"] for k in kps if k["span_lines"]]
    desc_lens = [k["desc_chars"] for k in kps if k["has_desc"]]
    name_lens = [len(k["name"]) for k in kps]
    total = len(kps)
    out = {
        "label": label,
        "files_with_sidecar": len(per_file),
        "kps_total": total,
        "kps_with_desc": sum(1 for k in kps if k["has_desc"]),
        "kps_with_tags": sum(1 for k in kps if k["tags"]),
        "name_chars": {"min": min(name_lens) if name_lens else 0, "p50": statistics.median(name_lens) if name_lens else 0, "max": max(name_lens) if name_lens else 0},
        "desc_chars": {"n": len(desc_lens), "min": min(desc_lens) if desc_lens else 0,
                        "p50": statistics.median(desc_lens) if desc_lens else 0,
                        "p90": sorted(desc_lens)[int(len(desc_lens) * 0.9)] if desc_lens else 0,
                        "max": max(desc_lens) if desc_lens else 0},
        "kp_span_lines": {"n": len(spans_all), "min": min(spans_all) if spans_all else 0,
                           "p50": statistics.median(spans_all) if spans_all else 0,
                           "p90": sorted(spans_all)[int(len(spans_all) * 0.9)] if spans_all else 0,
                           "max": max(spans_all) if spans_all else 0,
                           "pct_span_gt_100": round(100.0 * sum(1 for x in spans_all if x > 100) / len(spans_all), 2) if spans_all else 0},
        "per_file": [{**{k: v for k, v in p.items() if k != "kp_span_lines"},
                       "kp_span_lines_max": max(p["kp_span_lines"]) if p["kp_span_lines"] else 0} for p in per_file],
        "index_cost": {
            "name_chars_total": sum(name_lens),
            "desc_chars_total": sum(k["desc_chars"] for k in kps),
            "tag_items_total": sum(len(k["tags"]) for k in kps),
            "est_tokens_1char1tok": sum(name_lens) + sum(k["desc_chars"] for k in kps),
            "est_tokens_1_5char1tok": round((sum(name_lens) + sum(k["desc_chars"] for k in kps)) / 1.5),
        },
        "samples": kps[:6],
    }
    return out


res = []
for label, kb, sub in [("数字通信原理", COURSE, "sidecars"), ("AAA_Vocab", VOCAB, "sidecars")]:
    if os.path.isdir(kb):
        res.append(analyze(label, kb, sub))
    else:
        print("MISSING_KB", kb)

outdir = r"D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval"
os.makedirs(outdir, exist_ok=True)
with io.open(os.path.join(outdir, "b-measure.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)

for r in res:
    print("=" * 30, r["label"])
    for key in ("files_with_sidecar", "kps_total", "kps_with_desc", "kps_with_tags", "name_chars", "desc_chars", "kp_span_lines", "index_cost"):
        print(key, ":", json.dumps(r[key], ensure_ascii=False))
    for p in r["per_file"]:
        print("  ", p["file"], "| kps", p["kps"], "desc", p["desc"], "headings", p["headings"],
              "kp_on_heading", p["kp_starts_on_heading"], "md_chars", p["md_chars"], "span_max", p["kp_span_lines_max"])
    print("samples:")
    for s in r["samples"][:5]:
        print("   ", s["id"], "|", s["name"], "| span", s["span_lines"], "| desc", s["desc_chars"],
              "| tags", len(s["tags"]), "|", s["desc"][:60].replace("\n", " "))
