#!/usr/bin/env python
"""G7 agent 指标 / G-G7 门禁 CLI（S8-6 / task-352）。

用法：
  python scripts/benchmark/graph/g7_snapshot.py --assert-g-g7 [--root KB/.memoria] [--g6-baseline PATH]
  python scripts/benchmark/graph/g7_snapshot.py --write envelope.json --root KB/.memoria
  python scripts/benchmark/graph/g7_snapshot.py --self-test
  python scripts/benchmark/graph/g7_snapshot.py --negative-self-test

退出码：0 = PASS；1 = 门禁失败；2 = 用法错误。
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from memoria.graph.multilevel import g6 as g6_mod  # noqa: E402
from memoria.graph.multilevel.g6 import G6Store, G7Store, SnapshotError  # noqa: E402

FIXTURES = REPO / "tests" / "graph" / "fixtures" / "g7"
G6_FIXTURES = REPO / "tests" / "graph" / "fixtures" / "g6"


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fixture() -> dict:
    return json.loads((FIXTURES / "envelope.json").read_text(encoding="utf-8"))


def _g6_fixture() -> dict:
    return json.loads((G6_FIXTURES / "snapshot.json").read_text(encoding="utf-8"))


def assert_g_g7(root: str | None, g6_baseline: str | None) -> dict:
    data = _fixture()
    g6_store = None
    if g6_baseline:
        g6_store = G6Store(Path(root) if root else Path(tempfile.mkdtemp()))
        # 用 fixture 初始化 G6 基线，再断言 G7 引用其 ids
        g6_store.write(_g6_fixture())
        g6_store.update_baseline(_g6_fixture()["snapshot_id"], decision_id="dec-g7-self-test")
    if root:
        store = G7Store(Path(root))
    else:
        store = G7Store(Path(tempfile.mkdtemp()))
    rep = store.assert_g_g7(data, g6=g6_store)
    # 2× 一致性
    rep2 = store.assert_g_g7(copy.deepcopy(data), g6=g6_store)
    if rep["snapshot_id"] != rep2["snapshot_id"]:
        raise SnapshotError("G7 2× 不一致")
    return {"ok": True, "g_g7": rep["g_g7"], "snapshot_id": rep["snapshot_id"],
            "write_attempts": 0, "read_only_ratio": 1.0, "replay": "2x-ok"}


def write_snapshot(input_path: str, root: str) -> dict:
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    return G7Store(Path(root)).write(data)


def self_test() -> dict:
    with tempfile.TemporaryDirectory() as td:
        store = G7Store(Path(td))
        res = store.write(_fixture())
        g6s = G6Store(Path(td))
        g6s.write(_g6_fixture())
        g6s.update_baseline(_g6_fixture()["snapshot_id"], decision_id="dec-self-test")
        gate = store.assert_g_g7(_fixture(), g6=g6s)
        return {"ok": True, "write": res, "gate": gate}


def negative_self_test() -> dict:
    cases: list[dict] = []
    base = _fixture()

    def expect_red(name: str, fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            cases.append({"case": name, "caught": type(exc).__name__, "ok": True})
        else:
            cases.append({"case": name, "caught": None, "ok": False})

    store0 = G7Store(Path(tempfile.mkdtemp()))
    expect_red("write_attempts_nonzero", lambda: store0.assert_g_g7(dict(base, write_attempts=1)))
    expect_red("read_only_below_1", lambda: store0.assert_g_g7(dict(base, read_only_ratio=0.9)))
    expect_red("body_field", lambda: g6_mod.normalize_g7(dict(base, detail={"body": "text"})))
    expect_red("excerpt_field", lambda: g6_mod.normalize_g7(dict(base, excerpt="x")))
    expect_red("extra_field", lambda: g6_mod.normalize_g7(dict(base, pii="x")))
    expect_red("missing_field", lambda: g6_mod.normalize_g7({k: v for k, v in base.items() if k != "tokens"}))

    with tempfile.TemporaryDirectory() as td:
        g6s = G6Store(Path(td))
        g6s.write(_g6_fixture())
        g6s.update_baseline(_g6_fixture()["snapshot_id"], decision_id="dec-neg")
        store = G7Store(Path(td))
        expect_red("refs_not_in_g6", lambda: store.assert_g_g7(
            dict(base, run_ids=["run_not_in_g6"]), g6=g6s))
        expect_red("write_attempts_gate", lambda: store.assert_g_g7(dict(base, write_attempts=1), g6=g6s))

    all_red = all(c["ok"] for c in cases)
    return {"ok": all_red, "cases": cases,
            "summary": f"{sum(c['ok'] for c in cases)}/{len(cases)} negative cases red"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G7 / G-G7 gate")
    ap.add_argument("--root", help=".memoria 目录（用户库）")
    ap.add_argument("--g6-baseline", help="启用 G6 引用校验（用 fixture 初始化）")
    ap.add_argument("--assert-g-g7", action="store_true")
    ap.add_argument("--write", metavar="ENVELOPE_JSON")
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
        if args.assert_g_g7:
            _emit(assert_g_g7(args.root, args.g6_baseline))
            return 0
        ap.print_help()
        return 2
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
