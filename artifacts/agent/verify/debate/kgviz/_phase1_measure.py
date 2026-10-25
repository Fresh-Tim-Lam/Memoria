# -*- coding: utf-8 -*-
"""kgviz Phase1 B 端测量：节点大小候选驱动的数据分布（AAA_Vocab live）。"""
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = r"D:\AAA_Jupyter\Memoria"
KB = os.path.join(ROOT, "docs", "example", "AAA_Vocab")
sys.path.insert(0, os.path.join(ROOT, "src"))
from memoria.graph.collector import collect_graph_data  # noqa: E402

g = collect_graph_data(KB)
nodes, edges = g["nodes"], g["edges"]
print("nodes", len(nodes), "edges", len(edges))

deg = Counter()
adj = defaultdict(set)
for e in edges:
    s = e.get("source_id") or e.get("source")
    for t in e.get("targets") or ([e.get("target")] if e.get("target") else []):
        if s and t:
            deg[s] += 1
            deg[t] += 1
            adj[s].add(t)
            adj[t].add(s)

def stats(name, vals):
    vals = sorted(vals)
    n = len(vals)
    if not n:
        print(name, "EMPTY")
        return
    def pct(p):
        return vals[min(n - 1, int(p * n))]
    print(f"{name}: n={n} min={vals[0]} p25={pct(.25)} median={pct(.5)} p75={pct(.75)} p90={pct(.9)} max={vals[-1]} distinct={len(set(vals))}")

stats("degree(all nodes, 0 for isolated)", [deg.get(n["id"], 0) for n in nodes])
dvals = [deg.get(n["id"], 0) for n in nodes]
print("degree>=1 nodes:", sum(1 for d in dvals if d >= 1), " degree>=5:", sum(1 for d in dvals if d >= 5), " degree>=10:", sum(1 for d in dvals if d >= 10))

# ---- content length per KP（sidecar range line_hint → md 切片）----
SIDE = os.path.join(KB, ".memoria", "sidecars")
kp_range = {}
for dp, _, fs in os.walk(SIDE):
    for f in fs:
        if not f.endswith(".memoria.yaml"):
            continue
        t = io.open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read()
        fm = re.search(r"^file:\s*(.+)$", t, re.M)
        km = re.search(r"^- id:\s*(\S+)", t, re.M)
        if not (fm and km):
            continue
        start = re.search(r"range:.*?\n\s*start:.*?\n(?:.*?\n)*?\s*line_hint:\s*(\d+)", t)
        end = re.search(r"range:.*?\n\s*start:.*?\n(?:.*?\n)*?\s*end:.*?\n(?:.*?\n)*?\s*line_hint:\s*(\d+)", t, re.S)
        # fallback: 两个 line_hint 中第二个为 end
        hints = [int(x) for x in re.findall(r"line_hint:\s*(\d+)", t)[:2]]
        s0 = int(start.group(1)) if start else (hints[0] if hints else 1)
        e0 = int(end.group(1)) if end else (hints[1] if len(hints) > 1 else s0)
        kp_range[km.group(1)] = (fm.group(1).strip(), s0, e0)

lengths = {}
file_bodies = {}
for kid, (rel, s0, e0) in kp_range.items():
    p = os.path.join(KB, rel)
    if p not in file_bodies:
        try:
            body = io.open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            body = ""
        file_bodies[p] = body.split("\n")
    lines = file_bodies[p]
    seg = "\n".join(lines[max(0, s0 - 1):max(s0, e0)])
    lengths[kid] = len(seg)
stats("content_chars(KP range)", [lengths.get(n["id"], 0) for n in nodes])

# ---- cards / FSRS ----
review = os.path.join(KB, ".memoria", "agent", "review")
cards = json.load(io.open(os.path.join(review, "cards.json"), encoding="utf-8"))["cards"]
card_kp = {}
for c in cards:
    card_kp[c.get("card_id")] = c.get("kp_id") or ""
card_count = Counter()
for c in cards:
    card_count[c.get("kp_id")] += 1
stats("cards_per_kp(only >0)", [v for v in card_count.values()])
print("KPs with cards:", len(card_count), "/", len(nodes))

progress = json.load(io.open(os.path.join(review, "progress.json"), encoding="utf-8"))
card_state = progress.get("cards") or progress.get("progress") or {}
diff, reps, stab = [], [], []
kp_diff = defaultdict(list)
for cid, st in card_state.items():
    kp = card_kp.get(cid, "")
    if not isinstance(st, dict):
        continue
    if isinstance(st.get("difficulty"), (int, float)):
        diff.append(st["difficulty"]); kp_diff[kp].append(st["difficulty"])
    if isinstance(st.get("reps"), (int, float)):
        reps.append(st["reps"])
    if isinstance(st.get("stability"), (int, float)):
        stab.append(st["stability"])
stats("FSRS difficulty", diff)
stats("FSRS reps", reps)
stats("FSRS stability", stab)
print("KPs with FSRS state:", len([k for k, v in kp_diff.items() if v]), "/", len(nodes))

# ---- union-find groups ----
parent = {n["id"]: n["id"] for n in nodes}
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb
for e in edges:
    s = e.get("source_id") or e.get("source")
    for t in e.get("targets") or []:
        if s in parent and t in parent:
            union(s, t)
gs = Counter(find(x) for x in parent)
sizes = sorted(gs.values(), reverse=True)
print("groups:", len(sizes), "top sizes:", sizes[:5], "largest fraction:", round(sizes[0] / len(nodes), 3))

# ---- 视觉可辨：半径映射示例 r=5..18，sqrt 比例 ----
def radii(vals, rmin=5, rmax=18):
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    out = [rmin + (rmax - rmin) * ((v - lo) / span) ** 0.5 for v in vals]
    return out

for name, vals in [
    ("degree", [deg.get(n["id"], 0) for n in nodes]),
    ("content", [lengths.get(n["id"], 0) for n in nodes]),
    ("cards", [card_count.get(n["id"], 0) for n in nodes]),
]:
    rr = radii(vals)
    buckets = Counter(round(r) for r in rr)
    print(name, "radius buckets(px):", dict(sorted(buckets.items())), "distinct:", len(buckets))
