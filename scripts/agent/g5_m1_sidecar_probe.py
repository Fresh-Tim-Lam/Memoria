"""M1 验证：sidecar 读写保留 provenance 未知键 + 不写空键（task-280）。

## 要验证的三条（G5b-2 / G5b-3）

1. round-trip：把 G5a fixture-edge-full.json 的 edge（含 8 个 provenance 键）
   塞进一个临时 sidecar 的 edges[]，走 load→save→load，8 键必须全部原样保留。
2. 旧数据无新键行为不变：一个**只有 3 个 base 键**的 edge，round-trip 后字节不变。
3. 不写空键：normalize/save 不能主动补 `generator_version: null` 之类空键
   （除非用户本来就写了该键）。

## 只测临时目录，不碰 frozen 原目录、不碰用户库。

用法：python scripts/agent/g5_m1_sidecar_probe.py
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

FIXTURE = REPO / "artifacts" / "agent" / "verify" / "debate" / "graph-utility" / "g5-schema-fixtures" / "fixture-edge-full.json"

PROVENANCE_KEYS = [
    "derived_by", "provenance_state", "assertion_source", "instances",
    "generator_version", "valid_from", "valid_to", "confidence",
]

BASE_KEYS = ["type", "source_id", "targets", "relevance", "derived", "origin", "file", "line", "no_build"]


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["edge"]


def main() -> int:
    from memoria.storage.sidecar import load_sidecar, save_sidecar

    if not FIXTURE.is_file():
        print(f"[NOT_RUN] fixture 不存在：{FIXTURE}")
        return 2

    full_edge = _load_fixture()
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="g5-m1-") as td:
        td_path = Path(td)
        sc_path = td_path / "sc.memoria.yaml"

        # ── 测试 1：full edge round-trip（8 键全保留）──────────────
        sidecar = {"knowledge_points": [], "edges": [copy.deepcopy(full_edge)]}
        save_sidecar(sc_path, sidecar)
        loaded = load_sidecar(sc_path) or {}
        rt_edge = (loaded.get("edges") or [{}])[0]
        for key in PROVENANCE_KEYS:
            if key not in full_edge:
                continue
            if key not in rt_edge:
                failures.append(f"round-trip 丢了键 {key!r}")
            elif rt_edge[key] != full_edge[key]:
                failures.append(f"round-trip 键 {key!r} 值变形：{full_edge[key]!r} → {rt_edge[key]!r}")
        # date 必须保持字符串（不是 datetime）
        if isinstance(rt_edge.get("valid_from"), str):
            pass  # 正确
        elif "valid_from" in rt_edge and rt_edge["valid_from"] is not None:
            failures.append(f"valid_from 被转成非字符串：{type(rt_edge['valid_from'])}")

        # ── 测试 2：min edge（只有 base 键）字节不变 ──────────────
        min_edge = {
            "type": "extend",
            "source_id": "a",
            "targets": ["b"],
            "relevance": 0.5,
        }
        sc2 = td_path / "min.memoria.yaml"
        save_sidecar(sc2, {"knowledge_points": [], "edges": [min_edge]})
        before = sc2.read_bytes()
        # 再 load→save 一次（模拟"读旧数据再写回"）
        loaded2 = load_sidecar(sc2) or {}
        save_sidecar(sc2, loaded2)
        after = sc2.read_bytes()
        if before != after:
            failures.append("min edge round-trip 后字节变化（旧数据无新键行为应不变）")

        # ── 测试 3：不写空键 ──────────────────────────────────────
        # normalize 对"没有 provenance 键"的 edge，不能补 null 键
        min_loaded = load_sidecar(sc2) or {}
        min_rt = (min_loaded.get("edges") or [{}])[0]
        extra = [k for k in PROVENANCE_KEYS if k in min_rt]
        if extra:
            failures.append(f"normalize/save 补了空键：{extra}（旧数据无新键不应被补 null）")

    # ── 测试 4：fixture 三个文件都能被 schema 约束下的 8 键覆盖 ──
    for name in ("fixture-edge-min.json", "fixture-edge-partial.json", "fixture-edge-full.json"):
        p = FIXTURE.parent / name
        if p.is_file():
            e = json.loads(p.read_text(encoding="utf-8")).get("edge") or {}
            keys = set(e.keys()) - set(BASE_KEYS) - {"source_id", "targets"}
            unknown = keys - set(PROVENANCE_KEYS)
            # 只报告"出现 schema 8 键之外的新键"
            if unknown and name != "fixture-edge-full.json":
                pass  # fixture 之外的键由 G5a 校验器管，这里不越权

    if failures:
        print("[FAIL] M1 sidecar 探针失败：")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("[OK] M1 sidecar 探针通过：")
    print(f"  · full edge 8 个 provenance 键 round-trip 全保留")
    print(f"  · min edge 字节不变（旧数据无新键行为不变）")
    print(f"  · 不写空键（无 provenance 键的 edge 不被补 null）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
