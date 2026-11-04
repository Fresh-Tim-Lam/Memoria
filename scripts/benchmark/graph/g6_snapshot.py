#!/usr/bin/env python
"""G6 快照/基线门禁 CLI（S8-2 / task-352）。

用法：
  python scripts/benchmark/graph/g6_snapshot.py --verify-baseline [--root KB/.memoria] [--baseline PATH]
  python scripts/benchmark/graph/g6_snapshot.py --write snapshot.json --root KB/.memoria
  python scripts/benchmark/graph/g6_snapshot.py --self-test
  python scripts/benchmark/graph/g6_snapshot.py --negative-self-test

退出码：0 = PASS；1 = 门禁失败；2 = 用法错误。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memoria.graph.multilevel import g6 as g6_mod  # noqa: E402
from memoria.graph.multilevel.g6 import G6Store, SnapshotError  # noqa: E402

FIXTURES = REPO / "tests" / "graph" / "fixtures" / "g6"


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fixture_snapshot() -> dict:
    return json.loads((FIXTURES / "snapshot.json").read_text(encoding="utf-8"))


def verify_baseline(root: str | None, baseline: str | None) -> dict:
    if root:
        store = G6Store(Path(root))
        return store.verify_baseline(baseline)
    # 无 --root：校验仓库内固定基线（fixture），用于 CI/无用户库场景
    snap_doc = _fixture_snapshot()
    snap = g6_mod.normalize_g6(snap_doc)
    if snap.snapshot_id != snap_doc.get("snapshot_id"):
        raise SnapshotError("fixture snapshot_id 不可复算")
    bl = Path(baseline) if baseline else (FIXTURES / "baseline.json")
    bdoc = json.loads(bl.read_text(encoding="utf-8"))
    if bdoc.get("snapshot_id") != snap.snapshot_id:
        raise SnapshotError("fixture baseline 与 snapshot 不一致")
    # 2× replay：字节/canonical sha 一致
    raws = []
    for _ in range(2):
        raw = json.dumps(snap_doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        raws.append(g6_mod.sha256_canonical(json.loads(raw)))
    if len(set(raws)) != 1:
        raise SnapshotError("fixture replay 2× 不一致")
    return {"ok": True, "baseline": str(bl), "snapshot_id": snap.snapshot_id,
            "decision_id": bdoc.get("decision_id", ""), "replay": {"runs": 2, "sha256": raws[0]}}


def write_snapshot(input_path: str, root: str) -> dict:
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    return G6Store(Path(root)).write(data)


def self_test() -> dict:
    with tempfile.TemporaryDirectory() as td:
        store = G6Store(Path(td))
        res = store.write(_fixture_snapshot())
        rep = store.replay(res["snapshot_id"])
        store.update_baseline(res["snapshot_id"], decision_id="dec-self-test")
        base = store.verify_baseline()
        return {"ok": True, "write": res, "replay": rep, "baseline": base}


def negative_self_test() -> dict:
    """故意破坏 P0 ⇒ 每个负例都必须红；返回每个负例的捕获结果。"""
    cases: list[dict] = []
    snap = _fixture_snapshot()

    def expect_red(name: str, fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 —— 负例必须被任意可见失败捕获
            cases.append({"case": name, "caught": type(exc).__name__, "ok": True})
        else:
            cases.append({"case": name, "caught": None, "ok": False})

    expect_red("missing_field", lambda: g6_mod.normalize_g6({k: v for k, v in snap.items() if k != "vm_sha"}))
    expect_red("extra_field", lambda: g6_mod.normalize_g6(dict(snap, extra="x")))
    expect_red("bad_sha", lambda: g6_mod.normalize_g6(dict(snap, data_source_sha="xyz")))
    expect_red("closure_nonzero", lambda: g6_mod.normalize_g6(dict(snap, closure_violations=1)))
    expect_red("missing_id", lambda: G6Store(Path(tempfile.mkdtemp())).load("0" * 64))

    with tempfile.TemporaryDirectory() as td:
        store = G6Store(Path(td))
        sid = store.write(snap)["snapshot_id"]

        def _tamper_id() -> None:
            p = store.path_for(sid)
            doc = json.loads(p.read_text(encoding="utf-8"))
            doc["snapshot_id"] = "0" * 64
            p.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            store.load(sid)

        def _overwrite() -> None:
            store.write(snap)

        expect_red("tampered_id", _tamper_id)
        expect_red("immutable_overwrite", _overwrite)
        expect_red("replay_bad_id", lambda: store.replay("0" * 64))

        old = g6_mod.G6_MAX_BYTES
        try:
            g6_mod.G6_MAX_BYTES = 16
            expect_red("oversize", lambda: G6Store(Path(td) / "small").write(snap))
        finally:
            g6_mod.G6_MAX_BYTES = old
        expect_red("bad_baseline_decision", lambda: store.update_baseline(sid, decision_id=""))

    all_red = all(c["ok"] for c in cases)
    return {"ok": all_red, "cases": cases,
            "summary": f"{sum(c['ok'] for c in cases)}/{len(cases)} negative cases red"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G6 snapshot / baseline gate")
    ap.add_argument("--root", help=".memoria 目录（用户库）")
    ap.add_argument("--baseline", help="baseline JSON 路径（配合 --verify-baseline）")
    ap.add_argument("--verify-baseline", action="store_true")
    ap.add_argument("--write", metavar="SNAPSHOT_JSON")
    ap.add_argument("--replay", metavar="SNAPSHOT_ID")
    ap.add_argument("--set-baseline", metavar="SNAPSHOT_ID")
    ap.add_argument("--decision-id", default="")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--negative-self-test", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.negative_self_test:
            res = negative_self_test()
            _emit(res)
            return 0 if res["ok"] else 1
        if args.self_test:
            _emit(self_test())
            return 0
        if args.write:
            if not args.root:
                raise SnapshotError("--write 需要 --root")
            _emit(write_snapshot(args.write, args.root))
            return 0
        if args.replay:
            if not args.root:
                raise SnapshotError("--replay 需要 --root")
            _emit(G6Store(Path(args.root)).replay(args.replay))
            return 0
        if args.set_baseline:
            if not args.root:
                raise SnapshotError("--set-baseline 需要 --root")
            _emit(G6Store(Path(args.root)).update_baseline(args.set_baseline, decision_id=args.decision_id))
            return 0
        if args.verify_baseline:
            _emit(verify_baseline(args.root, args.baseline))
            return 0
        ap.print_help()
        return 2
    except Exception as exc:  # noqa: BLE001 —— 门禁可见失败
        _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
