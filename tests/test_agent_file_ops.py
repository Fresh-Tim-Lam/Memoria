"""文件级 op（§7 的 2.4 / 2.5 / 2.6）：`create_file` / `rename_file` / `delete_file` 的离线单测。

钉住的口径：

1. **新建**：文件必须不存在；可带初始正文；落地走 `DocumentService.create_file()`；
   撤销 = 逐字节回到"没有这个文件"。
2. **重命名**：预演（`file_ops.rename_plan()`）列出的**牵动文件集**就是 apply 的 pre-image 备份集
   ⇒ 级联改写过的正文/侧车也能被撤销**逐一还原**（这是本轮最容易漏的一条）。
3. **批内顺序**：`create_file` 可与建点 / 挂链 / 改正文**同批**（`plan._View` 把新文件种进文件集）；
   `rename_file` 只能**收尾**（`rename_must_be_last`）。目标已存在 / 同名 / stem 冲突一律在校验期拒。
4. **删除整篇**（2026-09-22 起提供）：预演（`file_ops.delete_plan()`）算出"哪些 wikilink 会失去落点"
   ⇒ 正文里仍写着 `[[它]]` 的**别的**文档是**硬拦**（`delete_referenced`，可在同批先摘引用）；
   侧车里还挂着的只**警告**（`delete_leaves_edges`）。它也只能**收尾**（`delete_must_be_last`），
   且备份集必须含**它自己的侧车**（撤销要把它一起写回来）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent.apply import apply_plan, compile_plan
from memoria.services.agent.backup import restore_batch
from memoria.services.agent.file_ops import delete_plan, move_plan, rename_plan
from memoria.services.agent.plan import preview_plan, validate_plan
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME, build_kb_tools
from memoria.services.agent.tools.registry import ToolRegistry
from memoria.services.agent.llm.types import ToolCall
from memoria.services.document import DocumentService
from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md

A_MD = "# A 文档\n\n注意力机制是核心。\n\n末尾一行。\n"
B_MD = "# B 文档\n\n见 [[a]] 这篇。\n"
SESSION = "session-20260921T200000Z-bbbb2222"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8", newline="")
    (root / "notes" / "b.md").write_text(B_MD, encoding="utf-8", newline="")
    return root


@pytest.fixture()
def service(kb: Path) -> DocumentService:
    return DocumentService(kb_path=str(kb))


@pytest.fixture()
def api(kb: Path) -> UIAPI:
    return UIAPI(kb_path=str(kb))


def _plan(*ops: dict) -> dict:
    return {"v": 1, "txid": "20260921T200000Z-01", "intent": "文件级改动（测试）", "ops": list(ops)}


def _facts(root: Path) -> dict[str, str]:
    """**事实源**逐文件 sha256：库内 `.md` + 侧车 + manifest + pending。

    刻意排除（都不是"这次写动的正文事实源"）：
    - `.memoria/cache/**`、`.memoria/kp_targets.json` —— 可再生/派生索引（后者 payload 带 `built_at` 时间戳）；
    - `.memoria/agent/**` —— 备份批次与审计流（本来就该变）；
    - `*.bak` —— manifest / pending 原子写的旁路副本（既有行为）；
    - `.memoria/images/registry.json` —— 图片注册表（派生，按需重建；重命名级联会顺带维护它）。
    """
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


# ── ① create_file ────────────────────────────────────────────────────────


def test_create_file_round_trip_and_undo(kb: Path, service: DocumentService) -> None:
    """新建带初始正文 ⇒ 文件出现、正文就是给的内容；撤销 ⇒ 文件消失（逐字节状态还原）。"""
    before = _facts(kb)
    plan = _plan(
        {"op": "create_file", "op_id": "o1", "file": "notes/新篇.md", "body": "# 新篇\n\n第一段。\n"}
    )
    compiled = compile_plan(str(kb), plan, service=service)
    assert [call["primitive"] for call in compiled["calls"]] == ["create_file"]

    done = apply_plan(
        str(kb), plan, session_id=SESSION, txid="20260921T200000Z-01",
        base_versions=compiled["base_versions"], service=service,
    )
    assert done["status"] == "ok", done
    created = kb / "notes" / "新篇.md"
    assert created.read_text(encoding="utf-8") == "# 新篇\n\n第一段。\n"

    undone = restore_batch(str(kb), SESSION, "20260921T200000Z-01")
    assert undone["status"] == "ok", undone
    assert not created.exists()  # 新建文件的撤销 = 删除（备份里记的是 existed:false）
    assert _facts(kb) == before


def test_create_file_preview_lists_initial_body(kb: Path, service: DocumentService) -> None:
    plan = _plan({"op": "create_file", "op_id": "o1", "file": "x.md", "body": "# X\n\n一行。\n"})
    preview = preview_plan(str(kb), plan, service=service)
    entry = preview["files"][0]["ops"][0]
    assert preview["files"][0]["file"] == "x.md"
    assert entry["created"] == "x.md" and entry["diff_available"] is True
    assert [row["after"] for row in entry["diff"]] == ["# X", "", "一行。"]


def test_create_file_rejects_existing_path(kb: Path, service: DocumentService) -> None:
    plan = _plan({"op": "create_file", "op_id": "o1", "file": "notes/a.md"})
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "error"
    assert [e["code"] for e in checked["errors"]] == ["file_exists"]


# ── ② rename_file（含级联与"备份集完整"）─────────────────────────────────


def test_rename_plan_lists_cascade_and_apply_undo_restores_bytes(kb: Path, service: DocumentService) -> None:
    """重命名会改写**别的正文**里的 `[[a]]` ⇒ 预演要列出它、备份要含它，撤销才能逐字节还原。"""
    before = _facts(kb)
    cascade = rename_plan(str(kb), "notes/a.md", "注意力")
    assert cascade["ok"] is True
    assert cascade["to"] == "notes/注意力.md"
    assert cascade["md_files"] == ["notes/b.md"]  # 只有 b.md 引用 [[a]]
    assert "notes/b.md" in cascade["affected"]

    plan = _plan({"op": "rename_file", "op_id": "o1", "file": "notes/a.md", "new_name": "注意力"})
    compiled = compile_plan(str(kb), plan, service=service)
    call = compiled["calls"][0]
    assert call["primitive"] == "rename_file"
    # 备份集（受影响文件集）必须含级联文件与其侧车
    assert "notes/b.md" in compiled["files"] and "notes/a.md" in compiled["files"]
    assert "notes/注意力.md" in compiled["files"]

    done = apply_plan(
        str(kb), plan, session_id=SESSION, txid="20260921T200001Z-02",
        base_versions=compiled["base_versions"], service=service,
    )
    assert done["status"] == "ok", done
    assert not (kb / "notes" / "a.md").exists()
    assert (kb / "notes" / "注意力.md").read_text(encoding="utf-8") == A_MD
    assert "[[注意力|a]]" in (kb / "notes" / "b.md").read_text(encoding="utf-8")  # 级联真的发生

    undone = restore_batch(str(kb), SESSION, "20260921T200001Z-02")
    assert undone["status"] == "ok", undone
    assert _facts(kb) == before  # 文件回来了、b.md 的引用也改回去了


def test_rename_preview_shows_path_change_and_cascade(kb: Path, service: DocumentService) -> None:
    plan = _plan({"op": "rename_file", "op_id": "o1", "file": "notes/a.md", "new_name": "注意力"})
    entry = preview_plan(str(kb), plan, service=service)["files"][0]["ops"][0]
    assert entry["rename"] == {"from": "notes/a.md", "to": "notes/注意力.md"}
    assert entry["cascade"] == ["notes/b.md"]
    assert entry["diff"][0] == {"line": None, "before": "notes/a.md", "after": "notes/注意力.md"}
    assert any("引用将改写：notes/b.md" == row["after"] for row in entry["diff"])


@pytest.mark.parametrize(
    ("old", "new_name", "code"),
    [
        ("notes/a.md", "a", "bad_field"),  # 同名（没有变化）
        ("notes/a.md", "b.md", "target_exists"),  # 目标已在同目录占用
        ("notes/a.md", "b/../c", "bad_field"),  # 带路径分隔符
    ],
)
def test_rename_rejects_before_any_write(kb: Path, service: DocumentService, old: str, new_name: str, code: str) -> None:
    before = _facts(kb)
    checked = validate_plan(str(kb), _plan({"op": "rename_file", "op_id": "o1", "file": old, "new_name": new_name}), service=service)
    assert checked["status"] == "error"
    assert checked["errors"][0]["code"] == code
    assert _facts(kb) == before


# ── ③ 批内顺序（写机制放开之后）+ ④ 不提供删除 ────────────────────────────────


def test_create_file_may_share_a_batch_with_kp_and_links(kb: Path, service: DocumentService) -> None:
    """**新建 + 建点 + 挂链同一批**（写机制全线放开的直接收益）。

    新建的 `notes/新文档.md` 被 `plan._View` 立刻"种"进文件集 ⇒ 同批后面的 `upsert_kp`（按新文件
    的行号）与 `attach_links`（目标正好是它的 stem）都成立；落地后侧车也在。旧实现这里报
    `file_op_alone` —— 用户得为此提两批、点两次确认卡。撤销则**一并**回到"没有这个文件"。
    """
    before = _facts(kb)
    txid = "20260921T200001Z-01"
    plan = _plan(
        {"op": "create_file", "op_id": "o1", "file": "notes/新文档.md", "body": "# 新文档\n\n正文一段。\n"},
        {
            "op": "upsert_kp",
            "op_id": "o2",
            "file": "notes/新文档.md",
            "kp_id": "newdoc",
            "name": "新文档",
            "range": {"start": {"line": 1}, "end": {"line": 3}},
        },
        {
            "op": "attach_links",
            "op_id": "o3",
            "file": "notes/a.md",
            "anchor_text": "注意力机制",
            "targets": ["新文档"],
            "occurrences": [{"line": 3}],
        },
    )
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "ok", checked
    done = apply_plan(str(kb), plan, session_id=SESSION, txid=txid, service=service)
    assert done["status"] == "ok", done
    assert (kb / "notes" / "新文档.md").is_file()
    assert "[[注意力机制]]" in (kb / "notes" / "a.md").read_text(encoding="utf-8")
    # 侧车是"知识点存在"的唯一凭据（§1）：新建文件那一侧也要真的写出来
    new_sidecar = load_sidecar_for_md(str(kb / "notes" / "新文档.md"), str(kb)) or {}
    assert [kp.get("id") for kp in new_sidecar.get("knowledge_points", [])] == ["newdoc"]
    a_sidecar = load_sidecar_for_md(str(kb / "notes" / "a.md"), str(kb)) or {}
    assert [link.get("anchor_text") for link in a_sidecar.get("links", [])] == ["注意力机制"]

    undone = restore_batch(str(kb), SESSION, txid)
    assert undone["status"] == "ok", undone
    assert _facts(kb) == before  # 新文件、它的侧车、manifest / pending 条目**一起**回退


def test_rename_must_be_the_last_op(kb: Path, service: DocumentService) -> None:
    """`rename_file` 只能**收尾**：它重写全库 `[[旧名]]` 引用并搬路径 ⇒ 之后不能再有别的 op。

    这是**语义**约束（不是审批约束）：它后面若还有 op，"路径"与"引用是否可解析"就同时活在两套
    坐标系里。而它**之前**的改动照常可以同批（先改正文 / 建点，最后定名）。
    """
    edit = {
        "op": "replace_lines",
        "op_id": "o2",
        "file": "notes/b.md",
        "range": {"start": 3, "end": 3},
        "expect": "见 [[a]] 这篇。",
        "text": "见 [[a]] 这篇（改）。",
    }
    rename = {"op": "rename_file", "op_id": "o1", "file": "notes/a.md", "new_name": "注意力"}

    early = validate_plan(str(kb), _plan(rename, edit), service=service)
    assert early["status"] == "error"
    codes = [e["code"] for e in early["errors"]]
    assert "rename_must_be_last" in codes
    # 2026-09-22 起还有一条更通用的规矩（文件级 op 之后不得再有别的 op ⇒ 同一个错误会报两条，都在指路）
    assert "file_ops_must_be_last" in codes

    late = validate_plan(str(kb), _plan(edit, rename), service=service)
    assert late["status"] == "ok", late


# ── ④ delete_file（删整篇：悬空引用先拦 / 侧车引用只警告 / 备份含侧车）────────────


def test_delete_plan_lists_referrers_and_the_backup_set(kb: Path) -> None:
    """预演：`ids` 是"会失去落点的 wikilink"，`referrers_md` 是仍写着它们的正文。"""
    plan = delete_plan(str(kb), "notes/a.md")
    assert plan["ok"] is True
    assert plan["ids"] == ["a"]
    assert plan["referrers_md"] == ["notes/b.md"]  # b.md 正文里还写着 [[a]]
    assert plan["referrers_sidecar"] == []
    # 备份集 = 被删正文 + 它自己的侧车（两者都会被删掉）；引用者**不**在其中（删除不改写它们）
    assert set(plan["affected"]) == {"notes/a.md", ".memoria/sidecars/notes/a.memoria.yaml"}


def test_delete_rejects_while_another_doc_still_references_it(kb: Path, service: DocumentService) -> None:
    """正文里还写着 `[[a]]` ⇒ 硬拦（先摘引用再删），且**零写入**。"""
    before = _facts(kb)
    checked = validate_plan(
        str(kb), _plan({"op": "delete_file", "op_id": "o1", "file": "notes/a.md"}), service=service
    )
    assert checked["status"] == "error"
    assert [e["code"] for e in checked["errors"]] == ["delete_referenced"]
    assert "notes/b.md" in checked["errors"][0]["message"]
    assert (kb / "notes" / "a.md").is_file()  # 拒 = 没删
    assert _facts(kb) == before


def test_delete_allowed_once_the_same_batch_drops_the_reference(kb: Path, service: DocumentService) -> None:
    """同批先把引用摘掉、再删 ⇒ 放行；撤销要把**被删的正文与其侧车**逐字节写回来。"""
    before = _facts(kb)
    txid = "20260921T200003Z-01"
    plan = _plan(
        {
            "op": "replace_lines",
            "op_id": "o1",
            "file": "notes/b.md",
            "range": {"start": 3, "end": 3},
            "expect": "见 [[a]] 这篇。",
            "text": "见那篇笔记。",
        },
        {"op": "delete_file", "op_id": "o2", "file": "notes/a.md"},
    )
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "ok", checked
    compiled = compile_plan(str(kb), plan, service=service)
    assert [call["primitive"] for call in compiled["calls"]] == ["edit_body", "delete_file"]

    done = apply_plan(
        str(kb), plan, session_id=SESSION, txid=txid,
        base_versions=compiled["base_versions"], service=service,
    )
    assert done["status"] == "ok", done
    assert not (kb / "notes" / "a.md").exists()
    assert (kb / "notes" / "b.md").read_text(encoding="utf-8") == "# B 文档\n\n见那篇笔记。\n"

    undone = restore_batch(str(kb), SESSION, txid)
    assert undone["status"] == "ok", undone
    assert _facts(kb) == before  # 正文回来了、b.md 也回到原文（删除不改写引用者）


def test_delete_must_be_the_last_op(kb: Path, service: DocumentService) -> None:
    """`delete_file` 只能**收尾**（与 `rename_file` 同一条语义约束），但它之前的 op 可以同批。"""
    (kb / "notes" / "solo.md").write_text("# 独篇\n\n一段。\n", encoding="utf-8", newline="")
    edit = {
        "op": "replace_lines",
        "op_id": "o2",
        "file": "notes/solo.md",
        "range": {"start": 3, "end": 3},
        "expect": "一段。",
        "text": "一段（改）。",
    }
    delete = {"op": "delete_file", "op_id": "o1", "file": "notes/solo.md"}

    early = validate_plan(str(kb), _plan(delete, edit), service=service)
    codes = [e["code"] for e in early["errors"]]
    assert "delete_must_be_last" in codes
    assert validate_plan(str(kb), _plan(edit, delete), service=service)["status"] == "ok"


def test_delete_warns_when_only_sidecars_still_point_at_it(kb: Path, service: DocumentService) -> None:
    """正文已不引用、但**侧车**里还挂着指向它（KP id `a`）⇒ 只警告，不拦。"""
    (kb / "notes" / "b.md").write_text("# B 文档\n\n见那篇笔记。\n", encoding="utf-8", newline="")
    save_sidecar_for_md(
        str(kb / "notes" / "a.md"),
        str(kb),
        {
            "schema_version": 1,
            "file": "notes/a.md",
            "knowledge_points": [
                {
                    "id": "a",
                    "name": "A",
                    "range": {
                        "start_line": 1,
                        "end_line": 1,
                        "start_snippet": "# A 文档",
                        "end_snippet": "# A 文档",
                    },
                }
            ],
        },
    )
    save_sidecar_for_md(
        str(kb / "notes" / "b.md"),
        str(kb),
        {
            "schema_version": 1,
            "file": "notes/b.md",
            "links": [{"anchor_text": "那篇", "source_id": "", "targets": ["a"], "lines": [3]}],
        },
    )
    preview = preview_plan(
        str(kb), _plan({"op": "delete_file", "op_id": "o1", "file": "notes/a.md"}), service=service
    )
    assert preview["status"] == "ok", preview
    assert [w["code"] for w in preview["warnings"]] == ["delete_leaves_edges"]
    entry = preview["files"][0]["ops"][0]
    assert entry["delete"] == {"path": "notes/a.md", "ids": ["a"]}
    assert entry["diff"][0] == {"line": None, "before": "notes/a.md", "after": None}
    assert any(row["after"] == "将失去落点：[[a]]" for row in entry["diff"])


# ── ⑤ move_file（跨目录搬整篇：级联侧车 / 引用不断 / 文件相对引用先拦）────────────────


def test_move_plan_reports_from_to_and_backup_set(kb: Path) -> None:
    """预演：`from`/`to` + 备份集含**源与目标两侧**；同目录 / 已存在目标一律拒。"""
    plan = move_plan(str(kb), "notes/a.md", "notes/phrases")
    assert plan["ok"] is True
    assert plan["from"] == "notes/a.md" and plan["to"] == "notes/phrases/a.md"
    assert {"notes/a.md", "notes/phrases/a.md"} <= set(plan["affected"])
    # 两侧的镜像侧车都要在备份集里（源侧会被搬走、目标侧会新建 ⇒ 撤销要两边都能还原）
    assert ".memoria/sidecars/notes/a.memoria.yaml" in plan["affected"]
    assert ".memoria/sidecars/notes/phrases/a.memoria.yaml" in plan["affected"]

    same = move_plan(str(kb), "notes/a.md", "notes")
    assert same["ok"] is False and same["code"] == "same_dir"
    assert move_plan(str(kb), "notes/a.md", "notes/b.md")["ok"] is True  # 目录名不必先存在
    assert move_plan(str(kb), "notes/missing.md", "notes/phrases")["code"] == "file_not_found"


def test_move_moves_md_and_sidecar_and_undo_restores_bytes(kb: Path, service: DocumentService) -> None:
    """核心往返：正文**一字未改**、侧车跟着搬且 `file:` 改到新路径、`[[a]]` 引用**不改写**、撤销逐字节还原。"""
    save_sidecar_for_md(
        str(kb / "notes" / "a.md"),
        str(kb),
        {
            "schema_version": 1,
            "file": "notes/a.md",
            "knowledge_points": [
                {
                    "id": "a",
                    "name": "A",
                    "range": {
                        "start_line": 1,
                        "end_line": 1,
                        "start_snippet": "# A 文档",
                        "end_snippet": "# A 文档",
                    },
                }
            ],
        },
    )
    before = _facts(kb)
    txid = "20260922T210000Z-01"
    plan = _plan({"op": "move_file", "op_id": "o1", "file": "notes/a.md", "to_dir": "notes/phrases"})
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "ok", checked
    compiled = compile_plan(str(kb), plan, service=service)
    assert [call["primitive"] for call in compiled["calls"]] == ["move_file"]

    done = apply_plan(
        str(kb), plan, session_id=SESSION, txid=txid,
        base_versions=compiled["base_versions"], service=service,
    )
    assert done["status"] == "ok", done
    assert not (kb / "notes" / "a.md").exists()
    moved = kb / "notes" / "phrases" / "a.md"
    assert moved.read_text(encoding="utf-8") == A_MD, "正文**一字未改**"
    assert (kb / "notes" / "b.md").read_text(encoding="utf-8") == B_MD, "`[[a]]` 按 stem 寻址 ⇒ 不必改写"
    sc = kb / ".memoria" / "sidecars" / "notes" / "phrases" / "a.memoria.yaml"
    assert sc.is_file(), "侧车跟着搬到镜像布局的新路径"
    assert (load_sidecar_for_md(str(moved), str(kb)) or {}).get("file") == "notes/phrases/a.md"

    undone = restore_batch(str(kb), SESSION, txid)
    assert undone["status"] == "ok", undone
    assert _facts(kb) == before, "撤销把源/目标两侧（含侧车）逐字节还原"


def test_move_auto_creates_the_target_dir(kb: Path, service: DocumentService) -> None:
    """目标目录不存在 ⇒ 自动建（与 `create_file` 的"父目录自动建"同口径）。"""
    assert not (kb / "notes" / "deep" / "nested").exists()
    plan = _plan({"op": "move_file", "op_id": "o1", "file": "notes/a.md", "to_dir": "notes/deep/nested"})
    done = apply_plan(str(kb), plan, session_id=SESSION, txid="20260922T210001Z-01", service=service)
    assert done["status"] == "ok", done
    assert (kb / "notes" / "deep" / "nested" / "a.md").is_file()


def test_move_is_refused_when_the_body_uses_file_relative_refs(kb: Path, service: DocumentService) -> None:
    """`![x](img/a.png)` 这类**按文件所在目录**解析的引用 ⇒ 拦（`move_breaks_relative_refs`），零写入。"""
    (kb / "notes" / "img").mkdir()
    (kb / "notes" / "img" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (kb / "notes" / "a.md").write_text(
        "# A 文档\n\n![图](img/a.png)\n\n末尾一行。\n", encoding="utf-8", newline=""
    )
    before = _facts(kb)
    checked = validate_plan(
        str(kb), _plan({"op": "move_file", "op_id": "o1", "file": "notes/a.md", "to_dir": "notes/phrases"}),
        service=service,
    )
    assert checked["status"] == "error"
    assert [e["code"] for e in checked["errors"]] == ["move_breaks_relative_refs"]
    assert "img/a.png" in checked["errors"][0]["message"]
    assert _facts(kb) == before


def test_move_allows_root_relative_refs(kb: Path, service: DocumentService) -> None:
    """`.memoria/images/x.png` 这种**库根相对**写法（Memoria 图片引用的规范形态）⇒ 不算文件相对，放行。"""
    images = kb / ".memoria" / "images"
    images.mkdir(parents=True, exist_ok=True)
    (images / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (kb / "notes" / "a.md").write_text(
        '# A 文档\n\n![图](.memoria/images/x.png)\n\n末尾一行。\n', encoding="utf-8", newline=""
    )
    plan = _plan({"op": "move_file", "op_id": "o1", "file": "notes/a.md", "to_dir": "notes/phrases"})
    assert validate_plan(str(kb), plan, service=service)["status"] == "ok"
    done = apply_plan(str(kb), plan, session_id=SESSION, txid="20260922T210002Z-01", service=service)
    assert done["status"] == "ok", done
    assert (kb / "notes" / "phrases" / "a.md").is_file()


def test_move_may_repeat_in_one_batch_but_later_ops_are_rejected(kb: Path, service: DocumentService) -> None:
    """`move_file` 可以**连排多条**（各自动自己的文件）；但文件级 op 之后不能再有别类 op。"""
    two_moves = _plan(
        {"op": "move_file", "op_id": "o1", "file": "notes/a.md", "to_dir": "notes/phrases"},
        {"op": "move_file", "op_id": "o2", "file": "notes/b.md", "to_dir": "notes/phrases"},
    )
    checked = validate_plan(str(kb), two_moves, service=service)
    assert checked["status"] == "ok", checked
    done = apply_plan(
        str(kb), two_moves, session_id=SESSION, txid="20260922T210003Z-01", service=service
    )
    assert done["status"] == "ok", done
    assert (kb / "notes" / "phrases" / "a.md").is_file()
    assert (kb / "notes" / "phrases" / "b.md").is_file()

    mixed = _plan(
        {"op": "move_file", "op_id": "o1", "file": "notes/phrases/a.md", "to_dir": "notes"},
        {
            "op": "replace_lines",
            "op_id": "o2",
            "file": "notes/b.md",
            "range": {"start": 3, "end": 3},
            "expect": "见 [[a]] 这篇。",
            "text": "见 [[a]] 这篇（改）。",
        },
    )
    bad = validate_plan(str(kb), mixed, service=service)
    assert bad["status"] == "error"
    assert "file_ops_must_be_last" in [e["code"] for e in bad["errors"]]


def test_move_preview_shows_path_change(kb: Path, service: DocumentService) -> None:
    plan = _plan({"op": "move_file", "op_id": "o1", "file": "notes/a.md", "to_dir": "notes/phrases"})
    entry = preview_plan(str(kb), plan, service=service)["files"][0]["ops"][0]
    assert entry["move"] == {"from": "notes/a.md", "to": "notes/phrases/a.md"}
    assert entry["diff"] == [
        {"line": None, "before": "notes/a.md", "after": "notes/phrases/a.md"}
    ]


def test_propose_tool_documents_move_file(kb: Path) -> None:
    tool = ToolRegistry(build_kb_tools(str(kb))).get(PROPOSE_TOOL_NAME)
    assert tool is not None
    for needle in ("move_file", "to_dir", "move_breaks_relative_refs", "连排"):
        assert needle in tool.description, f"提议工具说明里缺 {needle}"


# ── ⑥ 移动的 `to_dir` 归一化（2026-09-22 真机取证：`""` 与 `.` 都表示库根）────────────────
# 真机（`docs/example/AAA_Vocab` 会话 23:08）里模型两种都试过、两种都失败：
# `to_dir=""` 被计划期判 `path_rejected`（而工具说明明写"空串 = 库根"）、`to_dir="."` 计划期放行
# 但落地期被 `move_file_document()` 当"系统/隐藏目录"拒掉 ⇒ 模型只能用 `tmp-move/` 当中转绕路。
# 修法 = `file_ops.normalize_target_dir()` 收口，计划期（`move_plan`）与落地期（`apply_move_file`）
# 都调它；**真正的**隐藏目录（`.memoria` 之类）照旧拒。


@pytest.mark.parametrize("to_dir", ["", ".", "./", "\\"])
def test_move_file_treats_root_spellings_as_library_root(
    kb: Path, service: DocumentService, to_dir: str
) -> None:
    """`""` / `.` / `./` / 反斜杠 ⇒ 都移到**库根**；且计划期与落地期口径一致。"""
    plan = _plan({"op": "move_file", "op_id": "o1", "file": "notes/b.md", "to_dir": to_dir})
    compiled = compile_plan(str(kb), plan, service=service)
    assert compiled["status"] == "ok", compiled
    assert move_plan(str(kb), "notes/b.md", to_dir)["ok"] is True, "计划期必须放行"

    done = apply_plan(
        str(kb), plan, session_id=SESSION, txid="20260921T200002Z-01",
        base_versions=compiled["base_versions"], service=service,
    )
    assert done["status"] == "ok", done
    assert (kb / "b.md").is_file(), f"to_dir={to_dir!r} 应当落到库根"
    assert not (kb / "notes" / "b.md").exists()


def test_move_file_still_refuses_real_hidden_dirs(kb: Path, service: DocumentService) -> None:
    """归一化**不代替**越界校验：`.memoria` 这类真·隐藏/系统目录照旧拒。"""
    plan = _plan({"op": "move_file", "op_id": "o1", "file": "notes/b.md", "to_dir": ".memoria"})
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "error", checked
    assert str(checked["errors"][0]["message"]).strip(), "必须给出理由"


# ── ⑥ 图片引用行（§7 4.1：只插引用，不做入库/属性/删除）──────────────────────────────


def test_insert_image_ref_writes_one_line_and_undo_restores(kb: Path, service: DocumentService) -> None:
    images = kb / ".memoria" / "images"
    images.mkdir(parents=True, exist_ok=True)
    (images / "结构图.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # 名字含中文 ⇒ 应写成尖括号形式
    before = _facts(kb)

    plan = _plan(
        {
            "op": "insert_image_ref",
            "op_id": "o1",
            "file": "notes/a.md",
            "after": 1,
            "expect": "# A 文档",
            "path": ".memoria/images/结构图.png",
            "alt": "结构图",
            "attrs": "width=300,align=center",
        }
    )
    preview = preview_plan(str(kb), plan, service=service)
    entry = preview["files"][0]["ops"][0]
    assert entry["image"] == ".memoria/images/结构图.png"
    added = [row["after"] for row in entry["diff"] if row["after"] is not None]
    assert added == ['![结构图](<.memoria/images/结构图.png> "width=300,align=center")']

    done = apply_plan(str(kb), plan, session_id=SESSION, txid="20260921T200002Z-03", service=service)
    assert done["status"] == "ok", done
    text = (kb / "notes" / "a.md").read_text(encoding="utf-8")
    assert '![结构图](<.memoria/images/结构图.png> "width=300,align=center")' in text
    assert text.splitlines()[0] == "# A 文档" and text.splitlines()[1].startswith("![结构图]")

    undone = restore_batch(str(kb), SESSION, "20260921T200002Z-03")
    assert undone["status"] == "ok" and _facts(kb) == before


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"path": "../secret.png"}, "path_rejected"),
        ({"path": "/abs/x.png"}, "path_rejected"),
        ({"path": ".memoria/images/none.png"}, "image_not_found"),
        ({"path": "notes/a.md"}, "bad_field"),  # 不是图片扩展名
        ({"path": ""}, "missing_field"),
    ],
)
def test_insert_image_ref_rejects_bad_path(kb: Path, service: DocumentService, patch: dict, code: str) -> None:
    op = {
        "op": "insert_image_ref",
        "op_id": "o1",
        "file": "notes/a.md",
        "after": 1,
        "expect": "# A 文档",
        "path": ".memoria/images/x.png",
    }
    op.update(patch)
    checked = validate_plan(str(kb), _plan(op), service=service)
    assert checked["status"] == "error"
    assert checked["errors"][0]["code"] == code, checked["errors"]


# ── ⑦ 工具面 / RPC 往返 ─────────────────────────────────────────────────


def test_propose_tool_documents_file_ops(kb: Path) -> None:
    registry = ToolRegistry(build_kb_tools(str(kb)))
    tool = registry.get(PROPOSE_TOOL_NAME)
    assert tool is not None
    # 写机制放开后：`create_file` 可以同批，只有 `rename_file` / `delete_file` 有顺序要求（收尾）
    for needle in ("create_file", "rename_file", "delete_file", "new_name", "最后一条", "不要拆批"):
        assert needle in tool.description, f"提议工具说明里缺 {needle}"

    result = registry.invoke(
        ToolCall(
            id="c1",
            name=PROPOSE_TOOL_NAME,
            arguments=json.dumps(
                {"intent": "新建一篇", "ops": [{"op": "create_file", "file": "new.md", "body": "# N\n"}]}
            ),
        )
    )
    assert result.is_error is False, result.content
    assert result.content.startswith("**已写入**")  # 写机制放开后：一次调用即落盘


def test_create_file_rpc_round_trip(kb: Path, api: UIAPI) -> None:
    plan = _plan({"op": "create_file", "op_id": "o1", "file": "notes/新篇.md", "body": "# 新篇\n"})
    preview = api.agent_plan_preview(plan)
    assert preview["status"] == "ok", preview
    done = api.agent_plan_apply(plan, None, None, preview["base_versions"])
    assert done["status"] == "ok", done
    assert (kb / "notes" / "新篇.md").read_text(encoding="utf-8") == "# 新篇\n"
    undone = api.agent_plan_undo(None, done["session_id"], done["txid"])
    assert undone["status"] == "ok", undone
    assert not (kb / "notes" / "新篇.md").exists()
