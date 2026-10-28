#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G4 · 链路（路径）候选普查 v3 —— 只读 G2 边清单 + G1 基线 + 冻结语料 sidecar，不碰产品代码/活动库。

v3（复核 FAIL-1 修正，关键）：
  · 修 same_file 分子/分母混帧 bug：357 帧的分子必须用【全部 357 个 KP】的 file 归属
    （从 frozen sidecar 读，357/357 都有非空 file，9 个文件含 KP），
    正确值：same-file 有序对 35,558 / p=27.98% / BA=0.860（raw/clean 相同）。
    v2 错误地拿边端点映射(79/65)当 357 帧分子、分母用 127,092 ⇒ 得到 1.27%/0.86% 的假值。
  · 新增 node_file_coverage + frame_scenario；3 节点同文件规则在四帧都可算。
  · 最长 extend 链改为枚举【全部】最长路径（不唯一，v2 只记一条）。

v2 相对 v1 的变更（回应复核员 gm-seminar-verifier 三条硬约束）：
  1) candidate 由"排序取前 15"改为【全量 23 条】并写死 selection_rule（非抽样、无选择偏差）
  2) trivial-separation 改为【显式帧口径】表：raw_79_62 / clean_65_54 / all_357(raw) / all_357(clean)
     + 平凡规则 BA（同文件 / 同分量），并给 recipe 说明；复核员 0.634%/0.097% 对应 raw_79_62 + 357 帧
  3) 增加 contain 参与度检查（source 入度 / target 出度；是否参与任何 ≥2 边路径）
  4) 增加 reference 跳占比、路径是否全部同块/同文件、43 条总数
  5) 增加 canonicalization recipe 字段（g4-canon-json-v1），供复核复现内容哈希

用途：给 G4 协议提供"当前图到底能枚举出多少条候选链路"的 B 源证据。
输入：G2-edge-inventory-raw.json（62 边）+ G1-baseline.json（节点总数 357）
      + frozen 语料 .memoria/sidecars/**/*.memoria.yaml（仅取 KP→file 归属；需要 PyYAML）
输出：G4-path-census.json
口径：数字通信原理 frozen（MANIFEST a4beaedc…），pre_build；
      有向简单路径（节点不重复、边不重复）；hop k∈{2,3}；退化边判定同 G2-edge-inventory.py。
运行（cwd = graph-utility 目录）：python scripts/G4-path-census.py
确定性：无随机（全量枚举 + 排序），连跑两次除 generated_at 外逐字节一致。
"""
import json
import re
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INV = ROOT / "G2-edge-inventory-raw.json"
BASE = ROOT / "G1-baseline.json"
OUT = ROOT / "G4-path-census.json"
# 冻结语料副本（只读；用于取【全部 357 个 KP】的 file 归属，修正 v2 的同文件混帧 bug）
SIDECAR_ROOT = ROOT.parent / "kg-retrieval" / "round2" / "frozen" / "数字通信原理" / ".memoria" / "sidecars"

CANON_RECIPE = (
    "g4-canon-json-v1: obj=json.load(文本); del obj['generated_at']; "
    "s=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')); "
    "sha256(s.encode('utf-8')).hexdigest()"
)


def norm_name(s):
    s = (s or "").strip()
    s = re.sub(r"^[※\s]+", "", s)
    s = re.sub(r"^\(\d+\)\s*", "", s)
    s = re.sub(r"^\d+\.\s*", "", s)
    s = re.sub(r"[\s\$\{\}\\\_\^]", "", s)
    return s


def is_degenerate(e):
    """与 G2-edge-inventory.py:71-78 同规则。"""
    if e["origin"] != "range":
        return False
    ns, nt = norm_name(e["src_name"]), norm_name(e["tgt_name"])
    return (ns == nt) or (("传" + nt) == ns) or (("传" + ns) == nt)


def build_adj(edges):
    adj = defaultdict(list)
    for i, e in enumerate(edges):
        adj[e["src"]].append((i, e["tgt"]))
    for v in adj:
        adj[v].sort()
    return adj


def weak_comps(nodes, edges):
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        ra, rb = find(e["src"]), find(e["tgt"])
        if ra != rb:
            parent[rb] = ra
    comp = defaultdict(set)
    for n in nodes:
        comp[find(n)].add(n)
    return comp


def enumerate_paths(adj, k):
    paths = []
    for v0 in sorted(adj):
        def dfs(cur, visited_nodes, visited_edges, acc_edges):
            if len(acc_edges) == k:
                paths.append((tuple(visited_nodes), tuple(acc_edges)))
                return
            for idx, nxt in adj[cur]:
                if idx in visited_edges or nxt in visited_nodes:
                    continue
                dfs(nxt, visited_nodes + [nxt], visited_edges | {idx}, acc_edges + [idx])

        dfs(v0, [v0], set(), [])
    return paths


def reachable_pairs(adj, nodes):
    """有向传递闭包，返回有序可达对数量（不含自反）。adj 元素为 (edge_idx, target)。"""
    n = 0
    for s in sorted(set(nodes) & set(adj)):
        seen, dq = set(), deque(t for _, t in adj[s])
        while dq:
            v = dq.popleft()
            if v in seen:
                continue
            seen.add(v)
            dq.extend(t for _, t in adj.get(v, []))
        seen.discard(s)
        n += len(seen)
    return n


def frame_stats(nodes, edges, universe_n):
    """一个显式帧：universe_n=分母节点数（可含不在边里的孤立点），edges 为该帧边集。"""
    adj = build_adj(edges)
    covered = set(nodes)
    comps = weak_comps(covered, edges)
    same_comp_pairs = sum(len(v) * (len(v) - 1) for v in comps.values())
    pairs = universe_n * (universe_n - 1)
    files = {}
    for e in edges:
        files.setdefault(e["src"], e["file"])
        files.setdefault(e["tgt"], e["file"])
    return {
        "universe_nodes": universe_n,
        "covered_nodes": len(covered),
        "edges": len(edges),
        "weak_components_including_isolated": len(comps) + (universe_n - len(covered)),
        "ordered_pairs": pairs,
        "adjacent_ordered_pairs": len(edges),
        "p_adjacent": round(len(edges) / pairs, 6),
        "same_component_ordered_pairs": same_comp_pairs,
        "p_same_component": round(same_comp_pairs / pairs, 6),
        "directed_reachable_ordered_pairs": reachable_pairs(adj, covered),
        "p_directed_reachable": round(reachable_pairs(adj, covered) / pairs, 6),
    }


def load_node_file_map():
    """从冻结语料的 sidecar 读取【全部 357 个 KP】的 file 归属（只读 YAML）。

    返回 (mapping, info)。缺失依赖/目录时返回 (None, info) —— same-file 帧标记 unavailable，
    **绝不**用"边端点映射当 357 帧分子"（v2 的混帧 bug，复核 FAIL-1）。
    """
    try:
        import yaml  # PyYAML 已是 G1 基线的依赖
    except ImportError:
        return None, {"available": False, "reason": "PyYAML missing"}
    if not SIDECAR_ROOT.is_dir():
        return None, {"available": False, "reason": f"sidecar root missing: {SIDECAR_ROOT}"}
    mapping, per_file, sidecars = {}, Counter(), 0
    for sp in sorted(SIDECAR_ROOT.glob("**/*.memoria.yaml")):
        rel = sp.relative_to(SIDECAR_ROOT).as_posix()
        md = rel[: -len(".memoria.yaml")] + ".md"
        d = yaml.safe_load(sp.read_text(encoding="utf-8")) or {}
        kps = d.get("knowledge_points") or []
        sidecars += 1
        for kp in kps:
            kid = kp.get("id")
            if kid:
                mapping[kid] = md
                per_file[md] += 1
    return mapping, {
        "available": True,
        "sidecars": sidecars,
        "nodes": len(mapping),
        "files_with_nodes": len(per_file),
        "per_file_counts": dict(sorted(per_file.items())),
    }


def same_file_pairs_for(nodes_subset, nmap, universe_n):
    """同文件有序对数：分子只数 nodes_subset 内、有 file 映射的节点；分母=universe_n*(universe_n-1)。"""
    by = Counter(nmap[n] for n in nodes_subset if n in nmap)
    same = sum(k * (k - 1) for k in by.values())
    total = universe_n * (universe_n - 1)
    return same, total, len(by)


def same_file_triples_for(nodes_subset, nmap, universe_n):
    by = Counter(nmap[n] for n in nodes_subset if n in nmap)
    same3 = sum(k * (k - 1) * (k - 2) for k in by.values())
    total3 = universe_n * (universe_n - 1) * (universe_n - 2)
    return same3, total3


def main():
    inv = json.loads(INV.read_text(encoding="utf-8"))
    raw = inv["edges"]
    TOTAL_NODES = json.loads(BASE.read_text(encoding="utf-8"))["counts"]["nodes"]

    for i, e in enumerate(raw):
        e["_idx"] = i
        e["_deg"] = is_degenerate(e)
    clean = [e for e in raw if not e["_deg"]]
    deg = [e for e in raw if e["_deg"]]

    nodes_raw = sorted({e["src"] for e in raw} | {e["tgt"] for e in raw})
    nodes_clean = sorted({e["src"] for e in clean} | {e["tgt"] for e in clean})

    adj_raw = build_adj(raw)
    adj_clean = build_adj(clean)
    out_deg = Counter({v: len(adj_clean.get(v, [])) for v in nodes_clean})
    in_deg = Counter()
    for e in clean:
        in_deg[e["tgt"]] += 1

    comps_raw = weak_comps(nodes_raw, raw)
    comps_clean = weak_comps(nodes_clean, clean)
    sizes_raw = sorted((len(v) for v in comps_raw.values()), reverse=True)
    sizes_clean = sorted((len(v) for v in comps_clean.values()), reverse=True)
    largest = max(comps_clean.values(), key=len)
    largest_edges = [e for e in clean if e["src"] in largest and e["tgt"] in largest]
    adj_largest = build_adj(largest_edges)

    def census(adj, edges, k):
        paths = enumerate_paths(adj, k)
        type_seqs = Counter()
        same_file = cross_file = ref_hop = authored = 0
        for ns, eidxs in paths:
            es = [edges[i] for i in eidxs]
            type_seqs[tuple(e["type"] for e in es)] += 1
            fls = {e["file"] for e in es}
            same_file += len(fls) == 1
            cross_file += len(fls) > 1
            ref_hop += any(e["type"] == "reference" for e in es)
            authored += any(not e["derived"] for e in es)
        return {
            "hops": k,
            "path_count": len(paths),
            "type_sequences": {"→".join(s): c for s, c in sorted(type_seqs.items())},
            "all_edges_same_file": same_file,
            "cross_file": cross_file,
            "with_reference_hop": ref_hop,
            "with_authored_edge": authored,
            "all_in_largest_component": len(paths) > 0 and all(
                all(n in largest for n in ns) for ns in (ns for ns, _ in paths)
            ),
        }

    c_raw_2 = census(adj_raw, raw, 2)
    c_clean_2 = census(adj_clean, clean, 2)
    c_clean_3 = census(adj_clean, clean, 3)
    c_largest_2 = census(adj_largest, largest_edges, 2)
    c_largest_3 = census(adj_largest, largest_edges, 3)

    # ---- 候选链路：全量（非抽样），按确定性顺序列出 ----
    cand = []
    for ns, eidxs in enumerate_paths(adj_clean, 2):
        es = [clean[i] for i in eidxs]
        cand.append({"nodes": list(ns), "hops": [dict(src=e["src"], tgt=e["tgt"], type=e["type"],
                                                     origin=e["origin"], file=e["file"]) for e in es]})
    cand.sort(key=lambda c: tuple(c["nodes"]))
    name_of = {}
    for e in raw:
        name_of.setdefault(e["src"], e["src_name"])
        name_of.setdefault(e["tgt"], e["tgt_name"])
    candidates = []
    for c in cand:
        candidates.append({
            "nodes": [{"id": n, "name": name_of.get(n, n)} for n in c["nodes"]],
            "hops": c["hops"],
        })

    # ---- contain 参与度（复核约束②：contain 是否参与任何 ≥2 边路径）----
    contain_raw = [e for e in raw if e["type"] == "contain"]
    contain_clean = [e for e in clean if e["type"] == "contain"]
    raw_in, raw_out = Counter(), Counter()
    for e in raw:
        raw_in[e["tgt"]] += 1
        raw_out[e["src"]] += 1
    contain_iso_raw = sum(1 for e in contain_raw if raw_in[e["src"]] == 0 and raw_out[e["tgt"]] == 0)
    paths2 = enumerate_paths(adj_clean, 2)
    paths3 = enumerate_paths(adj_clean, 3)
    contain_in_paths = 0
    for ns, eidxs in paths2:
        contain_in_paths += any(clean[i]["type"] == "contain" for i in eidxs)
    for ns, eidxs in paths3:
        contain_in_paths += any(clean[i]["type"] == "contain" for i in eidxs)
    contain_iso = sum(1 for e in contain_clean if in_deg[e["src"]] == 0 and out_deg[e["tgt"]] == 0)

    # ---- 链形状（重叠/独立性）----
    extend_edges = [e for e in clean if e["type"] == "extend"]
    adj_ext = build_adj(extend_edges)
    best = {"len_edges": 0, "paths": []}

    def walk_ext(v, visited, acc):
        if len(acc) > best["len_edges"]:
            best["len_edges"] = len(acc)
            best["paths"] = [list(visited)]
        elif len(acc) == best["len_edges"] and len(acc) > 0:
            best["paths"].append(list(visited))
        for _, nxt in adj_ext.get(v, []):
            if nxt in visited:
                continue
            visited.append(nxt)
            acc.append((v, nxt))
            walk_ext(nxt, visited, acc)
            acc.pop()
            visited.pop()

    for v in sorted(adj_ext):
        walk_ext(v, [v], [])
    # 去重（同一节点序列只留一次）并排序
    uniq = sorted({tuple(p) for p in best["paths"]})
    longest_paths = [list(p) for p in uniq]

    plist = [ns for ns, _ in paths2]
    share = Counter()
    for i in range(len(plist)):
        for j in range(i + 1, len(plist)):
            share[len(set(plist[i]) & set(plist[j]))] += 1

    # ---- trivial-separation：显式帧（帧 = universe 分母 + 边集 + 节点子集；引用必须带帧名）----
    # 复核 FAIL-1 修正：同文件分子必须用【该帧 universe 内全部节点】的 file 归属。
    # 357 帧的 universe = 全部 357 个 KP（来自 11 个 sidecar；357/357 都有非空 file），
    # 不能用"边端点映射"(79/65) 当分子 —— 那会把分子/分母混帧。
    nmap_all, file_info = load_node_file_map()
    if nmap_all is not None and len(nmap_all) != TOTAL_NODES:
        file_info["warning"] = f"node-file map size {len(nmap_all)} != G1 counts.nodes {TOTAL_NODES}"
    nodes_all = sorted(nmap_all) if nmap_all is not None else []

    frames = {
        "all_357_over_raw_graph": (frame_stats(nodes_raw, raw, TOTAL_NODES), nodes_all),
        "all_357_over_clean_graph": (frame_stats(nodes_clean, clean, TOTAL_NODES), nodes_all),
        "raw_79_62": (frame_stats(nodes_raw, raw, len(nodes_raw)), nodes_raw),
        "clean_65_54": (frame_stats(nodes_clean, clean, len(nodes_clean)), nodes_clean),
    }
    for k, (fr, subset) in frames.items():
        fr["frame_scenario"] = ("全库 357 节点随机负例" if fr["universe_nodes"] == TOTAL_NODES
                                else "仅被边覆盖节点随机负例")
        if nmap_all is None:
            fr["same_file_rule_BA_bound"] = None
            fr["same_file_note"] = "unavailable: node-file map missing"
        else:
            same, total, nfiles = same_file_pairs_for(subset, nmap_all, fr["universe_nodes"])
            fr["same_file_ordered_pairs"] = same
            fr["p_same_file"] = round(same / total, 6)
            fr["same_file_covered_nodes_in_frame"] = len(subset)
            fr["same_file_files_in_frame"] = nfiles
            # 正例 23 条候选链的节点是否全同文件（用全量映射验证，不假设）
            tpr_hits = 0
            for ns, _ in paths2:
                if len({nmap_all.get(n) for n in ns}) == 1 and None not in {nmap_all.get(n) for n in ns}:
                    tpr_hits += 1
            fr["same_file_rule_TPR_on_candidate_chains"] = round(tpr_hits / len(paths2), 6)
            fr["same_file_rule_BA_bound"] = round((1.0 + (1 - same / total)) / 2, 6)
            same3, total3 = same_file_triples_for(subset, nmap_all, fr["universe_nodes"])
            fr["same_file_rule_3node_p"] = round(same3 / total3, 6)
            fr["same_file_rule_3node_BA"] = round((1.0 + (1 - same3 / total3)) / 2, 6)
        # 同分量规则 BA 上界（正例 23 条全在最大块）
        fr["same_component_rule_BA_bound"] = round((1.0 + (1 - fr["p_same_component"])) / 2, 6)
    frames = {k: fr for k, (fr, _) in frames.items()}  # 去掉内部 subset，仅保留统计

    # ---- 负例可构造性 ----
    neg = {
        "N1_reverse_direction": len(paths2),
        "N2_neighbor_swap_feasible_paths": sum(1 for ns, _ in paths2 if len(adj_clean.get(ns[1], [])) >= 2),
        "N2_nodes_with_outdeg_ge2": sum(1 for d in out_deg.values() if d >= 2),
        "N3_composition_invalid_paths": sum(1 for ns, eidxs in paths2
                                            if "reference" in {clean[i]["type"] for i in eidxs}
                                            or len({clean[i]["type"] for i in eidxs}) > 1),
        "N5_predicate_relabel_2hop_paths": len(paths2),
        "N4_true_but_vacuous_note": "当前 k=2 无纯 contain 链（contain 不参与任何 ≥2 边路径）；D 链需 L2 判定 ⇒ 该档当前为空",
    }

    out = {
        "schema": "gue-g4-path-census/v3",
        "supersedes": "gue-g4-path-census/v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonicalization": CANON_RECIPE,
        "inputs": {
            "edge_inventory": "G2-edge-inventory-raw.json",
            "baseline": "G1-baseline.json (counts.nodes=%d)" % TOTAL_NODES,
            "corpus": "数字通信原理 frozen (MANIFEST a4beaedc…)",
            "corpus_identity_note": "引用身份 = MANIFEST 冻结快照 + taken_at；不使用实时 HEAD（已漂移）",
            "build_state": "pre_build (collect_graph_data on temp copy)",
            "hop_definition": "有向简单路径，节点不重复、边不重复",
        },
        "graph": {
            "nodes_with_edges": len(nodes_raw),
            "nodes_with_edges_clean": len(nodes_clean),
            "edges_raw": len(raw),
            "edges_clean": len(clean),
            "degenerate_edges": len(deg),
            "weak_components_raw": len(comps_raw),
            "weak_components_clean": len(comps_clean),
            "component_sizes_raw_top10": sizes_raw[:10],
            "component_sizes_clean_top10": sizes_clean[:10],
            "largest_component_nodes": len(largest),
            "largest_component_edges": len(largest_edges),
            "outdeg_hist_clean": {str(k): v for k, v in sorted(Counter(out_deg.values()).items())},
            "indeg_zero_nodes_clean": sum(1 for v in nodes_clean if in_deg[v] == 0),
        },
        "node_file_coverage": {
            "note": "357 帧同文件规则的分母必须配【全部 357 个 KP 的 file 归属】；复核曾指出 v2 用边端点映射当 357 帧分子=混帧错误。",
            "source": ".memoria/sidecars/**/*.memoria.yaml（只读）",
            **file_info,
            "all_nodes_have_file": (nmap_all is not None and all(
                nmap_all.get(n) for n in nodes_all)) if nmap_all is not None else None,
        },
        "paths_raw_2hop": c_raw_2,
        "paths_clean_2hop": c_clean_2,
        "paths_clean_3hop": c_clean_3,
        "paths_largest_component_2hop": c_largest_2,
        "paths_largest_component_3hop": c_largest_3,
        "paths_total_clean": {"k2": c_clean_2["path_count"], "k3": c_clean_3["path_count"],
                              "total": c_clean_2["path_count"] + c_clean_3["path_count"],
                              "with_reference_hop": c_clean_2["with_reference_hop"] + c_clean_3["with_reference_hop"]},
        "contain_participation": {
            "contain_edges_raw": len(contain_raw),
            "contain_edges_clean": len(contain_clean),
            "contain_edges_in_any_2or3hop_path": contain_in_paths,
            "contain_edges_isolated_in_clean_graph": contain_iso,
            "contain_edges_isolated_in_raw_graph": contain_iso_raw,
            "definition": "isolated = 该边 source 的入度为 0 且 target 的出度为 0（该帧图内）",
            "note": "contain 边不参与任何 ≥2 边路径 ⇒ '祖先链冗余'这一失效模式在当前 k≥2 池中不可出现（不是不存在，是没有材料）",
        },
        "candidate_sample_2hop_authored": {
            "selection_rule": "全量枚举（非抽样、非随机）：clean 图全部 23 条 2 跳简单路径；按节点序列字典序排列",
            "selection_bias": "无抽样偏差；但这 23 条本身是当前图的全部材料（同文件/同类型族），不代表任何总体",
            "count": len(candidates),
            "items": candidates,
        },
        "chain_shape": {
            "extend_subgraph_edges": len(extend_edges),
            "extend_longest_path_edges": best["len_edges"],
            "extend_longest_path_len_nodes": best["len_edges"] + 1,
            "extend_longest_paths_count": len(longest_paths),
            "extend_longest_paths": longest_paths,
            "extend_longest_path_note": "最长 extend 链不唯一（复核员另找到同长路径）；引用时须说明'其中一条'",
            "distinct_2hop_node_sequences": len(set(plist)),
            "nodes_used_by_2hop_paths": len({n for ns in plist for n in ns}),
            "pairwise_2hop_shared_node_hist": {str(k): v for k, v in sorted(share.items())},
            "note": "若 pairwise 共享 ≥2 节点的比例高 ⇒ 候选链路高度重叠（同一条长链的滑窗），等价独立样本量远小于条目数。",
        },
        "trivial_separation_frames": {
            "note": "帧 = universe 分母 + 边集 + 节点子集。357 帧分母=全部 357 KP（357/357 有 file，来自 11 sidecar）；"
                    "79/65 帧分母=被边覆盖节点。复核员报的 0.634% / 0.097% = all_357_over_raw_graph 帧；"
                    "clean 帧为 0.618% / 0.0905%。引用必须带帧名。",
            "frames": frames,
            "same_file_rule": {
                "definition": "item 的（前）两个节点同文件 ⇒ 判正；否则判负。正例 = 23 条 2 跳链（全部同文件）",
                "BA_by_frame": {k: v["same_file_rule_BA_bound"] for k, v in frames.items()},
                "verifier_reported_pair_level": 0.8706,
                "our_raw_frame": frames["raw_79_62"]["same_file_rule_BA_bound"],
                "our_clean_frame": frames["clean_65_54"]["same_file_rule_BA_bound"],
                "our_357_frames": {"raw": frames["all_357_over_raw_graph"]["same_file_rule_BA_bound"],
                                   "clean": frames["all_357_over_clean_graph"]["same_file_rule_BA_bound"]},
                "verifier_corrected_357_value": {"same_file_ordered_pairs": 35558, "p": 0.279782, "BA": 0.860109},
                "conclusion": "四帧 BA 均 ≥ 0.860 > G1 的 0.80 合格线 ⇒ 随机负例不可用；matched 设计必需",
            },
            "same_component_rule": {
                "definition": "item 的节点同弱连通分量 ⇒ 判正。正例 23 条全在最大块",
                "BA_by_frame": {k: v["same_component_rule_BA_bound"] for k, v in frames.items()},
            },
            "three_node_rule": {
                "definition": "item 的全部 3 个节点同文件 ⇒ 判正（2 跳链的完整形态）",
                "BA_by_frame": {k: v.get("same_file_rule_3node_BA") for k, v in frames.items()},
                "note": "按链的完整节点数判规则更强（BA 更高）⇒ 负例必须 matched 到同章，且呈现不得给文件标签",
            },
        },
        "negative_feasibility": neg,
        "honesty": [
            "本普查只数『结构上可枚举的路径』，不判断路径语义（那是 G4 人判协议的事）。",
            "类型序列用原始枚举 contain/extend/reference；G2 的 P1–P5/D 谓词尚未人判 ⇒ 组合表只能给候选，不能当结论。",
            "43 条路径全部在同一个 25 节点块、同一文件；距『代表性样本』差得远，只能 pilot。",
            "正则化（去 generated_at）哈希 recipe 见 canonicalization 字段；v1 未记录 recipe。",
        ],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ["graph", "paths_total_clean", "contain_participation",
                                          "chain_shape", "negative_feasibility"]},
                     ensure_ascii=False, indent=1))
    print(json.dumps(out["trivial_separation_frames"]["frames"], ensure_ascii=False, indent=1))
    print(f"\nwrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
