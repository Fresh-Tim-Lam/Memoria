#!/usr/bin/env python
"""task-370 P0 修订的回归测试：手册 v1.1 防泄漏/规则完备 + IAA 运行器有向池一致率。

只测“规则与工具”，不产生/不伪造任何 IAA 数值：
- 手册：不得含 A 的 unitization（kp-/edge- 编号）；P/N/B 与三类型正负边界例计数；
  concept_type 判定表 + 10 项试标；P30 类“引语必须在 span 内”规则；路径协议统一。
- 运行器：有向池一致率能识别方向反转（旧无向统计会吞掉）；tuple 方向归一化；
  type raw agreement + κ 退化标记；CLI 默认路径指向 annotations/annotator-b/。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "corpus"))

import iaa_runner  # noqa: E402

MANUAL = REPO / "docs/design/corpus-seminar/pilot/ANNOTATION-MANUAL.md"
REVISION = REPO / "docs/design/corpus-seminar/pilot/MANUAL-REVISION.md"
PLAN = REPO / "docs/design/corpus-seminar/pilot/PILOT-PLAN.md"
IAA_README = REPO / "artifacts/corpus/pilot/iaa/README.md"
IAA_DIR = REPO / "artifacts/corpus/pilot/iaa"
TEMPLATE_DIR = IAA_DIR / "annotator-b"


@pytest.fixture(scope="module")
def manual() -> str:
    return MANUAL.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 手册 v1.1
def test_manual_is_v11(manual: str):
    assert "v1.1" in manual
    assert "单标注草案" in manual


def test_manual_has_no_a_unitization_leak(manual: str):
    """P0-1：手册不得含 A 的 KP/边编号（kp-001 / edge-001）或旧 §1.1 逐条答案。

    注意：B 自己的 id 格式 `b-kp-001` 不算泄漏（负向 lookbehind 排除）。
    """
    assert not re.search(r"(?<![-\w])kp-\d{3}", manual), "手册泄漏了 A 的 KP 编号"
    assert not re.search(r"(?<![-\w])edge-\d{3}", manual), "手册泄漏了 A 的边编号"
    assert "全部来自本包 50 KP" not in manual
    assert "P1 `kp-" not in manual
    assert "P30 demand-pull" not in manual  # 旧 P30 逐条说明必须删除


def test_manual_example_counts(manual: str):
    assert len(re.findall(r"^- P\d+", manual, re.M)) >= 30
    assert len(re.findall(r"^- N\d+", manual, re.M)) >= 30
    assert len(re.findall(r"^- B\d+", manual, re.M)) >= 20


def test_manual_s0_type_definitions_and_examples(manual: str):
    for key in ("contain", "reference", "extend"):
        assert key in manual
    for token in ("整体-部分", "度量-表示", "因果-结果", "决策树", "操作定义"):
        assert token in manual, f"缺少 {token}"
    # 每类 ≥5 正例 / ≥5 负例 / ≥3 边界例
    for type_name, marker in (("contain", "T-CONTAIN"), ("reference", "T-REFERENCE"),
                              ("extend", "T-EXTEND")):
        pos = len(re.findall(rf"^- {marker}-P\d+", manual, re.M))
        neg = len(re.findall(rf"^- {marker}-N\d+", manual, re.M))
        bnd = len(re.findall(rf"^- {marker}-B\d+", manual, re.M))
        assert pos >= 5, f"{type_name} 正例不足: {pos}"
        assert neg >= 5, f"{type_name} 负例不足: {neg}"
        assert bnd >= 3, f"{type_name} 边界例不足: {bnd}"


def test_manual_assertion_evidence_and_direction_rules(manual: str):
    for token in ("断言 span", "一步推理", "high", "medium", "co-mention", "共现",
                  "direction", "both", "target->source", "Summary", "Key Terms",
                  "表格", "佐证"):
        assert token in manual, f"缺少规则 token: {token}"


def test_manual_p30_style_self_consistency_rule(manual: str):
    """P0-3：修 P30 类矛盾——引语必须在 span 内；禁止“2 句 + 引语”却引语在更后句。"""
    assert "引语必须落在" in manual
    assert "R3" in manual
    # 旧 P30 的逐条矛盾说明必须删除；规则本身可以以“禁止写法”的形式出现。
    assert "P30 demand-pull" not in manual
    assert "不允许写" in manual and "2 句 + 引语" in manual
    assert "定义句" in manual and "机制句" in manual


def test_manual_concept_type_table_and_trial(manual: str):
    for token in ("concept", "term", "mechanism", "procedure", "formula", "example",
                  "判定顺序", "type_uncertain", "raw agreement", "退化"):
        assert token in manual, f"缺少 concept_type token: {token}"
    assert len(re.findall(r"^- CT\d+", manual, re.M)) == 10


def test_revision_doc_exists_and_covers_p0():
    assert REVISION.exists(), "缺少 MANUAL-REVISION.md"
    text = REVISION.read_text(encoding="utf-8")
    for pid in ("P0-1", "P0-2", "P0-3", "P0-4", "P0-5", "P0-6", "P0-7"):
        assert pid in text, f"修订记录缺 {pid}"
    assert "剩余 P1" in text or "P1" in text
    assert "不伪造" in text or "未伪造" in text


def test_plan_updated_to_v11():
    text = PLAN.read_text(encoding="utf-8")
    assert "v1.1" in text
    assert "U-10" in text and "U-11" in text


# ---------------------------------------------------------------- 路径协议
def test_iaa_readme_path_protocol_unified():
    text = IAA_README.read_text(encoding="utf-8")
    assert "annotations/annotator-b/" in text
    assert "kps.annotator-b.jsonl" in text
    assert "pool-judgments.annotator-b.jsonl" in text
    assert "已废弃" in text  # 旧路径明确废弃
    assert "kps-second-annotator.jsonl" in text  # 仅在“已废弃”说明中出现
    assert "复制为 `kps-second-annotator.jsonl`" not in text, "仍在指示复制旧模板"


def test_canonical_templates_exist_and_parse():
    kps = TEMPLATE_DIR / "kps.annotator-b.template.jsonl"
    pool = TEMPLATE_DIR / "pool-judgments.annotator-b.template.jsonl"
    assert kps.exists() and pool.exists()
    kps_rows = [json.loads(x) for x in kps.read_text(encoding="utf-8").splitlines() if x.strip()]
    pool_rows = [json.loads(x) for x in pool.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert kps_rows[0]["_template"] is True
    assert pool_rows[0]["_template"] is True
    assert pool_rows[0]["record_schema"]["direction"].startswith("source->target")


def test_iaa_runner_cli_defaults_point_to_annotator_b():
    parser = iaa_runner.build_parser()
    args = parser.parse_args(["report"])
    assert args.kps_b == "artifacts/corpus/pilot/annotations/annotator-b/kps.annotator-b.jsonl"
    assert (args.edges_b ==
            "artifacts/corpus/pilot/annotations/annotator-b/pool-judgments.annotator-b.jsonl")
    assert args.adjudications.endswith("annotator-b/adjudication-log.jsonl")


# ---------------------------------------------------------------- 有向池一致率
def _kps(types: list[str]) -> list[dict]:
    return [{"id": f"kp-{i}", "spans": [{"start": i * 10, "end": i * 10 + 5}],
             "concept_type": t, "section_key": "s"} for i, t in enumerate(types)]


def _edges() -> list[dict]:
    return [{"id": "edge-1", "label": "semantic", "type": "contain",
             "source": "kp-0", "target": "kp-1", "direction": "source->target"}]


def test_directed_pool_agreement_detects_reversal():
    kps_a = _kps(["concept", "concept"])
    kps_b = _kps(["concept", "concept"])
    pool = [{"pair_id": "pair-001", "source": "kp-0", "target": "kp-1"}]
    reversed_b = [{"pair_id": "pair-001", "label": "edge", "type": "contain",
                   "source": "kp-0", "target": "kp-1", "direction": "target->source"}]
    report = iaa_runner.build_report(kps_a, kps_b, _edges(), reversed_b, pool)
    assert report["edge_pool_agreement_kappa"]["direction_reversals"] == ["pair-001"]
    assert report["edge_pool_agreement_kappa"]["observed_agreement"] == 0.0
    assert report["edge_pool_agreement_kappa_undirected"]["observed_agreement"] == 1.0
    assert "directed" in (report["edge_pool_agreement_note"] or "")
    # tuple F1 也应按方向归一化 → 反向 tuple 不等价
    assert report["edge_tuple_f1"]["f1"] == 0.0


def test_directed_tuples_normalization():
    row_t2s = {"type": "reference", "source": "a", "target": "b", "direction": "target->source"}
    assert iaa_runner.directed_tuples(row_t2s) == [("reference", "b", "a", "source->target")]
    row_both = {"type": "extend", "source": "a", "target": "b", "direction": "both"}
    assert sorted(iaa_runner.directed_tuples(row_both)) == [
        ("extend", "a", "b", "source->target"), ("extend", "b", "a", "source->target")]
    row_plain = {"type": "contain", "source": "a", "target": "b"}
    assert iaa_runner.directed_tuples(row_plain) == [("contain", "a", "b", "source->target")]
    assert iaa_runner.directed_tuples({"type": "bogus", "source": "a", "target": "b"}) == []


def test_pool_agreement_ignores_reverse_negatives_under_directed():
    """A 的反向负例（池中 reverse 对）在 undirected 里会误判；directed 下应一致。"""
    kps_a = _kps(["concept", "concept"])
    kps_b = _kps(["concept", "concept"])
    # A 只有 kp-0 -> kp-1；池里给出反向对 kp-1 -> kp-0 作为负例
    pool = [{"pair_id": "pair-001", "source": "kp-1", "target": "kp-0"}]
    b_rows = [{"pair_id": "pair-001", "label": "no_edge", "source": "kp-1", "target": "kp-0"}]
    report = iaa_runner.build_report(kps_a, kps_b, _edges(), b_rows, pool)
    assert report["edge_pool_agreement_kappa"]["observed_agreement"] == 1.0
    assert report["edge_pool_agreement_kappa_undirected"]["observed_agreement"] == 0.0


def test_type_raw_agreement_and_kappa_degenerate():
    kps_a = _kps(["concept"] * 9 + ["term"])
    kps_b = _kps(["concept"] * 10)
    report = iaa_runner.build_report(kps_a, kps_b, [], [], pool=[])
    kappa = report["kp_type_cohen_kappa"]
    assert kappa["kappa"] == 0.0
    assert kappa["raw_agreement"] == 0.9
    assert kappa["degenerate"] is True
    assert "degenerate" in kappa["kappa_note"]
    assert report["kp_type_raw_agreement"]["raw_agreement"] == 0.9


def test_type_uncertain_excluded_from_kappa():
    kps_a = _kps(["concept"] * 9 + ["term"])
    b = _kps(["concept"] * 10)
    b[9]["type_uncertain"] = True
    report = iaa_runner.build_report(kps_a, b, [], [], pool=[])
    kappa = report["kp_type_cohen_kappa"]
    assert kappa["excluded_uncertain"] == 1
    assert kappa["raw_n"] == 10
    assert kappa["n"] == 9
