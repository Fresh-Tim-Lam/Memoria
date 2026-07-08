"""Markdown 正文解析。"""

from __future__ import annotations

import yaml


def strip_frontmatter(text: str) -> tuple[str, dict | None]:
    if not text.startswith("---"):
        return text, None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text, None
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return text, None
    return parts[2].lstrip("\n"), fm if isinstance(fm, dict) else None


def compose_markdown(body: str, frontmatter: dict | None) -> str:
    """将正文与 frontmatter 合并写回 .md。"""
    if not frontmatter:
        return body
    fm_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm_text}\n---\n{body}"
