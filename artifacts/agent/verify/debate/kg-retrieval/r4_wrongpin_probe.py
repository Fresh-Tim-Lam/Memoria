"""R4 深挖：歧义 snippet 在漂移后，locate_snippet 实际钉到【哪一行】—— 是否钉错（task-191）。

前一个脚本只统计"歧义有几条"，本脚本回答更要命的问题：
  **hint 漂移后，locator 会不会钉到【错误的同名行】，而且【静默返回 ok=True】？**

这正是"共享锚点"架构最危险失效模式：锚点错了但不报错 ⇒ 用户看到的 ≠ agent 读到的，
而且没人知道。（与 KG 辩论里"看起来有实际没有"是同一类问题）

用法：python .../r4_anchor_wrongpin_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "src"))

from memoria.range.locator import resolve_range  # noqa: E402

KB = Path("D:/AAA_Courses/数字通信原理")


def _load(path: Path) -> dict:
    import yaml

    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _body(kb: Path, sidecar: Path) -> Path | None:
    rel = sidecar.relative_to(kb / ".memoria" / "sidecars")
    name = rel.name[: -len(".memoria.yaml")] if rel.name.endswith(".memoria.yaml") else rel.name
    md = kb / rel.parent / (name + ".md")
    return md if md.is_file() else None


def main() -> int:
    if not KB.is_dir():
        print(f"[SKIP] 真库不可访问：{KB}")
        return 0

    total = 0
    ambiguous = 0
    wrong_pin = 0          # 漂移后钉到了"不是原来那一行"的位置，但 ok=True
    silent_wrong: list[dict] = []

    for sidecar in (KB / ".memoria" / "sidecars").rglob("*.yaml"):
        data = _load(sidecar)
        kps = data.get("knowledge_points") or []
        md = _body(KB, sidecar)
        if md is None or not isinstance(kps, list):
            continue
        original = md.read_text(encoding="utf-8", errors="replace").splitlines()

        for kp in kps:
            if not isinstance(kp, dict):
                continue
            rng = kp.get("range") or {}
            start = rng.get("start") or {}
            end = rng.get("end") or {}
            snip = str(start.get("snippet") or "").strip()[:80]
            hint = start.get("line_hint")
            if not snip or not isinstance(hint, int):
                continue
            total += 1

            norm = [ln.strip() for ln in original]
            occ = [i for i, ln in enumerate(norm) if snip in ln]
            if len(occ) <= 1:
                continue
            ambiguous += 1

            # 真实位置（0-based）：hint 指向的那一行（如果它确实含 snippet）
            truth = hint - 1 if 0 <= hint - 1 < len(norm) and snip in norm[hint - 1] else None
            if truth is None:
                continue

            # 漂移：前插 50 行 ⇒ hint 现在指向"第 50 行之前"的位置（错的）
            shifted = ["# 新插入"] + [""] * 49 + original
            rr = resolve_range(shifted, start, end)
            if not rr.get("ok"):
                continue
            got = rr["start_line"] - 1
            expected = truth + 50  # 漂移后的真实位置

            if got != expected:
                wrong_pin += 1
                if len(silent_wrong) < 8:
                    silent_wrong.append(
                        {
                            "file": md.name,
                            "kp": kp.get("id"),
                            "snippet": snip[:50],
                            "occurrences_in_doc": len(occ),
                            "expected_after_drift": expected + 1,
                            "actually_pinned": got + 1,
                            "offset_error": got - expected,
                            "line_at_pinned": (shifted[got] if 0 <= got < len(shifted) else "")[:50],
                        }
                    )

    print("=== R4 深挖：歧义 snippet 漂移后是否【静默钉错】===")
    print(f"  可测 KP 总数: {total}")
    print(f"  snippet 歧义 KP: {ambiguous} ({100*ambiguous/max(total,1):.1f}%)")
    print(f"  ★ 漂移后【钉到错误行且 ok=True】（静默错）: {wrong_pin}")
    if ambiguous:
        print(f"  ⇒ 歧义 KP 中静默钉错比例: {100*wrong_pin/ambiguous:.1f}%")
    print()
    for w in silent_wrong:
        print(f"  {w['file']} / {w['kp']}")
        print(f"    snippet={w['snippet']!r} 文档内出现 {w['occurrences_in_doc']} 次")
        print(f"    漂移后应指向 L{w['expected_after_drift']}，实际钉到 L{w['actually_pinned']}"
              f"（偏移 {w['offset_error']:+d} 行）")
        print(f"    钉到的行内容: {w['line_at_pinned']!r}")

    out = REPO / "artifacts/agent/verify/debate/kg-retrieval/r4-wrongpin-probe.json"
    out.write_text(
        json.dumps(
            {
                "kb": str(KB),
                "total": total,
                "ambiguous": ambiguous,
                "silent_wrong_pin": wrong_pin,
                "examples": silent_wrong,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
