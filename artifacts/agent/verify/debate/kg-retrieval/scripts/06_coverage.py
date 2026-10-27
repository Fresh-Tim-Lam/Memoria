# -*- coding: utf-8 -*-
"""06_coverage.py — Q1/Q3 support: what the KP index actually covers.

Computes, for the target KB:
  * per 教材 chapter: does it have a sidecar, how many KPs, what share of the
    chapter's LINES is inside some KP range (union, not sum), and its token cost
  * unindexed 教材 chapters and their total token cost (the "index gap")
  * per document role (教材 / lectures-slides / notes): KP count, span size,
    name length, structural/OCR/duplicate-name shares
  * within-file duplicate KP names (index pollution), inverted ranges
  * index cost: names only vs names+tags vs name+first-40-chars-of-range

Run: python 06_coverage.py
"""
import os
import re
import json
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402


def main():
    data = K.ensure_data_dir()
    inv = json.load(open(os.path.join(data, 'kp_inventory.json'), encoding='utf-8'))
    rows = inv['target_kb_rows']
    root = K.KB_ROOTS[K.TARGET_KB]
    struct = json.load(open(os.path.join(data, 'structure.json'), encoding='utf-8'))
    files_meta = {r['file']: r for r in struct['files']}

    # ---------- per 教材 chapter coverage
    side_by_file = collections.defaultdict(list)
    for r in rows:
        side_by_file[r['file']].append(r)
    chapter_rows = []
    for f, meta in files_meta.items():
        if not f.startswith('教材/'):
            continue
        kps = side_by_file.get(f, [])
        lines = K.read_text(os.path.join(root, *f.split('/'))).split('\n')
        n_lines = len(lines)
        covered = set()
        for kp in kps:
            s = kp['start_found_line'] or kp['start_hint'] or 0
            e = kp['end_found_line'] or kp['end_hint'] or 0
            if not s:
                continue
            if e < s:
                e = s
            for i in range(max(1, s), min(e, n_lines) + 1):
                covered.add(i)
        chapter_rows.append({
            'file': f,
            'est_tokens': meta['est_tokens'],
            'lines': n_lines,
            'n_kps': len(kps),
            'has_sidecar': bool(kps),
            'covered_lines': len(covered),
            'line_coverage_pct': K.pct(len(covered), n_lines),
            'uncovered_lines': n_lines - len(covered),
        })
    indexed = [c for c in chapter_rows if c['has_sidecar']]
    unindexed = [c for c in chapter_rows if not c['has_sidecar']]
    gap = {
        'textbook_chapters': len(chapter_rows),
        'chapters_with_kps': len(indexed),
        'chapters_without_any_kp': len(unindexed),
        'unindexed_files': [c['file'] for c in unindexed],
        'unindexed_est_tokens': sum(c['est_tokens'] for c in unindexed),
        'indexed_est_tokens': sum(c['est_tokens'] for c in indexed),
        'textbook_est_tokens': sum(c['est_tokens'] for c in chapter_rows),
        'unindexed_token_share_pct': K.pct(sum(c['est_tokens'] for c in unindexed),
                                           sum(c['est_tokens'] for c in chapter_rows)),
        'chapter_mean_line_coverage_pct': round(
            sum(c['line_coverage_pct'] for c in indexed) / len(indexed), 1) if indexed else 0,
    }

    # ---------- per document role
    def role(f):
        if f.startswith('教材/'):
            return '教材'
        if f.startswith('img/'):
            return 'slides'
        if f.startswith('notes/') or f.startswith('homework/'):
            return 'notes'
        return 'other'
    roles = collections.defaultdict(list)
    for r in rows:
        roles[role(r['file'])].append(r)
    role_stats = {}
    for name, rs in roles.items():
        spans = [r['span_chars'] for r in rs if r['span_chars'] > 0]
        names = [len(r['name'] or '') for r in rs]
        dup_in_file = collections.Counter((r['file'], r['name']) for r in rs)
        dup_kps = sum(c for c in dup_in_file.values() if c > 1)
        structural = sum(1 for r in rs if re.match(
            r'^(目录|单选题|多选题|小结|本章小结|引言|前言|封面|附录|参考文献|参考教程|'
            r'习题|作业|练习题|思考题|答案|定义：?|求解过程|例题)$', r['name'] or ''))
        ocr = sum(1 for r in rs if re.search(r'^([un])\s|※|（续）|\(续\)|续$', r['name'] or ''))
        inverted = sum(1 for r in rs
                       if (r['start_found_line'] or 0) and (r['end_found_line'] or 0)
                       and r['end_found_line'] < r['start_found_line'])
        role_stats[name] = {
            'n_kps': len(rs),
            'span_p50': round(K.percentile(spans, 50) or 0, 1),
            'span_p90': round(K.percentile(spans, 90) or 0, 1),
            'span_max': max(spans) if spans else 0,
            'span_lt_200': sum(1 for s in spans if s < 200),
            'name_len_p50': round(K.percentile(names, 50) or 0, 1),
            'duplicate_name_kps': dup_kps,
            'structural_names': structural,
            'ocr_dirty_names': ocr,
            'inverted_ranges': inverted,
        }

    # ---------- inverted ranges + within-file dup names (target KB, all roles)
    inverted = []
    for r in rows:
        s = r['start_found_line'] or 0
        e = r['end_found_line'] or 0
        if s and e and e < s:
            inverted.append({'id': r['id'], 'name': r['name'], 'file': r['file'],
                             'start_line': s, 'end_line': e,
                             'start_hint': r['start_hint'], 'end_hint': r['end_hint']})
    dup_names = []
    by_file = collections.defaultdict(list)
    for r in rows:
        by_file[r['file']].append(r)
    for f, rs in by_file.items():
        c = collections.Counter(r['name'] for r in rs)
        for n, k in c.items():
            if k > 1:
                dup_names.append({'file': f, 'name': n, 'count': k,
                                  'kps': [r['id'] for r in rs if r['name'] == n][:6]})
    dup_names.sort(key=lambda x: -x['count'])

    # ---------- index cost
    def est(s):
        return round(K.est_tokens(s))
    names_only = est(''.join(r['name'] or '' for r in rows))
    with_tags = est(''.join((r['name'] or '') + '|'.join(r.get('tags') or []) for r in rows))
    snippets = est(''.join((r['name'] or '') + K.norm_snip(r['start_snippet'] or '')[:40]
                           for r in rows))
    index_cost = {'kps': len(rows), 'names_only_tokens_est': names_only,
                  'name_plus_tags_tokens_est': with_tags,
                  'name_plus_first40_snippet_tokens_est': snippets,
                  'tokens_per_kp_names_only': round(names_only / len(rows), 1),
                  'tokens_per_kp_name_plus40': round(snippets / len(rows), 1)}

    out = {'coverage_per_chapter': chapter_rows, 'gap': gap,
           'role_stats': role_stats, 'inverted_ranges': inverted,
           'duplicate_names_within_file': dup_names[:40],
           'duplicate_name_kp_total': sum(d['count'] for d in dup_names),
           'index_cost': index_cost}
    with open(os.path.join(data, 'coverage.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---------- print
    print('# 06 KP coverage & index cost (数字通信原理)')
    print('\n## 教材 chapters: is there an index for it?')
    print('| chapter | est tokens | lines | KPs | has KPs | lines covered | coverage % |')
    print('|---|---|---|---|---|---|---|')
    for c in chapter_rows:
        print(f"| {c['file']} | {c['est_tokens']:,} | {c['lines']:,} | {c['n_kps']} | "
              f"{'yes' if c['has_sidecar'] else 'NO'} | {c['covered_lines']:,} | {c['line_coverage_pct']}% |")
    print(f"\n- chapters={gap['textbook_chapters']}, with KPs={gap['chapters_with_kps']}, "
          f"without any KP={gap['chapters_without_any_kp']} ({', '.join(gap['unindexed_files'])})")
    print(f"- UNINDEXED textbook tokens={gap['unindexed_est_tokens']:,} of {gap['textbook_est_tokens']:,} "
          f"= {gap['unindexed_token_share_pct']}% of the textbook")
    print(f"- mean line-coverage inside indexed chapters = {gap['chapter_mean_line_coverage_pct']}%")
    print('\n## per document role')
    print('| role | KPs | span p50 | span p90 | span max | span<200 | name len p50 | dup-name KPs | structural | OCR-dirty | inverted |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    for name, s in role_stats.items():
        print(f"| {name} | {s['n_kps']} | {s['span_p50']} | {s['span_p90']} | {s['span_max']} | "
              f"{s['span_lt_200']} | {s['name_len_p50']} | {s['duplicate_name_kps']} | "
              f"{s['structural_names']} | {s['ocr_dirty_names']} | {s['inverted_ranges']} |")
    print('\n## index cost (what the agent must load to *see* the index)')
    print('| representation | est tokens | tokens/KP |')
    print('|---|---|---|')
    for k in ('names_only_tokens_est', 'name_plus_tags_tokens_est', 'name_plus_first40_snippet_tokens_est'):
        print(f"| {k} | {index_cost[k]:,} | {index_cost[k] / index_cost['kps']:.1f} |")
    print(f"\n## inverted ranges (end before start): {len(inverted)}")
    for r in inverted:
        print(f"- {r['name']} | {r['file']} | start={r['start_line']} end={r['end_line']} (hints {r['start_hint']}/{r['end_hint']})")
    print(f"\n## within-file duplicate names: {len(dup_names)} name groups, "
          f"{out['duplicate_name_kp_total']} KPs involved")
    for d in dup_names[:12]:
        print(f"- {d['count']}x {d['name']} @ {d['file']}")
    print('\nwrote data/coverage.json')


if __name__ == '__main__':
    main()
