#!/usr/bin/env python
"""把抓取原始日志整理成 pilot 源清单（pages.json / license-evidence.json / fetch-log.json）。

输入：
  - `artifacts/corpus/pilot/source/fetch-log.partial.json`：抓取时记录的
    page / url / http_status / title / bytes / sha256（curl GET 实测）；
  - `artifacts/corpus/pilot/source/raw/*.html`：原样字节（sha256 与日志交叉核对）；
  - `artifacts/corpus/pilot/source/evidence/*`：许可定义证据（SPDX / Choose a License / 仓库 LICENSE）。
输出：
  - `fetch-log.json`：全部抓取记录（含 raw 本地路径、文件 mtime 作为 verified_at）；
  - `pages.json`：章节正文页（供 build_source_snapshot.py）；
  - `license-evidence.json`：许可/署名证据页（不进入 chapter.txt）。

只离线整理，不发网络请求；任何 sha/大小不符立即失败（不静默）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

CHAPTER_PAGES = {
    "1-introduction": {"page_id": "ch1-intro", "kind": "chapter_intro", "section_num": None,
                       "section_key": "ch1-intro"},
    "1-1-the-nature-of-business": {"page_id": "ch1-s1", "kind": "section", "section_num": "1.1",
                                   "section_key": "ch1-s1"},
    "1-2-understanding-the-business-environment": {"page_id": "ch1-s2", "kind": "section",
                                                   "section_num": "1.2", "section_key": "ch1-s2"},
    "1-3-how-business-and-economics-work": {"page_id": "ch1-s3", "kind": "section",
                                            "section_num": "1.3", "section_key": "ch1-s3"},
    "1-4-macroeconomics-the-big-picture": {"page_id": "ch1-s4", "kind": "section",
                                           "section_num": "1.4", "section_key": "ch1-s4"},
    "1-5-achieving-macroeconomic-goals": {"page_id": "ch1-s5", "kind": "section",
                                          "section_num": "1.5", "section_key": "ch1-s5"},
    "1-6-microeconomics-zeroing-in-on-businesses-and-consumers": {
        "page_id": "ch1-s6", "kind": "section", "section_num": "1.6", "section_key": "ch1-s6"},
    "1-7-competing-in-a-free-market": {"page_id": "ch1-s7", "kind": "section", "section_num": "1.7",
                                       "section_key": "ch1-s7"},
    "1-8-trends-in-the-business-environment-and-competition": {
        "page_id": "ch1-s8", "kind": "section", "section_num": "1.8", "section_key": "ch1-s8"},
    "1-key-terms": {"page_id": "ch1-key-terms", "kind": "key_terms", "section_num": None,
                    "section_key": "ch1-key-terms"},
    "1-summary-of-learning-outcomes": {"page_id": "ch1-summary", "kind": "summary",
                                       "section_num": None, "section_key": "ch1-summary"},
}

LICENSE_EVIDENCE = {
    "preface": {
        "evidence_kind": "book_license_statement",
        "note": "OpenStax 官方图书前言页，含本书 CC BY 4.0 许可声明与署名要求。",
    },
    "spdx-cc-by-4.0.html": {
        "evidence_kind": "spdx_license_definition",
        "url": "https://spdx.org/licenses/CC-BY-4.0.html",
        "note": "SPDX 官方 CC-BY-4.0 许可证定义页（许可短标识覆盖正文与图表，除非逐项标注例外）。",
    },
    "choosealicense-cc-by-4.0.html": {
        "evidence_kind": "license_plain_language",
        "url": "https://choosealicense.com/licenses/cc-by-4.0/",
        "note": "CC BY 4.0 的通俗条款说明（署名/再分发/修改标注）。",
    },
    "osbooks-introduction-business-LICENSE.txt": {
        "evidence_kind": "book_repository_license_text",
        "url": "https://cdn.jsdelivr.net/gh/openstax/osbooks-introduction-business@main/LICENSE",
        "note": ("OpenStax 图书仓库 LICENSE 原文 = CC BY 4.0 法律文本；"
                 "该仓库 README 另有“NC-SA”旧文案，属上游文案不一致，已在本 pilot "
                 "SOURCE-LICENSE.md 记录并以出版前言页为准。"),
    },
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mtime_iso(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def build(source_dir: Path) -> dict:
    raw_dir = source_dir / "raw"
    ev_dir = source_dir / "evidence"
    partial = json.loads((source_dir / "fetch-log.partial.json").read_text(encoding="utf-8-sig"))
    by_page = {row["page"]: row for row in partial}

    fetch_log: list[dict] = []
    pages: list[dict] = []
    for page, meta in CHAPTER_PAGES.items():
        row = by_page[page]
        raw_path = raw_dir / f"{page}.html"
        raw_sha = _sha(raw_path)
        if raw_sha != row["sha256"]:
            raise SystemExit(f"raw sha 不符: {raw_path}")
        if raw_path.stat().st_size != row["bytes"]:
            raise SystemExit(f"raw 大小不符: {raw_path}")
        entry = {
            "page": page,
            "url": row["url"],
            "http_status": row["http_status"],
            "title": row["title"],
            "bytes": row["bytes"],
            "sha256": raw_sha,
            "local_path": str(raw_path).replace("\\", "/"),
            "verified_at": _mtime_iso(raw_path),
            "method": "HTTP GET (curl, browser UA, no JS execution)",
            "purpose": "chapter content",
        }
        fetch_log.append(entry)
        pages.append({
            **meta,
            "title": row["title"],
            "url": row["url"],
            "http_status": row["http_status"],
            "raw_path": entry["local_path"],
            "raw_sha256": raw_sha,
            "fetched_at": entry["verified_at"],
        })

    evidence: list[dict] = []
    rows = [
        dict(LICENSE_EVIDENCE["preface"], name="preface",
             local_path=str(raw_dir / "preface.html").replace("\\", "/"),
             url=by_page["preface"]["url"], http_status=by_page["preface"]["http_status"],
             title=by_page["preface"]["title"], expected_sha=by_page["preface"]["sha256"],
             expected_bytes=by_page["preface"]["bytes"]),
        dict(LICENSE_EVIDENCE["spdx-cc-by-4.0.html"], name="spdx-cc-by-4.0.html",
             local_path=str(ev_dir / "spdx-cc-by-4.0.html").replace("\\", "/"),
             http_status=200, title="Creative Commons Attribution 4.0 International | Software Package Data Exchange (SPDX)"),
        dict(LICENSE_EVIDENCE["choosealicense-cc-by-4.0.html"], name="choosealicense-cc-by-4.0.html",
             local_path=str(ev_dir / "choosealicense-cc-by-4.0.html").replace("\\", "/"),
             http_status=200, title="Creative Commons Attribution 4.0 International | Choose a License"),
        dict(LICENSE_EVIDENCE["osbooks-introduction-business-LICENSE.txt"],
             name="osbooks-introduction-business-LICENSE.txt",
             local_path=str(ev_dir / "osbooks-introduction-business-LICENSE.txt").replace("\\", "/"),
             http_status=200, title="(plain text license)"),
    ]
    for row in rows:
        path = Path(row["local_path"])
        if not path.exists():
            raise SystemExit(f"许可证据文件缺失: {path}")
        sha = _sha(path)
        if "expected_sha" in row and sha != row["expected_sha"]:
            raise SystemExit(f"许可证据 sha 不符: {path}")
        if "expected_bytes" in row and path.stat().st_size != row["expected_bytes"]:
            raise SystemExit(f"许可证据大小不符: {path}")
        evidence.append({
            "name": row["name"],
            "evidence_kind": row["evidence_kind"],
            "url": row["url"],
            "http_status": row.get("http_status"),
            "title": row.get("title"),
            "bytes": path.stat().st_size,
            "sha256": sha,
            "local_path": row["local_path"],
            "verified_at": _mtime_iso(path),
            "note": row["note"],
            "is_license_evidence": True,
        })

    book = {
        "title": "Introduction to Business",
        "edition": "1e (openstax.org/books/introduction-business)",
        "publisher": "OpenStax (Rice University)",
        "license": "CC BY 4.0",
        "spdx": "CC-BY-4.0",
        "license_tier": "A",
        "redistribution": "allowed with attribution",
        "language": "en",
        "chapter": "Chapter 1: Understanding Economic Systems and Business",
    }
    (source_dir / "pages.json").write_text(json.dumps({
        "schema": "corpus-pilot-source-pages/v1",
        "book": book,
        "pages": pages,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (source_dir / "license-evidence.json").write_text(json.dumps({
        "schema": "corpus-pilot-license-evidence/v1",
        "book": book,
        "evidence": evidence,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (source_dir / "fetch-log.json").write_text(json.dumps({
        "schema": "corpus-pilot-fetch-log/v1",
        "verified_on": datetime.now().astimezone().date().isoformat(),
        "method": "HTTP GET via curl 8.x, browser User-Agent, no JavaScript execution",
        "records": fetch_log + evidence,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"pages": len(pages), "license_evidence": len(evidence),
            "fetch_records": len(fetch_log) + len(evidence)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assemble pilot source manifests from fetch log")
    ap.add_argument("--source", default="artifacts/corpus/pilot/source")
    args = ap.parse_args(argv)
    res = build(Path(args.source))
    print(json.dumps({"ok": True, **res}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
