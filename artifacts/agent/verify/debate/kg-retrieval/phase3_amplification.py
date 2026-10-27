#!/usr/bin/env python
"""Phase 3 自我攻击 · 目标一：放大系数 10.94× 是否被错误计算

## 攻击点（Lead 提出）
我原来的算法：
    repeat_cost = Σ_k (tool_delta[k] × (总轮数 - k - 1))
=> 假设"第 k 轮产生的工具结果会在【后续所有轮】重发"。

但 compaction 会 shadowed 旧结果（实测 8 次、遮蔽 1,598,999 字符、压掉 96.8%）。
=> 被 shadow 之后，该工具结果【不再进入后续 prompt】，不应继续算放大。
=> 正确的放大应按【存活轮数】算，不是【剩余轮数】。

## 本脚本做三件事
1. 重建每个 tool result 的"产生轮次"
2. 找出每次 compaction 的 shadowed 集合（按 seq），推断哪些 tool result 在何时失效
3. 分别算两种口径的放大系数，并给出所有中间量

## 口径定义（关键）
剩余轮数口径（原）  : 存活假设 = 一直活到会话结束
存活轮数口径（新）  : 存活假设 = 活到第一次被 shadow 覆盖的那一轮

注意：shadowed 列表里是 【seq (消息序号)】，需要把 tool/result 的 seq 映射进去。
"""

from __future__ import annotations

import json
import os
import re
import hashlib
import sys
from datetime import datetime

# ⚠️ 2026-10-27：真实会话文件是【活的】（用户 app 在跑），每次重跑数字都会变。
# ⇒ 必须用【冻结快照】才能复现。优先使用 snapshot（若存在），否则用原始会话并明确标注。
_DEFAULT_SESSION = r"D:\AAA_Courses\数字通信原理\.memoria\agent\sessions\session-20261027T011706Z-0cb419b6.jsonl"
_SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase3-session-snapshot.jsonl")
SESSION = _SNAPSHOT if os.path.exists(_SNAPSHOT) else _DEFAULT_SESSION
SESSION_IS_SNAPSHOT = os.path.exists(_SNAPSHOT)
REPO = r"D:\AAA_Jupyter\Memoria"


def est(text: str) -> int:
    if not text:
        return 0
    cn = len(re.findall(r"[\u4e00-\u9fff]", text))
    return int(cn / 1.5 + (len(text) - cn) / 3.5)


def main():
    evs = []
    for line in open(SESSION, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                evs.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # ── 1. 标注每个事件属于第几轮 ──
    turn = 0
    for e in evs:
        if e.get("type") == "loop/end":
            e["_turn"] = turn          # 本轮结束事件属于当前轮
            turn += 1
        else:
            e["_turn"] = turn          # 当前正在进行第 turn+1 轮（0-based）
    total_turns = turn
    print(f"总轮次(loop/end): {total_turns}")

    # ── 2. 收集 tool/result 及其轮次、seq、token ──
    tool_results = []
    for i, e in enumerate(evs):
        if e.get("type") != "tool/result":
            continue
        d = e.get("data") or {}
        txt = str(d.get("content") or "")
        tool_results.append({
            "idx": i,
            "seq": e.get("seq"),
            "turn": e["_turn"],
            "tool": d.get("name"),
            "tokens": est(txt),
            "chars": len(txt),
        })
    print(f"tool/result 数: {len(tool_results)}")
    print(f"tool/result 总 token(单次合计): {sum(t['tokens'] for t in tool_results):,}")

    # ── 3. 收集 compaction 的 shadowed 集合 ──
    # ⚠️ 2026-10-27 核实：`shadowed` 里的数字是【事件在文件中的行索引 idx】，
    #    不是 `seq` 字段（实测 seq==idx 为 0/713，因为 idx=0 的 session/header 无 seq，
    #    之后整体偏移 1）。两种解释在本会话恰好都命中 124 个事件，但语义上应是 idx。
    #    ⇒ 本脚本用 idx 匹配，并同时输出 seq 匹配结果作对照（若二者差异大需报警）。
    compactions = []
    for i, e in enumerate(evs):
        if e.get("type") == "compaction":
            d = e.get("data") or {}
            sh = d.get("shadowed") or []
            compactions.append({
                "idx": i,
                "seq": e.get("seq"),
                "turn": e["_turn"],
                "shadowed_idxs": set(sh) if isinstance(sh, list) else set(),
                "shadowed_count": len(sh),
                "shadowed_chars": d.get("shadowed_chars"),
            })
    print(f"compaction 数: {len(compactions)}")
    for c in compactions:
        print(f"  idx={c['idx']} turn={c['turn']+1} seq={c['seq']} "
              f"shadowed={c['shadowed_count']} 个, chars={c['shadowed_chars']}")

    # ── 4. 对每个 tool result，找它第一次被 shadow 的轮次（用 idx 匹配）──
    for t in tool_results:
        t["shadowed_at_turn"] = None
        for c in compactions:
            if c["turn"] < t["turn"]:
                continue        # 不可能遮蔽"产生之前"的东西
            if t["idx"] in c["shadowed_idxs"]:
                t["shadowed_at_turn"] = c["turn"]
                break

    shadowed = [t for t in tool_results if t["shadowed_at_turn"] is not None]
    survived = [t for t in tool_results if t["shadowed_at_turn"] is None]
    print()
    print(f"被 shadow 的 tool result: {len(shadowed)} 个  "
          f"(token {sum(t['tokens'] for t in shadowed):,})")
    print(f"存活到结束的 tool result: {len(survived)} 个  "
          f"(token {sum(t['tokens'] for t in survived):,})")

    # ── 5. 两种口径的放大系数 ──
    # 口径 A（原，剩余轮数）：第 k 轮产生 ⇒ 后续 (total_turns - 1 - k) 轮重发
    rep_remain = 0
    for t in tool_results:
        remaining = total_turns - 1 - t["turn"]
        rep_remain += t["tokens"] * max(remaining, 0)

    # 口径 B（新，存活轮数）：第 k 轮产生 ⇒ 只活到 shadowed_at_turn（不含）
    rep_alive = 0
    detail = []
    for t in tool_results:
        if t["shadowed_at_turn"] is None:
            alive_rounds = total_turns - 1 - t["turn"]
        else:
            alive_rounds = t["shadowed_at_turn"] - t["turn"] - 1
            alive_rounds = max(alive_rounds, 0)
        rep_remain_k = max(total_turns - 1 - t["turn"], 0)
        rep_alive += t["tokens"] * alive_rounds
        detail.append({
            "seq": t["seq"], "turn": t["turn"] + 1, "tool": t["tool"],
            "tokens": t["tokens"],
            "remain_rounds": rep_remain_k,
            "alive_rounds": alive_rounds,
            "shadowed_at_turn": (t["shadowed_at_turn"] + 1) if t["shadowed_at_turn"] is not None else None,
        })

    base = sum(t["tokens"] for t in tool_results)
    print()
    print("=" * 76)
    print("两种口径的放大系数")
    print("=" * 76)
    print(f"基准：tool result 单次合计 = {base:,} token")
    print()
    print(f"口径A（剩余轮数，我原来的算法）:")
    print(f"  重发额外量 = {rep_remain:,} token")
    print(f"  放大系数   = {rep_remain/base:.2f}×   (总发送量/单次量 = {(base+rep_remain)/base:.2f}×)")
    print()
    print(f"口径B（存活轮数，考虑 compaction 遮蔽）:")
    print(f"  重发额外量 = {rep_alive:,} token")
    print(f"  放大系数   = {rep_alive/base:.2f}×   (总发送量/单次量 = {(base+rep_alive)/base:.2f}×)")
    print()
    print(f"差异: {rep_remain - rep_alive:,} token "
          f"({(1-rep_alive/max(rep_remain,1))*100:.1f}% 被 compaction 消掉)")
    print(f"系数比: {rep_alive/max(rep_remain,1):.3f}")

    # ── 6. 按工具分组看两种口径 ──
    print()
    print("按工具（剩余轮数 vs 存活轮数）:")
    bytool = {}
    for d in detail:
        x = bytool.setdefault(d["tool"], {"tokens": 0, "remain": 0, "alive": 0, "n": 0})
        x["tokens"] += d["tokens"]
        x["remain"] += d["tokens"] * d["remain_rounds"]
        x["alive"] += d["tokens"] * d["alive_rounds"]
        x["n"] += 1
    print(f"  {'工具':<16} {'n':>3} {'单次tok':>9} {'剩余口径':>10} {'存活口径':>10} {'存活系数':>8}")
    for tool, x in sorted(bytool.items(), key=lambda kv: -kv[1]["alive"]):
        coef_a = x["remain"] / max(x["tokens"], 1)
        coef_b = x["alive"] / max(x["tokens"], 1)
        print(f"  {tool:<16} {x['n']:>3} {x['tokens']:>9,} {coef_a:>9.2f}× {coef_b:>9.2f}×")

    # ── 7. 结论判定 ──
    coef_a = rep_remain / max(base, 1)
    coef_b = rep_alive / max(base, 1)
    print()
    print("=" * 76)
    print("判定")
    print("=" * 76)
    if coef_b < 4.0:
        verdict = f"❌ 我的 10.94× 站不住：按存活口径只有 {coef_b:.2f}×，应降级 P0 优先级"
    elif coef_b < 7.0:
        verdict = f"⚠️ 我的 10.94× 被高估：真实 {coef_b:.2f}×，仍显著但需修正表述"
    else:
        verdict = f"✅ 我的 10.94× 基本成立：存活口径仍有 {coef_b:.2f}×"
    print("  " + verdict)

    payload = {
        "schema": "r8-objection-amplification/v1",
        "measured_at": datetime.now().astimezone().isoformat(),
        "session": SESSION,
        "session_is_frozen_snapshot": SESSION_IS_SNAPSHOT,
        "session_sha256": hashlib.sha256(open(SESSION, "rb").read()).hexdigest(),
        "REPRODUCIBILITY_NOTE": (
            "原始会话是活的（用户 app 在写）；本结果基于冻结快照 "
            "phase3-session-snapshot.jsonl，其 sha256 见上。"
            "若直接用原始会话重跑，数字会变——这是本项目已记录的"
            "『语料不可复现』类问题（见 kgviz corpus-refreeze）。"
        ),
        "total_turns": total_turns,
        "tool_results": {
            "count": len(tool_results),
            "sum_tokens": base,
            "shadowed_count": len(shadowed),
            "shadowed_tokens": sum(t["tokens"] for t in shadowed),
            "survived_count": len(survived),
            "survived_tokens": sum(t["tokens"] for t in survived),
        },
        "amplification": {
            "residual_rounds": {"extra": rep_remain, "coefficient": round(coef_a, 3)},
            "survival_rounds": {"extra": rep_alive, "coefficient": round(coef_b, 3)},
            "ratio": round(coef_b / max(coef_a, 1e-9), 3),
        },
        "by_tool": {k: {"n": v["n"], "tokens": v["tokens"],
                        "coef_residual": round(v["remain"] / max(v["tokens"], 1), 3),
                        "coef_survival": round(v["alive"] / max(v["tokens"], 1), 3)}
                    for k, v in bytool.items()},
        "detail": detail,
        "verdict": verdict,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    payload["artifact_sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()

    out = os.path.join(REPO, "artifacts/agent/verify/debate/kg-retrieval/phase3-amplification.json")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print()
    print(f"artifact: {out}")
    print(f"sha256  : {payload['artifact_sha256'][:16]}…")


if __name__ == "__main__":
    main()
