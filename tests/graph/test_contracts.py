"""B1 契约测试：I-01 DataSourceReader / I-12 ErrorMap / I-13 SchemaValidator。

## 这个文件守什么

| 验收项 | 落点 |
|---|---|
| 错误码覆盖 S6 + ADDENDUM-1 + ADDENDUM-2 | ``test_error_codes_cover_frozen_documents``（**对冻结文档反查**，不信表自己） |
| 未知码 ⇒ ``GRAPH_INTERNAL`` | ``test_unknown_code_falls_back_to_internal`` |
| 契约 sha 绑定（R3 防漂移） | ``test_schema_contract_bindings_ok`` + ``test_contract_sha_drift_is_detected`` |
| 非法 fixture fail-closed | ``test_invalid_fixtures_fail_closed`` |
| 不支持关键字 fail-closed | ``test_unsupported_keyword_fails_closed`` |
| **D-3 无 sidecar 写** | ``test_datasource_does_not_write_kb`` + ``test_write_guard_trips_on_write`` |
| E_relation_min | ``test_datasource_edges_use_relation_min`` |

> 关键设计：守卫类测试都配一条"**注入违规必须被抓到**"的对照（写文件/改 sha），
> 否则"绿"只能证明函数被调用过，不能证明它真的会拦。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from memoria.graph.multilevel import datasource as ds_mod
from memoria.graph.multilevel import errors as err_mod
from memoria.graph.multilevel import schema as schema_mod
from memoria.graph.multilevel.datasource import (
    E_RELATION_MIN,
    DataSourceReader,
    detect_writes,
    read_only_guard,
    snapshot_kb,
)
from memoria.graph.multilevel.errors import (
    ERROR_SPECS,
    GRAPH_INTERNAL,
    GraphError,
    canonicalize,
    spec_for,
    validate_table,
)
from memoria.graph.multilevel.schema import (
    SCHEMA_FILES,
    SCHEMAS_DIR,
    load_schema,
    validate,
    validate_or_raise,
    verify_all_bindings,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FROZEN_DOCS = REPO / "docs" / "design" / "multilevel-graph"

FROZEN_DOC_FILES = (
    "S6-contract-v1.md",
    "S6-ADDENDUM-1.md",
    "S6-ADDENDUM-2.md",
)


# ── 测试夹具：临时 KB ─────────────────────────────────────────────────────


def _make_kb(root: Path) -> Path:
    """造一个最小合法 KB（1 篇 md + 3 层嵌套 KP ⇒ 2 条 contain 边）。

    range 必须**严格嵌套**（``strictly_contains`` 要求 outer.start ≤ inner.start
    且 inner.end ≤ outer.end，且至少一侧更宽）：
    ``a 1..13`` ⊃ ``a1 3..11`` ⊃ ``a1-1 7..9``。
    """
    kb = root / "kb"
    (kb / ".memoria" / "sidecars").mkdir(parents=True)
    (kb / "a.md").write_text(
        "# A\n"          # 1
        "\n"             # 2
        "## A1\n"        # 3
        "\n"             # 4
        "text a1\n"      # 5
        "\n"             # 6
        "### A1-1\n"     # 7
        "\n"             # 8
        "text a11\n"     # 9
        "\n"             # 10
        "text tail\n"    # 11
        "\n"             # 12
        "text end\n",    # 13
        encoding="utf-8",
    )
    (kb / ".memoria" / "manifest.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    sidecar = {
        "schema_version": 1,
        "file": "a.md",
        "knowledge_points": [
            {"id": "a", "name": "A", "range": {
                "start": {"snippet": "# A", "line_hint": 1},
                "end": {"snippet": "text end", "line_hint": 13}}},
            {"id": "a1", "name": "A1", "range": {
                "start": {"snippet": "## A1", "line_hint": 3},
                "end": {"snippet": "text tail", "line_hint": 11}}},
            {"id": "a1-1", "name": "A1-1", "range": {
                "start": {"snippet": "### A1-1", "line_hint": 7},
                "end": {"snippet": "text a11", "line_hint": 9}}},
        ],
    }
    (kb / ".memoria" / "sidecars" / "a.memoria.yaml").write_text(
        yaml.safe_dump(sidecar, allow_unicode=True, sort_keys=False, width=4096),
        encoding="utf-8",
    )
    return kb


# ── I-12 ErrorMap ────────────────────────────────────────────────────────


def test_error_table_self_check() -> None:
    """错误表自检（severity/i18n/来源/计数下限）。"""
    assert validate_table() == []


def test_error_codes_cover_frozen_documents() -> None:
    """**对冻结文档反查**：文档里出现的每个 GRAPH_* 码都必须在表里（除兜底码）。

    这条不信任错误表自身：直接解析三份冻结设计稿的正文，
    文档新增码而表没跟 ⇒ 红（R3 契约漂移）。
    """
    doc_codes: set[str] = set()
    for name in FROZEN_DOC_FILES:
        text = (FROZEN_DOCS / name).read_text(encoding="utf-8")
        doc_codes.update(re.findall(r"GRAPH_[A-Z0-9_]+", text))

    assert doc_codes, "冻结文档里没解析到任何 GRAPH_* 码，解析逻辑失效"

    canonical = set(ERROR_SPECS)
    missing = sorted(
        c for c in doc_codes
        if c not in canonical and c not in err_mod.LEGACY_CODES
    )
    assert not missing, f"冻结文档里有而错误表缺失的码：{missing}"

    # legacy-only 的历史码允许只作映射目标存在
    assert doc_codes <= (canonical | err_mod.LEGACY_CODES)


def test_error_counts_per_source() -> None:
    """三源计数：ADDENDUM-1 = 6，ADDENDUM-2 = 14，S6 ≥ 4。"""
    assert len(err_mod.ADDENDUM1_CODES) == 6
    assert len(err_mod.ADDENDUM2_CODES) == 14
    assert len(err_mod.S6_ONLY_CODES) >= 4
    # S6 实际收 5 个（S6-6 四个 + S6-3 的 GRAPH_HISTORY_SIGNATURE_INVALID）
    assert "GRAPH_HISTORY_SIGNATURE_INVALID" in err_mod.S6_ONLY_CODES
    for code in ("GRAPH_FRAME_ID_INVALID", "GRAPH_PRESENCE_INVALID",
                 "GRAPH_SUBSET_VIOLATION", "GRAPH_BUDGET_INVALID"):
        assert code in err_mod.S6_ONLY_CODES


def test_error_specs_have_valid_metadata() -> None:
    """每个码：severity ∈ {error,warn}；i18n 前缀 graph.；legacy 可解析或为空。"""
    for code, spec in ERROR_SPECS.items():
        assert spec.severity in err_mod.SEVERITIES, f"{code} severity"
        assert re.match(r"^graph\.[a-z0-9_.]+$", spec.i18n_key), f"{code} i18n"
        assert spec.source in FROZEN_DOC_FILES, f"{code} 来源"
        if spec.legacy_code:
            assert spec.legacy_code.startswith("GRAPH_")


def test_unknown_code_falls_back_to_internal() -> None:
    """未知输入一律折成 GRAPH_INTERNAL（绝不抛、绝不原样透传）。"""
    for bad in ("NOT_A_CODE", "", None, 123, "graph.edge.invalid"):
        assert canonicalize(bad) == GRAPH_INTERNAL
        assert spec_for(bad).code == GRAPH_INTERNAL


def test_legacy_only_code_is_not_canonical() -> None:
    """只作 legacy 的历史码没有 canonical 身份 ⇒ 折回 GRAPH_INTERNAL。"""
    assert "GRAPH_EDITION_STALE" in err_mod.LEGACY_CODES
    assert "GRAPH_EDITION_STALE" not in ERROR_SPECS
    assert canonicalize("GRAPH_EDITION_STALE") == GRAPH_INTERNAL


def test_graph_error_envelope_matches_schema() -> None:
    """GraphError 信封满足 ``error.json`` 契约（含 audit_id 字段存在）。"""
    env = GraphError("GRAPH_EDGE_INVALID", "boom", audit_id="aud-1").to_envelope()
    result = validate(env, "error")
    assert result.ok, result.to_dict()
    assert env["code"] == "GRAPH_EDGE_INVALID"
    assert env["severity"] == "error"


def test_graph_error_unknown_code_envelope_is_internal() -> None:
    env = GraphError("WHATEVER", "boom").to_envelope()
    assert env["code"] == GRAPH_INTERNAL
    assert validate(env, "error").ok


# ── I-13 SchemaValidator：契约绑定 ───────────────────────────────────────


def test_schema_files_exist_and_parse() -> None:
    for name, filename in SCHEMA_FILES.items():
        path = SCHEMAS_DIR / filename
        assert path.is_file(), f"{name} schema 缺失"
        assert isinstance(load_schema(name), dict)


def test_schema_contract_bindings_ok() -> None:
    """S6 + 两个 ADDENDUM 的 sha 与磁盘冻结文档一致（R3 第一道闸）。"""
    problems = verify_all_bindings()
    bad = {k: v for k, v in problems.items() if v}
    assert not bad, f"契约 sha 绑定失败：{bad}"


def test_schema_declares_known_failure_code() -> None:
    for name in SCHEMA_FILES:
        schema = load_schema(name)
        code = schema_mod.schema_failure_code(schema)
        assert code in ERROR_SPECS


@pytest.mark.parametrize("name", sorted(SCHEMA_FILES))
def test_schema_has_contract_sources(name: str) -> None:
    schema = load_schema(name)
    sources = schema.get("x-contract-sources")
    assert isinstance(sources, dict) and sources
    # 三份冻结文档必须全部绑定（少一份就是"漏绑"）
    assert set(FROZEN_DOC_FILES) <= set(sources)


def test_contract_sha_drift_is_detected(tmp_path: Path, monkeypatch) -> None:
    """**守卫活性对照**：篡改冻结文档 → 绑定检查必须报漂移。

    没有这条，"绑定通过"只能证明函数跑过，不能证明它真的会拦。
    """
    fake_docs = tmp_path / "docs"
    fake_docs.mkdir()
    for name in FROZEN_DOC_FILES:
        (fake_docs / name).write_text("被篡改的冻结文档\n", encoding="utf-8")
    monkeypatch.setattr(schema_mod, "_FROZEN_DOCS_DIR", fake_docs)

    problems = schema_mod.verify_all_bindings()
    assert any(problems.values()), "篡改冻结文档后绑定检查仍全绿 ⇒ 绑定形同虚设"
    with pytest.raises(GraphError) as ei:
        schema_mod.assert_contract_bindings()
    assert ei.value.code == GRAPH_INTERNAL


def test_datasource_defs_match_standalone_schemas() -> None:
    """``datasource.json`` 内联的 $defs 必须与独立 schema 一致（防两处漂移）。"""
    ds = load_schema("datasource")
    defs = ds.get("$defs") or {}
    ignore = {"$schema", "$id", "title", "description", "x-failure-code", "x-contract-sources"}

    def body(schema: dict) -> dict:
        return {k: v for k, v in schema.items() if k not in ignore}

    assert body(defs["kp"]) == body(load_schema("kp"))
    assert body(defs["edge"]) == body(load_schema("edge"))


# ── I-13：合法/非法 fixture ──────────────────────────────────────────────


def _valid_cases() -> list[tuple[str, str]]:
    mapping = {
        "edge-min.json": "edge",
        "edge-full.json": "edge",
        "kp-min.json": "kp",
        "kp-full.json": "kp",
        "datasource.json": "datasource",
        "error-envelope.json": "error",
    }
    return [(f, s) for f, s in sorted(mapping.items()) if (FIXTURES / "valid" / f).is_file()]


def _invalid_cases() -> list[tuple[str, dict]]:
    expect = json.loads((FIXTURES / "invalid" / "_expectations.json").read_text(encoding="utf-8"))
    return sorted(expect.items())


@pytest.mark.parametrize("filename,schema_name", _valid_cases())
def test_valid_fixtures_pass(filename: str, schema_name: str) -> None:
    payload = json.loads((FIXTURES / "valid" / filename).read_text(encoding="utf-8"))
    result = validate(payload, schema_name)
    assert result.ok, f"{filename} 应通过：{result.to_dict()}"


@pytest.mark.parametrize("filename,expect", _invalid_cases())
def test_invalid_fixtures_fail_closed(filename: str, expect: dict) -> None:
    """非法 fixture 必须 fail-closed，且报出期望的码与路径。"""
    payload = json.loads((FIXTURES / "invalid" / filename).read_text(encoding="utf-8"))
    result = validate(payload, expect["schema"])
    assert not result.ok, f"{filename} 竟然通过了（fail-open，违反 S6-9）"
    assert expect["code"] in result.codes, f"{filename} 码不符：{result.codes}"
    assert any(expect["path_has"] in e.path or expect["path_has"] in e.message
               for e in result.errors), f"{filename} 未指出 {expect['path_has']}：{result.to_dict()}"


def test_validate_or_raise_raises_graph_error() -> None:
    payload = json.loads((FIXTURES / "invalid" / "edge-bad-type.json").read_text(encoding="utf-8"))
    with pytest.raises(GraphError) as ei:
        validate_or_raise(payload, "edge")
    assert ei.value.code == "GRAPH_EDGE_INVALID"


def test_unknown_schema_name_fails_closed() -> None:
    with pytest.raises(GraphError) as ei:
        validate({}, "no_such_schema")
    assert ei.value.code == GRAPH_INTERNAL


def test_unsupported_keyword_fails_closed(tmp_path: Path, monkeypatch) -> None:
    """schema 用了校验器不支持的关键字 ⇒ 判失败（**跳过的校验器等于没校验**）。"""
    fake = tmp_path / "schemas"
    fake.mkdir()
    # 绑定用真实 sha（这样绑定先通过，唯一变量是"不支持的关键字"）
    real_sources = load_schema("edge")["x-contract-sources"]
    bad_schema = {
        "$id": "memoria://graph/contracts/edge/v1",
        "x-failure-code": "GRAPH_EDGE_INVALID",
        "x-contract-sources": real_sources,
        "type": "object",
        "format": "uri",  # ← 不支持的关键字
    }
    (fake / "edge.json").write_text(json.dumps(bad_schema), encoding="utf-8")
    monkeypatch.setattr(schema_mod, "SCHEMAS_DIR", fake)

    result = validate({"type": "contain"}, "edge")
    assert not result.ok, "不支持的关键字被静默跳过（fail-open）"
    assert any("不支持" in e.message for e in result.errors)


def test_schema_missing_file_fails_closed(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "schemas"
    empty.mkdir()
    monkeypatch.setattr(schema_mod, "SCHEMAS_DIR", empty)
    with pytest.raises(GraphError) as ei:
        load_schema("edge")
    assert ei.value.code == GRAPH_INTERNAL


# ── I-01 DataSourceReader ───────────────────────────────────────────────


def test_datasource_shape_and_contract(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    ds = DataSourceReader(kb).read()

    assert ds.status == "ok"
    assert ds.e_relation_min == E_RELATION_MIN
    assert all(k["kind"] == "kp" for k in ds.kps)
    assert ds.edges, "应至少有 contain 边"
    assert validate(ds.to_dict(), "datasource").ok


def test_datasource_edges_use_relation_min(tmp_path: Path) -> None:
    """边的 type 只能落在 E_relation_min 的三种基础类型里（S0-3 R-1）。"""
    kb = _make_kb(tmp_path)
    ds = DataSourceReader(kb).read()
    allowed = {"contain", "reference", "extend"}
    assert {e["type"] for e in ds.edges} <= allowed
    assert len(E_RELATION_MIN) == 4


def test_datasource_does_not_write_kb(tmp_path: Path) -> None:
    """**D-3 硬断言**：读取前后 KB 全树 sha 不变（无新增/删除/修改）。"""
    kb = _make_kb(tmp_path)
    before = snapshot_kb(kb)
    DataSourceReader(kb).read()
    after = snapshot_kb(kb)
    assert detect_writes(before, after) == [], "读取期间 KB 被写入（D-3 违规）"


def test_datasource_does_not_write_real_example_kb() -> None:
    """对仓库内真实示例库做一次只读读取，KB 仍需零变化（D-3）。"""
    kb = REPO / "docs" / "example" / "AAA_Vocab"
    if not kb.is_dir():
        pytest.skip("示例库不存在")
    before = snapshot_kb(kb)
    ds = DataSourceReader(kb).read()
    after = snapshot_kb(kb)
    assert detect_writes(before, after) == []
    assert validate(ds.to_dict(), "datasource").ok


def test_write_guard_trips_on_write(tmp_path: Path, monkeypatch) -> None:
    """**守卫活性对照**：读取过程中写一个文件 ⇒ 必须抛 GRAPH_WRITE_FORBIDDEN。

    没有这条，``test_datasource_does_not_write_kb`` 的绿只能说明"这次没写"，
    不能说明"写了会被抓"。
    """
    kb = _make_kb(tmp_path)

    def _writing_collect(self):
        (Path(self.kb_path) / "evil.txt").write_text("x", encoding="utf-8")
        return {"nodes": [], "edges": []}

    monkeypatch.setattr(datasource_cls(), "_collect_raw", _writing_collect)
    with pytest.raises(GraphError) as ei:
        DataSourceReader(kb).read()
    assert ei.value.code == "GRAPH_WRITE_FORBIDDEN"
    assert "evil.txt" in json.dumps(ei.value.detail, ensure_ascii=False)


def test_read_only_guard_detects_modification(tmp_path: Path) -> None:
    """守卫对"修改既有文件"同样生效（不只是新增）。"""
    kb = _make_kb(tmp_path)
    with pytest.raises(GraphError) as ei:
        with read_only_guard(kb):
            (kb / "a.md").write_text("# A\n改动\n", encoding="utf-8")
    assert ei.value.code == "GRAPH_WRITE_FORBIDDEN"


def test_read_only_guard_allows_pure_read(tmp_path: Path) -> None:
    kb = _make_kb(tmp_path)
    with read_only_guard(kb):
        snapshot_kb(kb)  # 只读
    # 未抛即通过


def test_datasource_canonical_id_is_stable(tmp_path: Path) -> None:
    """同一 KB 两次读取 canonical_id 必须相同（确定性；G6 复跑前提）。"""
    kb = _make_kb(tmp_path)
    a = DataSourceReader(kb).read()
    b = DataSourceReader(kb).read()
    assert a.canonical_id == b.canonical_id
    assert re.match(r"^[0-9a-f]{64}$", a.canonical_id)


def test_datasource_canonical_id_changes_with_content(tmp_path: Path) -> None:
    """内容变化 ⇒ canonical_id 变（防止"恒定 sha"式的假确定性）。"""
    kb = _make_kb(tmp_path)
    before = DataSourceReader(kb).read().canonical_id
    (kb / ".memoria" / "manifest.yaml").write_text("schema_version: 2\n", encoding="utf-8")
    after = DataSourceReader(kb).read().canonical_id
    assert before != after


def test_datasource_empty_kb_is_nosemantic(tmp_path: Path) -> None:
    """空 KB ⇒ status=empty_nosemantic（不是 error；fail-open 到"空图"是可接受的）。"""
    empty = tmp_path / "empty"
    (empty / ".memoria").mkdir(parents=True)
    ds = DataSourceReader(empty).read()
    assert ds.status == "empty_nosemantic"
    assert ds.kps == () and ds.edges == ()
    assert validate(ds.to_dict(), "datasource").ok


def test_datasource_missing_kb_raises(tmp_path: Path) -> None:
    with pytest.raises(GraphError) as ei:
        DataSourceReader(tmp_path / "nope").read()
    assert ei.value.code == GRAPH_INTERNAL


def test_datasource_contract_guard_can_be_disabled(tmp_path: Path) -> None:
    """``contract_guard=False`` 只跳过 sha 绑定，仍做 D-3 + schema 校验。"""
    kb = _make_kb(tmp_path)
    ds = DataSourceReader(kb, contract_guard=False).read()
    assert ds.status in ("ok", "empty_nosemantic")


# ── 辅助 ────────────────────────────────────────────────────────────────


def datasource_cls():
    """取被测类（便于 monkeypatch 时避免循环导入问题）。"""
    return ds_mod.DataSourceReader


def test_snapshot_kb_is_read_only(tmp_path: Path) -> None:
    """快照函数自身不写盘（否则 D-3 守卫会自己触发自己）。"""
    kb = _make_kb(tmp_path)
    before = snapshot_kb(kb)
    snapshot_kb(kb)
    assert snapshot_kb(kb) == before


def test_frozen_docs_unchanged_by_tests() -> None:
    """测试跑完冻结文档 sha 没被改（防止测试意外改写设计稿）。"""
    expected = {
        "S6-contract-v1.md": "40f12e5fd5946c8cc4ebdb71800579d3e9098f74ef7381ad65a2e51f389db82b",
    }
    for name, sha in expected.items():
        actual = hashlib.sha256((FROZEN_DOCS / name).read_bytes()).hexdigest()
        assert actual == sha, f"冻结文档被改动：{name}"
