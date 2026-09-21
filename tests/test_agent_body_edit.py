"""W 线第二步（**改正文**）：行级原语 `kb.file.edit` + 三个 op 的离线单测。

设计来源：`docs/design/agent-plugin-design.md §7` 的 2.1 / 2.2 / 2.3（改 / 插 / 删正文段落）——
那三行都标着「需要新原语 `kb.file.edit`」，本轮把它与 `replace_lines` / `insert_lines` /
`delete_lines` 三个 op 一起落地。

钉住的四条口径：

1. **只有被点名的行会变**：其余行**逐字节**保持（含行尾风格、末尾有无换行、"最后一行没有换行"）；
2. **`expect` 是硬门槛**：与盘上原文不符即拒（`expect_mismatch`），不猜、不改、不写；
3. **多条编辑按行号从大到小应用** ⇒ 每条的行号都以"编辑前"的正文为准；重叠即拒；
4. **预览与落地同一函数**（`body_edit.splice`）⇒ 卡片上看到的就是要写下去的那几行。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent.apply import apply_plan, compile_plan
from memoria.services.agent.backup import restore_batch
from memoria.services.agent.body_edit import (
    EditError,
    check_edit,
    normalize_edits,
    splice,
)
from memoria.services.agent.plan import preview_plan, validate_plan
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME, build_kb_tools
from memoria.services.agent.tools.registry import ToolRegistry
from memoria.services.agent.llm.types import ToolCall
from memoria.services.document import DocumentService

A_MD = "# A 文档\n\n注意力机制是核心。\n\n末尾一行。\n"
SESSION = "session-20260921T101500Z-aaaa1111"
TXID = "20260921T101500Z-01"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8", newline="")
    return root


@pytest.fixture()
def service(kb: Path) -> DocumentService:
    return DocumentService(kb_path=str(kb))


@pytest.fixture()
def api(kb: Path) -> UIAPI:
    return UIAPI(kb_path=str(kb))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plan(*ops: dict) -> dict:
    return {"v": 1, "txid": TXID, "intent": "改正文（测试）", "ops": list(ops)}


def _replace(start: int, end: int, expect: str, text: str, op_id: str = "o1") -> dict:
    return {
        "op": "replace_lines",
        "op_id": op_id,
        "file": "notes/a.md",
        "range": {"start": {"line": start}, "end": {"line": end}},
        "expect": expect,
        "text": text,
    }


# ── ① `splice()` 本身：字节保真 + 自检 ─────────────────────────────────────


def test_splice_replaces_only_the_named_lines() -> None:
    """未触及的行逐字节不变（含行尾风格与"最后一行没有换行"）。"""
    assert splice("a\nb\nc\n", [{"mode": "replace", "start": 2, "end": 2, "expect": "b", "text": "B"}])[0] == "a\nB\nc\n"
    assert splice("a\r\nb\r\nc", [{"mode": "replace", "start": 2, "end": 2, "expect": "b", "text": "B"}])[0] == "a\r\nB\r\nc"
    assert splice("a\nb", [{"mode": "delete", "start": 2, "end": 2, "expect": "b"}])[0] == "a"
    assert splice("a\nb", [{"mode": "insert", "after": 1, "expect": "a", "text": "X"}])[0] == "a\nX\nb"
    assert splice("a\nb\n", [{"mode": "insert", "after": 0, "expect": "", "text": "X"}])[0] == "X\na\nb\n"


def test_splice_applies_multiple_edits_bottom_up() -> None:
    """多条编辑：行号都以"编辑前"为准（内部从大到小）⇒ 结果与逐条手算一致。"""
    body = "a\nb\nc\n"
    edits = [
        {"mode": "replace", "start": 1, "end": 1, "expect": "a", "text": "A1"},
        {"mode": "replace", "start": 3, "end": 3, "expect": "c", "text": "C1"},
    ]
    assert splice(body, edits)[0] == "A1\nb\nC1\n"
    assert splice(body, edits)[1] == [1, 3]


def test_splice_reports_line_diff_with_nulls() -> None:
    """diff 行沿用确认卡形状：删除给 `after: null`、新增给 `before: null`。"""
    _body, _changed, diff = splice("a\nb\nc\n", [{"mode": "replace", "start": 2, "end": 2, "expect": "b", "text": "B1\nB2"}])
    assert diff == [
        {"line": 2, "before": "b", "after": None},
        {"line": 2, "before": None, "after": "B1"},
        {"line": 3, "before": None, "after": "B2"},
    ]


@pytest.mark.parametrize(
    ("edit", "code"),
    [
        ({"mode": "delete", "start": 2, "end": 2, "expect": "zzz"}, "expect_mismatch"),
        ({"mode": "delete", "start": 9, "end": 9, "expect": ""}, "range_out_of_bounds"),
        ({"mode": "insert", "after": 9, "expect": "x", "text": "X"}, "range_out_of_bounds"),
        ({"mode": "insert", "after": 0, "expect": "x", "text": "X"}, "bad_field"),
        ({"mode": "replace", "start": 1, "end": 1, "expect": "a", "text": "  "}, "empty_text"),
        ({"mode": "wat", "start": 1, "end": 1, "expect": "a"}, "bad_field"),
    ],
)
def test_splice_rejects_bad_edits(edit: dict, code: str) -> None:
    with pytest.raises(EditError) as err:
        splice("a\nb\nc\n", [edit])
    assert err.value.code == code


def test_normalize_and_check_are_the_same_rules_the_writers_use() -> None:
    """结构级 / 内容级是两个可单独调用的函数（plan 校验与落盘共用它们）。"""
    spec = normalize_edits([{"mode": "replace", "start": "2", "end": "2", "expect": "b", "text": "B"}])[0]
    assert spec["start"] == 2  # 字符串行号会被规范化成整数
    check_edit(spec, ["a", "b", "c"])  # 与正文相符 ⇒ 通过
    with pytest.raises(EditError):
        check_edit(spec, ["a", "zzz", "c"])


def test_overlapping_edits_are_rejected() -> None:
    with pytest.raises(EditError) as err:
        splice(
            "a\nb\nc\n",
            [
                {"mode": "delete", "start": 1, "end": 2, "expect": "a\nb"},
                {"mode": "delete", "start": 2, "end": 3, "expect": "b\nc"},
            ],
        )
    assert err.value.code == "overlapping_edits"


# ── ② plan 校验 / 预览 ────────────────────────────────────────────────────


def test_validate_accepts_body_edit_and_preview_shows_the_diff(kb: Path, service: DocumentService) -> None:
    plan = _plan(_replace(3, 3, "注意力机制是核心。", "注意力机制是核心机制。"))
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "ok", checked
    assert checked["warnings"] == []  # 已实现编译器的 op ⇒ 不再有"未编译"警告

    preview = preview_plan(str(kb), plan, service=service)
    entry = preview["files"][0]["ops"][0]
    assert entry["diff_available"] is True and entry["lines_changed"] == [3]
    assert entry["diff"] == [
        {"line": 3, "before": "注意力机制是核心。", "after": None},
        {"line": 3, "before": None, "after": "注意力机制是核心机制。"},
    ]


def test_validate_rejects_wrong_expect(kb: Path, service: DocumentService) -> None:
    """`expect` 与盘上不符 ⇒ 拒（错误码 + 实际原文回显），不猜也不改。"""
    plan = _plan(_replace(3, 3, "我猜的原文", "新的"))
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "error"
    assert checked["errors"][0]["code"] == "expect_mismatch"
    assert "注意力机制是核心。" in checked["errors"][0]["message"]


def test_validate_requires_body_edits_after_anchor_ops(kb: Path, service: DocumentService) -> None:
    """同一文件里"先改正文、后按行号挂跳转" ⇒ 拒（`body_edit_order`），并说明怎么改。"""
    plan = _plan(
        _replace(3, 3, "注意力机制是核心。", "注意力机制是核心机制。"),
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
    assert [e["code"] for e in checked["errors"]] == ["body_edit_order"]


def test_validate_allows_anchor_ops_before_body_edits(kb: Path, service: DocumentService) -> None:
    """顺序反过来的同一个 plan 应当放行（锚定 op 先跑，行号语义一致）。"""
    plan = _plan(
        {
            "op": "attach_links",
            "op_id": "o1",
            "file": "notes/a.md",
            "anchor_text": "注意力机制",
            "targets": ["a"],
            "occurrences": [{"line": 3}],
        },
        _replace(5, 5, "末尾一行。", "末尾两行之一。", op_id="o2"),
    )
    checked = validate_plan(str(kb), plan, service=service)
    assert checked["status"] == "ok", checked


# ── ③ 落地与撤销（逐字节） ────────────────────────────────────────────────


def test_apply_body_edit_writes_only_that_line_and_undo_restores(kb: Path, service: DocumentService) -> None:
    path = kb / "notes" / "a.md"
    before = path.read_bytes()
    plan = _plan(_replace(3, 3, "注意力机制是核心。", "注意力机制是核心机制。"))

    compiled = compile_plan(str(kb), plan, service=service)
    assert [call["primitive"] for call in compiled["calls"]] == ["edit_body"]

    done = apply_plan(
        str(kb),
        plan,
        session_id=SESSION,
        txid=TXID,
        base_versions=compiled["base_versions"],
        service=service,
    )
    assert done["status"] == "ok", done
    assert path.read_text(encoding="utf-8") == A_MD.replace("注意力机制是核心。", "注意力机制是核心机制。")
    assert path.read_bytes() != before

    undone = restore_batch(str(kb), SESSION, TXID)
    assert undone["status"] == "ok", undone
    assert path.read_bytes() == before  # 逐字节回到写入前（含末尾换行）


def test_apply_delete_and_insert_lines(kb: Path, service: DocumentService) -> None:
    plan = _plan(
        {"op": "insert_lines", "op_id": "o1", "file": "notes/a.md", "after": 1, "expect": "# A 文档", "text": "新增一段。"},
        {"op": "delete_lines", "op_id": "o2", "file": "notes/a.md", "range": {"start": 5, "end": 5}, "expect": "末尾一行。"},
    )
    done = apply_plan(str(kb), plan, session_id=SESSION, txid="20260921T101501Z-02", service=service)
    assert done["status"] == "ok", done
    text = (kb / "notes" / "a.md").read_text(encoding="utf-8")
    assert text == "# A 文档\n新增一段。\n\n注意力机制是核心。\n\n"


def test_apply_body_edit_rejects_stale_expect(kb: Path, service: DocumentService) -> None:
    """编译之后（拿到 base_versions 之后）文件被改 ⇒ 整批拒、零写入。"""
    plan = _plan(_replace(3, 3, "注意力机制是核心。", "新文本。"))
    compiled = compile_plan(str(kb), plan, service=service)
    path = kb / "notes" / "a.md"
    path.write_text(A_MD + "\n人写的尾巴。\n", encoding="utf-8")
    after = _sha(path)

    res = apply_plan(
        str(kb), plan, session_id=SESSION, txid=TXID, base_versions=compiled["base_versions"], service=service
    )
    assert res["status"] == "error" and res["code"] == "stale_write"
    assert _sha(path) == after


# ── ④ 工具面：模型看得见这三个 op ─────────────────────────────────────────


def test_propose_tool_documents_body_edit_ops(kb: Path) -> None:
    registry = ToolRegistry(build_kb_tools(str(kb)))
    tool = registry.get(PROPOSE_TOOL_NAME)
    assert tool is not None
    for needle in ("replace_lines", "insert_lines", "delete_lines", "expect", "after"):
        assert needle in tool.description, f"提议工具说明里缺 {needle}"

    result = registry.invoke(
        ToolCall(
            id="c1",
            name=PROPOSE_TOOL_NAME,
            arguments=json.dumps(
                {
                    "intent": "改一句正文",
                    "ops": [
                        {
                            "op": "replace_lines",
                            "file": "notes/a.md",
                            "range": {"start": {"line": 3}, "end": {"line": 3}},
                            "expect": "注意力机制是核心。",
                            "text": "注意力机制是核心机制。",
                        }
                    ],
                }
            ),
        )
    )
    assert result.is_error is False, result.content
    assert "尚未写入" in result.content


# ── ⑥ 块级：`upsert_block`（§7 5.1 / 5.3 / 5.5；表格不做）────────────────────────────────


CODE_MD = "# C 文档\n\n示例：\n\n```python\nprint(1)\n```\n\n完。\n"
MATH_MD = "# M 文档\n\n公式：\n\n$$\na = b + c\n$$\n\n完。\n"


def _kb_with(tmp_path: Path, text: str) -> Path:
    """按正文指纹建一个独立小库（同一测试里建多个也不撞目录）。"""
    root = tmp_path / f"kb-{abs(hash(text)) % 100000}"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "c.md").write_text(text, encoding="utf-8", newline="")
    return root


def test_upsert_block_rebuilds_code_fence(tmp_path: Path) -> None:
    """整块重建代码块：围栏由程序重建（保留/替换语言），撤销逐字节还原。"""
    root = _kb_with(tmp_path, CODE_MD)
    service = DocumentService(kb_path=str(root))
    body_lines = CODE_MD.splitlines()
    plan = _plan(
        {
            "op": "upsert_block",
            "op_id": "o1",
            "file": "notes/c.md",
            "kind": "code",
            "range": {"start": {"line": 5}, "end": {"line": 7}},
            "expect": "```python\nprint(1)\n```",
            "content": "print(2)\nprint(3)",
            "lang": "python",
        }
    )
    preview = preview_plan(str(root), plan, service=service)
    entry = preview["files"][0]["ops"][0]
    assert entry["diff_available"] is True and entry["block"] == {"kind": "code", "lang": "python"}
    assert [row["before"] for row in entry["diff"] if row["before"] is not None] == ["```python", "print(1)", "```"]

    done = apply_plan(
        str(root), plan, session_id=SESSION, txid="20260921T101502Z-03", service=service
    )
    assert done["status"] == "ok", done
    text = (root / "notes" / "c.md").read_text(encoding="utf-8")
    assert "```python\nprint(2)\nprint(3)\n```" in text
    assert text.count("```") == 2  # 围栏没有被多加/漏掉
    assert len(body_lines) == 9

    undone = restore_batch(str(root), SESSION, "20260921T101502Z-03")
    assert undone["status"] == "ok" and (root / "notes" / "c.md").read_text(encoding="utf-8") == CODE_MD


MERMAID_MD = "# D 文档\n\n图：\n\n```mermaid\ngraph TD\nA-->B\n```\n\n完。\n"


def test_upsert_block_math_and_mermaid(tmp_path: Path) -> None:
    root = _kb_with(tmp_path, MATH_MD)
    service = DocumentService(kb_path=str(root))
    plan = _plan(
        {
            "op": "upsert_block",
            "op_id": "o1",
            "file": "notes/c.md",
            "kind": "math",
            "range": {"start": {"line": 5}, "end": {"line": 7}},
            "expect": "$$\na = b + c\n$$",
            "content": "E = mc^2",
        }
    )
    assert apply_plan(str(root), plan, session_id=SESSION, txid="20260921T101503Z-04", service=service)["status"] == "ok"
    assert "$$\nE = mc^2\n$$" in (root / "notes" / "c.md").read_text(encoding="utf-8")

    mroot = _kb_with(tmp_path, MERMAID_MD)  # 同一 fixture 目录下的另一个库
    service = DocumentService(kb_path=str(mroot))
    plan = _plan(
        {
            "op": "upsert_block",
            "op_id": "o1",
            "file": "notes/c.md",
            "kind": "mermaid",
            "range": {"start": {"line": 5}, "end": {"line": 8}},  # 该 mermaid 块是 5..8 行（内容两行）
            "expect": "```mermaid\ngraph TD\nA-->B\n```",
            "content": "graph LR\nX-->Y",
        }
    )
    assert apply_plan(str(mroot), plan, session_id=SESSION, txid="20260921T101504Z-05", service=service)["status"] == "ok"
    text = (mroot / "notes" / "c.md").read_text(encoding="utf-8")
    assert "```mermaid\ngraph LR\nX-->Y\n```" in text  # 语言标记由程序保留（不用模型重复写）


@pytest.mark.parametrize(
    ("op_patch", "code"),
    [
        ({"kind": "table"}, "unsupported_kind"),  # 表格本轮不给（人 UI 尚不能写）
        ({"kind": "mermaid"}, "block_kind_mismatch"),  # 声明 mermaid 但围栏是 python
        ({"range": {"start": {"line": 4}, "end": {"line": 7}}}, "block_not_fenced"),  # 区间没对齐块首
        ({"content": "print(1)\n```\nprint(2)"}, "content_breaks_fence"),  # 内容会提前收尾
        ({"content": "   "}, "empty_text"),
        ({"expect": "我猜的整块原文"}, "expect_mismatch"),
    ],
)
def test_upsert_block_rejects_bad_input(tmp_path: Path, op_patch: dict, code: str) -> None:
    root = _kb_with(tmp_path, CODE_MD)
    service = DocumentService(kb_path=str(root))
    op = {
        "op": "upsert_block",
        "op_id": "o1",
        "file": "notes/c.md",
        "kind": "code",
        "range": {"start": {"line": 5}, "end": {"line": 7}},
        "expect": "```python\nprint(1)\n```",
        "content": "print(2)",
    }
    op.update(op_patch)
    checked = validate_plan(str(root), _plan(op), service=service)
    assert checked["status"] == "error", checked
    assert checked["errors"][0]["code"] == code, checked["errors"]


def test_upsert_block_runs_through_the_same_edit_body_primitive(tmp_path: Path) -> None:
    """块级**不新增落盘原语**：编译出来仍是 `edit_body`（备份/回滚/审计/撤销全部沿用）。"""
    root = _kb_with(tmp_path, CODE_MD)
    service = DocumentService(kb_path=str(root))
    plan = _plan(
        {
            "op": "upsert_block",
            "op_id": "o1",
            "file": "notes/c.md",
            "kind": "code",
            "range": {"start": {"line": 5}, "end": {"line": 7}},
            "expect": "```python\nprint(1)\n```",
            "content": "print(2)",
            "lang": "python",
        }
    )
    compiled = compile_plan(str(root), plan, service=service)
    assert [call["primitive"] for call in compiled["calls"]] == ["edit_body"]


# ── ⑦ RPC 面：卡片走的正是这三个 op ───────────────────────────────────────


def test_preview_rpc_renders_body_edit_diff(kb: Path, api: UIAPI) -> None:
    plan = _plan(_replace(3, 3, "注意力机制是核心。", "注意力机制是核心机制。"))
    preview = api.agent_plan_preview(plan)
    assert preview["status"] == "ok" and preview["previewed"] is True
    entry = preview["files"][0]["ops"][0]
    assert entry["op"] == "replace_lines" and entry["lines_changed"] == [3]
    assert entry["diff"][1]["after"] == "注意力机制是核心机制。"

    done = api.agent_plan_apply(plan, None, None, preview["base_versions"])
    assert done["status"] == "ok", done
    undone = api.agent_plan_undo(None, done["session_id"], done["txid"])
    assert undone["status"] == "ok", undone
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == A_MD
