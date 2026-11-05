#!/usr/bin/env python
"""pilot 语料包测试：正向（真实包通过）+ 负向（破坏后必须失败）+ IAA 工具单测 + 2× 复现。

原则：**测试只证明校验器有效**；不产生任何伪造的 IAA/许可数据。
- 正向：仓库内真实包 `validate_pilot.run` 全绿（含 2× 可复现）；
- 负向：复制真实包到 tmp，逐项破坏 schema/span/证据/许可/Tier/数量/负例/query，必须 fail；
- IAA：`iaa_runner` 的 κ / tuple-F1 / IoU 匹配 / self-test / insufficient 状态；
- kit：IAA 工具包固定 seed，两次生成逐字节一致。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "corpus"))

import iaa_runner  # noqa: E402
import make_iaa_kit  # noqa: E402
import validate_pilot  # noqa: E402

PATHS = [
    "artifacts/corpus/pilot/source",
    "artifacts/corpus/pilot/annotations",
    "artifacts/corpus/pilot/iaa",
    "docs/design/corpus-seminar/pilot",
]
KPS = "artifacts/corpus/pilot/annotations/kps.single.jsonl"
EDGES = "artifacts/corpus/pilot/annotations/edges.single.jsonl"
NEGS = "artifacts/corpus/pilot/annotations/edges.negative.single.jsonl"
PAGES = "artifacts/corpus/pilot/source/pages.json"
MANUAL = "docs/design/corpus-seminar/pilot/ANNOTATION-MANUAL.md"
QUERIES = "docs/design/corpus-seminar/pilot/queries.json"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.unlink(missing_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")


@pytest.fixture(scope="module")
def base_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("pilot_base")
    for rel in PATHS:
        shutil.copytree(REPO / rel, root / rel)
    return root


@pytest.fixture()
def root(base_root: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "pkg"
    for rel in PATHS:
        shutil.copytree(base_root / rel, dst / rel)
    return dst


def _fails(root: Path, prefix: str) -> list[str]:
    report = validate_pilot.run(root, check_reproducibility=False)
    assert report["ok"] is False, "破坏后校验仍然通过（校验器失效）"
    return [f for f in report["failed"] if f.startswith(prefix) or prefix in f]


# ---------------------------------------------------------------- 正向
def test_real_package_validates_without_repro():
    report = validate_pilot.run(REPO, check_reproducibility=False)
    assert report["ok"] is True, f"失败项: {report['failed']}"
    assert report["counts"]["kp"] == 50
    assert report["counts"]["edges"] == 30
    assert report["check_count"] > 1500


def test_real_package_is_2x_reproducible():
    report = validate_pilot.run(REPO, check_reproducibility=True)
    failed = [f for f in report["failed"] if f.startswith("repro")]
    assert not failed, f"2× 复现失败: {failed}"
    assert report["ok"] is True, f"失败项: {report['failed']}"


# ---------------------------------------------------------------- 负向：schema/span/证据
def test_span_out_of_bounds_fails(root: Path):
    rows = _read_jsonl(root / KPS)
    rows[0]["spans"][0]["end"] = 10 ** 9
    _write_jsonl(root / KPS, rows)
    assert _fails(root, "kp.span_bounds")


def test_overlapping_kps_fail(root: Path):
    rows = _read_jsonl(root / KPS)
    rows[1]["spans"][0] = dict(rows[0]["spans"][0])
    _write_jsonl(root / KPS, rows)
    assert _fails(root, "kp.overlap")


def test_evidence_quote_tamper_fails(root: Path):
    rows = _read_jsonl(root / KPS)
    rows[0]["evidence"][0]["quote"] = rows[0]["evidence"][0]["quote"] + " TAMPERED"
    _write_jsonl(root / KPS, rows)
    assert _fails(root, "kp.evidence_quote")


def test_kp_count_fails(root: Path):
    rows = _read_jsonl(root / KPS)[:-1]
    _write_jsonl(root / KPS, rows)
    assert _fails(root, "kp.count")


def test_fake_iaa_method_fails(root: Path):
    rows = _read_jsonl(root / KPS)
    rows[0]["annotation_method"] = "completed IAA"
    _write_jsonl(root / KPS, rows)
    assert _fails(root, "kp.iaa_honest")


# ---------------------------------------------------------------- 负向：许可/Tier
def test_tier_b_source_fails(root: Path):
    pages = json.loads((root / PAGES).read_text(encoding="utf-8"))
    pages["book"]["license_tier"] = "B"
    (root / PAGES).unlink()
    (root / PAGES).write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _fails(root, "source.tier_a")


def test_spdx_not_tier_a_fails(root: Path):
    pages = json.loads((root / PAGES).read_text(encoding="utf-8"))
    pages["book"]["spdx"] = "CC-BY-NC-SA-4.0"
    (root / PAGES).unlink()
    (root / PAGES).write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert _fails(root, "source.spdx")


# ---------------------------------------------------------------- 负向：边/负例/query
def test_structural_contain_masquerade_fails(root: Path):
    rows = _read_jsonl(root / EDGES)
    for row in rows:
        if row["type"] == "contain":
            row["contain_kind"] = "structural"
            break
    _write_jsonl(root / EDGES, rows)
    assert _fails(root, "edge.semantic_contain")


def test_negative_promoted_to_positive_fails(root: Path):
    negs = _read_jsonl(root / NEGS)
    neg = negs[0]
    rows = _read_jsonl(root / EDGES)
    for row in rows:
        if row["type"] == "contain":
            row["source"] = neg["candidate_source"]
            row["target"] = neg["candidate_target"]
            break
    _write_jsonl(root / EDGES, rows)
    assert _fails(root, "neg.not_in_positive")


def test_query_missing_graph_edge_fails(root: Path):
    doc = json.loads((root / QUERIES).read_text(encoding="utf-8"))
    for q in doc["queries"]:
        if q["query_type"] == "graph":
            q["expected_edge_ids"] = ["edge-does-not-exist"]
            break
    (root / QUERIES).unlink()
    (root / QUERIES).write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8")
    assert _fails(root, "query.expected_edges_exist")


def test_manual_missing_examples_fails(root: Path):
    (root / MANUAL).unlink()
    (root / MANUAL).write_text("# stub manual\n\nonly prose, no examples\n", encoding="utf-8")
    assert _fails(root, "docs.manual_positive") or _fails(root, "docs.manual_negative")


# ---------------------------------------------------------------- IAA 工具单测（合成 fixture，非真实 IAA）
def test_cohen_kappa_units():
    assert iaa_runner.cohen_kappa([("a", "a"), ("b", "b")])["kappa"] == 1.0
    kappa = iaa_runner.cohen_kappa([("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")])
    assert kappa["kappa"] == 0.0
    assert kappa["n"] == 4
    empty = iaa_runner.cohen_kappa([])
    assert empty["kappa"] is None


def test_tuple_set_f1_units():
    gold = {("contain", "kp-a", "kp-b", "source->target"),
            ("reference", "kp-b", "kp-c", "source->target")}
    pred = {("contain", "kp-a", "kp-b", "source->target")}
    res = iaa_runner.tuple_set_f1(gold, pred)
    assert res["tp"] == 1 and res["fp"] == 0 and res["fn"] == 1
    assert res["f1"] == pytest.approx(2 * 1 * 0.5 / 1.5, rel=1e-6)


def test_span_matching_iou():
    gold = [{"id": "a1", "spans": [{"start": 0, "end": 10}], "section_key": "s"}]
    pred = [{"id": "b1", "spans": [{"start": 2, "end": 12}], "section_key": "s"},
            {"id": "b2", "spans": [{"start": 100, "end": 110}], "section_key": "s"}]
    matching = iaa_runner.match_kp_spans(gold, pred)
    assert matching["matched_count"] == 1
    assert matching["pairs"][0]["second_id"] == "b1"
    assert matching["unmatched_second"] == ["b2"]


def test_unitizing_alpha_uses_c0a_script():
    a, b, _, _ = iaa_runner._fixture(True)
    result = iaa_runner.alpha_input(a, b)
    assert result["computed"]["alpha"] == 1.0
    assert result["computed"]["boundary_f1"] == 1.0
    assert len(result["annotations"]) == 2


def test_iaa_runner_self_test():
    res = iaa_runner.self_test()
    assert res["ok"] is True


def test_iaa_report_insufficient_when_no_second_annotator():
    kps = _read_jsonl(REPO / KPS)
    edges = _read_jsonl(REPO / EDGES)
    pool = _read_jsonl(REPO / "artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl")
    report = iaa_runner.build_report(kps, [], edges, [], pool)
    assert report["status"] == "insufficient_second_annotator"
    assert report["kp_span_unitizing_alpha"]["alpha"] is None
    assert report["kp_span_unitizing_alpha"]["note"] == "insufficient_second_annotator"
    assert report["pass"]["kp_span_alpha"] is False


def test_iaa_kit_is_deterministic(tmp_path: Path):
    out1 = tmp_path / "kit1"
    out2 = tmp_path / "kit2"
    m1 = make_iaa_kit.build(REPO / "artifacts/corpus/pilot/annotations", out1)
    m2 = make_iaa_kit.build(REPO / "artifacts/corpus/pilot/annotations", out2)
    assert m1["file_sha256"] == m2["file_sha256"]
    assert m1["pool_size"] == 60
    assert m1["pool_composition"] == {"a_positive_pairs": 30, "a_negative_pairs": 14,
                                      "distractor_pairs": 16}
    lines = _read_jsonl(out1 / "edge-candidate-pool.jsonl")
    assert all(not row["label"] for row in lines), "候选池不得泄漏标签"
