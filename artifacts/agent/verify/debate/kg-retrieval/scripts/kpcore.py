# -*- coding: utf-8 -*-
"""kpcore.py — read-only helpers for Memoria KB sidecars + markdown.

Part of the kg-retrieval debate corpus analysis. This module NEVER writes to
D:\\AAA_Courses; all outputs go under artifacts/agent/verify/debate/kg-retrieval/.

Sidecar YAML is parsed with a small subset parser (no PyYAML in the runtime).
The sidecar schema is flat and stable:
    schema_version / file / knowledge_points[]
      - id, name, range{start{snippet,line_hint}, end{snippet,line_hint}}
      optional: tags[], links[], edges[]
"""
import os
import re
import glob
import json

KB_ROOTS = {
    '\u6570\u5b57\u901a\u4fe1\u539f\u7406': r'D:\AAA_Courses\数字通信原理',
    '\u73b0\u4ee3\u64cd\u4f5c\u7cfb\u7edf': r'D:\AAA_Courses\现代操作系统',
    '\u8ba1\u7b97\u673a\u56fe\u5f62\u5b66': r'D:\AAA_Courses\计算机图形学',
    '\u8ba1\u7b97\u673a\u7f51\u8def': r'D:\AAA_Courses\计算机网路',
    '\u8f6f\u4ef6\u5de5\u7a0b\u6982\u8bba': r'D:\AAA_Courses\软件工程概论',
}
TARGET_KB = '\u6570\u5b57\u901a\u4fe1\u539f\u7406'

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                 # .../kg-retrieval
DATA = os.path.join(ROOT, 'data')

# ---------------------------------------------------------------- IO helpers

def read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def sidecar_paths(kb_root):
    base = os.path.join(kb_root, '.memoria', 'sidecars')
    return sorted(glob.glob(os.path.join(base, '**', '*.memoria.yaml'), recursive=True))


def md_files(kb_root, include_memoria=False):
    out = []
    for dirpath, dirnames, filenames in os.walk(kb_root):
        if not include_memoria:
            dirnames[:] = [d for d in dirnames if d not in ('.memoria', '.git')]
        for fn in filenames:
            if fn.lower().endswith('.md'):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def rel(path, root):
    return os.path.relpath(path, root).replace('\\', '/')

# ------------------------------------------------------- sidecar YAML subset

_CONT_KEYS = (r'(line_hint|snippet|end|start|tags|links|edges|name|id|range|'
              r'occurrence|targets|edge_type|instances|pool|relevance|source_id|'
              r'excluded|paging|segmentation|test|wrapped|anchor_text)')
_CONT_RE = re.compile(r'^\s*' + _CONT_KEYS + r'\s*:')


def _merge_snippets(lines):
    """YAML folded scalars: join indented continuation lines into one snippet."""
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'^(\s*)snippet:\s?(.*)$', ln)
        if not m:
            out.append(ln)
            i += 1
            continue
        ind = len(m.group(1))
        parts = [m.group(2)]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                break
            mind = len(nxt) - len(nxt.lstrip(' '))
            if mind > ind and not _CONT_RE.match(nxt):
                parts.append(nxt.strip())
                i += 1
            else:
                break
        val = ' '.join(p for p in parts if p != '')
        out.append(' ' * ind + 'snippet: ' + val)
    return out


def _scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1].replace("''", "'")
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1]
    return v


def parse_sidecar(path):
    """Return {'file': relative md path, 'kps': [...]} for one sidecar."""
    lines = _merge_snippets(read_text(path).splitlines())
    meta_file = None
    kps = []
    cur = None
    section = None          # 'start' | 'end'
    in_links = False
    for ln in lines:
        mfile = re.match(r'^file:\s*(.*)$', ln)
        if mfile is not None:
            meta_file = _scalar(mfile.group(1))
            continue
        if re.match(r'^\s*-\s+id:\s*', ln):
            if cur:
                kps.append(cur)
            cur = {'id': _scalar(re.sub(r'^\s*-\s+id:\s*', '', ln)),
                   'name': None, 'start': {}, 'end': {},
                   'tags': [], 'extra_keys': []}
            section = None
            in_links = False
            continue
        if cur is None:
            continue
        m = re.match(r'^(\s+)([a-zA-Z_]+):\s*(.*)$', ln)
        if not m:
            mt = re.match(r'^\s*-\s+(.*)$', ln)
            if mt and section is None and not in_links:
                cur['tags'].append(_scalar(mt.group(1)))
            continue
        ind = len(m.group(1))
        key = m.group(2)
        val = _scalar(m.group(3))
        if ind <= 2:
            section = None
            in_links = key in ('links', 'edges')
            if key == 'name':
                cur['name'] = val
            elif key not in ('id', 'name', 'range', 'tags', 'links', 'edges'):
                cur['extra_keys'].append(key)
        elif key in ('start', 'end') and not in_links:
            section = key
        elif key in ('snippet', 'line_hint') and section and not in_links:
            cur[section][key] = val
    if cur:
        kps.append(cur)
    if not meta_file:
        # fall back: derive from sidecar path  ...sidecars/<group>/<name>.memoria.yaml
        parts = path.replace('\\', '/').split('/')
        try:
            i = parts.index('sidecars')
            rest = parts[i + 1:]
            meta_file = '/'.join(rest)[:-len('.memoria.yaml')] + '.md'
        except ValueError:
            meta_file = ''
    return {'file': meta_file, 'kps': kps}


def load_kb(kb_name):
    root = KB_ROOTS[kb_name]
    out = []
    for p in sidecar_paths(root):
        side = parse_sidecar(p)
        md_path = os.path.join(root, *side['file'].split('/')) if side['file'] else ''
        out.append({
            'kb': kb_name,
            'kb_root': root,
            'sidecar': rel(p, root),
            'file': side['file'],
            'md_path': md_path,
            'md_exists': os.path.isfile(md_path),
            'kps': side['kps'],
        })
    return out

# ------------------------------------------------------------ text matching

HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')


def headings(lines):
    res = []
    for idx, ln in enumerate(lines, 1):
        m = HEADING_RE.match(ln)
        if m:
            res.append({'line': idx, 'level': len(m.group(1)),
                        'text': m.group(2).strip()})
    return res


def heading_path(hs, line):
    stack = []
    for h in hs:
        if h['line'] > line:
            break
        while stack and stack[-1]['level'] >= h['level']:
            stack.pop()
        stack.append(h)
    return stack


def norm_text(text):
    """Collapse whitespace runs to single spaces; keep offset->line map."""
    out = []
    linemap = []
    line = 1
    prev_space = True
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


def norm_snip(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def locate(nt, linemap, snippet, hint, max_matches=500):
    """Locate a snippet anchor against normalized text.

    The anchor is the pair (snippet, line_hint). Diagnostics separate the two
    sources so we can say which one is load-bearing:

      matches          how many places the snippet text occurs at all
      snippet_unique   the snippet alone pins one position
      match_lines      first line of every occurrence (capped)
      hint             the stored line_hint
      hint_prefix_ok   the *stored* line still starts with the snippet text
                       (=> anchor is fresh / in sync with the md)
      hint_delta       chosen_line - hint   (0 when the hint is fresh)
      line             chosen start line (hint when fresh, else nearest match)
      status           ok | ambiguous | drifted | not_found | missing
    """
    s = norm_snip(snippet)
    h = _toint(hint)
    d = {'hint': h, 'snippet_chars': len(s), 'matches': 0, 'snippet_unique': False,
         'match_lines': [], 'hint_prefix_ok': None, 'line': None,
         'line_delta': None, 'status': 'missing', 'chosen_by': None}
    if not s:
        return d
    occ = []
    i = nt.find(s)
    while i != -1 and len(occ) < max_matches:
        occ.append(i)
        i = nt.find(s, i + 1)
    match_lines = [linemap[o] for o in occ]
    d['matches'] = len(occ)
    d['snippet_unique'] = len(occ) == 1
    d['match_lines'] = sorted(set(match_lines))[:50]

    # does the stored hint still point at (a line starting with) the snippet?
    if h is not None:
        # a snippet may fold a paragraph: allow the match to start at h or h+1
        d['hint_prefix_ok'] = any(
            abs(o_line - h) <= 1 for o_line in match_lines[:max_matches]
        ) or h in match_lines
        # stricter: the stored line itself starts with the snippet prefix
        d['hint_line_starts_with'] = bool(d['hint_prefix_ok']) and h in match_lines

    if not occ:
        d['status'] = 'not_found'
        d['line'] = h
        d['choosen_by'] = 'hint_only'
        return d

    if h is not None:
        # pick the occurrence closest to the hint (what a sane resolver does)
        best = min(occ, key=lambda o: abs(linemap[o] - h))
        d['line'] = linemap[best]
        d['line_delta'] = d['line'] - h
        d['chosen_by'] = 'hint_disambiguated'
    else:
        d['line'] = match_lines[0]
        d['chosen_by'] = 'first_match'
    if len(occ) == 1:
        d['status'] = 'ok'
        d['chosen_by'] = 'snippet_unique'
    else:
        d['status'] = 'ambiguous'
    if d.get('hint_line_starts_with'):
        d['status'] = 'ok_hint_verified'
        d['chosen_by'] = 'hint_verified'
    return d


def _toint(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def line_char_span(lines, start_line, end_line):
    if not start_line or not end_line or end_line < start_line:
        return {'span_lines': 0, 'span_chars': 0}
    end_line = min(end_line, len(lines))
    start_line = max(1, start_line)
    seg = lines[start_line - 1:end_line]
    chars = sum(len(x) for x in seg) + max(0, len(seg) - 1)
    return {'span_lines': end_line - start_line + 1, 'span_chars': chars}

# --------------------------------------------------------------- token est.

CJK_RE = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
_CAL_PATH = os.path.join(DATA, 'token_calibration.json')


def load_token_calibration():
    """Return (cjk_tokens_per_char, other_tokens_per_char).

    data/token_calibration.json is produced by 04_sessions.py from 105 real
    trace/call observations in the owner's session (result_chars vs the app's
    own est_tokens).  When a uniform ratio is available we use it for every
    char, which is the honest choice for mixed CJK/ASCII textbook markdown.
    """
    try:
        with open(_CAL_PATH, 'r', encoding='utf-8') as f:
            c = json.load(f)
        u = c.get('uniform_tokens_per_char')
        if u:
            return float(u), float(u)
        return float(c['cjk_tokens_per_char']), float(c['other_tokens_per_char'])
    except Exception:
        return 0.42, 0.42


def est_tokens(text, cal=None):
    cjk, other = cal if cal else load_token_calibration()
    n_cjk = len(CJK_RE.findall(text))
    n_other = max(0, len(text) - n_cjk)
    return n_cjk * cjk + n_other * other


def fmt_int(n):
    return f'{int(n):,}'


def pct(x, n):
    return round(100.0 * x / n, 1) if n else 0.0


def percentile(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def ensure_data_dir():
    os.makedirs(DATA, exist_ok=True)
    return DATA
