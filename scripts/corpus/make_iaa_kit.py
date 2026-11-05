#!/usr/bin/env python
"""生成 IAA（第二标注者）工具包：空白模板、候选边对池、裁决/培训日志模板、清单。

为什么要“候选对池”而不是把 A 的 30 条边直接给第二标注者：
- 直接给正例会泄漏 A 的判定，tuple F1 变成抄写；
- 池子 = A 正例边对 + A 负例对 + 同 section 随机干扰对，**不带任何标签**，第二标注者独立判
  “有边/无边 + 类型/方向”；池子构造确实用到了 A 的候选集，因此 recall 只在池内可估——
  该限制写进 `iaa/README.md` 与报告中，不冒充全量 recall。

确定性：随机种子固定为 368；输出按 pair_id 排序；重复运行逐字节一致。

用法：
  python scripts/corpus/make_iaa_kit.py build
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

SEED = 368
POOL_SIZE = 60
DISTRACTOR_COUNT = POOL_SIZE - 30 - 14

TEMPLATE_KP = {"_template": True,
               "instructions": "删除本行；按 iaa/README.md 的格式独立标注 KP span（不要看 A 的 kps.single.jsonl）。"}
TEMPLATE_EDGE = {"_template": True,
                 "instructions": "删除本行；对 edge-candidate-pool.jsonl 每一对独立标注 edge 或 no_edge（不要看 A 的 edges.single.jsonl）。"}
TEMPLATE_ADJ = {"_template": True,
                "fields": ["item_id", "level", "question", "options", "decision", "rationale",
                           "reviewer", "date", "affected_items"]}
TEMPLATE_TRAIN = {"_template": True,
                  "fields": ["annotator", "stage", "items", "agreement", "passed", "date", "notes"]}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build(anno_dir: Path, out_dir: Path) -> dict:
    kps = load_jsonl(anno_dir / "kps.single.jsonl")
    edges = load_jsonl(anno_dir / "edges.single.jsonl")
    negatives = load_jsonl(anno_dir / "edges.negative.single.jsonl")
    kp_ids = {k["id"] for k in kps}
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 候选对：A 正例 + A 负例 + 同 section 干扰对 ----
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for e in edges:
        key = (e["source"], e["target"])
        if key not in seen:
            seen.add(key)
            pairs.append(key)
    for n in negatives:
        key = (n["candidate_source"], n["candidate_target"])
        if key not in seen:
            seen.add(key)
            pairs.append(key)

    by_section: dict[str, list[str]] = {}
    for k in kps:
        by_section.setdefault(k["section_key"], []).append(k["id"])
    rng = random.Random(SEED)
    candidates: list[tuple[str, str]] = []
    for ids in by_section.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                key = (ids[i], ids[j])
                if key in seen:
                    continue
                reverse = (ids[j], ids[i])
                if reverse in seen:
                    continue
                candidates.append(key)
    candidates.sort()
    rng.shuffle(candidates)
    for key in candidates:
        if len(pairs) >= POOL_SIZE:
            break
        seen.add(key)
        pairs.append(key)

    if len(pairs) != POOL_SIZE:
        raise ValueError(f"候选对不足：{len(pairs)} != {POOL_SIZE}")
    rng.shuffle(pairs)
    pool = [{
        "pair_id": f"pair-{i:03d}",
        "source": s,
        "target": t,
        "task": "label independently: no_edge | edge (type=contain/reference/extend, direction, confidence, rationale)",
        "label": "",
        "type": "",
        "direction": "",
        "confidence": "",
        "rationale": "",
    } for i, (s, t) in enumerate(pairs, 1)]
    pool.sort(key=lambda x: x["pair_id"])

    # ---- 写模板 ----
    def write_jsonl(path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                        encoding="utf-8", newline="\n")

    write_jsonl(out_dir / "kps-second-annotator.template.jsonl", [TEMPLATE_KP])
    write_jsonl(out_dir / "edges-second-annotator.template.jsonl", [TEMPLATE_EDGE])
    write_jsonl(out_dir / "adjudication-log.template.jsonl", [TEMPLATE_ADJ])
    write_jsonl(out_dir / "training-log.template.jsonl", [TEMPLATE_TRAIN])
    write_jsonl(out_dir / "edge-candidate-pool.jsonl", pool)

    # ---- 清单 ----
    manifest = {
        "schema": "corpus-pilot-iaa-kit/v1",
        "seed": SEED,
        "pool_size": len(pool),
        "pool_composition": {"a_positive_pairs": len(edges),
                             "a_negative_pairs": len(negatives),
                             "distractor_pairs": POOL_SIZE - len(edges) - len(negatives)},
        "files": {
            "kp_template": str(out_dir / "kps-second-annotator.template.jsonl").replace("\\", "/"),
            "edge_template": str(out_dir / "edges-second-annotator.template.jsonl").replace("\\", "/"),
            "edge_candidate_pool": str(out_dir / "edge-candidate-pool.jsonl").replace("\\", "/"),
            "adjudication_template": str(out_dir / "adjudication-log.template.jsonl").replace("\\", "/"),
            "training_template": str(out_dir / "training-log.template.jsonl").replace("\\", "/"),
        },
        "file_sha256": {
            "edge-candidate-pool.jsonl": sha256_file(out_dir / "edge-candidate-pool.jsonl"),
            "kps-second-annotator.template.jsonl": sha256_file(out_dir / "kps-second-annotator.template.jsonl"),
            "edges-second-annotator.template.jsonl": sha256_file(out_dir / "edges-second-annotator.template.jsonl"),
        },
        "limitations": [
            "候选对池由 A 的正例/负例/同 section 干扰对构成；第二标注者的边 recall 只在池内可估，不是全量 recall。",
            "第二标注者也可追加池外边（edges-second-annotator.jsonl 中 pair_id 写 'extra-*'），报告会单列。",
            "KP span 必须独立标注（不得看 A 的 kps.single.jsonl），否则 unitizing α 无意义。",
        ],
    }
    (out_dir / "iaa-kit-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build IAA kit for corpus pilot")
    ap.add_argument("command", choices=["build"])
    ap.add_argument("--anno", default="artifacts/corpus/pilot/annotations")
    ap.add_argument("--out", default="artifacts/corpus/pilot/iaa")
    args = ap.parse_args(argv)
    try:
        man = build(Path(args.anno), Path(args.out))
        print(json.dumps({"ok": True, "pool_size": man["pool_size"],
                          "pool_composition": man["pool_composition"],
                          "manifest": "artifacts/corpus/pilot/iaa/iaa-kit-manifest.json"},
                         ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
