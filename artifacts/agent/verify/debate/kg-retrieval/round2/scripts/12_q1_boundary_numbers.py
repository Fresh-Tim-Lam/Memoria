# -*- coding: utf-8 -*-
"""12_q1_boundary_numbers.py — Q1「KP 边界重算代价」的四个拍板数字（v2，复用 kpcore 解析器）。

固定快照：round2/frozen/数字通信原理（26 md / 11 sidecar；sha256 见 round2/MANIFEST.json，
对应 2026-10-27T14:09:46 的 data/corpus-snapshot.json）。只读该冻结副本。

输出（round2/data/q1-numbers.json）：
  N1 重切后：切片数 / KP 数变化 / 每 KP 映射几个切片（p50/p90/max）
     rule A 按「下一同级标题」；rule B 按「1200 字预算，超预算再按块边界拆」
     A1/B1 = 以每个 KP 的起点为界；A2/B2 = R2 切片视图（section 分区，可含多个 KP）
  N2 孤儿率（R2 falsifier，阈值 20%）：三种范围（含 KP 的 section / 有 KP 的文件 / 全库）
  N3 同名碰撞消歧后的剩余风险（对照旧口径 32 组 102 条 / 77.6%）
  N4 anchor_verified 覆盖率（R1 三判据；strict=仅靠 snippet 唯一；lenient=允许 hint 消歧）

Run: python 12_q1_boundary_numbers.py
"""
import os
import re
import json
import hashlib
import collections
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROUND2 = os.path.dirname(HERE)
ROOT = os.path.dirname(ROUND2)                      # kg-retrieval/
FROZEN = os.path.join(ROUND2, 'frozen', '数字通信原理')
DATA = os.path.join(ROUND2, 'data')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import kpcore as K  # noqa: E402

BUDGET = 1200
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')


def headings_of(lines):
    hs = []
    for i, l in enumerate(lines, 1):
        m = HEADING_RE.match(l)
        if m:
            hs.append({'line': i, 'level': len(m.group(1)), 'text': m.group(2).strip()})
    return hs


def line_chars(lines, a, b):
    a, b = max(1, a), min(b, len(lines))
    if b < a:
        return 0
    seg = lines[a - 1:b]
    return sum(len(x) for x in seg) + max(0, len(seg) - 1)


def split_budget(lines, start, end, budget=BUDGET):
    """把 [start,end] 按 ≤budget 字符切；优先在空行（块边界）断，否则按行断。"""
    if end < start:
        return []
    slices, cur_start, chars, last_blank = [], start, 0, None
    for i in range(start, end + 1):
        L = len(lines[i - 1]) + 1
        if chars + L > budget and i > cur_start:
            brk = last_blank if (last_blank and last_blank > cur_start) else (i - 1)
            if brk < cur_start:
                brk = i - 1
            slices.append((cur_start, brk))
            cur_start = brk + 1
            chars = sum(len(lines[j - 1]) + 1 for j in range(cur_start, i + 1))
        else:
            chars += L
        if lines[i - 1].strip() == '':
            last_blank = i - 1
    if cur_start <= end:
        slices.append((cur_start, end))
    return slices


def section_partition(lines, hs):
    """每个标题拥有「自己的直属正文」直到下一个 level<=自己的标题；互不重叠。"""
    out = []
    for k, h in enumerate(hs):
        end = len(lines)
        for h2 in hs[k + 1:]:
            if h2['level'] <= h['level']:
                end = h2['line'] - 1
                break
        out.append({'heading': h, 'start': h['line'], 'end': max(h['line'], end)})
    return out


def pct(x, n):
    return round(100.0 * x / n, 1) if n else 0.0


def dist(vals):
    vals = list(vals)
    return {'n': len(vals),
            'p50': round(K.percentile(vals, 50), 2) if vals else None,
            'p90': round(K.percentile(vals, 90), 2) if vals else None,
            'max': max(vals) if vals else None,
            'mean': round(sum(vals) / len(vals), 2) if vals else None}


def main():
    os.makedirs(DATA, exist_ok=True)
    man = json.load(open(os.path.join(ROUND2, 'frozen', 'MANIFEST.json'), encoding='utf-8'))
    md_rel = [f['path'] for f in man['files'] if f['path'].endswith('.md')]
    side_rel = [f['path'] for f in man['files'] if f['path'].endswith('.memoria.yaml')]

    texts = {rel: open(os.path.join(FROZEN, *rel.split('/')), 'r', encoding='utf-8').read()
             for rel in md_rel}
    sidecars = [K.parse_sidecar(os.path.join(FROZEN, *p.split('/'))) for p in side_rel]

    # ---------------------------------------------------------------- rows
    rows = []
    cache = {}
    for rel in md_rel:
        text = texts[rel]
        nt, linemap = K.norm_text(text)
        lines = text.split('\n')
        cache[rel] = {'lines': lines, 'hs': headings_of(lines), 'nt': nt, 'linemap': linemap}
    for sc in sidecars:
        rel = sc['file']
        if rel not in texts:
            continue
        c = cache[rel]
        lines, hs, nt, linemap = c['lines'], c['hs'], c['nt'], c['linemap']
        for kp in sc['kps']:
            st = K.locate(nt, linemap, (kp.get('start') or {}).get('snippet'),
                          (kp.get('start') or {}).get('line_hint'))
            en = K.locate(nt, linemap, (kp.get('end') or {}).get('snippet'),
                          (kp.get('end') or {}).get('line_hint'))
            start = st['line'] if st['status'] not in ('not_found', 'missing') else None
            if start is None:
                start = st['hint'] or 1
                start_ok = False
            else:
                start_ok = True
            owner, level = None, 1
            for h in hs:
                if h['line'] <= start:
                    owner, level = h, h['level']
                else:
                    break
            boundary = len(lines)
            for h in hs:
                if h['line'] > start and h['level'] <= level:
                    boundary = h['line'] - 1
                    break
            end_res = en['line'] if en['status'] not in ('not_found', 'missing') else None
            end_clamped = min(end_res, boundary) if end_res else boundary
            if end_clamped < start:
                end_clamped = max(start, boundary)
            range_ok = bool(start_ok and start <= boundary and end_clamped >= start)
            # R1 的可消歧：snippet 唯一，或 hint 仍指向某个 occurrence（±1 行）
            snippet_unique = bool(st['snippet_unique'])
            hint_disamb = bool(st.get('hint_prefix_ok'))
            hint_strict = bool(st.get('hint_line_starts_with'))
            verified_strict = range_ok and snippet_unique
            verified_lenient = range_ok and (snippet_unique or hint_disamb)
            verified_hintstrict = range_ok and (snippet_unique or hint_strict)
            ambiguous_r1 = range_ok and (st['matches'] > 1) and not hint_disamb
            end_repair = bool(end_res is None or end_res > boundary
                              or (en.get('matches') or 0) > 1 or end_res < start)
            m = re.match(r'^(\d+(?:\.\d+)*)', (owner or {}).get('text', ''))
            rows.append({
                'id': kp['id'], 'name': kp.get('name') or '', 'file': rel,
                'role': '教材' if rel.startswith('教材/') else
                        ('slides' if rel.startswith('img/') else 'notes'),
                'start': start, 'boundary': boundary, 'end': end_clamped,
                'chars': line_chars(lines, start, end_clamped),
                'chars_heading': line_chars(lines, start, boundary),
                'section': m.group(1) if m else None,
                'heading': (owner or {}).get('text', ''),
                'start_ok': start_ok, 'range_ok': range_ok,
                'matches': st['matches'], 'snippet_unique': snippet_unique,
                'hint_disamb': hint_disamb, 'hint_strict': hint_strict,
                'verified_strict': verified_strict, 'verified_lenient': verified_lenient,
                'verified_hintstrict': verified_hintstrict,
                'ambiguous_r1': ambiguous_r1, 'end_repair': end_repair,
            })
    N = len(rows)
    NB = sum(1 for r in rows if r['role'] == '教材')
    files_with_kp = {r['file'] for r in rows}

    # ---------------------------------------------------------------- N1 slices
    # A1: per-KP boundary slice (dedupe identical (file,start,boundary))
    a1 = collections.defaultdict(list)
    for r in rows:
        a1[(r['file'], r['start'], r['boundary'])].append(r['id'])
    # A2: section partition of every md file (non-overlap)
    a2 = []
    for rel in md_rel:
        c = cache[rel]
        for p in section_partition(c['lines'], c['hs']):
            ids = [r['id'] for r in rows if r['file'] == rel and p['start'] <= r['start'] <= p['end']]
            a2.append({'file': rel, 'start': p['start'], 'end': p['end'], 'kp_ids': ids})
    # B1: per-KP budget split
    b1 = collections.defaultdict(list)
    b1_per = {}
    for r in rows:
        lines = cache[r['file']]['lines']
        sl = split_budget(lines, r['start'], r['boundary'])
        b1_per[r['id']] = len(sl)
        for a, b in sl:
            b1[(r['file'], a, b)].append(r['id'])
    # B2: section partition + budget split (R2 视图定义)
    b2 = []
    b2_by_file = collections.defaultdict(list)
    for s in a2:
        for a, b in split_budget(cache[s['file']]['lines'], s['start'], s['end']):
            b2.append({'file': s['file'], 'start': a, 'end': b})
            b2_by_file[s['file']].append((a, b))
    b2_per = {}
    for r in rows:
        cnt = sum(1 for (a, b) in b2_by_file[r['file']]
                  if not (b < r['start'] or a > r['end']))
        b2_per[r['id']] = cnt

    # ---------------------------------------------------------------- N2 orphans
    def orphan_stats(slices, scope):
        tot = orph_any = orph_half = 0
        for s in slices:
            if scope and not scope(s):
                continue
            tot += 1
            lines = cache[s['file']]['lines']
            chars = line_chars(lines, s['start'], s['end'])
            if chars <= 0:
                continue
            cov = []
            for r in rows:
                if r['file'] != s['file']:
                    continue
                if r['end'] < s['start'] or r['start'] > s['end']:
                    continue
                cov.append(line_chars(lines, max(r['start'], s['start']), min(r['end'], s['end'])))
            if not cov or sum(cov) == 0:
                orph_any += 1
                orph_half += 1
            elif sum(cov) / chars < 0.5:
                orph_half += 1
        return {'slices': tot, 'orphan_any_pct': pct(orph_any, tot),
                'orphan_lt50_pct': pct(orph_half, tot)}

    def kp_section_scope(s):
        return any(r['file'] == s['file'] and r['start'] <= s['end'] and r['end'] >= s['start']
                   for r in rows)

    orphans = {
        'A2_kp_section': orphan_stats(a2, kp_section_scope),
        'A2_kp_files': orphan_stats(a2, lambda s: s['file'] in files_with_kp),
        'A2_all': orphan_stats(a2, None),
        'B2_kp_section': orphan_stats(b2, kp_section_scope),
        'B2_kp_files': orphan_stats(b2, lambda s: s['file'] in files_with_kp),
        'B2_all': orphan_stats(b2, None),
    }

    # ---------------------------------------------------------------- N3 duplicate names
    key = lambda r: re.sub(r'\s+', ' ', r['name']).strip()
    groups = collections.defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    dup = {k: v for k, v in groups.items() if len(v) > 1}
    sumk = sum(len(v) for v in dup.values())
    risk_all = (sumk - len(dup)) / sumk if sumk else 0.0
    top15 = sorted(dup.values(), key=len, reverse=True)[:15]
    sumk15 = sum(len(v) for v in top15)
    risk_top15 = (sumk15 - len(top15)) / sumk15 if sumk15 else 0.0

    def ctx(r):
        lines = cache[r['file']]['lines']
        body = ' '.join(lines[r['start'] - 1:min(r['end'], r['start'] + 5)])
        return hashlib.sha256(re.sub(r'\s+', ' ', body)[:200].encode('utf-8')).hexdigest()[:12]

    def residual(fn):
        g = collections.defaultdict(list)
        for r in rows:
            g[fn(r)].append(r)
        coll = {k: v for k, v in g.items() if len(v) > 1}
        return {'collision_groups': len(coll), 'kps': sum(len(v) for v in coll.values()),
                'share_pct': pct(sum(len(v) for v in coll.values()), N),
                'examples': [{'key': list(k) if isinstance(k, tuple) else k,
                              'n': len(v), 'ids': [x['id'] for x in v][:4]} for k, v in list(coll.items())[:5]]}

    dupinfo = {
        'dup_groups': len(dup), 'dup_kps': sumk, 'dup_share_pct': pct(sumk, N),
        'risk_name_only': round(risk_all, 4), 'risk_top15_groups': round(risk_top15, 4),
        'cross_file_groups': sum(1 for v in dup.values() if len({r['file'] for r in v}) > 1),
        'same_file_groups': sum(1 for v in dup.values() if len({r['file'] for r in v}) == 1),
        'disambig_by_file': residual(lambda r: (key(r), r['file'])),
        'disambig_by_file_start': residual(lambda r: (key(r), r['file'], r['start'])),
        'disambig_by_file_start_ctx': residual(lambda r: (key(r), r['file'], r['start'], ctx(r))),
    }

    # ---------------------------------------------------------------- N4 anchor
    def anchor(scope):
        rs = [r for r in rows if scope(r)]
        n = len(rs)
        un = [r for r in rs if not r['range_ok']]
        amb = [r for r in rs if r['range_ok'] and r['ambiguous_r1']]
        ver = [r for r in rs if r['verified_lenient']]
        strict = [r for r in rs if r['verified_strict']]
        hintstrict = [r for r in rs if r['verified_hintstrict']]
        return {'n': n,
                'ANCHOR_VERIFIED_r1': len(ver), 'ANCHOR_VERIFIED_r1_pct': pct(len(ver), n),
                'ANCHOR_VERIFIED_strict': len(strict), 'ANCHOR_VERIFIED_strict_pct': pct(len(strict), n),
                'ANCHOR_VERIFIED_hintstrict': len(hintstrict), 'ANCHOR_VERIFIED_hintstrict_pct': pct(len(hintstrict), n),
                'ANCHOR_UNRESOLVED': len(un), 'ANCHOR_UNRESOLVED_pct': pct(len(un), n),
                'AMBIGUOUS_ANCHOR': len(amb), 'AMBIGUOUS_ANCHOR_pct': pct(len(amb), n),
                'needs_end_repair': sum(1 for r in rs if r['end_repair']),
                'needs_end_repair_pct': pct(sum(1 for r in rs if r['end_repair']), n)}

    out = {
        'frozen': {'source': '2026-10-27T14:09:46', 'md': len(md_rel), 'sidecars': len(side_rel),
                   'kps': N, 'textbook_kps': NB, 'manifest': 'round2/MANIFEST.json'},
        'N1': {
            'budget_chars': BUDGET,
            'kp_count_change': 0,
            'kp_chars': {'all': dist([r['chars_heading'] for r in rows]),
                         'textbook': dist([r['chars_heading'] for r in rows if r['role'] == '教材']),
                         'gt1200_all_pct': pct(sum(1 for r in rows if r['chars_heading'] > 1200), N),
                         'gt1200_textbook_pct': pct(sum(1 for r in rows if r['role'] == '教材' and r['chars_heading'] > 1200), NB)},
            'kp_chars_current_anchor': {
                'all': dist([r['chars'] for r in rows]),
                'textbook': dist([r['chars'] for r in rows if r['role'] == '教材']),
                'note': '现行 range（end snippet 解析后再夹到下一同级标题）；N1 主口径用 chars_heading（重切后的语义边界）'},
            'A1_per_kp_section': {'slices': len(a1), 'slices_per_kp': dist([1] * N),
                                  'shared_slices': sum(1 for v in a1.values() if len(v) > 1),
                                  'kps_in_shared': sum(len(v) for v in a1.values() if len(v) > 1)},
            'A2_section_partition': {'slices': len(a2),
                                     'slices_kp_files': sum(1 for s in a2 if s['file'] in files_with_kp),
                                     'slices_with_kp': sum(1 for s in a2 if s['kp_ids']),
                                     'kp_per_slice': dist([len(s['kp_ids']) for s in a2]),
                                     'kp_per_slice_when_nonzero': dist([len(s['kp_ids']) for s in a2 if s['kp_ids']])},
            'B1_per_kp_budget': {'slices': len(b1), 'slices_per_kp': dist([b1_per[r['id']] for r in rows]),
                                 'kps_ge2': sum(1 for r in rows if b1_per[r['id']] > 1)},
            'B2_section_budget': {'slices': len(b2),
                                  'slices_kp_files': sum(1 for s in b2 if s['file'] in files_with_kp),
                                  'slices_per_kp': dist([b2_per[r['id']] for r in rows]),
                                  'kps_ge2': sum(1 for r in rows if b2_per[r['id']] > 1),
                                  'kps_ge5': sum(1 for r in rows if b2_per[r['id']] >= 5),
                                  'kps_zero': sum(1 for r in rows if b2_per[r['id']] == 0)},
            'by_role_textbook': {
                'kps': NB,
                'A1_slices': len({(r['file'], r['start'], r['boundary']) for r in rows if r['role'] == '教材'}),
                'B1_slices': sum(b1_per[r['id']] for r in rows if r['role'] == '教材'),
                'B1_slices_per_kp': dist([b1_per[r['id']] for r in rows if r['role'] == '教材']),
                'B2_slices_per_kp': dist([b2_per[r['id']] for r in rows if r['role'] == '教材']),
                'B2_unique_slices_touching_textbook_kp': sum(
                    1 for s in b2 if any(r['file'] == s['file'] and not (r['end'] < s['start'] or r['start'] > s['end'])
                                         for r in rows if r['role'] == '教材')),
            },
        },
        'N2': orphans,
        'N3': dupinfo,
        'N4': {'all': anchor(lambda r: True), 'textbook': anchor(lambda r: r['role'] == '教材'),
               'slides': anchor(lambda r: r['role'] == 'slides')},
    }
    json.dump(out, open(os.path.join(DATA, 'q1-numbers.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    print('# 12 Q1 boundary recompute (v2)')
    print('\n## frozen:', out['frozen'])
    n1 = out['N1']
    print('\n## N1 重切后（KP 数不变）')
    print(f"- KP chars（重切语义边界）all: {n1['kp_chars']['all']}")
    print(f"- KP chars（重切语义边界）textbook: {n1['kp_chars']['textbook']}")
    print(f"- KP chars（现行 end 锚点）textbook: {n1['kp_chars_current_anchor']['textbook']}")
    print(f"- >1200 字: all {n1['kp_chars']['gt1200_all_pct']}% / 教材 {n1['kp_chars']['gt1200_textbook_pct']}%")
    print(f"- A1 per-KP 下一同级标题: {json.dumps(n1['A1_per_kp_section'], ensure_ascii=False)}")
    print(f"- A2 section 分区: {json.dumps(n1['A2_section_partition'], ensure_ascii=False)}")
    print(f"- B1 per-KP 1200: {json.dumps(n1['B1_per_kp_budget'], ensure_ascii=False)}")
    print(f"- B2 section+1200: {json.dumps(n1['B2_section_budget'], ensure_ascii=False)}")
    print('\n## N2 孤儿率')
    for k, v in out['N2'].items():
        print(f"- {k}: {v}")
    n3 = out['N3']
    print('\n## N3 同名碰撞')
    print(f"- groups={n3['dup_groups']} kps={n3['dup_kps']} ({n3['dup_share_pct']}%) "
          f"risk_name_only={n3['risk_name_only']*100:.1f}% risk_top15={n3['risk_top15_groups']*100:.1f}% "
          f"cross/same file={n3['cross_file_groups']}/{n3['same_file_groups']}")
    for kk in ('disambig_by_file', 'disambig_by_file_start', 'disambig_by_file_start_ctx'):
        v = n3[kk]
        print(f"- {kk}: collisions={v['collision_groups']} kps={v['kps']} ({v['share_pct']}%)")
    print('\n## N4 anchor_verified (R1)')
    for k, v in out['N4'].items():
        print(f"- {k}: {json.dumps(v, ensure_ascii=False)}")
    print('\nwrote round2/data/q1-numbers.json')


if __name__ == '__main__':
    main()
