"""C0a：unitizing α 单测（span/边界/重叠/缺失/样本量；合成 fixture 红/绿）。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "verify" / "corpus"))

from unitizing_alpha import UnitizingError, unitizing_alpha  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _perfect():
    a = [{"start": 0, "end": 4, "label": "definition"},
         {"start": 5, "end": 9, "label": "claim"},
         {"start": 10, "end": 15, "label": "example"}]
    return [a, [dict(x) for x in a]]


def test_perfect_agreement_green():
    r = unitizing_alpha(_perfect())
    assert r["alpha"] == 1.0
    assert r["observed_disagreement"] == 0.0
    assert r["expected_disagreement"] > 0
    assert r["boundary_f1"] == 1.0


def test_label_disagreement_red():
    anns = _perfect()
    for s in anns[1]:
        s["label"] = {"definition": "example", "claim": "claim", "example": "definition"}[s["label"]]
    r = unitizing_alpha(anns)
    assert r["alpha"] is not None and r["alpha"] < 0.67
    assert r["observed_disagreement"] > 0


def test_boundary_shift_lowers_agreement():
    a = _perfect()[0]
    b = [dict(s) for s in a]
    b[1]["start"] = 6
    b[1]["end"] = 9
    r = unitizing_alpha([a, b])
    # unitizing α 比较区间标签；边界错位由 boundary_f1 反映
    assert r["boundary_f1"] < 1.0
    assert r["alpha"] is not None


def test_missing_annotation_is_explicit_not_fake_green():
    anns = _perfect()
    anns[1] = []
    r = unitizing_alpha(anns)
    assert r["alpha"] is None
    assert r["note"] == "insufficient_pairs"
    assert r["missing_segments"] > 0


def test_sample_size_and_overlap_fail_closed():
    with pytest.raises(UnitizingError):
        unitizing_alpha([_perfect()[0]])
    with pytest.raises(UnitizingError):
        unitizing_alpha([[{"start": 0, "end": 5, "label": "a"},
                          {"start": 3, "end": 8, "label": "b"}],
                         _perfect()[0]])
    with pytest.raises(UnitizingError):
        unitizing_alpha([[], []])


def test_cli_self_test_green_and_writes_json(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "verify" / "corpus" / "unitizing_alpha.py"),
                        "--self-test"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert out["perfect"]["alpha"] == 1.0
    assert out["disagreement"]["alpha"] < 0.67

    request = tmp_path / "ann.json"
    request.write_text(json.dumps({"annotations": _perfect()}), encoding="utf-8")
    dest = tmp_path / "alpha.json"
    r2 = subprocess.run([sys.executable, str(REPO / "scripts" / "verify" / "corpus" / "unitizing_alpha.py"),
                         "--input", str(request), "--out", str(dest)],
                        capture_output=True, text=True, encoding="utf-8")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert dest.is_file()
    assert json.loads(dest.read_text(encoding="utf-8"))["alpha"] == 1.0
