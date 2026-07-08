"""Lexical 分词（jieba + 拼音；字面层不做手工符号别名表）。"""

from __future__ import annotations

import os
import re

_ASCII_WORD = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.I)
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_JIEBA_READY = False


def configure_jieba_cache(kb_path: str | None) -> None:
    """将 jieba 缓存定向到知识库 `.memoria/cache/lexical/jieba/`。"""
    if not kb_path:
        return
    cache_dir = os.path.join(kb_path, ".memoria", "cache", "lexical", "jieba")
    os.makedirs(cache_dir, exist_ok=True)
    os.environ["JIEBA_CACHE_DIR"] = cache_dir


def _ensure_jieba() -> bool:
    global _JIEBA_READY
    if _JIEBA_READY:
        return True
    try:
        import jieba  # noqa: F401

        _JIEBA_READY = True
        return True
    except ImportError:
        return False


def _fallback_tokens(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _ASCII_WORD.finditer(text or ""):
        t = m.group(0).lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    for m in _CJK_RUN.finditer(text or ""):
        run = m.group(0)
        if len(run) <= 2:
            t = run.lower()
            if t not in seen:
                seen.add(t)
                out.append(t)
            continue
        for i in range(len(run) - 1):
            bg = run[i : i + 2].lower()
            if bg not in seen:
                seen.add(bg)
                out.append(bg)
    return out


def pinyin_compact(text: str) -> str:
    """中文 → 无调拼音（算法化同音匹配，非手工同义词表）。"""
    raw = (text or "").strip()
    if not raw or not _CJK_RUN.search(raw):
        return ""
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError:
        return ""
    parts = lazy_pinyin(raw, style=Style.NORMAL, errors="ignore")
    return "".join(p for p in parts if p).lower()


def pinyin_tokens(text: str) -> list[str]:
    compact = pinyin_compact(text)
    return [compact] if compact else []


def tokenize(text: str, *, kb_path: str | None = None) -> list[str]:
    """分词；去重保序，token 小写。"""
    raw = (text or "").strip()
    if not raw:
        return []
    if kb_path:
        configure_jieba_cache(kb_path)
    tokens: list[str] = []
    seen: set[str] = set()

    def add(tok: str) -> None:
        t = (tok or "").strip().lower()
        if len(t) < 1 or t in seen:
            return
        seen.add(t)
        tokens.append(t)

    if _ensure_jieba():
        import jieba

        for part in jieba.cut(raw, cut_all=False):
            add(part)
    else:
        for t in _fallback_tokens(raw):
            add(t)

    for m in _ASCII_WORD.finditer(raw):
        add(m.group(0))

    for py in pinyin_tokens(raw):
        add(py)

    add(raw.lower())
    return tokens


def tokenize_identifier(value: str) -> list[str]:
    """KP id：整段 + 按 `-_/` 拆分。"""
    v = (value or "").strip()
    if not v:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(t: str) -> None:
        tl = t.lower()
        if tl and tl not in seen:
            seen.add(tl)
            out.append(tl)

    add(v)
    for part in re.split(r"[-_/]+", v):
        add(part)
    return out
