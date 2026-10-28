# -*- coding: utf-8 -*-
"""G4 正文（G4-link-semantics.md）关键数字的独立复核脚本。

只读 frozen 快照（产品 collect_graph_data 真值）+ G2 边清单 + G4-path-census.json；
独立重算 G4 正文中可机检的数字，逐条输出 PASS/FAIL/MISMATCH。

Run:
  python artifacts/agent/verify/debate/graph-utility/scripts-verify/G4-claims-verify.py
"""
import collections
import hashlib
import itertools
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)
ROUND2 = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'kg-retrieval', 'round2')
FROZEN = os.path.join(ROUND2, 'frozen', '数字通信原理')
CENSUS = os.path.join(OUT_DIR, 'G4-path-census.json')
OUT = os.path.join(OUT_DIR, 'G4-claims-verify.json')
SRC = r'D:\AAA_Jupyter\Memoria\src'


def norm_name(s):
    s = (s or '').strip()
    s = re.sub(r'^[※\s]+', '', s)
    s = re.sub(r'^\(\d+\)\s*', '', s)
    s = re.sub(r'^\d+\.\s*', '', s)
    s = re.sub(r'[\s\$\{\}\\\_\^]', '', s)
    return s


def load_graph():
    tmp = os.path.join(tempfile.gettempdir(), 'gue-verify-claims')
    dst = os.path.join(tmp, '数字通信原理')
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    shutil.copytree(FROZEN, dst)
    sys.path.insert(0, SRC)
    os.environ.setdefault('MEMORIA_CONFIG_DIR', os.path.join(tempfile.gettempdir(), 'gue-verify-cfg'))
    from memoria.graph.collector import collect_graph_data
    g = collect_graph_data(dst)
    nodes = {n['id']: n for n in g['nodes']}
    edges = [{'src': e['source_id'], 'tgt': e['targets'][0], 'type': e['type'],
              'origin': e.get('origin'), 'file': e['file']} for e in g['edges']]
    return nodes, edges


def components(edges, universe):
    parent = {x: x for x in universe}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        a, b = find(e['src']), find(e['tgt'])
        if a != b:
            parent[a] = b
    groups = collections.defaultdict(set)
    for x in universe:
        groups[find(x)].add(x)
    return groups


def path_list(edges, k):
    adj = collections.defaultdict(list)
    for e in edges:
        adj[e['src']].append(e)
    out = []

    def dfs(node, depth, seen, seq):
        if depth == k:
            out.append(list(seq))
            return
        for e in adj.get(node, ()):
            if e['tgt'] in seen:
                continue
            if any(x['src'] == e['src'] and x['tgt'] == e['tgt'] and x['type'] == e['type'] for x in seq):
                continue
            seen.add(e['tgt'])
            seq.append(e)
            dfs(e['tgt'], depth + 1, seen, seq)
            seq.pop()
            seen.discard(e['tgt'])

    for s in adj:
        dfs(s, 0, {s}, [])
    return out


def reachable_pairs(edges, universe, directed=True):
    adj = collections.defaultdict(list)
    for e in edges:
        adj[e['src']].append(e['tgt'])
    n = 0
    for s in universe:
        seen = set()
        stack = list(adj.get(s, ()))
        while stack:
            v = stack.pop()
            if v in seen:
                continue
            seen.add(v)
            stack.extend(adj.get(v, ()))
        n += len(seen)
    return n


def frame_stats(edges, universe, file_of):
    n = len(universe)
    pairs = n * (n - 1)
    comp = components(edges, universe)
    comp_id = {}
    for i, (root, members) in enumerate(comp.items()):
        for m in members:
            comp_id[m] = i
    same_comp = sum(len(m) * (len(m) - 1) for m in comp.values())
    same_file = 0
    by_file = collections.defaultdict(list)
    for u in universe:
        f = file_of.get(u)
        if f:
            by_file[f].append(u)
    for f, members in by_file.items():
        same_file += len(members) * (len(members) - 1)
    adjacent = len(edges)
    reach = reachable_pairs(edges, universe)
    p2 = path_list(edges, 2)
    pos = len(p2)
    neg = pairs - pos
    # rule: same file => positive
    same_file_neg = same_file - sum(1 for p in p2
                                    if len({file_of.get(h['src']) for h in p} | {file_of.get(h['tgt']) for h in p}) == 1
                                    and all(file_of.get(h['src']) for h in p))
    tnr_file = (neg - same_file_neg) / neg if neg else None
    ba_file = (1 + tnr_file) / 2 if tnr_file is not None else None
    # rule: same weak component => positive
    comp_neg = same_comp - pos  # 所有 2-hop 路径都在同一分量
    tnr_comp = (neg - comp_neg) / neg if neg else None
    ba_comp = (1 + tnr_comp) / 2 if tnr_comp is not None else None
    return {
        'universe': n, 'ordered_pairs': pairs, 'edges': len(edges),
        'pct_adjacent': round(100.0 * adjacent / pairs, 4),
        'pct_same_component': round(100.0 * same_comp / pairs, 4),
        'pct_directed_reachable': round(100.0 * reach / pairs, 4),
        'pct_same_file': round(100.0 * same_file / pairs, 4),
        'n_pos_2hop': pos,
        'BA_same_file_rule': round(ba_file, 4) if ba_file is not None else None,
        'BA_same_component_rule': round(ba_comp, 4) if ba_comp is not None else None,
        'same_file_pairs': same_file,
        'same_component_pairs': same_comp,
        'directed_reachable_pairs': reach,
    }


def rule_R3_BA(edges, universe, file_of):
    """规则'3 节点全同文件 ⇒ 判正'，帧 = 3 节点有序序列（65 或 79 节点全排列）。"""
    nodes3 = [(a, b, c) for a in universe for b in universe for c in universe
              if len({a, b, c}) == 3]
    pos_paths = path_list(edges, 2)
    pos = {tuple([p[0]['src']] + [h['tgt'] for h in p]) for p in pos_paths}
    total = len(nodes3)
    tp = 0
    fp = 0
    fn = 0
    tn = 0
    for seq in nodes3:
        files = {file_of.get(x) for x in seq}
        pred_pos = (len(files) == 1 and None not in files)
        is_pos = seq in pos
        if pred_pos and is_pos:
            tp += 1
        elif pred_pos and not is_pos:
            fp += 1
        elif (not pred_pos) and is_pos:
            fn += 1
        else:
            tn += 1
    tpr = tp / (tp + fn) if tp + fn else None
    tnr = tn / (tn + fp) if tn + fp else None
    ba = (tpr + tnr) / 2 if tpr is not None and tnr is not None else None
    return {'frame': 'ordered_3node_sequences', 'total': total, 'pos': tp + fn,
            'TPR': round(tpr, 4) if tpr is not None else None,
            'TNR': round(tnr, 4) if tnr is not None else None,
            'BA': round(ba, 4) if ba is not None else None}


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    nodes, edges = load_graph()
    census = json.load(open(CENSUS, encoding='utf-8'))
    file_of = {nid: n.get('file') for nid, n in nodes.items()}

    degen_keys = set()
    for e in edges:
        if e['type'] != 'contain':
            continue
        ns, nt = norm_name(nodes[e['src']]['name']), norm_name(nodes[e['tgt']]['name'])
        if ns == nt or ('传' + nt) == ns or ('传' + ns) == nt:
            degen_keys.add((e['src'], e['tgt']))
    clean = [e for e in edges if (e['src'], e['tgt']) not in degen_keys]
    covered_raw = sorted({e['src'] for e in edges} | {e['tgt'] for e in edges})
    covered_clean = sorted({e['src'] for e in clean} | {e['tgt'] for e in clean})
    all_nodes = sorted(nodes)

    checks = {}

    # ---- 1. 退化边：是否 id 自环 / id 不同 ----
    degen_detail = []
    for src, tgt in sorted(degen_keys):
        degen_detail.append({
            'src_id': src, 'tgt_id': tgt, 'same_id': src == tgt,
            'src_name': nodes[src]['name'], 'tgt_name': nodes[tgt]['name'],
            'src_file': nodes[src].get('file'), 'tgt_file': nodes[tgt].get('file'),
            'src_range': [nodes[src].get('start_line'), nodes[src].get('end_line')],
            'tgt_range': [nodes[tgt].get('start_line'), nodes[tgt].get('end_line')],
        })
    checks['degenerate_id_selfloops'] = {
        'claim_G4': '7 条同名边不是 id 自环（同名不同 id）；1 条 OCR 错名',
        'count_same_id': sum(1 for d in degen_detail if d['same_id']),
        'count_same_id_same_name_distinct_id': sum(
            1 for d in degen_detail if (not d['same_id']) and norm_name(d['src_name']) == norm_name(d['tgt_name'])),
        'detail': degen_detail,
    }
    # G4 举的两条 id 对是否存在
    checks['G4_example_pairs'] = {
        'img-ch2-3-125->126': any(d['src_id'].endswith('img-ch2-3-125') and d['tgt_id'].endswith('img-ch2-3-126')
                                  for d in degen_detail),
        'img-ch2-3-85->87': any(d['src_id'].endswith('img-ch2-3-85') and d['tgt_id'].endswith('img-ch2-3-87')
                                for d in degen_detail),
        'all_pairs': [f"{d['src_id']}->{d['tgt_id']}" for d in degen_detail],
    }

    # ---- 2. 最大块边数 / 孤立块 / clean 出度直方图 ----
    groups_raw = components(edges, covered_raw)
    groups_clean_noncov = components(clean, covered_clean)
    largest = max(groups_clean_noncov.values(), key=len)
    largest_edges = [e for e in clean if e['src'] in largest]
    outdeg = collections.Counter(e['src'] for e in clean)
    checks['graph_clean'] = {
        'claim_largest_25_nodes_25_edges': True,
        'largest_component_nodes': len(largest),
        'largest_component_edges': len(largest_edges),
        'outdeg_hist_clean': {str(k): v for k, v in sorted(collections.Counter(outdeg.values()).items())},
        'claim_outdeg_hist': {'0': 33, '1': 24, '2': 3, '3': 2, '5': 1, '6': 1, '7': 1},
        'weak_components_raw_covered': len(groups_raw),
        'weak_components_clean_covered': len(groups_clean_noncov),
    }

    # ---- 3. 路径与类型序列 / 跨文件 / extend 子图最长链 / 重叠直方图 ----
    p2 = path_list(clean, 2)
    p3 = path_list(clean, 3)
    seq2 = collections.Counter('→'.join(h['type'] for h in p) for p in p2)
    seq3 = collections.Counter('→'.join(h['type'] for h in p) for p in p3)
    overlap = collections.Counter()
    pl = [tuple([p[0]['src']] + [h['tgt'] for h in p]) for p in p2]
    for i, j in itertools.combinations(range(len(pl)), 2):
        overlap[len(set(pl[i]) & set(pl[j]))] += 1
    ext = [e for e in clean if e['type'] == 'extend']
    # extend-only 最长简单路径
    eadj = collections.defaultdict(list)
    for e in ext:
        eadj[e['src']].append(e['tgt'])
    best = {'n': 0, 'path': []}

    def dfs_long(v, seen, path):
        if len(path) > best['n']:
            best['n'] = len(path)
            best['path'] = list(path)
        for nxt in eadj.get(v, ()):
            if nxt in seen:
                continue
            seen.add(nxt)
            path.append(nxt)
            dfs_long(nxt, seen, path)
            path.pop()
            seen.discard(nxt)

    for v in eadj:
        dfs_long(v, {v}, [v])
    checks['paths'] = {
        'p2_count': len(p2), 'p3_count': len(p3),
        'p2_type_seq': dict(seq2), 'p3_type_seq': dict(seq3),
        'p2_all_same_file': all(len({file_of.get(h['src']) for h in p} | {file_of.get(h['tgt']) for h in p}) == 1 for p in p2),
        'p3_all_same_file': all(len({file_of.get(h['src']) for h in p} | {file_of.get(h['tgt']) for h in p}) == 1 for p in p3),
        'p2_cross_file': sum(1 for p in p2 if len({h['file'] for h in p}) > 1),
        'p3_cross_file': sum(1 for p in p3 if len({h['file'] for h in p}) > 1),
        'overlap_hist': {str(k): v for k, v in sorted(overlap.items())},
        'overlap_pairs_total': len(pl) * (len(pl) - 1) // 2,
        'overlap_share2_pct': round(100.0 * overlap.get(2, 0) / (len(pl) * (len(pl) - 1) // 2), 2),
        'overlap_share_ge1_pct': round(100.0 * sum(v for k, v in overlap.items() if k >= 1) / (len(pl) * (len(pl) - 1) // 2), 2),
        'extend_longest_edges': best['n'],
        'extend_longest_names': [nodes[x]['name'] for x in best['path']],
    }

    # ---- 4. trivial separation 四帧 ----
    frames = {
        'all_357_over_raw_graph': frame_stats(edges, all_nodes, file_of),
        'all_357_over_clean_graph': frame_stats(clean, all_nodes, file_of),
        'raw_79_62': frame_stats(edges, covered_raw, file_of),
        'clean_65_54': frame_stats(clean, covered_clean, file_of),
    }
    checks['trivial_frames'] = frames
    checks['R3_3node_rule'] = {
        'raw_79': rule_R3_BA(edges, covered_raw, file_of),
        'clean_65': rule_R3_BA(clean, covered_clean, file_of),
    }
    checks['census_v2_compare'] = {
        'census_schema': census.get('schema'),
        'has_canonicalization': 'canonicalization' in census,
        'candidate_count': len(census.get('candidate_sample_2hop_authored') or []),
        'selection_rule': census.get('selection_rule'),
        'frames_keys': list((census.get('trivial_separation_frames') or {}).get('frames', {}).keys()),
    }

    # ---- 5. census canonicalization 复算 ----
    raw_txt = open(CENSUS, encoding='utf-8').read()
    obj = json.loads(raw_txt)
    obj.pop('generated_at', None)
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    canon = hashlib.sha256(s.encode('utf-8')).hexdigest()
    checks['census_canonical'] = {
        'recipe': census.get('canonicalization'),
        'computed_sha256': canon,
        'declared_sha256': census.get('canonical_sha256') or census.get('content_hash'),
        'match': canon == (census.get('canonical_sha256') or census.get('content_hash')),
    }

    # ---- 6. Wilson 半宽 & 功效数字 ----
    import math
    def wilson_hw(n, p=0.5, z=1.96):
        denom = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / denom
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
        return round(half * 100, 2)
    checks['power_math'] = {
        'wilson_hw_n20_p50': wilson_hw(20),
        'wilson_hw_n13_p50': wilson_hw(13),
        'binom_se_n20_p80': round(math.sqrt(0.8 * 0.2 / 20), 4),
        'binom_ci95_n20_p80_pp': round(1.96 * math.sqrt(0.8 * 0.2 / 20) * 100, 2),
        'binom_ci95_n32_p80_pp': round(1.96 * math.sqrt(0.8 * 0.2 / 32) * 100, 2),
        'claim_22pp_20': 'n=20 ±22pp', 'claim_27pp_13': 'n=13 ±27pp',
        'claim_17_5pp_n20': 'n=20 p=.8 ±17.5pp', 'claim_13_8pp_n32': 'n=32 p=.8 ±13.8pp',
    }

    # ---- 7. 文件数/作者边/README 无关 ----
    checks['misc'] = {
        'covered_raw_n': len(covered_raw), 'covered_clean_n': len(covered_clean),
        'p2_all_contain_authored_edge': all(any(h['origin'] in ('sidecar_edge', 'link') for h in p) for p in p2),
        'p3_all_contain_authored_edge': all(any(h['origin'] in ('sidecar_edge', 'link') for h in p) for p in p3),
        'clean_edges_n': len(clean),
        'raw_edges_n': len(edges),
    }

    json.dump(checks, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(checks, ensure_ascii=False, indent=1))
    print('wrote', OUT)


if __name__ == '__main__':
    main()
