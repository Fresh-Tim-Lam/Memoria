#!/usr/bin/env python
"""task-199｜第二轮：四门禁可执行性实测（M4 / M5 / M2 / M12）

## 这是一份"能不能跑"的探测脚本，不是门禁实现
目的：对每个门禁回答
  · 需要什么前置数据
  · 现在能不能跑（能 / 缺什么）
  · 跑一次要多久

## 语料
真库 `D:\\AAA_Courses\\数字通信原理`（26 md / 11 sidecar，与 14:09:46 快照一致）
快照身份：`artifacts/agent/verify/debate/kg-retrieval/data/corpus-snapshot.json`

## 口径纪律（上一轮教训）
· 凡"现在跑不出"，明确写缺什么，不用估算冒充
· 凡计时，标注是单次实测
"""

from __future__ import annotations

import json
import os
import sys
import time
import hashlib
import tempfile

REPO = r"D:\AAA_Jupyter\Memoria"
KB_REAL = r"D:\AAA_Courses\数字通信原理"
KB_COPY = os.path.join(REPO, "artifacts", "baseline-kb", "数字通信原理")
SNAPSHOT = os.path.join(REPO, "artifacts", "agent", "verify", "debate", "kg-retrieval",
                        "data", "corpus-snapshot.json")

os.environ.setdefault("MEMORIA_CONFIG_DIR", tempfile.mkdtemp(prefix="memoria-r2-"))
sys.path.insert(0, os.path.join(REPO, "src"))


def t0() -> float:
    return time.perf_counter()


def run_validate_kb(kb: str) -> dict:
    """M4 的数据来源：validate_kb 的 errors/warnings"""
    from memoria.services.agent.tools.kb import build_kb_tools
    tools = {t.name: t for t in build_kb_tools(kb, session_id="r2-probe")}
    start = t0()
    out = tools["validate_kb"].handler({})
    elapsed = t0() - start
    return {"text": out.text, "elapsed_ms": round(elapsed * 1000, 1)}


def parse_validate(text: str) -> dict:
    """从 validate_kb 文本里抽 error/warning 计数与错误码分布"""
    import re
    from collections import Counter
    m = re.search(r"检查\s*(\d+)\s*篇文档，errors=(\d+)\s*warnings=(\d+)", text)
    codes = Counter(re.findall(r"'code':\s*'([^']+)'", text))
    kps = re.findall(r"'kp_id':\s*'([^']+)'", text)
    return {
        "docs_checked": int(m.group(1)) if m else None,
        "errors": int(m.group(2)) if m else None,
        "warnings": int(m.group(3)) if m else None,
        "codes": dict(codes),
        "affected_kp_count": len(set(kps)),
        "affected_kp_sample": sorted(set(kps))[:5],
    }


def probe_kp_health(kb: str) -> dict:
    """M4 真正需要的：逐 KP 的 range_ok / 反转 / span / snippet 唯一性"""
    from memoria.services.document import DocumentService
    start = t0()
    svc = DocumentService(kb)
    # 触发解析
    docs = []
    try:
        docs = svc.list_documents() if hasattr(svc, "list_documents") else []
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    total_kp = 0
    range_ok_false = 0
    inverted = 0
    span_zero = 0
    snippet_missing = 0
    per_doc = []

    for d in docs:
        rel = d.get("path") or d.get("rel") or ""
        if not rel.endswith(".md"):
            continue
        try:
            doc = svc.get_document(rel) if hasattr(svc, "get_document") else None
        except Exception:
            doc = None
        if doc is None:
            continue
        for kp in (getattr(doc, "knowledge_points", None) or []):
            total_kp += 1
            rr = getattr(kp, "range_resolved", None)
            ok = getattr(rr, "ok", None) if rr else None
            if ok is False:
                range_ok_false += 1
            s = getattr(rr, "start_line", None) if rr else None
            e = getattr(rr, "end_line", None) if rr else None
            if isinstance(s, int) and isinstance(e, int):
                if e < s:
                    inverted += 1
                if e == s:
                    span_zero += 1
            sn = getattr(kp, "range", None)
            if isinstance(sn, dict):
                if not sn.get("snippet") or not sn.get("end_snippet"):
                    snippet_missing += 1
        per_doc.append({"path": rel, "kps": len(getattr(doc, "knowledge_points", None) or [])})
    elapsed = t0() - start
    return {
        "elapsed_ms": round(elapsed * 1000, 1),
        "docs_parsed": len(per_doc),
        "total_kp": total_kp,
        "range_ok_false": range_ok_false,
        "inverted": inverted,
        "span_zero": span_zero,
        "snippet_missing": snippet_missing,
        "per_doc_kp_total": sum(x["kps"] for x in per_doc),
    }


def probe_m2_collision(kb: str) -> dict:
    """M2 需要的：同文件重名 KP"""
    from memoria.services.document import DocumentService
    start = t0()
    svc = DocumentService(kb)
    try:
        docs = svc.list_documents() if hasattr(svc, "list_documents") else []
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    from collections import Counter
    collisions = []
    total = 0
    for d in docs:
        rel = d.get("path") or ""
        if not rel.endswith(".md"):
            continue
        try:
            doc = svc.get_document(rel)
        except Exception:
            continue
        if doc is None:
            continue
        names = []
        for kp in (getattr(doc, "knowledge_points", None) or []):
            name = getattr(kp, "name", None) or getattr(kp, "id", "")
            names.append(name)
            total += 1
        c = Counter(names)
        for nm, n in c.items():
            if n > 1:
                collisions.append({"file": rel, "name": nm, "count": n})
    elapsed = t0() - start
    return {
        "elapsed_ms": round(elapsed * 1000, 1),
        "total_kp": total,
        "collision_groups": len(collisions),
        "collision_kp_total": sum(c["count"] for c in collisions),
        "risk_ratio": round(sum(c["count"] for c in collisions) / total, 4) if total else None,
        "top": sorted(collisions, key=lambda x: -x["count"])[:5],
    }


def main() -> int:
    print("=" * 78)
    print("四门禁可执行性实测")
    print("=" * 78)
    print(f"KB_REAL exists: {os.path.isdir(KB_REAL)}  ({KB_REAL})")
    print(f"KB_COPY exists: {os.path.isdir(KB_COPY)}  ({KB_COPY})")
    print(f"snapshot exists: {os.path.exists(SNAPSHOT)}")
    print()

    # 选可用 KB
    kb = KB_COPY if os.path.isdir(KB_COPY) else KB_REAL
    print(f"用 KB: {kb}")
    print()

    out = {"kb": kb, "snapshot": SNAPSHOT}

    # ── M4 ──
    print("── M4 锚点健康 ──")
    v = run_validate_kb(kb)
    pv = parse_validate(v["text"])
    print(f"  validate_kb 耗时: {v['elapsed_ms']} ms")
    print(f"  输出: docs={pv['docs_checked']} errors={pv['errors']} warnings={pv['warnings']}")
    print(f"  错误码分布: {pv['codes']}")
    print(f"  受影响 KP 数: {pv['affected_kp_count']}  样例={pv['affected_kp_sample']}")
    out["M4_validate_kb"] = {**pv, "elapsed_ms": v["elapsed_ms"]}

    # 逐 KP 健康（M4 真正需要的）
    print("  逐 KP 健康探测（需要 DocumentService）:")
    kh = probe_kp_health(kb)
    if "error" in kh:
        print(f"    ❌ 失败: {kh['error']}")
    else:
        print(f"    耗时 {kh['elapsed_ms']} ms  docs={kh['docs_parsed']} KP={kh['total_kp']}")
        print(f"    range_ok=False: {kh['range_ok_false']}  反转: {kh['inverted']}  "
              f"span=0: {kh['span_zero']}  snippet缺失: {kh['snippet_missing']}")
    out["M4_kp_health"] = kh
    print()

    # ── M2 ──
    print("── M2 同名碰撞 ──")
    m2 = probe_m2_collision(kb)
    if "error" in m2:
        print(f"  ❌ 失败: {m2['error']}")
    else:
        print(f"  耗时 {m2['elapsed_ms']} ms  KP={m2['total_kp']}")
        print(f"  碰撞组={m2['collision_groups']}  涉及KP={m2['collision_kp_total']}  "
              f"风险比={m2['risk_ratio']}")
        if m2["top"]:
            print(f"  最大碰撞: {m2['top'][0]}")
    out["M2_collision"] = m2
    print()

    # ── M5（需要两次快照）──
    print("── M5 陈旧 ──")
    print("  需要：两次快照的 identity 差")
    print(f"  现有快照: {os.path.basename(SNAPSHOT)} (taken_at 见下)")
    if os.path.exists(SNAPSHOT):
        snap = json.load(open(SNAPSHOT, encoding="utf-8"))
        print(f"  taken_at = {snap['taken_at']}")
        tgt = snap["kbs"].get("数字通信原理")
        if tgt:
            print(f"  快照含 md={len(tgt['md'])} sidecar={len(tgt['sidecars'])} 的 sha256")
            # 对比当前实际
            cur = {}
            base = KB_REAL
            if os.path.isdir(base):
                for dp, dn, fn in os.walk(base):
                    dn[:] = [d for d in dn if d not in (".git", "__pycache__")]
                    for f in fn:
                        if f.endswith(".md"):
                            p = os.path.join(dp, f)
                            rel = os.path.relpath(p, base).replace("\\", "/")
                            cur[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
            diff = []
            for it in tgt["md"]:
                p = it["path"]
                if p not in cur:
                    diff.append((p, "MISSING"))
                elif cur[p] != it["sha256"]:
                    diff.append((p, "CHANGED"))
            print(f"  当前 md 数={len(cur)}  与快照不一致={len(diff)}")
            if diff:
                print(f"    前 5: {diff[:5]}")
            out["M5_snapshot_diff"] = {"snapshot_at": snap["taken_at"],
                                       "md_in_snapshot": len(tgt["md"]),
                                       "md_now": len(cur),
                                       "diff_count": len(diff),
                                       "diff_sample": diff[:5]}
    print()

    # ── M12 ──
    print("── M12 Δhit ──")
    print("  需要：索引上线前后的【真实 LLM 调用】cache_read/cache_miss")
    print("  ⇒ 离线不可算；必须跑真实会话 × 2（上线前/后）")
    print("  现有可用的基线：phase3-session-snapshot.jsonl（21 轮，命中率 94.72%）")
    print("  缺失：索引上线后的会话")
    out["M12"] = {
        "can_run_offline": False,
        "needs": "两次真实 LLM 会话（索引前/后），每次 ≥5 轮",
        "baseline_available": "phase3-session-snapshot.jsonl（21 轮，hit=94.72%）",
        "missing": "索引上线后的会话数据",
    }
    print()

    blob = json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2)
    out_path = os.path.join(REPO, "artifacts", "agent", "verify", "debate", "kg-retrieval",
                            "round2", "gate-probe.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(blob + "\n")
    print(f"wrote: {out_path}")
    print(f"sha256: {hashlib.sha256(blob.encode()).hexdigest()[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
