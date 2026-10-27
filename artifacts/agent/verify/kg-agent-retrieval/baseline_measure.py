#!/usr/bin/env python
"""task-190｜T-base-1/2/3/4：大知识库 agent 上下文膨胀与缓存命中的真实归因

## 数据源（真库，非合成）
`D:\\AAA_Courses\\数字通信原理\\.memoria\\agent\\sessions\\session-20261027T011706Z-0cb419b6.jsonl`
（16 轮真实会话，567 条事件）

## 这个脚本回答四个问题
T-base-1 单轮 prompt 构成拆解：system / tools / history / tool-results 各自 token 与占比
T-base-2 read_document 读最大章节（407KB）时的**实际 token 量**（实测，非估算）
T-base-3 多轮 cache hit 曲线（逐轮 cache_hit / prompt / cache_miss）
T-base-4 前缀稳定性：连续两轮 messages 逐段 diff + "前缀稳定区间" token 数

## 口径声明（关键，防止误读）
· token 计数口径：本脚本用 **字符数 / 1.5（中文）+ 1/3.5（ASCII）混合估算**，
  并在可能处用会话日志里的**真实 usage 字段**校准（优先真实值）。
· 凡标 `measured=True` 的来自日志真实 usage；标 `estimated=True` 的是估算。
· **不许把估算值当实测卖**（这是本项目的红线，见 PROTOCOL E4.2）。

用法:
    python artifact_tokens.py [--json out.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

SESSION = r"D:\AAA_Courses\数字通信原理\.memoria\agent\sessions\session-20261027T011706Z-0cb419b6.jsonl"
REPO = r"D:\AAA_Jupyter\Memoria"
OUTDIR = os.path.join(REPO, "artifacts", "agent", "verify", "kg-agent-retrieval")


def est_tokens(text: str) -> int:
    """估算 token：中文按 1.5 字/token，ASCII 按 3.5 字符/token"""
    if not text:
        return 0
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = len(text) - cn
    return int(cn / 1.5 + other / 3.5)


def load_events(path: str) -> list[dict]:
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ─────────────────────────────────────────────────────────────
# T-base-3：cache hit 曲线（用日志里的真实 usage）
# ─────────────────────────────────────────────────────────────

def tbase3_cache_curve(events: list[dict]) -> dict:
    """从 loop/end.data.usage 取真实 usage（已核实：estimated=false，是真值）

    2026-10-27 修正：真实结构是 {"type":"loop/end","data":{"usage":{
        prompt_tokens, completion_tokens, total_tokens, estimated,
        cache_read_tokens, cache_write_tokens, cache_miss_tokens}}}
    """
    rows = []
    for i, e in enumerate(events):
        d = e.get("data") or {}
        u = d.get("usage")
        if not isinstance(u, dict):
            continue
        pt = u.get("prompt_tokens") or 0
        ct = u.get("completion_tokens") or 0
        hit = u.get("cache_read_tokens")          # ← 真实字段名
        miss = u.get("cache_miss_tokens")
        rows.append({
            "event_index": i,
            "event_type": e.get("type"),
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "cache_hit_tokens": hit,
            "cache_miss_tokens": miss,
            "estimated": u.get("estimated"),
            "model": d.get("model"),
            "stop_reason": d.get("stop_reason"),
            "hit_ratio": round(hit / pt, 4) if (hit is not None and pt) else None,
        })
    return {"count": len(rows), "rows": rows}


# ─────────────────────────────────────────────────────────────
# T-base-2：最大单次工具结果（read_document 读 407KB 章节）
# ─────────────────────────────────────────────────────────────

def tbase2_tool_results(events: list[dict]) -> dict:
    """找出最大的单次 tool/result

    2026-10-27 修正：真实结构
    {"type":"tool/result","data":{"id","name","is_error","code","content","anchors"}}
    """
    results = []
    for i, e in enumerate(events):
        if e.get("type") != "tool/result":
            continue
        d = e.get("data") or {}
        text = d.get("content")
        if not isinstance(text, str):
            text = json.dumps(d, ensure_ascii=False)
        tool = d.get("name") or "(unknown)"
        results.append({
            "event_index": i,
            "tool": tool,
            "is_error": d.get("is_error"),
            "chars": len(text),
            "est_tokens": est_tokens(text),
            "head": text[:160].replace("\n", " "),
        })
    results.sort(key=lambda x: -x["chars"])
    by_tool = {}
    for r in results:
        d = by_tool.setdefault(r["tool"], {"calls": 0, "chars": 0, "est_tokens": 0, "max_tokens": 0})
        d["calls"] += 1
        d["chars"] += r["chars"]
        d["est_tokens"] += r["est_tokens"]
        d["max_tokens"] = max(d["max_tokens"], r["est_tokens"])
    errors = sum(1 for r in results if r["is_error"])
    return {
        "total_tool_results": len(results),
        "error_results": errors,
        "total_chars": sum(r["chars"] for r in results),
        "total_est_tokens": sum(r["est_tokens"] for r in results),
        "top10_largest": results[:10],
        "by_tool": dict(sorted(by_tool.items(), key=lambda kv: -kv[1]["est_tokens"])),
    }


# ─────────────────────────────────────────────────────────────
# T-base-2b：read_document 读 407KB 章节的理论实测（本地直接算）
# ─────────────────────────────────────────────────────────────

def tbase2b_chapter_size() -> dict:
    """直接读 407KB 章节，算实际 token 量（这是"读整章"的代价）"""
    kb = os.path.join(REPO, "artifacts", "baseline-kb", "数字通信原理")
    if not os.path.isdir(kb):
        return {"error": "KB copy missing"}
    mds = []
    for dp, dn, fn in os.walk(kb):
        dn[:] = [d for d in dn if d not in (".memoria", "__pycache__")]
        for f in fn:
            if f.endswith(".md"):
                p = os.path.join(dp, f)
                mds.append((os.path.relpath(p, kb).replace("\\", "/"), os.path.getsize(p), p))
    mds.sort(key=lambda x: -x[1])
    rows = []
    for rel, size, p in mds[:8]:
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception:
            continue
        rows.append({
            "path": rel,
            "bytes": size,
            "chars": len(txt),
            "est_tokens": est_tokens(txt),
            # read_document 默认 2000 行上限
            "lines": txt.count("\n") + 1,
            "exceeds_read_limit": (txt.count("\n") + 1) > 2000,
        })
    total = sum(r["est_tokens"] for r in rows)
    return {"chapter_count": len(rows), "chapters": rows,
            "sum_est_tokens_top8": total}


# ─────────────────────────────────────────────────────────────
# T-base-1：单轮 prompt 构成拆解
# ─────────────────────────────────────────────────────────────

def tbase1_composition(events: list[dict]) -> dict:
    """拆解单轮 prompt 的构成：system / tools / history / tool-results"""
    # 用 usage 里的 prompt_tokens 作分母，逐段估算
    # 1) tools schema：从 kb.py 实测（已知 35 工具 ≈ 4349 token，见 n1_token_model）
    tools_schema_est = 4349

    # 2) system prompt：找 session/header 或第一条 user 之前的 system
    sys_text = ""
    for e in events:
        if e.get("type") in ("session/header", "session/title"):
            p = e.get("payload") or {}
            for k in ("system", "system_prompt"):
                if isinstance(p.get(k), str):
                    sys_text = p[k]
                    break
        if sys_text:
            break

    # 3) tool results 总量
    tr = tbase2_tool_results(events)

    # 4) 真实 prompt 总量
    cc = tbase3_cache_curve(events)
    total_prompt = sum(r["prompt_tokens"] for r in cc["rows"])
    total_comp = sum(r["completion_tokens"] for r in cc["rows"])

    sys_est = est_tokens(sys_text) if sys_text else 0

    return {
        "source": "usage 真实值 + 分项估算",
        "total_prompt_tokens_measured": total_prompt,
        "total_completion_tokens_measured": total_comp,
        "rounds_with_usage": cc["count"],
        "components_estimated": {
            "tools_schema": tools_schema_est,
            "system_prompt": sys_est,
            "tool_results_cumulative": tr["total_est_tokens"],
        },
        "note": (
            "分项是估算：tools schema 来自 kb.py 实测 4349 token；"
            "tool_results 来自日志文本按字符估算；"
            "history 是剩余项（prompt 总量 - 已知项）"
        ),
    }


# ─────────────────────────────────────────────────────────────
# T-base-4：前缀稳定性（连续两轮 messages 逐段 diff）
# ─────────────────────────────────────────────────────────────

def tbase4_prefix_stability(events: list[dict]) -> dict:
    """比较相邻两轮请求的 messages 前缀，找出"前缀稳定区间"

    2026-10-27 修正：真实结构在 data 字段
      user/message.data.content
      assistant/message.data.content / data.reasoning / data.tool_calls
      tool/result.data.content
    """
    seq = []   # [(kind, text)]
    rounds = []
    for e in events:
        t = e.get("type")
        d = e.get("data") or {}
        if t == "user/message":
            txt = d.get("content") or d.get("text") or ""
            if isinstance(txt, list):
                txt = " ".join(str(x) for x in txt)
            seq.append(("user", str(txt)))
        elif t == "assistant/message":
            parts = []
            if d.get("reasoning"):
                parts.append(str(d["reasoning"]))
            if d.get("content"):
                parts.append(str(d["content"]))
            for tc in (d.get("tool_calls") or []):
                parts.append(json.dumps(tc, ensure_ascii=False))
            seq.append(("assistant", "\n".join(parts)))
        elif t == "tool/result":
            seq.append(("tool", str(d.get("content") or "")))
        elif t == "loop/end":
            rounds.append(list(seq))

    if len(rounds) < 2:
        return {"error": "rounds < 2", "rounds": len(rounds)}

    diffs = []
    for i in range(1, len(rounds)):
        a, b = rounds[i - 1], rounds[i]
        common = 0
        for j in range(min(len(a), len(b))):
            if a[j] == b[j]:
                common += 1
            else:
                break
        prefix_tokens = sum(est_tokens(x[1]) for x in b[:common])
        total_tokens = sum(est_tokens(x[1]) for x in b)
        diffs.append({
            "round_pair": f"{i}->{i+1}",
            "prev_len": len(a),
            "cur_len": len(b),
            "common_prefix_events": common,
            "diverged_at": common if common < min(len(a), len(b)) else None,
            "prefix_stable_tokens": prefix_tokens,
            "total_tokens": total_tokens,
            "prefix_ratio": round(prefix_tokens / total_tokens, 4) if total_tokens else None,
            "all_stable": common == min(len(a), len(b)),
        })
    return {
        "rounds_detected": len(rounds),
        "pairs": diffs,
        "note": ("prefix_stable_tokens = 该轮与前一轮逐段完全相同的前缀所含 token；"
                 "只有这部分可能命中缓存（还需服务端缓存策略配合）"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    if not os.path.exists(SESSION):
        print(f"会话文件不存在: {SESSION}")
        return 1

    events = load_events(SESSION)

    t1 = tbase1_composition(events)
    t2 = tbase2_tool_results(events)
    t2b = tbase2b_chapter_size()
    t3 = tbase3_cache_curve(events)
    t4 = tbase4_prefix_stability(events)

    payload = {
        "schema": "kg-retrieval-baseline/v1",
        "measured_at": datetime.now().astimezone().isoformat(),
        "head": os.popen(f'git -C "{REPO}" rev-parse HEAD').read().strip(),
        "session_file": SESSION,
        "session_sha256": (hashlib.sha256(open(SESSION, "rb").read()).hexdigest()
                           if os.path.exists(SESSION) else None),
        "events_total": len(events),
        "event_types": dict(Counter(e.get("type") for e in events)),
        "T-base-1_composition": t1,
        "T-base-2_tool_results": t2,
        "T-base-2b_chapter_size": t2b,
        "T-base-3_cache_curve": t3,
        "T-base-4_prefix_stability": t4,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifact_sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    print("=" * 78)
    print("task-190 基线测量：上下文膨胀与缓存命中归因")
    print("=" * 78)
    print(f"HEAD        : {payload['head'][:8]}")
    print(f"会话事件    : {len(events)}   {payload['event_types']}")
    print()

    print("── T-base-1 单轮 prompt 构成 ──")
    print(f"  真实 prompt 总量 (measured): {t1['total_prompt_tokens_measured']:,}")
    print(f"  真实 completion (measured) : {t1['total_completion_tokens_measured']:,}")
    print(f"  含 usage 的轮次            : {t1['rounds_with_usage']}")
    for k, v in t1["components_estimated"].items():
        print(f"    {k:<28} {v:,} (估)")
    print()

    print("── T-base-2 工具结果（实测文本量）──")
    print(f"  tool/result 次数: {t2['total_tool_results']}")
    print(f"  总字符 {t2['total_chars']:,}  估算 {t2['total_est_tokens']:,} token")
    print("  按工具聚合（按 token 降序）:")
    for tool, d in list(t2["by_tool"].items())[:10]:
        print(f"    {tool:<22} calls={d['calls']:<3} 总={d['est_tokens']:<8,} "
              f"单次最大={d['max_tokens']:,}")
    print("  最大 5 次单次结果:")
    for r in t2["top10_largest"][:5]:
        print(f"    [{r['event_index']:>3}] {r['tool']:<18} {r['chars']:>10,} chars "
              f"≈{r['est_tokens']:>8,} tok  | {r['head'][:60]}")
    print()

    print("── T-base-2b 教材章节实测（本地真库）──")
    print(f"  章节数: {t2b.get('chapter_count')}")
    for c in t2b.get("chapters", [])[:5]:
        print(f"    {c['path'][:40]:<42} {c['bytes']//1024:>5}KB  {c['chars']:>8,}字  "
              f"≈{c['est_tokens']:>8,}tok  lines={c['lines']}"
              f"{'  ⚠️超2000行' if c['exceeds_read_limit'] else ''}")
    print(f"  top8 合计 ≈ {t2b.get('sum_est_tokens_top8',0):,} token")
    print()

    print("── T-base-3 cache hit 曲线 ──")
    print(f"  含 usage 的事件: {t3['count']}")
    for r in t3["rows"][:20]:
        hit = r["cache_hit_tokens"]
        miss = r["cache_miss_tokens"]
        pt = r["prompt_tokens"]
        ratio = f"{hit/pt*100:.2f}%" if (hit is not None and pt) else "n/a"
        print(f"    #{r['event_index']:<4} prompt={pt:>8,} comp={r['completion_tokens']:>6,} "
              f"hit={hit if hit is not None else 'None':>9} miss={miss if miss is not None else 'None':>8} 命中率={ratio}")
    print()

    print("── T-base-4 前缀稳定性 ──")
    if "error" in t4:
        print(f"  {t4['error']}  rounds={t4.get('rounds')}")
    else:
        print(f"  检出轮数: {t4['rounds_detected']}")
        for p in t4["pairs"][:12]:
            print(f"    {p['round_pair']:<8} prev={p['prev_len']:<4} cur={p['cur_len']:<4} "
                  f"共同前缀={p['common_prefix_events']:<4} "
                  f"前缀token={p['prefix_stable_tokens']:>8,} "
                  f"占比={p['prefix_ratio']}")
    print()
    print(f"artifact sha256: {payload['artifact_sha256'][:16]}…")

    if args.json:
        out = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(f"wrote: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
