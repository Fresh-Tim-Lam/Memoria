"""文件级 op（§7 的 2.4 / 2.6）：`create_file` / `rename_file` 的离线单测。

钉住的口径：

1. **新建**：文件必须不存在；可带初始正文；落地走 `DocumentService.create_file()`；
   撤销 = 逐字节回到"没有这个文件"。
2. **重命名**：预演（`file_ops.rename_plan()`）列出的**牵动文件集**就是 apply 的 pre-image 备份集
   ⇒ 级联改写过的正文/侧车也能被撤销**逐一还原**（这是本轮最容易漏的一条）。
3. **两条硬规矩**：文件级 op 必须**单独成批**（`file_op_alone`）；目标已存在 / 同名 / stem 冲突
   一律在先校验期拒。
4. **不提供删除**：`delete_file` 不在已知 op 表里 ⇒ 提了就被 `unknown_op` 拒（设计里属「默认关」）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent.apply import apply_plan, compile_plan
from memoria.services.agent.backup import restore_batch
from memoria.services.agent.file_ops import rename_plan
from memoria.services.agent.plan import KNOWN_OPS, preview_plan, validate_plan
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME, build_kb_tools
from memoria.services.agent.tools.registry import ToolRegistry
from memoria.services.agent.llm.types import ToolCall
from memoria.services.document import DocumentService

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


# ── ③ 两条硬规矩 + ④ 不提供删除 ──────────────────────────────────────────


def test_file_ops_must_stand_alone(kb: Path, service: DocumentService) -> None:
    """文件级 op 与别的 op 同批 ⇒ 拒（`file_op_alone`），并提示分成两批。"""
    plan = _plan(
        {"op": "create_file", "op_id": "o1", "file": "x.md", "body": "# X\n"},
        {
            "op": "attach_links",
            "op_id": "o2",
            "file": "notes/a.md",
            "anchor_text": "注意力机制",
            "targets": ["a"],
            "occurrences": [{"line": 3}],
        },
    )
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "error"
    assert [e["code"] for e in checked["errors"]] == ["file_op_alone"]


def test_delete_file_is_not_a_known_op(kb: Path, service: DocumentService) -> None:
    """删除文件本轮不提供（设计属「默认关」）：提了即 `unknown_op`，且**没有任何写**。"""
    assert "delete_file" not in KNOWN_OPS
    before = _facts(kb)
    checked = validate_plan(str(kb), _plan({"op": "delete_file", "op_id": "o1", "file": "notes/a.md"}), service=service)
    assert checked["status"] == "error"
    assert checked["errors"][0]["code"] == "unknown_op"
    assert _facts(kb) == before


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
    for needle in ("create_file", "rename_file", "new_name", "单独成一批", "删除文件本轮不提供"):
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
    assert "尚未写入" in result.content


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
