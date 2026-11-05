#!/usr/bin/env python
"""Build a draft human judge pack for the evaluation-first corpus pilot.

This is deliberately a *draft* pack: it reuses the frozen source chapter, the
machine KP candidates and the 20 draft queries. It is not a C0 gate artifact.
It emits a blind judge pack (no expected ids), a separate answer key, a CSV/
JSONL judge sheet, A/B presentation tasks, and a small zip that excludes the
chapter in full.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAPTER = ROOT / "artifacts/corpus/pilot/source/chapter.txt"
KPS = ROOT / "artifacts/corpus/pilot/annotations/kps.single.jsonl"
QUERIES = ROOT / "docs/design/corpus-seminar/pilot/queries.json"
IMAGES = ROOT / "artifacts/agent/verify/graph/visual-parity"
OUT = ROOT / "artifacts/corpus/pilot/judge"
ZIP = ROOT / "artifacts/corpus/pilot/JUDGE-PACK.zip"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clip(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "â€¦"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261105)
    args = ap.parse_args()
    chapter = CHAPTER.read_text(encoding="utf-8")
    kps = {k["id"]: k for k in read_jsonl(KPS)}
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    if len(queries) != 20:
        raise SystemExit(f"expected 20 queries, got {len(queries)}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    rng = random.Random(args.seed)

    def kp_quote(kp: dict) -> tuple[str, str, int, int]:
        ev = (kp.get("evidence") or [{}])[0]
        quote = ev.get("quote") or kp.get("name") or ""
        return quote, kp.get("section_key") or "ch1-?", int(ev.get("start") or 0), int(ev.get("end") or 0)

    blind_questions = []
    key_questions = []
    total_context = 0
    for q in queries:
        expected = [k for k in q.get("expected_kp_ids", []) if k in kps]
        snippets = []
        seen = set()
        for kid in expected:
            quote, section, start, end = kp_quote(kps[kid])
            if not quote or quote in seen:
                continue
            seen.add(quote)
            snippets.append({
                "snippet_id": f"s{len(snippets)+1}",
                "section_key": section,
                "start": start,
                "end": end,
                "text": clip(quote, 260),
            })
        # deterministic distractors from other sections, until 4 snippets
        candidates = [k for k in kps.values() if k.get("section_key") != (kps[expected[0]].get("section_key") if expected else "")]
        offset = (int(sha(q["id"])[:8], 16) + args.seed) % max(1, len(candidates))
        candidates = candidates[offset:] + candidates[:offset]
        for d in candidates:
            if len(snippets) >= 4:
                break
            quote, section, start, end = kp_quote(d)
            if quote and quote not in seen:
                seen.add(quote)
                snippets.append({
                    "snippet_id": f"s{len(snippets)+1}",
                    "section_key": section,
                    "start": start,
                    "end": end,
                    "text": clip(quote, 260),
                })
        # last-resort chapter windows around the expected span (not full text)
        if len(snippets) < 3 and expected:
            _, _, start, end = kp_quote(kps[expected[0]])
            for pad in (120, 240, 360):
                if len(snippets) >= 3:
                    break
                a, b = max(0, start - pad), min(len(chapter), end + pad)
                text = clip(chapter[a:b], 260)
                if text and text not in seen:
                    seen.add(text)
                    snippets.append({"snippet_id": f"s{len(snippets)+1}", "section_key": kps[expected[0]].get("section_key") or "ch1-?", "start": a, "end": b, "text": text})
        snippets = snippets[:5]
        if len(snippets) < 3:
            raise SystemExit(f"{q['id']}: fewer than 3 snippets")
        total_context += sum(len(s["text"]) for s in snippets)
        candidate_answer = "ï¼›".join(
            clip((kps[k].get("name") or "") + "ï¼š" + (kps[k].get("description") or ""), 220)
            for k in expected
        )[:520]
        blind_questions.append({
            "question_id": q["id"],
            "question": q["query"],
            "type": q["query_type"],
            "split": q.get("split", "dev"),
            "control": bool(q.get("control")),
            "candidate_answer": candidate_answer,
            "snippets": snippets,
        })
        key_questions.append({
            "question_id": q["id"],
            "expected_kp_ids": q.get("expected_kp_ids", []),
            "expected_edge_ids": q.get("expected_edge_ids", []),
            "rationale": q.get("rationale", ""),
            "control": bool(q.get("control")),
        })

    pack = {
        "schema": "memoria-judge-pack-draft/v1",
        "status": "draft_pre_amendment",
        "not_c8_conclusion": True,
        "source_chapter_sha256": sha(chapter),
        "n_questions": len(blind_questions),
        "note": "Draft only: answer candidates come from machine KP descriptions; judge independently. Do not use as C0 gate evidence.",
        "questions": blind_questions,
    }
    key = {"schema": "memoria-judge-key/v1", "questions": key_questions}
    (OUT / "judge-pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT.parent / "judge-answer-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")

    judge_rows = []
    for q in blind_questions:
        judge_rows.append({
            "question_id": q["question_id"],
            "answer_correct": "",
            "citation_supported": "",
            "citation_ids": "",
            "abstain_expected": "",
            "time_s": "",
            "notes": "",
        })
    with (OUT / "judge-sheet.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(judge_rows[0]))
        w.writeheader()
        w.writerows(judge_rows)
    (OUT / "judge-sheet.jsonl").write_text(
        "\n".join(json.dumps({k: (v if v != "" else None) for k, v in r.items()}, ensure_ascii=False) for r in judge_rows) + "\n",
        encoding="utf-8",
    )

    (OUT / "JUDGE-GUIDE.md").write_text(
        """# JUDGE-PACKï¼ˆè‰ç¨¿ï¼‰â€” 20 é¢˜ç›²åˆ¤

> **è¿™æ˜¯è‰ç¨¿åŒ…ï¼Œä¸æ˜¯ C0 gate è¯æ®ã€‚** é¢˜ç›®æ¥è‡ª pilot æ—¢æœ‰ 20 æ¡ queryï¼›ç­”æ¡ˆå€™é€‰æ¥è‡ªæœºå™¨ KP æè¿°ï¼›ä½ ç‹¬ç«‹åˆ¤æ–­ï¼Œä¸è¢«â€œé¢„æœŸ KPâ€å½±å“ã€‚
> ä¸è¦è¯» `answer-key.json`ï¼ˆè¯„åˆ†ç”¨ï¼Œä¸æ˜¯ç»™ä½ çœ‹çš„ï¼‰ã€‚

## ä½ è¦åšçš„ï¼ˆçº¦ 2â€“3 å°æ—¶ï¼‰

1. æ‰“å¼€ `judge-pack.json` æˆ– `judge-sheet.csv`ï¼›æ¯é¢˜æœ‰ 1 ä¸ªå€™é€‰ç­”æ¡ˆ + 3â€“5 ä¸ªå€™é€‰ç‰‡æ®µã€‚
2. å¯¹æ¯é¢˜å¡«ï¼š
   - `answer_correct`ï¼š`correct` / `partial` / `incorrect`ï¼ˆå€™é€‰ç­”æ¡ˆæ˜¯å¦æ­£ç¡®å›žç­”ï¼‰
   - `citation_supported`ï¼š`supported` / `partial` / `unsupported`ï¼ˆå€™é€‰ç‰‡æ®µæ˜¯å¦æ”¯æŒç­”æ¡ˆï¼‰
   - `citation_ids`ï¼šæ”¯æŒçš„ç‰‡æ®µç¼–å·ï¼ˆå¦‚ `s1,s3`ï¼›æ²¡æœ‰å°±ç©ºï¼‰
   - `abstain_expected`ï¼š`yes` / `no`ï¼ˆè¿™é“é¢˜æ˜¯å¦æœ¬åº”æ‹’ç­”ï¼‰
   - `time_s`ï¼šæœ¬é¢˜ç§’æ•°
   - `notes`ï¼šå¯é€‰
3. 20 é¢˜åŽï¼Œåš `A-B-TASKS.md` çš„ 3 ä¸ªå‘ˆçŽ°åå¥½é¢˜ï¼ˆçœ‹ä¸¤å¼ å›¾ï¼Œçº¦ 20â€“30 åˆ†é’Ÿï¼‰ã€‚
4. äº¤å›žï¼š`judge-sheet.csv`ï¼ˆæˆ– jsonlï¼‰+ `A-B-TASKS.md` é‡Œå¡«çš„ç­”æ¡ˆ + `TIME-LOG.csv`ã€‚

## è§„åˆ™

- åªåˆ¤æ–­â€œå€™é€‰ç­”æ¡ˆ + ç‰‡æ®µâ€ï¼Œä¸è¦è‡ªå·±é‡è¯»å…¨ç« ï¼›ç‰‡æ®µä¸å¤Ÿå°±æŒ‰ `partial/unsupported`ã€‚
- ä¸è¦çœ‹ `answer-key.json`ï¼›ä¸è¦å‚è€ƒ agent A/B æ ‡ç­¾ã€‚
- `control=true` çš„é¢˜æ˜¯â€œæ— éœ€è¯­ä¹‰è¾¹ä¹Ÿå¯ç­”â€çš„å¯¹ç…§ï¼›æ­£å¸¸åˆ¤å³å¯ã€‚
- è¿™æ˜¯ **draft**ï¼šç»“æžœåªç”¨äºŽæ ¡å‡† judge æµç¨‹ï¼Œä¸ä½œä¸º 0.5 è§£ç¦ä¾æ®ã€‚
""",
        encoding="utf-8",
    )

    (OUT / "A-B-TASKS.md").write_text(
        """# A/B å‘ˆçŽ°ä»»åŠ¡ï¼ˆè‰ç¨¿ï¼Œçº¦ 20â€“30 åˆ†é’Ÿï¼‰

> è¿™æ˜¯é™æ€æˆªå›¾å¯¹æ¯”ï¼Œä¸æ˜¯å®Œæ•´äº¤äº’æµ‹è¯•ï¼›åªä½œå‘ˆçŽ°åˆç­›ï¼Œä¸ä½œ 0.5 ä¾æ®ã€‚
> å›¾ï¼š`images/legacy-2d.png`ï¼ˆæ—§ KGviz é£Žæ ¼ï¼‰ vs `images/multilevel-2d.png`ï¼ˆæ–°å¤šå±‚æ¬¡ 2Dï¼‰ã€‚

## A1
çœ‹ä¸¤å¼ å›¾ï¼Œå›žç­”ï¼š**å“ªä¸€ä¸ªæ›´å®¹æ˜“çœ‹å‡ºâ€œfactors of productionâ€ä¸Ž sub-concepts çš„å±‚çº§å…³ç³»ï¼Ÿ**
- æ—§ / æ–° / å·®ä¸å¤šï¼›ç†ç”±ä¸€å¥ï¼š

## A2
**å“ªä¸€ä¸ªæ›´å®¹æ˜“æ‰¾åˆ°â€œnational debtâ€ä¸Žâ€œbudget deficitâ€çš„å…³ç³»ï¼Ÿ**
- æ—§ / æ–° / å·®ä¸å¤šï¼›ç†ç”±ä¸€å¥ï¼š

## A3
æ•´ä½“åå¥½ï¼š**æ—§ / æ–° / æ— æ‰€è°“**ï¼›æœ€å½±å“åˆ¤æ–­çš„ä¸€ä¸ªè§†è§‰å› ç´ ï¼š

## é™åˆ¶
é™æ€å›¾æ— æ³•æµ‹æ‹–æ‹½/æ‚¬åœ/ç¼©æ”¾/æ‰¾ç­”æ¡ˆæ—¶é—´ï¼›è¿™äº›ç•™åˆ°åŽç»­äº¤äº’ A/Bã€‚ä¸è¦æ®æ­¤å®£ç§° graph æœ‰æ•ˆã€‚
""",
        encoding="utf-8",
    )

    (OUT / "TIME-LOG.csv").write_text(
        "date,stage,items,minutes,notes\n"
        "2026-11-05,judge-pack-draft,20 questions,,\n"
        "2026-11-05,ab-presentation,3 tasks,,\n",
        encoding="utf-8",
    )

    # copy screenshots and NOTICE
    for name in ("legacy-2d.png", "multilevel-2d.png"):
        src = IMAGES / name
        if src.exists():
            (OUT / "images" / name).write_bytes(src.read_bytes())
    notice = ROOT / "artifacts/corpus/pilot/source/NOTICE.md"
    if notice.exists():
        (OUT / "NOTICE.md").write_text(notice.read_text(encoding="utf-8"), encoding="utf-8")

    total_pack_bytes = (OUT / "judge-pack.json").stat().st_size
    stale = OUT / "answer-key.json"
    if stale.exists():
        stale.unlink()
    if total_context > 40000:
        raise SystemExit(f"context too large: {total_context}")
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(OUT))
    print(json.dumps({
        "questions": len(blind_questions),
        "snippets": sum(len(q["snippets"]) for q in blind_questions),
        "context_chars": total_context,
        "pack_bytes": total_pack_bytes,
        "zip": str(ZIP),
        "zip_bytes": ZIP.stat().st_size,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



