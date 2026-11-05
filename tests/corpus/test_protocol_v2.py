#!/usr/bin/env python
"""Protocol v2（task-373）测试：阶段工作量/人时、spotcheck 包不泄全文、IAA mode 标记、纯 agent 拒绝 human 标记。

全部 fixture 均为合成测试数据（test fixture），**不生成任何人类/agent 正式标签**。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "corpus"))

import make_iaa_report_v2  # noqa: E402
import make_spotcheck_pack  # noqa: E402
import validate_human_labels  # noqa: E402

DOCS = REPO / "docs/design/corpus-seminar/pilot"
PROTOCOL = DOCS / "PILOT-PROTOCOL-V2.md"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- 协议文档 / 人时
def test_protocol_doc_exists_and_has_modes():
    text = PROTOCOL.read_text(encoding="utf-8")
    for token in ("agent_bulk_human_adjudication", "pure_agent", "agent_vs_agent",
                  "human_adjudication_agreement", "human_unvalidated",
                  "not_c8_conclusion", "spotcheck", "G3", "G5", "G6", "G7", "G8"):
        assert token in text, f"protocol v2 缺 {token}"


def test_protocol_human_budget_under_3h():
    text = PROTOCOL.read_text(encoding="utf-8")
    # 机器可读预算标记（测试解析）
    m = re.search(r"HUMAN_BUDGET_MINUTES:\s*total_min=(\d+)\s+total_max=(\d+)", text)
    assert m, "缺 HUMAN_BUDGET_MINUTES 机器可读标记"
    total_min, total_max = int(m.group(1)), int(m.group(2))
    assert total_min > 0 and total_max < 180, f"人类总时 {total_min}–{total_max} 必须 <3h"
    assert total_max <= 120, "protocol v2 声称人类 ≤2h"
    # G3/G5 是机器 bulk（人类 0）
    assert re.search(r"G3=0", text) and re.search(r"G5=0", text)
    assert "0（内容多 → 机器 bulk）" in text or "机器 bulk" in text


def test_old_human_kit_marked_optional():
    kit = (DOCS / "HUMAN-ANNOTATION-KIT.md").read_text(encoding="utf-8")
    assert "可选 full-human" in kit
    assert "默认不再执行" in kit or "默认不做" in kit
    assert "PILOT-PROTOCOL-V2.md" in kit
    ready = (REPO / "artifacts/agent/verify/corpus/pilot/HUMAN-KIT-READY.md").read_text(encoding="utf-8")
    assert "可选" in ready and "PILOT-PROTOCOL-V2.md" in ready


# ---------------------------------------------------------------- spotcheck 包
CHAPTER_TAIL_SENTINEL = "ZZ_SECRET_TAIL_MARKER_9f3a"


def _agent_fixture(tmp_path: Path) -> dict[str, Path]:
    """合成 chapter + 两位 agent 的 KP/池判定（1 个分歧 KP、1 个分歧 pair、若干无分歧）。"""
    def build_chapter() -> tuple[str, list[tuple[int, int]]]:
        quotes = []
        parts = []
        for i in range(9):
            q = f"Concept{i} is defined as a synthetic term for testing."
            start = sum(len(p) + 1 for p in parts)
            parts.append(q)
            quotes.append((start, start + len(q)))
        filler = " ".join(["filler"] * 3000)
        chapter = " ".join(parts) + " " + filler + " " + CHAPTER_TAIL_SENTINEL
        return chapter, quotes

    chapter, quotes = build_chapter()
    chapter_path = tmp_path / "chapter.txt"
    chapter_path.write_text(chapter, encoding="utf-8", newline="\n")
    kps_a, kps_b = [], []
    for i, (start, end) in enumerate(quotes):
        kps_a.append({"id": f"a-kp-{i:03d}", "annotator": "agent-a",
                      "status": "agent_annotator_draft",
                      "spans": [{"start": start, "end": end}], "section_key": "ch1-s1",
                      "concept_type": "concept"})
        end_b = end - 1 if i == 8 else end  # 第 9 个：边界分歧
        kps_b.append({"id": f"b-kp-{i:03d}", "annotator": "agent-b",
                      "status": "agent_annotator_draft",
                      "spans": [{"start": start, "end": end_b}], "section_key": "ch1-s1",
                      "concept_type": "term" if i == 8 else "concept"})
    pool = []
    pool_a, pool_b = [], []
    for i in range(9):
        pair = {"pair_id": f"pair-{i + 1:03d}", "source": f"kp-{i}", "target": f"kp-{(i + 1) % 9}"}
        pool.append(pair)
        if i < 8:
            pool_a.append({**pair, "annotator": "agent-a", "label": "no_edge"})
            pool_b.append({**pair, "annotator": "agent-b", "label": "no_edge"})
        else:
            q_start, q_end = quotes[0]
            pool_a.append({**pair, "annotator": "agent-a", "label": "edge", "type": "reference",
                           "direction": "source->target", "confidence": "high",
                           "rationale": "explicit assertion",
                           "assertion_span": {"start": q_start, "end": q_end,
                                              "quote": chapter[q_start:q_end]}})
            pool_b.append({**pair, "annotator": "agent-b", "label": "no_edge"})
    dirs = {"a": tmp_path / "agent-a", "b": tmp_path / "agent-b"}
    for role, kps, pools in (("a", kps_a, pool_a), ("b", kps_b, pool_b)):
        (dirs[role]).mkdir(parents=True, exist_ok=True)
        _write_jsonl(dirs[role] / f"kps.agent-{role}.jsonl", kps)
        _write_jsonl(dirs[role] / f"pool-judgments.agent-{role}.jsonl", pools)
    pool_path = tmp_path / "pool.jsonl"
    _write_jsonl(pool_path, pool)
    return {"a": dirs["a"], "b": dirs["b"], "chapter": chapter_path, "pool": pool_path}


def test_spotcheck_pack_no_full_text_leak(tmp_path: Path):
    fx = _agent_fixture(tmp_path)
    pack = make_spotcheck_pack.build(fx["a"], fx["b"], fx["chapter"], fx["pool"],
                                     seed=373, sample_kps=5, sample_pairs=5, context=120)
    chapter = fx["chapter"].read_text(encoding="utf-8")
    blob = json.dumps(pack, ensure_ascii=False)
    assert pack["counts"]["kp_samples"] == 5, pack["counts"]
    assert pack["counts"]["edge_samples"] == 5, pack["counts"]
    assert pack["counts"]["diffs"] >= 2
    assert CHAPTER_TAIL_SENTINEL not in blob, "spotcheck 包泄露了远端的全文内容"
    assert chapter not in blob, "spotcheck 包包含 chapter 全文"
    assert pack["context_chars_total"] < len(chapter) * 0.5, "上下文总量应远小于全文"
    assert pack["est_human_minutes"] <= 120
    # 每项上下文窗口 ≤ 2*context + span 长度
    for item in pack["items"]:
        for side in ("a", "b"):
            data = item.get(side)
            if not data or not data.get("excerpt"):
                continue
            ex = data["excerpt"]
            span_len = ex["span"]["end"] - ex["span"]["start"]
            assert ex["chars"] <= 2 * 120 + max(span_len, 1) + 2, (item["item_id"], ex["chars"])


def test_spotcheck_pack_markdown_and_missing_input(tmp_path: Path):
    fx = _agent_fixture(tmp_path)
    md, js = tmp_path / "pack.md", tmp_path / "pack.json"
    code = make_spotcheck_pack.main([
        "--agent-a-dir", str(fx["a"]), "--agent-b-dir", str(fx["b"]),
        "--chapter", str(fx["chapter"]), "--pool", str(fx["pool"]),
        "--context-chars", "100", "--out", str(md), "--json-out", str(js)])
    assert code == 0 and md.exists() and js.exists()
    text = md.read_text(encoding="utf-8")
    assert "SPOTCHECK-PACK" in text and "decision" in text
    assert CHAPTER_TAIL_SENTINEL not in text
    # 缺输入 → exit 2
    code = make_spotcheck_pack.main([
        "--agent-a-dir", str(tmp_path / "none-a"), "--agent-b-dir", str(tmp_path / "none-b"),
        "--chapter", str(fx["chapter"]), "--pool", str(fx["pool"]),
        "--out", str(tmp_path / "x.md"), "--json-out", str(tmp_path / "x.json")])
    assert code == 2


# ---------------------------------------------------------------- IAA v2 modes
def test_iaa_v2_pure_agent_marking(tmp_path: Path):
    fx = _agent_fixture(tmp_path)
    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps({"sections": []}), encoding="utf-8")
    report = make_iaa_report_v2.build("pure_agent", fx["a"], fx["b"], fx["pool"],
                                      sections, None, None)
    assert report["mode"] == "pure_agent"
    assert report["annotator_type"] == "agent"
    assert report["human_iaa"] is False
    assert report["human_unvalidated"] is True
    assert report["not_c8_conclusion"] is True
    assert report["human_adjudication_agreement"] is None
    assert "human_iaa\": true" not in json.dumps(report)
    assert report["agent_vs_agent"]["kp_span_unitizing_alpha"] is not None


def test_iaa_v2_rejects_human_labels(tmp_path: Path):
    fx = _agent_fixture(tmp_path)
    human_kps = [{"id": "a-kp-001", "annotator": "annotator-a",
                  "spans": [{"start": 0, "end": 10}], "section_key": "s1",
                  "concept_type": "concept"}]
    _write_jsonl(fx["a"] / "kps.agent-a.jsonl", human_kps)
    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps({"sections": []}), encoding="utf-8")
    code = make_iaa_report_v2.main([
        "--mode", "pure_agent", "--agent-a-dir", str(fx["a"]), "--agent-b-dir", str(fx["b"]),
        "--pool", str(fx["pool"]), "--sections", str(sections),
        "--out", str(tmp_path / "r.json")])
    assert code == 1, "human 标签混入 agent 报告必须 exit 1"
    assert not (tmp_path / "r.json").exists()


def test_iaa_v2_bulk_requires_adjudication(tmp_path: Path):
    fx = _agent_fixture(tmp_path)
    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps({"sections": []}), encoding="utf-8")
    code = make_iaa_report_v2.main([
        "--mode", "agent_bulk_human_adjudication",
        "--agent-a-dir", str(fx["a"]), "--agent-b-dir", str(fx["b"]),
        "--pool", str(fx["pool"]), "--sections", str(sections),
        "--adjudications", str(tmp_path / "none.jsonl"),
        "--out", str(tmp_path / "r.json")])
    assert code == 2, "bulk 模式缺人类裁决应 exit 2"


def test_iaa_v2_bulk_agreement_and_completeness(tmp_path: Path):
    fx = _agent_fixture(tmp_path)
    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps({"sections": []}), encoding="utf-8")
    pack_ids = ["kp-diff-01", "edge-diff-01", "kp-sample-01", "edge-sample-01"]
    spotcheck = tmp_path / "spotcheck.json"
    spotcheck.write_text(json.dumps({"items": [{"item_id": i} for i in pack_ids]}), encoding="utf-8")
    log = tmp_path / "adjudication-log.jsonl"
    _write_jsonl(log, [
        {"item_id": "kp-diff-01", "item_type": "disagreement", "kind": "kp", "decision": "采 A"},
        {"item_id": "edge-diff-01", "item_type": "disagreement", "kind": "edge", "decision": "采 B"},
        {"item_id": "kp-sample-01", "item_type": "spotcheck", "kind": "kp", "decision": "重判：重切"},
        {"item_id": "edge-sample-01", "item_type": "spotcheck", "kind": "edge", "decision": "采 A"},
    ])
    report = make_iaa_report_v2.build(
        "agent_bulk_human_adjudication", fx["a"], fx["b"], fx["pool"],
        sections, log, spotcheck)
    assert report["human_iaa"] is False
    assert report["human_adjudication"] is True
    assert report["human_unvalidated"] is False
    assert report["not_c8_conclusion"] is True
    assert report["human_adjudication_complete"] is True
    adj = report["human_adjudication_agreement"]
    assert adj["n_judged"] == 4 and adj["accepted_a"] == 2 and adj["accepted_b"] == 1
    assert adj["overturned"] == 1
    assert adj["human_adjudication_agreement"] == 0.75
    assert adj["missing_item_ids"] == []


def test_validator_agent_annotator_type(tmp_path: Path):
    fx = _agent_fixture(tmp_path)
    sections = tmp_path / "sections.json"
    # validator 需要真实 sections 覆盖 span；用单 section 覆盖整章
    chapter = fx["chapter"].read_text(encoding="utf-8")
    sections.write_text(json.dumps({"sections": [{"page_id": "ch1-s1", "start": 0,
                                                  "end": len(chapter)}]}), encoding="utf-8")
    # 只用前 2 个 KP + 2 个池对验证 annotator-type 语义（数量参数放宽）
    kps = json.loads((fx["a"] / "kps.agent-a.jsonl").read_text(encoding="utf-8").splitlines()[0])
    kps2 = json.loads((fx["a"] / "kps.agent-a.jsonl").read_text(encoding="utf-8").splitlines()[1])
    pool_rows = [json.loads(x) for x in (fx["a"] / "pool-judgments.agent-a.jsonl")
                 .read_text(encoding="utf-8").splitlines()[:2]]
    simple_pool = [{"pair_id": r["pair_id"], "source": r["source"], "target": r["target"]}
                   for r in pool_rows]
    paths = {"kps": tmp_path / "k.agent-a.jsonl", "poolj": tmp_path / "p.agent-a.jsonl",
             "a_kps": tmp_path / "a_kps.jsonl"}
    _write_jsonl(paths["kps"], [kps, kps2])
    _write_jsonl(paths["poolj"], pool_rows)
    _write_jsonl(paths["a_kps"], [{"id": f"kp-{i}"} for i in range(10)])
    pool_file = tmp_path / "pool2.jsonl"
    _write_jsonl(pool_file, simple_pool)
    report = validate_human_labels.run(
        "a", paths["kps"], paths["poolj"], fx["chapter"], sections, pool_file,
        paths["a_kps"], min_kps=2, max_kps=2, expected_pool=2, annotator_type="agent")
    assert report["ok"] is True, report["failed"]
    # 把 annotator 改成 human → 应失败
    bad = json.loads(json.dumps(kps))
    bad["annotator"] = "annotator-a"
    _write_jsonl(paths["kps"], [bad, kps2])
    report = validate_human_labels.run(
        "a", paths["kps"], paths["poolj"], fx["chapter"], sections, pool_file,
        paths["a_kps"], min_kps=2, max_kps=2, expected_pool=2, annotator_type="agent")
    assert report["ok"] is False
    assert any(f.startswith("kp.annotator") for f in report["failed"])
