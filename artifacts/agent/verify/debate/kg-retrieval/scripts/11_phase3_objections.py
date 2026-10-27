# -*- coding: utf-8 -*-
"""11_phase3_objections.py — Phase 3 交叉异议的证据计算。

回答三个防守点 + 两个攻击点的量化部分：
  D1 O-B3 : KP span 的三种口径（end.line_hint / 已解析 snippet / 下一同级标题）
             × 三个人群（全部 / 教材 / slides），并给 todo-owner 的 hybrid 口径。
  D2 O2-A : 块身份的精确定义所需的实测 —— 内容 hash 是否唯一（重复块）、
            插入 40 行后 hash 保留率 vs offset 平移率。
  D3 O2-C : 冷启动是否有死结 —— 章节标题（14 条，~85 tok）能否把真实问题路由到正确章；
            用 4 个真实 KB 的会话做「问题→同轮 read_document 章」自动标注（n≈数百），
            再用 373 个 section 标题做目标库的 section 级路由。
  D4 攻击B: M1/M3 小样本阈值的 Wilson 置信区间与所需样本量（含归属订正：
            metrics-baseline 的 M1=答对率 / M3=峰值 prompt；≥70%/≥85% 是语料 R9 指标）。
  D5 攻击A: GraphRAG 610k/query 与我们的可比性 —— 语料规模、单轮新上下文、问题集中度。

只读 D:\\AAA_Courses；输出 data/phase3-objections.json。
Run: python 11_phase3_objections.py
"""
import os
import re
import json
import math
import glob
import collections
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402

CH_RE = re.compile(r'教材[/\\](\d+)[_第]')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')


# ------------------------------------------------------------------ helpers
def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(p, 4), round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def toks(text):
    out = []
    for run in re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]+', text or ''):
        for i in range(len(run) - 1):
            out.append(run[i:i + 2])
    for w in re.findall(r'[A-Za-z0-9_]+', text or ''):
        if len(w) > 1:
            out.append(w.lower())
    return out


class BM25:
    def __init__(self, docs):
        self.docs = docs
        self.N = len(docs)
        self.tf = [collections.Counter(d) for d in docs]
        self.dl = [len(d) for d in docs]
        self.df = collections.Counter()
        for d in docs:
            for t in set(d):
                self.df[t] += 1
        self.avgdl = sum(self.dl) / self.N if self.N else 1

    def rank(self, q, k=3):
        qc = collections.Counter(toks(q))
        res = []
        for i in range(self.N):
            s = 0.0
            for t, qn in qc.items():
                f = self.tf[i].get(t)
                if not f:
                    continue
                idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * (self.dl[i] or 1) / self.avgdl)) * qn
            if s > 0:
                res.append((s, i))
        res.sort(key=lambda x: (-x[0], x[1]))
        return res[:k]


def line_chars(lines, a, b):
    a = max(1, a)
    b = min(b, len(lines))
    if b < a:
        return 0
    seg = lines[a - 1:b]
    return sum(len(x) for x in seg) + max(0, len(seg) - 1)


# ------------------------------------------------------------------ D1
def d1_span_calib(data):
    inv = json.load(open(os.path.join(data, 'kp_inventory.json'), encoding='utf-8'))
    rows = inv['target_kb_rows']
    root = K.KB_ROOTS[K.TARGET_KB]
    lines_cache = {}
    for r in rows:
        f = r['file']
        if f not in lines_cache:
            p = os.path.join(root, *f.split('/'))
            lines_cache[f] = K.read_text(p).split('\n') if os.path.isfile(p) else []
    out_rows = []
    for r in rows:
        lines = lines_cache.get(r['file'], [])
        hs = K.headings(lines)
        start_resolved = r['start_found_line'] or r['start_hint'] or 1
        # next heading with level <= level of the heading that owns the start line
        owner = None
        for h in hs:
            if h['line'] <= start_resolved:
                owner = h
            else:
                break
        own_level = owner['level'] if owner else 1
        nxt = None
        for h in hs:
            if h['line'] > start_resolved and h['level'] <= own_level:
                nxt = h['line']
                break
        end_heading = (nxt - 1) if nxt else len(lines)

        hint_start = r['start_hint'] or 1
        hint_end = r['end_hint'] or hint_start
        # hybrid per todo-owner O-B3 proposal
        if hint_end >= hint_start:
            hybrid_end = min(hint_end, end_heading)
        else:
            hybrid_end = end_heading
        out_rows.append({
            'id': r['id'], 'file': r['file'],
            'role': '教材' if r['file'].startswith('教材/') else ('slides' if r['file'].startswith('img/') else 'notes'),
            'span_hint': line_chars(lines, hint_start, hint_end),
            'span_resolved': line_chars(lines, start_resolved, r['end_found_line'] or hint_end),
            'span_heading': line_chars(lines, start_resolved, end_heading),
            'span_hybrid': line_chars(lines, hint_start, hybrid_end),
            'resolved_end': r['end_found_line'], 'hint_end': r['end_hint'],
            'inverted': bool((r['end_found_line'] or 0) and (r['end_found_line'] or 0) < start_resolved),
        })

    def stats(vals):
        vals = [v for v in vals if v > 0]
        if not vals:
            return {}
        p = lambda x: round(K.percentile(vals, x), 1)
        return {'n': len(vals), 'p50': p(50), 'p90': p(90), 'max': max(vals),
                'min': min(vals),
                'lt200': K.pct(sum(1 for v in vals if v < 200), len(vals)),
                'lt800': K.pct(sum(1 for v in vals if v < 800), len(vals)),
                'gt1200': K.pct(sum(1 for v in vals if v > 1200), len(vals)),
                'gt3000': K.pct(sum(1 for v in vals if v > 3000), len(vals))}

    res = {'by_method_by_role': {}, 'n_kps': len(out_rows),
           'inverted': sum(1 for x in out_rows if x['inverted'])}
    for role in ('全部', '教材', 'slides', 'notes'):
        rs = out_rows if role == '全部' else [x for x in out_rows if x['role'] == role]
        res['by_method_by_role'][role] = {
            m: stats([x['span_' + m] for x in rs])
            for m in ('hint', 'resolved', 'heading', 'hybrid')
        }
    res['rows'] = out_rows
    return res


# ------------------------------------------------------------------ D2
def d2_blocks(data):
    root = K.KB_ROOTS[K.TARGET_KB]
    import hashlib
    per_file = []
    total = uniq = 0
    dup_examples = collections.Counter()
    for p in K.md_files(root):
        rel = K.rel(p, root)
        text = K.read_text(p)
        parts = [x.strip('\n') for x in re.split(r'\n\s*\n', text)]
        blocks = []
        for part in parts:
            norm = re.sub(r'\s+', ' ', part).strip()
            if not norm:
                continue
            h = hashlib.sha256(norm.encode('utf-8')).hexdigest()[:16]
            blocks.append((h, norm))
        hs = [b[0] for b in blocks]
        total += len(hs)
        uniq += len(set(hs))
        c = collections.Counter(hs)
        for h, n in c.items():
            if n > 1:
                norm = next(b[1] for b in blocks if b[0] == h)
                dup_examples[norm[:60]] += n
        per_file.append({'file': rel, 'blocks': len(hs), 'unique': len(set(hs))})
    # insertion simulation: insert 40 lines at a random position in ch03
    p = os.path.join(root, '教材', '03_第3章_模拟信号的数字编码.md')
    text = K.read_text(p)
    base = [hashlib.sha256(re.sub(r'\s+', ' ', b).strip().encode('utf-8')).hexdigest()[:16]
            for b in re.split(r'\n\s*\n', text) if b.strip()]
    lines = text.split('\n')
    pos = 1200
    new_text = '\n'.join(lines[:pos] + ['插入测试行 %d' % i for i in range(40)] + lines[pos:])
    new = [hashlib.sha256(re.sub(r'\s+', ' ', b).strip().encode('utf-8')).hexdigest()[:16]
           for b in re.split(r'\n\s*\n', new_text) if b.strip()]
    retained = len(set(base) & set(new))
    return {
        'total_blocks': total, 'unique_hashes': uniq,
        'duplicate_hash_rate_pct': K.pct(total - uniq, total),
        'files': per_file,
        'top_duplicate_contents': [{'text': t, 'count': n} for t, n in dup_examples.most_common(15)],
        'insertion_sim': {
            'file': '教材/03_第3章_模拟信号的数字编码.md',
            'blocks_before': len(base), 'blocks_after': len(new),
            'identical_hash_retained': retained,
            'retained_pct': K.pct(retained, len(base)),
            'note': 'identity(hash) 不变；但被插行之后的所有块 offset 整体 +40 行',
        },
        'definition': {
            'identity': 'sha256(file_rel + normalized_block_text) — 用于 stale/dedup/cache',
            'location': '(file_rel, start_char_offset, end_char_offset) — 每次 build 重算，用于读取',
            'anchor': 'section_number + block ordinal_in_section + content_hash — 用于跨 build 重定位',
            'why_composite': 'content hash 会重复（见 duplicate_hash_rate），单 hash 不足以唯一定位',
        },
    }


# ------------------------------------------------------------------ D3
def parse_session_events(path):
    events = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def turns_with_reads(path):
    """Return [(question_text_or_None, [chapter,...])] per loop/end turn."""
    calls = {}
    turns = []
    cur_q = None
    cur_reads = []
    for e in parse_session_events(path):
        t = e.get('type')
        d = e.get('data') or {}
        if t == 'user/message':
            cur_q = (d.get('text') or '').strip()
        elif t == 'tool/call':
            calls[d.get('id')] = d
        elif t == 'tool/result':
            c = calls.get(d.get('id')) or {}
            if (d.get('name') or c.get('name')) == 'read_document':
                try:
                    args = json.loads(c.get('arguments') or '{}')
                except json.JSONDecodeError:
                    args = {}
                m = CH_RE.search(args.get('path') or '')
                if m:
                    cur_reads.append(int(m.group(1)))
        elif t == 'loop/end':
            if cur_q:
                turns.append((cur_q, list(cur_reads)))
            cur_q = None
            cur_reads = []
    return turns


def chapter_titles(root):
    """[(chapter_no, title)] from textbook file names."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x not in ('.memoria', '.git')]
        for fn in filenames:
            if not fn.lower().endswith('.md'):
                continue
            rel = K.rel(os.path.join(dirpath, fn), root)
            if not rel.startswith('教材/') or 'pipeline_old' in rel:
                continue
            m = CH_RE.search(rel)
            if not m:
                continue
            title = re.sub(r'^\d+[_第]', '', fn[:-3])
            out.append((int(m.group(1)), title))
    return sorted(set(out))


def d3_coldstart(data):
    root = K.KB_ROOTS[K.TARGET_KB]
    # (a) chapter-title routing on the 19 real questions (ground truth = ch3)
    qs = json.load(open(os.path.join(data, 'questions.json'), encoding='utf-8'))
    titles = chapter_titles(root)
    bm = BM25([toks(t) for _, t in titles])
    hits1 = hits3 = 0
    per_q = []
    for q in qs:
        r = bm.rank(q['text'], 3)
        top = [titles[i][0] for _, i in r]
        h1 = bool(top) and top[0] == 3
        h3 = 3 in top
        hits1 += h1
        hits3 += h3
        per_q.append({'q': q['text'][:40], 'top': top, 'hit1': h1})
    chapter_cost_tokens = round(K.est_tokens(''.join(t for _, t in titles)))

    # (b) section-heading routing on the target KB: 13 text questions, GT = ideal KP spans
    inv = json.load(open(os.path.join(data, 'kp_inventory.json'), encoding='utf-8'))
    rows = inv['target_kb_rows']
    ch03 = [r for r in rows if r['file'].startswith('教材/03')]
    gt = {
        1: ['quantization-overview', 'scalar-quantization'],
        3: ['aliasing', 'quantization-overview', 'uniform-quantization'],
        4: ['uniform-quantization', 'nonuniform-quantization'],
        5: ['pcm'],
        6: ['aliasing', 'uniform-quantization', 'nonuniform-quantization'],
        8: ['pcm', 'a-law-mu-law-pcm', 'pcm-coding-methods'],
        9: ['aliasing', 'ideal-sampling'],
        10: ['bandpass-sampling'], 11: ['bandpass-sampling'], 12: ['bandpass-sampling'],
        16: ['uniform-quantization'], 18: ['nonuniform-quantization', 'logarithmic-quantization'],
        19: ['quantization-overview', 'uniform-quantization'],
    }
    by_id = {r['id']: r for r in rows}
    sec_entries = []   # (file, start_line, end_line, text)
    for f in ('教材/01_第1章_绪论.md', '教材/02_第2章_信号分析基础.md',
              '教材/03_第3章_模拟信号的数字编码.md'):
        p = os.path.join(root, *f.split('/'))
        lines = K.read_text(p).split('\n')
        hs = K.headings(lines)
        for i, h in enumerate(hs):
            end = hs[i + 1]['line'] - 1 if i + 1 < len(hs) else len(lines)
            sec_entries.append((f, h['line'], end, h['text']))
    bm2 = BM25([toks(t) for _, _, _, t in sec_entries])
    h1 = h3 = 0
    for qno, ids in gt.items():
        q = next(x['text'] for x in qs if x['text'] == next(
            t for t in [qq['text'] for qq in qs] if True) ) if False else None
        # rebuild query from GROUND_TRUTH table in 07 via questions.json order
    # use questions.json in order: the 13 content questions are indexes 1,3,4,5,6,8,9,10,11,12,16,18,19 (1-based)
    qtexts = [qq['text'] for qq in qs]
    for qno, ids in gt.items():
        q = qtexts[qno - 1]
        r = bm2.rank(q, 3)
        # hit if any top-3 section range overlaps any ideal KP resolved span
        ok1 = ok3 = False
        for rank_i, (_, idx) in enumerate(r):
            f, s, e, _ = sec_entries[idx]
            inter = False
            for kid in ids:
                kr = by_id.get(kid)
                if not kr or kr['file'] != f:
                    continue
                ks = kr['start_found_line'] or kr['start_hint'] or 1
                ke = kr['end_found_line'] or kr['end_hint'] or ks
                if ke < ks:
                    ke = ks
                if not (e < ks or s > ke):
                    inter = True
            if inter:
                if rank_i == 0:
                    ok1 = True
                ok3 = True
                break
        h1 += ok1
        h3 += ok3
    n_sec_q = len(gt)

    # (c) cross-KB: session-derived labels (question -> chapter read in the same turn)
    cross = {}
    for kb, kbroot in K.KB_ROOTS.items():
        sess = sorted(glob.glob(os.path.join(kbroot, '.memoria', 'agent', 'sessions', '*.jsonl')))
        if not sess:
            continue
        turns = []
        for p in sess:
            turns += turns_with_reads(p)
        labelled = []
        for q, reads in turns:
            if not reads:
                continue
            c = collections.Counter(reads)
            top_ch, cnt = c.most_common(1)[0]
            if cnt / len(reads) >= 0.6:      # clear majority -> usable label
                labelled.append((q, top_ch))
        titles_kb = chapter_titles(kbroot)
        if not titles_kb or not labelled:
            cross[kb] = {'labelled_questions': len(labelled), 'note': 'no labels/chapters'}
            continue
        bmk = BM25([toks(t) for _, t in titles_kb])
        id2ch = {i: ch for i, (ch, _) in enumerate(titles_kb)}
        k1 = k3 = 0
        for q, gt_ch in labelled:
            r = bmk.rank(q, 3)
            top = [id2ch[i] for _, i in r]
            k1 += bool(top) and top[0] == gt_ch
            k3 += gt_ch in top
        cross[kb] = {'labelled_questions': len(labelled),
                     'hit1': k1, 'hit3': k3,
                     'hit1_wilson': wilson(k1, len(labelled)),
                     'chapters': len(titles_kb),
                     'chapter_label_tokens': round(K.est_tokens(''.join(t for _, t in titles_kb)))}
    total_lab = sum(v.get('labelled_questions', 0) for v in cross.values())
    total_h1 = sum(v.get('hit1', 0) for v in cross.values())
    return {
        'target_19_questions_chapter_routing': {
            'entries': len(titles), 'entry_tokens': chapter_cost_tokens,
            'hit1': hits1, 'hit3': hits3, 'n': len(qs),
            'hit1_pct': K.pct(hits1, len(qs)), 'hit3_pct': K.pct(hits3, len(qs)),
            'hit1_wilson': wilson(hits1, len(qs)),
        },
        'target_13_questions_section_routing': {
            'entries': len(sec_entries),
            'entry_tokens': round(K.est_tokens(''.join(t for *_, t in sec_entries))),
            'hit1': h1, 'hit3': h3, 'n': n_sec_q,
            'hit1_pct': K.pct(h1, n_sec_q), 'hit3_pct': K.pct(h3, n_sec_q),
        },
        'cross_kb_session_labels': cross,
        'cross_kb_total': {'labelled': total_lab, 'hit1': total_h1,
                           'hit1_pct': K.pct(total_h1, total_lab),
                           'hit1_wilson': wilson(total_h1, total_lab)} if total_lab else {},
    }


# ------------------------------------------------------------------ D4
def d4_sample_power(data):
    obs = []
    for label, k, n in [('M1 hit@3 name-only', 7, 13),
                        ('M1 hit@3 +问句型desc', 10, 13),
                        ('M3 A-class (可判)', 9, 20),
                        ('M3 C-class (判错)', 0, 20)]:
        p, lo, hi = wilson(k, n)
        obs.append({'metric': label, 'k': k, 'n': n, 'p': p, 'wilson95': [lo, hi]})
    # required n for CI lower bound >= threshold given point estimate p
    def need_n(p, target, z=1.96):
        for n in range(5, 5001):
            if wilson(round(p * n), n, z)[1] >= target:
                return n
        return None
    need = {
        'hit@3 p=0.769 CI_low>=0.70': need_n(0.769, 0.70),
        'hit@3 p=0.538 CI_low>=0.70': need_n(0.538, 0.70),
        'decidability p=0.85 CI_low>=0.80': need_n(0.85, 0.80),
    }
    return {'observed': obs, 'required_n': need,
            'note': 'M1/M3 的两组阈值（≥70%/≥85%）来自语料 R9；metrics-baseline 的 M1=答对率、M3=峰值 prompt，两者不是同一指标'}


# ------------------------------------------------------------------ D5
def d5_external(data):
    snap_path = os.path.join(data, 'phase3-session-snapshot.jsonl')
    turns = prompts = miss = completion = 0
    peak = 0
    if os.path.isfile(snap_path):
        for e in parse_session_events(snap_path):
            if e.get('type') == 'loop/end':
                u = (e.get('data') or {}).get('usage') or {}
                turns += 1
                prompts += u.get('prompt_tokens') or 0
                miss += u.get('cache_miss_tokens') or 0
                completion += u.get('completion_tokens') or 0
                peak = max(peak, u.get('prompt_tokens') or 0)
    return {
        'source': 'phase3-session-snapshot.jsonl（D 方冻结快照，本脚本只读）',
        'turns': turns, 'prompt_total': prompts, 'cache_miss_total': miss,
        'completion_total': completion, 'prompt_peak': peak,
        'prompt_per_turn': round(prompts / turns) if turns else None,
        'new_context_per_turn': round(miss / turns) if turns else None,
        'lightrag_graphrag_legal_tokens_per_query': 610000,
        'legal_corpus_tokens': 5081069,
        'our_corpus_tokens': 606726,
        'ratio_prompt_per_turn_vs_610k': round(610000 / (prompts / turns), 2) if turns else None,
        'ratio_new_context_vs_610k': round(610000 / (miss / turns), 1) if turns else None,
        'question_concentration': '19/19 问题落 ch03（read_document 39/40=97.5% 同章）',
    }


def main():
    data = K.ensure_data_dir()
    out = {}
    out['D1_span_calib'] = d1_span_calib(data)
    out['D2_blocks'] = d2_blocks(data)
    out['D3_coldstart'] = d3_coldstart(data)
    out['D4_sample_power'] = d4_sample_power(data)
    out['D5_external'] = d5_external(data)
    with open(os.path.join(data, 'phase3-objections.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---- print
    print('# 11 Phase3 objections evidence')
    print('\n## D1 KP span 三口径 × 三人群')
    print('| role | method | n | p50 | p90 | max | <200 | <800 | >1200 | >3000 |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for role, d in out['D1_span_calib']['by_method_by_role'].items():
        for m, s in d.items():
            print(f"| {role} | {m} | {s.get('n')} | {s.get('p50')} | {s.get('p90')} | {s.get('max')} | "
                  f"{s.get('lt200')}% | {s.get('lt800')}% | {s.get('gt1200')}% | {s.get('gt3000')}% |")
    print(f"- inverted ranges: {out['D1_span_calib']['inverted']}")

    b = out['D2_blocks']
    print(f"\n## D2 块身份: blocks={b['total_blocks']}, unique hashes={b['unique_hashes']}, "
          f"duplicate-hash rate={b['duplicate_hash_rate_pct']}%")
    print(f"- insertion sim: {b['insertion_sim']}")
    print(f"- top duplicate contents: {[x['text'][:20] for x in b['top_duplicate_contents'][:6]]}")

    c = out['D3_coldstart']
    t = c['target_19_questions_chapter_routing']
    print(f"\n## D3 冷启动")
    print(f"- 章标题路由（{t['entries']} 条章节标题 = {t['entry_tokens']} tok）: "
          f"19 问 → hit@1 {t['hit1']}/{t['n']} ({t['hit1_pct']}%), hit@3 {t['hit3_pct']}%, "
          f"Wilson95={t['hit1_wilson']}")
    s = c['target_13_questions_section_routing']
    print(f"- section 标题路由（{s['entries']} 条标题 = {s['entry_tokens']} tok）: 13 问 → "
          f"hit@1 {s['hit1']}/{s['n']} ({s['hit1_pct']}%), hit@3 {s['hit3_pct']}%")
    for kb, v in c['cross_kb_session_labels'].items():
        print(f"- {kb}: labelled={v.get('labelled_questions')} hit@1={v.get('hit1')} "
              f"({v.get('hit1_pct') if 'hit1_pct' in v else '-'}%) wilson={v.get('hit1_wilson')}")
    print(f"- cross-KB total: {c['cross_kb_total']}")

    p = out['D4_sample_power']
    print('\n## D4 小样本阈值')
    for o in p['observed']:
        print(f"- {o['metric']}: {o['k']}/{o['n']} = {o['p']}  Wilson95={o['wilson95']}")
    print(f"- required n: {p['required_n']}")

    e = out['D5_external']
    print('\n## D5 外部可比性')
    for k, v in e.items():
        print(f"- {k}: {v}")
    print('\nwrote data/phase3-objections.json')


if __name__ == '__main__':
    main()
