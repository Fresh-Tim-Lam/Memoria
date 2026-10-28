# -*- coding: utf-8 -*-
"""G4 复核：对 researcher 的 G4-path-census.json 做独立交叉核验。

独立数据源：G2-edge-inventory-raw.json（62 条边全量；已由我在
scripts-verify/G4-verify-prep.py 中用产品 collect_graph_data 复核过 62/33/21/8）。
本脚本只按该清单重算，不 import researcher 的 census 生成代码。

核验项：
  1. 2-hop / 3-hop 简单有向路径数（含节点不重复）
  2. clean 口径弱连通分量（去 8 退化边）top10 与分量数
  3. candidate_sample_2hop_authored 条目数 vs 实际 2-hop 路径数
  4. trivial_separation 数字（65 覆盖节点 / same-file / adjacent / 2-hop reachable）
  5. 我自己复算的 G4 可用"负例区分下界"（same-file 规则 balanced accuracy）

Run:
  python artifacts/agent/verify/debate/graph-utility/scripts-verify/G4-census-crosscheck.py
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)
INV = os.path.join(OUT_DIR, 'G2-edge-inventory-raw.json')
CENSUS = os.path.join(OUT_DIR, 'G4-path-census.json')
OUT = os.path.join(OUT_DIR, 'G4-census-crosscheck.json')

sys.path.insert(0, os.path.dirname(__file__))


def norm_name(s):
    import re
    s = (s or '').strip()
    s = re.sub(r'^[※\s]+', '', s)
    s = re.sub(r'^\(\d+\)\s*', '', s)
    s = re.sub(r'^\d+\.\s*', '', s)
    s = re.sub(r'[\s\$\{\}\\\_\^]', '', s)
    return s


def path_counts(edges, k):
    """返回 (路径条数, 类型序列计数, 路径列表)；简单有向路径，节点/边都不重复。"""
    adj = collections.defaultdict(list)
    for e in edges:
        adj[e['src']].append(e)
    paths = []

    def dfs(node, depth, seen, seq):
        if depth == k:
            paths.append([(x['src'], x['tgt'], x['type'], x['file']) for x in seq])
            return
        for e in adj.get(node, ()):
            if e['tgt'] in seen:
                continue
            if any(s['src'] == e['src'] and s['tgt'] == e['tgt'] for s in seq):
                continue
            seen.add(e['tgt'])
            seq.append(e)
            dfs(e['tgt'], depth + 1, seen, seq)
            seq.pop()
            seen.discard(e['tgt'])

    for s in adj:
        dfs(s, 0, {s}, [])
    types = collections.Counter('→'.join(x[2] for x in p) for p in paths)
    return len(paths), dict(types.most_common()), paths


def components(edges):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        a, b = find(e['src']), find(e['tgt'])
        if a != b:
            parent[a] = b
    groups = collections.defaultdict(set)
    for x in list(parent):
        groups[find(x)].add(x)
    return sorted((len(v) for v in groups.values()), reverse=True)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    inv = json.load(open(INV, encoding='utf-8'))
    census = json.load(open(CENSUS, encoding='utf-8'))
    edges = inv['edges']

    degen_keys = set()
    for e in edges:
        if e['type'] != 'contain':
            continue
        ns, nt = norm_name(e['src_name']), norm_name(e['tgt_name'])
        if ns == nt or ('传' + nt) == ns or ('传' + ns) == nt:
            degen_keys.add((e['src'], e['tgt']))
    clean = [e for e in edges if (e['src'], e['tgt']) not in degen_keys]

    out = {'schema': 'gue-g4-census-crosscheck/v1'}
    out['inputs'] = {'inventory': 'G2-edge-inventory-raw.json',
                     'census': 'G4-path-census.json',
                     'degenerate_edges_detected': len(degen_keys)}
    out['graph'] = {
        'edges_raw': len(edges), 'edges_clean': len(clean),
        'nodes_with_edges_raw': len({e['src'] for e in edges} | {e['tgt'] for e in edges}),
        'nodes_with_edges_clean': len({e['src'] for e in clean} | {e['tgt'] for e in clean}),
        'weak_components_raw': len(components(edges)),
        'weak_components_clean': len(components(clean)),
        'component_sizes_clean_top10': components(clean)[:10],
        'census_weak_components_clean': census['graph']['weak_components_clean'],
        'census_component_sizes_clean_top10': census['graph']['component_sizes_clean_top10'],
    }

    for k in (2, 3):
        for label, es in (('raw', edges), ('clean', clean)):
            n, types, paths = path_counts(es, k)
            out[f'paths_{label}_{k}hop'] = {
                'path_count': n, 'type_sequences': types,
                'census_path_count': (census.get(f'paths_raw_2hop') or census.get(f'paths_clean_3hop') or {}).get('path_count')
                if False else census.get(f'paths_{label}_{k}hop', {}).get('path_count'),
                'same_file_all': all(len({h[3] for h in p}) == 1 for p in paths),
                'nodes_used': len({x for p in paths for h in p for x in (h[0], h[1])}),
            }
            if k == 2 and label == 'clean':
                # candidate list 与实际路径集合是否一一对应
                cand = census.get('candidate_sample_2hop_authored') or []
                cand_seqs = [tuple(x['id'] for x in c['nodes']) for c in cand]
                real_seqs = [tuple(p[0][0:1] + tuple(h[1] for h in p)) for p in paths]
                out['candidate_sample'] = {
                    'census_listed': len(cand), 'actual_paths': n,
                    'listed_equals_actual_set': sorted(cand_seqs) == sorted(real_seqs),
                    'listed_missing_from_actual': [s for s in cand_seqs if s not in real_seqs],
                    'actual_missing_from_listed': [s for s in real_seqs if s not in cand_seqs],
                }

    # trivial separation：与 census 同口径（clean 覆盖节点）
    clean_nodes = sorted({e['src'] for e in clean} | {e['tgt'] for e in clean})
    n_clean = len(clean_nodes)
    pairs = n_clean * (n_clean - 1)
    file_of = {}
    for e in clean:
        file_of[e['src']] = e['file']
        file_of[e['tgt']] = e['file']
    same_file = sum(1 for a in clean_nodes for b in clean_nodes
                    if a != b and file_of.get(a) == file_of.get(b))
    adjacent = len(clean)
    _, _, paths2 = path_counts(clean, 2)
    two_hop = len(paths2)
    # same-file 规则当作"分类器"的 balanced accuracy（正例=2-hop 路径，负例=其余 ordered pairs）
    tp = sum(1 for p in paths2 if len({h[3] for h in p}) == 1)
    pos = two_hop
    neg = pairs - pos
    same_file_neg = same_file - sum(
        1 for p in paths2 if len({h[3] for h in p}) == 1)  # 近似：仅扣正例
    tn = neg - same_file_neg
    ba = round((tp / pos + (tn / neg)) / 2, 4) if pos and neg else None
    out['trivial_separation'] = {
        'covered_nodes_clean': n_clean,
        'ordered_pairs': pairs,
        'adjacent_ordered_pairs': adjacent,
        'p_adjacent': round(adjacent / pairs, 6),
        'same_file_ordered_pairs': same_file,
        'p_same_file': round(same_file / pairs, 6),
        'two_hop_reachable_ordered_pairs': two_hop,
        'p_two_hop_reachable': round(two_hop / pairs, 6),
        'census_trivial_separation': census.get('trivial_separation_lower_bound'),
        'same_file_rule_balanced_accuracy_upper_bound': ba,
        'note': 'BA 下界口径：正例=2-hop 路径（23），负例=其余 ordered pairs；规则=两端同文件即判正。'
                '若负例不按同文件匹配，该条平凡规则即可接近此 BA ⇒ 区分度虚高。',
    }
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print('wrote', OUT)


if __name__ == '__main__':
    main()
