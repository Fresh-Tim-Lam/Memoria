"""Phase 1 / C 线：真实会话的 agent 检索决策路径测量（只读）。

分析对象（ACCOUNT 同一会话）：
  D:\\AAA_Courses\\数字通信原理\\.memoria\\agent\\sessions\\session-20261027T011706Z-0cb419b6.jsonl

产出：
  · 每轮工具序列/工具结果字符数/成功失败
  · search_kb 命中率、read_document/read_kp/outline/section/snippet/kb_overview/pwsh 使用分布
  · 重复读同一文件/重复同一 query 的次数
  · 工具结果 token 增量 vs prompt 增量（看工具输出是不是上下文膨胀主因）
  · 费用场景测算：只减 prompt vs 只减轮数 vs 两者都减

用法：
  python artifacts/agent/verify/debate/kg-retrieval/scripts/analyze_session.py --json out.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections import Counter, defaultdict

ROOT = r"D:\AAA_Jupyter\Memoria"
sys.path.insert(0, os.path.join(ROOT, "src"))
from memoria.services.agent.llm import pricing  # noqa: E402

SESSION = os.path.join(
    r"D:\AAA_Courses\数字通信原理",
    ".memoria", "agent", "sessions", "session-20261027T011706Z-0cb419b6.jsonl",
)
CHARS_PER_TOKEN = 3.5  # N1/项目经验口径（与 section_index.estimate_tokens 一致）


def est_tokens(text: str) -> float:
    return len(text) / CHARS_PER_TOKEN


def load_events(path: str) -> list[dict]:
    out: list[dict] = []
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def command_head(cmd: str, n: int = 100) -> str:
    return " ".join(str(cmd or "").split())[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    events = load_events(SESSION)
    # tool/result 按 id 索引
    results: dict[str, dict] = {}
    for e in events:
        if e.get("type") == "tool/result":
            d = e.get("data") or {}
            results[str(d.get("id"))] = d

    turns: list[dict] = []
    cur: dict = {"user": None, "calls": [], "usage": None, "loop": {}}
    pending_user: str | None = None
    for e in events:
        t = e.get("type")
        d = e.get("data") or {}
        if t == "user/message":
            pending_user = str(d.get("text") or "")
        elif t == "tool/call":
            name = str(d.get("name") or "")
            a = parse_args(d.get("arguments"))
            r = results.get(str(d.get("id"))) or {}
            content = str(r.get("content") or "")
            cur["calls"].append(
                {
                    "name": name,
                    "args": a,
                    "result_chars": len(content),
                    "result_tokens": round(est_tokens(content), 1),
                    "is_error": bool(r.get("is_error")),
                    "code": r.get("code"),
                    "content_head": content[:180],
                }
            )
        elif t == "loop/end":
            cur["usage"] = d.get("usage") or {}
            cur["loop"] = {
                "stop_reason": d.get("stop_reason"),
                "iterations": d.get("iterations"),
                "model": d.get("model"),
                "time": e.get("time"),
            }
            cur["user"] = pending_user
            pending_user = None
            turns.append(cur)
            cur = {"user": None, "calls": [], "usage": None, "loop": {}}

    # ── 工具面统计 ──
    name_counts: Counter = Counter()
    result_chars_by_name: Counter = Counter()
    errors_by_name: Counter = Counter()
    reads_by_path: Counter = Counter()
    search_queries: Counter = Counter()
    search_missing = 0
    pwsh_cmds: list[dict] = []
    for ti, turn in enumerate(turns, 1):
        turn["tool_calls"] = len(turn["calls"])
        turn["result_chars"] = sum(c["result_chars"] for c in turn["calls"])
        turn["result_tokens"] = round(sum(c["result_tokens"] for c in turn["calls"]), 1)
        turn["tool_seq"] = [c["name"] for c in turn["calls"]]
        for c in turn["calls"]:
            c["turn"] = ti
            name_counts[c["name"]] += 1
            result_chars_by_name[c["name"]] += c["result_chars"]
            if c["is_error"]:
                errors_by_name[c["name"]] += 1
            if c["name"] == "read_document":
                p = str(c["args"].get("path") or c["args"].get("rel_path") or "")
                reads_by_path[p] += 1
            elif c["name"] == "search_kb":
                q = str(c["args"].get("query") or "")
                search_queries[q] += 1
                if c["is_error"] or "未在知识库中检索到" in (c["content_head"] or ""):
                    search_missing += 1
            elif c["name"] in ("pwsh", "cmd"):
                pwsh_cmds.append(
                    {
                        "turn": ti,
                        "name": c["name"],
                        "cmd": command_head(str(c["args"].get("command") or "")),
                        "result_chars": c["result_chars"],
                        "is_error": c["is_error"],
                    }
                )

    # ── 费用 ──
    rows = []
    for ti, turn in enumerate(turns, 1):
        u = turn["usage"] or {}
        prompt = int(u.get("prompt_tokens") or 0)
        hit = int(u.get("cache_read_tokens") or 0)
        miss = int(u.get("cache_miss_tokens") or 0)
        out = int(u.get("completion_tokens") or 0)
        row = {
            "prompt": prompt,
            "cache_hit": hit,
            "cache_miss": miss,
            "completion": out,
            "time": turn["loop"].get("time"),
        }
        model = turn["loop"].get("model") or "deepseek-v4-flash"
        cost = pricing.turn_cost(row, model)
        rows.append(
            {
                "turn": ti,
                "prompt": prompt,
                "hit": hit,
                "miss": miss,
                "out": out,
                "cost_hit": cost["hit_cost"] if cost else None,
                "cost_miss": cost["miss_cost"] if cost else None,
                "cost_out": cost["output_cost"] if cost else None,
                "cost_total": (cost["hit_cost"] + cost["miss_cost"] + cost["output_cost"]) if cost else None,
            }
        )

    total_hit = sum(r["cost_hit"] or 0 for r in rows)
    total_miss = sum(r["cost_miss"] or 0 for r in rows)
    total_out = sum(r["cost_out"] or 0 for r in rows)
    total = total_hit + total_miss + total_out

    # ── 工具结果的"上下文放大"成本 ──
    # 一个工具结果在加入后的每一轮/每次迭代都会被重新发送。loop/end 的 usage 是整轮聚合，
    # 因此用下界近似：结果 token × (1 + 后续轮数)，再用各轮实际单价折算金额。
    total_turns = len(turns)
    amp_tokens: Counter = Counter()
    amp_cost: Counter = Counter()
    for idx, turn in enumerate(turns, 1):
        remaining = total_turns - idx
        u = turn["usage"] or {}
        miss = int(u.get("cache_miss_tokens") or 0)
        r = rows[idx - 1]
        unit_miss = (r["cost_miss"] / miss) if miss and r["cost_miss"] else 0.0
        for c in turn["calls"]:
            factor = 1 + remaining
            amp_tokens[c["name"]] += c["result_tokens"] * factor
            amp_cost[c["name"]] += c["result_tokens"] * factor * unit_miss  # 保守：按未命中单价

    amplification = {
        "note": "工具结果 token × (1+后续轮数)；金额按各轮未命中单价保守折算（未计入同轮内多次迭代）",
        "tokens_by_name": {k: round(v, 1) for k, v in amp_tokens.most_common()},
        "cost_est_by_name": {k: round(v, 5) for k, v in amp_cost.most_common()},
        "total_cost_est": round(sum(amp_cost.values()), 5),
    }

    # ── 场景测算 ──
    def scenario(prompt_factor: float, round_factor: float) -> dict:
        """prompt_factor: 每轮 prompt token 比例；round_factor: 轮数比例（按随机等价：按比例缩放计量）。"""
        cost = 0.0
        for r in rows:
            # 价格按各轮实际档位（用该轮原价的每 token 单价）
            unit_hit = (r["cost_hit"] or 0) / r["hit"] if r["hit"] else 0.0
            unit_miss = (r["cost_miss"] or 0) / r["miss"] if r["miss"] else 0.0
            unit_out = (r["cost_out"] or 0) / r["out"] if r["out"] else 0.0
            cost += (
                (r["hit"] * unit_hit + r["miss"] * unit_miss) * prompt_factor + r["out"] * unit_out
            ) * round_factor
        return {"cost": round(cost, 5), "delta_pct": round((cost - total) / total * 100, 2) if total else None}

    scenarios = {
        "current": {"cost": round(total, 5), "delta_pct": 0.0},
        "prompt_x0.5_only": scenario(0.5, 1.0),
        "prompt_x0.25_only": scenario(0.25, 1.0),
        "rounds_x0.75_only": scenario(1.0, 0.75),
        "rounds_x0.5_only": scenario(1.0, 0.5),
        "both_prompt0.5_rounds0.75": scenario(0.5, 0.75),
    }

    report = {
        "session": SESSION,
        "turns": len(turns),
        "events": len(events),
        "tool_calls_total": sum(name_counts.values()),
        "name_counts": dict(name_counts.most_common()),
        "result_chars_by_name": dict(result_chars_by_name.most_common()),
        "result_tokens_by_name": {k: round(v / CHARS_PER_TOKEN, 1) for k, v in result_chars_by_name.most_common()},
        "errors_by_name": dict(errors_by_name),
        "search_kb": {
            "calls": name_counts.get("search_kb", 0),
            "missing": search_missing,
            "queries": dict(search_queries),
        },
        "read_document_paths": dict(reads_by_path.most_common()),
        "read_kp_calls": name_counts.get("read_kp", 0),
        "outline_calls": name_counts.get("outline", 0),
        "section_calls": name_counts.get("section", 0),
        "snippet_calls": name_counts.get("snippet", 0),
        "kb_overview_calls": name_counts.get("kb_overview", 0),
        "pwsh_calls": len(pwsh_cmds),
        "pwsh_samples": pwsh_cmds[:20],
        "dup_reads": {p: n for p, n in reads_by_path.items() if n > 1},
        "amplification": amplification,
        "per_turn": [
            {
                "turn": idx,
                "user": (t["user"] or "")[:80],
                "tool_calls": t["tool_calls"],
                "tool_seq": t["tool_seq"],
                "result_chars": t.get("result_chars"),
                "result_tokens": t.get("result_tokens"),
                "prompt": (t["usage"] or {}).get("prompt_tokens"),
                "cost_total": rows[idx - 1]["cost_total"],
            }
            for idx, t in enumerate(turns, 1)
        ],
        "cost": {
            "total": round(total, 5),
            "hit": round(total_hit, 5),
            "miss": round(total_miss, 5),
            "out": round(total_out, 5),
            "share_out_pct": round(total_out / total * 100, 2) if total else None,
            "share_miss_pct": round(total_miss / total * 100, 2) if total else None,
            "share_hit_pct": round(total_hit / total * 100, 2) if total else None,
            "per_round_avg": round(total / len(rows), 5) if rows else None,
        },
        "scenarios": scenarios,
        "prompt_tokens": {
            "total": sum(r["prompt"] for r in rows),
            "avg": round(sum(r["prompt"] for r in rows) / len(rows), 1) if rows else None,
            "max": max((r["prompt"] for r in rows), default=0),
        },
        "tool_result_tokens_total": round(sum(result_chars_by_name.values()) / CHARS_PER_TOKEN, 1),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
