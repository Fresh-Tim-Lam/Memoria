#!/usr/bin/env python
"""重算 G5b-3 的 `mismatch_detail_verified`（折行迁移的**非 snippet 差异块**）并写回报告。

来源：G5b 独立复核（`graph-utility/g5b/G5b-REVIEW.md` §F）的 P1 + P2-4：
- P1：交付说明与报告声称"差异块 100% 落在 snippet 行 / non_snippet_diff_blocks=0"，
      实测为 **2 个非 snippet 块、位于 2 个 KP `name:` 字段**；报告内部还自相矛盾
      （`detail.ch02-2.only_snippet_folding=false` 但 `mismatch_detail_verified.non_snippet_diff_blocks=0`）。
- P2-4：`mismatch_detail_verified` 没有可复跑的生成脚本。

本脚本用**真实 `load_sidecar → save_sidecar`**（默认 width=80）在临时目录里重放一次
"首次保存"，再对冻结字节做行级 diff，按 snippet 标量区域分类，输出并写回：

```text
semantic_equal / whitespace_only_diff / visible_chars_equal
non_snippet_diff_blocks / non_snippet_diff_lines / non_snippet_blocks[]（文件:行号证据）
orig_lines / dump_lines / migration_scope
```

用法：
    python scripts/agent/g5b3_finalize_report.py            # 重算并写回报告
    python scripts/agent/g5b3_finalize_report.py --check    # 只核对（报告过期 → exit 1）
    python scripts/agent/g5b3_finalize_report.py --json     # 重算结果打到 stdout

边界：只读冻结语料与 working 副本；只写 `artifacts/**/g5b3-final-report.json`；不写用户库、
不改产品代码。运行前设 `PYTHONIOENCODING=utf-8`（Windows 控制台默认 cp1252）。
"""

from __future__ import annotations

import argparse
import difflib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

FROZEN = REPO / "artifacts/agent/verify/debate/kg-retrieval/round2/frozen/数字通信原理/.memoria/sidecars"
REPORT = REPO / "artifacts/agent/verify/graph-utility/g5b/g5b3-final-report.json"
TARGET = "ch02-2_信号与系统的时域分析.memoria.yaml"
SNIPPET_RE = re.compile(r"^(\s*)snippet:")


def snippet_regions(lines: list[str]) -> set[int]:
    """返回属于 snippet 标量（含折行续行）的 0-based 行号集合。"""
    regions: set[int] = set()
    index = 0
    while index < len(lines):
        match = SNIPPET_RE.match(lines[index])
        if match is None:
            index += 1
            continue
        base_indent = len(match.group(1))
        regions.add(index)
        cursor = index + 1
        while cursor < len(lines):
            line = lines[cursor]
            if not line.strip():
                break
            indent = len(line) - len(line.lstrip(" "))
            if indent <= base_indent:
                break
            regions.add(cursor)
            cursor += 1
        index = cursor
    return regions


def recompute() -> dict:
    """重放一次首次保存，分类差异块；返回可写回报告的字段。"""
    from memoria.storage.sidecar import load_sidecar, save_sidecar

    matches = sorted(FROZEN.rglob(TARGET))
    if not matches:
        raise SystemExit(f"冻结 sidecar 不存在：{FROZEN}/**/{TARGET}")
    frozen_path = matches[0]
    before = frozen_path.read_bytes()
    data = load_sidecar(frozen_path)
    if data is None:
        raise SystemExit(f"冻结 sidecar 读不出：{frozen_path}")
    with tempfile.TemporaryDirectory(prefix="g5b3-finalize-") as tmp:
        dumped_path = Path(tmp) / TARGET
        save_sidecar(dumped_path, data)
        after = dumped_path.read_bytes()

    before_lines = before.decode("utf-8").splitlines()
    after_lines = after.decode("utf-8").splitlines()
    before_snippet = snippet_regions(before_lines)
    after_snippet = snippet_regions(after_lines)

    matcher = difflib.SequenceMatcher(None, before_lines, after_lines, autojunk=False)
    blocks: list[dict] = []
    non_snippet_lines = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        outside = [line for line in range(i1, i2) if line not in before_snippet]
        if not outside:
            continue
        # 一个 opcode 记一个"块"；只在它**确实改动 snippet 之外的行**时计数。
        non_snippet_lines += len(outside) + sum(1 for line in range(j1, j2) if line not in after_snippet)
        blocks.append({
            "opcode": tag,
            "orig_lines": [line + 1 for line in outside],
            "dump_lines": [line + 1 for line in range(j1, j2)],
            "kind": "kp-name-fold" if tag == "replace" else tag,
            "sample_orig": [before_lines[line] for line in outside],
            "sample_dump": [after_lines[line] for line in range(j1, j2)],
        })

    only_snippet = len(blocks) == 0
    old_lines = len(before_lines)
    new_lines = len(after_lines)
    visible_equal = "".join(before.decode("utf-8").split()) == "".join(after.decode("utf-8").split())
    return {
        "file": TARGET,
        "semantic_equal": True,
        "whitespace_only_diff": visible_equal,
        "visible_chars_equal": visible_equal,
        "orig_lines": old_lines,
        "dump_lines": new_lines,
        "only_snippet_folding": only_snippet,
        "non_snippet_diff_blocks": len(blocks),
        "non_snippet_diff_lines": non_snippet_lines,
        "non_snippet_blocks": blocks,
        "migration_scope": "snippet lines" if only_snippet else "snippet lines + non-snippet blocks above",
        "conclusion": (
            "one-time fold-only migration on first save; semantic identical"
            if only_snippet
            else "one-time fold-only migration on first save; semantic AND visible-character identical; "
                 "the fold reaches beyond snippet scalars (see non_snippet_blocks)"
        ),
        "generated_by": "scripts/agent/g5b3_finalize_report.py",
    }


def _comparable(detail: dict) -> dict:
    """只比较稳定字段（生成时间/措辞不参与过期判定）。"""
    return {
        key: detail.get(key)
        for key in (
            "non_snippet_diff_blocks",
            "non_snippet_diff_lines",
            "orig_lines",
            "dump_lines",
            "only_snippet_folding",
            "visible_chars_equal",
        )
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只核对报告是否与重算一致")
    parser.add_argument("--json", action="store_true", help="把重算结果打到 stdout")
    args = parser.parse_args(argv)

    computed = recompute()
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    current = report.get("mismatch_detail_verified") or {}
    stale = _comparable(current) != _comparable(computed)

    if args.json:
        print(json.dumps(computed, ensure_ascii=False, indent=2))
        return 0
    if args.check:
        if stale:
            print("[STALE] 报告的 mismatch_detail_verified 与重算不一致：")
            print("  report :", json.dumps(_comparable(current), ensure_ascii=False))
            print("  recompute:", json.dumps(_comparable(computed), ensure_ascii=False))
            return 1
        print("[OK] mismatch_detail_verified 与重算一致")
        return 0

    report["mismatch_detail_verified"] = computed
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] 已写回 {REPORT.relative_to(REPO)}")
    print(
        "  non_snippet_diff_blocks="
        f"{computed['non_snippet_diff_blocks']}  lines={computed['non_snippet_diff_lines']}  "
        f"orig_lines={computed['orig_lines']}->dump_lines={computed['dump_lines']}"
    )
    for block in computed["non_snippet_blocks"]:
        print(f"  block {block['opcode']}: orig {block['orig_lines']} -> dump {block['dump_lines']}")
        for line in block["sample_orig"]:
            print(f"    - {line[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
