"""写闸门的**写前基线**规则：只拦"本次新引入的" sidecar 问题，既有残缺不阻塞修复性写入。

真机来源（2026-09-21）：agent 连提 4 批 `propose_write` 全 `WRITE_FAILED`，报的永远是**同一批既有**问题
（`notes/channel-utilization-and-delay.md` 的 `mac-throughput-formulas` / `tcp-rtt-estimation` 两个 KP 的
`end.snippet` 早年丢了）；"只更新一个 KP"的探针批**也没写进去**，只是报错列表里不再点名它 ⇒ 看起来像
"放行了"，其实是假象。根因：写闸门（`document.py` 11 处同形 + `save_document`）逐原语跑在**整份** sidecar
上，且"任何 error 都拒写" ⇒ 库里**一处既有残缺** = **所有修复性写入都写不进去**（不可修的死锁）。

钉住三条：

1. `validate_sidecar(baseline=…)`：与基线**同签名**的问题降级到 `pre_existing`（`ok=True`）；
   **新引入**的问题照旧拦（`ok=False`）；`baseline=None` 与旧口径逐字一致（既有用例的回归面）。
2. 原语层（`confirm_kp_range`）：修 `a` 时 `b` 的既有残缺不再拒写，且 **`b` 不被顺手改**（事实保真）。
3. 批级（agent 走的 `apply_plan`）：同一文件 3 条 `upsert_kp` 一次补齐 3 个残缺 KP ⇒ **整批 ok**、
   落盘后校验 0 error。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoria.services.agent.apply import apply_plan, compile_plan
from memoria.services.agent.llm import ToolCall
from memoria.services.agent.tools import ToolRegistry, build_kb_tools
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME
from memoria.services.document import DocumentService
from memoria.storage.constants import SIDECAR_SCHEMA_VERSION
from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md
from memoria.storage.sidecar_validate import validate_sidecar

BODY = "# A 文档\n\n第一段。\n\n第二段。\n\n第三段。\n"
REL = "notes/a.md"
SESSION = "session-20260922T160000Z-gate1"
TXID = "20260922T160000Z-01"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text(BODY, encoding="utf-8", newline="")
    return root


@pytest.fixture()
def service(kb: Path) -> DocumentService:
    return DocumentService(kb_path=str(kb))


def _lines(kb: Path) -> list[str]:
    return (kb / "notes" / "a.md").read_text(encoding="utf-8").splitlines()


def _kp(kp_id: str, name: str, start: tuple[str, int], end: tuple[str, int] | None) -> dict:
    """一个 KP；`end=None` = 整个 `end` 键都缺（真机里是 `snippet` 为**空串**，两种都该被判残缺）。"""
    rng: dict = {"start": {"snippet": start[0], "line_hint": start[1]}}
    if end is not None:
        rng["end"] = {"snippet": end[0], "line_hint": end[1]}
    return {"id": kp_id, "name": name, "range": rng}


def _sidecar(*kps: dict) -> dict:
    return {"schema_version": SIDECAR_SCHEMA_VERSION, "file": REL, "knowledge_points": list(kps)}


def _write_sidecar(kb: Path, *kps: dict) -> None:
    save_sidecar_for_md(kb / "notes" / "a.md", str(kb), _sidecar(*kps))


# ── ① 基线规则本身 ────────────────────────────────────────────────────────


def test_baseline_demotes_pre_existing_but_still_blocks_new(kb: Path) -> None:
    """既有残缺 ⇒ 放行且如实回报；本次新弄坏的 ⇒ 照旧拦。`baseline=None` = 旧口径。"""
    lines = _lines(kb)
    pre = _sidecar(_kp("a", "A", ("# A 文档", 1), ("", 4)))  # a 的 end.snippet 空 ⇒ 既有残缺
    assert validate_sidecar(pre, REL, lines)["ok"] is False, "旧口径：既有残缺就是 error"

    fixed = _sidecar(_kp("a", "A", ("# A 文档", 1), ("第二段。", 5)))
    clean = validate_sidecar(fixed, REL, lines, baseline=pre)
    assert clean["ok"] is True and clean["errors"] == [], "修好了就是干净"
    assert [e["kp_id"] for e in clean["pre_existing"]] == [], "a 已修好 ⇒ 它那条不再是既有问题"

    # 修 a 的同时把 b 弄成残缺 ⇒ 这是**新引入的**，必须拦住
    worse = _sidecar(fixed["knowledge_points"][0], _kp("b", "B", ("第三段。", 7), None))
    r = validate_sidecar(worse, REL, lines, baseline=pre)
    assert r["ok"] is False
    assert [e["code"] for e in r["errors"]] == ["kp_range_missing_snippet"] and r["errors"][0]["kp_id"] == "b"


def test_baseline_demotes_when_nothing_changed(kb: Path) -> None:
    """一个字没动（写前后同状态）⇒ 既有问题全部降级，不因"库里本来就有"拒写。"""
    lines = _lines(kb)
    data = _sidecar(_kp("a", "A", ("# A 文档", 1), ("", 4)), _kp("b", "B", ("第三段。", 7), None))
    r = validate_sidecar(data, REL, lines, baseline=data)
    assert r["ok"] is True and len(r["pre_existing"]) == 2 and r["errors"] == []


# ── ② 原语层：修一个不该被另一个的残缺挡住 ────────────────────────────────


def test_confirm_kp_range_not_blocked_by_another_broken_kp(kb: Path, service: DocumentService) -> None:
    """真机死锁的直接回归：`b` 的 `end.snippet` 早丢了，修 `a` 也必须能写进去。"""
    _write_sidecar(
        kb,
        _kp("b", "B", ("第一段。", 3), ("", 4)),  # 残缺（end.snippet 空）
        _kp("a", "A", ("# A 文档", 1), None),  # 残缺（没有 end）
    )
    res = service.confirm_kp_range(REL, "a", "A", 1, 5)
    assert res.get("status") == "ok", f"修复性写入必须放行，实际：{res}"

    side = load_sidecar_for_md(kb / "notes" / "a.md", str(kb)) or {}
    by_id = {k["id"]: k for k in side.get("knowledge_points", [])}
    assert by_id["a"]["range"]["end"]["snippet"] == "第二段。", "a 真写进去了"
    assert not (by_id["b"]["range"].get("end") or {}).get("snippet"), "b 不被顺手改（事实保真）"
    v = validate_sidecar(side, REL, _lines(kb))
    assert v["ok"] is False and [e.get("kp_id") for e in v["errors"]] == ["b"], "库里仍如实反映 b 的残缺"


# ── ③ 批级：agent 那一批的等价物 ──────────────────────────────────────────


def test_batch_repairs_several_broken_kps_in_one_pass(kb: Path, service: DocumentService) -> None:
    """一个 plan 里 3 条 `upsert_kp` 把 3 个残缺 KP 一次补齐 ⇒ 整批 ok、落盘后 0 error。"""
    _write_sidecar(
        kb,
        _kp("p1", "P1", ("# A 文档", 1), ("", 4)),
        _kp("p2", "P2", ("第一段。", 3), None),
        _kp("p3", "P3", ("第二段。", 5), ("", 6)),
    )
    plan = {
        "v": 1,
        "txid": TXID,
        "intent": "补齐 3 个 KP 的 end 锚点",
        "ops": [
            {"op": "upsert_kp", "op_id": "k1", "file": REL, "kp_id": "p1", "name": "P1", "range": {"start": {"line": 1}, "end": {"line": 3}}},
            {"op": "upsert_kp", "op_id": "k2", "file": REL, "kp_id": "p2", "name": "P2", "range": {"start": {"line": 3}, "end": {"line": 5}}},
            {"op": "upsert_kp", "op_id": "k3", "file": REL, "kp_id": "p3", "name": "P3", "range": {"start": {"line": 5}, "end": {"line": 7}}},
        ],
    }
    compiled = compile_plan(str(kb), plan, service=service)
    done = apply_plan(
        str(kb), plan, session_id=SESSION, txid=TXID, base_versions=compiled["base_versions"], service=service
    )
    assert done["status"] == "ok", f"整批必须过（真机在这里全批失败）：{done}"

    side = load_sidecar_for_md(kb / "notes" / "a.md", str(kb)) or {}
    kps = {k["id"]: k for k in side.get("knowledge_points", [])}
    assert set(kps) == {"p1", "p2", "p3"}, "三条 op 都要生效（不是只落了第一条）"
    assert all((k["range"].get("end") or {}).get("snippet") for k in kps.values()), "三个 end 锚点都补齐"
    assert validate_sidecar(side, REL, _lines(kb))["ok"] is True, "落盘后整份 sidecar 0 error"


def test_body_edit_not_blocked_by_an_existing_kp_defect(kb: Path, service: DocumentService) -> None:
    """同一批里"精简正文"那一半也一样：正文编辑的闸门不能被**别处**的既有残缺挡住。

    （真机那一批既改正文又刷 KP；`save_document`（`document.py:3109` 那处闸门）同属这一族。）
    """
    _write_sidecar(kb, _kp("a", "A", ("# A 文档", 1), ("", 4)))  # 既有残缺（end.snippet 空）
    plan = {
        "v": 1,
        "txid": TXID,
        "intent": "改正文（测试）",
        "ops": [
            {
                "op": "replace_lines",
                "op_id": "o1",
                "file": REL,
                "range": {"start": {"line": 3}, "end": {"line": 3}},
                "expect": "第一段。",
                "text": "第一段（精简）。",
            }
        ],
    }
    compiled = compile_plan(str(kb), plan, service=service)
    done = apply_plan(
        str(kb), plan, session_id=SESSION, txid=TXID, base_versions=compiled["base_versions"], service=service
    )
    assert done["status"] == "ok", f"正文改动必须放行：{done}"
    assert "第一段（精简）。" in (kb / "notes" / "a.md").read_text(encoding="utf-8"), "正文真改了"


# ── ⑤ 工具回执回报「库里还剩的既有问题」（人：「把 pre_existing 透传到工具回执」）────────────


def _invoke_write(kb: Path, service: DocumentService, ops: list[dict]) -> object:
    """走**真注册表**写一批（先读后写 —— 2026-09-22 起有读后写闸）。"""
    registry = ToolRegistry(build_kb_tools(str(kb), session_id="session-write-receipt", service=service))
    registry.invoke(ToolCall(id="r1", name="read_document", arguments=json.dumps({"path": REL})))
    return registry.invoke(
        ToolCall(
            id="c1",
            name=PROPOSE_TOOL_NAME,
            arguments=json.dumps({"intent": "补一个点", "ops": ops}, ensure_ascii=False),
        )
    )


def _upsert(kp_id: str, name: str, line: int = 3) -> list[dict]:
    return [
        {
            "op": "upsert_kp",
            "op_id": "o1",
            "file": REL,
            "kp_id": kp_id,
            "name": name,
            "range": {"start": {"line": line}, "end": {"line": line}},
        }
    ]


def test_tool_receipt_reports_the_remaining_pre_existing_issues(kb: Path, service: DocumentService) -> None:
    """写成功后回执要**如实列出**库里还剩的既有问题（新引入的已被闸门拦住 ⇒ 剩下的都是存量）。"""
    _write_sidecar(kb, _kp("broken", "残缺点", ("# A 文档", 1), None))

    result = _invoke_write(kb, service, _upsert("fresh", "新点"))

    assert result.is_error is False, result.content
    assert "**已写入**" in result.content
    assert "**库里还有一些既有问题**" in result.content, "既有问题必须浮出来给模型看"
    assert "kp_range_missing_snippet" in result.content
    assert "与本批无关" in result.content and "**不要**因为这几条就重提本批" in result.content, "防误动作"


def test_tool_receipt_stays_silent_when_nothing_is_left(kb: Path, service: DocumentService) -> None:
    """库里没有既有问题时回执**逐字不多说**（只在真有存量时才加那一段）。"""
    result = _invoke_write(kb, service, _upsert("fresh", "新点"))

    assert result.is_error is False, result.content
    assert "**已写入**" in result.content
    assert "既有问题" not in result.content
    assert validate_sidecar(load_sidecar_for_md(kb / "notes" / "a.md", str(kb)) or {}, REL, _lines(kb))["errors"] == []
