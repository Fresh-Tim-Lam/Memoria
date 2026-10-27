# -*- coding: utf-8 -*-
"""04_sessions.py — Q3: what did the owner ACTUALLY ask, and what did the agent
actually read?

Parses the real agent session logs (read-only) under
<KB>/.memoria/agent/sessions/*.jsonl:

  * every user/message (the real question distribution)
  * loop/end usage.prompt_tokens -> per-turn prompt cost, peak, total
  * compaction events (already-fired context pressure)
  * tool/call counts and every read_document / search_kb / read_kp / outline
    call with arguments and result sizes (trace/call carries result_chars and
    est_tokens, which we use to CALIBRATE tokens-per-char)

Writes data/sessions.json + data/questions.json.
Run: python 04_sessions.py
"""
import os
import re
import json
import glob
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402


def load_events(path):
    out = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def main():
    data = K.ensure_data_dir()
    root = K.KB_ROOTS[K.TARGET_KB]
    sess_dir = os.path.join(root, '.memoria', 'agent', 'sessions')
    files = sorted(glob.glob(os.path.join(sess_dir, '*.jsonl')))
    all_events = []
    per_file = []
    for p in files:
        ev = load_events(p)
        per_file.append({'file': os.path.basename(p), 'events': len(ev),
                         'bytes': os.path.getsize(p)})
        for e in ev:
            e['_file'] = os.path.basename(p)
            all_events.append(e)

    # ---------------- user questions
    questions = []
    for e in all_events:
        if e.get('type') == 'user/message':
            d = e.get('data') or {}
            txt = (d.get('text') or '').strip()
            if txt:
                questions.append({'file': e['_file'], 'seq': e.get('seq'),
                                  'time': e.get('time'), 'text': txt})
    # de-dup identical question text within same session
    seen = set()
    uniq_questions = []
    for q in questions:
        key = (q['file'], q['text'])
        if key in seen:
            continue
        seen.add(key)
        uniq_questions.append(q)

    # ---------------- turn cost
    turns = []
    for e in all_events:
        if e.get('type') == 'loop/end':
            d = e.get('data') or {}
            u = d.get('usage') or {}
            turns.append({
                'file': e['_file'], 'iterations': d.get('iterations'),
                'stop_reason': d.get('stop_reason'),
                'prompt_tokens': u.get('prompt_tokens'),
                'completion_tokens': u.get('completion_tokens'),
                'cache_read_tokens': u.get('cache_read_tokens'),
                'cache_miss_tokens': u.get('cache_miss_tokens'),
                'model': d.get('model'),
            })
    costs = [t['prompt_tokens'] for t in turns if t['prompt_tokens']]
    turn_summary = {
        'turns': len(turns),
        'prompt_tokens_total': sum(costs),
        'prompt_tokens_mean': round(sum(costs) / len(costs), 0) if costs else None,
        'prompt_tokens_p50': K.percentile(costs, 50),
        'prompt_tokens_p90': K.percentile(costs, 90),
        'prompt_tokens_max': max(costs) if costs else None,
        'context_window_1m_peak_pct': round(100.0 * max(costs) / 1_000_000, 2) if costs else None,
        'compaction_events': sum(1 for e in all_events if e.get('type') == 'compaction'),
        'compaction_chars_removed': sum((e.get('data') or {}).get('chars_removed', 0)
                                        for e in all_events
                                        if e.get('type') == 'compaction/prune'),
    }

    # ---------------- tool usage + reads
    tool_calls = {}
    tool_results = {}
    reads = []
    searches = []
    for e in all_events:
        if e.get('type') == 'tool/call':
            d = e.get('data') or {}
            name = d.get('name')
            tool_calls[name] = tool_calls.get(name, 0) + 1
        if e.get('type') == 'tool/result':
            d = e.get('data') or {}
            name = d.get('name')
            tool_results[name] = tool_results.get(name, 0) + 1
            if name == 'search_kb':
                searches.append({
                    'file': e['_file'],
                    'content': (d.get('content') or '')[:300],
                    'is_error': d.get('is_error'),
                })
    # trace/call gives args digest + result chars; join by tool order with tool/call
    calls_by_id = {}
    for e in all_events:
        if e.get('type') == 'tool/call':
            d = e.get('data') or {}
            calls_by_id[d.get('id')] = {'name': d.get('name'), 'arguments': d.get('arguments')}
    for e in all_events:
        if e.get('type') != 'tool/result':
            continue
        d = e.get('data') or {}
        call = calls_by_id.get(d.get('id')) or {}
        name = d.get('name') or call.get('name')
        content = d.get('content') or ''
        try:
            args = json.loads(call.get('arguments') or '{}')
        except json.JSONDecodeError:
            args = {}
        rec = {'file': e['_file'], 'tool': name, 'args': args,
               'result_chars': len(content), 'is_error': d.get('is_error'),
               'content_head': content[:160]}
        if name == 'read_document':
            reads.append(rec)
        if name in ('read_kp', 'outline', 'kb_overview', 'snippet', 'grep', 'search_kb'):
            rec['kind'] = name
    # trace/call: est_tokens vs result_chars calibration
    pairs = []
    for e in all_events:
        if e.get('type') == 'trace/call':
            d = e.get('data') or {}
            rc = d.get('result_chars')
            et = d.get('est_tokens')
            if rc and et:
                pairs.append((rc, et))
    ratios = sorted(et / rc for rc, et in pairs if 0 < rc <= 200000)
    calib = {
        'n_pairs': len(ratios),
        'tokens_per_char_p50': round(K.percentile(ratios, 50), 4) if ratios else None,
        'tokens_per_char_p10': round(K.percentile(ratios, 10), 4) if ratios else None,
        'tokens_per_char_p90': round(K.percentile(ratios, 90), 4) if ratios else None,
    }

    # mixed CJK/ASCII calibration: need CJK share per result; approximate with
    # the app's estimator: fit a,b in tokens = a*cjk + b*other using result text
    # only available as head; fall back to p50 ratio for the report.

    # write calibration for kpcore (uses CJK/other split). Solve from observed:
    # assume app estimator ~ ceil(chars/4) for ASCII and ~chars for CJK? We keep
    # our own conservative constants but record the observed aggregate ratio.
    if calib['tokens_per_char_p50']:
        # choose CJK=0.65 (typical) and solve other so that a random mix matches
        cjk_share = 26588 / 132905  # measured on 教材/03 as representative
        cjk_const = 0.70
        other_const = max(0.05, (calib['tokens_per_char_p50'] - cjk_share * cjk_const)
                          / max(1e-6, (1 - cjk_share)))
        note = ('empirical: p50 tokens/char over the session own trace/call '
                f"observations (n={len(ratios)}); uniform estimate for markdown")
        with open(os.path.join(data, 'token_calibration.json'), 'w', encoding='utf-8') as f:
            json.dump({'uniform_tokens_per_char': calib['tokens_per_char_p50'],
                       'cjk_tokens_per_char': round(cjk_const, 3),
                       'other_tokens_per_char': round(other_const, 3),
                       'note': note}, f, ensure_ascii=False, indent=1)

    # ---------------- per-turn: how much tool output entered the context
    session_ev = [e for e in all_events if e['_file'].startswith('session-')]
    turn_tool = []
    acc_chars = 0
    acc_tools = {}
    for e in session_ev:
        if e.get('type') == 'tool/result':
            d = e.get('data') or {}
            c = len(d.get('content') or '')
            acc_chars += c
            acc_tools[d.get('name')] = acc_tools.get(d.get('name'), 0) + 1
        elif e.get('type') == 'loop/end':
            turn_tool.append({
                'tool_result_chars': acc_chars,
                'tool_result_tokens_est': round(acc_chars * (calib['tokens_per_char_p50'] or 0.42)),
                'tool_calls': dict(acc_tools),
            })
            acc_chars = 0
            acc_tools = {}
    for i, tt in enumerate(turn_tool):
        if i < len(turns):
            turns[i]['tool_result_chars'] = tt['tool_result_chars']
            turns[i]['tool_result_tokens_est'] = tt['tool_result_tokens_est']
            turns[i]['tool_calls'] = tt['tool_calls']
    tool_summary = {
        'read_document_total_chars': sum(r['result_chars'] for r in reads),
        'read_document_calls': len(reads),
        'read_document_with_window': sum(1 for r in reads
                                         if 'offset' in r['args'] or 'limit' in r['args']),
        'read_document_whole_file': sum(1 for r in reads
                                        if 'offset' not in r['args'] and 'limit' not in r['args']),
        'read_document_by_path': {},
        'tool_result_tokens_total_est': sum(t.get('tool_result_tokens_est', 0) for t in turns),
    }
    for r in reads:
        p = r['args'].get('path', '?')
        tool_summary['read_document_by_path'][p] = \
            tool_summary['read_document_by_path'].get(p, 0) + 1

    # ---------------- write
    out = {
        'session_files': per_file,
        'questions': uniq_questions,
        'question_count_raw': len(questions),
        'turn_cost': turn_summary,
        'turns': turns,
        'tool_calls': tool_calls,
        'tool_results': tool_results,
        'reads': reads,
        'searches': searches,
        'read_summary': tool_summary,
        'token_calibration': calib,
    }
    with open(os.path.join(data, 'sessions.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(os.path.join(data, 'questions.json'), 'w', encoding='utf-8') as f:
        json.dump(uniq_questions, f, ensure_ascii=False, indent=1)

    # ---------------- print
    print('# 04 real agent session (数字通信原理)')
    print(f"session files: {len(per_file)} -> {per_file}")
    print(f"\nuser questions: {len(uniq_questions)} unique / {len(questions)} raw")
    for i, q in enumerate(uniq_questions, 1):
        print(f"{i:>2}. {q['text'][:160]}")
    print('\n## per-turn prompt cost (loop/end)')
    print('| # | iterations | prompt_tokens | completion | cache_read | cache_miss | stop_reason |')
    print('|---|---|---|---|---|---|---|')
    for i, t in enumerate(turns, 1):
        print(f"| {i} | {t['iterations']} | {t['prompt_tokens']:,} | {t['completion_tokens']} | "
              f"{t['cache_read_tokens']:,} | {t['cache_miss_tokens']:,} | {t['stop_reason']} |")
    print(f"\n- turns={turn_summary['turns']}, total prompt={turn_summary['prompt_tokens_total']:,}, "
          f"mean={turn_summary['prompt_tokens_mean']:,}, p90={turn_summary['prompt_tokens_p90']:,.0f}, "
          f"peak={turn_summary['prompt_tokens_max']:,} ({turn_summary['context_window_1m_peak_pct']}% of 1M)")
    print(f"- compaction events={turn_summary['compaction_events']}, "
          f"pruned chars={turn_summary['compaction_chars_removed']:,}")
    print('\n## tool usage')
    for k, v in sorted(tool_calls.items(), key=lambda kv: -kv[1]):
        print(f"- {k}: {v}")
    print('\n## read_document calls')
    print('| file | tool | args | result chars |')
    print('|---|---|---|---|')
    for r in reads:
        print(f"| {r['file']} | {r['tool']} | {json.dumps(r['args'], ensure_ascii=False)[:100]} | {r['result_chars']:,} |")
    rs = tool_summary
    print(f"\n- read_document calls={rs['read_document_calls']}, with offset/limit window={rs['read_document_with_window']}, "
          f"whole-file={rs['read_document_whole_file']}, total result chars={rs['read_document_total_chars']:,} "
          f"(~{round(rs['read_document_total_chars']*0.4237):,} tokens)")
    print(f"- read paths: {rs['read_document_by_path']}")
    print(f"- tool-result tokens over the whole session (est)={rs['tool_result_tokens_total_est']:,}")
    print('\n## search_kb results (retrieval quality)')
    for s in searches:
        ok = 'ERROR' if s['is_error'] else ('MISS' if ('未在知识库' in s['content'] or '未找到' in s['content']) else 'HIT')
        print(f"- {ok}: {s['content'][:150]}")
    print(f"\n## token calibration from trace/call: n={calib['n_pairs']}, "
          f"tokens/char p50={calib['tokens_per_char_p50']} p10={calib['tokens_per_char_p10']} p90={calib['tokens_per_char_p90']}")
    print('\nwrote data/sessions.json, data/questions.json, data/token_calibration.json')


if __name__ == '__main__':
    main()
