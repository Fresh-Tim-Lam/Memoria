# -*- coding: utf-8 -*-
"""03_structure.py — Q5: markdown structure of the real textbooks.

Measures, per file: size, CJK vs ASCII composition, heading levels, inline
LaTeX ($...$), display math, image references, tables, code fences, paragraph
lengths (would "split by block" survive?), highlight/link macro density, and
the token cost of reading the whole file.

Run: python 03_structure.py
"""
import os
import re
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402

H_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
INLINE_MATH = re.compile(r'(?<!\$)\$(?!\$)[^$\n]{1,120}\$(?!\$)')
DISPLAY_MATH = re.compile(r'\$\$.+?\$\$', re.S)
IMG = re.compile(r'!\[[^\]]*\]\([^)]*\)')
TABLE_ROW = re.compile(r'^\s*\|.*\|\s*$')
FENCE = re.compile(r'^\s*```')
HILITE = re.compile(r'\[\[\\[hc]:')
LINKMACRO = re.compile(r'\[\[[^\]]*\|')


def file_stats(path, root):
    text = K.read_text(path)
    raw = open(path, 'rb').read()
    lines = text.split('\n')
    cjk = len(K.CJK_RE.findall(text))
    other = len(text) - cjk
    hs = [{'level': len(m.group(1)), 'text': m.group(2).strip()}
          for m in (H_RE.match(l) for l in lines) if m]
    level_counts = {}
    for h in hs:
        level_counts[h['level']] = level_counts.get(h['level'], 0) + 1
    paras = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    para_chars = [len(p) for p in paras]
    # paragraph = block between blank lines; strip image-only blocks separately
    non_img_paras = [p for p in paras if not re.fullmatch(r'(\s*!\[[^\]]*\]\([^)]*\)\s*)+', p)]
    non_img_chars = [len(p) for p in non_img_paras]
    max_para = max(non_img_paras, key=len) if non_img_paras else ''
    return {
        'file': K.rel(path, root),
        'bytes': len(raw),
        'chars': len(text),
        'cjk_chars': cjk,
        'ascii_other_chars': other,
        'cjk_ratio': round(cjk / max(1, len(text)), 3),
        'lines': len(lines),
        'headings': len(hs),
        'heading_levels': level_counts,
        'max_heading_level': max(level_counts) if level_counts else 0,
        'inline_math': len(INLINE_MATH.findall(text)),
        'display_math_blocks': len(DISPLAY_MATH.findall(text)),
        'images': len(IMG.findall(text)),
        'image_only_lines': sum(1 for l in lines if re.match(r'^\s*!\[', l)),
        'table_rows': sum(1 for l in lines if TABLE_ROW.match(l)),
        'code_fences': sum(1 for l in lines if FENCE.match(l)),
        'hilite_macros': len(HILITE.findall(text)),
        'link_macros': len(LINKMACRO.findall(text)),
        'paragraphs': len(paras),
        'non_image_paragraphs': len(non_img_paras),
        'para_chars_p50': round(K.percentile(non_img_chars, 50) or 0, 1),
        'para_chars_p90': round(K.percentile(non_img_chars, 90) or 0, 1),
        'para_chars_p99': round(K.percentile(non_img_chars, 99) or 0, 1),
        'para_chars_max': max(non_img_chars) if non_img_chars else 0,
        'max_para_head': max_para[:120],
        'est_tokens': round(K.est_tokens(text)),
        'bytes_per_char': round(len(raw) / max(1, len(text)), 3),
    }


def main():
    data = K.ensure_data_dir()
    root = K.KB_ROOTS[K.TARGET_KB]
    paths = K.md_files(root)
    rows = [file_stats(p, root) for p in paths]
    by = {r['file']: r for r in rows}

    textbook = [r for r in rows if r['file'].startswith('教材/')]
    others = [r for r in rows if not r['file'].startswith('教材/')]
    total = {
        'md_files': len(rows),
        'bytes': sum(r['bytes'] for r in rows),
        'chars': sum(r['chars'] for r in rows),
        'cjk_chars': sum(r['cjk_chars'] for r in rows),
        'est_tokens': sum(r['est_tokens'] for r in rows),
        'textbook_files': len(textbook),
        'textbook_bytes': sum(r['bytes'] for r in textbook),
        'textbook_cjk_chars': sum(r['cjk_chars'] for r in textbook),
        'textbook_est_tokens': sum(r['est_tokens'] for r in textbook),
    }
    # aggregate heading-level distribution across textbook chapters
    agg = {}
    for r in textbook:
        for lv, c in r['heading_levels'].items():
            agg[str(lv)] = agg.get(str(lv), 0) + c
    total['textbook_heading_levels'] = agg
    total['textbook_images'] = sum(r['images'] for r in textbook)
    total['textbook_inline_math'] = sum(r['inline_math'] for r in textbook)
    total['textbook_display_math'] = sum(r['display_math_blocks'] for r in textbook)
    total['textbook_para_p90_max'] = max(r['para_chars_p90'] for r in textbook)
    total['textbook_long_paras_over_2k'] = sum(
        1 for r in textbook for p in [] )  # placeholder, computed below

    # count long paragraphs directly
    long_threshold = 2000
    long_paras = 0
    for r in textbook:
        p = os.path.join(root, *r['file'].split('/'))
        text = K.read_text(p)
        for para in re.split(r'\n\s*\n', text):
            if para.strip() and not re.fullmatch(r'(\s*!\[[^\]]*\]\([^)]*\)\s*)+', para) and len(para) >= long_threshold:
                long_paras += 1
    total['textbook_long_paras_over_2k'] = long_paras

    with open(os.path.join(data, 'structure.json'), 'w', encoding='utf-8') as f:
        json.dump({'total': total, 'files': rows}, f, ensure_ascii=False, indent=1)

    print('# 03 markdown structure (数字通信原理)')
    print(f"\nKB: {total['md_files']} md files, {total['bytes']/1048576:.2f} MB, "
          f"{total['chars']:,} chars, {total['cjk_chars']:,} CJK, est {total['est_tokens']:,} tokens")
    print(f"教材: {total['textbook_files']} files, {total['textbook_bytes']/1048576:.2f} MB, "
          f"{total['textbook_cjk_chars']:,} CJK chars, est {total['textbook_est_tokens']:,} tokens")
    print('\n## 教材 chapter table')
    print('| file | bytes | chars | CJK | est tokens | lines | H# | max H lvl | inline $ | $$ blocks | images | table rows | para p90 | para max |')
    print('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for r in textbook:
        print(f"| {r['file']} | {r['bytes']:,} | {r['chars']:,} | {r['cjk_chars']:,} | {r['est_tokens']:,} | "
              f"{r['lines']:,} | {r['headings']} | {r['max_heading_level']} | {r['inline_math']:,} | "
              f"{r['display_math_blocks']} | {r['images']} | {r['table_rows']} | {r['para_chars_p90']} | {r['para_chars_max']:,} |")
    print('\n## heading level distribution across 教材')
    print('| level | count |')
    print('|---|---|')
    for lv in sorted(agg, key=int):
        print(f"| H{lv} | {agg[lv]} |")
    print(f"\n- images in 教材: {total['textbook_images']}, inline math: {total['textbook_inline_math']:,}, "
          f"display math: {total['textbook_display_math']}")
    print(f"- paragraphs >= 2000 chars in 教材: {total['textbook_long_paras_over_2k']}")
    print('\n## non-教材 files')
    print('| file | bytes | est tokens | lines | H# | images |')
    print('|---|---|---|---|---|---|')
    for r in others:
        print(f"| {r['file']} | {r['bytes']:,} | {r['est_tokens']:,} | {r['lines']:,} | {r['headings']} | {r['images']} |")
    print('\nwrote data/structure.json')


if __name__ == '__main__':
    main()
