#!/usr/bin/env python
"""生成**人类**双标注 IAA 报告（annotator-a vs annotator-b），强制 `annotator_type=human`。

- 只接受人类标注者文件（行内 `annotator` 必须是 `annotator-a` / `annotator-b`）；
  一旦发现机器草案标记（如 `corpus-pilot-builder` / `agent` / `machine`）→ exit 1（拒绝混入）；
- 缺任一人类文件或文件为空 → **exit 2**，不生成报告、不伪造指标；
- 指标计算复用 `scripts/corpus/iaa_runner.py`（unitizing α 复用 C0a 的 `unitizing_alpha.py`），
  本脚本只做“人类输入 + provenance + 落盘”，**不生成任何标签**。

用法（canonical 人类路径）：
  python scripts/corpus/make_iaa_report.py \
    --out artifacts/agent/verify/corpus/pilot/human-iaa-report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import iaa_runner  # noqa: E402

MACHINE_MARKERS = ("corpus-pilot-builder", "agent", "machine", "llm")
HUMAN_ROLE = {"a": "annotator-a", "b": "annotator-b"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def assert_human(rows: list[dict], expected: str, file_label: str) -> list[str]:
    errors = []
    for i, row in enumerate(rows, 1):
        annotator = str(row.get("annotator", ""))
        method = str(row.get("annotation_method", ""))
        blob = f"{annotator} {method}".lower()
        if annotator != expected:
            errors.append(f"{file_label} 第 {i} 行 annotator={annotator!r}，应为 {expected!r}")
        if any(marker in blob for marker in MACHINE_MARKERS):
            errors.append(f"{file_label} 第 {i} 行含机器/agent 标记（{annotator!r}/{method!r}），拒绝")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate HUMAN IAA report (annotator-a vs annotator-b)")
    ap.add_argument("--kps-a",
                    default="artifacts/corpus/pilot/human-kit/annotator-a/kps.annotator-a.jsonl")
    ap.add_argument("--kps-b",
                    default="artifacts/corpus/pilot/human-kit/annotator-b/kps.annotator-b.jsonl")
    ap.add_argument("--pool-a",
                    default="artifacts/corpus/pilot/human-kit/annotator-a/pool-judgments.annotator-a.jsonl")
    ap.add_argument("--pool-b",
                    default="artifacts/corpus/pilot/human-kit/annotator-b/pool-judgments.annotator-b.jsonl")
    ap.add_argument("--pool", default="artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl")
    ap.add_argument("--sections", default="artifacts/corpus/pilot/source/sections.json")
    ap.add_argument("--adjudications", default="")
    ap.add_argument("--manual-version", default="v1.1")
    ap.add_argument("--out", default="artifacts/agent/verify/corpus/pilot/human-iaa-report.json")
    args = ap.parse_args(argv)

    paths = {"kps_a": Path(args.kps_a), "kps_b": Path(args.kps_b),
             "pool_a": Path(args.pool_a), "pool_b": Path(args.pool_b),
             "pool": Path(args.pool), "sections": Path(args.sections)}
    missing = [key for key, p in paths.items() if not p.exists()]
    if missing:
        print(json.dumps({"ok": False, "status": "missing_input",
                          "annotator_type": "human", "missing": missing,
                          "note": "人类标注文件缺失：不生成报告（exit 2）"},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    try:
        kps_a = read_jsonl(paths["kps_a"])
        kps_b = read_jsonl(paths["kps_b"])
        pool_a = read_jsonl(paths["pool_a"])
        pool_b = read_jsonl(paths["pool_b"])
        pool = read_jsonl(paths["pool"])
        sections = json.loads(paths["sections"].read_text(encoding="utf-8"))["sections"]
        adjudications = (read_jsonl(Path(args.adjudications))
                         if args.adjudications and Path(args.adjudications).exists() else [])
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "status": "invalid", "error": type(exc).__name__,
                          "message": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    if not kps_a or not kps_b or not pool_a or not pool_b:
        empty = [name for name, rows in (("kps_a", kps_a), ("kps_b", kps_b),
                                         ("pool_a", pool_a), ("pool_b", pool_b)) if not rows]
        print(json.dumps({"ok": False, "status": "empty_input",
                          "annotator_type": "human", "empty": empty,
                          "note": "人类标注文件为空：不生成报告（exit 2）"},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    errors = (assert_human(kps_a, HUMAN_ROLE["a"], "kps_a")
              + assert_human(pool_a, HUMAN_ROLE["a"], "pool_a")
              + assert_human(kps_b, HUMAN_ROLE["b"], "kps_b")
              + assert_human(pool_b, HUMAN_ROLE["b"], "pool_b"))
    if errors:
        print(json.dumps({"ok": False, "status": "non_human_input",
                          "annotator_type": "human", "errors": errors[:20],
                          "note": "拒绝机器/agent 标签混入人类 IAA（exit 1）"},
                         ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    report = iaa_runner.build_report(kps_a, kps_b, pool_a, pool_b, pool,
                                     adjudications or None, sections)
    report["annotator_type"] = "human"
    report["human_iaa"] = True
    report["manual_version"] = args.manual_version
    report["provenance"] = {
        "inputs": {name: {"path": str(paths[name]), "sha256": sha256_file(paths[name])}
                   for name in ("kps_a", "kps_b", "pool_a", "pool_b", "pool")},
        "adjudications": ({"path": args.adjudications,
                           "sha256": sha256_file(Path(args.adjudications))}
                          if args.adjudications and Path(args.adjudications).exists() else None),
        "annotator_type": "human",
        "note": ("本报告由两位**人类**标注者文件生成；不读取/不引用 pilot 机器草案标签；"
                 "不生成任何标签。若 `annotator_type` 不是 human 则不得用于 C8。"),
    }
    report["warning"] = "human IAA report; verify annotator credentials before citing as C8 evidence."
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "out": str(out), "annotator_type": "human",
                      "status": report["status"], "sample_sizes": report["sample_sizes"],
                      "pass": report["pass"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
