# -*- coding: utf-8 -*-
"""02_anchors.py — Q4: are the KP anchors {snippet, line_hint} stable?

Three independent questions, measured separately:

  A. In-sync check (today): does the stored line_hint still point at a line
     that starts with the stored snippet?  A failure here means the sidecar is
     ALREADY stale relative to the markdown.
  B. Snippet-only ambiguity: how often does the snippet text occur more than
     once in the file / in the whole KB? (anchor needs the hint to resolve)
  C. Drift simulation: apply controlled edits to a COPY of the md in memory
     (never on disk) and re-resolve:
        a) insert a 40-line paragraph at a random position before the anchor
        b) delete a 20-line paragraph before the anchor
        c) rewrite the anchor's own first line (the snippet region)
     Metrics: line_hint error (lines), snippet still unique-resolvable, and
     whether the *end* anchor survives when the edit is inside the range.

Writes data/anchor_stats.json and prints tables.
Run: python 02_anchors.py
"""
import os
import re
import json
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402


def analyze(rec, kp, lines, nt, linemap):
    sd = K.locate(nt, linemap, kp['start'].get('snippet'), kp['start'].get('line_hint'))
    ed = K.locate(nt, linemap, kp['end'].get('snippet'), kp['end'].get('line_hint'))
    start_line = sd['line'] or sd['hint']
    end_line = ed['line'] or ed['hint']
    span = K.line_char_span(lines, start_line, end_line)
    return {
        'kb': rec['kb'], 'sidecar': rec['sidecar'], 'file': rec['file'],
        'id': kp['id'], 'name': kp['name'],
        'start': sd, 'end': ed,
        'start_line': start_line, 'end_line': end_line,
        'span_lines': span['span_lines'], 'span_chars': span['span_chars'],
        'start_line_len': len(lines[start_line - 1]) if start_line and start_line <= len(lines) else 0,
    }


def resolve_in(lines, snippet, hint):
    text = '\n'.join(lines)
    nt, linemap = K.norm_text(text)
    return K.locate(nt, linemap, snippet, hint)


def main():
    data = K.ensure_data_dir()
    all_rows = []
    for kb_name in K.KB_ROOTS:
        for rec in K.load_kb(kb_name):
            if not rec['md_exists']:
                continue
            text = K.read_text(rec['md_path'])
            lines = text.split('\n')
            nt, linemap = K.norm_text(text)
            for kp in rec['kps']:
                all_rows.append(analyze(rec, kp, lines, nt, linemap))

    def agg(rows):
        n = len(rows)
        def cnt(pred):
            return sum(1 for r in rows if pred(r))
        return {
            'n': n,
            'start_ok_hint_verified': cnt(lambda r: r['start']['status'] == 'ok_hint_verified'),
            'start_ok_snippet_unique': cnt(lambda r: r['start']['status'] == 'ok'),
            'start_ambiguous': cnt(lambda r: r['start']['status'] == 'ambiguous'),
            'start_not_found': cnt(lambda r: r['start']['status'] == 'not_found'),
            'start_missing_snippet': cnt(lambda r: r['start']['status'] == 'missing'),
            'hint_stale': cnt(lambda r: r['start'].get('hint_prefix_ok') is False),
            'start_snippet_ge_2_matches': cnt(lambda r: r['start']['matches'] >= 2),
            'start_snippet_ge_5_matches': cnt(lambda r: r['start']['matches'] >= 5),
            'end_not_found': cnt(lambda r: r['end']['status'] == 'not_found'),
            'end_ambiguous': cnt(lambda r: r['end']['status'] == 'ambiguous'),
            'end_hint_stale': cnt(lambda r: r['end'].get('hint_prefix_ok') is False),
            'end_snippet_ge_2_matches': cnt(lambda r: r['end']['matches'] >= 2),
            'degenerate_start_eq_end': cnt(lambda r: r['start_line'] is not None and r['start_line'] == r['end_line']),
        }

    stats = {
        'all_kbs': agg(all_rows),
        'per_kb': {},
        'target_kb': {},
    }
    for kb in K.KB_ROOTS:
        stats['per_kb'][kb] = agg([r for r in all_rows if r['kb'] == kb])

    tgt = [r for r in all_rows if r['kb'] == K.TARGET_KB]
    stats['target_kb'] = agg(tgt)
    stats['target_kb']['start_line_delta_hist'] = _hist([r['start'].get('line_delta') for r in tgt])
    stats['target_kb']['snippet_chars_dist'] = _dist([r['start']['snippet_chars'] for r in tgt])
    stats['target_kb']['end_snippet_chars_dist'] = _dist([r['end']['snippet_chars'] for r in tgt if r['end']['snippet_chars']])
    stats['target_kb']['snippet_len_hist'] = _hist([r['start']['snippet_chars'] for r in tgt])
    stats['target_kb']['ambiguous_examples'] = [
        {'id': r['id'], 'name': r['name'], 'sidecar': r['sidecar'],
         'matches': r['start']['matches'], 'hint': r['start']['hint'],
         'chosen_line': r['start_line'], 'match_lines': r['start']['match_lines'][:12],
         'span_lines': r['span_lines'], 'span_chars': r['span_chars']}
        for r in sorted(tgt, key=lambda x: -x['start']['matches'])[:25]
    ]
    stats['target_kb']['end_ambiguous_examples'] = [
        {'id': r['id'], 'name': r['name'], 'sidecar': r['sidecar'],
         'matches': r['end']['matches'], 'snippet': (r['end'] or {}).get('hint'),
         'end_snippet_chars': r['end']['snippet_chars']}
        for r in sorted(tgt, key=lambda x: -x['end']['matches'])[:15]
    ]
    stats['target_kb']['degenerate_examples'] = [
        {'id': r['id'], 'name': r['name'], 'sidecar': r['sidecar'],
         'line': r['start_line'], 'span_chars': r['span_chars']}
        for r in tgt if r['start_line'] == r['end_line']
    ][:20]

    # ---------------- drift simulation on the biggest real chapters
    sim = []
    rng = random.Random(20261027)
    tgt_sidecars = [s for s in K.load_kb(K.TARGET_KB)
                    if s['md_exists'] and s['kps'] and '跳转渲染测试' not in s['file']]
    for rec in tgt_sidecars:
        text = K.read_text(rec['md_path'])
        lines = text.split('\n')
        nt, linemap = K.norm_text(text)
        resolved = [(kp, analyze(rec, kp, lines, nt, linemap)) for kp in rec['kps']]
        resolved = [(kp, r) for kp, r in resolved if r['start_line']]
        if not resolved:
            continue
        # a) insert 40 lines before the anchor
        # b) delete 20 lines before the anchor
        # c) rewrite the anchor's own first line
        results = {'insert40': [], 'delete20': [], 'rewrite_anchor': []}
        for kp, r in resolved:
            sl = r['start_line']
            el = r['end_line'] or sl
            # a) insert 40 lines at max(1, sl - 10)
            pos = max(1, sl - 10)
            new_lines = lines[:pos - 1] + ['新增段落 ' * 3] * 40 + lines[pos - 1:]
            rr = resolve_in(new_lines, kp['start'].get('snippet'), kp['start'].get('line_hint'))
            results['insert40'].append({
                'id': kp['id'],
                'hint_line_error': None if rr['line'] is None else rr['line'] - sl,
                'snippet_found': rr['status'] not in ('not_found', 'missing'),
                'stale_hint_prefix': rr.get('hint_prefix_ok') is False,
            })
            # b) delete 20 lines at max(1, sl - 40)
            pos2 = max(1, sl - 40)
            new_lines = lines[:pos2 - 1] + lines[pos2 - 1 + 20:]
            rr = resolve_in(new_lines, kp['start'].get('snippet'), kp['start'].get('line_hint'))
            results['delete20'].append({
                'id': kp['id'],
                'hint_line_error': None if rr['line'] is None else rr['line'] - sl,
                'snippet_found': rr['status'] not in ('not_found', 'missing'),
                'stale_hint_prefix': rr.get('hint_prefix_ok') is False,
            })
            # c) rewrite the anchor line itself: insert a word into the snippet
            #    region (after ~1/2 of the stored snippet)
            snip = K.norm_snip(kp['start'].get('snippet'))
            if snip and sl - 1 < len(lines):
                line = lines[sl - 1]
                cut = max(1, min(len(snip) // 2, len(line)))
                lines2 = list(lines)
                lines2[sl - 1] = line[:cut] + '（改写）' + line[cut:]
                rr = resolve_in(lines2, kp['start'].get('snippet'), kp['start'].get('line_hint'))
                results['rewrite_anchor'].append({
                    'id': kp['id'],
                    'snippet_found': rr['status'] not in ('not_found', 'missing'),
                    'status': rr['status'],
                })
        sim.append({'sidecar': rec['sidecar'], 'n_anchors': len(resolved), 'results': results})

    stats['drift_sim'] = [_summ_sim(s) for s in sim]
    with open(os.path.join(data, 'anchor_stats.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    # ---------------- print
    print('# 02 anchor stability')
    print('\n## Anchor status (stored hint vs actual md)')
    print('| scope | KPs | hint-verified | snippet-unique ok | ambiguous | not found | hint STALE |')
    print('|---|---|---|---|---|---|---|')
    for name, a in [('ALL 5 KB', stats['all_kbs'])] + [(k, v) for k, v in stats['per_kb'].items()]:
        print(f"| {name} | {a['n']} | {a['start_ok_hint_verified']} | {a['start_ok_snippet_unique']} | "
              f"{a['start_ambiguous']} | {a['start_not_found']} | {a['hint_stale']} |")
    t = stats['target_kb']
    print(f"\n数字通信原理 detail: KPs={t['n']}")
    print(f"- start snippet >=2 matches: {t['start_snippet_ge_2_matches']} ({K.pct(t['start_snippet_ge_2_matches'], t['n'])}%)")
    print(f"- start snippet >=5 matches: {t['start_snippet_ge_5_matches']} ({K.pct(t['start_snippet_ge_5_matches'], t['n'])}%)")
    print(f"- end anchor >=2 matches: {t['end_snippet_ge_2_matches']}")
    print(f"- start==end line (degenerate): {t['degenerate_start_eq_end']}")
    print(f"- snippet chars: p50={t['snippet_chars_dist']['p50']} p90={t['snippet_chars_dist']['p90']} max={t['snippet_chars_dist']['max']}")
    print(f"- snippet length top values: {sorted(t['snippet_len_hist'].items(), key=lambda x: -x[1])[:8]}")
    print(f"- start line_delta hist: {t['start_line_delta_hist']}")
    print('\n## Most ambiguous start snippets (数字通信原理)')
    for e in t['ambiguous_examples'][:15]:
        print(f"- {e['matches']:>3}x | {e['name'][:40]:40s} | hint={e['hint']} chosen={e['chosen_line']} | span={e['span_chars']} chars | {e['sidecar']}")
    print('\n## Degenerate anchors (start==end)')
    for e in t['degenerate_examples'][:10]:
        print(f"- {e['name'][:40]:40s} @line {e['line']} | {e['sidecar']}")
    print('\n## Drift simulation (in memory only)')
    print('| sidecar | anchors | insert40: hint-error mean/max | insert40 snippet found | delete20: hint-error mean/max | delete20 snippet found | rewrite-anchor snippet found |')
    print('|---|---|---|---|---|---|---|')
    for s in stats['drift_sim']:
        print(f"| {s['sidecar']} | {s['n_anchors']} | "
              f"{s['insert_hint_error_mean']}/{s['insert_hint_error_max']} | {s['insert_found_pct']}% | "
              f"{s['delete_hint_error_mean']}/{s['delete_hint_error_max']} | {s['delete_found_pct']}% | "
              f"{s['rewrite_found_pct']}% |")
    print('\nwrote data/anchor_stats.json')


def _summ_sim(s):
    ins = s['results']['insert40']
    dele = s['results']['delete20']
    rew = s['results']['rewrite_anchor']
    def hint_err(xs):
        vals = [abs(x['hint_line_error']) for x in xs if x['hint_line_error'] is not None]
        return (round(sum(vals) / len(vals), 1) if vals else None, max(vals) if vals else None)
    im, ix = hint_err(ins)
    dm, dx = hint_err(dele)
    return {
        'sidecar': s['sidecar'],
        'n_anchors': s['n_anchors'],
        'insert_hint_error_mean': im, 'insert_hint_error_max': ix,
        'insert_found_pct': K.pct(sum(1 for x in ins if x['snippet_found']), len(ins)),
        'delete_hint_error_mean': dm, 'delete_hint_error_max': dx,
        'delete_found_pct': K.pct(sum(1 for x in dele if x['snippet_found']), len(dele)),
        'rewrite_found_pct': K.pct(sum(1 for x in rew if x['snippet_found']), len(rew)),
    }


def _hist(vals):
    h = {}
    for v in vals:
        if v is None:
            h['None'] = h.get('None', 0) + 1
        else:
            h[str(v)] = h.get(str(v), 0) + 1
    return dict(sorted(h.items(), key=lambda kv: (kv[0] == 'None', abs(int(kv[0])) if kv[0] != 'None' else 0)))


def _dist(vals):
    vals = [v for v in vals if v]
    return {'n': len(vals), 'p50': round(K.percentile(vals, 50) or 0, 1),
            'p90': round(K.percentile(vals, 90) or 0, 1),
            'max': max(vals) if vals else 0, 'min': min(vals) if vals else 0}


if __name__ == '__main__':
    main()
