"""B5：I-11 G6 快照/基线门禁（S8-2）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoria.graph.multilevel import g6 as g6_mod
from memoria.graph.multilevel.g6 import G6Store, SnapshotError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "g6"


def _snap() -> dict:
    return json.loads((FIXTURES / "snapshot.json").read_text(encoding="utf-8"))


def test_fixture_is_canonical_and_baseline_matches():
    doc = _snap()
    snap = g6_mod.normalize_g6(doc)
    assert snap.snapshot_id == doc["snapshot_id"]
    baseline = json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))
    assert baseline["snapshot_id"] == snap.snapshot_id


def test_write_immutable_and_replay_2x(tmp_path):
    store = G6Store(tmp_path)
    res = store.write(_snap())
    assert store.path_for(res["snapshot_id"]).exists()
    assert res["bytes"] <= g6_mod.G6_MAX_BYTES
    rep = store.replay(res["snapshot_id"], times=2)
    assert rep["ok"] and rep["runs"] == 2
    with pytest.raises(SnapshotError):
        store.write(_snap())  # 不可变：拒绝覆盖


def test_baseline_requires_decision_and_verifies(tmp_path):
    store = G6Store(tmp_path)
    sid = store.write(_snap())["snapshot_id"]
    with pytest.raises(SnapshotError):
        store.update_baseline(sid, decision_id="")
    store.update_baseline(sid, decision_id="dec-test")
    rep = store.verify_baseline()
    assert rep["ok"] and rep["snapshot_id"] == sid


@pytest.mark.parametrize("mutate", [
    lambda d: {k: v for k, v in d.items() if k != "vm_sha"},
    lambda d: dict(d, extra="x"),
    lambda d: dict(d, data_source_sha="not-sha"),
    lambda d: dict(d, closure_violations=1),
    lambda d: dict(d, behind_violations=1),
    lambda d: dict(d, subset_ok="true"),
    lambda d: dict(d, run_ids=["b", "a", "a"]),
    lambda d: dict(d, rule_histogram={"x": -1}),
])
def test_strict_fields_fail_closed(mutate):
    with pytest.raises(SnapshotError):
        g6_mod.normalize_g6(mutate(_snap()))


def test_tampered_file_is_detected(tmp_path):
    store = G6Store(tmp_path)
    sid = store.write(_snap())["snapshot_id"]
    p = store.path_for(sid)
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["node_count"] = 999
    p.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SnapshotError):
        store.load(sid)


def test_size_limit_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(g6_mod, "G6_MAX_BYTES", 16)
    with pytest.raises(SnapshotError):
        G6Store(tmp_path).write(_snap())


def test_g6_fields_equal_frozen_set():
    assert set(g6_mod.G6_FIELDS) == {
        "g6_version", "data_source_sha", "run_ids", "registry_sha", "vm_sha",
        "frame_ids", "frame_sha", "nav_sha", "rule_histogram", "node_count",
        "edge_count", "subset_ok", "determinism_sha", "closure_violations",
        "behind_violations", "history_signed",
    }
