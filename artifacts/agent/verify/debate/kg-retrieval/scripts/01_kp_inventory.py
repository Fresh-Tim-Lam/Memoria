# -*- coding: utf-8 -*-
"""01_kp_inventory.py — Q1: are the existing KPs usable as index units?

Reads every .memoria/sidecars/**/*.memoria.yaml across the 5 real KBs under
D:\\AAA_Courses (read-only), resolves each KP's {snippet, line_hint} anchor
against the actual markdown, and reports:

  * KP count / file, chars per KP, span (lines, chars) distributions
  * KP vs heading level: is a KP a chapter / section / subsection / sentence?
  * too-coarse and too-fragmented KP lists
  * how much of the KB text is actually covered by KPs (index coverage)
  * non-knowledge-point candidates (TOC / preface / test anchors ...)

Writes data/kp_inventory.json, data/kp_target.csv and prints markdown tables.
Run: python 01_kp_inventory.py
"""
import os
import re
import csv
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402


def analyze_sidecar(rec):
    root = rec['kb_root']
    if not rec['md_exists']:
        return None
    text = K.read_text(rec['md_path'])
    lines = text.split('\n')
    hs = K.headings(lines)
    nt, linemap = K.norm_text(text)
    rows = []
    for kp in rec['kps']:
        sd = K.locate(nt, linemap, kp['start'].get('snippet'), kp['start'].get('line_hint'))
        ed = K.locate(nt, linemap, kp['end'].get('snippet'), kp['end'].get('line_hint'))
        start_line = sd['line'] or sd['hint']
        end_line = ed['line'] or ed['hint']
        span = K.line_char_span(lines, start_line, end_line)
        hp = K.heading_path(hs, start_line) if start_line else []
        inner = [h for h in hs if start_line and end_line and start_line < h['line'] <= end_line]
        starts_with_heading = bool(re.match(r'^\s*#{1,6}\s', lines[start_line - 1])) if start_line and start_line <= len(lines) else False
        rows.append({
            'kb': rec['kb'],
            'sidecar': rec['sidecar'],
            'file': rec['file'],
            'id': kp['id'],
            'name': kp['name'],
            'start_snippet': kp['start'].get('snippet'),
            'end_snippet': kp['end'].get('snippet'),
            'start_hint': sd['hint'],
            'end_hint': ed['hint'],
            'start_found_line': sd['line'],
            'end_found_line': ed['line'],
            'start_status': sd['status'],
            'end_status': ed['status'],
            'start_matches': sd['matches'],
            'end_matches': ed['matches'],
            'start_line_delta': sd['line_delta'],
            'end_line_delta': ed['line_delta'],
            'start_snippet_chars': sd['snippet_chars'],
            'end_snippet_chars': ed['snippet_chars'],
            'span_lines': span['span_lines'],
            'span_chars': span['span_chars'],
            'heading_level': hp[-1]['level'] if hp else None,
            'heading_text': hp[-1]['text'] if hp else None,
            'heading_path': ' > '.join(h['text'] for h in hp),
            'starts_with_heading': starts_with_heading,
            'inner_headings': len(inner),
            'inner_heading_levels': ','.join(str(h['level']) for h in inner),
            'tags': ';'.join(kp.get('tags') or []),
            'extra_keys': ';'.join(kp.get('extra_keys') or []),
        })
    return {
        'sidecar': rec['sidecar'],
        'file': rec['file'],
        'md_exists': rec['md_exists'],
        'md_chars': len(text),
        'md_lines': len(lines),
        'md_bytes': os.path.getsize(rec['md_path']),
        'n_kps': len(rows),
        'rows': rows,
    }


def main():
    data = K.ensure_data_dir()
    summary = {'kb': {}, 'target_kb': K.TARGET_KB}
    all_rows = []
    for kb_name in K.KB_ROOTS:
        recs = K.load_kb(kb_name)
        side_infos = [analyze_sidecar(r) for r in recs]
        side_infos = [s for s in side_infos if s]
        rows = [r for s in side_infos for r in s['rows']]
        all_rows += rows
        mds = K.md_files(K.KB_ROOTS[kb_name])
        md_chars = sum(os.path.getsize(p) for p in mds)
        target_md = set()
        for s in side_infos:
            target_md.add(s['file'])
        indexed_md_bytes = sum(s['md_bytes'] for s in side_infos if s['md_exists'])
        summary['kb'][kb_name] = {
            'sidecar_files': len(recs),
            'sidecars_with_md': len(side_infos),
            'n_kps': len(rows),
            'md_files_total': len(mds),
            'md_files_with_sidecar': len(target_md),
            'md_bytes_total': md_chars,
            'md_bytes_indexed': indexed_md_bytes,
            'md_coverage_pct': K.pct(indexed_md_bytes, md_chars),
            'kps_with_unresolved_start_anchor': sum(1 for r in rows if r['start_status'] in ('not_found', 'missing')),
            'kps_with_ambiguous_anchor': sum(1 for r in rows if r['start_status'] == 'ambiguous'),
            'kps_with_not_found_anchor': sum(1 for r in rows if r['start_status'] == 'not_found'),
            'kps_with_stale_hint': sum(1 for r in rows if r['start_status'] == 'ambiguous' and r['start_line_delta'] not in (0, None)),
            'kps_tags_present': sum(1 for r in rows if r['tags']),
            'span_chars': [r['span_chars'] for r in rows if r['span_chars'] > 0],
            'span_lines': [r['span_lines'] for r in rows if r['span_lines'] > 0],
            'per_sidecar': [{
                'sidecar': s['sidecar'], 'file': s['file'],
                'md_chars': s['md_chars'], 'n_kps': s['n_kps'],
                'chars_per_kp': round(s['md_chars'] / s['n_kps'], 1) if s['n_kps'] else None,
            } for s in side_infos],
        }

    # ---------------- focus: target KB
    tgt = summary['kb'][K.TARGET_KB]
    trows = [r for r in all_rows if r['kb'] == K.TARGET_KB]
    chars = [r['span_chars'] for r in trows if r['span_chars'] > 0]
    lines_ = [r['span_lines'] for r in trows if r['span_lines'] > 0]

    def dist(vals):
        return {
            'n': len(vals),
            'p50': round(K.percentile(vals, 50) or 0, 1),
            'p90': round(K.percentile(vals, 90) or 0, 1),
            'max': max(vals) if vals else 0,
            'min': min(vals) if vals else 0,
            'mean': round(sum(vals) / len(vals), 1) if vals else 0,
        }

    tgt['span_chars_dist'] = dist(chars)
    tgt['span_lines_dist'] = dist(lines_)
    tgt['kp_level_dist'] = {}
    for r in trows:
        key = str(r['heading_level'])
        tgt['kp_level_dist'][key] = tgt['kp_level_dist'].get(key, 0) + 1
    tgt['starts_with_heading_n'] = sum(1 for r in trows if r['starts_with_heading'])
    tgt['starts_with_heading_pct'] = K.pct(tgt['starts_with_heading_n'], len(trows))
    tgt['kp_with_inner_headings'] = sum(1 for r in trows if r['inner_headings'] > 0)
    tgt['name_equals_id'] = sum(1 for r in trows if r['name'] == r['id'])
    tgt['duplicate_names'] = _dups([r['name'] for r in trows])
    tgt['duplicate_ids'] = _dups([r['id'] + '@' + str(r['sidecar']) for r in trows])

    # rough token cost of the whole KP index (name+anchors only)
    index_chars = sum(len(r['name'] or '') for r in trows)
    tgt['index_name_chars_total'] = index_chars
    tgt['index_name_tokens_est'] = round(K.est_tokens(''.join(r['name'] or '' for r in trows)))

    # too coarse / too fragmented
    tgt['too_coarse'] = [r for r in trows if r['span_chars'] >= 20000][:60]
    tgt['too_fragmented'] = [r for r in trows if 0 < r['span_chars'] < 300][:80]

    summary['target_kb_stats'] = tgt
    summary['target_kb_rows'] = trows

    with open(os.path.join(data, 'kp_inventory.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    fields = ['kb', 'sidecar', 'file', 'id', 'name', 'start_hint', 'end_hint',
              'start_found_line', 'end_found_line', 'start_status', 'end_status',
              'start_matches', 'end_matches', 'start_line_delta', 'end_line_delta',
              'span_lines', 'span_chars', 'heading_level', 'heading_text',
              'heading_path', 'starts_with_heading', 'inner_headings', 'tags']
    with open(os.path.join(data, 'kp_target.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(trows)

    # ---------------- print
    print('# 01 KP inventory')
    print('\n## All KBs under D:\\AAA_Courses')
    print('| KB | sidecars | KPs | md files | indexed md | indexed bytes/MB | KP coverage of md bytes |')
    print('|---|---|---|---|---|---|---|')
    for kb, s in summary['kb'].items():
        print(f"| {kb} | {s['sidecar_files']} | {s['n_kps']} | {s['md_files_total']} | "
              f"{s['md_files_with_sidecar']} | {s['md_bytes_indexed']/1048576:.2f} | "
              f"{s['md_coverage_pct']}% |")
    print('\n## 数字通信原理: per-sidecar')
    print('| sidecar | md chars | KPs | chars/KP |')
    print('|---|---|---|---|')
    for p in tgt['per_sidecar']:
        print(f"| {p['sidecar']} | {p['md_chars']} | {p['n_kps']} | {p['chars_per_kp']} |")
    print('\n## 数字通信原理: span distribution')
    print('| metric | n | p50 | p90 | max | mean |')
    print('|---|---|---|---|---|---|')
    for name, d in (('span_chars', tgt['span_chars_dist']), ('span_lines', tgt['span_lines_dist'])):
        print(f"| {name} | {d['n']} | {d['p50']} | {d['p90']} | {d['max']} | {d['mean']} |")
    print('\n## 数字通信原理: KP vs heading level')
    print('| parent heading level | KPs |')
    print('|---|---|')
    for k in sorted(tgt['kp_level_dist'], key=lambda x: (x == 'None', x)):
        print(f"| {k} | {tgt['kp_level_dist'][k]} |")
    print(f"\n- starts with a heading markdown line: {tgt['starts_with_heading_n']}/{len(trows)} "
          f"({tgt['starts_with_heading_pct']}%)")
    print(f"- KP span contains nested headings: {tgt['kp_with_inner_headings']}/{len(trows)}")
    print(f"- name == id: {tgt['name_equals_id']}/{len(trows)}")
    print(f"- duplicate names: {tgt['duplicate_names']}")
    print(f"- index (names only) chars={tgt['index_name_chars_total']}, est tokens={tgt['index_name_tokens_est']}")
    print(f"\n## too coarse (span_chars >= 20000): {len(tgt['too_coarse'])}")
    for r in tgt['too_coarse'][:40]:
        print(f"- {r['span_chars']:>7} chars / {r['span_lines']:>4} lines | {r['name']} | {r['sidecar']}:{r['start_hint']}-{r['end_hint']}")
    print(f"\n## too fragmented (0 < span_chars < 300): {len(tgt['too_fragmented'])}")
    for r in tgt['too_fragmented'][:40]:
        print(f"- {r['span_chars']:>5} chars | {r['name']} | {r['sidecar']}:{r['start_hint']}")
    print('\nwrote data/kp_inventory.json, data/kp_target.csv')


def _dups(vals):
    seen = {}
    for v in vals:
        seen[v] = seen.get(v, 0) + 1
    return {k: c for k, c in seen.items() if c > 1}


if __name__ == '__main__':
    main()
