"""B5：G7 agent 指标 / G-G7 门禁（S8-6）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoria.graph.multilevel import g6 as g6_mod
from memoria.graph.multilevel.g6 import G6Store, G7Store, SnapshotError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
G7_FIX = FIXTURES / "g7" / "envelope.json"
G6_FIX = FIXTURES / "g6" / "snapshot.json"


def _g7() -> dict:
    return json.loads(G7_FIX.read_text(encoding="utf-8"))


def _g6() -> dict:
    return json.loads(G6_FIX.read_text(encoding="utf-8"))


def _stores(tmp_path):
    g6 = G6Store(tmp_path)
    doc = _g6()
    g6.write(doc)
    g6.update_baseline(doc["snapshot_id"], decision_id="dec-test")
    return g6, G7Store(tmp_path)


def test_fixture_passes_gate(tmp_path):
    g6s, g7s = _stores(tmp_path)
    rep = g7s.assert_g_g7(_g7(), g6=g6s)
    assert rep["ok"] and rep["g_g7"] == {"write_attempts": 0, "read_only_ratio": 1.0}


def test_g7_2x_hash_is_stable(tmp_path):
    _, g7s = _stores(tmp_path)
    a = g6_mod.normalize_g7(_g7())
    b = g6_mod.normalize_g7(_g7())
    assert a.snapshot_id == b.snapshot_id


def test_write_and_immutability(tmp_path):
    _, g7s = _stores(tmp_path)
    res = g7s.write(_g7())
    assert g7s.path_for(res["snapshot_id"]).exists()
    with pytest.raises(SnapshotError):
        g7s.write(_g7())


@pytest.mark.parametrize("mutate", [
    lambda d: dict(d, write_attempts=1),
    lambda d: dict(d, read_only_ratio=0.9),
    lambda d: dict(d, run_ids=["run_not_in_g6"]),
    lambda d: dict(d, frame_ids=["frame_not_in_g6"]),
])
def test_gate_fail_closed(tmp_path, mutate):
    g6s, g7s = _stores(tmp_path)
    with pytest.raises(SnapshotError):
        g7s.assert_g_g7(mutate(_g7()), g6=g6s)


@pytest.mark.parametrize("mutate", [
    lambda d: {k: v for k, v in d.items() if k != "tokens"},
    lambda d: dict(d, extra="x"),
    lambda d: dict(d, read_only_ratio=1.1),
    lambda d: dict(d, body="正文"),
    lambda d: dict(d, excerpt="x"),
])
def test_schema_fail_closed(mutate):
    with pytest.raises(SnapshotError):
        g6_mod.normalize_g7(mutate(_g7()))


def test_negative_self_test_cli():
    """门禁负向自证：故意破坏 P0 必须红；脚本自身 exit 0 仅当全部负例被捕获。"""
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        [sys.executable, str(repo / "scripts" / "benchmark" / "graph" / "g7_snapshot.py"),
         "--negative-self-test"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] and all(c["ok"] for c in out["cases"])
