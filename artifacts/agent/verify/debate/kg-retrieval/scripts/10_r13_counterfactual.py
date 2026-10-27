# -*- coding: utf-8 -*-
"""10_r13_counterfactual.py — R13 反事实检验（task-197）。

固定 sha256 语料快照，回答：
  A. 三场景（S1 早期 / S2 中期 / S3 大章） × 三策略（A 书序 / B 前沿+前置 / C 随机）
     在 20% 预算下的覆盖率、实际花费、达到 100% 所需预算。
  B. 用真实 KB 的真实章节使用分布（会话日志 read_document，见 09）重复 A/B/C。
  C. 数字通信原理的「前沿信号」可得性（会话读取 / 批注宏 / mtime / sidecar mtime）。
  D. 现状 sidecar 覆盖 vs 使用（现状是"按书序建"还是"哪里用建哪里"）。

口径说明（两种都报，避免单一假设决定结论）：
  primary : 预算 = 20% × 全书「建造成本」(读一遍正文 + 写条目)；
            skeleton（全库标题骨架）先从预算扣除 → semantic budget。
  read    : 预算 = 20% × 全书「正文 token」(R13 原口径)；
            skeleton 仍先从预算扣除（更保守）。
  章节建造成本 = 正文 token + 标题数 × 134.6 字 × 0.4237。

输出 data/r13-counterfactual.json；打印全部表。
Run: python 10_r13_counterfactual.py
"""
import os
import re
import json
import random
import sys
import collections
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402

TARGET = K.TARGET_KB
BUDGET_FRAC = 0.20
TOK_PER_CHAR = 0.4237
ENTRY_CHARS_PER_HEADING = 14.6 + 40 + 80
HEADING_RE = re.compile(r'^#{1,6}\s+(.+?)\s*$')
CH_RE = re.compile(r'教材[/\\](\d+)[_第]')


def chapter_files(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('.memoria', '.git')]
        for fn in filenames:
            if not fn.lower().endswith('.md'):
                continue
            p = os.path.join(dirpath, fn)
            rel = K.rel(p, root)
            if 'pipeline_old' in rel or not rel.startswith('教材/'):
                continue
            m = CH_RE.search(rel)
            if not m:
                continue
            ch = int(m.group(1))
            text = K.read_text(p)
            heads = sum(1 for l in text.split('\n') if HEADING_RE.match(l))
            out[ch] = {'rel': rel, 'path': p, 'chars': len(text), 'headings': heads,
                       'tokens': len(text) * TOK_PER_CHAR}
    return out


class Costs:
    def __init__(self, chapters):
        self.content = {ch: v['tokens'] for ch, v in chapters.items()}
        self.entries = {ch: v['headings'] * ENTRY_CHARS_PER_HEADING * TOK_PER_CHAR
                        for ch, v in chapters.items()}
        self.build = {ch: self.content[ch] + self.entries[ch] for ch in chapters}
        self.total_content = sum(self.content.values())
        self.total_build = sum(self.build.values())
        self.skeleton = sum(v['headings'] for v in chapters.values()) * 14.1 * TOK_PER_CHAR
        self.n = max(chapters) if chapters else 0


def coverage(order, weights, budget, costs):
    """Build chapters along `order` while budget allows.

    Returns coverage (usage-weighted), spent, list of built chapters,
    spend on unneeded chapters, and the budget needed to reach 100% along
    this order (counting all chapters built before the needed ones).
    """
    spent = 0.0
    built = []
    for ch in order:
        c = costs.build.get(ch)
        if c is None or spent + c > budget:
            continue
        built.append(ch)
        spent += c
    total_w = sum(weights.values()) or 1.0
    cov = sum(weights.get(ch, 0) for ch in built) / total_w
    built_set = set(built)
    waste = sum(costs.build[ch] for ch in built if ch not in weights)
    # budget to reach 100% along the order (accumulate ALL chapters crossed)
    need = 0.0
    covered = set()
    budget_100 = None
    for ch in order:
        if ch not in costs.build:
            continue
        need += costs.build[ch]
        if ch in weights:
            covered.add(ch)
        if covered >= set(weights):
            budget_100 = need
            break
    return {'built': sorted(built), 'spent': round(spent), 'coverage': round(cov, 4),
            'waste_on_unneeded': round(waste),
            'budget_for_100': None if budget_100 is None else round(budget_100)}


def frontier_order(f, n_chapters):
    """前沿 → 前置链（f-1 … 1）→ 后续章（f+1 …）。前置是理解前提，优先于后续。"""
    order = [f]
    for ch in range(f - 1, 0, -1):
        order.append(ch)
    for ch in range(f + 1, n_chapters + 1):
        order.append(ch)
    return order


def coverage_frac(order, weights, budget, costs):
    """Like coverage() but a chapter may be built partially (section-level,
    R10 支持按小节切分) — the last chapter consumes the remaining budget
    proportionally to its section cost."""
    spent = 0.0
    cover = 0.0
    built = []
    total_w = sum(weights.values()) or 1.0
    for ch in order:
        c = costs.build.get(ch)
        if not c:
            continue
        if spent >= budget:
            break
        frac = min(1.0, (budget - spent) / c)
        cover += weights.get(ch, 0) * frac
        spent += c * frac
        built.append((ch, round(frac, 3)))
        if frac < 1.0:
            break
    budget_100 = sum(costs.build.get(ch, 0) for ch in weights)
    return {'built': built, 'spent': round(spent), 'coverage': round(cover / total_w, 4),
            'budget_for_100': round(budget_100), 'fractional': True}


def greedy_density(weights, budget, costs):
    """Diagnostic upper-ish bound: build needed chapters by usage-per-token
    density (frontier-aware), partial last. Needs per-chapter usage weights."""
    order = sorted(weights, key=lambda ch: -(weights[ch] / max(1.0, costs.build.get(ch, 1e9))))
    return coverage_frac(order, weights, budget, costs)


def scenario_block(chapters, costs, budget, label):
    res = {}
    s1_w = {3: 1.0}
    raw2 = {5: costs.content[5], 6: costs.content[6], 7: costs.content[7]}
    s2_w = {k: v / sum(raw2.values()) for k, v in raw2.items()}
    s3_w = {8: 1.0}
    for name, w, fc in [
        ('S1 早期（用到 ch3；19 问实测全部落 ch3）', s1_w, [3]),
        ('S2 中期（用到 ch5–7；假设）', s2_w, [5, 6, 7]),
        ('S3 大章（用到 ch8；假设）', s3_w, [8]),
    ]:
        rows = []
        A = coverage(list(range(1, costs.n + 1)), w, budget, costs)
        rows.append({'policy': 'A 书序', **A})
        brows = []
        for f in fc:
            B = coverage(frontier_order(f, costs.n), w, budget, costs)
            brows.append({'frontier': f, **B})
        rows.append({'policy': 'B 前沿+前置链', 'variants': brows,
                     'best_cov': max(b['coverage'] for b in brows),
                     'worst_cov': min(b['coverage'] for b in brows)})
        # B0: frontier chapter only (no prerequisite) — the cheapest possible policy
        b0 = []
        for f in fc:
            B0 = coverage([f], w, budget, costs)
            b0.append({'frontier': f, **B0})
        rows.append({'policy': 'B0 只建前沿章(无前置)', 'variants': b0,
                     'best_cov': max(b['coverage'] for b in b0)})
        # B-frac: same frontier order, but the frontier chapter may be built
        # partially (section-level). This is the fair model when one chapter
        # alone exceeds the budget (real case: 计算机网路 ch05, R10 支持按节切分).
        bfrac = [{'frontier': f, **coverage_frac(frontier_order(f, costs.n), w, budget, costs)}
                 for f in fc]
        rows.append({'policy': 'B-frac 前沿+部分章', 'variants': bfrac,
                     'best_cov': max(b['coverage'] for b in bfrac)})
        rows.append({'policy': 'D 使用密度贪心(诊断上界)', **greedy_density(w, budget, costs)})
        rng = random.Random(20261027)
        covs = []
        for _ in range(2000):
            order = list(range(1, costs.n + 1))
            rng.shuffle(order)
            covs.append(coverage(order, w, budget, costs)['coverage'])
        rows.append({'policy': 'C 随机(2000 次)', 'coverage': round(sum(covs) / len(covs), 4),
                     'p10': round(K.percentile(covs, 10), 4), 'p90': round(K.percentile(covs, 90), 4)})
        res[name] = {'needed_weights': {str(k): round(v, 4) for k, v in w.items()}, 'rows': rows}
    return {label: res}


def main():
    data = K.ensure_data_dir()
    snap = json.load(open(os.path.join(data, 'corpus-snapshot.json'), encoding='utf-8'))
    out = {'snapshot': snap['taken_at'], 'budget_frac': BUDGET_FRAC, 'token_per_char': TOK_PER_CHAR}

    # ---------------- target KB
    root = K.KB_ROOTS[TARGET]
    chapters = chapter_files(root)
    costs = Costs(chapters)
    budget_primary = BUDGET_FRAC * costs.total_build
    budget_read = BUDGET_FRAC * costs.total_content
    b_primary_sem = budget_primary - costs.skeleton
    b_read_sem = budget_read - costs.skeleton
    out['setup_target'] = {
        'chapters': costs.n, 'book_content_tokens': round(costs.total_content),
        'build_all_tokens': round(costs.total_build), 'skeleton_tokens': round(costs.skeleton),
        'budget_primary_20pct': round(budget_primary),
        'budget_primary_semantic_after_skeleton': round(b_primary_sem),
        'budget_read_20pct': round(budget_read),
        'budget_read_semantic_after_skeleton': round(b_read_sem),
        'chapter_build_costs': {ch: round(costs.build[ch]) for ch in sorted(costs.build)},
        'chapter_content_tokens': {ch: round(costs.content[ch]) for ch in sorted(costs.content)},
    }
    out['counterfactual_primary'] = scenario_block(chapters, costs, b_primary_sem, 'primary')
    out['counterfactual_read_basis'] = scenario_block(chapters, costs, b_read_sem, 'read')

    # ---------------- real KB validation
    usage = json.load(open(os.path.join(data, 'real-usage.json'), encoding='utf-8'))
    real = {}
    for kb, u in usage['kbs'].items():
        if u['n_reads'] < 10:
            continue
        rroot = K.KB_ROOTS[kb]
        rch = chapter_files(rroot)
        if not rch:
            continue
        rc = Costs(rch)
        rbudget = BUDGET_FRAC * rc.total_build - rc.skeleton
        w = {int(ch): float(n) for ch, n in u['chapter_reads'].items()
             if int(ch) in rc.build and n > 0}
        if not w:
            continue
        A = coverage(list(range(1, rc.n + 1)), w, rbudget, rc)
        top = max(w, key=w.get)
        B = coverage(frontier_order(top, rc.n), w, rbudget, rc)
        B0 = coverage([top], w, rbudget, rc)
        Bfrac = coverage_frac(frontier_order(top, rc.n), w, rbudget, rc)
        D = greedy_density(w, rbudget, rc)
        rng = random.Random(20261027)
        covs = []
        for _ in range(2000):
            order = list(range(1, rc.n + 1))
            rng.shuffle(order)
            covs.append(coverage(order, w, rbudget, rc)['coverage'])
        real[kb] = {
            'chapters': rc.n, 'book_content_tokens': round(rc.total_content),
            'budget_20pct_semantic': round(rbudget),
            'chapter_build_costs': {ch: round(rc.build[ch]) for ch in sorted(rc.build)},
            'usage_weights_reads': {str(k): int(v) for k, v in sorted(w.items())},
            'top_usage_chapter': top,
            'top_chapter_position_pct': round(100.0 * top / rc.n, 1),
            'A_book_order': A, 'B_frontier_first': B, 'B0_frontier_only': B0,
            'B_frac_frontier': Bfrac, 'D_density_greedy': D,
            'C_random': {'coverage': round(sum(covs) / len(covs), 4),
                         'p10': round(K.percentile(covs, 10), 4),
                         'p90': round(K.percentile(covs, 90), 4)},
        }
    out['real_kb_validation'] = real

    # ---------------- frontier signals
    sessions = json.load(open(os.path.join(data, 'sessions.json'), encoding='utf-8'))
    read_by_ch = collections.Counter()
    for r in sessions['reads']:
        m = CH_RE.search(r['args'].get('path') or '')
        if m:
            read_by_ch[int(m.group(1))] += 1
    sig = []
    for ch in sorted(chapters):
        info = chapters[ch]
        text = K.read_text(info['path'])
        anno = len(re.findall(r'\[\[\\[hc]:', text))
        mtime = os.path.getmtime(info['path'])
        side = os.path.join(root, '.memoria', 'sidecars',
                            info['rel'].replace('.md', '.memoria.yaml'))
        smtime = os.path.getmtime(side) if os.path.isfile(side) else None
        sig.append({'chapter': ch, 'session_reads': read_by_ch.get(ch, 0),
                    'annotation_macros': anno,
                    'mtime': datetime.datetime.fromtimestamp(mtime).isoformat(timespec='minutes'),
                    'sidecar': os.path.isfile(side),
                    'sidecar_mtime': datetime.datetime.fromtimestamp(smtime).isoformat(timespec='minutes') if smtime else None})
    for i, x in enumerate(sorted(sig, key=lambda y: y['mtime'], reverse=True), 1):
        x['mtime_rank'] = i
    out['frontier_signals'] = sorted(sig, key=lambda x: -x['session_reads'])

    # ---------------- sidecar vs usage
    out['sidecar_vs_usage'] = {
        kb: {'sidecar_chapters': u['sidecar_chapters'],
             'used_chapters': sorted(int(x) for x in u['chapter_reads']),
             'overlap': u['sidecar_usage_aligned'],
             'sidecar_but_unused': u['sidecar_chapters_without_usage'],
             'used_but_no_sidecar': u['used_chapters_without_sidecar']}
        for kb, u in usage['kbs'].items()
    }

    with open(os.path.join(data, 'r13-counterfactual.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---------------- print
    s = out['setup_target']
    print('# 10 R13 counterfactual')
    print(f"\n## setup (数字通信原理, snapshot {out['snapshot']})")
    print(f"- chapters={s['chapters']}, content tokens={s['book_content_tokens']:,}, "
          f"build-all tokens={s['build_all_tokens']:,}, skeleton={s['skeleton_tokens']:,}")
    print(f"- budget primary(20% of build-all)={s['budget_primary_20pct']:,} "
          f"→ semantic after skeleton {s['budget_primary_semantic_after_skeleton']:,}")
    print(f"- budget read-basis(20% of content)={s['budget_read_20pct']:,} "
          f"→ semantic after skeleton {s['budget_read_semantic_after_skeleton']:,}")
    print(f"- chapter build costs: {s['chapter_build_costs']}")

    def print_block(block, title):
        print(f"\n## A. counterfactual — {title}")
        print('| scenario | policy | coverage@20% | spent tok | wasted on unneeded | budget for 100% |')
        print('|---|---|---|---|---|---|')
        for sname, sb in block.items():
            for row in sb['rows']:
                if 'variants' in row:
                    for b in row['variants']:
                        print(f"| {sname} | {row['policy']}(f=ch{b['frontier']:02d}) | {b['coverage']*100:.1f}% | "
                              f"{b.get('spent', 0):,} | {b.get('waste_on_unneeded', 0):,} | "
                              f"{b['budget_for_100'] if b.get('budget_for_100') else '>20%'} |")
                else:
                    print(f"| {sname} | {row['policy']} | {row.get('coverage', 0)*100:.1f}% | "
                          f"{row.get('spent', 0):,} | {row.get('waste_on_unneeded', 0):,} | "
                          f"{row.get('budget_for_100') if row.get('budget_for_100') else '>20%'} |")

    print_block(out['counterfactual_primary']['primary'], 'primary: 20% of build-all')
    print_block(out['counterfactual_read_basis']['read'], 'read-basis: 20% of content (R13 原口径)')

    print('\n## B. REAL-KB validation (usage weights = real read_document counts)')
    print('| KB | chapters | content tok | A book-order | B frontier+prereq | B0 frontier-only | B-frac partial | D density-greedy | C random | top ch / pos |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for kb, r in out['real_kb_validation'].items():
        def fmt(x):
            b100 = x['budget_for_100']
            return f"{x['coverage']*100:.1f}%" + (f" (100%需 {b100:,})" if b100 else "")
        print(f"| {kb} | {r['chapters']} | {r['book_content_tokens']:,} | {fmt(r['A_book_order'])} | "
              f"{fmt(r['B_frontier_first'])} | {fmt(r['B0_frontier_only'])} | {fmt(r['B_frac_frontier'])} | "
              f"{r['D_density_greedy']['coverage']*100:.1f}% | {r['C_random']['coverage']*100:.1f}% | "
              f"ch{r['top_usage_chapter']:02d} / {r['top_chapter_position_pct']}% |")

    print('\n## C. frontier signals (数字通信原理)')
    print('| ch | session reads | annotation macros | mtime | mtime rank | sidecar | sidecar mtime |')
    print('|---|---|---|---|---|---|---|')
    for x in out['frontier_signals']:
        print(f"| ch{x['chapter']:02d} | {x['session_reads']} | {x['annotation_macros']} | {x['mtime']} | "
              f"{x['mtime_rank']} | {x['sidecar']} | {x['sidecar_mtime']} |")

    print('\n## D. sidecar coverage vs real usage')
    for kb, x in out['sidecar_vs_usage'].items():
        print(f"- {kb}: sidecars={x['sidecar_chapters']} used={x['used_chapters']} overlap={x['overlap']} "
              f"sidecar-but-unused={x['sidecar_but_unused']} used-but-no-sidecar={x['used_but_no_sidecar']}")
    print('\nwrote data/r13-counterfactual.json')


if __name__ == '__main__':
    main()
