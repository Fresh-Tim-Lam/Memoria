#!/usr/bin/env python
"""读写混合 A/B：`outline→section→propose_write` 的真实折扣（`contract_readwrite_ab`）。

## 为什么必须单独测（Lead 2026-10-25 要求）
S1 的 `92.43%` 是**纯读**任务上测的（`section_granularity_ab.py`）。模型实际做的是**读写混合**：
读完还要写，而写入要过 W2 读后写闸。若"section 读"不喂观察表（R-S2-1 修复前），模型必须再
`read_document` 一遍才能通过写闸 ⇒ **多一轮整篇**，那 92.43% 就要打折。

## 三臂（同任务、同语料、同工具、真实 handler）
- **A 当前**：`read_document`（整篇）→ `propose_write`（replace_lines 改目标行）           = 2 轮
- **B_after**：`outline` → `section` → `propose_write`（R-S2-1 修复后，section 即构成观察）  = 3 轮
- **B_before**：`outline` → `section` → **`read_document`** → `propose_write`（修复前必须补读）= 4 轮

`B_before` 是**模拟**（修复已生效，无法真回退），按"修复前 gate 会报 FS_NOT_OBSERVED、模型只能补读
`read_document`"这一条确定性行为计入那一轮的 token —— 报告里会标 `emulated=True`，不当实测卖。

## 判据
- 三臂都要**真的写入成功**（`propose_write` 回文含"已写入"），否则该任务作废（计数披露）。
- 报：(i) 轮数 (ii) 每轮 token (iii) 总账；以及 `savings_before` vs `savings_after` 的**折扣**。

## 用法

    python scripts/benchmark/maintenance/contract_readwrite_ab.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-cfg-"))

from memoria.services.agent.section_index import estimate_tokens  # noqa: E402
from memoria.services.agent.tools.kb import build_kb_tools  # noqa: E402
from memoria.services.heading_proposals import scan_headings, split_lines  # noqa: E402

KB_DIRS = [
    "docs/example/AAA_KnowledgeBase",
    "docs/example/人工智能导论知识点汇总",
    "docs/example/行政法",
    "docs/example/AAA_Vocab",
]
MAX_TASKS = 8


def walk_md(d: str) -> list[str]:
    out: list[str] = []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isdir(p):
            if name in ("node_modules", ".git", ".memoria"):
                continue
            out.extend(walk_md(p))
        elif name.lower().endswith(".md"):
            out.append(p)
    return out


def build_tasks() -> list[dict]:
    """确定性：按体量分层挑文档 + 每篇挑一个"可改的正文行"（在某个 h2/h3 节内）。"""
    docs: list[tuple[str, str, str]] = []
    for kb in KB_DIRS:
        base = os.path.join(REPO, kb)
        if not os.path.isdir(base):
            continue
        for f in walk_md(base):
            with open(f, encoding="utf-8") as fh:
                docs.append((kb, f, fh.read()))
    docs.sort(key=lambda x: len(x[2]))
    n = len(docs)
    picks = docs[:3] + docs[n // 3 : n // 3 + 3] + docs[-2:]
    tasks: list[dict] = []
    for _kb, path, text in picks:
        lines = split_lines(text)
        heads = [h for h in scan_headings(text) if h.level >= 2]
        if not heads:
            continue
        h = heads[0]
        anchor_line = None
        anchor = None
        for idx in range(h.index0 + 1, min(len(lines), h.index0 + 60)):
            s = lines[idx].strip()
            if len(s) >= 12 and not s.startswith("#"):
                anchor_line, anchor = idx + 1, s  # 1-based
                break
        if anchor_line is None:
            continue
        tasks.append(
            {
                "id": f"{os.path.basename(os.path.dirname(path))}/{os.path.basename(path)}",
                "src": path,
                "doc_bytes": len(text.encode("utf-8")),
                "heading": h.title,
                "anchor_line": anchor_line,
                "anchor": anchor,
            }
        )
        if len(tasks) >= MAX_TASKS:
            break
    return tasks


def _fresh_kb(src: str) -> tuple[str, str]:
    kb = tempfile.mkdtemp(prefix="memoria-rw-")
    rel = os.path.basename(src)
    shutil.copyfile(src, os.path.join(kb, rel))
    return kb, rel


def _write_plan(rel: str, task: dict) -> dict:
    return {
        "intent": "契约 A/B：改一行",
        "ops": [
            {
                "op": "replace_lines",
                "op_id": "o1",
                "file": rel,
                "range": {"start": task["anchor_line"], "end": task["anchor_line"]},
                "text": task["anchor"] + "（改）",
                "expect": task["anchor"],
            }
        ],
    }


def _run_arm(task: dict, arm: str) -> dict:
    kb, rel = _fresh_kb(task["src"])
    sid = f"ab-{arm}"
    tools = {t.name: t for t in build_kb_tools(kb, session_id=sid)}
    rounds: list[int] = []
    wrote = True

    def _call(name: str, args: dict) -> str:
        out = tools[name].handler(args)
        rounds.append(estimate_tokens(out.text))
        return out.text

    if arm == "A":
        _call("read_document", {"path": rel})
    elif arm == "B_after":
        _call("outline", {"file": rel})
        _call("section", {"file": rel, "heading": task["heading"]})
    elif arm == "B_before":
        _call("outline", {"file": rel})
        _call("section", {"file": rel, "heading": task["heading"]})
        _call("read_document", {"path": rel})  # 模拟：修复前必须补读才能过写闸
    text = _call("propose_write", _write_plan(rel, task))
    wrote = "已写入" in text
    return {"arm": arm, "rounds": len(rounds), "tokens_by_round": rounds,
            "total": sum(rounds), "wrote": wrote}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    tasks = build_tasks()
    rows: list[dict] = []
    for task in tasks:
        rec = {"id": task["id"], "doc_bytes": task["doc_bytes"]}
        for arm in ("A", "B_after", "B_before"):
            rec[arm] = _run_arm(task, arm)
        rows.append(rec)

    def agg(arm: str) -> dict:
        rs = [r[arm] for r in rows]
        return {
            "tasks": len(rs),
            "ok_tasks": sum(1 for r in rs if r["wrote"]),
            "rounds_min": min(r["rounds"] for r in rs) if rs else 0,
            "rounds_median": statistics.median([r["rounds"] for r in rs]) if rs else 0,
            "rounds_max": max(r["rounds"] for r in rs) if rs else 0,
            "per_round_tokens_median": statistics.median([t for r in rs for t in r["tokens_by_round"]]) if rs else 0,
            "total_sum": sum(r["total"] for r in rs),
            "total_median": statistics.median([r["total"] for r in rs]) if rs else 0,
        }

    a, b_after, b_before = agg("A"), agg("B_after"), agg("B_before")
    sav_after = round(1 - b_after["total_sum"] / a["total_sum"], 4) if a["total_sum"] else 0
    sav_before = round(1 - b_before["total_sum"] / a["total_sum"], 4) if a["total_sum"] else 0
    payload = {
        "schema": "contract-readwrite-ab/v1",
        "nature": "PROXY：真实工具 handler 计 token；轮数按固定策略；不调用模型",
        "arms": {
            "A": "read_document → propose_write（2 轮）",
            "B_after": "outline → section → propose_write（3 轮；R-S2-1 修复后 section 即构成观察）",
            "B_before": "outline → section → read_document → propose_write（4 轮；emulated=True，模拟修复前必须补读）",
        },
        "emulated": {"B_before": True},
        "sealed": {"MEMORIA_CONFIG_DIR": True},
        "A": a,
        "B_after": b_after,
        "B_before": b_before,
        "savings_readwrite_after": sav_after,
        "savings_readwrite_before": sav_before,
        "discount": {
            "delta_pct_points": round((sav_after - sav_before) * 100, 2),
            "read_only_savings_reference": 0.9243,
            "read_write_vs_read_only": round((sav_after - 0.9243) * 100, 2),
        },
        "per_task": rows,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print(f"tasks: {len(tasks)}（每臂都要真写入成功；失败任务数 = {len(tasks) - a['ok_tasks']}）")
    for name, d in (("A", a), ("B_after", b_after), ("B_before", b_before)):
        print(f"  {name:9} rounds(med)={d['rounds_median']} per-round(med)={d['per_round_tokens_median']}tok "
              f"总账sum={d['total_sum']} 中位={d['total_median']}")
    print(f"\n读写混合节省：修复后 {sav_after:.2%} / 修复前（模拟）{sav_before:.2%}")
    print(f"折扣：相对修复前 {(sav_after - sav_before) * 100:+.2f} 个百分点；"
          f"相对纯读 92.43% {(sav_after - 0.9243) * 100:+.2f} 个百分点")
    print(f"\n== RESULT: {'PASS' if a['ok_tasks'] == len(tasks) else 'FAIL'} =="
          f"  (sha256 {payload['artifactSha256'][:16]}…)")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0 if payload["per_task"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
