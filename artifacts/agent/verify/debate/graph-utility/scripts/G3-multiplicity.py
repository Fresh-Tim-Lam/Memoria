# -*- coding: utf-8 -*-
"""G3 引用多重性（inbound multiplicity）基线探针 —— 只读 frozen 快照。

回答人 2026-10-27 追加口径：
  A 出现/嵌入（placement）：同一内容被物理放进多个视图/层级
  B 被引用（inbound）：多个地方用【任意类型】链接指向它

测量：
  · 62 条 graph edges 的入边分布（多少节点被 ≥2 处指向）——用产品 collect_graph_data 真值
  · 清洗口径对比：全量 / 去退化 contain / 只 extend / 去 reference
  · links[]（正文锚点）的入链、instances、孤立目标
  · co-citation / bibliographic coupling 若物化会产生多少伪边
  · 同名 identity 碰撞（同名 ≠ 多重出现，是身份歧义）
  · placement 现状（当前模型是否支持跨视图多重归属）

Run:  python scripts/G3-multiplicity.py
"""
import collections
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
OUT = os.path.join(OUT_DIR, 'G3-inbound-baseline.json')

sys.path.insert(0, r'D:\AAA_Jupyter\Memoria\src')


def norm_name(s):
    s = (s or '').strip()
    s = re.sub(r'^[※\s]+', '', s)
    s = re.sub(r'^\(\d+\)\s*', '', s)
    s = re.sub(r'^\d+\.\s*', '', s)
    s = re.sub(r'[\s\$\{\}\\\_\^]', '', s)
    return s


def load_sidecars():
    import yaml
    links, edges, kps = [], [], []
    base = os.path.join(FROZEN, '.memoria', 'sidecars')
    for root, _, files in os.walk(base):
        for fn in files:
            if not fn.endswith('.memoria.yaml'):
                continue
            with open(os.path.join(root, fn), encoding='utf-8') as fh:
                sc = yaml.safe_load(fh) or {}
            f = sc.get('file') or os.path.relpath(os.path.join(root, fn), base).replace('\\', '/')
            for kp in sc.get('knowledge_points') or []:
                kps.append({'file': f, 'id': str(kp.get('id') or ''), 'name': kp.get('name') or kp.get('id') or ''})
            for ln in sc.get('links') or []:
                links.append({
                    'file': f,
                    'anchor': ln.get('anchor_text') or '',
                    'targets': [str(t).strip() for t in (ln.get('targets') or []) if str(t).strip()],
                    'edge_type': ln.get('edge_type'),
                    'instances': ln.get('instances') or [],
                })
            for ed in sc.get('edges') or []:
                if ed.get('no_build'):
                    continue
                edges.append({'file': f, 'type': str(ed.get('type') or ''),
                              'source': str(ed.get('source_id') or ''),
                              'targets': [str(t).strip() for t in (ed.get('targets') or []) if str(t).strip()]})
    return kps, links, edges


def copy_and_collect():
    tmp_root = os.path.join(tempfile.gettempdir(), 'gue-g3')
    dst = os.path.join(tmp_root, '数字通信原理')
    if os.path.isdir(tmp_root):
        shutil.rmtree(tmp_root)
    os.makedirs(tmp_root, exist_ok=True)
    shutil.copytree(FROZEN, dst)
    os.environ.setdefault('MEMORIA_CONFIG_DIR', os.path.join(tempfile.gettempdir(), 'gue-cfg'))
    from memoria.graph.collector import collect_graph_data
    return collect_graph_data(dst)


def inbound_stats(edges, label):
    indeg = collections.Counter()
    for e in edges:
        for t in e['targets']:
            indeg[t] += 1
    hist = collections.Counter(indeg.values())
    return {
        'label': label, 'edges': len(edges),
        'targets_covered': len(indeg),
        'targets_indeg_ge2': sum(1 for n in indeg.values() if n >= 2),
        'indeg_hist': {str(k): v for k, v in sorted(hist.items())},
        'top_indeg': sorted(indeg.items(), key=lambda x: -x[1])[:8],
    }


def main():
    kps, links, sidecar_edges = load_sidecars()

    # ---- 62 条 graph edges（产品真值）----
    g = copy_and_collect()
    g_edges = [{'type': e['type'], 'source': e['source_id'],
                'targets': e['targets'], 'origin': e.get('origin')} for e in g['edges']]
    names = {n['id']: n['name'] for n in g['nodes']}
    degenerate = []
    for e in g_edges:
        if e['type'] != 'contain':
            continue
        ns = norm_name(names.get(e['source'], e['source']))
        nt = norm_name(names.get(e['targets'][0], e['targets'][0]))
        if ns == nt or ('传' + nt) == ns or ('传' + ns) == nt:
            degenerate.append(e)

    all_nodes = [n['id'] for n in g['nodes']]
    def stats_with_nodes(edges, label):
        s = inbound_stats(edges, label)
        s['pct_of_all_nodes_ge2'] = round(100.0 * s['targets_indeg_ge2'] / len(all_nodes), 2)
        s['pct_of_covered_nodes_ge2'] = round(
            100.0 * s['targets_indeg_ge2'] / s['targets_covered'], 1) if s['targets_covered'] else 0.0
        return s

    edge_stats = {
        'all_62': stats_with_nodes(g_edges, 'all_62'),
        'exclude_degenerate_contain': stats_with_nodes(
            [e for e in g_edges if e not in degenerate], 'exclude_degenerate_contain'),
        'only_authored_extend_reference': stats_with_nodes(
            [e for e in g_edges if e['origin'] in ('sidecar_edge', 'link')], 'authored_edges(26)'),
        'only_extend': stats_with_nodes([e for e in g_edges if e['type'] == 'extend'], 'only_extend'),
        'only_contain': stats_with_nodes([e for e in g_edges if e['type'] == 'contain'], 'only_contain'),
        'degenerate_count': len(degenerate),
    }

    # ---- links[]（正文锚点；含 instances）----
    link_targets = collections.Counter()
    link_instances = 0
    link_entries = 0
    for ln in links:
        link_entries += 1
        link_instances += len(ln['instances'])
        for t in ln['targets']:
            link_targets[t] += 1
    link_multi = {t: n for t, n in link_targets.items() if n >= 2}
    known = {k['id'] for k in kps} | set(names)
    link_orphan = [t for t in link_targets if t not in known and t not in names.values()]

    # ---- 派生相似度 ----
    src_targets = collections.defaultdict(set)
    tgt_sources = collections.defaultdict(set)
    for e in g_edges:
        for t in e['targets']:
            src_targets[e['source']].add(t)
            tgt_sources[t].add(e['source'])

    def shared_pairs(groups, label):
        pairs = set()
        for members in groups.values():
            for a, b in itertools.combinations(sorted(members), 2):
                pairs.add((a, b))
        return {'label': label, 'pairs': len(pairs),
                'potential_pairs': sum(len(m) * (len(m) - 1) // 2 for m in groups.values()),
                'groups_with_ge2': sum(1 for m in groups.values() if len(m) >= 2)}

    def derived_for(edges_sub, label):
        st = collections.defaultdict(set)
        ts = collections.defaultdict(set)
        for e in edges_sub:
            for t in e['targets']:
                st[e['source']].add(t)
                ts[t].add(e['source'])
        return {
            'label': label,
            'bibliographic_coupling_by_target': shared_pairs(ts, 'sources sharing a target'),
            'co_citation_by_source': shared_pairs(st, 'targets sharing a source'),
        }

    derived = {
        'all_62': derived_for(g_edges, 'all_62'),
        'exclude_degenerate_contain': derived_for(
            [e for e in g_edges if e not in degenerate], 'exclude_degenerate_contain'),
        'authored_only': derived_for(
            [e for e in g_edges if e['origin'] in ('sidecar_edge', 'link')], 'authored_only(26+3)'),
    }

    # ---- identity 同名碰撞 ----
    by_norm = collections.defaultdict(list)
    for k in kps:
        if k['id']:
            by_norm[norm_name(k['name'])].append(k['id'])
    collision = {n: v for n, v in by_norm.items() if len(v) >= 2}
    collision_kps = sum(len(v) for v in collision.values())

    file_of = collections.defaultdict(set)
    for k in kps:
        if k['id']:
            file_of[k['id']].add(k['file'])

    data = {
        'schema': 'gue-g3-inbound/v2',
        'corpus': '数字通信原理 frozen (26 md / 11 sidecar)',
        'identity': {'kps': len(kps), 'graph_nodes': len(all_nodes), 'files_with_kp': len({k['file'] for k in kps})},
        'edges_62': edge_stats,
        'links': {'link_entries': link_entries, 'targets': len(link_targets),
                  'instances': link_instances, 'targets_ge2': len(link_multi),
                  'multi_targets': link_multi, 'orphan_targets': link_orphan},
        'derived_similarity_if_materialized': derived,
        'identity_collisions': {'groups': len(collision), 'kps_in_collision_groups': collision_kps,
                                'pct_kps': round(100.0 * collision_kps / len(kps), 1) if kps else 0,
                                'top_groups': sorted(((n, len(v)) for n, v in collision.items()),
                                                     key=lambda x: -x[1])[:8]},
        'placement': {'multi_file_identities': sum(1 for v in file_of.values() if len(v) > 1),
                      'note': '现有模型一个 KP 只属于 1 个文件/区间；跨视图多重归属(transclusion)机制不存在 ⇒ A 类现状=0'},
    }
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(data, ensure_ascii=False, indent=1))
    print('\nwrote', OUT)


if __name__ == '__main__':
    main()
