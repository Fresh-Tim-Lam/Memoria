# -*- coding: utf-8 -*-
"""Phase 3 候选语义边测量 v2：从 md 中「标记词所在行 + wikilink」反推候选边。"""
import io
import os
import re
from collections import Counter, defaultdict

KB = r"D:\AAA_Jupyter\Memoria\docs\example\AAA_Vocab"
SIDE = os.path.join(KB, ".memoria", "sidecars")

# file -> kp id
file_kp = {}
for dp, _, fs in os.walk(SIDE):
    for f in fs:
        if not f.endswith(".memoria.yaml"):
            continue
        p = os.path.join(dp, f)
        t = io.open(p, encoding="utf-8", errors="ignore").read()
        fm = re.search(r"^file:\s*(.+)$", t, re.M)
        km = re.search(r"^- id:\s*(\S+)", t, re.M)
        if fm and km:
            file_kp[fm.group(1).strip()] = km.group(1)

MARKERS = {
    "prerequisite": r"先学|前置|prerequisite|需要先|基础先",
    "contrast": r"对比|相比|易混|\bvs\b|混淆",
    "sequence": r"步骤|流程|首先|第一步|Step\s*\d",
    "exemplify": r"example|例句|例如|For example",
}
LINK = re.compile(r"\[\[([^\]|#\n]+)")

stats = {}
samples = defaultdict(list)
for typ, pat in MARKERS.items():
    n_links = 0
    pairs = set()
    srcs = set()
    for dp, _, fs in os.walk(KB):
        if ".memoria" in dp or ".git" in dp:
            continue
        for f in fs:
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, KB).replace("\\", "/")
            src = file_kp.get(rel)
            lines = io.open(p, encoding="utf-8", errors="ignore").read().split("\n")
            for ln in lines:
                if not re.search(pat, ln, re.I):
                    continue
                for tgt in LINK.findall(ln):
                    tgt = tgt.strip()
                    if src:
                        n_links += 1
                        srcs.add(src)
                        pairs.add((src, tgt))
                        if len(samples[typ]) < 6:
                            samples[typ].append(f"{rel}:{tgt} :: {ln.strip()[:110]}")
    stats[typ] = {"link_instances": n_links, "pairs": len(pairs), "src_kps": len(srcs)}

total_links = 429
for typ, s in stats.items():
    pct = 100.0 * s["pairs"] / total_links
    gate1 = s["pairs"] >= 10 or pct >= 5
    print(f"{typ}: pairs={s['pairs']} src_kps={s['src_kps']} inst={s['link_instances']} pct_of_429={pct:.2f}% gate1={'PASS' if gate1 else 'FAIL'}")
print("--- samples ---")
for typ, ss in samples.items():
    print("##", typ)
    for x in ss:
        print("  ", x)
