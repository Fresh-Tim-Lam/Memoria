# -*- coding: utf-8 -*-
"""05_judge.py — Q2: can a *name* alone decide "should I read this KP?".

Also: Q3 linkage (which KP would each real question need?), and the
"should never be in the index" contamination list.

This script does the MECHANICAL part and emits the sample sheets that the
analyst then judges by hand (judgments live in the proposal, marked as
judgment; the samples are listed so a human can re-check).

Writes data/sample20.json, data/sample10.json, data/judge_metrics.json,
data/non_kp_candidates.json and prints the sample sheets.
Run: python 05_judge.py
"""
import os
import re
import json
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402

SEED = 20261027
GENERIC_NAMES = {
    '目录', '单选题', '多选题', '小结', '本章小结', '引言', '前言', '封面', '附录',
    '参考教程', '参考文献', '习题', '作业', '定义', '定义：', '求解过程', '例题',
    '极限模型', '对称特性', '跳转测试节点',
}
STRUCTURAL_RE = re.compile(r'^(目录|单选题|多选题|小结|本章小结|引言|前言|封面|附录|'
                           r'参考文献|参考教程|习题|作业|练习题|思考题|答案|'
                           r'定义：?|求解过程|例题|【例】?)$')
NUMBERED_RE = re.compile(r'^\d+(\.\d+)*[\s、.]')
OCR_DIRTY_RE = re.compile(r'^([un])\s|※|（续）|\(续\)|续$')
EXAMPLE_RE = re.compile(r'【例】|^例\d*|例题|^\d+\.\s*【例】')
FORMULA_RE = re.compile(r'\$|\\[a-zA-Z]+|\\\(|\\\)')
CJK_RE = K.CJK_RE


def bigrams(s):
    s = ''.join(ch for ch in s if CJK_RE.match(ch) or ch.isalnum())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def name_metrics(rows, text_by_file):
    out = []
    name_counts = {}
    for r in rows:
        name_counts[r['name']] = name_counts.get(r['name'], 0) + 1
    for r in rows:
        text = text_by_file.get(r['file'], '')
        name = r['name'] or ''
        span_text = r.get('_span_text', '')
        nb = bigrams(name)
        sb = bigrams(span_text)
        out.append({
            'kb': r['kb'], 'sidecar': r['sidecar'], 'file': r['file'],
            'id': r['id'], 'name': name,
            'name_chars': len(name), 'name_cjk': len(CJK_RE.findall(name)),
            'name_duplicates_in_kb': name_counts.get(name, 1),
            'name_in_content': (name in text) if text else None,
            'name_in_span': (name in span_text) if span_text else None,
            'name_bigram_recall_by_span': round(len(nb & sb) / len(nb), 3) if nb else None,
            'span_bigram_recall_by_name': round(len(nb & sb) / len(sb), 3) if sb else None,
            'is_structural': bool(STRUCTURAL_RE.match(name)),
            'is_generic': name in GENERIC_NAMES,
            'is_numbered': bool(NUMBERED_RE.match(name)),
            'is_ocr_dirty': bool(OCR_DIRTY_RE.search(name)),
            'is_example': bool(EXAMPLE_RE.search(name)),
            'has_formula': bool(FORMULA_RE.search(name)),
            'starts_with_heading': r['starts_with_heading'],
            'span_chars': r['span_chars'],
            'heading_path': r['heading_path'],
        })
    return out


def span_text_for(root, row, lines):
    s = row['start_found_line'] or row['start_hint'] or 1
    e = row['end_found_line'] or row['end_hint'] or s
    if e < s:
        e = s
    e = min(e, len(lines))
    s = max(1, s)
    return '\n'.join(lines[s - 1:e])


def sample_sheet(rows, k, seed, label, exclude_ids=None):
    rng = random.Random(seed)
    exclude_ids = set(exclude_ids or [])
    pool = [r for r in rows if r['_uid'] not in exclude_ids]
    # stratified by document role
    strata = {'教材': [r for r in pool if r['file'].startswith('教材/')],
              'slides': [r for r in pool if r['file'].startswith('img/')],
              'notes': [r for r in pool if r['file'].startswith('notes/')
                        or r['file'].startswith('homework/')]}
    if label == 'sample10_textbook':
        strata = {'教材': strata['教材']}
        alloc = {'教材': k}
    else:
        alloc = {'教材': 10 if k == 20 else 0, 'slides': 8 if k == 20 else 0,
                 'notes': 2 if k == 20 else 0}
    picked = []
    for s, n in alloc.items():
        if n <= 0:
            continue
        picked += rng.sample(strata[s], min(n, len(strata[s])))
    return picked


def main():
    data = K.ensure_data_dir()
    inv = json.load(open(os.path.join(data, 'kp_inventory.json'), encoding='utf-8'))
    rows = inv['target_kb_rows']
    # attach span text
    for r in rows:
        r['_uid'] = f"{r['sidecar']}::{r['id']}"
    root = K.KB_ROOTS[K.TARGET_KB]
    text_by_file = {}
    lines_by_file = {}
    for r in rows:
        if r['file'] in text_by_file:
            continue
        p = os.path.join(root, *r['file'].split('/'))
        if os.path.isfile(p):
            t = K.read_text(p)
            text_by_file[r['file']] = t
            lines_by_file[r['file']] = t.split('\n')
    for r in rows:
        lines = lines_by_file.get(r['file'], [])
        r['_span_text'] = span_text_for(root, r, lines) if lines else ''

    metrics = name_metrics(rows, text_by_file)
    with open(os.path.join(data, 'judge_metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)

    # ---------------- non-KP candidates
    candidates = []
    for m in metrics:
        reasons = []
        if m['is_structural']:
            reasons.append('structural')
        if m['is_generic']:
            reasons.append('generic')
        if m['is_ocr_dirty']:
            reasons.append('ocr_dirty')
        if m['name_duplicates_in_kb'] > 1:
            reasons.append('duplicate_name')
        if m['name_chars'] <= 2:
            reasons.append('too_short')
        if m['span_chars'] and m['span_chars'] < 50:
            reasons.append('near_empty_span')
        if reasons:
            candidates.append({**{k: m[k] for k in ('sidecar', 'file', 'id', 'name',
                                                     'name_chars', 'span_chars',
                                                     'name_duplicates_in_kb')},
                               'reasons': reasons})
    with open(os.path.join(data, 'non_kp_candidates.json'), 'w', encoding='utf-8') as f:
        json.dump(candidates, f, ensure_ascii=False, indent=1)

    # ---------------- samples
    s20 = sample_sheet(rows, 20, SEED, 'sample20')
    s10 = sample_sheet(rows, 10, SEED + 1, 'sample10_textbook',
                       exclude_ids=[r['_uid'] for r in s20])

    def sheet_rows(picked, tag):
        out = []
        for i, r in enumerate(picked, 1):
            st = r['_span_text']
            out.append({
                'no': i, 'uid': r['_uid'], 'sidecar': r['sidecar'],
                'file': r['file'], 'id': r['id'], 'name': r['name'],
                'heading_path': r['heading_path'],
                'start_line': r['start_found_line'], 'end_line': r['end_found_line'],
                'span_chars': r['span_chars'], 'span_lines': r['span_lines'],
                'start_snippet': r['start_snippet'], 'end_snippet': r['end_snippet'],
                'span_head': st[:260], 'span_tail': st[-120:],
                'est_tokens': round(K.est_tokens(st)),
            })
        return out
    sheet20 = sheet_rows(s20, 'sample20')
    sheet10 = sheet_rows(s10, 'sample10')
    with open(os.path.join(data, 'sample20.json'), 'w', encoding='utf-8') as f:
        json.dump(sheet20, f, ensure_ascii=False, indent=1)
    with open(os.path.join(data, 'sample10.json'), 'w', encoding='utf-8') as f:
        json.dump(sheet10, f, ensure_ascii=False, indent=1)

    # ---------------- question -> KP lexical candidate mapping
    qs = json.load(open(os.path.join(data, 'questions.json'), encoding='utf-8'))
    qmap = []
    for q in qs:
        qb = bigrams(q['text'])
        scored = []
        for r in rows:
            rb = bigrams((r['name'] or '') * 3 + r['_span_text'][:600])
            if not rb:
                continue
            overlap = len(qb & rb)
            scored.append((overlap, r))
        scored.sort(key=lambda x: (-x[0], x[1]['span_chars']))
        top = [{'id': r['id'], 'name': r['name'], 'sidecar': r['sidecar'],
                'score_bigrams': s} for s, r in scored[:3]]
        qmap.append({'no': qs.index(q) + 1, 'question': q['text'], 'top3': top})
    with open(os.path.join(data, 'question_kp_lexical.json'), 'w', encoding='utf-8') as f:
        json.dump(qmap, f, ensure_ascii=False, indent=1)

    # ---------------- print
    n = len(metrics)
    print(f'# 05 judgeability — target KB KP population: {n}')
    print('\n## mechanical name metrics (all %d KPs)' % n)
    print('| metric | count | pct |')
    print('|---|---|---|')
    def cnt(pred):
        return sum(1 for m in metrics if pred(m))
    for label, pred in [
        ('name <= 6 CJK chars', lambda m: m['name_cjk'] <= 6),
        ('name is structural/navigational', lambda m: m['is_structural']),
        ('name is generic placeholder-ish', lambda m: m['is_generic']),
        ('name has OCR artifact', lambda m: m['is_ocr_dirty']),
        ('name is numbered section title', lambda m: m['is_numbered']),
        ('name is an example/exercise', lambda m: m['is_example']),
        ('name contains formula', lambda m: m['has_formula']),
        ('name duplicated within KB', lambda m: m['name_duplicates_in_kb'] > 1),
        ('name not literally present in its own md', lambda m: m['name_in_content'] is False),
        ('name not literally present in its own span', lambda m: m['name_in_span'] is False),
        ('span < 50 chars', lambda m: 0 < m['span_chars'] < 50),
        ('span >= 20000 chars', lambda m: m['span_chars'] >= 20000),
    ]:
        c = cnt(pred)
        print(f'| {label} | {c} | {K.pct(c, n)}% |')
    print(f"- name_chars p50/p90/max = {K.percentile([m['name_chars'] for m in metrics],50)}/"
          f"{K.percentile([m['name_chars'] for m in metrics],90)}/"
          f"{max(m['name_chars'] for m in metrics)}")
    print(f"- name bigram recall by span: p50={K.percentile([m['name_bigram_recall_by_span'] for m in metrics if m['name_bigram_recall_by_span'] is not None],50)}")

    print(f"\n## non-KP candidate list: {len(candidates)} rows (mechanical flags)")
    print('| reasons | name | span chars | sidecar |')
    print('|---|---|---|---|')
    for c in sorted(candidates, key=lambda x: (x['sidecar'], x['no'] if 'no' in x else 0))[:80]:
        print(f"| {','.join(c['reasons'])} | {c['name'][:34]:34s} | {c['span_chars']} | {c['sidecar'].split('/')[-1][:46]} |")

    print('\n## SAMPLE-20 (stratified: 10 教材 / 8 slides / 2 notes) — for manual judging')
    for r in sheet20:
        print(f"\n[{r['no']}] {r['file']} :: line {r['start_line']}-{r['end_line']} ({r['span_chars']} chars, ~{r['est_tokens']} tok)")
        print(f"    name: {r['name']}")
        print(f"    path: {r['heading_path'][:150]}")
        print(f"    head: {r['span_head'][:240].replace(chr(10),' / ')}")
        print(f"    tail: {r['span_tail'][:120].replace(chr(10),' / ')}")

    print('\n## SAMPLE-10 (textbook only, description-template exercise)')
    for r in sheet10:
        print(f"\n[{r['no']}] {r['file']} :: line {r['start_line']}-{r['end_line']} ({r['span_chars']} chars)")
        print(f"    name: {r['name']}  | path: {r['heading_path'][:120]}")
        print(f"    head: {r['span_head'][:220].replace(chr(10),' / ')}")

    print('\n## question -> top-3 KP by lexical bigram overlap')
    for q in qmap:
        tops = '; '.join(f"{t['name'][:24]}({t['score_bigrams']})" for t in q['top3'])
        print(f"{q['no']:>2}. {q['question'][:60]:60s} -> {tops}")
    print('\nwrote data/sample20.json data/sample10.json data/judge_metrics.json '
          'data/non_kp_candidates.json data/question_kp_lexical.json')


if __name__ == '__main__':
    main()
