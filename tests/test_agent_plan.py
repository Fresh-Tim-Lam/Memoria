"""写模块**只读骨架**（`services/agent/plan.py`）的离线单测：只校验与 dry-run，**零落盘**。

口径来源：`docs/design/agent-capabilities.md` §2.3.3（计划 API）/ §2.3.4（校验器）/ §2.6（M3a）。

覆盖：① 信封（版本 / txid / intent / ops）；② **未知 op 即拒整批**；③ `op_id` 唯一；
④ 路径越界即拒（复用 `_safe_rel`）；⑤ KP id 全局唯一 + **幂等键 `(file, kp_id)`**；
⑥ range 空行 / 顺序；⑦ 链接目标 `ok` / `ambiguous` / `not_found`；⑧ `occurrences` 的
「行 + 匹配文本」双核对；⑨ detach 的 sidecar 命中；⑩ `preview_plan` 给出行级 diff 且
**一个字节都不写**（逐文件 SHA256 比对）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.plan import (
    PLAN_VERSION,
    preview_plan,
    resolve_target,
    validate_plan,
)
from memoria.services.document import DocumentService

A_MD = "\n".join(
    [
        "# A 文档",  # 1
        "",  # 2（空行 ⇒ range 落到这里必须被拒）
        "注意力机制是核心。注意力机制也出现在别处。",  # 3
        "",  # 4
        "末尾一行。",  # 5
    ]
)
B_MD = "\n".join(["# B 文档", "", "乙知识点正文。", ""])


def _sidecar(rel: str, kp_id: str, *, name: str, start: str, end: str, end_line: int, links: str = "links: []") -> str:
    return "\n".join(
        [
            "schema_version: 1",
            f"file: {rel}",
            "knowledge_points:",
            f"- id: {kp_id}",
            f"  name: {name}",
            "  range:",
            "    start:",
            f"      snippet: '{start}'",
            "      line_hint: 1",
            "    end:",
            f"      snippet: '{end}'",
            f"      line_hint: {end_line}",
            links,
            "edges: []",
            "",
        ]
    )


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小知识库：两份正文 + 一个已挂接的 sidecar + 一对同 id 文件（造多义目标）。"""
    root = tmp_path / "kb"
    for sub in ("notes", "dup1", "dup2", ".memoria/sidecars/notes", ".memoria/sidecars/dup1", ".memoria/sidecars/dup2"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    (root / "notes" / "a.md").write_text(A_MD + "\n", encoding="utf-8")
    (root / "notes" / "b.md").write_text(B_MD + "\n", encoding="utf-8")
    (root / ".memoria" / "sidecars" / "notes" / "b.memoria.yaml").write_text(
        _sidecar(
            "notes/b.md",
            "b-kp",
            name="乙知识点",
            start="# B 文档",
            end="乙知识点正文。",
            end_line=3,
            links="\n".join(
                [
                    "links:",
                    "- anchor_text: 乙知识点正文",
                    "  targets:",
                    "  - b-kp",
                    "  instances:",
                    "  - line: 3",
                ]
            ),
        ),
        encoding="utf-8",
    )
    for dup in ("dup1", "dup2"):
        (root / dup / "same.md").write_text(f"# {dup}\n\n同一 id 的另一处。\n", encoding="utf-8")
        (root / ".memoria" / "sidecars" / dup / "same.memoria.yaml").write_text(
            _sidecar(f"{dup}/same.md", "dup-kp", name="同 id", start=f"# {dup}", end="同一 id 的另一处。", end_line=3),
            encoding="utf-8",
        )
    return root


@pytest.fixture()
def service(kb: Path) -> DocumentService:
    """先装载一次（既有装载语义会补写 manifest/pending），此后快照才可比对"零写入"。"""
    return DocumentService(kb_path=str(kb))


def _snapshot(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _plan(*ops: dict[str, Any], v: Any = PLAN_VERSION, txid: str = "20260920T021100Z-07") -> dict[str, Any]:
    return {"v": v, "txid": txid, "intent": "测试用 plan", "ops": list(ops)}


def _codes(checked: dict) -> set[str]:
    return {str(e["code"]) for e in checked["errors"]}


def _upsert(op_id: str = "o1", *, file: str = "notes/a.md", kp_id: str = "attention", start: int = 1, end: int = 3, **extra: Any) -> dict[str, Any]:
    op = {
        "op": "upsert_kp",
        "op_id": op_id,
        "file": file,
        "kp_id": kp_id,
        "name": "注意力机制",
        "range": {"start": {"line": start}, "end": {"line": end}},
    }
    op.update(extra)
    return op


def _attach(op_id: str = "o2", *, file: str = "notes/a.md", anchor: str = "注意力机制", targets: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    op = {
        "op": "attach_links",
        "op_id": op_id,
        "file": file,
        "anchor_text": anchor,
        "targets": targets if targets is not None else ["b-kp"],
    }
    op.update(extra)
    return op


def test_validate_plan_accepts_a_minimal_plan(kb: Path, service: DocumentService) -> None:
    """① 正常 plan：新建 KP 的 range 被解析成具体行区间，且 `create` 动作被认出。"""
    checked = validate_plan(str(kb), _plan(_upsert()), service=service)
    assert checked["status"] == "ok", checked["errors"]
    assert checked["errors"] == []
    op = checked["ops"][0]
    assert op["op"] == "upsert_kp" and op["file"] == "notes/a.md"
    assert op["action"] == "create"
    assert op["resolved"] == {"start_line": 1, "end_line": 3}
    # 非首批 op 只警告、不报错（M3b 才编译）
    lazy = validate_plan(str(kb), _plan({"op": "set_kp_range", "op_id": "o9", "file": "notes/a.md", "kp_id": "x"}), service=service)
    assert any(w["code"] == "op_not_in_m3a" for w in lazy["warnings"])
    assert lazy["ops"][0]["action"] == "uncompiled"  # 本片不编译它，也不假装编译过


def test_validate_plan_rejects_unknown_op_and_version(kb: Path, service: DocumentService) -> None:
    """② **未知即拒**：未知 op / 未知 `v` 都拒整批（P12 推荐①：格式演进不改提示词）。"""
    unknown = validate_plan(str(kb), _plan({"op": "delete_kb", "op_id": "o1", "file": "notes/a.md"}), service=service)
    assert unknown["status"] == "error" and "unknown_op" in _codes(unknown)
    bad_v = validate_plan(str(kb), _plan(_upsert(), v=2), service=service)
    assert bad_v["status"] == "error" and "bad_plan_version" in _codes(bad_v)
    no_intent = validate_plan(str(kb), {"v": 1, "txid": "x", "ops": [_upsert()]}, service=service)
    assert "missing_field" in _codes(no_intent)  # 缺 intent


def test_validate_plan_rejects_path_escape_and_duplicates(kb: Path, service: DocumentService) -> None:
    """③④ 路径越界即拒（复用 `_safe_rel`）；`op_id` 在 plan 内只能出现一次。"""
    escaped = validate_plan(str(kb), _plan(_upsert(file="../outside.md")), service=service)
    assert "path_rejected" in _codes(escaped)
    missing = validate_plan(str(kb), _plan(_upsert(file="notes/none.md")), service=service)
    assert "file_not_found" in _codes(missing)
    dup = validate_plan(str(kb), _plan(_upsert("same"), _upsert("same", kp_id="other")), service=service)
    assert "duplicate_op_id" in _codes(dup)


def test_validate_plan_kp_id_uniqueness_and_idempotency_key(kb: Path, service: DocumentService) -> None:
    """⑤ 跨库唯一 ⇒ 别处已有同 id 即拒；**本文件已有同 id ⇒ 幂等走更新**（幂等键 `(file, kp_id)`）。"""
    taken = validate_plan(str(kb), _plan(_upsert(kp_id="b-kp")), service=service)
    assert "kp_id_taken" in _codes(taken)
    update = validate_plan(str(kb), _plan(_upsert(file="notes/b.md", kp_id="b-kp")), service=service)
    assert update["status"] == "ok", update["errors"]
    assert update["ops"][0]["action"] == "update"


def test_validate_plan_range_rules(kb: Path, service: DocumentService) -> None:
    """⑥ 空行与顺序：两端落在空行上拒；`start > end` 拒。"""
    empty = validate_plan(str(kb), _plan(_upsert(start=2)), service=service)
    assert "range_line_empty" in _codes(empty)
    inverted = validate_plan(str(kb), _plan(_upsert(start=5, end=3)), service=service)
    assert "range_invalid" in _codes(inverted)
    out_of_range = validate_plan(str(kb), _plan(_upsert(start=99)), service=service)
    assert "bad_field" in _codes(out_of_range)


def test_validate_plan_link_targets_must_be_resolvable(kb: Path, service: DocumentService) -> None:
    """⑦ 目标**必须可解析**：唯一命中放行；多义/不存在一律拒（带各自的 code）。"""
    ok = validate_plan(str(kb), _plan(_attach()), service=service)
    assert ok["status"] == "ok", ok["errors"]
    assert ok["ops"][0]["lines"] == [3]  # 第 3 行两处「注意力机制」都在同一行 ⇒ 按行去重
    ghost = validate_plan(str(kb), _plan(_attach(targets=["ghost"])), service=service)
    assert "target_not_found" in _codes(ghost)
    ambiguous = validate_plan(str(kb), _plan(_attach(targets=["dup-kp"])), service=service)
    assert "target_ambiguous" in _codes(ambiguous)
    bad_edge = validate_plan(str(kb), _plan(_attach(edge_type="contain")), service=service)
    assert "bad_edge_type" in _codes(bad_edge)  # contain 不由 plan 写


def test_validate_plan_occurrences_are_cross_checked(kb: Path, service: DocumentService) -> None:
    """⑧ 「行 + 匹配文本」双核对（§2.3.3 第 2 条最小能力）：文本不符 / 行无锚 都拒。"""
    good = validate_plan(
        str(kb), _plan(_attach(occurrences=[{"line": 3, "matched_text": "注意力机制"}])), service=service
    )
    assert good["status"] == "ok", good["errors"]
    mismatch = validate_plan(str(kb), _plan(_attach(occurrences=[{"line": 3, "matched_text": "注意"}])), service=service)
    assert "occurrence_mismatch" in _codes(mismatch)
    absent = validate_plan(str(kb), _plan(_attach(occurrences=[{"line": 5}])), service=service)
    assert "occurrence_not_found" in _codes(absent)


def test_validate_plan_detach_requires_sidecar_anchor(kb: Path, service: DocumentService) -> None:
    """⑨ detach：锚必须在 sidecar `links[]` 命中，行必须是已挂接实例或含 `[[…]]`。"""
    op = {
        "op": "detach_links",
        "op_id": "o3",
        "file": "notes/b.md",
        "anchor_text": "乙知识点正文",
        "occurrences": [{"line": 3}],
        "mode": "detach",
    }
    assert validate_plan(str(kb), _plan(op), service=service)["status"] == "ok"
    ghost = {**op, "anchor_text": "不存在的锚"}
    assert "anchor_not_in_sidecar" in _codes(validate_plan(str(kb), _plan(ghost), service=service))
    bad_line = {**op, "occurrences": [{"line": 1}]}  # 第 1 行既非实例也不含 [[…]]
    assert "occurrence_not_found" in _codes(validate_plan(str(kb), _plan(bad_line), service=service))
    bad_mode = {**op, "mode": "explode"}
    assert "bad_field" in _codes(validate_plan(str(kb), _plan(bad_mode), service=service))


def test_preview_plan_gives_a_diff_and_writes_nothing(kb: Path, service: DocumentService) -> None:
    """⑩ dry-run：给出"将改哪几行 + 逐行 before/after"，且**逐文件 SHA256 完全不变**。"""
    before = _snapshot(kb)
    preview = preview_plan(str(kb), _plan(_upsert(), _attach()), service=service)
    assert preview["previewed"] is True and preview["status"] == "ok"
    assert [f["file"] for f in preview["files"]] == ["notes/a.md"]
    attach = next(op for op in preview["files"][0]["ops"] if op["op"] == "attach_links")
    assert attach["diff_available"] is True and attach["wrapped"] == 1
    assert attach["lines_changed"] == [3]
    row = attach["diff"][0]
    assert row["line"] == 3 and row["before"] == "注意力机制是核心。注意力机制也出现在别处。"
    # 正文包裹的是**锚文本**（`[[注意力机制]]`），目标 `b-kp` 记在 sidecar 的 links[]（Memoria 链接模型）
    assert row["after"].startswith("[[注意力机制]]是核心。")
    assert "注意力机制也出现在别处。" in row["after"]
    # 「零落盘」= **不写事实源**。复用既有只读 API 时可能碰可再生缓存：`resolve_link_target()`
    # → `build_kp_index()` 会补写 `.memoria/cache/search_aux/kp/*.json`（AGENTS.md §1 明确
    # `cache/**` 是**可再生缓存、不作为事实源**）。故：缓存目录之外的每一个文件都必须逐字节不变。
    after = _snapshot(kb)
    drifted = {k: v for k, v in after.items() if before.get(k) != v and not k.startswith(".memoria/cache/")}
    assert drifted == {}, drifted
    assert {k for k in after if k not in before} <= {k for k in after if k.startswith(".memoria/cache/")}
    assert all(after[k] == v for k, v in before.items() if not k.startswith(".memoria/cache/"))
    # 非法 plan 不预览（先校验，再 diff）
    bad = preview_plan(str(kb), _plan(_upsert(file="../x.md")), service=service)
    assert bad["previewed"] is False and bad["files"] == []


def test_resolve_target_shapes(kb: Path) -> None:
    """`resolve` 只读面：ok / ambiguous / not_found 三种形状稳定。"""
    ok = resolve_target(str(kb), "b-kp")
    assert ok["status"] == "ok" and ok["candidates"]
    ambiguous = resolve_target(str(kb), "dup-kp")
    assert ambiguous["status"] == "ambiguous" and len(ambiguous["candidates"]) == 2
    missing = resolve_target(str(kb), "ghost")
    assert missing["status"] == "not_found" and missing["candidates"] == []
    assert resolve_target(str(kb), "  ")["status"] == "not_found"
