# -*- coding: utf-8 -*-
"""07_index_method.py — Phase 1.5 measurements for R9/R10/R13/R14.

Read-only over D:\\AAA_Courses. Produces data/index-method.json.

E1 ROUTING   lexical routing hit@1/@3 over 7 entry variants / 2 index scopes
             (13 text questions; 2 line-anchored + 4 meta reported separately)
E2 CENTRALITY question-free "importance" proxies: cross-unit term centrality
             (over all units and over textbook units only)
E3 COVERAGE  "if only 20% can be built, which 20%?" — 8 policies at equal budget
E4 BLOCKS    blank-line blocks vs headings: count, classes, stability under
             formatting reflow / blank-line edits / content edits
E5 QUALITY   duplicate names (content divergence), content-free units,
             boundary-ambiguous sibling names
E6 COSTS     skeleton / minimum-viable-index / full-build cost model inputs

Run: python 07_index_method.py
"""
import os
import re
import json
import math
import sys
import collections
import random as _random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402

GROUND_TRUTH = [
    (1, "什么叫量化", ["quantization-overview", "scalar-quantization"], "content"),
    (2, "帮我记笔记划关键词", [], "meta"),
    (3, "抽样和量化有什么区别", ["aliasing", "quantization-overview", "uniform-quantization"], "content"),
    (4, "为什么要分这么多电平量化", ["uniform-quantization", "nonuniform-quantization"], "content"),
    (5, "PCM是什么", ["pcm"], "content"),
    (6, "从数学公式上学习抽样和量化的区别", ["aliasing", "uniform-quantization", "nonuniform-quantization"], "content"),
    (7, "维护知识点和链接避免爆上下文", [], "meta"),
    (8, "信道上传输的是幅度量化之后各种频率的波吗", ["pcm", "a-law-mu-law-pcm", "pcm-coding-methods"], "content"),
    (9, "f_H是什么只要保证大于两倍不论带通还是理想抽样都能无损还原吗", ["aliasing", "ideal-sampling"], "content"),
    (10, "带通抽样需要满足怎样的条件才可以无损", ["bandpass-sampling"], "content"),
    (11, "为什么会有上界低通思路只有下界", ["bandpass-sampling"], "content"),
    (12, "可行区域是一连串区间并上超宽松区间", ["bandpass-sampling"], "content"),
    (13, "好", [], "meta"),
    (14, "按照你建议", [], "meta"),
    (15, "3.3.19推导跳步了", ["uniform-quantization"], "line"),
    (16, "只有功率信号分布均匀才能这样推导", ["uniform-quantization"], "content"),
    (17, "为什么要这样设计", ["nonuniform-quantization"], "line"),
    (18, "先变换然后再均匀量化吗为什么可以降低噪声", ["nonuniform-quantization", "logarithmic-quantization"], "content"),
    (19, "量化的含义这个公式只能代入均匀分布", ["quantization-overview", "uniform-quantization"], "content"),
]

CJK = K.CJK_RE
DEF_CUES = ['称为', '定义为', '所谓', '即', '是指', '表示', '定理', '性质', '结论', '条件', '因此', '由此']
HOT_IDS = sorted({i for _, _, ids, kind in GROUND_TRUTH if kind == 'content' for i in ids})
CORE_HOT = ['quantization-overview', 'uniform-quantization', 'nonuniform-quantization',
            'bandpass-sampling', 'aliasing', 'pcm']


def tokens_of(text):
    text = text or ''
    toks = []
    for run in re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]+', text):
        for i in range(len(run) - 1):
            toks.append(run[i:i + 2])
    for w in re.findall(r'[A-Za-z0-9_]+', text):
        if len(w) > 1:
            toks.append(w.lower())
    return toks


class BM25:
    def __init__(self, docs):
        self.docs = docs
        self.N = len(docs)
        self.df = collections.Counter()
        self.tf = []
        self.dl = []
        for d in docs:
            c = collections.Counter(d)
            self.tf.append(c)
            self.dl.append(len(d))
            for t in c:
                self.df[t] += 1
        self.avgdl = (sum(self.dl) / self.N) if self.N else 0

    def idf(self, t):
        df = self.df.get(t, 0)
        return math.log(1 + (self.N - df + 0.5) / (df + 0.5))

    def rank(self, query, topk=3):
        q = collections.Counter(tokens_of(query))
        scored = []
        for di in range(self.N):
            tf, dl = self.tf[di], (self.dl[di] or 1)
            s = 0.0
            for t, qn in q.items():
                f = tf.get(t)
                if not f:
                    continue
                denom = f + 1.2 * (1 - 0.75 + 0.75 * dl / (self.avgdl or 1))
                s += self.idf(t) * (f * 2.2 / denom) * qn
            if s > 0:
                scored.append((s, di))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored[:topk]


def norm_query(q):
    q = re.sub(r'@[^\s，。]+', ' ', q)
    q = re.sub(r'#L\d+(C\d+)?(-L\d+(C\d+)?)?', ' ', q)
    return q.strip()


def unit_text(r):
    return (r['name'] or '') + ' ' + r['_span_text']


def main():
    data = K.ensure_data_dir()
    inv = json.load(open(os.path.join(data, 'kp_inventory.json'), encoding='utf-8'))
    rows = inv['target_kb_rows']
    root = K.KB_ROOTS[K.TARGET_KB]
    cache = {}
    for r in rows:
        r['_uid'] = f"{r['sidecar']}::{r['id']}"
        f = r['file']
        if f not in cache:
            p = os.path.join(root, *f.split('/'))
            cache[f] = K.read_text(p).split('\n') if os.path.isfile(p) else []
        lines = cache[f]
        s = r['start_found_line'] or r['start_hint'] or 1
        e = r['end_found_line'] or r['end_hint'] or s
        if e < s:
            e = s
        s, e = max(1, s), min(e, len(lines))
        r['_span_text'] = '\n'.join(lines[s - 1:e])
        r['_textbook'] = f.startswith('教材/')
    by_id = {r['id']: r for r in rows}
    ch03 = [r for r in rows if r['file'].startswith('教材/03')]
    descs = json.load(open(os.path.join(data, 'ch03-descriptions.json'), encoding='utf-8'))
    out = {}

    # ============================================================ E1 ROUTING
    text_qs = [(n, norm_query(q), ids) for n, q, ids, kind in GROUND_TRUTH if kind == 'content']
    line_qs = [(n, q, ids) for n, q, ids, kind in GROUND_TRUTH if kind == 'line']

    def evaluate(units, fn, label, qs):
        bm = BM25([tokens_of(fn(u)) for u in units])
        h1 = h3 = wrong1 = zero = 0
        detail = []
        for n, q, ids in qs:
            ranked = bm.rank(q, 3)
            exp = set(ids)
            top = [units[i] for _, i in ranked]
            got1 = top[0]['id'] if top else None
            ok1 = got1 in exp
            ok3 = any(u['id'] in exp for u in top)
            h1 += ok1
            h3 += ok3
            if not top:
                zero += 1
            elif not ok1:
                wrong1 += 1
            detail.append({'q': n, 'top1': got1, 'top3': [u['id'] for u in top],
                           'hit1': ok1, 'hit3': ok3})
        return {'label': label, 'n': len(qs), 'hit1': h1, 'hit3': h3,
                'hit1_pct': K.pct(h1, len(qs)), 'hit3_pct': K.pct(h3, len(qs)),
                'wrong_top1_pct': K.pct(wrong1, len(qs)),
                'zero_score_pct': K.pct(zero, len(qs)), 'detail': detail}

    n_units = len(rows)
    variants = [
        (f'V0 name only ({n_units})', lambda u: u['name'], rows),
        (f'V1 name+tags ({n_units})', lambda u: (u['name'] or '') + ' ' + (u.get('tags') or ''), rows),
        (f'V2 name+snippet40 ({n_units})', lambda u: (u['name'] or '') + ' ' + K.norm_snip(u['start_snippet'] or '')[:40], rows),
        (f'V3 name+snippet160 ({n_units})', lambda u: (u['name'] or '') + ' ' + K.norm_snip(u['start_snippet'] or '')[:160], rows),
        (f'V4 name+full unit ({n_units})', lambda u: unit_text(u), rows),
        ('V6 ch03 28 names only', lambda u: u['name'], ch03),
        ('V7 ch03 28 name+question-worded desc', lambda u: (u['name'] or '') + ' ' + descs.get(u['id'], ''), ch03),
    ]
    out['routing'] = {'variants': [evaluate(u, f, l, text_qs) for l, f, u in variants],
                      'line_anchored': {'n': len(line_qs),
                                        'rule': 'file#line -> unit whose range contains the line (no lexical routing)',
                                        'detail': [{'q': n, 'ideal': ids,
                                                    'range': [by_id[ids[0]]['start_hint'], by_id[ids[0]]['end_hint']]
                                                    if ids and ids[0] in by_id else None}
                                                   for n, q, ids in line_qs]},
                      'hot_ids': HOT_IDS, 'core_hot': CORE_HOT}
    # harmful misroute: top1 wrong but content similar (Jaccard >= 0.25) to an
    # ideal unit -> the agent would trust a plausible-but-wrong slice.
    def jac(a, b):
        A, B = set(tokens_of(a)), set(tokens_of(b))
        return len(A & B) / max(1, len(A | B))
    for v in out['routing']['variants']:
        harm = []
        for d in v['detail']:
            if d['hit1'] or not d['top1'] or d['top1'] not in by_id:
                continue
            cand = [by_id[i] for i in GROUND_TRUTH[d['q'] - 1][2] if i in by_id]
            if not cand:
                continue
            sim = max(jac(by_id[d['top1']]['_span_text'], c['_span_text']) for c in cand)
            harm.append({'q': d['q'], 'top1': d['top1'], 'sim_to_ideal': round(sim, 3),
                         'harmful': sim >= 0.25})
        v['wrong_top1'] = len(harm)
        v['harmful_misroute'] = sum(1 for h in harm if h['harmful'])
        v['harmful_misroute_pct'] = K.pct(v['harmful_misroute'], v['n'])
        v['harmful_examples'] = harm[:6]
    # MVI audit: does the 7-unit MVI cover each question at unit granularity?
    mvi = ['aliasing', 'bandpass-sampling', 'quantization-overview', 'uniform-quantization',
           'nonuniform-quantization', 'logarithmic-quantization', 'pcm']
    mvi_cov = []
    for n, q, ids, kind in GROUND_TRUTH:
        if kind in ('content', 'line'):
            mvi_cov.append({'q': n, 'ideal': ids, 'covered': bool(set(ids) & set(mvi))})
    out['routing']['mvi'] = {'units': mvi, 'questions_covered': sum(1 for x in mvi_cov if x['covered']),
                             'questions_total': len(mvi_cov), 'detail': mvi_cov}

    # ============================================================ E2 CENTRALITY
    def centrality_table(units):
        docs = [tokens_of(unit_text(u)) for u in units]
        N = len(units)
        df = collections.Counter()
        for d in docs:
            for t in set(d):
                df[t] += 1
        stop = {t for t, c in df.items() if c / N > 0.30}
        scored = []
        for u, d in zip(units, docs):
            c = collections.Counter(d)
            terms = [t for t in c if t not in stop and df[t] >= 2]
            terms.sort(key=lambda t: -(c[t] * math.log(N / df[t])))
            top = terms[:20]
            v = sum(math.log(N / df[t]) * (df[t] - 1) for t in top) / len(top) if top else 0.0
            scored.append({'id': u['id'], 'file': u['file'], 'centrality': round(v, 3)})
        scored.sort(key=lambda x: -x['centrality'])
        return scored, {s['id']: i + 1 for i, s in enumerate(scored)}

    cen_all, rank_all = centrality_table(rows)
    textbook_rows = [r for r in rows if r['_textbook']]
    cen_tb, rank_tb = centrality_table(textbook_rows)
    out['centrality'] = {
        'definition': 'per unit: mean over its top20 non-stop bigrams of idf*(df-1); higher = unit vocabulary reused across many units',
        'all_units': [{'id': i, 'rank': rank_all.get(i)} for i in HOT_IDS],
        'textbook_units_only': [{'id': i, 'rank': rank_tb.get(i)} for i in HOT_IDS],
        'n_all': len(rows), 'n_textbook': len(textbook_rows),
        'hot_in_top20pct_all': sum(1 for i in HOT_IDS if rank_all.get(i, 9999) <= len(rows) * 0.2),
        'hot_in_top20pct_textbook': sum(1 for i in HOT_IDS if rank_tb.get(i, 9999) <= len(textbook_rows) * 0.2),
        'top20_all': cen_all[:20], 'top20_textbook': cen_tb[:20],
    }

    # ============================================================ E3 COVERAGE
    unit_tokens = {r['id']: round(K.est_tokens(r['_span_text'])) for r in rows}
    struct = json.load(open(os.path.join(data, 'structure.json'), encoding='utf-8'))
    book_tokens = struct['total']['textbook_est_tokens']
    budget = 0.20 * book_tokens
    hot = set(HOT_IDS)

    # book order: 教材/00..13 by name, then others
    book_files = [r['file'] for r in rows if r['_textbook']]
    def file_key(f):
        m = re.match(r'教材/(\d+)', f)
        return (0, int(m.group(1))) if m else (1, f)
    book_files = sorted(set(book_files), key=file_key)
    others_files = sorted({r['file'] for r in rows if not r['_textbook']})
    def order_units(files):
        ids = []
        for f in files:
            ids += [r['id'] for r in sorted([x for x in rows if x['file'] == f],
                                            key=lambda x: x['start_hint'] or 0)]
        return ids

    def sel_until(ids, budget_tokens):
        sel, acc = [], 0
        for i in ids:
            if acc >= budget_tokens:
                break
            sel.append(i)
            acc += unit_tokens.get(i, 0)
        return sel

    p1 = sel_until(order_units(book_files), budget)
    p1b = sel_until(order_units(book_files + others_files), budget)
    p2 = sel_until([r['id'] for r in sorted(rows, key=lambda x: -unit_tokens[x['id']])], budget)
    p3 = sel_until([s['id'] for s in cen_all], budget)
    p4 = list(hot)
    p6 = sel_until([r['id'] for r in sorted(rows, key=lambda x: -_cue_score(x))], budget)
    p7 = sel_until([r['id'] for r in sorted(rows, key=lambda x: -_formula_density(x))], budget)
    rng = _random.Random(20261027)
    rand_cov = []
    for _ in range(300):
        sel = set(rng.sample([r['id'] for r in rows], 60))
        rand_cov.append(len(hot & sel))

    policies = [
        ('P1 教材按书序（从第1章起）', p1),
        ('P1b 全部按书序（教材优先）', p1b),
        ('P2 单元从大到小', p2),
        ('P3 中心度从高到低', p3),
        ('P4 后见之明：只建理想 KP', p4),
        ('P6 定义/结论线索密度从高到低', p6),
        ('P7 公式密度从高到低', p7),
    ]
    cov_tok = []
    for label, sel in policies:
        c = len(hot & set(sel))
        cov_tok.append({'policy': label, 'units': len(sel),
                        'tokens': sum(unit_tokens.get(i, 0) for i in set(sel)),
                        'hot_covered': c, 'hot_total': len(hot), 'hot_cover_pct': K.pct(c, len(hot))})
    cov_tok.append({'policy': 'P5 随机（60 单元，300 次期望）', 'units': 60, 'tokens': None,
                    'hot_covered': round(sum(rand_cov) / len(rand_cov), 2), 'hot_total': len(hot),
                    'hot_cover_pct': K.pct(sum(rand_cov) / len(rand_cov), len(hot))})
    # 20% of units
    bud_u = int(0.20 * len(rows))
    cov_units = []
    for label, ids in [('教材按书序', order_units(book_files)),
                       ('全部按书序', order_units(book_files + others_files)),
                       ('单元从大到小', [r['id'] for r in sorted(rows, key=lambda x: -unit_tokens[x['id']])]),
                       ('中心度', [s['id'] for s in cen_all]),
                       ('定义线索密度', [r['id'] for r in sorted(rows, key=lambda x: -_cue_score(x))])]:
        sel = ids[:bud_u]
        c = len(hot & set(sel))
        cov_units.append({'policy': label, 'units': len(sel), 'hot_covered': c,
                          'hot_cover_pct': K.pct(c, len(hot))})
    out['coverage'] = {'book_tokens': book_tokens, 'budget_20pct_tokens': round(budget),
                       'indexed_unit_tokens_total': sum(unit_tokens.values()),
                       'by_tokens': cov_tok, 'budget_20pct_units': bud_u, 'by_units': cov_units,
                       'hot_ids': sorted(hot), 'core_hot': CORE_HOT,
                       'hot_tokens': {i: unit_tokens.get(i) for i in sorted(hot)}}

    # ============================================================ E4 BLOCKS
    md_all = K.md_files(root)
    block_stats = []
    for path in md_all:
        f = K.rel(path, root)
        blocks = _blocks(K.read_text(path))
        cls = collections.Counter(b['kind'] for b in blocks)
        block_stats.append({'file': f, 'blocks': len(blocks), 'kinds': dict(cls)})
    kind_tot = dict(sum((collections.Counter(b['kinds']) for b in block_stats), collections.Counter()))
    stability = _block_stability(K.read_text(os.path.join(root, '教材', '03_第3章_模拟信号的数字编码.md')))
    out['blocks'] = {'files': len(block_stats), 'total_blocks': sum(b['blocks'] for b in block_stats),
                     'mean_blocks_per_file': round(sum(b['blocks'] for b in block_stats) / max(1, len(block_stats)), 1),
                     'kind_totals': kind_tot, 'per_file': block_stats, 'stability': stability,
                     'definition': 'block = run of non-empty lines separated by one or more blank lines'}

    # ============================================================ E5 QUALITY
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r['file'], r['name'])].append(r)
    dup = []
    for (f, n), rs in groups.items():
        if len(rs) < 2:
            continue
        tsets = [set(tokens_of(r['_span_text'])) for r in rs]
        jac = []
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = tsets[i], tsets[j]
                jac.append(len(a & b) / max(1, len(a | b)))
        dup.append({'file': f, 'name': n, 'n': len(rs),
                    'mean_jaccard': round(sum(jac) / len(jac), 3), 'min_jaccard': round(min(jac), 3),
                    'kps': [r['id'] for r in rs]})
    dup.sort(key=lambda x: -x['n'])

    def unit_kind(r):
        t = r['_span_text']
        cjk = len(CJK.findall(t))
        chars = max(1, len(t))
        lines = [l for l in t.split('\n') if l.strip()]
        bullets = sum(1 for l in lines if re.match(r'^\s*([-*]|\d+[.、])\s', l))
        formula = sum(1 for l in lines if re.search(r'\$|\\[a-zA-Z]', l))
        images = sum(1 for l in lines if l.lstrip().startswith('!['))
        if chars < 200:
            return 'too-small'
        if cjk / chars < 0.05 and formula / max(1, len(lines)) > 0.5:
            return 'formula-only'
        if cjk / chars < 0.08 and images / max(1, len(lines)) > 0.4:
            return 'image-only'
        if bullets / len(lines) > 0.6 and chars < 500:
            return 'toc-like'
        if cjk / chars < 0.15:
            return 'formula-heavy(warn)'
        return 'ok'
    kinds = collections.Counter()
    bad = []
    for r in rows:
        k = unit_kind(r)
        kinds[k] += 1
        if k != 'ok':
            bad.append({'id': r['id'], 'name': r['name'], 'file': r['file'], 'kind': k,
                        'chars': len(r['_span_text'])})
    # boundary ambiguity: same file, both names >=3 CJK, bigram jaccard >=0.66
    def cjk_len(s):
        return len(CJK.findall(s or ''))
    boundary = []
    by_file = collections.defaultdict(list)
    for r in rows:
        by_file[r['file']].append(r)
    for f, rs in by_file.items():
        for r in rs:
            nt = set(tokens_of(r['name']))
            if cjk_len(r['name']) < 3 or len(nt) < 2:
                continue
            near = []
            for o in rs:
                if o['id'] == r['id'] or cjk_len(o['name']) < 3:
                    continue
                ot = set(tokens_of(o['name']))
                if len(ot) < 2:
                    continue
                j = len(nt & ot) / max(1, len(nt | ot))
                if j >= 0.66:
                    near.append((o['id'], round(j, 2)))
            if near:
                boundary.append({'id': r['id'], 'name': r['name'], 'file': f, 'near': near[:4]})
    out['quality'] = {'dup_groups': len(dup), 'dup_units': sum(d['n'] for d in dup),
                      'dup_low_divergence_groups': sum(1 for d in dup if d['mean_jaccard'] < 0.30),
                      'dup_examples': dup[:15], 'unit_kinds': dict(kinds),
                      'bad_units': bad, 'bad_unit_count': len(bad),
                      'boundary_ambiguous': len(boundary), 'boundary_examples': boundary[:30]}

    # ============================================================ E6 COSTS
    secs = []
    for path in md_all:
        f = K.rel(path, root)
        if not f.startswith('教材/'):
            continue
        for h in K.headings(K.read_text(path).split('\n')):
            m = re.match(r'^(\d+(?:\.\d+)+)\s*(.*)$', h['text'])
            secs.append({'file': f, 'num': m.group(1) if m else None, 'title': h['text'],
                         'level': h['level']})
    num_secs = [s for s in secs if s['num']]
    skeleton_text = '|'.join((s['num'] or '') + s['title'] for s in secs)
    mvi_ids = mvi
    mvi_read = sum(unit_tokens.get(i, 0) for i in mvi_ids)
    mvi_entry_chars = sum(len(descs.get(i, '')) + len(by_id[i]['name']) for i in mvi_ids if i in by_id)
    proj_index_chars = len(secs) * (14.6 + 40 + 80)
    out['costs'] = {
        'textbook_headings': len(secs), 'numbered_sections': len(num_secs),
        'skeleton_est_tokens': round(K.est_tokens(skeleton_text)),
        'avg_heading_chars': round(sum(len(s['title']) for s in secs) / max(1, len(secs)), 1),
        'chapter03_content_tokens': round(K.est_tokens(K.read_text(
            os.path.join(root, '教材', '03_第3章_模拟信号的数字编码.md')))),
        'mvi_units': len(mvi_ids),
        'mvi_read_tokens_if_all_opened': mvi_read,
        'mvi_entry_tokens': round(K.est_tokens(''.join(
            descs.get(i, '') + by_id[i]['name'] for i in mvi_ids if i in by_id))),
        'mvi_question_coverage': f"{sum(1 for x in mvi_cov if x['covered'])}/{len(mvi_cov)} content+line questions",
        'full_build_read_tokens': book_tokens,
        'projected_full_index_entry_tokens': round(proj_index_chars * 0.4237),
        'token_per_char': 0.4237,
        'assumption': 'build cost model: index writing needs reading each unit once (book tokens) + emitting entries; entry ~= num+title14.6+desc40+anchors80 chars',
    }

    with open(os.path.join(data, 'index-method.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---------------------------------------------------------------- print
    print('# 07 index-method measurements')
    print('\n## E1 ROUTING (13 text questions)')
    print('| variant | hit@1 | hit@3 | top1-wrong | harmful-misroute | zero-score |')
    print('|---|---|---|---|---|---|')
    for r in out['routing']['variants']:
        print(f"| {r['label']} | {r['hit1']}/{r['n']} ({r['hit1_pct']}%) | {r['hit3']}/{r['n']} "
              f"({r['hit3_pct']}%) | {r['wrong_top1_pct']}% | {r['harmful_misroute']} ({r['harmful_misroute_pct']}%) | {r['zero_score_pct']}% |")
    for r in out['routing']['variants']:
        if r['label'].startswith(('V0', 'V6', 'V7')):
            print(f"\n{r['label']} top1:")
            for d in r['detail']:
                print(f"  Q{d['q']:>2} -> {d['top1']} hit1={d['hit1']}")
    print(f"\nMVI: {out['routing']['mvi']['questions_covered']}/{out['routing']['mvi']['questions_total']} questions covered at unit granularity")
    print('\n## E2 CENTRALITY (question-free importance proxy)')
    print(f"- all units: hot in top20% = {out['centrality']['hot_in_top20pct_all']}/{len(HOT_IDS)}")
    print(f"- textbook units only: hot in top20% = {out['centrality']['hot_in_top20pct_textbook']}/{len(HOT_IDS)}")
    print(f"- hot ranks (all units): {[(x['id'], x['rank']) for x in out['centrality']['all_units']]}")
    print(f"- top20 all: {[(x['id'], x['centrality']) for x in out['centrality']['top20_all'][:8]]}")
    print(f"\n## E3 COVERAGE (budget=20% of full book tokens {book_tokens:,} = {budget:,.0f} tok)")
    print('| policy | units | tokens | hot covered |')
    print('|---|---|---|---|')
    for c in cov_tok:
        print(f"| {c['policy']} | {c['units']} | {c['tokens']} | {c['hot_covered']}/{c['hot_total']} ({c['hot_cover_pct']}%) |")
    print(f"\n20% of units ({bud_u}):")
    for c in cov_units:
        print(f"- {c['policy']}: {c['hot_covered']}/{len(hot)} ({c['hot_cover_pct']}%)")
    print(f"\n## E4 BLOCKS: {out['blocks']['total_blocks']} blocks over {out['blocks']['files']} md, "
          f"mean {out['blocks']['mean_blocks_per_file']}/file")
    print(f"- kinds: {kind_tot}")
    print(f"- stability: {json.dumps(stability, ensure_ascii=False)}")
    print('\n## E5 QUALITY')
    print(f"- duplicate-name groups={len(dup)}, units={out['quality']['dup_units']}, low-divergence={out['quality']['dup_low_divergence_groups']}")
    for d in dup[:6]:
        print(f"  {d['n']}x {d['name']} @{d['file']} meanJ={d['mean_jaccard']}")
    print(f"- unit kinds: {dict(kinds)}  (bad={len(bad)})")
    for k in ('formula-only', 'image-only', 'toc-like', 'too-small'):
        ex = [b['name'] for b in bad if b['kind'] == k][:5]
        print(f"  {k}: {kinds.get(k,0)} examples={ex}")
    print(f"- boundary-ambiguous (sibling name jaccard>=0.66): {len(boundary)}")
    print('\n## E6 COSTS')
    for k, v in out['costs'].items():
        print(f"- {k}: {v}")
    print('\nwrote data/index-method.json')


def _cue_score(r):
    t = r['_span_text']
    return sum(t.count(c) for c in DEF_CUES) / max(1, len(t)) * 1000


def _formula_density(r):
    t = r['_span_text']
    return len(re.findall(r'\$|\\[a-zA-Z]+', t)) / max(1, len(t)) * 1000


def _blocks(text):
    parts = re.split(r'\n\s*\n', text)
    out = []
    for p in parts:
        t = p.strip('\n')
        if not t.strip():
            continue
        lines = [l for l in t.split('\n') if l.strip()]
        if re.match(r'^#{1,6}\s', lines[0]):
            kind = 'heading'
        elif all(l.lstrip().startswith('![') for l in lines):
            kind = 'image-only'
        elif re.match(r'^\s*\|', lines[0]):
            kind = 'table'
        elif all(re.search(r'\$|\\[a-zA-Z]', l) and not CJK.search(l) for l in lines):
            kind = 'formula-only'
        elif all(re.match(r'^\s*([-*]|\d+[.、])\s', l) for l in lines):
            kind = 'list'
        else:
            kind = 'prose'
        out.append({'text': t, 'kind': kind})
    return out


def _block_sig(blocks):
    return [b['text'] for b in blocks]


def _block_stability(text):
    import difflib
    base = _block_sig(_blocks(text))
    n = len(base)
    res = {'blocks': n}
    # (a) insert one blank line inside a prose paragraph (splits a block)
    lines = text.split('\n')
    # find a blank line index after a prose block, insert blank before its 3rd line
    idx = None
    for i, l in enumerate(lines):
        if l.strip() and not l.startswith('#') and not l.startswith('!') and i + 3 < len(lines):
            idx = i + 2
            break
    text_a = '\n'.join(lines[:idx] + [''] + lines[idx:])
    a = _block_sig(_blocks(text_a))
    res['insert_blank_line_changed_blocks'] = sum(1 for x in difflib.ndiff(base, a) if x.startswith('- '))
    # (b) delete an existing blank line between two blocks (merges two blocks)
    bi = None
    for i in range(1, len(lines) - 1):
        if not lines[i].strip() and lines[i - 1].strip() and lines[i + 1].strip():
            bi = i
            break
    text_b = '\n'.join(lines[:bi] + lines[bi + 1:])
    b = _block_sig(_blocks(text_b))
    res['delete_blank_line_blocks_before'] = n
    res['delete_blank_line_blocks_after'] = len(b)
    res['delete_blank_line_blocks_destroyed'] = n - len(b) + 1
    # (c) reflow: join wrapped lines inside one paragraph (no blank lines inside)
    res['reflow_note'] = 'wrapped lines are rare in this corpus (paragraphs are single lines)'
    # (d) content edit inside one block
    text_d = text.replace('## 3.3 模拟信号的量化', '## 3.3 模拟信号的量化（改）', 1)
    d = _block_sig(_blocks(text_d))
    res['content_edit_changed_blocks'] = sum(1 for x in difflib.ndiff(base, d) if x.startswith('- '))
    # (e) headings/section paths stable under all of the above?
    res['sections_base'] = len(K.headings(text.split('\n')))
    res['sections_after_insert'] = len(K.headings(text_a.split('\n')))
    res['sections_after_delete'] = len(K.headings(text_b.split('\n')))
    return res


if __name__ == '__main__':
    main()
