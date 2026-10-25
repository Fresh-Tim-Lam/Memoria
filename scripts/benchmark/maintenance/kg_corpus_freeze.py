"""C4 语料冻结测量（Phase 3 / agent-arch）。

目的：让 479 / 408 / 404 / 429 四个数字可复核，并给出【冻结语料】与【冻结测量源】。

用法（仓库根目录）：
    python artifacts/agent/verify/debate/kg/evidence/kg_corpus_freeze.py
    python artifacts/agent/verify/debate/kg/evidence/kg_corpus_freeze.py --json out.json

冻结方案（本脚本实现）：
  A. 语料 = `git archive HEAD docs/example` 的 tar 字节 sha256（git 已提交树，确定性）；
     并在解包副本上计算【文件清单 sha256】：只纳入 *.md 与 .memoria/sidecars/**，
     排除 .memoria/agent/**（会话/备份/运行时）、.memoria/build/**（旧生成物）、
     .memoria/cache/**（可再生缓存）、__pycache__/**。
  B. 测量源 = 现场调用 `memoria.graph.collector.collect_graph_data()`（不是 .memoria/build/graph.json）。
     后者是 2026-10-23 的旧缓存（B 的 121/408 即来自它），不能当语料事实。
  C. 同时测 working tree（含用户 live 未提交改动）与旧 build 缓存，用于解释数字分歧。

只读：不写仓库（除 --json 指定路径）；解包到系统临时目录。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = _HERE
while not os.path.isdir(os.path.join(REPO, "src", "memoria")):
    parent = os.path.dirname(REPO)
    if parent == REPO:
        raise RuntimeError("cannot locate repo root from evidence script")
    REPO = parent
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from memoria.graph.collector import collect_graph_data  # noqa: E402
from memoria.storage.scanner import collect_md_files  # noqa: E402
from memoria.storage.sidecar import load_sidecar_for_md  # noqa: E402

EXCLUDE_PREFIXES = (".memoria/agent/", ".memoria/build/", ".memoria/cache/", "__pycache__/")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _manifest_sha(root: str) -> tuple[str, int]:
    rows: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir + "/"
        if any((rel_dir + d + "/").startswith(p) or rel_dir.startswith(p) for d in dirnames for p in EXCLUDE_PREFIXES):
            dirnames[:] = [d for d in dirnames if not (rel_dir + d + "/").startswith(EXCLUDE_PREFIXES)]
        for name in filenames:
            rel = (rel_dir + name).replace("\\", "/")
            if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
                continue
            if not (rel.endswith(".md") or "/.memoria/sidecars/" in "/" + rel):
                continue
            with open(os.path.join(dirpath, name), "rb") as f:
                rows.append((rel, _sha256(f.read())))
    rows.sort()
    payload = "\n".join(f"{p}\0{h}" for p, h in rows).encode("utf-8")
    return _sha256(payload), len(rows)


def _kb_stats(kb: str) -> dict:
    files = collect_md_files(kb)
    links = 0
    links_with_line = 0
    link_types: Counter = Counter()
    explicit = 0
    explicit_types: Counter = Counter()
    for rel in files:
        sc = load_sidecar_for_md(os.path.join(kb, rel), kb) or {}
        for link in sc.get("links") or []:
            if not isinstance(link, dict):
                continue
            links += 1
            link_types[str(link.get("edge_type"))] += 1
            insts = link.get("instances") or []
            if any(isinstance(i, dict) and i.get("line") is not None for i in insts):
                links_with_line += 1
        for edge in sc.get("edges") or []:
            if isinstance(edge, dict):
                explicit += 1
                explicit_types[str(edge.get("type"))] += 1
    data = collect_graph_data(kb)
    edges = data.get("edges") or []
    by_type: Counter = Counter()
    by_origin: Counter = Counter()
    indeg: Counter = Counter()
    outdeg: Counter = Counter()
    for e in edges:
        by_type[str(e.get("type"))] += 1
        by_origin[str(e.get("origin"))] += 1
        src = str(e.get("source_id") or "")
        if src:
            outdeg[src] += 1
        for t in e.get("targets") or []:
            indeg[str(t)] += 1
    nodes = data.get("nodes") or []
    n = max(1, len(nodes))
    return {
        "md_files": len(files),
        "nodes": len(nodes),
        "edges": len(edges),
        "edges_by_type": dict(sorted(by_type.items())),
        "edges_by_origin": dict(sorted(by_origin.items())),
        "links": links,
        "links_with_line_instances": links_with_line,
        "links_raw_edge_type": dict(sorted(link_types.items(), key=lambda kv: str(kv[0]))),
        "explicit_edges": explicit,
        "explicit_edge_types": dict(sorted(explicit_types.items())),
        "link_edges": int(by_origin.get("link", 0)),
        "edges_per_link": round(len(edges) / links, 3) if links else None,
        "avg_degree": round(sum(indeg.values()) + sum(outdeg.values()), 3) / n,
        "avg_in_degree": round(sum(indeg.values()) / n, 3),
        "max_in_degree": max(indeg.values()) if indeg else 0,
    }


def _measure_corpus(base: str) -> dict:
    out: dict = {}
    if not os.path.isdir(base):
        return {"error": f"missing {base}"}
    for name in sorted(os.listdir(base)):
        kb = os.path.join(base, name)
        if not os.path.isdir(os.path.join(kb, ".memoria", "sidecars")):
            continue
        try:
            out[name] = _kb_stats(kb)
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": repr(exc)}
    return out


def _git_archive_head() -> tuple[str, str]:
    """返回 (archive_sha256, tar_bytes)。"""
    proc = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "docs/example"],
        cwd=REPO,
        capture_output=True,
        check=True,
    )
    return _sha256(proc.stdout), proc.stdout


def _stale_build_snapshot() -> dict:
    p = os.path.join(REPO, "docs", "example", "AAA_Vocab", ".memoria", "build", "graph.json")
    if not os.path.isfile(p):
        return {"absent": True}
    st = os.stat(p)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    edges = data.get("edges") or []
    return {
        "path": "docs/example/AAA_Vocab/.memoria/build/graph.json",
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
        "nodes": len(data.get("nodes") or []),
        "edges": len(edges),
        "by_type": dict(Counter(str(e.get("type")) for e in edges)),
        "by_origin": dict(Counter(str(e.get("origin")) for e in edges)),
        "warning": "旧生成物 cache，不是语料事实；B 的 121/408 即来自此文件",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    started = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    archive_sha, tar_bytes = _git_archive_head()
    tmp = tempfile.mkdtemp(prefix="kg-freeze-")
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
        try:
            tf.extractall(tmp, filter="data")  # py3.12+
        except TypeError:
            tf.extractall(tmp)
    head_manifest_sha, head_manifest_files = _manifest_sha(os.path.join(tmp, "docs", "example"))
    worktree_root = os.path.join(REPO, "docs", "example")
    wt_manifest_sha, wt_manifest_files = _manifest_sha(worktree_root)

    result = {
        "measured_at": started,
        "schema": "kg-corpus-freeze/v2",
        # ── D-KG-01 强制三元组 ──────────────────────────────────────────────
        # 裁决原文（kg-ontology-v0.md §5.1）：
        #   「强制格式 (语料 sha, 测量源, 时间) 三元组 —— 缺一即 E1 无效」
        # 本块是**机检入口**：任何下游量化都必须引用这三个值，不得只写数字。
        "triplet": {
            "corpus_sha": archive_sha,
            "measurement_source": "memoria.graph.collector.collect_graph_data() 现场调用",
            "measured_at": started,
        },
        "freeze_protocol": {
            "corpus": "git archive HEAD docs/example",
            "archive_sha256": archive_sha,
            "head_manifest_sha256": head_manifest_sha,
            "head_manifest_files": head_manifest_files,
            "worktree_manifest_sha256": wt_manifest_sha,
            "worktree_manifest_files": wt_manifest_files,
            "manifest_includes": "*.md + .memoria/sidecars/**",
            "manifest_excludes": list(EXCLUDE_PREFIXES),
            "measurement_source": "memoria.graph.collector.collect_graph_data() 现场调用",
            "not_measurement_source": ".memoria/build/graph.json（旧 cache，非事实源）",
        },
        "head_corpus": _measure_corpus(os.path.join(tmp, "docs", "example")),
        "worktree_now": _measure_corpus(worktree_root),
        "stale_build_snapshot": _stale_build_snapshot(),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
