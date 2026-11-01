"""验证 width=4096 下 sidecar save 的幂等性 + 语义等价（G5b-3 口径 a/b）。"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

FROZEN = REPO / "artifacts" / "agent" / "verify" / "debate" / "kg-retrieval" / "round2" / "frozen" / "数字通信原理" / ".memoria" / "sidecars"


def _summarize(data: dict | None) -> list:
    if not data:
        return []
    out = []
    for k in data.get("knowledge_points") or []:
        if not isinstance(k, dict):
            continue
        r = k.get("range") or {}
        out.append((
            k.get("id"),
            (r.get("start") or {}).get("line_hint"),
            (r.get("end") or {}).get("line_hint"),
        ))
    # edges summary
    edges = []
    for e in data.get("edges") or []:
        if isinstance(e, dict):
            edges.append((e.get("type"), e.get("source_id"), tuple(e.get("targets") or [])))
    return [out, sorted(edges, key=str)]


def main() -> int:
    from memoria.storage.sidecar import load_sidecar, save_sidecar

    sidecars = sorted(FROZEN.rglob("*.yaml"))
    idem_ok = 0
    sema_ok = 0
    idem_fail = []
    sema_fail = []

    for sc in sidecars:
        with tempfile.TemporaryDirectory(prefix="g5-idem-") as td:
            tmp = Path(td) / "s.yaml"
            shutil.copy2(sc, tmp)
            orig_data = load_sidecar(tmp)
            orig_summ = _summarize(orig_data)

            save_sidecar(tmp, orig_data)              # 第一次
            b1 = tmp.read_bytes()
            d2 = load_sidecar(tmp)
            save_sidecar(tmp, d2)                      # 第二次
            b2 = tmp.read_bytes()

            # 幂等：两次 save 字节相等
            if b1 == b2:
                idem_ok += 1
            else:
                idem_fail.append(sc.name)

            # 语义等价：第二次 save 后 load 的 id/hints/edges 与原始相等
            if _summarize(d2) == orig_summ:
                sema_ok += 1
            else:
                sema_fail.append(sc.name)

    print("=== 验证：语义等价 + 幂等（width=4096）===")
    print(f"  幂等（save 两次字节相等）: {idem_ok}/{len(sidecars)}")
    if idem_fail:
        for n in idem_fail:
            print(f"    ✗ {n}")
    print(f"  语义等价（id/hints/edges 全等）: {sema_ok}/{len(sidecars)}")
    if sema_fail:
        for n in sema_fail:
            print(f"    ✗ {n}")

    if idem_ok == len(sidecars) and sema_ok == len(sidecars):
        print("[OK] 幂等 + 语义等价全部通过")
        return 0
    print("[FAIL] 存在不幂等或语义不等")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
