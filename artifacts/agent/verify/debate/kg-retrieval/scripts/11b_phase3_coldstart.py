# -*- coding: utf-8 -*-
"""11b_phase3_coldstart.py — 修正版冷启动 / 外部可比性证据（配合 11_phase3_objections.py）。

11 号脚本的两处实现缺陷：
  - 冷启动只用了「章标题」（14 条），且 section 路由只覆盖 ch01–03 → 低估
  - D5 读错了快照路径（快照在 kg-retrieval/ 而不是 data/）→ turns=0
本脚本给出：
  D3' 冷启动三档信源的实测：
      (a) 章标题 14 条（~63 tok）
      (b) 全部教材 section 标题（目标库 373 条 ≈2.9k tok；各库相应）
      (c) 无索引基线 = 现有 grep/字面检索（问题 bigram 直接扫全文章节）
      跨库用「问题→同一轮 read_document 章（多数≥60%）」自动标注（n≈150+）
      + 目标库 13 条人工标注（GT=ideal KP range）
  D5' 与 LightRAG/GraphRAG「610k tokens/query」的可比性：读 D 方冻结快照
      phase3-session-snapshot.jsonl（只读），算每轮 prompt / 每轮新上下文。
Run: python 11b_phase3_coldstart.py
"""
import os
import re
import json
import glob
import math
import collections
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402

CH_RE = re.compile(r'教材[/\\](\d+)[_第]')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
HERE = K.ROOT
SNAP = os.path.join(HERE, 'phase3-session-snapshot.jsonl')


def toks(text):
    out = []
    for run in re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]+', text or ''):
        for i in range(len(run) - 1):
            out.append(run[i:i + 2])
    for w in re.findall(r'[A-Za-z0-9_]+', text or ''):
        if len(w) > 1:
            out.append(w.lower())
    return out


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(p, 4), round(max(0, c - h), 4), round(min(1, c + h), 4))


class BM25:
    def __init__(self, docs):
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


# ---------------------------------------------------------------- KB structure
def textbook_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('.memoria', '.git')]
        for fn in filenames:
            if not fn.lower().endswith('.md'):
                continue
            rel = K.rel(os.path.join(dirpath, fn), root)
            if not rel.startswith('教材/') or 'pipeline_old' in rel:
                continue
            m = CH_RE.search(rel)
            if m:
                out.append((int(m.group(1)), rel, os.path.join(dirpath, fn)))
    return sorted(out)


def kb_structure(root):
    """Return chapters: {ch: {'title','text','sections':[(line,title)]}}"""
    chapters = {}
    for ch, rel, path in textbook_files(root):
        text = K.read_text(path)
        lines = text.split('\n')
        hs = [{'line': i, 'level': len(m.group(1)), 'text': m.group(2).strip()}
              for i, l in enumerate(lines, 1) for m in [HEADING_RE.match(l)] if m]
        title = re.sub(r'^\d+[_第]', '', os.path.basename(path)[:-3])
        chapters[ch] = {'title': title, 'text': text, 'lines': lines, 'headings': hs}
    return chapters


def chapter_titles(chapters):
    return sorted((ch, v['title']) for ch, v in chapters.items())


def all_sections(chapters):
    """[(ch, title, start, end)] across the whole book."""
    out = []
    for ch, v in chapters.items():
        hs = v['headings']
        for i, h in enumerate(hs):
            end = hs[i + 1]['line'] - 1 if i + 1 < len(hs) else len(v['lines'])
            out.append((ch, h['text'], h['line'], end))
    return out


# ---------------------------------------------------------------- session labels
def parse_events(path):
    ev = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ev.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return ev


def labelled_turns(path):
    calls, turns, cur_q, cur = {}, [], None, []
    for e in parse_events(path):
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
                    cur.append(int(m.group(1)))
        elif t == 'loop/end':
            if cur_q and cur:
                cnt = collections.Counter(cur)
                ch, n = cnt.most_common(1)[0]
                if n / len(cur) >= 0.6:
                    turns.append((cur_q, ch))
            cur_q, cur = None, []
    return turns


def grep_rank(q, chapters):
    """No-index baseline: rank chapters by share of question bigrams found in text."""
    qb = set(toks(q))
    if not qb:
        return []
    scored = []
    for ch, v in chapters.items():
        tb = set(toks(v['text']))
        scored.append((len(qb & tb) / len(qb), ch))
    scored.sort(reverse=True)
    return [ch for _, ch in scored]


# ---------------------------------------------------------------- D3
def d3(data):
    out = {}
    # (a) target KB: 20 questions, GT = ch3 (all 19 old + new formula question still ch3);
    #     plus manually derived: only questions 1..19 known; q20 also ch3 by content.
    qs = json.load(open(os.path.join(data, 'questions.json'), encoding='utf-8'))
    tgt_root = K.KB_ROOTS[K.TARGET_KB]
    tgt = kb_structure(tgt_root)
    titles = chapter_titles(tgt)
    bm_ct = BM25([toks(t) for _, t in titles])
    secs = all_sections(tgt)
    bm_sec = BM25([toks(s[1]) for s in secs])
    qt = [q['text'] for q in qs]
    ct_h1 = ct_h3 = sec_h1 = sec_h3 = gr_h1 = gr_h3 = 0
    for q in qt:
        gt = 3
        r = bm_ct.rank(q, 3)
        top = [titles[i][0] for _, i in r]
        ct_h1 += bool(top) and top[0] == gt
        ct_h3 += gt in top
        r = bm_sec.rank(q, 3)
        top = [secs[i][0] for _, i in r]
        sec_h1 += bool(top) and top[0] == gt
        sec_h3 += gt in top
        g = grep_rank(q, tgt)
        gr_h1 += bool(g) and g[0] == gt
        gr_h3 += gt in g[:3]
    n = len(qt)
    out['target_20q_gt_ch3'] = {
        'n': n,
        'chapter_titles': {'entries': len(titles), 'tokens': round(K.est_tokens(''.join(t for _, t in titles))),
                           'hit1': ct_h1, 'hit3': ct_h3, 'hit1_pct': K.pct(ct_h1, n),
                           'hit3_pct': K.pct(ct_h3, n), 'hit1_wilson': wilson(ct_h1, n)},
        'section_titles': {'entries': len(secs), 'tokens': round(K.est_tokens(''.join(s[1] for s in secs))),
                           'hit1': sec_h1, 'hit3': sec_h3, 'hit1_pct': K.pct(sec_h1, n),
                           'hit3_pct': K.pct(sec_h3, n), 'hit1_wilson': wilson(sec_h1, n)},
        'grep_no_index': {'hit1': gr_h1, 'hit3': gr_h3, 'hit1_pct': K.pct(gr_h1, n),
                          'hit3_pct': K.pct(gr_h3, n), 'hit1_wilson': wilson(gr_h1, n)},
    }
    # (b) target KB: 13 manual questions vs ideal KP ranges, section-title index only
    inv = json.load(open(os.path.join(data, 'kp_inventory.json'), encoding='utf-8'))
    by_id = {r['id']: r for r in inv['target_kb_rows']}
    gt13 = {1: ['quantization-overview', 'scalar-quantization'],
            3: ['aliasing', 'quantization-overview', 'uniform-quantization'],
            4: ['uniform-quantization', 'nonuniform-quantization'], 5: ['pcm'],
            6: ['aliasing', 'uniform-quantization', 'nonuniform-quantization'],
            8: ['pcm', 'a-law-mu-law-pcm', 'pcm-coding-methods'],
            9: ['aliasing', 'ideal-sampling'], 10: ['bandpass-sampling'],
            11: ['bandpass-sampling'], 12: ['bandpass-sampling'],
            16: ['uniform-quantization'],
            18: ['nonuniform-quantization', 'logarithmic-quantization'],
            19: ['quantization-overview', 'uniform-quantization']}
    h1 = h3 = 0
    for qno, ids in gt13.items():
        q = qt[qno - 1]
        r = bm_sec.rank(q, 3)
        ok1 = ok3 = False
        for ri, (_, idx) in enumerate(r):
            ch, title, s, e = secs[idx]
            inter = False
            for kid in ids:
                kr = by_id.get(kid)
                if not kr:
                    continue
                ks = kr['start_found_line'] or kr['start_hint'] or 1
                ke = kr['end_found_line'] or kr['end_hint'] or ks
                if ke < ks:
                    ke = ks
                if kr['file'].startswith('教材/03') and ch == 3 and not (e < ks or s > ke):
                    inter = True
            if inter:
                ok1 = ok1 or ri == 0
                ok3 = True
                break
        h1 += ok1
        h3 += ok3
    out['target_13q_section_vs_ideal'] = {'n': len(gt13), 'hit1': h1, 'hit3': h3,
                                          'hit1_pct': K.pct(h1, len(gt13)),
                                          'hit3_pct': K.pct(h3, len(gt13))}

    # (c) cross-KB: session-derived labels; chapter-title vs section-title vs grep
    cross = {}
    for kb, root in K.KB_ROOTS.items():
        sess = sorted(glob.glob(os.path.join(root, '.memoria', 'agent', 'sessions', '*.jsonl')))
        labels = []
        for p in sess:
            labels += labelled_turns(p)
        chapters = kb_structure(root)
        if not labels or not chapters:
            cross[kb] = {'labelled': len(labels), 'chapters': len(chapters)}
            continue
        ttl = chapter_titles(chapters)
        bct = BM25([toks(t) for _, t in ttl])
        sec = all_sections(chapters)
        bsec = BM25([toks(s[1]) for s in sec])
        a1 = a3 = b1 = b3 = c1 = c3 = 0
        for q, gt in labels:
            r = bct.rank(q, 3)
            top = [ttl[i][0] for _, i in r]
            a1 += bool(top) and top[0] == gt
            a3 += gt in top
            r = bsec.rank(q, 3)
            top = [sec[i][0] for _, i in r]
            b1 += bool(top) and top[0] == gt
            b3 += gt in top
            g = grep_rank(q, chapters)
            c1 += bool(g) and g[0] == gt
            c3 += gt in g[:3]
        n = len(labels)
        cross[kb] = {
            'labelled': n, 'chapters': len(chapters),
            'chapter_titles': {'entries': len(ttl), 'tokens': round(K.est_tokens(''.join(t for _, t in ttl))),
                               'hit1': a1, 'hit3': a3, 'hit1_pct': K.pct(a1, n), 'hit3_pct': K.pct(a3, n),
                               'hit1_wilson': wilson(a1, n)},
            'section_titles': {'entries': len(sec), 'tokens': round(K.est_tokens(''.join(s[1] for s in sec))),
                               'hit1': b1, 'hit3': b3, 'hit1_pct': K.pct(b1, n), 'hit3_pct': K.pct(b3, n),
                               'hit1_wilson': wilson(b1, n)},
            'grep_no_index': {'hit1': c1, 'hit3': c3, 'hit1_pct': K.pct(c1, n), 'hit3_pct': K.pct(c3, n),
                              'hit1_wilson': wilson(c1, n)},
        }
    tot = sum(v.get('labelled', 0) for v in cross.values())
    out['cross_kb'] = cross
    out['cross_kb_total'] = {
        'labelled': tot,
        'chapter_titles_hit1': sum(v.get('chapter_titles', {}).get('hit1', 0) for v in cross.values()),
        'section_titles_hit1': sum(v.get('section_titles', {}).get('hit1', 0) for v in cross.values()),
        'section_titles_hit3': sum(v.get('section_titles', {}).get('hit3', 0) for v in cross.values()),
        'grep_hit1': sum(v.get('grep_no_index', {}).get('hit1', 0) for v in cross.values()),
        'grep_hit3': sum(v.get('grep_no_index', {}).get('hit3', 0) for v in cross.values()),
        'grep_hit1_wilson': wilson(sum(v.get('grep_no_index', {}).get('hit1', 0) for v in cross.values()), tot),
    }
    return out


# ---------------------------------------------------------------- D5
def d5():
    turns = prompt = miss = comp = peak = 0
    if os.path.isfile(SNAP):
        for e in parse_events(SNAP):
            if e.get('type') == 'loop/end':
                u = (e.get('data') or {}).get('usage') or {}
                turns += 1
                prompt += u.get('prompt_tokens') or 0
                miss += u.get('cache_miss_tokens') or 0
                comp += u.get('completion_tokens') or 0
                peak = max(peak, u.get('prompt_tokens') or 0)
    return {
        'snapshot': os.path.basename(SNAP), 'turns': turns,
        'prompt_total': prompt, 'cache_miss_total': miss, 'completion_total': comp,
        'prompt_peak': peak,
        'prompt_per_turn': round(prompt / turns) if turns else None,
        'new_context_per_turn': round(miss / turns) if turns else None,
        'lightrag_graphrag_legal_tokens_per_query': 610000,
        'legal_corpus_tokens': 5081069,
        'our_corpus_tokens': 606726,
        'ratio_ours_prompt_vs_610k': round(610000 / (prompt / turns), 2) if turns else None,
        'ratio_ours_newctx_vs_610k': round(610000 / (miss / turns), 1) if turns else None,
        'question_concentration': '19/19 旧问题 + 第20问均落 ch03；read_document 39/40=97.5% 同章',
        'corpus_size_ratio_legal_vs_ours': round(5081069 / 606726, 2),
    }


def main():
    data = K.ensure_data_dir()
    out = {'D3_coldstart': d3(data), 'D5_external': d5()}
    with open(os.path.join(data, 'phase3-coldstart.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print('# 11b cold-start & external comparability')
    print('\n## D3 目标库：20 问（GT=ch3）× 三种冷启动信源')
    t = out['D3_coldstart']['target_20q_gt_ch3']
    for name, key in [('章标题', 'chapter_titles'), ('section 标题', 'section_titles'),
                      ('grep 无索引', 'grep_no_index')]:
        s = t[key]
        tok = s.get('tokens')
        extra = f", {s['entries']} 条, {tok} tok" if tok is not None else ', 0 tok'
        print(f"- {name}{extra}: hit@1 {s['hit1']}/{t['n']} ({s['hit1_pct']}%), "
              f"hit@3 {s['hit3_pct']}%, Wilson95={s.get('hit1_wilson')}")
    s = out['D3_coldstart']['target_13q_section_vs_ideal']
    print(f"- 目标库 13 条人工标注 × section 标题: hit@1 {s['hit1_pct']}%, hit@3 {s['hit3_pct']}%")
    print('\n## D3 跨库（问题→同轮 read_document 章，多数≥60% 才标注）')
    print('| KB | labelled | chapter titles hit@1 | section titles hit@1/@3 | grep hit@1/@3 |')
    print('|---|---|---|---|---|')
    for kb, v in out['D3_coldstart']['cross_kb'].items():
        if 'chapter_titles' not in v:
            print(f"| {kb} | {v.get('labelled')} | - | - | - |")
            continue
        print(f"| {kb} | {v['labelled']} | {v['chapter_titles']['hit1_pct']}% | "
              f"{v['section_titles']['hit1_pct']}% / {v['section_titles']['hit3_pct']}% | "
              f"{v['grep_no_index']['hit1_pct']}% / {v['grep_no_index']['hit3_pct']}% |")
    print(f"\n- cross-KB total: {out['D3_coldstart']['cross_kb_total']}")
    print('\n## D5 外部可比性')
    for k, v in out['D5_external'].items():
        print(f"- {k}: {v}")
    print('\nwrote data/phase3-coldstart.json')


if __name__ == '__main__':
    main()
