# -*- coding: utf-8 -*-
"""Phase 3 C4 冻结语料 + D 三闸自检测量（AAA_Vocab，工作区 live）。"""
import hashlib
import io
import json
import os
import re
import subprocess

KB = r"D:\AAA_Jupyter\Memoria\docs\example\AAA_Vocab"
ROOT = r"D:\AAA_Jupyter\Memoria"

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def sh(args):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip()

print("HEAD:", sh(["git", "rev-parse", "HEAD"]))
dirty = sh(["git", "status", "--porcelain", "--", "docs/example/AAA_Vocab"])
print("dirty files (docs/example/AAA_Vocab):", len(dirty.splitlines()))

# sidecar scan
sidecars = []
for dp, _, fs in os.walk(os.path.join(KB, ".memoria", "sidecars")):
    for f in fs:
        if f.endswith(".memoria.yaml"):
            sidecars.append(os.path.join(dp, f))
print("sidecar files:", len(sidecars))

kp_count = 0
link_count = 0
link_types = {}
edge_decl = 0
edge_types = {}
tag_counter = {}
for p in sidecars:
    text = io.open(p, encoding="utf-8", errors="ignore").read()
    lines = text.split("\n")
    kp_count += len(re.findall(r"^- id:", text, re.M))
    # links: count '- anchor_text:' blocks
    link_count += len(re.findall(r"^- anchor_text:", text, re.M))
    for m in re.finditer(r"^\s+edge_type:\s*(\S+)", text, re.M):
        link_types[m.group(1)] = link_types.get(m.group(1), 0) + 1
    # top-level edges: section
    m = re.search(r"^edges:\s*$", text, re.M)
    if m:
        tail = text[m.end():]
        # until next top-level key (non-indented line)
        seg = re.split(r"^(?=\S)", tail, flags=re.M)[0]
        edge_decl += len(re.findall(r"^- ", seg, re.M))
        for t in re.findall(r"^\s+type:\s*(\S+)", seg, re.M):
            edge_types[t] = edge_types.get(t, 0) + 1
    for t in re.findall(r"^\s+-\s*([^\s#][^\n]*)$", text, re.M):
        pass
    # tags: lines under 'tags:' until next non-indented/'-' key
    tm = re.search(r"^  tags:\n((?:  - [^\n]*\n)+)", text, re.M)
    if tm:
        for tag in re.findall(r"^  - (.+)$", tm.group(1), re.M):
            tag = tag.strip()
            tag_counter[tag] = tag_counter.get(tag, 0) + 1

print("KPs:", kp_count, "links:", link_count)
print("link edge_type dist:", link_types)
print("explicit edges[]:", edge_decl, "types:", edge_types)
for k in ("对比", "转折", "写作", "口语", "步骤", "流程", "因果", "例证"):
    print(f"tag {k}:", tag_counter.get(k, 0))

# 语义候选（跨文档 md 文本标记，仅作代理，不是结构化关系）
md_files = []
for dp, _, fs in os.walk(KB):
    if ".memoria" in dp or ".git" in dp:
        continue
    for f in fs:
        if f.endswith(".md"):
            md_files.append(os.path.join(dp, f))
print("md files:", len(md_files))

def count_markers(pattern):
    n = 0
    files = 0
    for p in md_files:
        t = io.open(p, encoding="utf-8", errors="ignore").read()
        c = len(re.findall(pattern, t, re.M | re.I))
        if c:
            files += 1
            n += c
    return n, files

for label, pat in [
    ("prerequisite 显式词(先学/前置/prerequisite/基础先/需要先)", r"先学|前置|prerequisite|需要先|基础先"),
    ("contrast 显式词(对比/相比/易混/vs)", r"对比|相比|易混|\bvs\b|混淆"),
    ("sequence 显式词(步骤/流程/首先/其次/最后)", r"步骤|流程|首先|第一步|Step\s*\d"),
    ("example 显式词(example/例句/例如/For example)", r"example|例句|例如|For example"),
]:
    n, files = count_markers(pat)
    print(label, "=> occurrences", n, "files", files)

# graph.json 缓存身份
gp = os.path.join(KB, ".memoria", "build", "graph.json")
st = os.stat(gp)
print("graph.json mtime:", st.st_mtime, "sha256:", sha(gp))
g = json.load(io.open(gp, encoding="utf-8"))
print("cached graph nodes/edges:", len(g.get("nodes", [])), len(g.get("edges", [])))
print("cached edge types:", {})
from collections import Counter
print("cached edge types:", Counter(e.get("type") for e in g.get("edges", [])))
print("cached node tags sample:", [n.get("tags") for n in g.get("nodes", [])[:3]])
