# -*- coding: utf-8 -*-
"""G2 边清单 + 分层抽样（确定种子；只读 frozen 快照）。

产物：
  G2-edge-inventory-raw.json   62 条边全量（含 source/target 名称）
  G2-sampling.json             分层抽样 24 条 + 分层定义 + 种子

抽样设计（Lead 约束：24 条；作者边 26 里取 12；约 1 分钟/条）：
  authored_extend              21 -> 9
  authored_reference            5 -> 3
  link_reference                3 -> 3   （全取：唯一一类"由正文链接投影的边"）
  derived_contain_valid        25 -> 6   （33 条 contain - 8 条退化）
  derived_contain_degenerate    8 -> 3   （同名/OCR 错名：M2 known-bad 夹具）
  合计 24。种子 20261027；层内按 (file,src,tgt) 排序后 sample。
  退化判定：contain 且 (去编号/标点空白后 src 名 == tgt 名) 或 ("传"+tgt 名 == src 名，OCR 前缀错)。

Run:  python scripts/G2-edge-inventory.py
"""
import json
import os
import random
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)
FROZEN = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'kg-retrieval', 'round2', 'frozen', '数字通信原理')
SEED = 20261027
ALLOC = {'authored_extend': 9, 'authored_reference': 3, 'link_reference': 3,
         'derived_contain_valid': 6, 'derived_contain_degenerate': 3}


def ensure_copy():
    tmp_root = os.path.join(tempfile.gettempdir(), 'gue-g2')
    dst = os.path.join(tmp_root, '数字通信原理')
    if os.path.isdir(tmp_root):
        shutil.rmtree(tmp_root)
    os.makedirs(tmp_root, exist_ok=True)
    shutil.copytree(FROZEN, dst)
    return dst


def main():
    kb = ensure_copy()
    sys.path.insert(0, r'D:\AAA_Jupyter\Memoria\src')
    os.environ.setdefault('MEMORIA_CONFIG_DIR', os.path.join(tempfile.gettempdir(), 'gue-cfg'))
    from memoria.graph.collector import collect_graph_data

    g = collect_graph_data(kb)
    names = {n['id']: n['name'] for n in g['nodes']}
    edges = []
    for e in g['edges']:
        edges.append({
            'src': e['source_id'], 'src_name': names.get(e['source_id'], e['source_id']),
            'tgt': e['targets'][0], 'tgt_name': names.get(e['targets'][0], e['targets'][0]),
            'type': e['type'], 'origin': e['origin'], 'derived': e.get('derived'),
            'relevance': e.get('relevance'), 'file': e['file'],
        })
    edges.sort(key=lambda x: (x['file'], x['type'], x['src'], x['tgt']))

    def norm_name(s):
        s = (s or '').strip()
        s = re.sub(r'^[※\s]+', '', s)
        s = re.sub(r'^\(\d+\)\s*', '', s)
        s = re.sub(r'^\d+\.\s*', '', s)
        s = re.sub(r'[\s\$\{\}\\\_\^]', '', s)
        return s

    def stratum(e):
        if e['origin'] == 'range':
            ns, nt = norm_name(e['src_name']), norm_name(e['tgt_name'])
            degenerate = (ns == nt) or (('传' + nt) == ns) or (('传' + ns) == nt)
            return 'derived_contain_degenerate' if degenerate else 'derived_contain_valid'
        if e['origin'] == 'link':
            return 'link_reference'
        return 'authored_extend' if e['type'] == 'extend' else 'authored_reference'

    groups = {}
    for e in edges:
        groups.setdefault(stratum(e), []).append(e)

    rng = random.Random(SEED)
    selected, rest = [], []
    for st, n in ALLOC.items():
        pool = list(groups.get(st, []))
        take = min(n, len(pool))
        picked = rng.sample(pool, take)
        for e in pool:
            e2 = dict(e)
            e2['stratum'] = st
            (selected if e in picked else rest).append(e2)
    selected.sort(key=lambda x: (x['stratum'], x['file'], x['src'], x['tgt']))

    for i, e in enumerate(selected, 1):
        e['sample_id'] = f'L2-{i:02d}'

    inv = {'schema': 'gue-g2-edge-inventory/v1', 'count': len(edges), 'edges': edges}
    json.dump(inv, open(os.path.join(OUT_DIR, 'G2-edge-inventory-raw.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    sampling = {
        'schema': 'gue-g2-sampling/v1',
        'seed': SEED,
        'strata': {st: {'population': len(groups.get(st, [])), 'allocated': ALLOC[st],
                        'sampled': sum(1 for e in selected if e['stratum'] == st)}
                   for st in ALLOC},
        'selected': [{k: e.get(k) for k in ('sample_id', 'stratum', 'type', 'origin', 'derived',
                                           'file', 'src', 'src_name', 'tgt', 'tgt_name', 'relevance')}
                     for e in selected],
        'not_selected_count': len(rest),
        'note': '种子 20261027；层内按 (file,type,src,tgt) 排序后 random.Random.sample；'
                '若抽样版与全量版结论冲突，按 G2-L2-protocol.md §4.3 扩展规则执行',
    }
    json.dump(sampling, open(os.path.join(OUT_DIR, 'G2-sampling.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('# 全量边清单（62）')
    for i, e in enumerate(edges, 1):
        print(f"{i:02d}\t{e['type']}\t{e['origin']}\t{e['file']}\t{e['src_name']} -> {e['tgt_name']}")
    print('\n# 分层抽样（24）')
    for e in selected:
        print(f"{e['sample_id']}\t{e['stratum']}\t{e['src_name']} -> {e['tgt_name']}\t({e['file']})")
    print('\nstrata:', json.dumps(sampling['strata'], ensure_ascii=False))
    print('wrote G2-edge-inventory-raw.json / G2-sampling.json')


if __name__ == '__main__':
    main()
