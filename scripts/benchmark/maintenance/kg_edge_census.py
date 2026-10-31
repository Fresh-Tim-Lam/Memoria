#!/usr/bin/env python
"""task: KG 辩论 Phase 3 / C4 —— 数字口径冲突的度量裁决

问题：四份提案给出四个不同的图边数
  A(arch-contract): 479（引 task-86）
  B(todo-owner):    408
  C(agent-arch):    404（+links 429）
  D(metrics):       未测（本次补）

本脚本做三件事：
  1. **枚举所有可能的"边"口径**（同一份数据，不同定义 ⇒ 不同数字）
  2. 对每个口径实测，看能否复现 479 / 408 / 404
  3. 冻结语料身份（每个库所有 md + sidecar 的 sha256），让任何人可重算

口径候选（这是关键：四个数字可能只是四个口径，而不是数据漂移）：
  K1 图边 = graph_data.edges 长度                       （collect_graph_data 输出）
  K2 links 总数（sidecar links[] 条目数）
  K3 sidecar 中 edge_type/target_edges 出现次数
  K4 explicit edges[] 条目数（纯边）
  K5 含 target_edges 展开后的目标级边数
  K6 links[].instances 行级展开数（每个 instance 一条）

用法:
    python scripts/benchmark/maintenance/kg_edge_census.py [--json out.json]
                                                            [--kb DIR ...]
                                                            [--repeat 2]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

DEFAULT_KBS = [
    "docs/example/AAA_Vocab",
    "docs/example/行政法",
    "docs/example/examples",
    "docs/example/showcase",
    "docs/example/AAA_KnowledgeBase",
]


def kb_fingerprint(kb: str) -> dict:
    """冻结语料身份：所有 md + sidecar 的逐文件 sha256 + 汇总 sha256"""
    files = []
    base = os.path.join(REPO, kb)
    for dp, dn, fn in os.walk(base):
        # 跳过可再生缓存
        dn[:] = [d for d in dn if d not in ("__pycache__", "node_modules", ".git")]
        for f in sorted(fn):
            if not (f.endswith(".md") or f.endswith(".yaml") or f.endswith(".jsonl")):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, base).replace("\\", "/")
            # .memoria/build/*.json 也是可再生的，但要纳入（因为提案引用它）
            try:
                b = open(p, "rb").read()
            except Exception:
                continue
            files.append((rel, len(b), hashlib.sha256(b).hexdigest()))
    files.sort()
    agg = hashlib.sha256()
    for rel, n, sh in files:
        agg.update(f"{rel}\t{n}\t{sh}\n".encode("utf-8"))
    return {"file_count": len(files), "corpus_sha256": agg.hexdigest(),
            "files": files}


def census_kb(kb: str) -> dict:
    """对单个库做多口径 census"""
    from memoria.graph.collector import collect_graph_data
    from memoria.storage.sidecar import load_sidecar_for_md

    base = os.path.join(REPO, kb)
    out = {"kb": kb}

    # ── K1：graph_data.edges（权威图口径）──
    try:
        gd = collect_graph_data(base)
        edges = gd.get("edges", []) if isinstance(gd, dict) else []
        nodes = gd.get("nodes", []) if isinstance(gd, dict) else []
        out["K1_graph_edges"] = len(edges)
        out["K1_nodes"] = len(nodes)
        out["K1_by_type"] = dict(Counter(e.get("type") for e in edges))
        out["K1_by_origin"] = dict(Counter(e.get("origin") for e in edges))
        out["K1_by_derived"] = dict(Counter(str(e.get("derived")) for e in edges))
        # 自环/重复
        pairs = [(e.get("source_id"), tuple(sorted(e.get("targets") or []))) for e in edges]
        out["K1_self_loops"] = sum(1 for s, ts in pairs if s in ts)
    except Exception as e:
        out["K1_error"] = f"{type(e).__name__}: {e}"

    # ── sidecar 级统计（K2–K6）──
    mds = []
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d not in ("__pycache__", "node_modules", ".git")]
        for f in sorted(fn):
            if f.endswith(".md"):
                mds.append(os.path.join(dp, f))

    n_links = 0
    n_link_instances = 0
    n_explicit_edges = 0
    n_target_edges = 0
    edge_type_lines = 0
    link_type_counter = Counter()
    explicit_type_counter = Counter()
    load_err = 0

    for md in mds:
        try:
            sc = load_sidecar_for_md(md, base)
        except Exception:
            load_err += 1
            continue
        if not sc:
            continue
        links = sc.get("links") or []
        n_links += len(links)
        for l in links:
            link_type_counter[l.get("edge_type") or "(none)"] += 1
            inst = l.get("instances") or []
            n_link_instances += len(inst) if inst else 0
            te = l.get("target_edges") or {}
            n_target_edges += len(te) if isinstance(te, dict) else 0
            # 每个 link 若没有 instances，某些口径可能仍算 1 条边
            if not inst:
                n_link_instances += 0  # 记录但不加，口径另算
        for e in (sc.get("edges") or []):
            n_explicit_edges += 1
            explicit_type_counter[e.get("type") or "(none)"] += 1

    out["K2_links"] = n_links
    out["K2_link_types"] = dict(link_type_counter)
    out["K3_link_instances"] = n_link_instances
    out["K4_explicit_edges"] = n_explicit_edges
    out["K4_explicit_types"] = dict(explicit_type_counter)
    out["K5_target_edges"] = n_target_edges
    out["md_files"] = len(mds)
    out["sidecar_load_errors"] = load_err

    # ── K6：原始 yaml 文本里 "edge_type" 出现次数（C 用的口径之一：472 行）──
    txt_hits = 0
    for md in mds:
        side = md[:-3] + ".memoria.yaml"
        # 真实 sidecar 路径规则由 load_sidecar 决定，这里用近似：扫 .memoria/sidecars
    # 直接扫 sidecars 目录
    side_dir = os.path.join(base, ".memoria", "sidecars")
    if os.path.isdir(side_dir):
        for dp, dn, fn in os.walk(side_dir):
            for f in fn:
                if not f.endswith(".yaml"):
                    continue
                try:
                    t = open(os.path.join(dp, f), encoding="utf-8").read()
                except Exception:
                    continue
                txt_hits += t.count("edge_type")
    out["K6_yaml_edge_type_occurrences"] = txt_hits

    # ── 语料身份 ──
    fp = kb_fingerprint(kb)
    out["corpus_sha256"] = fp["corpus_sha256"]
    out["corpus_file_count"] = fp["file_count"]
    return out


def git_head() -> str:
    import subprocess
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "(unknown)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--kb", action="append", default=[])
    ap.add_argument("--repeat", type=int, default=2)
    args = ap.parse_args()

    kbs = args.kb or [k for k in DEFAULT_KBS if os.path.isdir(os.path.join(REPO, k))]
    if not kbs:
        print("没有可用 KB")
        return 1

    runs = []
    for _ in range(args.repeat):
        runs.append([census_kb(k) for k in kbs])

    # 稳定性：除 corpus sha 外的字段逐字节一致
    sigs = []
    for r in runs:
        sigs.append(hashlib.sha256(json.dumps(r, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
    stable = len(set(sigs)) == 1

    rows = runs[0]
    payload = {
        "schema": "kg-edge-census/v1",
        "head": git_head(),
        "measured_at": __import__("datetime").datetime.now().astimezone().isoformat(),
        "sealed": {"MEMORIA_CONFIG_DIR": True, "repeats": args.repeat, "stable": stable,
                   "sigs": sigs},
        "note": "同一份数据、六种『边』口径 ⇒ 解释 C4 的 479/408/404 分歧",
        "calibers": {
            "K1_graph_edges": "graph_data.edges 长度（collect_graph_data 权威输出）",
            "K2_links": "sidecar links[] 条目数（链接数，非边数）",
            "K3_link_instances": "links[].instances 行级展开数（每处出现一条）",
            "K4_explicit_edges": "sidecar edges[] 条目数（纯边，无 link）",
            "K5_target_edges": "links[].target_edges 目标级覆盖条目数",
            "K6_yaml_edge_type_occurrences": "sidecar yaml 文本里 edge_type 字符串出现次数",
        },
        "kbs": rows,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print(f"HEAD: {payload['head']}   重复 {args.repeat} 次一致: {stable}")
    print()
    hdr = f"{'库':<22}{'K1图边':>8}{'K2links':>9}{'K3实例':>8}{'K4纯边':>8}{'K5te':>6}{'K6txt':>7}{'节点':>6}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['kb'].split('/')[-1]:<22}"
              f"{r.get('K1_graph_edges',-1):>8}"
              f"{r.get('K2_links',-1):>9}"
              f"{r.get('K3_link_instances',-1):>8}"
              f"{r.get('K4_explicit_edges',-1):>8}"
              f"{r.get('K5_target_edges',-1):>6}"
              f"{r.get('K6_yaml_edge_type_occurrences',-1):>7}"
              f"{r.get('K1_nodes',-1):>6}")
    print()
    # 全库合计
    tot = {}
    for k in ("K1_graph_edges", "K2_links", "K3_link_instances", "K4_explicit_edges",
              "K5_target_edges", "K6_yaml_edge_type_occurrences", "K1_nodes"):
        tot[k] = sum(r.get(k, 0) for r in rows)
    print("全库合计：" + "  ".join(f"{k}={v}" for k, v in tot.items()))
    print()
    # 复现检验：哪个口径能凑出 479 / 408 / 404
    print("=== 复现检验（哪个口径能得出提案里的数字）===")
    targets = {"A 的 479": 479, "B 的 408": 408, "C 的 404": 404, "C 的 429": 429}
    for label, want in targets.items():
        hits = []
        for k, v in tot.items():
            if v == want:
                hits.append(k)
        # 也检查单库
        for r in rows:
            for k, v in r.items():
                if isinstance(v, int) and v == want and k.startswith("K"):
                    hits.append(f"{r['kb'].split('/')[-1]}.{k}")
        print(f"  {label:<12} ⇒ {' / '.join(hits) if hits else '❌ 任何口径都复现不出'}")
    print()
    print("=== 语料身份（冻结后任何人可重算）===")
    for r in rows:
        print(f"  {r['kb'].split('/')[-1]:<22} files={r['corpus_file_count']:<4} sha={r['corpus_sha256'][:16]}…")
    print()
    print(f"sha256: {payload['artifactSha256'][:16]}…")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
