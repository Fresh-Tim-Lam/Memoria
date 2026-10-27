"""R4 锚点稳定性实测：现有 {snippet, line_hint} 锚点的失效场景（task-191).

只读语料，不改任何文件。

测什么（每条都要能出数字）：
  1. snippet 在文档内的**唯一性**：同一 snippet 出现多次时，锚点是否歧义
  2. snippet 的**长度分布**：短 snippet 是歧义主因
  3. **空/极短 snippet**：会不会匹配到海量行
  4. line_hint **漂移鲁棒性**：把文档整体前插 N 行，看 resolve_range 还能否定位
  5. 真实库（数字通信原理）与仓库示例库的对比

用法：
  python artifacts/agent/verify/debate/kg-retrieval/r4_anchor_probe.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "src"))

from memoria.range.locator import resolve_range  # noqa: E402

CORPORA = {
    "AAA_Vocab": REPO / "docs" / "example" / "AAA_Vocab",
    "真库-数字通信原理": Path("D:/AAA_Courses/数字通信原理"),
}


def _iter_sidecars(kb: Path):
    for p in (kb / ".memoria" / "sidecars").rglob("*.yaml"):
        yield p


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ModuleNotFoundError:  # pragma: no cover
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _body_for(kb: Path, sidecar: Path) -> Path | None:
    """由 sidecar 路径反推正文 md 路径（`.memoria/sidecars/<rel>.memoria.yaml`）。"""
    try:
        rel = sidecar.relative_to(kb / ".memoria" / "sidecars")
    except ValueError:
        return None
    name = rel.name
    if name.endswith(".memoria.yaml"):
        name = name[: -len(".memoria.yaml")]
    md = (kb / rel.parent / (name + ".md"))
    return md if md.is_file() else None


def probe_kb(name: str, kb: Path) -> dict:
    out = {
        "corpus": name,
        "kb": str(kb),
        "sidecars": 0,
        "kps": 0,
        "empty_snippet": 0,
        "short_snippet_le8": 0,
        "ambiguous_snippet": 0,      # snippet 在该文档里出现 >1 次
        "hint_mismatch": 0,          # line_hint 行不含 snippet
        "resolve_fail": 0,
        "resolve_ok": 0,
        "snippet_len_hist": Counter(),
        "worst": [],                 # 最坏例子
    }
    for sidecar in _iter_sidecars(kb):
        data = _load_yaml(sidecar)
        kps = data.get("knowledge_points") or []
        if not isinstance(kps, list):
            continue
        out["sidecars"] += 1
        md = _body_for(kb, sidecar)
        if md is None:
            continue
        lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
        norm_lines = [ln.strip() for ln in lines]
        for kp in kps:
            if not isinstance(kp, dict):
                continue
            rng = kp.get("range") or {}
            start = rng.get("start") or {}
            end = rng.get("end") or {}
            s_snip = str(start.get("snippet") or "")
            s_hint = start.get("line_hint")
            out["kps"] += 1

            if not s_snip.strip():
                out["empty_snippet"] += 1
                continue

            L = len(s_snip.strip())
            out["snippet_len_hist"][min(L, 40)] += 1
            if L <= 8:
                out["short_snippet_le8"] += 1

            # 唯一性：该 snippet 在文档中出现几次（子串匹配，与 locator 同口径）
            needle = s_snip.strip()[:80]
            occ = [i for i, ln in enumerate(norm_lines) if needle in ln]
            if len(occ) > 1:
                out["ambiguous_snippet"] += 1
                if len(out["worst"]) < 5:
                    out["worst"].append(
                        {
                            "file": md.name,
                            "kp": kp.get("id"),
                            "kind": "ambiguous",
                            "snippet": needle[:60],
                            "occurrences": len(occ),
                        }
                    )

            # hint 一致性：hint 行是否真的含 snippet
            if isinstance(s_hint, int) and 1 <= s_hint <= len(lines):
                if needle not in norm_lines[s_hint - 1]:
                    out["hint_mismatch"] += 1
                    if len(out["worst"]) < 10:
                        out["worst"].append(
                            {
                                "file": md.name,
                                "kp": kp.get("id"),
                                "kind": "hint_mismatch",
                                "hint": s_hint,
                                "snippet": needle[:60],
                            }
                        )

            # resolve_range 实际结果
            rr = resolve_range(lines, start, end)
            if rr.get("ok"):
                out["resolve_ok"] += 1
            else:
                out["resolve_fail"] += 1
                if len(out["worst"]) < 15:
                    out["worst"].append(
                        {
                            "file": md.name,
                            "kp": kp.get("id"),
                            "kind": "resolve_fail",
                            "error": rr.get("error"),
                            "snippet": needle[:60],
                        }
                    )
    out["snippet_len_hist"] = dict(out["snippet_len_hist"])
    return out


def drift_test(name: str, kb: Path, insert_lines: int = 50) -> dict:
    """漂移鲁棒性：整篇前面插入 N 行，line_hint 全部失效后再 resolve，看还能不能定位。

    这是**模拟"用户在文档开头加了一节"**这个最常见的编辑。
    """
    res = {"corpus": name, "insert": insert_lines, "total": 0, "still_ok": 0, "lost": 0}
    for sidecar in _iter_sidecars(kb):
        data = _load_yaml(sidecar)
        kps = data.get("knowledge_points") or []
        md = _body_for(kb, sidecar)
        if md is None or not isinstance(kps, list):
            continue
        lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
        shifted = ["# 新插入的一节"] + [""] * (insert_lines - 1) + lines
        for kp in kps:
            if not isinstance(kp, dict):
                continue
            rng = kp.get("range") or {}
            res["total"] += 1
            rr = resolve_range(shifted, rng.get("start") or {}, rng.get("end") or {})
            if rr.get("ok"):
                res["still_ok"] += 1
            else:
                res["lost"] += 1
    return res


def main() -> int:
    report = {"corpora": [], "drift": []}
    for name, kb in CORPORA.items():
        if not kb.is_dir():
            report["corpora"].append({"corpus": name, "error": "不可访问"})
            continue
        report["corpora"].append(probe_kb(name, kb))
        report["drift"].append(drift_test(name, kb))

    for c in report["corpora"]:
        if "error" in c:
            print(f"\n=== {c['corpus']}: {c['error']} ===")
            continue
        print(f"\n=== {c['corpus']} ===")
        print(f"  sidecar={c['sidecars']}  KP={c['kps']}")
        print(f"  snippet 空: {c['empty_snippet']}   极短(≤8字符): {c['short_snippet_le8']}")
        print(f"  snippet 在该文档出现>1次(歧义): {c['ambiguous_snippet']}")
        print(f"  line_hint 指向行不含 snippet: {c['hint_mismatch']}")
        print(f"  resolve_range: ok={c['resolve_ok']}  fail={c['resolve_fail']}")

    print("\n=== 漂移测试（前插 50 行后重定位）===")
    for d in report["drift"]:
        print(f"  {d['corpus']}: total={d['total']} still_ok={d['still_ok']} lost={d['lost']}")

    out = REPO / "artifacts/agent/verify/debate/kg-retrieval/r4-anchor-probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
