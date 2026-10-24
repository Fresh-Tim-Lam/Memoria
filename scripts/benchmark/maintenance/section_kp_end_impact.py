#!/usr/bin/env python
r"""R-S1C-2 前置实测：fence-aware 的 KP end 重建会改动多少**既有 sidecar**。

## 背景

S1c 把 `document._resync_kp_ranges_after_edit()` 的"下一条 heading"从**朴素行首正则**
改为**围栏/frontmatter 感知**（C1）。该分支只在**编辑后保存**时触发，且只对
`resolve_range(...).error == "end_snippet_not_found"` 且有 `start_line` 的 KP 生效。

它对**既有用户数据**的影响面 = 「当前就会走该修复分支、且新旧口径给出的下一条 heading 不同」的 KP 数。

- **0 个** ⇒ 改动是纯潜在行为（只影响未来损坏修复），不触碰既有 sidecar。
- **>0 个** ⇒ 必须选：只读容忍（写侧保持原行为）或 带备份迁移。

## 判据（逐 KP，可复现）

1. 逐 md 加载 sidecar（`load_sidecar_for_md`）；
2. `body` 用 `strip_frontmatter` 后 `splitlines()`（与 `document.py` 同口径）；
3. 对每个 KP 跑 `resolve_range(lines, start, end)`：
   - `ok == True` ⇒ 不触发修复，**不受影响**；
   - 否则若 `error == "end_snippet_not_found"` 且 `start_line` ⇒ 触发修复分支：
     - `naive_next` = start_line 之后**第一条行首标题**（旧口径 `^(#{1,6})\s+`，不看围栏）
     - `aware_next` = start_line 之后**第一条围栏感知 heading**（新口径 `scan_headings`）
     - 二者不同 ⇒ **该 KP 的 end 会变**（affected）；
   - 其它 error ⇒ 不触发（不受影响）。

## 用法

    python scripts/benchmark/maintenance/section_kp_end_impact.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

from memoria.range import locator  # noqa: E402
from memoria.services.heading_proposals import scan_headings  # noqa: E402
from memoria.storage.markdown import strip_frontmatter  # noqa: E402
from memoria.storage.sidecar import load_sidecar_for_md  # noqa: E402

#: 旧口径（fence-aware 之前 `document.py:420` 的逐字正则）——只用于对照，不供产品代码使用。
OLD_HEADING_RE = re.compile(r"^(#{1,6})\s+")

DEFAULT_KBS = ["docs/example"]


def default_kbs() -> list[str]:
    """`docs/example/*` 里**真正带 `.memoria/sidecars`** 的子目录即各自一个 KB 根。

    注意：KB 根是子目录（如 `docs/example/AAA_Vocab`），不是 `docs/example` 本身——
    `sidecar_path_for(md, kb_root)` 按 `<kb_root>/.memoria/sidecars/<rel>.memoria.yaml` 映射。
    """
    base = os.path.join(REPO, "docs", "example")
    out: list[str] = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name)
        if os.path.isdir(p) and os.path.isdir(os.path.join(p, ".memoria", "sidecars")):
            out.append(os.path.relpath(p, REPO).replace("\\", "/"))
    return out


def walk_md(d: str) -> list[str]:
    out: list[str] = []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isdir(p):
            if name in ("node_modules", ".git"):
                continue
            out.extend(walk_md(p))
        elif name.lower().endswith(".md"):
            out.append(p)
    return out


def naive_next_heading(lines: list[str], after_idx0: int) -> int | None:
    for i in range(after_idx0 + 1, len(lines)):
        if OLD_HEADING_RE.match(lines[i]):
            return i
    return None


def aware_next_heading(lines: list[str], after_idx0: int) -> int | None:
    body = "\n".join(lines)
    for h in scan_headings(body):
        if h.index0 > after_idx0:
            return h.index0
    return None


def analyze_kb(kb_root: str) -> dict:
    rows: list[dict] = []
    stats = {
        "docs": 0,
        "docsWithSidecar": 0,
        "kps": 0,
        "kpResolved": 0,
        "kpRepairBranch": 0,
        "kpAffected": 0,
    }
    for md in walk_md(kb_root):
        stats["docs"] += 1
        sc = load_sidecar_for_md(md, kb_root)
        if not sc:
            continue
        stats["docsWithSidecar"] += 1
        try:
            with open(md, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            continue
        body, _ = strip_frontmatter(raw)
        lines = body.splitlines()
        kps = sc.get("knowledge_points")
        if not isinstance(kps, list):
            continue
        for kp in kps:
            if not isinstance(kp, dict) or not isinstance(kp.get("range"), dict):
                continue
            stats["kps"] += 1
            rng = kp["range"]
            start = dict(rng.get("start") or {})
            end = dict(rng.get("end") or {})
            rr = locator.resolve_range(lines, start, end)
            if rr.get("ok"):
                stats["kpResolved"] += 1
                continue
            if rr.get("error") != "end_snippet_not_found" or not rr.get("start_line"):
                continue
            stats["kpRepairBranch"] += 1
            si = rr["start_line"] - 1
            nn = naive_next_heading(lines, si)
            an = aware_next_heading(lines, si)
            if nn != an:
                stats["kpAffected"] += 1
                rows.append(
                    {
                        "kb": os.path.relpath(kb_root, REPO).replace("\\", "/"),
                        "doc": os.path.relpath(md, kb_root).replace("\\", "/"),
                        "kp_id": kp.get("id"),
                        "start_line": rr["start_line"],
                        "naive_next_heading_line": (nn + 1) if nn is not None else None,
                        "aware_next_heading_line": (an + 1) if an is not None else None,
                        "old_end_line_hint": end.get("line_hint"),
                        "would_change": True,
                    }
                )
    return {"kb": os.path.relpath(kb_root, REPO).replace("\\", "/"), "stats": stats, "affected": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", action="append", default=[])
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    kbs = args.kb or default_kbs()
    per_kb = []
    total = {
        "docs": 0,
        "docsWithSidecar": 0,
        "kps": 0,
        "kpResolved": 0,
        "kpRepairBranch": 0,
        "kpAffected": 0,
    }
    for kb in kbs:
        root = kb if os.path.isabs(kb) else os.path.join(REPO, kb)
        if not os.path.isdir(root):
            print(f"[skip] 不存在: {kb}")
            continue
        r = analyze_kb(root)
        per_kb.append(r)
        for k in total:
            total[k] += r["stats"][k]

    payload = {
        "schema": "section-kp-end-impact/v1",
        "question": "fence-aware 的 KP end 重建会改动多少既有 sidecar？",
        "method": "resolve_range 触发 end_snippet_not_found 修复分支的 KP，比较旧(朴素)/新(围栏感知)下一条 heading 行号",
        "scope_note": "只覆盖仓库随附 docs/example/**（用户私有 KB 不在仓库内，未覆盖）",
        "kbs": per_kb,
        "totals": total,
        "verdict": (
            "NO_IMPACT" if total["kpAffected"] == 0 else "IMPACT_REQUIRES_MIGRATION_DECISION"
        ),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print("== per KB ==")
    for r in per_kb:
        s = r["stats"]
        print(
            f"  {r['kb']}: docs={s['docs']} withSidecar={s['docsWithSidecar']} kps={s['kps']} "
            f"resolved={s['kpResolved']} repairBranch={s['kpRepairBranch']} affected={s['kpAffected']}"
        )
    print("\n== totals ==")
    for k, v in total.items():
        print(f"  {k} = {v}")
    print(f"\n== VERDICT: {payload['verdict']} ==")
    if payload["kbs"]:
        for r in payload["kbs"]:
            for row in r["affected"]:
                print(f"  AFFECTED {row['doc']} kp={row['kp_id']} start={row['start_line']} "
                      f"naive_next={row['naive_next_heading_line']} aware_next={row['aware_next_heading_line']}")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"\nwrote: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
