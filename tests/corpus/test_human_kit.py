#!/usr/bin/env python
"""人类标注执行包（task-371）测试：防泄漏、模板、试标 key、校验器、裁决表、人类 IAA 报告。

原则：测试**不生成任何人类标签**——校验器/裁决/IAA 的“正例”都是合成 fixture（标记为 test fixture），
只证明工具可执行、坏文件必红、机器标签混入必被拒。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "corpus"))

import make_adjudication_sheet  # noqa: E402
import make_iaa_report  # noqa: E402
import validate_human_labels  # noqa: E402

HUMAN_KIT = REPO / "artifacts/corpus/pilot/human-kit"
CHAPTER = REPO / "artifacts/corpus/pilot/source/chapter.txt"
SECTIONS = REPO / "artifacts/corpus/pilot/source/sections.json"
POOL = REPO / "artifacts/corpus/pilot/iaa/edge-candidate-pool.jsonl"
A_KPS = REPO / "artifacts/corpus/pilot/annotations/kps.single.jsonl"
A_EDGES = REPO / "artifacts/corpus/pilot/annotations/edges.single.jsonl"
DOCS = REPO / "docs/design/corpus-seminar/pilot"


# ---------------------------------------------------------------- human-kit 防泄漏
def _jsonl_rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_human_kit_has_no_symlinks():
    for p in HUMAN_KIT.rglob("*"):
        assert not p.is_symlink(), f"human-kit 不得含符号链接: {p}"


def test_human_kit_has_no_a_label_files_or_references():
    names = {p.name for p in HUMAN_KIT.rglob("*")}
    assert not ({"kps.single.jsonl", "edges.single.jsonl"} & names), "human-kit 不得含 A 标签文件"
    for p in HUMAN_KIT.rglob("*"):
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        assert "kps.single" not in text, f"{p} 引用了 A 标签文件"
        assert "edges.single" not in text, f"{p} 引用了 A 标签文件"
        assert "corpus-pilot-builder" not in text, f"{p} 含机器草案标记"
        assert not re.search(r"(?<![-\w])kp-\d{3}", text), f"{p} 含 A 的 KP 编号"
        assert not re.search(r"(?<![-\w])edge-\d{3}", text), f"{p} 含 A 的边编号"


def test_human_kit_templates_are_placeholders_only():
    templates = list(HUMAN_KIT.glob("annotator-*/[!R]*.jsonl"))
    assert len(templates) >= 8, f"模板数量不足: {len(templates)}"
    for path in templates:
        rows = _jsonl_rows(path)
        assert rows and all(r.get("_template") is True for r in rows), f"{path} 必须是纯占位模板"
        assert len(rows) == 1, f"{path} 只能有 1 行 _template"


def test_trial_answer_key_is_coordinator_only_and_consistent():
    key_path = HUMAN_KIT / "coordinator/trial/TRIAL-10-ANSWERKEY.json"
    text_path = HUMAN_KIT / "coordinator/trial/TRIAL-TEXT.txt"
    assert key_path.exists() and text_path.exists()
    assert not (HUMAN_KIT / "annotator-a/TRIAL-10-ANSWERKEY.json").exists()
    assert not (HUMAN_KIT / "annotator-b/TRIAL-10-ANSWERKEY.json").exists()
    text = text_path.read_text(encoding="utf-8")
    key = json.loads(key_path.read_text(encoding="utf-8"))
    assert len(key["span_items"]) == 6 and len(key["pair_items"]) == 4
    for item in key["span_items"]:
        start, end = item["span"]["start"], item["span"]["end"]
        assert 0 <= start < end <= len(text)
        assert text[start:end] == item["quote"]
    assert key["trial_text_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_human_docs_and_time_log_exist():
    for rel in ("HUMAN-ANNOTATION-KIT.md", "ADJUDICATION-SHEET.md", "ANNOTATION-MANUAL.md"):
        assert (DOCS / rel).exists(), f"缺少 {rel}"
    assert (HUMAN_KIT / "START-HERE.md").exists()
    time_log = (HUMAN_KIT / "TIME-LOG.csv").read_text(encoding="utf-8")
    assert time_log.startswith("date,annotator,role,stage,items,minutes,notes")


def test_kit_doc_has_required_sections():
    kit = (DOCS / "HUMAN-ANNOTATION-KIT.md").read_text(encoding="utf-8")
    for token in ("G0", "G8", "培训 20 项", "试标 10 项", "60 候选对",
                  "validate_human_labels.py", "make_adjudication_sheet.py",
                  "make_iaa_report.py", "agent 干跑值", "退回条件", "独立性"):
        assert token in kit, f"KIT 缺内容: {token}"


# ---------------------------------------------------------------- 校验器 fixture
def _fixture(tmp_path: Path) -> dict[str, Path]:
    chapter = ("Alpha is a concept about tides. "
               "Beta is another concept about winds.")
    cut = chapter.index("Beta")
    sections = [{"page_id": "s1", "start": 0, "end": cut},
                {"page_id": "s2", "start": cut, "end": len(chapter)}]
    pool = [{"pair_id": "pair-001", "source": "kp-900", "target": "kp-901"}]
    a_kps = [{"id": "kp-900"}, {"id": "kp-901"}]
    quote1 = "Alpha is a concept about tides."
    quote2 = "Beta is another concept about winds."
    s1 = chapter.index(quote1)
    s2 = chapter.index(quote2)
    kps_rows = [
        {"id": "a-kp-001", "annotator": "annotator-a", "status": "human_annotator_draft",
         "spans": [{"start": s1, "end": s1 + len(quote1)}], "section_key": "s1",
         "concept_type": "concept"},
        {"id": "a-kp-002", "annotator": "annotator-a", "status": "human_annotator_draft",
         "spans": [{"start": s2, "end": s2 + len(quote2)}], "section_key": "s2",
         "concept_type": "term"},
    ]
    pool_rows = [{
        "pair_id": "pair-001", "source": "kp-900", "target": "kp-901",
        "annotator": "annotator-a", "status": "human_annotator_draft",
        "label": "edge", "type": "reference", "direction": "source->target",
        "confidence": "high", "rationale": "explicit textual assertion",
        "assertion_span": {"start": s2, "end": s2 + len(quote2), "quote": quote2,
                           "quote_sha256": hashlib.sha256(quote2.encode()).hexdigest()},
    }]
    paths = {
        "chapter": tmp_path / "chapter.txt",
        "sections": tmp_path / "sections.json",
        "pool": tmp_path / "pool.jsonl",
        "a_kps": tmp_path / "a_kps.jsonl",
        "kps": tmp_path / "kps.a.jsonl",
        "pool_rows": tmp_path / "pool-judgments.a.jsonl",
    }
    paths["chapter"].write_text(chapter, encoding="utf-8", newline="\n")
    paths["sections"].write_text(json.dumps({"sections": sections}, ensure_ascii=False),
                                 encoding="utf-8")
    for name, rows in (("pool", pool), ("a_kps", a_kps), ("kps", kps_rows),
                       ("pool_rows", pool_rows)):
        paths[name].write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                               encoding="utf-8", newline="\n")
    return paths


def _run_validator(paths: dict[str, Path], **kw) -> dict:
    defaults = dict(role="a", min_kps=2, max_kps=2, expected_pool=1)
    defaults.update(kw)
    return validate_human_labels.run(
        defaults["role"], paths["kps"], paths["pool_rows"], paths["chapter"],
        paths["sections"], paths["pool"], paths["a_kps"],
        min_kps=defaults["min_kps"], max_kps=defaults["max_kps"],
        expected_pool=defaults["expected_pool"])


def _write(path: Path, rows: list[dict]) -> None:
    path.unlink(missing_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")


def test_validate_human_labels_valid(tmp_path: Path):
    paths = _fixture(tmp_path)
    report = _run_validator(paths)
    assert report["ok"] is True, report["failed"]
    assert report["counts"]["kp"] == 2 and report["counts"]["pool_judgments"] == 1


@pytest.mark.parametrize("mutation,failed_prefix", [
    ("bounds", "kp.bounds"),
    ("overlap", "kp.no_overlap"),
    ("section_key", "kp.section_key"),
    ("count", "kps.count"),
    ("cross_section", "kp.single_section"),
    ("unknown_pair", "pool.known_pair"),
    ("dup_pair", "pool.pair_unique"),
    ("bad_quote", "pool.assertion_quote"),
    ("bad_sha", "pool.assertion_sha"),
    ("missing_coverage", "pool.coverage"),
    ("no_edge_dirty", "pool.no_edge_clean"),
    ("bad_direction", "pool.direction"),
    ("bad_annotator", "pool.annotator"),
    ("bad_label", "pool.label"),
])
def test_validate_human_labels_bad_files_go_red(tmp_path: Path, mutation: str,
                                               failed_prefix: str):
    paths = _fixture(tmp_path)
    kps = _jsonl_rows(paths["kps"])
    pool_rows = _jsonl_rows(paths["pool_rows"])
    if mutation == "bounds":
        kps[0]["spans"][0]["end"] = 99999
    elif mutation == "overlap":
        kps[1]["spans"][0] = dict(kps[0]["spans"][0])
    elif mutation == "section_key":
        kps[0]["section_key"] = "s2"
    elif mutation == "count":
        _write(paths["kps"], kps[:1])
        kps = _jsonl_rows(paths["kps"])
    elif mutation == "cross_section":
        kps[1]["spans"][0] = {"start": 1, "end": len(paths["chapter"].read_text()) - 1}
    elif mutation == "unknown_pair":
        pool_rows[0]["pair_id"] = "pair-999"
    elif mutation == "dup_pair":
        pool_rows.append(dict(pool_rows[0]))
    elif mutation == "bad_quote":
        pool_rows[0]["assertion_span"]["quote"] = "wrong quote"
    elif mutation == "bad_sha":
        pool_rows[0]["assertion_span"]["quote_sha256"] = "0" * 64
    elif mutation == "missing_coverage":
        pool = [{"pair_id": "pair-001", "source": "kp-900", "target": "kp-901"},
                {"pair_id": "pair-002", "source": "kp-901", "target": "kp-900"}]
        _write(paths["pool"], pool)
    elif mutation == "no_edge_dirty":
        pool_rows[0].update({"label": "no_edge", "type": "contain"})
    elif mutation == "bad_direction":
        pool_rows[0]["direction"] = "sideways"
    elif mutation == "bad_annotator":
        pool_rows[0]["annotator"] = "someone-else"
        kps[0]["annotator"] = "someone-else"
    elif mutation == "bad_label":
        pool_rows[0]["label"] = "maybe"
    _write(paths["kps"], kps)
    _write(paths["pool_rows"], pool_rows)
    report = _run_validator(paths)
    assert report["ok"] is False, f"{mutation} 应失败"
    assert any(f.startswith(failed_prefix) for f in report["failed"]), (
        f"{mutation} 未命中 {failed_prefix}: {report['failed'][:10]}")


def test_validate_human_labels_missing_input_exit_2(tmp_path: Path, capsys):
    code = validate_human_labels.main([
        "--role", "a", "--kps", str(tmp_path / "none.jsonl"),
        "--pool-judgments", str(tmp_path / "none2.jsonl"),
        "--chapter", str(tmp_path / "none3.txt"),
        "--sections", str(tmp_path / "none4.json"),
        "--pool", str(tmp_path / "none5.jsonl"),
        "--a-kps", str(tmp_path / "none6.jsonl")])
    assert code == 2


# ---------------------------------------------------------------- 裁决表
def _human_pair(tmp_path: Path) -> dict[str, Path]:
    chapter = ("Alpha is a concept about tides. "
               "Beta is another concept about winds.")
    cut = chapter.index("Beta")
    sections = [{"page_id": "s1", "start": 0, "end": cut},
                {"page_id": "s2", "start": cut, "end": len(chapter)}]
    quote1 = "Alpha is a concept about tides."
    quote2 = "Beta is another concept about winds."
    s1, s2 = chapter.index(quote1), chapter.index(quote2)
    pool = [{"pair_id": "pair-001", "source": "kp-900", "target": "kp-901"},
            {"pair_id": "pair-002", "source": "kp-901", "target": "kp-900"}]
    kps_a = [
        {"id": "a-kp-001", "annotator": "annotator-a",
         "spans": [{"start": s1, "end": s1 + len(quote1)}], "section_key": "s1",
         "concept_type": "concept"},
        {"id": "a-kp-002", "annotator": "annotator-a",
         "spans": [{"start": s2, "end": s2 + len(quote2)}], "section_key": "s2",
         "concept_type": "term"},
    ]
    kps_b = [
        {"id": "b-kp-001", "annotator": "annotator-b",
         "spans": [{"start": s1, "end": s1 + len(quote1) - 1}], "section_key": "s1",
         "concept_type": "mechanism"},
        {"id": "b-kp-003", "annotator": "annotator-b",
         "spans": [{"start": s2, "end": s2 + len(quote2)}], "section_key": "s2",
         "concept_type": "term"},
    ]
    pool_a = [
        {"pair_id": "pair-001", "annotator": "annotator-a", "label": "edge",
         "type": "reference", "direction": "source->target",
         "source": "kp-900", "target": "kp-901"},
        {"pair_id": "pair-002", "annotator": "annotator-a", "label": "no_edge",
         "source": "kp-901", "target": "kp-900"},
    ]
    pool_b = [
        {"pair_id": "pair-001", "annotator": "annotator-b", "label": "no_edge",
         "source": "kp-900", "target": "kp-901"},
        {"pair_id": "pair-002", "annotator": "annotator-b", "label": "edge",
         "type": "reference", "direction": "source->target",
         "source": "kp-901", "target": "kp-900"},
    ]
    paths = {"chapter": tmp_path / "chapter.txt", "pool": tmp_path / "pool.jsonl",
             "kps_a": tmp_path / "kps.a.jsonl", "kps_b": tmp_path / "kps.b.jsonl",
             "pool_a": tmp_path / "pool.a.jsonl", "pool_b": tmp_path / "pool.b.jsonl"}
    paths["chapter"].write_text(chapter, encoding="utf-8", newline="\n")
    for name, rows in (("pool", pool), ("kps_a", kps_a), ("kps_b", kps_b),
                       ("pool_a", pool_a), ("pool_b", pool_b)):
        _write(paths[name], rows)
    return paths


def test_adjudication_sheet_builds_diffs(tmp_path: Path):
    paths = _human_pair(tmp_path)
    result = make_adjudication_sheet.build(
        paths["kps_a"], paths["kps_b"], paths["pool_a"], paths["pool_b"],
        paths["pool"], paths["chapter"])
    md = result["markdown"]
    assert "ADJUDICATION-SHEET" in md
    assert "span_boundary" in md or "concept_type" in md
    assert "existence" in md
    assert result["kp_stats"]["adjudication_rows"] >= 1
    assert result["edge_stats"]["adjudication_rows"] >= 1


def test_adjudication_sheet_identical_inputs_no_diffs(tmp_path: Path):
    paths = _human_pair(tmp_path)
    result = make_adjudication_sheet.build(
        paths["kps_a"], paths["kps_a"], paths["pool_a"], paths["pool_a"],
        paths["pool"], paths["chapter"])
    assert result["kp_stats"]["adjudication_rows"] == 0
    assert result["edge_stats"]["adjudication_rows"] == 0
    assert "无差异" in result["markdown"]


def test_adjudication_sheet_missing_input_exit_2(tmp_path: Path):
    code = make_adjudication_sheet.main([
        "--kps-a", str(tmp_path / "none.jsonl"),
        "--kps-b", str(tmp_path / "none.jsonl"),
        "--pool-a", str(tmp_path / "none.jsonl"),
        "--pool-b", str(tmp_path / "none.jsonl"),
        "--pool", str(POOL), "--chapter", str(CHAPTER),
        "--out", str(tmp_path / "sheet.md")])
    assert code == 2


# ---------------------------------------------------------------- 人类 IAA 报告
def test_make_iaa_report_missing_data_exit_2(tmp_path: Path):
    code = make_iaa_report.main([
        "--kps-a", str(tmp_path / "none1.jsonl"),
        "--kps-b", str(tmp_path / "none2.jsonl"),
        "--pool-a", str(tmp_path / "none3.jsonl"),
        "--pool-b", str(tmp_path / "none4.jsonl"),
        "--pool", str(POOL), "--sections", str(SECTIONS),
        "--out", str(tmp_path / "report.json")])
    assert code == 2


def test_make_iaa_report_rejects_machine_labels(tmp_path: Path):
    code = make_iaa_report.main([
        "--kps-a", str(A_KPS), "--kps-b", str(A_KPS),
        "--pool-a", str(A_EDGES), "--pool-b", str(A_EDGES),
        "--pool", str(POOL), "--sections", str(SECTIONS),
        "--out", str(tmp_path / "report.json")])
    assert code == 1
    assert not (tmp_path / "report.json").exists()


def test_kit_pipeline_end_to_end_synthetic(tmp_path: Path):
    """端到端：校验 a/b → 裁决表 → 人类 IAA 报告（全部用合成 fixture，不生成真实人类标签）。"""
    paths = _fixture(tmp_path)
    # 生成 role b 的等价 fixture（把 annotator 改成 annotator-b；不改变判定）
    b_kps = _jsonl_rows(paths["kps"])
    for row in b_kps:
        row["annotator"] = "annotator-b"
    b_pool = _jsonl_rows(paths["pool_rows"])
    for row in b_pool:
        row["annotator"] = "annotator-b"
    b_kps_path, b_pool_path = tmp_path / "kps.b.jsonl", tmp_path / "pool.b.jsonl"
    _write(b_kps_path, b_kps)
    _write(b_pool_path, b_pool)
    # G3/G5 校验
    assert _run_validator(paths)["ok"] is True
    assert validate_human_labels.run(
        "b", b_kps_path, b_pool_path, paths["chapter"], paths["sections"],
        paths["pool"], paths["a_kps"], min_kps=2, max_kps=2, expected_pool=1)["ok"] is True
    # G6 裁决表
    sheet = tmp_path / "sheet.md"
    code = make_adjudication_sheet.main([
        "--kps-a", str(paths["kps"]), "--kps-b", str(b_kps_path),
        "--pool-a", str(paths["pool_rows"]), "--pool-b", str(b_pool_path),
        "--pool", str(paths["pool"]), "--chapter", str(paths["chapter"]),
        "--out", str(sheet)])
    assert code == 0 and sheet.exists()
    # G7 人类 IAA 报告
    report_path = tmp_path / "human-iaa-report.json"
    code = make_iaa_report.main([
        "--kps-a", str(paths["kps"]), "--kps-b", str(b_kps_path),
        "--pool-a", str(paths["pool_rows"]), "--pool-b", str(b_pool_path),
        "--pool", str(paths["pool"]), "--sections", str(paths["sections"]),
        "--out", str(report_path)])
    assert code == 0 and report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["annotator_type"] == "human" and report["status"] == "computed"


def test_make_iaa_report_human_fixture_ok(tmp_path: Path):
    chapter = ("Alpha is a concept about tides. "
               "Beta is another concept about winds.")
    cut = chapter.index("Beta")
    sections = [{"page_id": "s1", "start": 0, "end": cut},
                {"page_id": "s2", "start": cut, "end": len(chapter)}]
    quote1 = "Alpha is a concept about tides."
    quote2 = "Beta is another concept about winds."
    s1, s2 = chapter.index(quote1), chapter.index(quote2)
    pool = [{"pair_id": "pair-001", "source": "kp-900", "target": "kp-901"}]
    kps_a = [
        {"id": "a-kp-001", "annotator": "annotator-a",
         "spans": [{"start": s1, "end": s1 + len(quote1)}], "section_key": "s1",
         "concept_type": "concept"},
        {"id": "a-kp-002", "annotator": "annotator-a",
         "spans": [{"start": s2, "end": s2 + len(quote2)}], "section_key": "s2",
         "concept_type": "term"},
    ]
    kps_b = [
        {"id": "b-kp-001", "annotator": "annotator-b",
         "spans": [{"start": s1, "end": s1 + len(quote1)}], "section_key": "s1",
         "concept_type": "concept"},
        {"id": "b-kp-002", "annotator": "annotator-b",
         "spans": [{"start": s2, "end": s2 + len(quote2)}], "section_key": "s2",
         "concept_type": "term"},
    ]
    edge_row = {"pair_id": "pair-001", "source": "kp-900", "target": "kp-901",
                "label": "edge", "type": "reference", "direction": "source->target",
                "confidence": "high", "rationale": "explicit"}
    pool_a = [{**edge_row, "annotator": "annotator-a"}]
    pool_b = [{**edge_row, "annotator": "annotator-b"}]
    paths = {name: tmp_path / name for name in
             ("chapter.txt", "sections.json", "pool.jsonl", "kps.a.jsonl",
              "kps.b.jsonl", "pool.a.jsonl", "pool.b.jsonl", "out.json")}
    paths["chapter.txt"].write_text(chapter, encoding="utf-8", newline="\n")
    paths["sections.json"].write_text(json.dumps({"sections": sections}, ensure_ascii=False),
                                      encoding="utf-8")
    for name, rows in (("pool.jsonl", pool), ("kps.a.jsonl", kps_a),
                       ("kps.b.jsonl", kps_b), ("pool.a.jsonl", pool_a),
                       ("pool.b.jsonl", pool_b)):
        _write(paths[name], rows)
    code = make_iaa_report.main([
        "--kps-a", str(paths["kps.a.jsonl"]), "--kps-b", str(paths["kps.b.jsonl"]),
        "--pool-a", str(paths["pool.a.jsonl"]), "--pool-b", str(paths["pool.b.jsonl"]),
        "--pool", str(paths["pool.jsonl"]), "--sections", str(paths["sections.json"]),
        "--out", str(paths["out.json"])])
    assert code == 0, "人类 fixture 应生成报告"
    report = json.loads(paths["out.json"].read_text(encoding="utf-8"))
    assert report["annotator_type"] == "human"
    assert report["human_iaa"] is True
    assert report["status"] == "computed"
    assert report["kp_span_unitizing_alpha"]["alpha"] is not None
    assert report["provenance"]["annotator_type"] == "human"
