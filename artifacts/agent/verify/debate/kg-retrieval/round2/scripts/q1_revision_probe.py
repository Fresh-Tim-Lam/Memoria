# -*- coding: utf-8 -*-
"""q1_revision_probe.py — Q1 修订版口径复算（吸收复核意见，第一方数字）。

目的：把 Q1 原材料的三个口径问题用第一方复算钉死，供 Q1-research.md §13 引用：
  1) 尺寸四口径：literal-hint / raw-resolved / clamped / heading（原 D2 标签错位）
  2) A2「end 全部语义化」到底多少 KP 会变（含"当前 end 已越界、会变短"）
  3) 产品 range_ok 口径下的 anchor_verified 当前值（不是"clamp 修复后投影"）
  4) token 系数用 data/token_calibration.json 的 0.4247（不是硬编码 0.4237）
  5) `比特率` 的 context 是否可消歧（复核员指出可消歧）

复用 q1_research_probe.py 的解析与 locate 函数（同目录 import），不重复实现；
只读 frozen 快照，不写活动库。

Run:
  python artifacts/agent/verify/debate/kg-retrieval/round2/scripts/q1_revision_probe.py
"""
import os
import sys
import json
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import q1_research_probe as base  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
FROZEN = os.path.join(ROOT, 'round2', 'frozen', '数字通信原理')
MANIFEST = os.path.join(ROOT, 'round2', 'frozen', 'MANIFEST.json')
DATA = os.path.join(ROOT, 'round2', 'data')
OUT = os.path.join(DATA, 'q1-revision.json')
CAL = os.path.join(ROOT, 'data', 'token_calibration.json')


def pct(x, n):
    return round(100.0 * x / n, 1) if n else 0.0


def main():
    os.makedirs(DATA, exist_ok=True)
    man = json.load(open(MANIFEST, encoding='utf-8'))
    files = {f['path']: f for f in man['files']}
    md_files = sorted(p for p in files if p.endswith('.md'))
    side_files = sorted(p for p in files if p.endswith('.memoria.yaml'))

    texts, lines_by, heads_by = {}, {}, {}
    for rel in md_files:
        t = base.read_text(os.path.join(FROZEN, *rel.split('/')))
        texts[rel] = t
        lines_by[rel] = t.split('\n')
        heads_by[rel] = base.headings_of(lines_by[rel])

    rows = []
    for rel in side_files:
        sc = base.parse_sidecar(os.path.join(FROZEN, *rel.split('/')))
        md = sc['file']
        if md not in texts:
            continue
        nt, linemap = base.norm_text(texts[md])
        lines, hs = lines_by[md], heads_by[md]
        eof = len(lines)
        for kp in sc['kps']:
            sh = kp['start']['line_hint']
            eh = kp['end']['line_hint']
            st = base.resolve(nt, linemap, kp['start']['snippet'], sh)
            en = base.resolve(nt, linemap, kp['end']['snippet'], eh)
            start_res = st['line'] if st['found'] else None
            end_res = en['line'] if en['found'] else None
            if start_res is None:
                start_res = sh or 1
            owner, oi = base.nearest_heading_before(hs, start_res)
            boundary = (base.section_end(hs, oi, eof) if owner
                        else (hs[0]['line'] - 1 if hs else eof))
            boundary = max(boundary, start_res)
            end_clamped = (min(end_res, boundary) if end_res is not None else boundary)
            end_clamped = max(end_clamped, start_res)
            role = ('教材' if md.startswith('教材/') else
                    ('slides' if md.startswith('img/') else 'notes'))
            start_heading = (owner is not None and owner['line'] == start_res)
            # product range_ok = resolve_range ok：start/end 都解析到且不反转
            ok = (start_res is not None and end_res is not None and end_res >= start_res)
            # 消歧档（只在 ok 的 KP 上算）
            sec_unique = False
            if st['found'] and start_res is not None:
                in_sec = [ln for ln in st['occ_lines']
                          if (owner['line'] if owner else 1) <= ln <= boundary]
                sec_unique = len(set(in_sec)) == 1
            ctx_unique = False
            ctx_lines = []
            if st['found'] and st['matches'] > 1:
                chosen = None
                for o in base.occurrences(nt, st['snippet']):
                    if linemap[o] == start_res:
                        chosen = o
                        break
                if chosen is not None:
                    ctx = nt[max(0, chosen - 40):chosen]
                    cand = [o for o in base.occurrences(nt, st['snippet'])
                            if nt[max(0, o - 40):o] == ctx]
                    ctx_unique = len(cand) == 1
            # sizes
            def size(a, b):
                if a is None or b is None or b < a:
                    return None
                return base.line_chars(lines, a, b)
            sizes = {
                'literal_hint': size(sh, eh) if (sh and eh and eh >= sh) else None,
                'hint_end_only': size(start_res, eh),
                'raw_resolved': size(start_res, end_res),
                'clamped': size(start_res, end_clamped),
                'heading': size(start_res, boundary),
            }
            end_repair = (en['matches'] == 0 or en['matches'] > 1
                          or (end_res is not None and end_res > boundary)
                          or end_res is None)
            rows.append({
                'id': kp['id'], 'name': kp['name'], 'file': md, 'role': role,
                'start_hint': sh, 'end_hint': eh,
                'start_resolved': start_res, 'end_resolved': end_res,
                'boundary': boundary, 'start_heading': start_heading,
                'ok': ok, 'sec_unique': sec_unique, 'ctx_unique': ctx_unique,
                'start_unique': st['unique'], 'start_matches': st['matches'],
                'end_matches': en['matches'], 'end_repair': end_repair,
                'end_missing': en['matches'] == 0,
                'end_lt_boundary': end_res is not None and end_res < boundary,
                'end_gt_boundary': end_res is not None and end_res > boundary,
                'end_differs_from_boundary': (end_res is None or end_res != boundary),
                'sizes': sizes,
            })
    N = len(rows)

    def box(rs, key):
        vals = [r['sizes'][key] for r in rs if r['sizes'][key] is not None]
        return {'n': len(vals), 'p50': base.pctl(vals, 50), 'p90': base.pctl(vals, 90),
                'max': max(vals) if vals else None,
                'gt1200_pct': pct(sum(1 for v in vals if v > 1200), len(vals))}

    role = lambda sel: [r for r in rows if r['role'] == sel]
    sizes = {}
    for key in ('literal_hint', 'hint_end_only', 'raw_resolved', 'clamped', 'heading'):
        sizes[key] = {'all': box(rows, key), 'textbook': box(role('教材'), key)}

    total_raw = sum(r['sizes']['raw_resolved'] for r in rows if r['sizes']['raw_resolved'])
    total_clamped = sum(r['sizes']['clamped'] for r in rows if r['sizes']['clamped'])
    total_heading = sum(r['sizes']['heading'] for r in rows if r['sizes']['heading'])
    total_literal = sum(r['sizes']['literal_hint'] for r in rows if r['sizes']['literal_hint'])

    # A2: end 全部改成 heading 语义边界 → 哪些 KP 会变（含"当前已越界、会变短"）
    a2_changed = [r for r in rows if r['end_differs_from_boundary']]
    a2_lt = [r for r in rows if r['end_lt_boundary']]
    a2_gt = [r for r in rows if r['end_gt_boundary']]
    a2_missing = [r for r in rows if r['end_missing']]
    a2 = {'n': N, 'changed': len(a2_changed), 'changed_pct': pct(len(a2_changed), N),
          'end_lt_boundary': len(a2_lt), 'end_gt_boundary': len(a2_gt),
          'end_missing': len(a2_missing),
          'changed_by_role': {k: sum(1 for r in a2_changed if r['role'] == k)
                              for k in ('教材', 'slides', 'notes')}}

    # anchor：产品 range_ok 口径下的当前值（不是 clamp 后的投影）
    ok = [r for r in rows if r['ok']]
    anchor = {
        'product_range_ok': len(ok), 'product_range_ok_pct': pct(len(ok), N),
        'ok_strict': sum(1 for r in ok if r['start_unique']),
        'ok_strict_pct': pct(sum(1 for r in ok if r['start_unique']), len(ok)),
        'ok_section': sum(1 for r in ok if r['start_unique'] or r['sec_unique']),
        'ok_section_pct': pct(sum(1 for r in ok if r['start_unique'] or r['sec_unique']), len(ok)),
        'ok_context': sum(1 for r in ok if r['start_unique'] or r['sec_unique'] or r['ctx_unique']),
        'ok_context_pct': pct(sum(1 for r in ok if r['start_unique'] or r['sec_unique'] or r['ctx_unique']), len(ok)),
        'bad_ids': [r['id'] for r in rows if not r['ok']],
        'end_missing_ids': [r['id'] for r in rows if r['end_missing']],
    }

    # 比特率：context 是否可消歧
    bit = [r for r in rows if r['id'] == '比特率']
    bit_detail = []
    if bit:
        b = bit[0]
        md = b['file']
        nt, linemap = base.norm_text(texts[md])
        occ = []
        for rel in side_files:
            sc = base.parse_sidecar(os.path.join(FROZEN, *rel.split('/')))
            if sc['file'] == md:
                kp = next(k for k in sc['kps'] if k['id'] == '比特率')
                snip = base.norm_snip(kp['start']['snippet'])
                occ = base.occurrences(nt, snip)
                break
        for o in occ:
            line = linemap[o]
            ctx = texts[md].split('\n')[line - 1][:80] if line - 1 < len(texts[md].split('\n')) else ''
            pre = nt[max(0, o - 40):o]
            bit_detail.append({'line': line, 'pre40': pre, 'line_head': ctx})
    bit_ctx = {'occurrences': len(bit_detail),
               'distinct_pre40': len({d['pre40'] for d in bit_detail}),
               'detail': bit_detail}

    # token 系数（用标定文件，不用硬编码）
    cal = json.load(open(CAL, encoding='utf-8'))
    coef = float(cal['uniform_tokens_per_char'])
    tb_raw_p50 = sizes['raw_resolved']['textbook']['p50']
    tok = {
        'calibration_uniform': coef,
        'read_kp_textbook_raw_p50_chars': tb_raw_p50,
        'read_kp_textbook_raw_p50_tokens': round(tb_raw_p50 * coef) if tb_raw_p50 else None,
        'read_kp_textbook_heading_p50_tokens': round(
            sizes['heading']['textbook']['p50'] * coef) if sizes['heading']['textbook']['p50'] else None,
    }

    # 非标题起点 + 需修 end 的病态 KP（A1 风险叙事）
    pathological = [{'id': r['id'], 'file': r['file'], 'start_heading': r['start_heading'],
                     'raw_chars': r['sizes']['raw_resolved'],
                     'heading_chars': r['sizes']['heading']}
                    for r in rows
                    if r['end_repair'] and not r['start_heading'] and r['role'] == '教材']
    pathological.sort(key=lambda x: -(x['heading_chars'] or 0))
    pathological_all = [{'id': r['id'], 'file': r['file'],
                         'start_heading': r['start_heading'],
                         'raw_chars': r['sizes']['raw_resolved'],
                         'heading_chars': r['sizes']['heading']}
                        for r in rows if r['end_repair']]
    pathological_all.sort(key=lambda x: -(x['heading_chars'] or 0))

    out = {
        'snapshot': {'md': len(md_files), 'sidecars': len(side_files),
                     'kps': N, 'token_calibration': CAL},
        'sizes': sizes,
        'totals': {'literal_hint': total_literal, 'raw_resolved': total_raw,
                   'clamped': total_clamped, 'heading': total_heading,
                   'raw_to_heading_pct': round(100.0 * (total_heading - total_raw) / total_raw, 1),
                   'clamped_to_heading_pct': round(100.0 * (total_heading - total_clamped) / total_clamped, 1)},
        'A2_changed_raw': a2,
        'anchor_product_ok': anchor,
        'bitrate_context': bit_ctx,
        'tokens': tok,
        'pathological_repaired_textbook': pathological,
        'pathological_all': pathological_all,
        'note': '本文件是 Q1-research.md §13 修订口径的第一方复算；与复核员 Q1-verify.md 的独立数字并列时，'
                '两者都对同一 frozen 快照，但引擎不同（本脚本复用 q1_research_probe 的定位器；'
                '复核员用产品 range.locator + heading_proposals）。',
    }
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print('# Q1 revision probe — 第一方口径复算（frozen 14:09:46）')
    print(f"\n## sizes")
    for k, v in sizes.items():
        print(f"- {k}: all p50={v['all']['p50']} (>1200 {v['all']['gt1200_pct']}%) | "
              f"textbook p50={v['textbook']['p50']} (>1200 {v['textbook']['gt1200_pct']}%)")
    print(f"\n## totals: literal={total_literal} raw={total_raw} clamped={total_clamped} "
          f"heading={total_heading} | raw→heading {out['totals']['raw_to_heading_pct']}% | "
          f"clamped→heading {out['totals']['clamped_to_heading_pct']}%")
    print(f"\n## A2 changed(raw)={a2['changed']}/{a2['n']} ({a2['changed_pct']}%) "
          f"| end<boundary={a2['end_lt_boundary']} end>boundary={a2['end_gt_boundary']} missing={a2['end_missing']} "
          f"| by_role={a2['changed_by_role']}")
    print(f"\n## anchor product-ok: {anchor['product_range_ok']}/{N} ({anchor['product_range_ok_pct']}%) "
          f"strict={anchor['ok_strict_pct']}% section={anchor['ok_section_pct']}% context={anchor['ok_context_pct']}%")
    print(f"   bad_ids={anchor['bad_ids']}")
    print(f"\n## 比特率: occurrences={bit_ctx['occurrences']} distinct_pre40={bit_ctx['distinct_pre40']}")
    for d in bit_ctx['detail']:
        print(f"   line {d['line']}: pre40={d['pre40']!r}")
    print(f"\n## tokens: coef={tok['calibration_uniform']} read_kp textbook raw p50 "
          f"{tok['read_kp_textbook_raw_p50_chars']} 字 ≈ {tok['read_kp_textbook_raw_p50_tokens']} tok")
    print('\n## pathological (教材, 非标题起点, 需修/越界) heading sizes:')
    for p in pathological:
        print(f"   {p['id']}: raw={p['raw_chars']} -> heading={p['heading_chars']}")
    print('\nwrote', OUT)


if __name__ == '__main__':
    main()


