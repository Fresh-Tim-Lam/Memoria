#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""E1 B-source probe (repo code, read-only).

Reproduces the numbers quoted in E1-repo.md against the frozen debate corpus:

  1. Frozen corpus == data/corpus-snapshot.json (2026-10-27 14:09:46) sidecar sha256
  2. KP health through Memoria's own resolver (range_ok / error / span=0)
  3. Sidecar validator view (error vs warning counts)
  4. A1 counterfactual: change only range.*.line_hint, keep snippet -> still False?
  5. KP unit size (span lines/chars/tokens) + read-tool output sizes

Run from repo root:
  .venv/Scripts/python.exe artifacts/agent/verify/debate/kg-retrieval/evidence/E1-repo-probe.py
"""
from __future__ import annotations

import collections
import io
import json
import os
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.abspath(".")
sys.path.insert(0, os.path.join(ROOT, "src"))

import memoria.services  # noqa: F401,E402  (initialize services before sidecar_validate)
from memoria.range.locator import locate_snippet, resolve_range  # noqa: E402
from memoria.services.agent import section_index as si  # noqa: E402
from memoria.services.agent.tools import kb as K  # noqa: E402
from memoria.services.kp_resolver import resolve_knowledge_points  # noqa: E402
from memoria.storage.markdown import strip_frontmatter  # noqa: E402
from memoria.storage.sidecar import (  # noqa: E402
    collect_sidecar_md_rels,
    load_sidecar_for_md,
)
from memoria.storage.sidecar_validate import validate_sidecar  # noqa: E402

FROZEN = os.path.abspath(
    os.path.join(ROOT, "artifacts/agent/verify/debate/kg-retrieval/round2/frozen/数字通信原理")
)
SNAPSHOT = os.path.abspath(
    os.path.join(ROOT, "artifacts/agent/verify/debate/kg-retrieval/data/corpus-snapshot.json")
)
MANIFEST = os.path.abspath(
    os.path.join(ROOT, "artifacts/agent/verify/debate/kg-retrieval/round2/frozen/MANIFEST.json")
)


def snapshot_check() -> None:
    snap = json.load(open(SNAPSHOT, encoding="utf-8"))["kbs"]["数字通信原理"]
    man = json.load(open(MANIFEST, encoding="utf-8"))
    sm = {x["path"]: x["sha256"] for x in snap["sidecars"]}
    mm = {x["path"]: x["sha256"] for x in man["files"] if x["path"].endswith(".memoria.yaml")}
    print("== 1. frozen == 14:09:46 snapshot ==")
    print("sidecars:", len(mm), "| same set:", set(sm) == set(mm),
          "| all sha256 equal:", all(sm.get(k) == mm.get(k) for k in mm))


def kp_health():
    print("\n== 2. KP health via Memoria range resolver ==")
    total = ok = 0
    errs: collections.Counter = collections.Counter()
    span0, inverted = [], []
    for rel in collect_sidecar_md_rels(FROZEN):
        full = os.path.join(FROZEN, rel)
        body, _ = strip_frontmatter(open(full, encoding="utf-8").read())
        lines = body.splitlines()
        sc = load_sidecar_for_md(full, FROZEN) or {}
        for kp in resolve_knowledge_points(body, sc):
            total += 1
            rr = kp.get("range_resolved") or {}
            if not rr.get("ok"):
                errs[rr.get("error")] += 1
                continue
            ok += 1
            if rr["start_line"] == rr["end_line"]:
                span0.append(kp.get("id"))
            if rr["start_line"] > rr["end_line"]:
                inverted.append(kp.get("id"))
    print(f"total={total} range_ok={ok} bad={total - ok} fresh={100.0 * ok / total:.2f}%")
    print("errors:", dict(errs), "| span_zero:", span0, "| inverted:", inverted)
    return total, ok


def validate_view() -> None:
    print("\n== 3. validate_sidecar view on same corpus ==")
    codes: collections.Counter = collections.Counter()
    sev: collections.Counter = collections.Counter()
    affected = set()
    for rel in collect_sidecar_md_rels(FROZEN):
        full = os.path.join(FROZEN, rel)
        body, _ = strip_frontmatter(open(full, encoding="utf-8").read())
        sc = load_sidecar_for_md(full, FROZEN) or {}
        res = validate_sidecar(sc, rel.replace("\\", "/"), body.splitlines())
        for bucket, counter in (("errors", "error"), ("warnings", "warning")):
            for item in res.get(bucket) or []:
                codes[item.get("code")] += 1
                sev[counter] += 1
                if item.get("kp_id"):
                    affected.add(item["kp_id"])
    print("severity:", dict(sev), "| codes:", dict(codes), "| affected kp:", len(affected))


def a1_counterfactual() -> None:
    print("\n== 4. A1 counterfactual: only line_hint changed, snippet untouched ==")
    for rel in collect_sidecar_md_rels(FROZEN):
        full = os.path.join(FROZEN, rel)
        body, _ = strip_frontmatter(open(full, encoding="utf-8").read())
        lines = body.splitlines()
        sc = load_sidecar_for_md(full, FROZEN) or {}
        for kp in sc.get("knowledge_points") or []:
            if not isinstance(kp, dict):
                continue
            rng = kp.get("range") or {}
            st = dict(rng.get("start") or {})
            en = dict(rng.get("end") or {})
            if not st.get("snippet") or not en.get("snippet"):
                print(f"  {kp.get('id')}: missing snippet -> resolver never calls resolve_range "
                      f"=> range_ok stays False (missing_snippet)")
                continue
            rr = resolve_range(lines, st, en)
            if rr.get("ok"):
                continue
            st2, en2 = dict(st), dict(en)
            st2["line_hint"], en2["line_hint"] = 1, len(lines)
            rr2 = resolve_range(lines, st2, en2)
            idx, _ = locate_snippet(lines, en["snippet"], en.get("line_hint"))
            print(f"  {kp.get('id')}: original error={rr.get('error')} | hint-only ok={rr2.get('ok')} "
                  f"error={rr2.get('error')} | end snippet locatable={idx is not None}")


def sizes() -> None:
    print("\n== 5a. KP unit size (range_ok KPs) ==")
    spans = []
    starts_heading = 0
    for rel in collect_sidecar_md_rels(FROZEN):
        full = os.path.join(FROZEN, rel)
        body, _ = strip_frontmatter(open(full, encoding="utf-8").read())
        lines = body.splitlines()
        sc = load_sidecar_for_md(full, FROZEN) or {}
        for kp in resolve_knowledge_points(body, sc):
            rr = kp.get("range_resolved") or {}
            if not rr.get("ok"):
                continue
            seg = lines[rr["start_line"] - 1: rr["end_line"]]
            spans.append((len(seg), sum(len(x) + 1 for x in seg), si.estimate_tokens("\n".join(seg))))
            starts_heading += lines[rr["start_line"] - 1].lstrip().startswith("#")
    lines_sorted = sorted(x[0] for x in spans)
    chars_sorted = sorted(x[1] for x in spans)
    tok_sorted = sorted(x[2] for x in spans)
    p = lambda arr, q: arr[min(len(arr) - 1, int(q * len(arr)))]
    print("n:", len(spans))
    print("span_lines  p50/p90/max:", statistics.median(lines_sorted), p(lines_sorted, .9), max(lines_sorted))
    print("span_chars  p50/p90/max:", statistics.median(chars_sorted), p(chars_sorted, .9), max(chars_sorted))
    print("span_tokens p50/p90/max:", statistics.median(tok_sorted), p(tok_sorted, .9), max(tok_sorted))
    big = sum(1 for c in chars_sorted if c > 1200)
    print(f">1200 chars: {big}/{len(chars_sorted)} ({100.0 * big / len(chars_sorted):.1f}%)")
    print(f"KP start is a heading line: {starts_heading}/{len(spans)}")

    print("\n== 5b. measured tool output sizes (same corpus) ==")
    K._read_roots = lambda _kb: (FROZEN,)  # allow-root = frozen KB root
    rel = "教材/03_第3章_模拟信号的数字编码.md"
    out = K._read_document(FROZEN, rel)
    print(f"read_document default: chars={len(out.text)} est_tokens={si.estimate_tokens(out.text)} "
          f"anchors={len(out.anchors)} truncated={out.truncated} text0={out.text[:60]!r}")
    out = K._read_kp(FROZEN, "nonuniform-quantization")
    print(f"read_kp(nonuniform-quantization): chars={len(out.text)} est_tokens={si.estimate_tokens(out.text)}")
    bad = K._read_kp(FROZEN, "img-ch2-4-13-随机过程的统计值")
    print(f"read_kp(bad range): chars={len(bad.text)} header={bad.text.splitlines()[0]!r} "
          f"body_first={bad.text.splitlines()[2]!r}")
    body, _ = K._read_body_lines(FROZEN, rel)
    sec = si.get_section(body, heading="3.2.3 混叠现象与低通抽样定理")
    print(f"section(3.2.3): tokens={sec.get('tokens')} parts={sec.get('parts')} chars={len(sec.get('text') or '')}")
    sec = si.get_section(body, heading="3.3.4 非均匀量化")
    print(f"section(3.3.4): tokens={sec.get('tokens')} parts={sec.get('parts')} chars={len(sec.get('text') or '')}")
    sn = si.get_snippet(body, query="量化")
    print(f"snippet(量化): windows={len(sn.get('windows') or [])} tokens={sn.get('tokens')}")
    ol = si.build_outline(body)
    print(f"outline: headings={ol.get('count')} tokens={ol.get('tokens')}")


if __name__ == "__main__":
    snapshot_check()
    kp_health()
    validate_view()
    a1_counterfactual()
    sizes()
