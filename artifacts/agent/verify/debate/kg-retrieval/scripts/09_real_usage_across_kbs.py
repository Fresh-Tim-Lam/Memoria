# -*- coding: utf-8 -*-
"""09_real_usage_across_kbs.py — R13 反事实检验的「真实依据」部分。

Lead 要求：S1–S3 可以是假设，但若能找到更硬的真实依据优先用。
本脚本读 5 个真实知识库的 agent 会话日志（只读），统计：
  * 每个 KB 的会话数 / 用户提问数 / read_document 调用数
  * 这些调用落在哪些教材章（按文件名里的章号）
  * 使用是否集中在少数章？top 章在书里的位置（前面还是后面）？
  * 已建 sidecar 的章 vs 实际被读的章是否一致（现状是不是"哪里用建哪里"）

输出 data/real-usage.json（供 10_r13_counterfactual.py 与报告引用）。
Run: python 09_real_usage_across_kbs.py
"""
import os
import re
import json
import glob
import collections
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402

CHAPTER_RE = re.compile(r'(?:教材|notes|img|ppt|problems|animation)[/\\](?:(\d+)[_第]|([^/\\]+))')
TEXTBOOK_RE = re.compile(r'教材[/\\](\d+)')


def parse_session(path):
    """Yield user/message texts and read_document paths from one jsonl."""
    calls = {}
    questions = []
    reads = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = e.get('type')
            d = e.get('data') or {}
            if t == 'user/message':
                txt = (d.get('text') or '').strip()
                if txt:
                    questions.append(txt)
            elif t == 'tool/call':
                calls[d.get('id')] = d
            elif t == 'tool/result':
                c = calls.get(d.get('id')) or {}
                if (d.get('name') or c.get('name')) == 'read_document':
                    try:
                        args = json.loads(c.get('arguments') or '{}')
                    except json.JSONDecodeError:
                        args = {}
                    p = args.get('path') or ''
                    if p:
                        reads.append(p)
    return questions, reads


def chapter_of(path):
    m = TEXTBOOK_RE.search(path)
    if m:
        return int(m.group(1))
    return None


def sidecar_chapters(root):
    out = []
    for p in K.sidecar_paths(root):
        rel = K.rel(p, root)
        m = TEXTBOOK_RE.search(rel)
        if m:
            out.append(int(m.group(1)))
    return sorted(set(out))


def main():
    data = K.ensure_data_dir()
    snap = json.load(open(os.path.join(data, 'corpus-snapshot.json'), encoding='utf-8'))
    result = {'taken_at': snap['taken_at'], 'kbs': {}}
    for kb, root in K.KB_ROOTS.items():
        sess_dir = os.path.join(root, '.memoria', 'agent', 'sessions')
        files = sorted(glob.glob(os.path.join(sess_dir, '*.jsonl'))) if os.path.isdir(sess_dir) else []
        all_q, all_r, per_session = [], [], []
        for p in files:
            q, r = parse_session(p)
            per_session.append({'file': os.path.basename(p), 'bytes': os.path.getsize(p),
                                'questions': len(q), 'reads': len(r)})
            all_q += q
            all_r += r
        chapter_reads = collections.Counter()
        other_reads = collections.Counter()
        for p in all_r:
            ch = chapter_of(p)
            if ch is None:
                top = p.replace('\\', '/').split('/')[0]
                other_reads[top] += 1
            else:
                chapter_reads[ch] += 1
        # chapter file inventory (textbook only)
        chap_files = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != '.memoria']
            for fn in filenames:
                if not fn.lower().endswith('.md'):
                    continue
                p = os.path.join(dirpath, fn)
                rel = K.rel(p, root)
                m = TEXTBOOK_RE.search(rel)
                if m:
                    chap_files[int(m.group(1))] = {'rel': rel, 'bytes': os.path.getsize(p)}
        n_chapters = max(chap_files) if chap_files else 0
        total_reads = sum(chapter_reads.values())
        top = chapter_reads.most_common(3)
        top_ch = top[0][0] if top else None
        top_share = K.pct(top[0][1], total_reads) if top else 0.0
        top3_share = K.pct(sum(c for _, c in top), total_reads) if top else 0.0
        sc_ch = sidecar_chapters(root)
        # review cards (FSRS): cards.json has a `file` field per card -> direct frontier signal
        review_files = os.path.join(root, '.memoria', 'agent', 'review', 'cards.json')
        review_ch = collections.Counter()
        review_n = 0
        if os.path.isfile(review_files):
            try:
                rd = json.load(open(review_files, encoding='utf-8'))
                for card in (rd.get('cards') or []):
                    m = TEXTBOOK_RE.search(card.get('file') or '')
                    if m:
                        review_ch[int(m.group(1))] += 1
                        review_n += 1
            except (json.JSONDecodeError, OSError):
                pass
        review_top = review_ch.most_common(1)[0][0] if review_ch else None
        # is the sidecar coverage aligned with usage?
        aligned = sorted(set(sc_ch) & set(chapter_reads))
        result['kbs'][kb] = {
            'sessions': len(files), 'per_session': per_session,
            'n_questions': len(all_q), 'n_reads': total_reads,
            'chapter_reads': dict(sorted(chapter_reads.items())),
            'other_read_dirs': dict(other_reads.most_common(5)),
            'n_textbook_chapters': n_chapters,
            'top_chapter': top_ch, 'top_share_pct': top_share, 'top3_share_pct': top3_share,
            'top_chapter_position_pct': round(100.0 * top_ch / n_chapters, 1) if top_ch else None,
            'sidecar_chapters': sc_ch,
            'review_cards_by_chapter': dict(sorted(review_ch.items())),
            'review_cards_total_with_file': review_n,
            'review_top_chapter': review_top,
            'review_vs_session_top': (review_top == top_ch) if review_top else None,
            'sidecar_usage_aligned': aligned,
            'sidecar_chapters_without_usage': sorted(set(sc_ch) - set(chapter_reads)),
            'used_chapters_without_sidecar': sorted(set(chapter_reads) - set(sc_ch)),
            'question_samples': all_q[:12],
        }
    with open(os.path.join(data, 'real-usage.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    print('# 09 real usage across KBs (from agent session logs, read-only)')
    print('\n| KB | sessions | questions | read_document | chapters | top chapter | top share | top3 share | top ch position | sidecar chapters | aligned |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    for kb, s in result['kbs'].items():
        print(f"| {kb} | {s['sessions']} | {s['n_questions']} | {s['n_reads']} | {s['n_textbook_chapters']} | "
              f"ch{str(s['top_chapter']).zfill(2)} | {s['top_share_pct']}% | {s['top3_share_pct']}% | "
              f"{s['top_chapter_position_pct']}% into book | {s['sidecar_chapters']} | {s['sidecar_usage_aligned']} |")
    print('\n## per-KB chapter read distribution')
    for kb, s in result['kbs'].items():
        print(f"- {kb}: reads={s['chapter_reads']}")
        print(f"    sidecars={s['sidecar_chapters']}  aligned={s['sidecar_usage_aligned']}  "
              f"sidecar-but-unused={s['sidecar_chapters_without_usage']}  used-but-no-sidecar={s['used_chapters_without_sidecar']}")
        print(f"    review cards by chapter={s['review_cards_by_chapter']}  top={s['review_top_chapter']} "
              f"== session top? {s['review_vs_session_top']}")
        print(f"    sample questions: {[q[:40] for q in s['question_samples'][:4]]}")
    print('\nwrote data/real-usage.json')


if __name__ == '__main__':
    main()
