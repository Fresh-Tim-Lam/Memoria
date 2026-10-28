# -*- coding: utf-8 -*-
"""G4 复核准备探针（verifier 独立实现，不复用 G1/G2/G3 的聚合代码）。

目的：在 G4-link-semantics.md 出现之前，先独立复算 G1/G2/G3 的关键数字，
并预计算 G4 必然要用的"链路样本空间"上界（长度 2/3 的简单有向路径数），
供复核清单逐条比对。

纪律：
  - 只读 frozen 快照；复制到独立临时目录（名字带 verify，避免与 researcher 的
    gue-baseline/gue-g2/gue-g3 临时目录互相覆盖）
  - 不复用 scripts/G*.py 的统计函数；union-find / 路径枚举 / 归一化全部本文件重写
  - 输出 G4-verify-prep.json；不 touch researcher 的产物
Run:
  python artifacts/agent/verify/debate/graph-utility/scripts-verify/G4-verify-prep.py
"""
import collections
import itertools
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)                      # graph-utility/
ROUND2 = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'kg-retrieval', 'round2')
FROZEN = os.path.join(ROUND2, 'frozen', '数字通信原理')
OUT = os.path.join(OUT_DIR, 'G4-verify-prep.json')

SRC = r'D:\AAA_Jupyter\Memoria\src'


def copy_frozen(tag):
    tmp_root = os.path.join(tempfile.gettempdir(), f'gue-verify-{tag}')
    dst = os.path.join(tmp_root, '数字通信原理')
    if os.path.isdir(tmp_root):
        shutil.rmtree(tmp_root)
    os.makedirs(tmp_root, exist_ok=True)
    shutil.copytree(FROZEN, dst)
    return dst


def norm_name(s):
    """独立重写的名字归一化（含 ※/(n)/编号/空白/数学符号清除）。"""
    s = (s or '').strip()
    s = re.sub(r'^[※\s]+', '', s)
    s = re.sub(r'^\(\d+\)\s*', '', s)
    s = re.sub(r'^\d+\.\s*', '', s)
    s = re.sub(r'[\s\$\{\}\\\_\^]', '', s)
    return s


def union_find_components(ids, edges):
    parent = {i: i for i in ids}
    rank = {i: 0 for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    cyc = 0
    for e in edges:
        a, b = e['src'], e['tgt']
        ra, rb = find(a), find(b)
        if ra == rb:
            cyc += 1
        else:
            if rank[ra] < rank[rb]:
                ra, rb = rb, ra
            parent[rb] = ra
            if rank[ra] == rank[rb]:
                rank[ra] += 1
    sizes = collections.Counter(find(i) for i in ids)
    return sorted(sizes.values(), reverse=True), cyc


def count_simple_paths(adj, k, type_map=None):
    """有向简单路径（节点不重复）条数，长度 = k 条边。"""
    total = 0

    def dfs(node, depth, seen):
        nonlocal total
        if depth == k:
            total += 1
            return
        for nxt in adj.get(node, ()):
            if nxt in seen:
                continue
            seen.add(nxt)
            dfs(nxt, depth + 1, seen)
            seen.discard(nxt)

    for s in adj:
        dfs(s, 0, {s})
    return total


def path_type_composition(adj, type_map, k):
    """按经过的边类型序列统计简单路径数，返回 {(t1,...): n}。"""
    out = collections.Counter()

    def dfs(node, depth, seen, seq):
        if depth == k:
            out[tuple(seq)] += 1
            return
        for nxt, etype in adj.get(node, ()):
            if nxt in seen:
                continue
            seen.add(nxt)
            seq.append(etype)
            dfs(nxt, depth + 1, seen, seq)
            seq.pop()
            seen.discard(nxt)

    for s in adj:
        dfs(s, 0, {s}, [])
    return {('→'.join(k2)): v for k2, v in sorted(out.items(), key=lambda x: -x[1])}


def reachable_pairs(ids, adj):
    """有向可达（含 0 步自身？不含）与无向同分量 pair 计数，用于量化随机负例难度。"""
    # 有向可达：DFS 每点
    reach = 0
    for s in ids:
        seen = set()
        stack = list(adj.get(s, ()))
        while stack:
            v = stack.pop()
            if v in seen:
                continue
            seen.add(v)
            stack.extend(adj.get(v, ()))
        reach += len(seen)
    return reach


def comp_nodes(ids, edges):
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        ra, rb = find(e['src']), find(e['tgt'])
        if ra != rb:
            parent[ra] = rb
    groups = collections.defaultdict(set)
    for i in ids:
        groups[find(i)].add(i)
    return groups


def longest_simple_path_len(adj, nodes):
    best = [0]

    def dfs(node, depth, seen):
        if depth > best[0]:
            best[0] = depth
        for nxt in adj.get(node, ()):
            if nxt in seen:
                continue
            seen.add(nxt)
            dfs(nxt, depth + 1, seen)
            seen.discard(nxt)

    for s in nodes:
        dfs(s, 0, {s})
    return best[0]


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    kb = copy_frozen('prep')
    sys.path.insert(0, SRC)
    os.environ.setdefault('MEMORIA_CONFIG_DIR', os.path.join(tempfile.gettempdir(), 'gue-verify-cfg'))
    from memoria.graph.collector import collect_graph_data

    g = collect_graph_data(kb)
    nodes = g['nodes']
    edges = [{'src': e['source_id'], 'tgt': e['targets'][0], 'type': e['type'],
              'origin': e.get('origin'), 'derived': e.get('derived'),
              'relevance': e.get('relevance')} for e in g['edges']]
    names = {n['id']: n.get('name') or '' for n in nodes}
    ids = [n['id'] for n in nodes]

    # ---------- A. 图基线 ----------
    deg = collections.Counter()
    for e in edges:
        deg[e['src']] += 1
        deg[e['tgt']] += 1
    covered = set(deg)
    comps, cycles = union_find_components(ids, edges)
    edges_missing_endpoint = sum(1 for e in edges if e['src'] not in names or e['tgt'] not in names)

    baseline = {
        'nodes': len(nodes),
        'edges': len(edges),
        'edge_types': dict(collections.Counter(e['type'] for e in edges)),
        'edge_origins': dict(collections.Counter(e['origin'] for e in edges)),
        'relevance': {str(k): v for k, v in collections.Counter(str(e['relevance']) for e in edges).items()},
        'derived': {str(k): v for k, v in collections.Counter(str(e.get('derived')) for e in edges).items()},
        'covered_nodes': len(covered),
        'isolated_nodes': len(ids) - len(covered),
        'covered_pct': round(100.0 * len(covered) / len(ids), 2),
        'isolated_pct': round(100.0 * (len(ids) - len(covered)) / len(ids), 2),
        'components': len(comps),
        'largest_component': comps[0] if comps else 0,
        'component_sizes_top10': comps[:10],
        'avg_degree': round(sum(deg.values()) / len(ids), 4),
        'edge_node_ratio': round(len(edges) / len(ids), 4),
        'degree_hist': {str(k): v for k, v in sorted(collections.Counter(deg.values()).items())},
        'max_degree': max(deg.values()) if deg else 0,
        'range_ok_nodes': sum(1 for n in nodes if n.get('range_ok')),
        'range_ok_pct': round(100.0 * sum(1 for n in nodes if n.get('range_ok')) / len(ids), 2),
        'description_nonempty': sum(1 for n in nodes if (n.get('description') or '').strip()),
        'edge_field_absence': {f: sum(1 for e in g['edges'] if f in e)
                               for f in ('fact', 'valid_at', 'invalid_at', 'confidence',
                                         'provenance', 'instances')},
        'multi_target_edges': sum(1 for e in g['edges'] if len(e.get('targets') or []) != 1),
        'edges_with_missing_endpoint': edges_missing_endpoint,
        'cycles_detected_union_find': cycles,
        'node_fields': sorted(nodes[0].keys()) if nodes else [],
    }

    # ---------- B. 退化 contain（独立判定） ----------
    degen = []
    for e in edges:
        if e['type'] != 'contain':
            continue
        ns, nt = norm_name(names.get(e['src'])), norm_name(names.get(e['tgt']))
        if ns == nt:
            degen.append({**e, 'kind': 'same_name', 'src_name': names.get(e['src']), 'tgt_name': names.get(e['tgt'])})
        elif ('传' + nt) == ns or ('传' + ns) == nt:
            degen.append({**e, 'kind': 'ocr_prefix', 'src_name': names.get(e['src']), 'tgt_name': names.get(e['tgt'])})
    degenerate_info = {
        'count': len(degen),
        'same_name': sum(1 for d in degen if d['kind'] == 'same_name'),
        'ocr_prefix': sum(1 for d in degen if d['kind'] == 'ocr_prefix'),
        'items': [{k: d[k] for k in ('kind', 'type', 'origin', 'src_name', 'tgt_name')} for d in degen],
    }

    # ---------- C. inbound 多重性 ----------
    def inbound(edges_sub):
        indeg = collections.Counter()
        srcs = collections.defaultdict(set)
        for e in edges_sub:
            indeg[e['tgt']] += 1
            srcs[e['tgt']].add(e['src'])
        return {
            'edges': len(edges_sub),
            'targets_covered': len(indeg),
            'indeg_hist': {str(k): v for k, v in sorted(collections.Counter(indeg.values()).items())},
            'indeg_ge2': sum(1 for v in indeg.values() if v >= 2),
            'indeg_ge2_nodes': sorted(n for n, v in indeg.items() if v >= 2),
            'distinct_source_ge2': sum(1 for v in srcs.values() if len(v) >= 2),
        }

    degen_keys = {(d['src'], d['tgt']) for d in degen}
    inbound_info = {
        'all_62': inbound(edges),
        'exclude_degenerate': inbound([e for e in edges if (e['src'], e['tgt']) not in degen_keys]),
        'authored_only': inbound([e for e in edges if e['origin'] in ('sidecar_edge', 'link')]),
        'extend_only': inbound([e for e in edges if e['type'] == 'extend']),
        'contain_only': inbound([e for e in edges if e['type'] == 'contain']),
        'reference_only': inbound([e for e in edges if e['type'] == 'reference']),
    }

    # ---------- D. 派生相似度（若物化） ----------
    def derived(edges_sub):
        st = collections.defaultdict(set)   # source -> targets
        ts = collections.defaultdict(set)   # target -> sources
        for e in edges_sub:
            st[e['src']].add(e['tgt'])
            ts[e['tgt']].add(e['src'])

        def pairs(groups):
            n = 0
            detail = []
            for v, members in groups.items():
                m = sorted(members)
                if len(m) >= 2:
                    n += len(m) * (len(m) - 1) // 2
                    detail.append((v, len(m)))
            return n, sorted(detail, key=lambda x: -x[1])[:5]

        cc, ccd = pairs(st)
        bc, bcd = pairs(ts)
        return {'co_citation_pairs': cc, 'co_citation_top': ccd,
                'bibliographic_coupling_pairs': bc, 'bib_coupling_top': bcd}

    derived_info = {
        'all_62': derived(edges),
        'exclude_degenerate': derived([e for e in edges if (e['src'], e['tgt']) not in degen_keys]),
        'authored_only': derived([e for e in edges if e['origin'] in ('sidecar_edge', 'link')]),
    }

    # ---------- E. 链路样本空间（长度 2/3 的简单有向路径） ----------
    adj = collections.defaultdict(list)
    typed_adj = collections.defaultdict(list)
    for e in edges:
        adj[e['src']].append(e['tgt'])
        typed_adj[e['src']].append((e['tgt'], e['type']))
    groups = comp_nodes(ids, edges)
    largest = max(groups.values(), key=len)
    largest_adj = collections.defaultdict(list)
    for e in edges:
        if e['src'] in largest:
            largest_adj[e['src']].append(e['tgt'])

    # 无向同分量 pair / 有向可达 pair：量化"随机负例有多容易"
    same_comp_pairs = sum(len(s) * (len(s) - 1) for s in groups.values())
    total_ordered_pairs = len(ids) * (len(ids) - 1)
    directed_reach = reachable_pairs(ids, adj)

    path_space = {
        'note': '简单有向路径（节点不重复）；长度 k = 经过 k 条边 / k+1 个节点',
        'len2_total_graph': count_simple_paths(adj, 2),
        'len3_total_graph': count_simple_paths(adj, 3),
        'len2_largest_component': count_simple_paths(largest_adj, 2),
        'len3_largest_component': count_simple_paths(largest_adj, 3),
        'largest_component_size': len(largest),
        'longest_simple_path_edges_largest': longest_simple_path_len(largest_adj, largest),
        'len2_type_composition': path_type_composition(typed_adj, None, 2),
        'len3_type_composition': path_type_composition(typed_adj, None, 3),
        'components_ge2_nodes': sum(1 for s in groups.values() if len(s) >= 2),
        'components_ge3_nodes': sum(1 for s in groups.values() if len(s) >= 3),
        'same_component_ordered_pairs': same_comp_pairs,
        'total_ordered_pairs': total_ordered_pairs,
        'random_pair_same_component_pct': round(100.0 * same_comp_pairs / total_ordered_pairs, 3),
        'directed_reachable_ordered_pairs': directed_reach,
        'random_pair_directed_reachable_pct': round(100.0 * directed_reach / total_ordered_pairs, 3),
    }

    # extend 链是否按 start_line 单调（回答 G1 §5.3 "章节顺序"判断）
    node_line = {n['id']: (n.get('file'), n.get('start_line')) for n in nodes}
    ext_edges = [e for e in edges if e['type'] == 'extend']
    monotone = 0
    comparable = 0
    for e in ext_edges:
        fs, ls = node_line.get(e['src'], (None, None))
        ft, lt = node_line.get(e['tgt'], (None, None))
        if fs and fs == ft and ls is not None and lt is not None:
            comparable += 1
            if lt > ls:
                monotone += 1
    path_space['extend_edges'] = len(ext_edges)
    path_space['extend_same_file_pairs'] = comparable
    path_space['extend_target_after_source_in_file'] = monotone

    # ---------- F. sidecar 原文：links / edges / kps / 同名碰撞 / placement ----------
    import yaml
    base = os.path.join(FROZEN, '.memoria', 'sidecars')
    links, sidecar_edges, kps = [], [], []
    for root, _, files in os.walk(base):
        for fn in files:
            if not fn.endswith('.memoria.yaml'):
                continue
            with open(os.path.join(root, fn), encoding='utf-8') as fh:
                sc = yaml.safe_load(fh) or {}
            rel = os.path.relpath(os.path.join(root, fn), base).replace('\\', '/')
            for kp in sc.get('knowledge_points') or []:
                kps.append({'file': rel, 'id': str(kp.get('id') or ''),
                            'name': kp.get('name') or kp.get('id') or ''})
            for ln in sc.get('links') or []:
                links.append({'file': rel, 'anchor': ln.get('anchor_text') or '',
                              'targets': [str(t).strip() for t in (ln.get('targets') or []) if str(t).strip()],
                              'instances': ln.get('instances') or []})
            for ed in sc.get('edges') or []:
                if ed.get('no_build'):
                    continue
                sidecar_edges.append({'file': rel, 'type': str(ed.get('type') or ''),
                                      'source': str(ed.get('source_id') or ''),
                                      'targets': [str(t).strip() for t in (ed.get('targets') or []) if str(t).strip()]})

    link_targets = collections.Counter()
    instances = 0
    for ln in links:
        instances += len(ln['instances'])
        for t in ln['targets']:
            link_targets[t] += 1
    known_ids = {k['id'] for k in kps if k['id']} | set(ids)
    known_names = set(names.values()) | {k['name'] for k in kps}
    orphans = [t for t in link_targets if t not in known_ids and t not in known_names]
    sidecar_info = {
        'sidecar_edges_total': len(sidecar_edges),
        'sidecar_edges_by_type': dict(collections.Counter(e['type'] for e in sidecar_edges)),
        'links_entries': len(links),
        'links_instances': instances,
        'links_targets': len(link_targets),
        'links_targets_ge2': sum(1 for v in link_targets.values() if v >= 2),
        'links_orphan_targets': orphans,
        'kps_total': len(kps),
        'kps_with_id': sum(1 for k in kps if k['id']),
    }

    by_norm = collections.defaultdict(list)
    for k in kps:
        if k['id']:
            by_norm[norm_name(k['name'])].append(k['id'])
    collisions = {n: v for n, v in by_norm.items() if len(v) >= 2}
    file_of = collections.defaultdict(set)
    for k in kps:
        if k['id']:
            file_of[k['id']].add(k['file'])
    identity_info = {
        'name_collision_groups': len(collisions),
        'kps_in_collision_groups': sum(len(v) for v in collisions.values()),
        'pct_kps': round(100.0 * sum(len(v) for v in collisions.values()) / len(kps), 2) if kps else 0,
        'top_collision_groups': sorted(((n, len(v)) for n, v in collisions.items()), key=lambda x: -x[1])[:5],
        'multi_file_identities': sum(1 for v in file_of.values() if len(v) > 1),
        'distinct_kp_ids': len(file_of),
    }

    # ---------- 输出 ----------
    data = {
        'schema': 'gue-g4-verify-prep/v1',
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'measurement': {
            'corpus': '数字通信原理',
            'manifest_sha256': 'a4beaedc5f852816129ebc8399072a17b6b07e97bd22ea848246ae90a3b75466',
            'measurement_source': 'memoria.graph.collector.collect_graph_data() on independent temp copy',
            'build_state': 'no .memoria/build (pre_build)',
            'node_count_sidecar_kps': len(kps),
        },
        'baseline': baseline,
        'degenerate_contain': degenerate_info,
        'inbound': inbound_info,
        'derived_if_materialized': derived_info,
        'path_space': path_space,
        'sidecar': sidecar_info,
        'identity': identity_info,
    }
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(data, ensure_ascii=False, indent=1))
    print('\nwrote', OUT)


if __name__ == '__main__':
    main()
