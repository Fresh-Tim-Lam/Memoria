#!/usr/bin/env python
"""从已抓取的 OpenStax 章节 HTML 构建确定性纯文本语料快照（pilot 源）。

为什么要单独脚本（C0 / C4 / C10）：
- KP 的 span 必须锚定在一个**字节确定、可复核**的纯文本文件上，而不是活的网页；
- 抓取与抽取分离：raw HTML 原样落盘（含 sha256），抽取规则版本化，
  二次运行必须产出相同 chapter.txt（2× 可复现，见 `validate_pilot.py`）；
- 只抽取 `#main-content` 区域，去掉 script/style/svg/导航；不执行页面任何脚本。

输入：`artifacts/corpus/pilot/source/pages.json`（page_id/kind/section/title/url/raw_path）
输出：
  - `artifacts/corpus/pilot/source/chapter.txt`（UTF-8, LF；KP span 的坐标系）
  - `artifacts/corpus/pilot/source/sections.json`（每个 page 的区间 + 标题块）
  - `artifacts/corpus/pilot/source/snapshot-meta.json`（sha256/规则版本/统计）

坐标约定：`chapter.txt` 解码后的 **Unicode code point 偏移**（Python `str` 下标），
左闭右开 `[start, end)`；不允许 CRLF / BOM。

用法：
  python scripts/corpus/build_source_snapshot.py \
      --pages artifacts/corpus/pilot/source/pages.json \
      --out artifacts/corpus/pilot/source
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

TOOL_VERSION = "corpus-pilot-source-snapshot/v1"
BLOCK_TAGS = {
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
    "p": "paragraph",
    "li": "list_item",
    "blockquote": "quote",
    "figcaption": "caption",
    "dt": "term",
    "dd": "definition",
}
SKIP_TAGS = {"script", "style", "svg", "noscript", "button", "template", "head"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _MainContentParser(HTMLParser):
    """抽取 `<div id="main-content">` 内的块级文本；不执行脚本。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.div_depth = 0
        self.skip_depth = 0
        self.block_type: str | None = None
        self.block_level: int = 0
        self.buffer: list[str] = []
        self.cell_buffer: list[str] = []
        self.row_cells: list[str] = []
        self.in_table_row = False
        self.blocks: list[dict] = []

    # -- helpers ---------------------------------------------------------
    def _flush(self) -> None:
        text = _norm("".join(self.buffer))
        if text:
            self.blocks.append({"type": self.block_type or "paragraph",
                                "level": self.block_level, "text": text})
        self.buffer = []
        self.block_type = None
        self.block_level = 0

    def _open_block(self, btype: str, level: int = 0) -> None:
        if self.block_type is not None:
            self._flush()
        self.block_type = btype
        self.block_level = level

    # -- parser hooks ----------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if not self.in_main:
            if tag == "div" and attr.get("id") == "main-content":
                self.in_main = True
                self.div_depth = 1
            return
        if tag == "div":
            self.div_depth += 1
        if tag in SKIP_TAGS or attr.get("aria-hidden") == "true":
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in BLOCK_TAGS:
            self._open_block(BLOCK_TAGS[tag], int(tag[1]) if tag.startswith("h") else 0)
            return
        if tag == "tr":
            if self.block_type is not None:
                self._flush()
            self.in_table_row = True
            self.row_cells = []
            self.buffer = []
            return
        if tag in ("td", "th"):
            self.cell_buffer = []
            return
        if tag == "br":
            self.buffer.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_main:
            return
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            if tag == "div":
                self.div_depth -= 1
                if self.div_depth <= 0:
                    self.in_main = False
            return
        if self.skip_depth:
            if tag == "div":
                self.div_depth -= 1
            return
        if tag == "div":
            self.div_depth -= 1
            if self.div_depth <= 0:
                self._flush()
                self.in_main = False
                return
        if tag in ("td", "th"):
            cell = _norm("".join(self.cell_buffer))
            if cell:
                self.row_cells.append(cell)
            self.cell_buffer = []
            return
        if tag == "tr":
            row = " | ".join(self.row_cells)
            if row:
                self.blocks.append({"type": "table_row", "level": 0, "text": row})
            self.in_table_row = False
            self.row_cells = []
            self.buffer = []
            return
        if tag in BLOCK_TAGS and self.block_type == BLOCK_TAGS[tag]:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self.in_main or self.skip_depth:
            return
        if self.cell_buffer is not None and self.in_table_row:
            self.cell_buffer.append(data)
            return
        if self.block_type is not None:
            self.buffer.append(data)


def _norm(text: str) -> str:
    """压缩空白；保留可读单空格。"""
    return " ".join(text.replace("\u00a0", " ").split())


def extract_page(html: str) -> list[dict]:
    parser = _MainContentParser()
    parser.feed(html)
    parser.close()
    if parser.in_main:
        parser._flush()
    return parser.blocks


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(pages_path: Path) -> dict:
    """从 pages.json + raw HTML 重建 chapter_text / sections / 扁平 block 列表。

    `build_source_snapshot.py` 与 `make_annotations.py` 共用本函数，保证
    “快照字符偏移”只有一个实现（避免两套坐标算法漂移）。
    """
    manifest = json.loads(pages_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "corpus-pilot-source-pages/v1":
        raise ValueError(f"未知 pages schema: {manifest.get('schema')!r}")

    chapter_parts: list[str] = []
    sections: list[dict] = []
    cursor = 0
    all_blocks_flat: list[dict] = []

    for page in manifest["pages"]:
        raw_path = Path(page["raw_path"])
        raw_bytes = raw_path.read_bytes()
        raw_sha = hashlib.sha256(raw_bytes).hexdigest()
        if raw_sha != page["raw_sha256"]:
            raise ValueError(f"raw sha 不符：{raw_path} ({raw_sha} != {page['raw_sha256']})")
        html = raw_bytes.decode("utf-8")
        blocks = extract_page(html)
        if not blocks:
            raise ValueError(f"未抽取到任何块：{raw_path}")

        start = cursor
        section_blocks: list[dict] = []
        for idx, block in enumerate(blocks):
            if chapter_parts:
                chapter_parts.append("\n\n")
                cursor += 2
            text = block["text"]
            chapter_parts.append(text)
            block_start = cursor
            cursor += len(text)
            flat = {
                "page_id": page["page_id"],
                "block_index": idx,
                "type": block["type"],
                "level": block["level"],
                "start": block_start,
                "end": cursor,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            section_blocks.append(flat)
            all_blocks_flat.append(flat)
        sections.append({
            "page_id": page["page_id"],
            "kind": page["kind"],
            "section_num": page.get("section_num"),
            "title": page["title"],
            "url": page["url"],
            "raw_path": page["raw_path"],
            "raw_sha256": raw_sha,
            "start": start,
            "end": cursor,
            "block_count": len(section_blocks),
            "heading": page["title"],
        })

    chapter_text = "".join(chapter_parts)
    if "\r" in chapter_text:
        raise ValueError("chapter.txt 不允许包含 CR")
    return {"manifest": manifest, "chapter_text": chapter_text,
            "sections": sections, "blocks": all_blocks_flat}


def build(pages_path: Path, out_dir: Path) -> dict:
    collected = collect(pages_path)
    manifest = collected["manifest"]
    chapter_text = collected["chapter_text"]
    sections = collected["sections"]
    all_blocks_flat = collected["blocks"]
    out_dir.mkdir(parents=True, exist_ok=True)
    chapter_path = out_dir / "chapter.txt"
    chapter_path.write_text(chapter_text, encoding="utf-8", newline="\n")

    sections_path = out_dir / "sections.json"
    sections_path.write_text(json.dumps({
        "schema": "corpus-pilot-sections/v1",
        "coordinate_system": "unicode-code-point-offsets-half-open",
        "chapter_file": "artifacts/corpus/pilot/source/chapter.txt",
        "chapter_sha256": hashlib.sha256(chapter_text.encode("utf-8")).hexdigest(),
        "chapter_chars": len(chapter_text),
        "sections": sections,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    meta = {
        "schema": "corpus-pilot-snapshot-meta/v1",
        "tool": TOOL_VERSION,
        "pages_manifest": "artifacts/corpus/pilot/source/pages.json",
        "pages_manifest_sha256": _sha256_file(pages_path),
        "chapter_file": "artifacts/corpus/pilot/source/chapter.txt",
        "chapter_sha256": hashlib.sha256(chapter_text.encode("utf-8")).hexdigest(),
        "chapter_bytes": len(chapter_text.encode("utf-8")),
        "chapter_chars": len(chapter_text),
        "sections_file": "artifacts/corpus/pilot/source/sections.json",
        "sections_sha256": _sha256_file(sections_path),
        "page_count": len(sections),
        "block_count": len(all_blocks_flat),
        "block_type_counts": _counts(b["type"] for b in all_blocks_flat),
        "extraction_rules": {
            "scope": "div#main-content only",
            "skip_tags": sorted(SKIP_TAGS),
            "skip_aria_hidden": True,
            "block_types": sorted(set(BLOCK_TAGS.values())) + ["table_row"],
            "whitespace": "collapse all runs of whitespace to single space; NBSP -> space",
            "line_endings": "LF",
            "encoding": "UTF-8 without BOM",
            "offsets": "Unicode code point offsets, half-open [start,end)",
        },
    }
    (out_dir / "snapshot-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return meta


def _counts(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build deterministic corpus pilot source snapshot")
    ap.add_argument("--pages", default="artifacts/corpus/pilot/source/pages.json")
    ap.add_argument("--out", default="artifacts/corpus/pilot/source")
    args = ap.parse_args(argv)
    try:
        meta = build(Path(args.pages), Path(args.out))
        print(json.dumps({
            "ok": True,
            "chapter_sha256": meta["chapter_sha256"],
            "chapter_chars": meta["chapter_chars"],
            "pages": meta["page_count"],
            "blocks": meta["block_count"],
            "block_types": meta["block_type_counts"],
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 —— 失败必须可见
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
