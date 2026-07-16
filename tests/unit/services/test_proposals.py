"""SearchKernel v1.5b：aux → sidecar 候选提议同步。"""

from pathlib import Path

import pytest

from memoria.services.proposals import merge_aux_into_kp_proposals, sync_kp_implicit_proposals
from memoria.services.search_aux import generate_aux_for_kp, rebuild_search_aux
from memoria.storage.manifest import rebuild_manifest
from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "benchmark_retrieval_tiny"


@pytest.fixture
def tiny_kb(tmp_path):
    import shutil

    kb = tmp_path / "kb"
    shutil.copytree(FIXTURE, kb)
    rebuild_manifest(str(kb))
    return kb


def test_merge_aux_into_kp_proposals_skips_selected(tiny_kb):
    md = tiny_kb / "corpus" / "doc-vitd.md"
    sidecar = load_sidecar_for_md(str(md), str(tiny_kb))
    kp = dict(sidecar["knowledge_points"][0])
    lines = md.read_text(encoding="utf-8").splitlines()
    aux = generate_aux_for_kp(
        kb_path=str(tiny_kb),
        rel_path="corpus/doc-vitd.md",
        kp=kp,
        lines=lines,
    )

    fresh = merge_aux_into_kp_proposals(
        kb_path=str(tiny_kb),
        rel_path="corpus/doc-vitd.md",
        kp=kp,
        lines=lines,
        aux=aux,
    )
    tag_names = {r["tag"].lower() for r in fresh["tag_candidates"]}
    for t in kp["tags"]:
        assert t.lower() not in tag_names

    kp["description"] = ""
    fresh2 = merge_aux_into_kp_proposals(
        kb_path=str(tiny_kb),
        rel_path="corpus/doc-vitd.md",
        kp=kp,
        lines=lines,
        aux=aux,
    )
    assert fresh2["description_candidates"]
    assert fresh2["description_candidates"][0]["source"] == "system"


def test_sync_kp_implicit_proposals_respects_dismissed(tiny_kb):
    rebuild_search_aux(str(tiny_kb))
    md_path = str(tiny_kb / "corpus" / "doc-vitd.md")
    sidecar = load_sidecar_for_md(md_path, str(tiny_kb))
    kp = sidecar["knowledge_points"][0]
    kp["tag_candidates"] = [
        {"tag": "immunology", "source": "system", "status": "dismissed"},
    ]
    save_sidecar_for_md(md_path, str(tiny_kb), sidecar)

    res = sync_kp_implicit_proposals(
        kb_path=str(tiny_kb),
        rel_path="corpus/doc-vitd.md",
        kp_id="doc-vitd",
        rebuild=False,
    )
    assert res["status"] == "ok"
    assert res["aux_present"] is True
    tags = {r["tag"].lower() for r in res["tag_candidates"]}
    immunology = [r for r in res["tag_candidates"] if r["tag"].lower() == "immunology"]
    assert len(immunology) == 1
    assert immunology[0].get("status") == "dismissed"


def test_sync_kp_implicit_proposals_merges_new_rows(tiny_kb):
    rebuild_search_aux(str(tiny_kb))
    res = sync_kp_implicit_proposals(
        kb_path=str(tiny_kb),
        rel_path="corpus/doc-vitd.md",
        kp_id="doc-vitd",
        rebuild=False,
    )
    assert res["status"] == "ok"
    assert isinstance(res["tag_candidates"], list)
    assert isinstance(res["alias_candidates"], list)
    assert isinstance(res["description_candidates"], list)
