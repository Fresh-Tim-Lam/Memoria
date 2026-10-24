"""读侧 section 寻址：`outline` / `section` / `snippet`（D 节契约的落地）。

## 契约来源

`artifacts/agent/verify/debate/assumptions/as-section-range.md` §0 C1–C5 与 §4 D.1–D.5。
本模块是 `AS-SECTION-RANGE`（有条件成立）的**读侧消费者**，heading 语义**不在本模块自实现**，
一律走 `memoria.services.heading_proposals.scan_headings`（唯一实现，见其模块 docstring）。

## 与本模块直接相关的四条条件

- **C1** 围栏/frontmatter 感知 → 由 `scan_headings` 提供（不在本模块重复）
- **C2** 重名消歧用「父级路径 + 行号」双锚 → `resolve_section(path=…, near_line=…)`
- **C3** 无法唯一 ⇒ **`AMBIGUOUS_SECTION`**，附全部候选；**绝不取首个**
- **C4** `#L<行号>` 是一等回退 → `resolve_section(line=…)` 直接按行号取所在节

## 失败语义（D.3，逐条可复现）

| 码 | 触发 | 附带 |
|---|---|---|
| `SECTION_NOT_FOUND` | 归一化后无匹配 | `suggestions[]`（最近 3 个标题）+ `candidate_count` |
| `AMBIGUOUS_SECTION` | 多候选且 `path`/`line` 均无法消歧 | `candidates[]`（每项 `line_no/level/title/parent_path`） |
| `NO_HEADINGS` | 文档 0 heading | `suggestion` |
| `INVALID_LEVEL` | 请求的级别超出 1..6 | `actual_levels[]` |
| `UNSUPPORTED` | 非 markdown（由调用方判定后传入 `kind`） | — |

## token 口径（与 N1 对齐，**是估算不是实测**）

`estimate_tokens()` 用 N1 的静态口径：CJK 字符 1.5 字/token、其它 3.5 字/token。
它只用于**预算与截断**（相对量）；绝对值须真机测量（E4.2），故所有返回都带
`tokens_estimated=True`。**完整往返**口径（B4.f）由调用方把 schema+system 一起记账，本模块只报自身载荷。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from difflib import get_close_matches

from memoria.services.heading_proposals import (
    HEADING_LEVEL_MAX,
    HEADING_LEVEL_MIN,
    Heading,
    normalize_title,
    scan_headings,
    split_lines,
)

# ── 预算（初值；真机测量后按 E4 调整，调整须留档）──────────────────────────
OUTLINE_MAX_TOKENS = 800
SECTION_MAX_TOKENS = 4000
SNIPPET_MAX_TOKENS = 600

#: 片段窗口默认上下文行数（±N）
SNIPPET_DEFAULT_CTX_LINES = 3

#: snippet 一次最多回几个命中窗口（超出则报计数 + 收窄提示，不静默取一个）
SNIPPET_MAX_WINDOWS = 5

#: CJK 判定（估算 token 用）
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")

#: 错误码（改名即破坏调用方契约）
SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
AMBIGUOUS_SECTION = "AMBIGUOUS_SECTION"
NO_HEADINGS = "NO_HEADINGS"
INVALID_LEVEL = "INVALID_LEVEL"
UNSUPPORTED = "UNSUPPORTED"


def estimate_tokens(text: str) -> int:
    """估算 token（N1 静态口径：CJK 1.5 字/token，其它 3.5 字/token）。"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return int(math.ceil(cjk / 1.5 + other / 3.5))


@dataclass(frozen=True, slots=True)
class Section:
    """一个可寻址的节（**区间是原文件 1-based 行号，闭区间**）。"""

    heading: Heading
    end_line_no: int
    """本节最后一行（含）。"""
    text: str
    """本节正文（含标题行）。"""
    line_count: int
    block_count: int
    """空行分隔的正文块数（不含标题行）——outline 的"块计数"。"""

    def ident(self) -> dict:
        out = self.heading.ident()
        out["end_line_no"] = self.end_line_no
        return out


@dataclass
class _Err:
    code: str
    message: str
    extra: dict = field(default_factory=dict)

    def payload(self) -> dict:
        p = {"ok": False, "code": self.code, "message": self.message}
        p.update(self.extra)
        return p


# ── 内部：按 heading 切节 ────────────────────────────────────────────────────
def _section_end_index(lines: list[str], headings: list[Heading], i: int) -> int:
    """第 i 个 heading 的节末行（0-based，不裁剪尾随空行）。"""
    h = headings[i]
    for later in headings[i + 1 :]:
        if later.level <= h.level:
            return later.index0 - 1
    return len(lines) - 1


def _trim_trailing_blank(lines: list[str], start: int, end: int) -> int:
    while end > start and not lines[end].strip():
        end -= 1
    return end


def _count_blocks(body_lines: list[str]) -> int:
    """非空行组成的连续块数（粗略但确定：空行分隔）。"""
    n = 0
    in_block = False
    for line in body_lines:
        if line.strip():
            if not in_block:
                n += 1
                in_block = True
        else:
            in_block = False
    return n


def _build_sections(body: str) -> tuple[list[str], list[Heading], list[Section]]:
    lines = split_lines(body)
    heads = scan_headings(body)
    out: list[Section] = []
    for i, h in enumerate(heads):
        end_raw = _section_end_index(lines, heads, i)
        end = _trim_trailing_blank(lines, h.index0, end_raw)
        body_lines = lines[h.index0 + 1 : end + 1]
        out.append(
            Section(
                heading=h,
                end_line_no=end + 1,
                text="\n".join(lines[h.index0 : end + 1]),
                line_count=end - h.index0 + 1,
                block_count=_count_blocks(body_lines),
            )
        )
    return lines, heads, out


# ── outline ────────────────────────────────────────────────────────────────
def build_outline(body: str, *, max_tokens: int = OUTLINE_MAX_TOKENS) -> dict:
    """标题树 + 每节行号区间 + 块计数；超预算自动降级（见 §降级阶梯）。"""
    lines, heads, sections = _build_sections(body)
    if not heads:
        return {
            "ok": True,
            "headings": [],
            "count": 0,
            "level_dist": {},
            "degraded": [],
            "note": "该文档没有 heading；请用 read_document(offset/limit) 或 #L 行号区间",
            "tokens_estimated": True,
        }

    def node(sec: Section, *, with_text: bool) -> dict:
        h = sec.heading
        d = {
            "title": h.title,
            "level": h.level,
            "line_no": h.line_no,
            "end_line_no": sec.end_line_no,
            "lines": sec.line_count,
            "blocks": sec.block_count,
            "parent_path": list(h.parent_path),
        }
        if with_text:
            d["first_line"] = lines[h.index0].strip()
        return d

    # 降级阶梯：① 全量（含 first_line）② 去 first_line ③ 只留 level<=2 + 其余计数
    attempts: list[tuple[str, list[dict]]] = [
        ("full", [node(s, with_text=True) for s in sections]),
        ("no_first_line", [node(s, with_text=False) for s in sections]),
    ]
    for label, nodes in attempts:
        payload = _outline_payload(nodes, heads, lines)
        if payload["tokens"] <= max_tokens:
            payload["degraded"] = [] if label == "full" else [label]
            return payload

    shallow = [node(s, with_text=False) for s in sections if s.heading.level <= 2]
    payload = _outline_payload(shallow, heads, lines)
    payload["degraded"] = ["level<=2_only"]
    payload["truncated"] = len(shallow) < len(sections)
    payload["omitted_count"] = len(sections) - len(shallow)
    payload["budget_tokens"] = max_tokens
    return payload


def _outline_payload(nodes: list[dict], heads: list[Heading], lines: list[str]) -> dict:
    text = "\n".join(f"{'  ' * (n['level'] - 1)}{n['title']}  (L{n['line_no']}-{n['end_line_no']})" for n in nodes)
    dist: dict[str, int] = {}
    for h in heads:
        dist[str(h.level)] = dist.get(str(h.level), 0) + 1
    return {
        "ok": True,
        "headings": nodes,
        "count": len(nodes),
        "level_dist": {k: dist[k] for k in sorted(dist, key=lambda x: int(x))},
        "tokens": estimate_tokens(text),
        "budget_tokens": OUTLINE_MAX_TOKENS,
        "truncated": False,
        "tokens_estimated": True,
    }


# ── section：D.2 三级消歧 + D.3 失败语义 ───────────────────────────────────
def _candidates(
    heads: list[Heading],
    *,
    title: str | None,
    level: int | None,
    ci: bool,
) -> list[Heading]:
    if title is None:
        return list(heads)
    want = normalize_title(title, ci=ci)
    if ci:
        want = want.lower()
    out = [h for h in heads if (h.title.lower() if ci else h.title) == want]
    if level is not None:
        out = [h for h in out if h.level == level]
    return out


def _path_matches(h: Heading, path: list[str] | str | None, *, ci: bool) -> bool:
    """C2：`path` 是父级标题链，按**后缀**匹配（允许只给最近一级）。"""
    if not path:
        return True
    want = [path] if isinstance(path, str) else list(path)
    if isinstance(path, str):
        want = [p for p in re.split(r"\s*/\s*", path) if p]
    have = list(h.parent_path)
    if ci:
        want = [w.lower() for w in want]
        have = [x.lower() for x in have]
    if len(want) > len(have):
        return False
    return have[len(have) - len(want) :] == want


def _suggestions(heads: list[Heading], title: str) -> list[str]:
    titles = [h.title for h in heads]
    return get_close_matches(title, titles, n=3, cutoff=0.0)


def resolve_section(
    body: str,
    *,
    heading: str | None = None,
    level: int | None = None,
    path: list[str] | str | None = None,
    near_line: int | None = None,
    line: int | None = None,
    ci: bool = False,
    outermost: bool = False,
) -> tuple[Section | None, _Err | None]:
    """按 D.2 解析一个节。

    选择器（优先级）：
      1. `line`（`#L<n>` 一等回退，C4）：取包含该行的节（默认**最深层**，`outermost=True` 取最外层）
      2. `heading`（归一化文本）：① 唯一即命中 ② 多候选用 `path`（C2 父级链）过滤
         ③ 再用 `near_line`（该行之前最近的同名）④ 仍多 ⇒ `AMBIGUOUS_SECTION`（C3）
    """
    if level is not None and not (HEADING_LEVEL_MIN <= level <= HEADING_LEVEL_MAX):
        return None, _Err(
            INVALID_LEVEL,
            f"level 必须在 {HEADING_LEVEL_MIN}..{HEADING_LEVEL_MAX}",
            {"actual_levels": sorted({h.level for h in scan_headings(body)})},
        )

    lines, heads, sections = _build_sections(body)
    if not heads:
        return None, _Err(NO_HEADINGS, "该文档没有 heading", {"suggestion": "整篇读取，或按 #L 行号区间引用"})

    # ① C4：按行号（一等回退）
    if line is not None:
        if line < 1 or line > len(lines):
            return None, _Err(
                SECTION_NOT_FOUND,
                f"行号 {line} 超出文档范围（1..{len(lines)}）",
                {"suggestions": [], "candidate_count": 0},
            )
        containing = [
            (i, s) for i, s in enumerate(sections) if s.heading.line_no <= line <= s.end_line_no
        ]
        if not containing:
            return None, _Err(
                SECTION_NOT_FOUND,
                f"行号 {line} 不在任何节内",
                {"suggestions": _suggestions(heads, ""), "candidate_count": 0},
            )
        if outermost:
            return containing[0][1], None
        return containing[-1][1], None  # 最深层（最后出现的包含者即是嵌套最深的）

    if heading is None:
        # 无选择器：取第一个节（调用方若要全篇应走 read_document）
        return sections[0], None

    cands = _candidates(heads, title=heading, level=level, ci=ci)
    if not cands:
        return None, _Err(
            SECTION_NOT_FOUND,
            f"找不到标题 {heading!r}",
            {"suggestions": _suggestions(heads, heading), "candidate_count": 0},
        )
    if len(cands) > 1 and path:
        cands = [h for h in cands if _path_matches(h, path, ci=ci)]
        if not cands:
            return None, _Err(
                SECTION_NOT_FOUND,
                f"标题 {heading!r} 存在但父级路径 {path!r} 下没有",
                {"suggestions": _suggestions(heads, heading), "candidate_count": 0},
            )
    if len(cands) > 1 and near_line is not None:
        before = [h for h in cands if h.line_no <= near_line]
        if before:
            cands = [before[-1]]
    if len(cands) > 1:
        return None, _Err(
            AMBIGUOUS_SECTION,
            f"标题 {heading!r} 有 {len(cands)} 个同名候选，无法唯一确定（C3：不取首个）",
            {
                "candidates": [h.ident() for h in cands],
                "how_to_disambiguate": "传入 path=[父级标题…] 或 near_line=<行号>，或用 line=<#L行号>",
            },
        )
    sec = next(s for s in sections if s.heading is cands[0])
    return sec, None


def get_section(
    body: str,
    *,
    max_tokens: int = SECTION_MAX_TOKENS,
    **selector,
) -> dict:
    """取单节正文；超预算切成 `part i/n` + `next_cursor`（不静默截断）。"""
    sec, err = resolve_section(body, **selector)
    if err is not None:
        return err.payload()

    text = sec.text
    tokens = estimate_tokens(text)
    base = {
        "ok": True,
        "section": {**sec.ident(), "blocks": sec.block_count, "lines": sec.line_count},
        "tokens": tokens,
        "budget_tokens": max_tokens,
        "tokens_estimated": True,
    }
    if tokens <= max_tokens:
        return {**base, "text": text, "part": 1, "parts": 1, "next_cursor": None, "truncated": False}

    # 超预算：按"行 + token 预算"切片，保证每片 ≤ 预算
    chunks: list[str] = []
    cur: list[str] = []
    for ln in text.split("\n"):
        trial = "\n".join([*cur, ln])
        if cur and estimate_tokens(trial) > max_tokens:
            chunks.append("\n".join(cur))
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        chunks.append("\n".join(cur))

    return {
        **base,
        "text": chunks[0],
        "part": 1,
        "parts": len(chunks),
        "next_cursor": {"kind": "section_part", "line_no": sec.heading.line_no, "part": 2},
        "truncated": True,
        "note": f"本节 {tokens} tok 超预算 {max_tokens}；已切 {len(chunks)} 片，续读用 next_cursor",
    }


def get_section_part(
    body: str,
    *,
    part: int,
    max_tokens: int = SECTION_MAX_TOKENS,
    **selector,
) -> dict:
    """取 `part i/n` 的第 i 片（配合 `next_cursor` 使用）。"""
    first = get_section(body, max_tokens=max_tokens, **selector)
    if not first.get("ok"):
        return first
    parts = int(first["parts"])
    if part < 1 or part > parts:
        return {
            "ok": False,
            "code": SECTION_NOT_FOUND,
            "message": f"part {part} 超出范围 1..{parts}",
            "suggestions": [],
            "candidate_count": 0,
        }
    # 重新切（确定性：同一 body/预算 ⇒ 同一分片）
    sec, _ = resolve_section(body, **selector)
    assert sec is not None
    chunks: list[str] = []
    cur: list[str] = []
    for ln in sec.text.split("\n"):
        trial = "\n".join([*cur, ln])
        if cur and estimate_tokens(trial) > max_tokens:
            chunks.append("\n".join(cur))
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        chunks.append("\n".join(cur))
    return {
        "ok": True,
        "section": {**sec.ident(), "blocks": sec.block_count, "lines": sec.line_count},
        "text": chunks[part - 1],
        "part": part,
        "parts": parts,
        "next_cursor": (
            {"kind": "section_part", "line_no": sec.heading.line_no, "part": part + 1}
            if part < parts
            else None
        ),
        "truncated": True,
        "tokens_estimated": True,
    }


# ── snippet ────────────────────────────────────────────────────────────────
def _fit_window(
    lines: list[str], hit: int, ctx: int, budget: int
) -> tuple[int, int, str, int, bool]:
    """把单个命中窗口压进 `budget`：先缩 ±ctx，仍超则截断该行字符。

    返回 `(start_line_no, end_line_no, text, ctx_used, chars_truncated)`。
    """
    ctx_use = ctx
    while True:
        a = max(1, hit - ctx_use)
        b = min(len(lines), hit + ctx_use)
        text = "\n".join(lines[a - 1 : b])
        if estimate_tokens(text) <= budget:
            return a, b, text, ctx_use, False
        if ctx_use == 0:
            raw = lines[hit - 1]
            lo, hi = 0, len(raw)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if estimate_tokens(raw[:mid] + "…") <= budget:
                    lo = mid
                else:
                    hi = mid - 1
            return hit, hit, raw[:lo] + "…", 0, True
        ctx_use -= 1


def get_snippet(
    body: str,
    *,
    query: str | None = None,
    line: int | None = None,
    ctx_lines: int = SNIPPET_DEFAULT_CTX_LINES,
    max_tokens: int = SNIPPET_MAX_TOKENS,
) -> dict:
    """命中窗口（±N 行）。多命中时回最多 `SNIPPET_MAX_WINDOWS` 个窗口 + 总命中数。

    **硬预算**：`tokens`（所有窗口合计）≤ `max_tokens`。做法：先把预算按窗口数均分，
    每窗口内先缩 ±ctx、必要时截断该行字符；连"均分额度"都不够的窗口不再纳入（如实报数）。
    """
    lines = split_lines(body)
    if query is None and line is None:
        return {
            "ok": False,
            "code": UNSUPPORTED,
            "message": "snippet 需要 query 或 line 之一",
        }

    hits: list[int] = []
    if line is not None:
        if line < 1 or line > len(lines):
            return {
                "ok": False,
                "code": SECTION_NOT_FOUND,
                "message": f"行号 {line} 超出 1..{len(lines)}",
                "suggestions": [],
                "candidate_count": 0,
            }
        hits = [line]
    else:
        q = query or ""
        for i, ln in enumerate(lines, start=1):
            if q in ln:
                hits.append(i)
        if not hits:
            return {
                "ok": True,
                "windows": [],
                "match_count": 0,
                "scanned_lines": len(lines),
                "note": "0 命中（已按子串扫描全文）",
                "tokens_estimated": True,
            }

    n_show = min(len(hits), SNIPPET_MAX_WINDOWS)
    per_window_budget = max(80, max_tokens // max(1, n_show))

    windows: list[dict] = []
    spent = 0
    for hit in hits[:n_show]:
        remaining = max_tokens - spent
        if remaining < 80:
            break
        a, b, text, ctx_used, chars_trunc = _fit_window(
            lines, hit, ctx_lines, min(per_window_budget, remaining)
        )
        tk = estimate_tokens(text)
        windows.append(
            {
                "line_no": hit,
                "start_line_no": a,
                "end_line_no": b,
                "text": text,
                "tokens": tk,
                "ctx_lines": ctx_used,
                "chars_truncated": chars_trunc,
            }
        )
        spent += tk

    return {
        "ok": True,
        "windows": windows,
        "match_count": len(hits),
        "shown": len(windows),
        "truncated": len(hits) > len(windows),
        "tokens": spent,
        "budget_tokens": max_tokens,
        "tokens_estimated": True,
        "note": (
            None
            if len(hits) <= len(windows)
            else f"共 {len(hits)} 处命中，只回 {len(windows)} 个窗口（受预算 {max_tokens} tok 限制）；"
            f"收窄 query 或改用 section"
        ),
    }


__all__ = [
    "OUTLINE_MAX_TOKENS",
    "SECTION_MAX_TOKENS",
    "SNIPPET_MAX_TOKENS",
    "Section",
    "build_outline",
    "resolve_section",
    "get_section",
    "get_section_part",
    "get_snippet",
    "estimate_tokens",
    "SECTION_NOT_FOUND",
    "AMBIGUOUS_SECTION",
    "NO_HEADINGS",
    "INVALID_LEVEL",
    "UNSUPPORTED",
]
