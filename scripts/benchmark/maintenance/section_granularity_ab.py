#!/usr/bin/env python
"""S1a 双指标 (b)：粒度化 vs 整篇读的**代理 A/B**（含往返轮数与总账，密封环境）。

## 这是代理指标，不是完成率（R-S1A-1 已裁决：不烧模型额度）

- **命中判据**：任务需要的"答案锚点行"是否出现在某一次工具返回里（检索充分性）。
  它**不**证明模型一定能完成任务；它只证明"完成任务所需的材料，落在返回窗口内"。
- **轮数**：按**固定策略**模拟一个有能力的 agent（先看结构、再取所需），不是真实模型行为。
  目的正是抓 U3：粒度切细 ⇒ 轮数上升 ⇒ **总账**可能反升。所以必须同报 (i)(ii)(iii)。

## 两臂（都用**真实工具 handler** 跑，不是我自己编的 payload）

- **A 当前**：`read_document(file, offset, limit=2000)` 分页整篇读 —— 直到锚点出现（最多 8 轮）。
- **B 粒度**：`outline(file)` → `section(file, heading|near_line)` → 必要时按 `next_cursor` 续片（最多 8 轮）。

两臂的工具都在同一个 `build_kb_tools()` 里（同一 schema 环境）⇒ 差异只来自**返回粒度与轮数**。
新增的 3 把工具 schema 成本单独测（一次性/会话），并算"摊平到多少个任务才回本"。

## 用法

    python scripts/benchmark/maintenance/section_granularity_ab.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

# ── 密封性（R-S1A-3）：`DocumentService.__post_init__` 会调 `remember_last_kb_path()`
# 写**全局** UI 设置（`config/ui-settings.json`）；app 运行时该文件被占用 ⇒ PermissionError。
# 把 config 目录重定向到临时目录，测量才能密封可复跑，且**不改全局配置**。
_SEALED_CONFIG_DIR = tempfile.mkdtemp(prefix="memoria-cfg-")
os.environ.setdefault("MEMORIA_CONFIG_DIR", _SEALED_CONFIG_DIR)

from memoria.services.agent.section_index import (  # noqa: E402
    SECTION_MAX_TOKENS,
    estimate_tokens,
)
from memoria.services.agent.tools.kb import build_kb_tools  # noqa: E402
from memoria.services.heading_proposals import scan_headings, split_lines  # noqa: E402

KB_DIRS = [
    "docs/example/AAA_KnowledgeBase",
    "docs/example/人工智能导论知识点汇总",
    "docs/example/行政法",
    "docs/example/AAA_Vocab",
]
MAX_ROUNDS = 8
TASKS_PER_DOC = 2


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
    """确定性任务集：每个文档挑 `TASKS_PER_DOC` 个 (目标标题, 答案锚点行)。"""
    docs: list[tuple[str, str, str]] = []  # (kb_root_rel, rel_under_kb, text)
    for kb in KB_DIRS:
        base = os.path.join(REPO, kb)
        if not os.path.isdir(base):
            continue
        for f in walk_md(base):
            with open(f, encoding="utf-8") as fh:
                docs.append((kb, os.path.relpath(f, base).replace("\\", "/"), fh.read()))
    # 按体量分层抽样：小/中/大各取若干（避免只测一种规模）
    docs.sort(key=lambda x: len(x[2]))
    n = len(docs)
    picks = (
        docs[:4] + docs[n // 3 : n // 3 + 4] + docs[2 * n // 3 : 2 * n // 3 + 4] + docs[-3:]
    )
    tasks: list[dict] = []
    for kb, rel, text in picks:
        lines = split_lines(text)
        heads = scan_headings(text)
        if len(heads) < 2:
            continue
        # 目标节：跳过第一个（通常是整篇标题），往后取有正文字数的
        cand = [h for h in heads[1:] if h.level >= 2]
        for i, h in enumerate(cand[: TASKS_PER_DOC * 2][:TASKS_PER_DOC]):
            # 锚点 = 该节里第一条够长的正文行（不是标题）
            anchor = None
            for ln in lines[h.index0 + 1 :]:
                s = ln.strip()
                if not s or s.startswith("#"):
                    continue
                if len(s) >= 12:
                    anchor = s
                    break
            if not anchor:
                continue
            tasks.append(
                {
                    "id": f"{os.path.basename(kb)}::{rel}::{i}",
                    "kb_root": kb,
                    "file": rel,
                    "doc_bytes": len(text.encode("utf-8")),
                    "heading": h.title,
                    "heading_line": h.line_no,
                    "anchor": anchor,
                    # 两种典型意图交替：读一节 / 找一句话（前者容易 U3，后者是粒度的强项）
                    "kind": "read_section" if i % 2 == 0 else "find_sentence",
                }
            )
    return tasks


def run_arm_a(tools: dict, task: dict) -> dict:
    """A 当前：按意图走**既有工具**的老路子。

    - `find_sentence`：`search_kb(query)` → 命中就停；不中再 `read_document` 整篇（最多 8 轮）
    - `read_section`：直接 `read_document` 分页整篇读（最多 8 轮）
    """
    rounds: list[int] = []
    hit = False
    if task["kind"] == "find_sentence":
        out = tools["search_kb"].handler({"query": task["anchor"][:24]})
        rounds.append(estimate_tokens(out.text))
        if task["anchor"] in out.text:
            return {"arm": "A_read_document", "rounds": len(rounds), "tokens_by_round": rounds,
                    "total": sum(rounds), "hit": True}
    offset = 1
    for _ in range(MAX_ROUNDS):
        out = tools["read_document"].handler({"path": task["file"], "offset": offset, "limit": 2000})
        rounds.append(estimate_tokens(out.text))
        if task["anchor"] in out.text:
            hit = True
            break
        offset += 2000
    return {"arm": "A_read_document", "rounds": len(rounds), "tokens_by_round": rounds,
            "total": sum(rounds), "hit": hit}


def run_arm_b(tools: dict, task: dict) -> dict:
    """B 粒度：按意图走三级粒度。

    - `find_sentence`：`snippet(query)` 一轮（不中再 outline→section 兜底）
    - `read_section`：`outline` → `section(near_line)` → 必要时按 next_cursor 续片
    """
    rounds: list[int] = []
    hit = False
    sec_args: dict = {"file": task["file"], "near_line": task["heading_line"]}

    if task["kind"] == "find_sentence":
        out = tools["snippet"].handler({"file": task["file"], "query": task["anchor"][:24]})
        rounds.append(estimate_tokens(out.text))
        if task["anchor"] in out.text:
            return {"arm": "B_granular", "rounds": len(rounds), "tokens_by_round": rounds,
                    "total": sum(rounds), "hit": True}

    out = tools["outline"].handler({"file": task["file"]})
    rounds.append(estimate_tokens(out.text))
    out = tools["section"].handler(sec_args)
    rounds.append(estimate_tokens(out.text))
    if task["anchor"] in out.text:
        hit = True
    else:
        part = 2
        while len(rounds) < MAX_ROUNDS:
            out = tools["section"].handler({**sec_args, "part": part})
            rounds.append(estimate_tokens(out.text))
            if task["anchor"] in out.text:
                hit = True
                break
            if "本片未完" not in out.text:
                break
            part += 1
    return {"arm": "B_granular", "rounds": len(rounds), "tokens_by_round": rounds,
            "total": sum(rounds), "hit": hit}


def arm_summary(rows: list[dict]) -> dict:
    rounds = [r["rounds"] for r in rows]
    totals = [r["total"] for r in rows]
    return {
        "tasks": len(rows),
        "hit_rate": round(sum(1 for r in rows if r["hit"]) / max(1, len(rows)), 4),
        "rounds_min": min(rounds) if rounds else 0,
        "rounds_median": statistics.median(rounds) if rounds else 0,
        "rounds_max": max(rounds) if rounds else 0,
        "per_round_tokens_median": statistics.median(
            [t for r in rows for t in r["tokens_by_round"]]
        )
        if any(r["tokens_by_round"] for r in rows)
        else 0,
        "total_median": statistics.median(totals) if totals else 0,
        "total_sum": sum(totals),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    tasks = build_tasks()
    # 每个 KB 根绑一套工具（工具 api 绑定 root，跨库读会 NOT_FOUND ⇒ 必须按 task 的 kb_root 取）
    tools_by_kb: dict[str, dict] = {}
    for kb in {t["kb_root"] for t in tasks}:
        tools_by_kb[kb] = {t.name: t for t in build_kb_tools(os.path.join(REPO, kb))}
    # schema 成本用任意一套（各库 schema 相同）：3 把新工具自身定义（一次性 / 每会话）
    tools = next(iter(tools_by_kb.values())) if tools_by_kb else {}
    if not tools:
        raise SystemExit("没有可用任务/工具")

    # schema 成本：3 把新工具的定义自身（一次性 / 每会话）
    new_schema_tokens = 0
    for name in ("outline", "section", "snippet"):
        tool = tools[name]
        blob = json.dumps(
            {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
            ensure_ascii=False,
        )
        new_schema_tokens += estimate_tokens(blob)
    all_schema_tokens = 0
    for tool in tools.values():
        blob = json.dumps(
            {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
            ensure_ascii=False,
        )
        all_schema_tokens += estimate_tokens(blob)

    rows_a: list[dict] = []
    rows_b: list[dict] = []
    per_task: list[dict] = []
    for task in tasks:
        tk = tools_by_kb[task["kb_root"]]
        a = run_arm_a(tk, task)
        b = run_arm_b(tk, task)
        rows_a.append(a)
        rows_b.append(b)
        per_task.append(
            {
                "id": task["id"],
                "doc_bytes": task["doc_bytes"],
                "kind": task["kind"],
                "band": "small" if task["doc_bytes"] < 10_000 else ("mid" if task["doc_bytes"] < 30_000 else "large"),
                "heading": task["heading"],
                "A": {"rounds": a["rounds"], "total": a["total"], "hit": a["hit"]},
                "B": {"rounds": b["rounds"], "total": b["total"], "hit": b["hit"]},
                "savings": round(1 - b["total"] / a["total"], 4) if a["total"] else 0,
                "rounds_delta": b["rounds"] - a["rounds"],
            }
        )

    sa, sb = arm_summary(rows_a), arm_summary(rows_b)
    savings = round(1 - sb["total_sum"] / sa["total_sum"], 4) if sa["total_sum"] else 0
    # 分档看（U3 通常发生在 small：B 固定 2 轮 vs A 1 轮）
    # 按**意图**分档（U3 通常发生 read_section：B 固定多一轮；find_sentence 是粒度的强项）
    bands: dict[str, dict] = {}
    for band in ("read_section", "find_sentence"):
        sub = [r for r in per_task if r.get("kind") == band]
        if not sub:
            continue
        a_sum = sum(r["A"]["total"] for r in sub)
        b_sum = sum(r["B"]["total"] for r in sub)
        bands[band] = {
            "tasks": len(sub),
            "A_total_sum": a_sum,
            "B_total_sum": b_sum,
            "savings": round(1 - b_sum / a_sum, 4) if a_sum else 0,
            "avg_rounds_A": round(sum(r["A"]["rounds"] for r in sub) / len(sub), 2),
            "avg_rounds_B": round(sum(r["B"]["rounds"] for r in sub) / len(sub), 2),
        }
    # 按文档体量再拆一层（粒度收益高度依赖"所需材料占全文比例"）
    bands_by_size: dict[str, dict] = {}
    for band in ("small", "mid", "large"):
        sub = [r for r in per_task if r.get("band") == band]
        if not sub:
            continue
        a_sum = sum(r["A"]["total"] for r in sub)
        b_sum = sum(r["B"]["total"] for r in sub)
        bands_by_size[band] = {
            "tasks": len(sub),
            "A_total_sum": a_sum,
            "B_total_sum": b_sum,
            "savings": round(1 - b_sum / a_sum, 4) if a_sum else 0,
        }

    u3_alert = sb["total_sum"] > sa["total_sum"]

    payload = {
        "schema": "section-granularity-ab/v1",
        "nature": "PROXY（检索充分性 + 固定策略轮数），不是完成率；不调用模型",
        "sealed": {"MEMORIA_CONFIG_DIR": True},
        "arms": {
            "A_read_document": "read_document(offset/limit=2000) 分页整篇读，直到锚点出现",
            "B_granular": "outline → section(near_line) → 续片，直到锚点出现",
        },
        "max_rounds_per_task": MAX_ROUNDS,
        "token_estimator": "N1 静态口径（CJK 1.5 字/token，其它 3.5 字/token）",
        "tasks": len(tasks),
        "A": sa,
        "B": sb,
        "savings_total_pct": savings,
        "rounds_delta_median": statistics.median([r["rounds_delta"] for r in per_task]) if per_task else 0,
        "u3_total_up": u3_alert,
        "bands": bands,
        "bands_by_doc_size": bands_by_size,
        "schema_cost": {
            "three_new_tools_tokens": new_schema_tokens,
            "all_tools_tokens": all_schema_tokens,
            "share_pct": round(100 * new_schema_tokens / all_schema_tokens, 2) if all_schema_tokens else 0,
            "breakeven_tasks": round(new_schema_tokens / max(1, (sa["total_sum"] - sb["total_sum"]) / max(1, len(tasks))), 1)
            if sa["total_sum"] > sb["total_sum"]
            else None,
        },
        "per_task": per_task,
        "verdict": {
            "savings_ge_70pct": savings >= 0.70,
            "no_u3_regression": not u3_alert,
            "note": "双指标要求的 (i) 轮数 (ii) 每轮 token (iii) 总账 均已报；完成率需 metrics-baseline 真机补",
        },
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifactSha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print(f"tasks: {len(tasks)}（分档：{ {k: v['tasks'] for k, v in bands.items()} }）")
    print("\n== A 当前（read_document 整篇分页）==")
    print(f"  rounds: min={sa['rounds_min']} median={sa['rounds_median']} max={sa['rounds_max']} | "
          f"per-round中位={sa['per_round_tokens_median']} tok | 总账 sum={sa['total_sum']} 中位={sa['total_median']} | hit={sa['hit_rate']}")
    print("== B 粒度（outline→section）==")
    print(f"  rounds: min={sb['rounds_min']} median={sb['rounds_median']} max={sb['rounds_max']} | "
          f"per-round中位={sb['per_round_tokens_median']} tok | 总账 sum={sb['total_sum']} 中位={sb['total_median']} | hit={sb['hit_rate']}")
    print(f"\n总账节省: {savings:.2%} | 轮数变化中位: {payload['rounds_delta_median']:+} | U3 总账反升: {u3_alert}")
    for band, v in bands.items():
        print(f"  [{band}] tasks={v['tasks']} A={v['A_total_sum']} B={v['B_total_sum']} "
              f"savings={v['savings']:.2%} rounds A/B={v['avg_rounds_A']}/{v['avg_rounds_B']}")
    sc = payload["schema_cost"]
    print(f"\nschema 成本: 新增 3 工具 {sc['three_new_tools_tokens']} tok（占全部 {sc['share_pct']}%），"
          f"回本任务数≈{sc['breakeven_tasks']}")
    print(f"\n== RESULT: {'PASS' if payload['verdict']['savings_ge_70pct'] and payload['verdict']['no_u3_regression'] else 'ATTENTION'} =="
          f"  (sha256 {payload['artifactSha256'][:16]}…)")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
