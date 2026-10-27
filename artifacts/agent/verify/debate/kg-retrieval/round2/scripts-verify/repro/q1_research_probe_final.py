# -*- coding: utf-8 -*-
"""q1_research_probe.py — Q1「KP 边界重算会付出什么代价」专职研究员自算脚本。

固定快照：round2/frozen/数字通信原理（26 md / 11 sidecar，sha256 见 round2/frozen/MANIFEST.json，
对应 2026-10-27T14:09:46）。只读冻结副本；不读、不写活动库。

产出（round2/data/q1-research.json + 打印表）：
  P0  快照自检（MANIFEST sha256 / 26 md / 11 sidecar / live 漂移）
  P1  KP 盘点：角色、start 是否标题行、三种尺寸口径（hint / resolved / heading）
  P2  anchor_verified（R1 三判据；strict / section / context / lenient 四档）
  P3  选项 A：A1 最小修复 / A2 全部 end=下一同级标题；受影响的 KP 数与尺寸变化
  P4  选项 B：B1 按 KP 预算重切 / B2 按文件结构重切；新 KP 数、旧 KP 一对多扇出、迁移冲突
  P5  选项 C：切片视图（leaf section + 200–1200 打包）；切片数、每 KP 映射几片、孤儿率（多 scope）
  P6  用户数据面：links / edges / cards（本库）
  P7  描述生成量（C 的隐性成本）

Run:
  python artifacts/agent/verify/debate/kg-retrieval/round2/scripts/q1_research_probe.py
"""
import os
import re
import json
import hashlib
import collections
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # kg-retrieval/
FROZEN = r'D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval\round2\frozen\数字通信原理'
MANIFEST = r'D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval\round2\frozen\MANIFEST.json'
DATA = r'D:\AAA_Jupyter\Memoria\artifacts\agent\verify\debate\kg-retrieval\round2\scripts-verify\repro'
OUT = os.path.join(DATA, 'q1-research.json')
LIVE = r'D:\AAA_Courses\数字通信原理'

BUDGET_CHARS = 1200      # 切片预算上限（R7.1 / O-B1 口径：>1200 字视为过粗）
MIN_SLICE = 200          # B 提案的 200–1200 下限（软约束）
TOKEN_PER_CHAR = 0.4237  # 本仓标定（data/token_calibration.json，105 条 trace 均值）

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
KEY_LINE_RE = re.compile(r'^\s*(id|name|range|start|end|snippet|line_hint|tags|links|edges|'
                         r'occurrence|targets|edge_type|target_edges|pool|instances|excluded|'
                         r'source_id|anchor_text|wrapped|relevance|schema_version|file|'
                         r'knowledge_points|type|file_desc|description|note)\s*:')


# ------------------------------------------------------------------ utils
def read_text(p):
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def norm_snip(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def norm_text(text):
    out, linemap = [], []
    line, prev_space = 1, True
    for ch in text:
        if ch == '\n':
            line += 1
            continue
        if ch.isspace():
            if prev_space:
                continue
            out.append(' ')
            linemap.append(line)
            prev_space = True
        else:
            out.append(ch)
            linemap.append(line)
            prev_space = False
    return ''.join(out), linemap


def pct(x, n):
    return round(100.0 * x / n, 1) if n else 0.0


def pctl(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


def dist(vals):
    return {'n': len(vals), 'p50': pctl(vals, 50), 'p90': pctl(vals, 90),
            'max': round(max(vals), 2) if vals else None,
            'mean': round(sum(vals) / len(vals), 2) if vals else None,
            'min': round(min(vals), 2) if vals else None}


def to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


# -------------------------------------------------------------- sidecar parser
def parse_sidecar(path):
    """Own parser. Handles folded snippet scalars (indented continuation lines)."""
    raw = read_text(path).splitlines()
    lines, i = [], 0
    while i < len(raw):
        ln = raw[i]
        m = re.match(r'^(\s*)snippet:\s?(.*)$', ln)
        if not m:
            lines.append(ln)
            i += 1
            continue
        ind = len(m.group(1))
        parts = [m.group(2)]
        i += 1
        while i < len(raw):
            nxt = raw[i]
            if not nxt.strip():
                break
            mind = len(nxt) - len(nxt.lstrip(' '))
            if mind > ind and not KEY_LINE_RE.match(nxt):
                parts.append(nxt.strip())
                i += 1
            else:
                break
        lines.append(' ' * ind + 'snippet: ' + ' '.join(p for p in parts if p != ''))

    meta_file, kps, cur, section = None, [], None, None
    links, edges = [], []
    for ln in lines:
        mf = re.match(r'^file:\s*(.*)$', ln)
        if mf is not None:
            meta_file = mf.group(1).strip().strip('"\'')
            continue
        if re.match(r'^\s*-\s+id:\s*', ln):
            if cur:
                kps.append(cur)
            cur = {'id': re.sub(r'^\s*-\s+id:\s*', '', ln).strip().strip('"\''),
                   'name': None,
                   'start': {'snippet': None, 'line_hint': None},
                   'end': {'snippet': None, 'line_hint': None}}
            section = None
            continue
        if cur is None:
            if re.match(r'^\s*links:\s*$', ln):
                section = 'links'
            elif re.match(r'^\s*edges:\s*$', ln):
                section = 'edges'
            elif section == 'links':
                mt = re.search(r'targets:\s*$', ln)
                if mt:
                    pass
            continue
        m = re.match(r'^(\s+)([a-zA-Z_]+):\s*(.*)$', ln)
        if not m:
            continue
        ind = len(m.group(1))
        key, val = m.group(2), m.group(3).strip()
        if key in ('start', 'end'):
            section = key
            continue
        if key in ('snippet', 'line_hint') and section in ('start', 'end'):
            if key == 'snippet':
                cur[section]['snippet'] = val.strip('"\'')
            else:
                cur[section]['line_hint'] = to_int(val)
            continue
        if ind <= 2:
            section = None
            if key == 'name':
                cur['name'] = val.strip('"\'')
            elif key == 'links':
                section = 'links'
            elif key == 'edges':
                section = 'edges'
    if cur:
        kps.append(cur)

    # links / edges: line-based scan (list items start at column 0)
    raw_lines = read_text(path).split('\n')
    def block_after(key):
        for idx, ln in enumerate(raw_lines):
            if ln.rstrip() == key + ':':
                out, i = [], idx + 1
                while i < len(raw_lines):
                    s = raw_lines[i]
                    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*:', s):
                        break
                    out.append(s)
                    i += 1
                return out
        return []

    links = []
    blk = block_after('links')
    i = 0
    while i < len(blk):
        m = re.match(r'^- anchor_text:\s*(.*)$', blk[i])
        if not m:
            i += 1
            continue
        blk_item = {'anchor_text': m.group(1).strip(), 'targets': [], 'source_id': None}
        i += 1
        while i < len(blk) and not re.match(r'^- anchor_text:', blk[i]):
            s = blk[i]
            mt = re.match(r'^\s*targets:\s*$', s)
            ms = re.match(r'^\s*source_id:\s*(\S+)$', s)
            if ms:
                blk_item['source_id'] = ms.group(1)
            if mt:
                i += 1
                while i < len(blk) and re.match(r'^\s+- (.+)$', blk[i]):
                    blk_item['targets'].append(blk[i].strip()[2:].strip())
                    i += 1
                continue
            i += 1
        links.append(blk_item)
    edges = []
    blk = block_after('edges')
    i = 0
    while i < len(blk):
        m = re.match(r'^- type:\s*(\S+)$', blk[i])
        if not m:
            i += 1
            continue
        item = {'type': m.group(1), 'source_id': None, 'targets': []}
        i += 1
        while i < len(blk) and not re.match(r'^- type:', blk[i]):
            s = blk[i]
            ms = re.match(r'^\s*source_id:\s*(\S+)$', s)
            if ms:
                item['source_id'] = ms.group(1)
            if re.match(r'^\s*targets:\s*$', s):
                i += 1
                while i < len(blk) and re.match(r'^\s+- (.+)$', blk[i]):
                    item['targets'].append(blk[i].strip()[2:].strip())
                    i += 1
                continue
            i += 1
        edges.append(item)
    return {'file': meta_file, 'kps': kps, 'links': links, 'edges': edges}


# -------------------------------------------------------------- markdown helpers
def headings_of(lines):
    out = []
    for i, ln in enumerate(lines, 1):
        m = HEADING_RE.match(ln)
        if m:
            out.append({'line': i, 'level': len(m.group(1)), 'text': m.group(2).strip()})
    return out


def line_chars(lines, a, b):
    if b < a or a < 1:
        return 0
    b = min(b, len(lines))
    seg = lines[a - 1:b]
    return sum(len(x) for x in seg) + max(0, len(seg) - 1)


def nearest_heading_before(hs, line):
    owner, idx = None, -1
    for k, h in enumerate(hs):
        if h['line'] <= line:
            owner, idx = h, k
        else:
            break
    return owner, idx


def section_end(hs, owner_idx, eof):
    """End line owned by heading owner_idx (next heading of level <= owner level)."""
    if owner_idx < 0:
        return eof
    owner = hs[owner_idx]
    for h in hs[owner_idx + 1:]:
        if h['level'] <= owner['level']:
            return h['line'] - 1
    return eof


# -------------------------------------------------------------- anchors
def occurrences(nt, snip):
    occ, i = [], nt.find(snip)
    while i != -1 and len(occ) < 5000:
        occ.append(i)
        i = nt.find(snip, i + 1)
    return occ


def resolve(nt, linemap, snip, hint):
    s = norm_snip(snip)
    d = {'snippet': s, 'chars': len(s), 'matches': 0, 'unique': False,
         'line': None, 'hint_verified': False, 'found': False, 'occ_lines': []}
    if not s:
        return d
    occ = occurrences(nt, s)
    d['matches'] = len(occ)
    d['unique'] = len(occ) == 1
    ml = [linemap[o] for o in occ]
    d['occ_lines'] = sorted(set(ml))[:60]
    if not occ:
        return d
    d['found'] = True
    h = hint
    if h is not None:
        best = min(occ, key=lambda o: abs(linemap[o] - h))
        d['line'] = linemap[best]
        d['hint_verified'] = h in ml
    else:
        d['line'] = ml[0]
    return d


# -------------------------------------------------------------- slicing
def protected_ranges(lines, start, end):
    """Ranges (1-based inclusive) of display-math blocks / code fences that must
    not be split. Conservative: unclosed block extends to `end`."""
    prot, in_math, in_code, s0 = [], False, False, None
    for i in range(start, end + 1):
        ln = lines[i - 1]
        st = ln.strip()
        if st.startswith('```'):
            if not in_code:
                in_code, s0 = True, i
            else:
                prot.append((s0, i)); in_code = False
        elif st.startswith('$$'):
            if not in_math:
                in_math, s0 = True, i
            else:
                prot.append((s0, i)); in_math = False
    if in_math:
        prot.append((s0, end))
    if in_code:
        prot.append((s0, end))
    return prot


def atoms(lines, start, end):
    """Blank-line-separated paragraph atoms; display-math/code blocks kept whole."""
    if end < start:
        return []
    prot = protected_ranges(lines, start, end)
    ranges = []

    def inside_prot(i, j):
        for a, b in prot:
            if i <= b and j >= a:
                return (a, b)
        return None

    i = start
    while i <= end:
        # if i is inside a protected range, emit it atomically
        pr = inside_prot(i, i)
        if pr:
            a, b = max(pr[0], start), min(pr[1], end)
            ranges.append((a, b))
            i = b + 1
            continue
        j = i
        while j <= end:
            if lines[j - 1].strip() == '':
                # blank line inside math block belongs to the block; already handled
                break
            if inside_prot(j + 1, j + 1) and j + 1 <= end:
                # next line starts a protected block -> close atom before it
                break
            j += 1
        ranges.append((i, j))
        i = j + 1
    # merge adjacent atoms if the blank line between them is inside a protected range
    out = []
    for r in ranges:
        if out:
            prev = out[-1]
            gap = prev[1] + 1
            if any(a <= gap <= b for a, b in prot):
                out[-1] = (prev[0], r[1])
                continue
        out.append(r)
    return out


def split_long(lines, a, b, budget):
    """Split one atom > budget at line boundaries (last resort)."""
    out, cur, chars = [], a, 0
    for i in range(a, b + 1):
        L = len(lines[i - 1]) + 1
        if chars + L > budget and i > cur:
            out.append((cur, i - 1))
            cur, chars = i, 0
        chars += L
    if cur <= b:
        out.append((cur, b))
    return out


def pack(lines, start, end, budget=BUDGET_CHARS, min_chars=MIN_SLICE):
    """Greedy pack atoms into slices <= budget; soft min_chars."""
    out = []
    cur_a, cur_b, cur_chars = None, None, 0
    for (a, b) in atoms(lines, start, end):
        seg_chars = line_chars(lines, a, b)
        if seg_chars > budget:
            # close current, then split the long atom
            if cur_a is not None:
                out.append((cur_a, cur_b)); cur_a = None; cur_chars = 0
            out.extend(split_long(lines, a, b, budget))
            continue
        if cur_a is None:
            cur_a, cur_b, cur_chars = a, b, seg_chars
        elif cur_chars + seg_chars + 1 > budget and cur_chars >= min_chars:
            out.append((cur_a, cur_b))
            cur_a, cur_b, cur_chars = a, b, seg_chars
        else:
            cur_b, cur_chars = b, cur_chars + seg_chars + 1
    if cur_a is not None:
        out.append((cur_a, cur_b))
    return out


def leaf_sections(lines, hs):
    """Non-overlapping partition at every heading line: (start, end)."""
    out = []
    if not hs:
        return [(1, len(lines))] if len(lines) else []
    if hs[0]['line'] > 1:
        out.append((1, hs[0]['line'] - 1))
    for k, h in enumerate(hs):
        s = h['line']
        e = hs[k + 1]['line'] - 1 if k + 1 < len(hs) else len(lines)
        if e >= s:
            out.append((s, e))
    return out


# ------------------------------------------------------------------ main
def main():
    os.makedirs(DATA, exist_ok=True)
    man = json.load(open(MANIFEST, encoding='utf-8'))
    files = {f['path']: f for f in man['files']}
    md_files = sorted(p for p in files if p.endswith('.md'))
    side_files = sorted(p for p in files if p.endswith('.memoria.yaml'))

    # ---------- P0 snapshot self-check
    bad = []
    for p, meta in files.items():
        fp = os.path.join(FROZEN, *p.split('/'))
        if not os.path.isfile(fp):
            bad.append({'path': p, 'why': 'missing'})
        elif sha256_file(fp) != meta['sha256']:
            bad.append({'path': p, 'why': 'sha256_mismatch'})
    snap = {'manifest': os.path.relpath(MANIFEST, ROOT).replace('\\', '/'),
            'frozen_at': man['frozen_at'],
            'md': len(md_files), 'sidecars': len(side_files),
            'sha_mismatch': bad}
    # live drift (read-only existence/hash check for the same 37 files)
    live = {'root': LIVE, 'checked': 0, 'missing': 0, 'mismatch': 0,
            'mismatch_paths': []}
    for p, meta in files.items():
        fp = os.path.join(LIVE, *p.split('/'))
        live['checked'] += 1
        if not os.path.isfile(fp):
            live['missing'] += 1
        elif sha256_file(fp) != meta['sha256']:
            live['mismatch'] += 1
            if len(live['mismatch_paths']) < 30:
                live['mismatch_paths'].append(p)

    # ---------- load corpus
    texts, lines_by, heads_by = {}, {}, {}
    for rel in md_files:
        t = read_text(os.path.join(FROZEN, *rel.split('/')))
        texts[rel] = t
        lines_by[rel] = t.split('\n')
        heads_by[rel] = headings_of(lines_by[rel])

    sidecars = []
    for rel in side_files:
        sc = parse_sidecar(os.path.join(FROZEN, *rel.split('/')))
        sc['_sidecar'] = rel
        sidecars.append(sc)

    # ---------- P1 per-KP records
    kps = []
    for sc in sidecars:
        rel = sc['file']
        if rel not in texts:
            continue
        t = texts[rel]
        nt, linemap = norm_text(t)
        lines, hs = lines_by[rel], heads_by[rel]
        eof = len(lines)
        for kp in sc['kps']:
            st = resolve(nt, linemap, kp['start']['snippet'], kp['start']['line_hint'])
            en = resolve(nt, linemap, kp['end']['snippet'], kp['end']['line_hint'])
            start_line = st['line'] if st['line'] else (kp['start']['line_hint'] or 1)
            owner, oi = nearest_heading_before(hs, start_line)
            boundary = section_end(hs, oi, eof) if owner else (hs[0]['line'] - 1 if hs else eof)
            boundary = max(boundary, start_line)
            heading_line = (owner is not None and owner['line'] == start_line)
            # end resolution / clamping (R1 ③)
            end_res = en['line']
            end_inverted = end_res is not None and end_res < start_line
            end_clamped = min(end_res, boundary) if end_res is not None else boundary
            end_clamped = max(end_clamped, start_line)
            end_repair = (end_res is None or end_inverted or en['matches'] == 0
                          or end_res > boundary or en['matches'] > 1)
            range_ok = st['found'] and st['line'] is not None and end_clamped >= start_line
            # ambiguity tiers for start anchor
            sec_unique = False
            if st['found'] and st['line'] is not None:
                in_sec = [ln for ln in st['occ_lines'] if (owner['line'] if owner else 1) <= ln <= boundary]
                sec_unique = len(set(in_sec)) == 1
            ctx_unique = False
            if st['found'] and st['line'] is not None and st['matches'] > 1:
                chosen = None
                for o in occurrences(nt, st['snippet']):
                    if linemap[o] == st['line']:
                        chosen = o
                        break
                if chosen is not None:
                    ctx = nt[max(0, chosen - 40):chosen]
                    cand = [o for o in occurrences(nt, st['snippet'])
                            if nt[max(0, o - 40):o] == ctx]
                    ctx_unique = len(cand) == 1
            role = ('教材' if rel.startswith('教材/') else
                    ('slides' if rel.startswith('img/') else 'notes'))
            size_hint = line_chars(lines, start_line,
                                   end_res if (end_res and end_res >= start_line) else start_line)
            size_res = line_chars(lines, start_line, end_clamped)
            size_head = line_chars(lines, start_line, boundary)
            kps.append({
                'id': kp['id'], 'name': kp['name'], 'file': rel, 'role': role,
                'sidecar': sc['_sidecar'],
                'start_line': start_line, 'start_heading': heading_line,
                'start_matches': st['matches'], 'start_unique': st['unique'],
                'section_unique': sec_unique, 'context_unique': ctx_unique,
                'hint_verified': st['hint_verified'],
                'matched_snippet': st['snippet'],
                'end_line_raw': end_res, 'end_line': end_clamped,
                'boundary': boundary, 'end_repair': end_repair,
                'end_matches': en['matches'], 'end_inverted': end_inverted,
                'range_ok': range_ok,
                'verified_strict': range_ok and st['unique'],
                'verified_section': range_ok and (st['unique'] or sec_unique),
                'verified_context': range_ok and (st['unique'] or sec_unique or ctx_unique),
                'verified_lenient': range_ok and (st['unique'] or sec_unique or ctx_unique
                                                  or st['hint_verified']),
                'size_hint': size_hint, 'size_resolved': size_res,
                'size_heading': size_head,
            })
    N = len(kps)

    def role_box(role):
        return [r for r in kps if r['role'] == role]

    def size_stats(rs, key):
        vals = [r[key] for r in rs]
        gt1200 = sum(1 for v in vals if v > 1200)
        gt3000 = sum(1 for v in vals if v > 3000)
        return {'n': len(vals), 'p50': pctl(vals, 50), 'p90': pctl(vals, 90),
                'max': max(vals) if vals else None,
                'gt1200': gt1200, 'gt1200_pct': pct(gt1200, len(vals)),
                'gt3000_pct': pct(gt3000, len(vals))}

    # overlap / nesting structure of current KP spans (semantic)
    overlap_pairs = 0
    nested_pairs = 0
    kp_in_overlap = set()
    by_file = collections.defaultdict(list)
    for r in kps:
        by_file[r['file']].append(r)
    for rel, rs in by_file.items():
        rs = sorted(rs, key=lambda r: (r['start_line'], r['boundary']))
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                if a['start_line'] > b['boundary']:
                    break
                if not (a['boundary'] < b['start_line'] or b['boundary'] < a['start_line']):
                    overlap_pairs += 1
                    kp_in_overlap.add(a['id']); kp_in_overlap.add(b['id'])
                    if (a['start_line'] <= b['start_line'] and b['boundary'] <= a['boundary']) or \
                       (b['start_line'] <= a['start_line'] and a['boundary'] <= b['boundary']):
                        nested_pairs += 1

    # ---------- P2 anchor stats
    def anchor_box(rs):
        n = len(rs)
        return {
            'n': n,
            'range_ok': sum(1 for r in rs if r['range_ok']),
            'range_ok_pct': pct(sum(1 for r in rs if r['range_ok']), n),
            'strict': sum(1 for r in rs if r['verified_strict']),
            'strict_pct': pct(sum(1 for r in rs if r['verified_strict']), n),
            'section': sum(1 for r in rs if r['verified_section']),
            'section_pct': pct(sum(1 for r in rs if r['verified_section']), n),
            'context': sum(1 for r in rs if r['verified_context']),
            'context_pct': pct(sum(1 for r in rs if r['verified_context']), n),
            'lenient_hint': sum(1 for r in rs if r['verified_lenient']),
            'lenient_hint_pct': pct(sum(1 for r in rs if r['verified_lenient']), n),
            'start_multi': sum(1 for r in rs if r['start_matches'] > 1),
            'start_multi_pct': pct(sum(1 for r in rs if r['start_matches'] > 1), n),
            'end_repair': sum(1 for r in rs if r['end_repair']),
            'end_repair_pct': pct(sum(1 for r in rs if r['end_repair']), n),
            'end_inverted': sum(1 for r in rs if r['end_inverted']),
            'end_missing': sum(1 for r in rs if r['end_matches'] == 0),
            'start_heading_pct': pct(sum(1 for r in rs if r['start_heading']), n),
        }

    def end_reasons(rs):
        return {
            'end_missing': sum(1 for r in rs if r['end_matches'] == 0),
            'end_ambiguous_multi': sum(1 for r in rs if r['end_matches'] > 1),
            'end_over_boundary': sum(1 for r in rs if r['end_line_raw'] is not None
                                     and r['end_line_raw'] > r['boundary']),
            'end_inverted': sum(1 for r in rs if r['end_inverted']),
            'end_repair_total': sum(1 for r in rs if r['end_repair']),
        }

    anchor = {'all': dict(anchor_box(kps), end_reasons=end_reasons(kps)),
              'textbook': dict(anchor_box(role_box('教材')),
                               end_reasons=end_reasons(role_box('教材'))),
              'slides': dict(anchor_box(role_box('slides')),
                             end_reasons=end_reasons(role_box('slides'))),
              'notes': dict(anchor_box(role_box('notes')),
                            end_reasons=end_reasons(role_box('notes'))),
              'stored_range_ok': sum(1 for r in kps
                                     if r['end_matches'] > 0 and not r['end_inverted']
                                     and (r['end_line_raw'] is None or r['end_line_raw'] >= r['start_line'])),
              'stored_range_ok_pct': pct(sum(1 for r in kps
                                             if r['end_matches'] > 0 and not r['end_inverted']
                                             and (r['end_line_raw'] is None or r['end_line_raw'] >= r['start_line'])), N),
              'fail_section_ids': [r['id'] for r in kps if not r['verified_section']],
              'end_missing_ids': [r['id'] for r in kps if r['end_matches'] == 0],
              'end_inverted_ids': [r['id'] for r in kps if r['end_inverted']],
              'start_multi_ids_sample': [r['id'] for r in kps if r['start_matches'] > 1][:20]}
    anchor['fail_section_detail'] = [
        {'id': r['id'], 'file': r['file'], 'start_matches': r['start_matches'],
         'start_line': r['start_line'], 'section_unique': r['section_unique']}
        for r in kps if not r['verified_section']]

    # ---------- P3 option A
    # A1: minimal repair — only KPs with end_repair get end = boundary
    a1_changed = [r for r in kps if r['end_repair']]
    a1_sizes = [r['size_heading'] if r['end_repair'] else r['size_resolved'] for r in kps]

    def a1_size(r):
        return r['size_heading'] if r['end_repair'] else r['size_resolved']

    def next_any_heading_line(rel, start_line):
        for h in heads_by[rel]:
            if h['line'] > start_line:
                return h['line'] - 1
        return len(lines_by[rel])

    def a1b_size(r):
        if not r['end_repair']:
            return r['size_resolved']
        if r['start_heading']:
            end = r['boundary']
        else:
            end = next_any_heading_line(r['file'], r['start_line'])
            end = max(end, r['start_line'])
        return line_chars(lines_by[r['file']], r['start_line'], end)

    a1b_sizes = [a1b_size(r) for r in kps]
    repaired = [r for r in kps if r['end_repair']]
    repaired_heading = [r for r in repaired if r['start_heading']]
    repaired_nonheading = [r for r in repaired if not r['start_heading']]

    # A2: all ends = next same-level heading (semantic span)
    a2_changed = [r for r in kps if r['end_line'] != r['boundary']]
    optionA = {
        'A1_minimal_repair': {
            'kps_changed': len(a1_changed),
            'kps_changed_pct': pct(len(a1_changed), N),
            'changed_by_role': {role: sum(1 for r in a1_changed if r['role'] == role)
                                for role in ('教材', 'slides', 'notes')},
            'changed_ids_sample': [r['id'] for r in a1_changed[:20]],
            'size_all': dist(a1_sizes),
            'size_textbook': dist([a1_size(r) for r in kps if r['role'] == '教材']),
            'gt1200_all_pct': pct(sum(1 for r in kps if a1_size(r) > 1200), N),
            'gt1200_textbook_pct': pct(sum(1 for r in kps if r['role'] == '教材'
                                          and a1_size(r) > 1200), len(role_box('教材'))),
            'total_chars_before': sum(r['size_resolved'] for r in kps),
            'total_chars_after': sum(a1_sizes),
            'term': '只修 end_repair 的 KP（坏/歧义/缺/超边界），其余 end 不动',
            'repaired_heading': len(repaired_heading),
            'repaired_nonheading': len(repaired_nonheading),
            'repaired_size_dist': dist([r['size_heading'] for r in repaired]),
            'repaired_gt3000': sum(1 for r in repaired if r['size_heading'] > 3000),
            'repaired_nonheading_size_max': (max(r['size_heading'] for r in repaired_nonheading)
                                             if repaired_nonheading else None),
            'repaired_nonheading_ids': [
                {'id': r['id'], 'file': r['file'], 'start_line': r['start_line'],
                 'size_after': r['size_heading'], 'size_before': r['size_resolved']}
                for r in repaired_nonheading],
        },
        'A1b_hybrid_repair': {
            'rule': 'end_repair 的 KP：start 是标题行→下一同级标题；否则→下一个任意级标题前',
            'size_all': dist(a1b_sizes),
            'size_textbook': dist([a1b_size(r) for r in kps if r['role'] == '教材']),
            'gt1200_all_pct': pct(sum(1 for v in a1b_sizes if v > 1200), N),
            'gt1200_textbook_pct': pct(sum(1 for r in kps if r['role'] == '教材'
                                          and a1b_size(r) > 1200), len(role_box('教材'))),
            'repaired_size_dist': dist([a1b_size(r) for r in repaired]),
        },
        'A2_end_to_heading': {
            'kps_changed': len(a2_changed),
            'kps_changed_pct': pct(len(a2_changed), N),
            'changed_by_role': {role: sum(1 for r in a2_changed if r['role'] == role)
                                for role in ('教材', 'slides', 'notes')},
            'size_all': dist([r['size_heading'] for r in kps]),
            'size_textbook': dist([r['size_heading'] for r in kps if r['role'] == '教材']),
            'gt1200_all_pct': pct(sum(1 for r in kps if r['size_heading'] > 1200), N),
            'gt1200_textbook_pct': pct(sum(1 for r in kps if r['role'] == '教材'
                                          and r['size_heading'] > 1200),
                                       len(role_box('教材'))),
            'gt3000_textbook_pct': pct(sum(1 for r in kps if r['role'] == '教材'
                                          and r['size_heading'] > 3000),
                                       len(role_box('教材'))),
            'total_chars_before': sum(r['size_resolved'] for r in kps),
            'total_chars_after': sum(r['size_heading'] for r in kps),
            'term': '所有 end 都改为「下一同级标题前」的语义边界',
        },
    }

    # ---------- P4/P5 slicing scope
    # slices are built per file; two file scopes:
    #   S_kp_files : 11 sidecar-covered files (where the product would have KPs)
    #   S_all      : 26 md
    def build_slices(scope_files):
        out = []
        for rel in scope_files:
            lines, hs = lines_by[rel], heads_by[rel]
            for (a, b) in leaf_sections(lines, hs):
                for (x, y) in pack(lines, a, b):
                    out.append({'file': rel, 'start': x, 'end': y,
                                'chars': line_chars(lines, x, y)})
        return out

    def kp_overlap(rel, a, b):
        """KPs (semantic spans) overlapping [a,b]."""
        res = []
        for r in by_file[rel]:
            if r['boundary'] < a or r['start_line'] > b:
                continue
            ov = line_chars(lines_by[rel], max(a, r['start_line']), min(b, r['boundary']))
            res.append((r, ov))
        return res

    def orphan_stats(slices):
        n = len(slices)
        no_kp, lt50, multi = 0, 0, 0
        chars_total = 0
        for s in slices:
            chars_total += s['chars']
            ovs = kp_overlap(s['file'], s['start'], s['end'])
            if not ovs:
                no_kp += 1
                lt50 += 1
                continue
            if len(ovs) > 1:
                multi += 1
            share = sum(ov for _, ov in ovs) / s['chars'] if s['chars'] else 0
            if share < 0.5:
                lt50 += 1
        return {'slices': n, 'slice_chars_total': chars_total,
                'orphan_any': no_kp, 'orphan_any_pct': pct(no_kp, n),
                'orphan_lt50': lt50, 'orphan_lt50_pct': pct(lt50, n),
                'slices_with_2plus_kp': multi,
                'slices_with_2plus_kp_pct': pct(multi, n)}

    def slices_per_kp(slices, kp_filter=None):
        per = collections.Counter()
        for s in slices:
            for r, _ in kp_overlap(s['file'], s['start'], s['end']):
                per[r['id']] += 1
        rs = [r for r in kps if (kp_filter is None or kp_filter(r))]
        vals = [per.get(r['id'], 0) for r in rs]
        return {'dist': dist(vals),
                'n_kps_in_scope': len(rs),
                'kps_zero_slice': sum(1 for v in vals if v == 0),
                'kps_ge2_slices': sum(1 for v in vals if v >= 2),
                'kps_ge2_slices_pct': pct(sum(1 for v in vals if v >= 2), len(rs))}

    def fanout_top(slices, kp_filter=None, top=8):
        per = collections.Counter()
        for s in slices:
            for r, _ in kp_overlap(s['file'], s['start'], s['end']):
                per[r['id']] += 1
        rs = [r for r in kps if (kp_filter is None or kp_filter(r))]
        rows = sorted(((per.get(r['id'], 0), r) for r in rs), key=lambda x: -x[0])[:top]
        return [{'id': r['id'], 'file': r['file'], 'slices': n,
                 'size_heading': r['size_heading'], 'span_lines': r['boundary'] - r['start_line'] + 1}
                for n, r in rows]

    def per_file_orphans(slices):
        tab = collections.defaultdict(lambda: {'slices': 0, 'orphan': 0})
        for s in slices:
            tab[s['file']]['slices'] += 1
            if not kp_overlap(s['file'], s['start'], s['end']):
                tab[s['file']]['orphan'] += 1
        return {k: {'slices': v['slices'], 'orphan': v['orphan'],
                    'orphan_pct': pct(v['orphan'], v['slices'])}
                for k, v in sorted(tab.items())}

    kp_file_set = sorted({r['file'] for r in kps})
    slices_kp_files = build_slices(kp_file_set)
    slices_all = build_slices(md_files)
    # variant: drop "degenerate" sidecars that exist but carry <=1 KP (00 前言目录=0, 08=1 test)
    kp_count_by_file = collections.Counter(r['file'] for r in kps)
    files_indexed = sorted(f for f in kp_file_set if kp_count_by_file[f] >= 2)
    slices_indexed = build_slices(files_indexed)
    # textbook core (3 chapters that genuinely carry KPs) / core + single-KP prose notes
    files_core = sorted(f for f in kp_file_set if f.startswith('教材/') and kp_count_by_file[f] >= 2)
    files_core_plus = sorted(set(files_core + [f for f in kp_file_set
                                               if f.startswith('notes/') or '平滑' in f]))
    slices_core = build_slices(files_core)
    slices_core_plus = build_slices(files_core_plus)
    # section-scoped variant: only leaf sections that overlap >=1 KP; slice the WHOLE section
    slices_section_kp = []
    slices_section_kp_core = []
    for rel in kp_file_set:
        lines, hs = lines_by[rel], heads_by[rel]
        for (a, b) in leaf_sections(lines, hs):
            if not kp_overlap(rel, a, b):
                continue
            for (x, y) in pack(lines, a, b):
                rec = {'file': rel, 'start': x, 'end': y,
                       'chars': line_chars(lines, x, y)}
                slices_section_kp.append(rec)
                if rel in files_core_plus:
                    slices_section_kp_core.append(rec)
    # sensitivity: slice count under different budget / min-size settings
    def section_overlap_slices(files, budget, min_chars):
        out = []
        for rel in files:
            lines, hs = lines_by[rel], heads_by[rel]
            for (a, b) in leaf_sections(lines, hs):
                if not kp_overlap(rel, a, b):
                    continue
                for (x, y) in pack(lines, a, b, budget=budget, min_chars=min_chars):
                    out.append({'file': rel, 'start': x, 'end': y,
                                'chars': line_chars(lines, x, y)})
        return out

    sensitivity = {}
    for budget in (800, 1200, 2000):
        for mn in (0, 200):
            key = f'budget{budget}_min{mn}'
            s_core = section_overlap_slices(files_core_plus, budget, mn)
            s_all = section_overlap_slices(kp_file_set, budget, mn)
            sensitivity[key] = {
                'core_plus_slices': len(s_core),
                'core_plus_chars_p50': pctl([s['chars'] for s in s_core], 50),
                'core_plus_chars_max': max((s['chars'] for s in s_core), default=None),
                'all_kp_files_slices': len(s_all),
                'all_kp_files_slices_per_kp_p90': slices_per_kp(s_all)['dist']['p90'],
            }
    # chapters that pass the per-chapter 20% orphan gate (whole-file slicing metric)
    per_file_whole = per_file_orphans(slices_kp_files)
    files_passing = sorted(f for f in files_core_plus
                           if per_file_whole.get(f, {}).get('orphan_pct', 100) <= 20)
    slices_section_passing = section_overlap_slices(files_passing, BUDGET_CHARS, MIN_SLICE)

    # "纯 KP 内容 scope"：只对 KP 语义 span 的并集建切片（孤儿的定义域收缩到已索引内容）
    kp_union = []
    for rel in kp_file_set:
        rs = sorted(by_file[rel], key=lambda r: r['start_line'])
        cur = None
        for r in rs:
            if cur is None:
                cur = [r['start_line'], r['boundary']]
            elif r['start_line'] <= cur[1] + 1:
                cur[1] = max(cur[1], r['boundary'])
            else:
                kp_union.append({'file': rel, 'start': cur[0], 'end': cur[1]})
                cur = [r['start_line'], r['boundary']]
        if cur:
            kp_union.append({'file': rel, 'start': cur[0], 'end': cur[1]})
    slices_union = []
    for u in kp_union:
        for (x, y) in pack(lines_by[u['file']], u['start'], u['end']):
            slices_union.append({'file': u['file'], 'start': x, 'end': y,
                                 'chars': line_chars(lines_by[u['file']], x, y)})

    C = {
        'rule': 'leaf section（每级标题切段）→ 段落原子 200–1200 字打包；'
                '预算 1200 字；不切 $$/``` 块',
        'scope_kp_files': dict(orphan_stats(slices_kp_files),
                               slices_per_kp=slices_per_kp(slices_kp_files),
                               files=len(kp_file_set)),
        'scope_kp_files_excl_degenerate': dict(orphan_stats(slices_indexed),
                                               slices_per_kp=slices_per_kp(slices_indexed),
                                               files=len(files_indexed),
                                               files_included=files_indexed),
        'scope_all_26': orphan_stats(slices_all),
        'scope_kp_union_only': dict(orphan_stats(slices_union),
                                    slices_per_kp=slices_per_kp(slices_union)),
        'scope_textbook_core': dict(orphan_stats(slices_core),
                                    slices_per_kp=slices_per_kp(
                                        slices_core, lambda r: r['file'] in files_core),
                                    files=files_core),
        'scope_textbook_core_plus_prose': dict(orphan_stats(slices_core_plus),
                                               slices_per_kp=slices_per_kp(
                                                   slices_core_plus,
                                                   lambda r: r['file'] in files_core_plus),
                                               files=files_core_plus),
        'scope_section_overlap_kp': dict(orphan_stats(slices_section_kp),
                                         slices_per_kp=slices_per_kp(slices_section_kp)),
        'scope_section_overlap_kp_core_plus': dict(
            orphan_stats(slices_section_kp_core),
            slices_per_kp=slices_per_kp(slices_section_kp_core,
                                        lambda r: r['file'] in files_core_plus),
            files=files_core_plus),
        'fanout_top_section_overlap': fanout_top(slices_section_kp),
        'fanout_top_core_plus': fanout_top(slices_section_kp_core,
                                           lambda r: r['file'] in files_core_plus),
        'scope_passing_chapters_section_only': dict(
            orphan_stats(slices_section_passing),
            slices_per_kp=slices_per_kp(slices_section_passing,
                                        lambda r: r['file'] in files_passing),
            files=files_passing),
        'per_file_kp_files': per_file_orphans(slices_kp_files),
        'kp_count_by_file': dict(sorted(kp_count_by_file.items())),
        'sensitivity': sensitivity,
    }

    # ---------- P4 option B
    # B1: split each KP semantic span by budget (new ids); fan-out old KP -> new units
    b1_units = []
    b1_fan = {}
    for r in kps:
        lines = lines_by[r['file']]
        parts = pack(lines, r['start_line'], r['boundary'])
        b1_fan[r['id']] = len(parts)
        for (a, b) in parts:
            b1_units.append({'file': r['file'], 'start': a, 'end': b,
                             'chars': line_chars(lines, a, b),
                             'owners': [r['id']]})
    # overlap of B1 units across KPs (nested KPs -> same region re-cut N times)
    uniq_ranges = {(u['file'], u['start'], u['end']) for u in b1_units}
    # B2: whole-file structure re-cut == C's slice partition (same rule)
    b2_units = []
    for s in slices_kp_files:
        owners = [r['id'] for r, _ in kp_overlap(s['file'], s['start'], s['end'])]
        b2_units.append(dict(s, owners=owners))
    b2_fan = collections.Counter()
    for u in b2_units:
        for oid in u['owners']:
            b2_fan[oid] += 1
    b2_multi_owner = sum(1 for u in b2_units if len(u['owners']) > 1)
    b2_ownerless = sum(1 for u in b2_units if len(u['owners']) == 0)
    optionB = {
        'B1_per_kp_budget': {
            'new_kp_count_naive': len(b1_units),
            'new_kp_count_unique_ranges': len(uniq_ranges),
            'kp_count_change_naive': len(b1_units) - N,
            'fanout_dist': dist([b1_fan[r['id']] for r in kps]),
            'old_kps_ge2_new': sum(1 for v in b1_fan.values() if v >= 2),
            'old_kps_ge2_new_pct': pct(sum(1 for v in b1_fan.values() if v >= 2), N),
            'nested_overlap_pairs': nested_pairs,
            'note': '按每个 KP 的语义 span 独立重切；嵌套 KP 会重复切同一段正文，'
                    '需先裁决「嵌套 KP 是否合并」',
        },
        'B2_section_rewrite': {
            'new_kp_count': len(b2_units),
            'kp_count_change': len(b2_units) - N,
            'fanout_dist': dist([b2_fan.get(r['id'], 0) for r in kps]),
            'mapping_rows': sum(len(u['owners']) for u in b2_units),
            'new_units_without_old_kp': b2_ownerless,
            'new_units_claimed_by_2plus_old_kp': b2_multi_owner,
            'new_units_claimed_by_2plus_old_kp_pct': pct(b2_multi_owner, len(b2_units)),
            'old_kps_with_zero_new': sum(1 for r in kps if b2_fan.get(r['id'], 0) == 0),
        },
    }

    # ---------- P6 user data
    links = []
    edges = []
    for sc in sidecars:
        for l in sc['links']:
            links.append(dict(l, sidecar=sc['_sidecar']))
        for e in sc['edges']:
            edges.append(dict(e, sidecar=sc['_sidecar']))
    kp_ids = {r['id'] for r in kps}
    link_targets = [t for l in links for t in l['targets']]
    userdata = {
        'kp_ids': N,
        'links': len(links),
        'link_targets': len(link_targets),
        'link_target_orphans': sum(1 for t in link_targets if t not in kp_ids),
        'edge_edges': len(edges),
        'edge_targets': sum(len(e['targets']) for e in edges),
        'edge_target_orphans': sum(1 for e in edges for t in e['targets'] if t not in kp_ids),
        'cards_json': 'absent (frozen snapshot 不含 .memoria/agent；live 库 review 目录为空)',
        'orphan_link_target_ids': sorted({t for t in link_targets if t not in kp_ids}),
    }

    # ---------- P7 description volume (C's hidden cost)
    total_chars = sum(s['chars'] for s in slices_kp_files)
    union_chars = sum(s['chars'] for s in slices_union)
    desc_vol = {
        'scope_kp_files_slices': len(slices_kp_files),
        'slice_chars_total': total_chars,
        'est_input_tokens_if_one_call_per_slice': round(
            total_chars * TOKEN_PER_CHAR + len(slices_kp_files) * 300),  # + prompt overhead
        'est_output_chars_if_80_per_slice': len(slices_kp_files) * 80,
        'est_llm_calls_one_per_slice': len(slices_kp_files),
        'scope_kp_union_slices': len(slices_union),
        'scope_kp_union_chars': union_chars,
        'scope_kp_union_est_input_tokens': round(
            union_chars * TOKEN_PER_CHAR + len(slices_union) * 300),
        'scope_kp_union_est_llm_calls': len(slices_union),
        'note': 'description 生成必须改写不能截原文（R5）；token 按 0.4237 tok/字；'
                'prompt 开销按 300 tok/次粗估，仅量级参考',
    }

    out = {
        'snapshot': dict(snap, live_drift=live),
        'P1_kp_inventory': {
            'kps': N, 'textbook': len(role_box('教材')),
            'slides': len(role_box('slides')), 'notes': len(role_box('notes')),
            'start_is_heading_pct_all': pct(sum(1 for r in kps if r['start_heading']), N),
            'start_is_heading_pct_textbook': pct(
                sum(1 for r in role_box('教材') if r['start_heading']), len(role_box('教材'))),
            'size_hint_all': size_stats(kps, 'size_hint'),
            'size_resolved_all': size_stats(kps, 'size_resolved'),
            'size_heading_all': size_stats(kps, 'size_heading'),
            'size_resolved_textbook': size_stats(role_box('教材'), 'size_resolved'),
            'size_heading_textbook': size_stats(role_box('教材'), 'size_heading'),
            'kp_span_overlap_pairs': overlap_pairs,
            'kp_span_nested_pairs': nested_pairs,
            'kps_in_overlapping_spans': len(kp_in_overlap),
            'kps_in_overlapping_spans_pct': pct(len(kp_in_overlap), N),
        },
        'P2_anchor_verified': anchor,
        'P3_option_A': optionA,
        'P4_option_B': optionB,
        'P5_option_C': C,
        'P6_userdata': userdata,
        'P7_description_volume': desc_vol,
    }
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # ---------- print
    print('# Q1 research probe — 固定快照 2026-10-27T14:09:46（26 md / 11 sidecar）')
    print(f"\n## P0 快照: md={snap['md']} sidecars={snap['sidecars']} "
          f"sha_mismatch={len(bad)} | live 漂移 {live['mismatch']}/{live['checked']}")
    p1 = out['P1_kp_inventory']
    print(f"\n## P1 KP: {p1['kps']}（教材 {p1['textbook']} / slides {p1['slides']} / notes {p1['notes']}）"
          f" start=标题行 all {p1['start_is_heading_pct_all']}% / textbook {p1['start_is_heading_pct_textbook']}%")
    for k in ('size_hint_all', 'size_resolved_all', 'size_heading_all'):
        s = p1[k]
        print(f"- {k}: p50={s['p50']} p90={s['p90']} max={s['max']} >1200={s['gt1200_pct']}% >3000={s['gt3000_pct']}%")
    print(f"- 教材 resolved: {json.dumps(p1['size_resolved_textbook'], ensure_ascii=False)}")
    print(f"- 教材 heading : {json.dumps(p1['size_heading_textbook'], ensure_ascii=False)}")
    print(f"- KP 语义 span 重叠对={p1['kp_span_overlap_pairs']} 嵌套对={p1['kp_span_nested_pairs']} "
          f"涉及 KP={p1['kps_in_overlapping_spans']}（{p1['kps_in_overlapping_spans_pct']}%）")
    for k, v in anchor.items():
        if not isinstance(v, dict):
            continue
        print(f"\n## P2 anchor[{k}] n={v['n']} range_ok={v['range_ok_pct']}% "
              f"strict={v['strict_pct']}% section={v['section_pct']}% "
              f"context={v['context_pct']}% lenient={v['lenient_hint_pct']}% | "
              f"start_multi={v['start_multi_pct']}% end_repair={v['end_repair_pct']}% "
              f"inverted={v['end_inverted']} end_missing={v['end_missing']}")
    print(f"   stored_range_ok={anchor['stored_range_ok']}/{N} ({anchor['stored_range_ok_pct']}%) "
          f"fail_section={anchor['fail_section_ids']} end_missing_ids={anchor['end_missing_ids']}")
    print(f"   end_reasons_all={anchor['all']['end_reasons']}")
    a = out['P3_option_A']
    for k in ('A1_minimal_repair', 'A1b_hybrid_repair', 'A2_end_to_heading'):
        v = a[k]
        print(f"\n## P3 {k}: changed={v.get('kps_changed')} ({v.get('kps_changed_pct')}%) "
              f"by_role={v.get('changed_by_role')} "
              f"gt1200_all={v['gt1200_all_pct']}% gt1200_textbook={v['gt1200_textbook_pct']}%")
        print(f"   size_all={json.dumps(v['size_all'], ensure_ascii=False)}")
    print(f"   A1 repaired_heading={a['A1_minimal_repair']['repaired_heading']} "
          f"repaired_nonheading={a['A1_minimal_repair']['repaired_nonheading']} "
          f"repaired_size={json.dumps(a['A1_minimal_repair']['repaired_size_dist'], ensure_ascii=False)} "
          f"repaired_gt3000={a['A1_minimal_repair']['repaired_gt3000']} "
          f"nonheading_repair_max={a['A1_minimal_repair']['repaired_nonheading_size_max']}")
    print(f"   A1b repaired_size={json.dumps(a['A1b_hybrid_repair']['repaired_size_dist'], ensure_ascii=False)}")
    b = out['P4_option_B']
    print(f"\n## P4 B1: new_kp_naive={b['B1_per_kp_budget']['new_kp_count_naive']} "
          f"(Δ={b['B1_per_kp_budget']['kp_count_change_naive']}) "
          f"fanout={json.dumps(b['B1_per_kp_budget']['fanout_dist'], ensure_ascii=False)} "
          f"old_kps_ge2={b['B1_per_kp_budget']['old_kps_ge2_new_pct']}%")
    print(f"## P4 B2: new_kp={b['B2_section_rewrite']['new_kp_count']} "
          f"(Δ={b['B2_section_rewrite']['kp_count_change']}) "
          f"fanout={json.dumps(b['B2_section_rewrite']['fanout_dist'], ensure_ascii=False)}")
    print(f"   mapping_rows={b['B2_section_rewrite']['mapping_rows']} "
          f"units_no_old_kp={b['B2_section_rewrite']['new_units_without_old_kp']} "
          f"units_2plus_owner={b['B2_section_rewrite']['new_units_claimed_by_2plus_old_kp']}")
    c = out['P5_option_C']
    for k in ('scope_kp_files', 'scope_kp_files_excl_degenerate', 'scope_all_26',
              'scope_kp_union_only', 'scope_textbook_core', 'scope_textbook_core_plus_prose',
              'scope_section_overlap_kp', 'scope_section_overlap_kp_core_plus',
              'scope_passing_chapters_section_only'):
        v = c[k]
        print(f"\n## P5 C[{k}]: slices={v['slices']} orphan_any={v['orphan_any_pct']}% "
              f"orphan_lt50={v['orphan_lt50_pct']}% 2+kp={v['slices_with_2plus_kp_pct']}%")
        if 'slices_per_kp' in v:
            print(f"   slices/KP={json.dumps(v['slices_per_kp']['dist'], ensure_ascii=False)} "
                  f"zero={v['slices_per_kp']['kps_zero_slice']} "
                  f"ge2={v['slices_per_kp']['kps_ge2_slices_pct']}%")
    print('\n## P5 per-file orphan (kp-bearing files):')
    for f, v in c['per_file_kp_files'].items():
        print(f"   {f}: slices={v['slices']} orphan={v['orphan']} ({v['orphan_pct']}%) "
              f"kps={c['kp_count_by_file'].get(f, 0)}")
    print('\n## P5 fanout_top (section_overlap_kp):')
    for r in c['fanout_top_section_overlap']:
        print(f"   {r['id']} slices={r['slices']} size_heading={r['size_heading']} "
              f"span_lines={r['span_lines']}")
    print('\n## P5 sensitivity (section_overlap scope):')
    for k, v in c['sensitivity'].items():
        print(f"   {k}: core_plus_slices={v['core_plus_slices']} "
              f"p50={v['core_plus_chars_p50']} max={v['core_plus_chars_max']} "
              f"all_kp_files={v['all_kp_files_slices']}")
    print('\n## P6 userdata:', json.dumps(userdata, ensure_ascii=False))
    print(f"\n## P7 description volume: {json.dumps(desc_vol, ensure_ascii=False)}")
    print('\nwrote', OUT)


if __name__ == '__main__':
    main()
