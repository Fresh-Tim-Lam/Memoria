"""写模块**审计事件**与**撤销后一致性恢复**的离线单测（第二片 ③ 的可测部分）。

口径：`docs/design/agent-capabilities.md` §2.3.2 第 5/8 步 ——
① 一次 plan 的落地尝试（成功 / 被拒 / 失败回滚）都要在**会话**里留痕（log-only，回放跳过）；
② 撤销同样留痕；③ 用户明示「以我为准」的覆盖尤其要留痕；④ 审计失败**绝不回滚已完成的写入**，
但必须**如实带回**（`{"status": "ok"|"skipped"|"error"}`），不许静默；
⑤ 撤销是**直接写盘**（不走 `save_document`）⇒ 之后必须清解析缓存 + 跑 `validate_kb()`。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent import audit
from memoria.services.agent.apply import apply_plan, recover_after_write
from memoria.services.agent.backup import restore_batch
from memoria.services.agent.plan import preview_plan
from memoria.services.agent.session.store import session_file
from memoria.services.document import DocumentService

A_MD = "# A 文档\n\n注意力机制是核心。\n\n末尾一行。\n"
SESSION = "session-20260920T021100Z-abcd1234"
TXID = "20260920T021100Z-07"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8")
    return root


@pytest.fixture()
def api(kb: Path) -> UIAPI:
    return UIAPI(kb_path=str(kb))


def _plan() -> dict:
    return {
        "v": 1,
        "txid": TXID,
        "intent": "测试用 plan",
        "ops": [
            {
                "op": "upsert_kp",
                "op_id": "o1",
                "file": "notes/a.md",
                "kp_id": "attention",
                "name": "注意力机制",
                "range": {"start": {"line": 1}, "end": {"line": 3}},
            }
        ],
    }


def _events(kb: Path, session_id: str = SESSION) -> list[dict]:
    """该会话的全部事件（**保留** `session/header`：它是会话自身的头，不是审计事件）。"""
    path = Path(session_file(str(kb), session_id))
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cap_types(kb: Path, session_id: str = SESSION) -> list[str]:
    """只看 `capability/*` 审计事件（过滤掉会话自身的 `session/header` 等）。"""
    return [e["type"] for e in _events(kb, session_id) if e["type"].startswith("capability/")]


def test_apply_success_and_rejection_are_audited(kb: Path, api: UIAPI) -> None:
    """落地成功 ⇒ `capability/apply{status:ok}`；被版本保护拒绝 ⇒ 同样留痕（不同 status/code）。"""
    ok = apply_plan(str(kb), _plan(), session_id=SESSION, service=api._svc)
    assert ok["status"] == "ok" and ok["audit"]["status"] == "ok", ok
    assert _cap_types(kb) == ["capability/apply"]
    events = [e for e in _events(kb) if e["type"] == "capability/apply"]
    assert events[0]["data"]["txid"] == TXID and events[0]["data"]["status"] == "ok"
    assert events[0]["data"]["dir"] and events[0]["data"]["applied"]

    stale = apply_plan(
        str(kb), _plan(), session_id=SESSION, base_versions={"notes/a.md": "deadbeef"}, service=api._svc
    )
    assert stale["code"] == "stale_write" and stale["audit"]["status"] == "ok"
    last = _events(kb)[-1]
    assert last["type"] == "capability/apply" and last["data"]["code"] == "stale_write"


def test_undo_is_audited(kb: Path, api: UIAPI) -> None:
    """撤销也留痕（`capability/undo`，带 txid 与逐文件动作）。"""
    assert apply_plan(str(kb), _plan(), session_id=SESSION, service=api._svc)["status"] == "ok"
    undone = restore_batch(str(kb), SESSION, TXID)
    assert undone["status"] == "ok" and undone["audit"]["status"] == "ok"
    events = [e for e in _events(kb) if e["type"] == "capability/undo"]
    assert len(events) == 1 and events[0]["data"]["txid"] == TXID
    assert events[0]["data"]["verified"] is True


def test_apply_internal_rollback_does_not_fake_an_undo(kb: Path, api: UIAPI, monkeypatch) -> None:
    """**事务内回滚 ≠ 用户撤销**：失败回滚只记 `capability/apply{apply_failed}`，不冒充 `capability/undo`。"""

    def _boom(*_a, **_k):
        return {"status": "error", "message": "注入的失败"}

    monkeypatch.setattr(DocumentService, "confirm_kp_range", _boom)
    res = apply_plan(str(kb), _plan(), session_id=SESSION, service=api._svc)
    assert res["status"] == "error" and res["code"] == "apply_failed", res
    types = _cap_types(kb)
    assert types == ["capability/apply"] and "capability/undo" not in types


def test_force_save_is_audited(kb: Path, api: UIAPI) -> None:
    """用户明示「以我为准」的覆盖单独留痕（`capability/force_save`）。"""
    res = api.save_document("notes/a.md", "# 覆盖版\n", "", True)
    assert res["status"] == "ok", res
    assert _cap_types(kb, "manual-force") == ["capability/force_save"]
    events = [e for e in _events(kb, "manual-force") if e["type"] == "capability/force_save"]
    assert events[0]["data"]["txid"] == res["force_backup"]["txid"]


def test_audit_is_fail_open_and_honest(kb: Path) -> None:
    """**fail-open 但如实**：没有会话 ⇒ `skipped`；会话 id 非法 ⇒ `error`；**都不抛异常**。"""
    assert audit.append(str(kb), None, audit.EVENT_APPLY, {})["status"] == "skipped"
    assert audit.append(None, SESSION, audit.EVENT_APPLY, {})["status"] == "skipped"
    bad = audit.append(str(kb), "../evil", audit.EVENT_APPLY, {})
    assert bad["status"] == "error" and bad["message"]


def test_recover_after_write_clears_cache_and_validates(kb: Path) -> None:
    """撤销后的一致性恢复：**清该文件解析缓存** + `validate_kb()` 无错。"""
    service = DocumentService(kb_path=str(kb))
    service.load_document("notes/a.md")  # 让 `_cache` 里有这条
    assert "notes/a.md" in getattr(service, "_cache", {})

    report = recover_after_write(str(kb), ["notes/a.md"], service=service)
    assert report["status"] == "ok"
    assert report["cache_cleared"] == ["notes/a.md"]
    assert report["errors"] == 0
    assert "notes/a.md" not in getattr(service, "_cache", {})


def test_preview_detach_links_now_gives_body_diff(kb: Path, api: UIAPI) -> None:
    """`detach_links` 的 dry-run 不再只是"将作用于哪些行"，而是给出**行级 before/after**。"""
    assert apply_plan(str(kb), _plan(), session_id=SESSION, service=api._svc)["status"] == "ok"
    attach = {
        "v": 1,
        "txid": "20260920T021101Z-08",
        "intent": "给「注意力机制」挂到 attention",
        "ops": [
            {
                "op": "attach_links",
                "op_id": "o2",
                "file": "notes/a.md",
                "anchor_text": "注意力机制",
                "targets": ["attention"],
            }
        ],
    }
    res = apply_plan(str(kb), attach, session_id=SESSION, service=api._svc)
    assert res["status"] == "ok", res

    detach = {
        "v": 1,
        "txid": "20260920T021102Z-09",
        "intent": "撤掉「注意力机制」上的跳转",
        "ops": [
            {
                "op": "detach_links",
                "op_id": "o3",
                "file": "notes/a.md",
                "anchor_text": "注意力机制",
                "occurrences": [{"line": 3}],
                "mode": "detach",
            }
        ],
    }
    preview = preview_plan(str(kb), detach, service=api._svc)
    entry = preview["files"][0]["ops"][0]
    assert entry["diff_available"] is True and entry["unwrapped"] == 1
    assert entry["diff"][0]["line"] == 3
    assert "[[" in entry["diff"][0]["before"] and "[[" not in entry["diff"][0]["after"]
