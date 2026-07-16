"""SearchKernel v1.5a：search_aux 与隐式 Lexical 通道。"""

from pathlib import Path

import pytest

from memoria.services.lexical_index import rebuild_lexical_index, search_lexical
from memoria.services.search_aux import (
    aux_lexical_fields,
    generate_aux_for_kp,
    load_kp_aux,
    rebuild_search_aux,
    search_aux_manifest_path,
)
from memoria.storage.manifest import rebuild_manifest

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "benchmark_retrieval_tiny"


@pytest.fixture
def tiny_kb(tmp_path):
    import shutil

    kb = tmp_path / "kb"
    shutil.copytree(FIXTURE, kb)
    rebuild_manifest(str(kb))
    return kb


def test_generate_aux_for_kp(tiny_kb):
    from memoria.storage.sidecar import load_sidecar_for_md

    md = tiny_kb / "corpus" / "doc-vitd.md"
    sidecar = load_sidecar_for_md(str(md), str(tiny_kb))
    kp = sidecar["knowledge_points"][0]
    lines = md.read_text(encoding="utf-8").splitlines()

    aux = generate_aux_for_kp(
        kb_path=str(tiny_kb),
        rel_path="corpus/doc-vitd.md",
        kp=kp,
        lines=lines,
    )
    assert aux["kp_id"] == "doc-vitd"
    assert aux["source_fingerprint"]
    assert isinstance(aux["auto_tags"], list)
    assert aux["summary_1l"]
    assert "immun" in aux["summary_1l"].lower() or "Vitamin" in aux["summary_1l"]


def test_rebuild_search_aux_incremental(tiny_kb):
    m1 = rebuild_search_aux(str(tiny_kb))
    assert m1["kp_count"] >= 5
    assert Path(search_aux_manifest_path(str(tiny_kb))).is_file()

    m2 = rebuild_search_aux(str(tiny_kb))
    assert m2["skipped"] >= m1["kp_count"] - 1
    assert m2["updated"] == 0


def test_lexical_implicit_auto_tag_hit(tiny_kb):
    rebuild_lexical_index(str(tiny_kb))
    aux = load_kp_aux(str(tiny_kb), "doc-vitd")
    assert aux is not None

    from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md

    md_path = str(tiny_kb / "corpus" / "doc-vitd.md")
    sidecar = load_sidecar_for_md(md_path, str(tiny_kb))
    kp = sidecar["knowledge_points"][0]
    kp["tags"] = []
    kp["description"] = ""
    save_sidecar_for_md(md_path, str(tiny_kb), sidecar)
    rebuild_lexical_index(str(tiny_kb))

    res = search_lexical("lymphocyte", kb_path=str(tiny_kb), limit=5)
    ids = [r["kp_id"] for r in res["results"]]
    assert "doc-vitd" in ids
    hit = next(r for r in res["results"] if r["kp_id"] == "doc-vitd")
    src = hit.get("sources") or []
    assert any(
        "summary" in s or "key-phrase" in s or "body" in s or "token-" in s for s in src
    )


def test_aux_lexical_fields_respects_promoted():
    aux = {
        "auto_tags": ["RL", "math"],
        "aliases": ["mdp-id"],
        "promoted": {"auto_tags": ["RL"], "aliases": []},
    }
    fields = aux_lexical_fields(aux)
    assert "RL" not in fields["auto_tags"]
    assert "math" in fields["auto_tags"]
