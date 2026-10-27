# -*- coding: utf-8 -*-
"""G1 baseline probe — 图谱基线（绑定 frozen 快照；产品 collect_graph_data 真值）。

只做 G1 需要的基线统计：
  节点/边数、边类型×来源、relevance 分布、node 字段、边字段、
  连通性（covered/isolated/components/degree）、description 空值率。

纪律：
  - 只读 `round2/frozen/数字通信原理`，先复制到临时目录再跑（避免 build/cache 落盘污染 frozen）
  - 测量源 = 现场 `collect_graph_data()`（禁止 `.memoria/build/graph.json`）
  - 输出 `G1-baseline.json`；同参数连跑两次应逐字节一致（除 timestamp 字段）

Run:
  python artifacts/agent/verify/debate/graph-utility/scripts/G1-baseline.py
"""
import collections
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)                       # .../graph-utility
FROZEN = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'kg-retrieval', 'round2', 'frozen', '数字通信原理')
OUT = os.path.join(OUT_DIR, 'G1-baseline.json')


def _ensure_src():
    if not os.path.isdir(FROZEN):
        sys.exit(f'frozen snapshot not found: {FROZEN}')
    tmp_root = os.path.join(tempfile.gettempdir(), 'gue-baseline')
    dst = os.path.join(tmp_root, '数字通信原理')
    if os.path.isdir(tmp_root):
        shutil.rmtree(tmp_root)
    os.makedirs(tmp_root, exist_ok=True)
    shutil.copytree(FROZEN, dst)
    return dst


def _components(ids, edges):
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in edges:
        a = e['source_id']
        b = e['targets'][0]
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    sizes = collections.Counter(find(i) for i in ids)
    return sorted(sizes.values(), reverse=True)


def main():
    kb = _ensure_src()
    sys.path.insert(0, r'D:\AAA_Jupyter\Memoria\src')
    os.environ.setdefault('MEMORIA_CONFIG_DIR', os.path.join(tempfile.gettempdir(), 'gue-cfg'))
    from memoria.graph.collector import collect_graph_data  # noqa: E402

    g = collect_graph_data(kb)
    nodes = g.get('nodes') or []
    edges = g.get('edges') or []

    ids = [n['id'] for n in nodes]
    deg = collections.Counter()
    for e in edges:
        deg[e['source_id']] += 1
        deg[e['targets'][0]] += 1
    covered = set(deg)
    comp = _components(ids, edges)

    data = {
        'schema': 'gue-baseline/v1',
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'measurement': {
            'corpus': '数字通信原理',
            'corpus_identity': 'frozen copy of round2/frozen/数字通信原理 (37 files, MANIFEST sha256 a4beaedc5f852816129ebc8399072a17b6b07e97bd22ea848246ae90a3b75466)',
            'source': 'memoria.graph.collector.collect_graph_data() on temp copy',
            'build_state': 'no .memoria/build (pre_build)',
        },
        'counts': {
            'nodes': len(nodes), 'edges': len(edges),
            'md_files': 26, 'sidecars': 11,
            'covered_nodes': len(covered),
            'isolated_nodes': len(nodes) - len(covered),
            'covered_pct': round(100.0 * len(covered) / len(nodes), 1),
            'components': len(comp),
            'largest_component': comp[0] if comp else 0,
            'avg_degree': round(sum(deg.values()) / len(nodes), 3),
            'edge_node_ratio': round(len(edges) / len(nodes), 3),
            'range_ok_nodes': sum(1 for n in nodes if n.get('range_ok')),
            'range_ok_pct': round(100.0 * sum(1 for n in nodes if n.get('range_ok')) / len(nodes), 1),
        },
        'edge_types': dict(collections.Counter(e.get('type') for e in edges)),
        'edge_origins': dict(collections.Counter(e.get('origin') for e in edges)),
        'origin_x_type': {f'{k[0]}|{k[1]}': v for k, v in
                          collections.Counter((e.get('origin'), e.get('type')) for e in edges).items()},
        'derived': {str(k): v for k, v in collections.Counter(str(e.get('derived')) for e in edges).items()},
        'relevance': {str(k): v for k, v in collections.Counter(str(e.get('relevance')) for e in edges).items()},
        'edge_field_absence': {
            'fact': sum(1 for e in edges if 'fact' in e),
            'valid_at': sum(1 for e in edges if 'valid_at' in e),
            'invalid_at': sum(1 for e in edges if 'invalid_at' in e),
            'confidence': sum(1 for e in edges if 'confidence' in e),
            'provenance': sum(1 for e in edges if 'provenance' in e),
            'instances': sum(1 for e in edges if 'instances' in e),
        },
        'node_fields': sorted(nodes[0].keys()) if nodes else [],
        'node_description_nonempty': sum(1 for n in nodes if (n.get('description') or '').strip()),
        'degree_hist': {str(k): v for k, v in collections.Counter(deg.values()).items()},
        'component_sizes_top10': comp[:10],
        'multi_target_edges': sum(1 for e in edges if len(e.get('targets') or []) != 1),
    }
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(data, ensure_ascii=False, indent=1))
    print('\nwrote', OUT)


if __name__ == '__main__':
    main()
