"""知识点级 op（§7 的 1.2 / 1.7 / 1.8）：`upsert_edge` / `delete_kp` / `rename_kp` 的离线单测。

钉住的口径：

1. **纯边**（`upsert_edge` → 原语 `create_edge`）：只写 sidecar `edges[]`、**正文一字不动**。
   `source_id` 必须是**本文档**的知识点（`create_edge()` 的硬约束）、`target_id` 必须全库可解析、
   边类型只收 `reference` / `extend`（`contain` 由标题层级推导、禁手标）、同源同目标不重复建。
2. **删知识点**（`delete_kp` → `kb.kp.delete`）：只删 sidecar 里那一条，**正文一字不动**；
   别处仍指向它的引用**只警告**（`delete_leaves_dangling`）—— 库规明确允许悬空虚链（`kb-spec` §4），
   这与 `delete_file` 对正文引用**硬拦**是**有意不同的分层**（那里整篇消失，这里只少一个可解析目标）。
3. **全库改 id**（`rename_kp` → `kb.kp.rename`）：正文里的 `[[旧 id]]` 与**各侧车**的引用一起改；
   预演走 `kp_rename.rename_kp_in_kb(dry_run=True)`（同一份实现、不落盘）⇒ 它给出的清单就是备份集，
   撤销能**逐字节还原全库**。它**没有 `file` 字段** ⇒ 天然豁免读后写闸（那道闸的闸是审批卡），
   但它必须**收尾**（其后只允许再排文件级 op）。
4. 三个 op 都**可整批撤销**：`restore_batch()` 之后与写前逐文件 sha256 一致。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent import observation
from memoria.services.agent.apply import apply_plan, compile_plan
from memoria.services.agent.backup import restore_batch
from memoria.services.agent.file_ops import kp_referrers
from memoria.services.agent.llm import ToolCall
from memoria.services.agent.plan import preview_plan, validate_plan
from memoria.services.agent.tools import ToolRegistry, build_kb_tools
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME
from memoria.services.document import DocumentService
from memoria.storage.sidecar import load_sidecar_for_md

A_MD = "# A 文档\n\n注意力机制是核心。\n\n末尾一行。\n"
B_MD = "# B 文档\n\n见 [[a-kp]] 这篇。\n"
SESSION = "session-20260922T120000Z-kk11aa22"
TXID = "20260922T120000Z-01"


def _sidecar(rel: str, kps: list[tuple[str, str, str, str, int]], edges: str = "edges: []") -> str:
    rows = ["schema_version: 1", f"file: {rel}", "knowledge_points:"]
    for kp_id, name, start, end, end_line in kps:
        rows += [
            f"- id: {kp_id}",
            f"  name: {name}",
            "  range:",
            "    start:",
            f"      snippet: '{start}'",
            "      line_hint: 1",
            "    end:",
            f"      snippet: '{end}'",
            f"      line_hint: {end_line}",
        ]
    rows += ["links: []", edges, ""]
    return "\n".join(rows)


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """最小知识库：两篇正文 + 各自的侧车。

    - `notes/a.md`：两个 KP（`a-kp` / `a-second`），正文里**没有** `[[…]]`；
    - `notes/b.md`：一个 KP（`b-kp`）+ **一条指向 `a-kp` 的纯边**，且正文里写着 `[[a-kp]]`
      ⇒ 它是 `a-kp` 的**正文引用者**也是**侧车引用者**（两条预警路径各覆盖一次）。
    """
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria" / "sidecars" / "notes").mkdir(parents=True)
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8", newline="")
    (root / "notes" / "b.md").write_text(B_MD, encoding="utf-8", newline="")
    (root / ".memoria" / "sidecars" / "notes" / "a.memoria.yaml").write_text(
        _sidecar(
            "notes/a.md",
            [
                ("a-kp", "甲知识点", "# A 文档", "注意力机制是核心。", 3),
                ("a-second", "末尾一行", "末尾一行。", "末尾一行。", 5),
            ],
        ),
        encoding="utf-8",
    )
    (root / ".memoria" / "sidecars" / "notes" / "b.memoria.yaml").write_text(
        _sidecar(
            "notes/b.md",
            [("b-kp", "乙知识点", "# B 文档", "见 [[a-kp]] 这篇。", 3)],
            edges="\n".join(["edges:", "- type: reference", "  source_id: b-kp", "  targets:", "  - a-kp"]),
        ),
        encoding="utf-8",
    )
    return root


@pytest.fixture()
def service(kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocumentService:
    """隔离配置目录（装载会走"记录最近打开"，否则写真实 `config/ui-settings.json`）。"""
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(tmp_path / "cfg"))
    return DocumentService(kb_path=str(kb))


def _plan(*ops: dict) -> dict:
    return {"v": 1, "txid": TXID, "intent": "知识点级改动（测试）", "ops": list(ops)}


def _facts(root: Path) -> dict[str, str]:
    """事实源逐文件 sha256（与 `test_agent_file_ops.py` 同口径：排除备份/审计/派生索引/`.bak`）。"""
    facts: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.endswith(".bak") or rel.startswith(".memoria/agent/") or rel.startswith(".memoria/cache/"):
            continue
        if rel in (".memoria/kp_targets.json", ".memoria/images/registry.json"):
            continue
        facts[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return facts


def _codes(rows) -> list[str]:
    return [str(row.get("code")) for row in rows]


def _apply(kb: Path, service: DocumentService, plan: dict) -> dict:
    compiled = compile_plan(str(kb), plan, service=service)
    assert compiled["status"] == "ok", compiled
    done = apply_plan(
        str(kb), plan, session_id=SESSION, txid=TXID,
        base_versions=compiled["base_versions"], service=service,
    )
    return done


# ── ① upsert_edge（纯边）─────────────────────────────────────────────────────


def test_upsert_edge_writes_only_the_sidecar_and_undoes(kb: Path, service: DocumentService) -> None:
    before = _facts(kb)
    body_before = (kb / "notes" / "a.md").read_text(encoding="utf-8")
    plan = _plan(
        {
            "op": "upsert_edge", "op_id": "o1", "file": "notes/a.md",
            "source_id": "a-kp", "target_id": "b-kp", "edge_type": "extend",
        }
    )
    compiled = compile_plan(str(kb), plan, service=service)
    assert [call["primitive"] for call in compiled["calls"]] == ["create_edge"]
    assert compiled["calls"][0]["args"]["edge_type"] == "extend"
    assert _facts(kb) == before, "校验 / 编译**零落盘**"

    done = _apply(kb, service, plan)
    assert done["status"] == "ok", done
    sidecar = load_sidecar_for_md(str(kb / "notes" / "a.md"), str(kb)) or {}
    assert [(e.get("source_id"), e.get("targets"), e.get("type")) for e in sidecar.get("edges") or []] == [
        ("a-kp", ["b-kp"], "extend")
    ]
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == body_before, "纯边**不碰正文**"

    assert restore_batch(str(kb), SESSION, TXID)["status"] == "ok"
    assert _facts(kb) == before


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"source_id": "b-kp", "target_id": "a-second"}, "source_not_in_file"),
        ({"source_id": "a-kp", "target_id": "nope"}, "target_not_found"),
        ({"source_id": "a-kp", "target_id": "b-kp", "edge_type": "contain"}, "bad_edge_type"),
        ({"source_id": "a-kp", "target_id": "a-kp"}, "bad_field"),
        ({"target_id": "b-kp"}, "missing_field"),
    ],
)
def test_upsert_edge_rejections(kb: Path, service: DocumentService, fields: dict, code: str) -> None:
    plan = _plan({"op": "upsert_edge", "op_id": "o1", "file": "notes/a.md", **fields})
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "error", checked
    assert code in _codes(checked["errors"])


def test_upsert_edge_refuses_a_duplicate(kb: Path, service: DocumentService) -> None:
    """`notes/b.md` 的侧车里已经有 `b-kp → a-kp` 那条（其余同型同源同目标）⇒ 计划期就拒。"""
    plan = _plan(
        {"op": "upsert_edge", "op_id": "o1", "file": "notes/b.md", "source_id": "b-kp", "target_id": "a-kp"}
    )
    checked = validate_plan(str(kb), plan, service=service)
    assert _codes(checked["errors"]) == ["edge_exists"]


# ── ② delete_kp ─────────────────────────────────────────────────────────────


def test_delete_kp_warns_about_dangling_references_then_undoes(kb: Path, service: DocumentService) -> None:
    before = _facts(kb)
    body_before = (kb / "notes" / "a.md").read_text(encoding="utf-8")
    plan = _plan({"op": "delete_kp", "op_id": "o1", "file": "notes/a.md", "kp_id": "a-kp"})

    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "ok", checked
    assert _codes(checked["warnings"]) == ["delete_leaves_dangling"]
    assert "notes/b.md" in checked["warnings"][0]["message"], "正文引用者与侧车引用者都要点名"

    done = _apply(kb, service, plan)
    assert done["status"] == "ok", done
    sidecar = load_sidecar_for_md(str(kb / "notes" / "a.md"), str(kb)) or {}
    assert [kp.get("id") for kp in sidecar.get("knowledge_points") or []] == ["a-second"]
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == body_before, "删 KP **不改正文**"

    assert restore_batch(str(kb), SESSION, TXID)["status"] == "ok"
    assert _facts(kb) == before


def test_delete_kp_without_referrers_has_no_warning(kb: Path, service: DocumentService) -> None:
    plan = _plan({"op": "delete_kp", "op_id": "o1", "file": "notes/a.md", "kp_id": "a-second"})
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "ok", checked
    assert checked["warnings"] == []


def test_delete_kp_rejects_unknown_id(kb: Path, service: DocumentService) -> None:
    plan = _plan({"op": "delete_kp", "op_id": "o1", "file": "notes/a.md", "kp_id": "not-there"})
    checked = validate_plan(str(kb), plan, service=service)
    assert _codes(checked["errors"]) == ["kp_not_found"]


# ── ③ rename_kp（全库级联）───────────────────────────────────────────────────


def test_rename_kp_cascades_through_the_library_and_undoes(kb: Path, service: DocumentService) -> None:
    before = _facts(kb)
    plan = _plan({"op": "rename_kp", "op_id": "o1", "old_id": "a-kp", "new_id": "a-core"})

    compiled = compile_plan(str(kb), plan, service=service)
    assert [call["primitive"] for call in compiled["calls"]] == ["rename_kp_id"]
    assert set(compiled["calls"][0]["args"]["affected"]) == {"notes/a.md", "notes/b.md"}, (
        "全库级联的备份集 = 定义它的那篇 + 引用它的那篇（撤销要两篇都能还原）"
    )
    assert _facts(kb) == before, "预演（dry_run）**零落盘**"

    done = _apply(kb, service, plan)
    assert done["status"] == "ok", done
    assert "[[a-core|a-kp]]" in (kb / "notes" / "b.md").read_text(encoding="utf-8"), "正文 wikilink 跟着改"
    a_sidecar = load_sidecar_for_md(str(kb / "notes" / "a.md"), str(kb)) or {}
    assert [kp.get("id") for kp in a_sidecar.get("knowledge_points") or []] == ["a-core", "a-second"]
    b_sidecar = load_sidecar_for_md(str(kb / "notes" / "b.md"), str(kb)) or {}
    assert [(e.get("source_id"), e.get("targets")) for e in b_sidecar.get("edges") or []] == [("b-kp", ["a-core"])]

    assert restore_batch(str(kb), SESSION, TXID)["status"] == "ok"
    assert _facts(kb) == before, "撤销要把**全库**（正文 + 两侧车）逐字节还原"


@pytest.mark.parametrize(
    ("old_id", "new_id", "code"),
    [("nope", "x", "rename_kp_rejected"), ("a-kp", "a-second", "rename_kp_rejected")],
)
def test_rename_kp_rejections(kb: Path, service: DocumentService, old_id: str, new_id: str, code: str) -> None:
    """原 id 不存在 / 新 id 已被占用 —— 都由 `build_kp_index()` 在进入写入循环**之前**判掉。"""
    plan = _plan({"op": "rename_kp", "op_id": "o1", "old_id": old_id, "new_id": new_id})
    checked = validate_plan(str(kb), plan, service=service)
    assert code in _codes(checked["errors"])


def test_rename_kp_must_come_after_content_ops(kb: Path, service: DocumentService) -> None:
    """它全库改写正文里的 id ⇒ 之后的按原文 / 按行号的 op 会活在两套坐标系里（同"动路径"待遇）。"""
    plan = _plan(
        {"op": "rename_kp", "op_id": "o1", "old_id": "a-kp", "new_id": "a-core"},
        {
            "op": "replace_lines", "op_id": "o2", "file": "notes/a.md",
            "range": {"start": 5, "end": 5}, "expect": "末尾一行。", "text": "改过了。",
        },
    )
    checked = validate_plan(str(kb), plan, service=service)
    assert _codes(checked["errors"]) == ["file_ops_must_be_last"]


def test_rename_kp_may_be_followed_by_file_ops(kb: Path, service: DocumentService) -> None:
    """「先改 id → 再挪目录」是合法批：文件级 op 排在它后面照旧允许（顺序规矩只禁**非**文件级 op）。"""
    plan = _plan(
        {"op": "rename_kp", "op_id": "o1", "old_id": "a-kp", "new_id": "a-core"},
        {"op": "move_file", "op_id": "o2", "file": "notes/a.md", "to_dir": "教材"},
    )
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "ok", checked
    assert [call["primitive"] for call in compile_plan(str(kb), plan, service=service)["calls"]] == [
        "rename_kp_id",
        "move_file",
    ]


# ── ④ 读后写闸 + 预览 ────────────────────────────────────────────────────────


def test_observation_gate_covers_kp_ops_with_a_file_but_not_the_library_wide_one(kb: Path) -> None:
    """带 `file` 的两个照旧要"先读后写"；`rename_kp` 没有 `file` ⇒ 天然不入 targets（它的闸是审批卡）。"""
    assert observation.write_targets(
        [
            {"op": "upsert_edge", "file": "notes/a.md"},
            {"op": "delete_kp", "file": "notes/a.md"},
            {"op": "rename_kp", "old_id": "a-kp", "new_id": "a-core"},
        ]
    ) == ["notes/a.md"]
    verdict = observation.gate_ops(str(kb), SESSION, [{"op": "delete_kp", "file": "notes/a.md", "kp_id": "a-kp"}])
    assert verdict is not None and verdict[0] == "FS_NOT_OBSERVED"
    assert observation.gate_ops(str(kb), SESSION, [{"op": "rename_kp", "old_id": "a", "new_id": "b"}]) is None


def test_preview_names_the_new_op_and_stays_read_only(kb: Path, service: DocumentService) -> None:
    before = _facts(kb)
    plan = _plan(
        {"op": "delete_kp", "op_id": "o1", "file": "notes/a.md", "kp_id": "a-second"},
        {"op": "upsert_edge", "op_id": "o2", "file": "notes/a.md", "source_id": "a-second", "target_id": "b-kp"},
    )
    preview = preview_plan(str(kb), plan, service=service)
    assert preview["status"] == "ok", preview
    assert [row["op"] for row in preview["files"][0]["ops"]] == ["delete_kp", "upsert_edge"]
    assert _facts(kb) == before, "`preview_plan()` **零落盘**"


def test_kp_referrers_splits_body_and_sidecar_hits(kb: Path) -> None:
    """纯函数面：`md` 列正文引用者、`sidecar` 列侧车引用者，且 `owner` 那一篇**不进** `sidecar`。"""
    assert kp_referrers(str(kb), "a-kp", owner="notes/a.md") == {
        "md": ["notes/b.md"],
        "sidecar": ["notes/b.md"],
    }
    # 不给 owner ⇒ 定义它的那篇也算侧车引用者（它侧车里那条 KP 本身也是"指向该 id"）
    assert kp_referrers(str(kb), "a-kp") == {
        "md": ["notes/b.md"],
        "sidecar": ["notes/a.md", "notes/b.md"],
    }
    assert kp_referrers(str(kb), "") == {"md": [], "sidecar": []}


# ── ⑤ 真实工具入口往返（走 `propose_write`，不只是直调 apply）────────────────────────
# 教训（AG20 登记）：新加能力必须至少有一例走**真实工具入口**（`ToolRegistry.invoke`）——
# 否则"工具处理器里的闸 / 回执 / 工具说明"与底层实现的分歧无人发现（那条缺口正是这么漏的）。


@pytest.fixture(autouse=True)
def _clean_observations(kb: Path):
    """观察表是**进程内**状态：每个用例前后清干净，免得串味。"""
    observation.clear(str(kb))
    yield
    observation.clear(str(kb))


def _tool_registry(kb: Path) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb), session_id=SESSION))


def _invoke(kb: Path, name: str, **arguments: Any):
    return _tool_registry(kb).invoke(
        ToolCall(id="c1", name=name, arguments=json.dumps(arguments, ensure_ascii=False))
    )


def test_propose_tool_documents_the_three_new_ops(kb: Path) -> None:
    tool = _tool_registry(kb).get(PROPOSE_TOOL_NAME)
    assert tool is not None
    for needle in ("upsert_edge", "delete_kp", "rename_kp", "source_id", "old_id", "new_id", "收尾"):
        assert needle in tool.description, f"提议工具说明里缺 {needle}"


def test_kp_ops_round_trip_through_the_real_tool(kb: Path) -> None:
    """先读（过读后写闸）⇒ 一批里"删一个 KP + 连一条纯边" ⇒ 回执是「已写入」、盘上真的变了。"""
    read = _invoke(kb, "read_document", path="notes/a.md")
    assert read.is_error is False, read.content

    written = _invoke(
        kb, PROPOSE_TOOL_NAME, intent="删掉多余的点、并连一条边",
        ops=[
            {"op": "delete_kp", "op_id": "o1", "file": "notes/a.md", "kp_id": "a-second"},
            {"op": "upsert_edge", "op_id": "o2", "file": "notes/a.md", "source_id": "a-kp", "target_id": "b-kp"},
        ],
    )
    assert written.is_error is False, written.content
    assert written.content.startswith("**已写入**"), written.content
    sidecar = load_sidecar_for_md(str(kb / "notes" / "a.md"), str(kb)) or {}
    assert [kp.get("id") for kp in sidecar.get("knowledge_points") or []] == ["a-kp"]
    assert [(e.get("source_id"), e.get("targets")) for e in sidecar.get("edges") or []] == [("a-kp", ["b-kp"])]


def test_rename_kp_skips_the_read_gate_through_the_real_tool(kb: Path) -> None:
    """它**没有 `file` 字段** ⇒ 读后写闸天然不覆盖（闸按 `file` 收集目标）；它的闸是审批卡 + 收尾规矩。"""
    written = _invoke(
        kb, PROPOSE_TOOL_NAME, intent="全库改 id",
        ops=[{"op": "rename_kp", "op_id": "o1", "old_id": "a-kp", "new_id": "a-core"}],
    )
    assert written.is_error is False, written.content
    assert "[[a-core|a-kp]]" in (kb / "notes" / "b.md").read_text(encoding="utf-8")
