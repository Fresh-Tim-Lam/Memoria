"""写模块 **apply 入口**（`services/agent/apply.py`）的离线单测：编译 + 原语编排 + 整批回滚。

口径来源：`docs/design/agent-capabilities.md` §2.3.1（唯一写者 / 原语白名单）、
§2.3.2（调用序：pre-image → 原语 → post-image → trimming）、§2.3.3（编译器）。

覆盖：① `upsert_kp` 落地与幂等（同 `(file, kp_id)` 走更新，不重复建点）；② `attach_links`
包裹正文 + sidecar 路由 + 重复执行不二次包裹；③ `detach_links` 解除包裹并进 `excluded`；
④ **任一原语失败 ⇒ 整批回滚**（前一步已写入的 md / sidecar 逐字节回到原样）；
⑤ **备份失败 ⇒ 零写入**（fail-closed）；⑥ 编译产物的**顺序与受影响文件集**（含 sidecar /
manifest / pending）；⑦ 非法 plan ⇒ 既不写盘、也不建备份。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from memoria.services.agent import backup
from memoria.services.agent.apply import apply_plan, compile_plan
from memoria.services.document import DocumentService
from memoria.storage.sidecar import sidecar_path_for

SESSION = "session-20260920T021100Z-abcd1234"
A_MD = "\n".join(
    [
        "# A 文档",  # 1
        "",  # 2
        "注意力机制是核心。注意力机制也出现在别处。",  # 3
        "",  # 4
        "末尾一行。",  # 5
    ]
)


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text(A_MD + "\n", encoding="utf-8")
    return root


@pytest.fixture()
def service(kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocumentService:
    """**必须先隔离配置目录**：`DocumentService` 打开库会走「记录最近打开」链路
    （`ui_settings.remember_last_kb_path`）⇒ 不隔离就会写**真实** `config/ui-settings.json`
    （实测踩到：把临时库路径写进 recent_kbs）。隔离后一切偏好读写落在 tmp。
    """
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(tmp_path / "cfg"))
    return DocumentService(kb_path=str(kb))


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _sidecar(kb: Path, rel: str = "notes/a.md") -> dict:
    """读该 md 的侧车（不存在回空 dict）。"""
    path = Path(sidecar_path_for(str(kb / rel), str(kb)))
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _plan(*ops: dict[str, Any], txid: str = "20260920T021100Z-07") -> dict[str, Any]:
    return {"v": 1, "txid": txid, "intent": "测试用 plan", "ops": list(ops)}


def _upsert(kp_id: str = "attention", **extra: Any) -> dict[str, Any]:
    op = {
        "op": "upsert_kp",
        "op_id": "o1",
        "file": "notes/a.md",
        "kp_id": kp_id,
        "name": "注意力机制",
        "range": {"start": {"line": 1}, "end": {"line": 3}},
    }
    op.update(extra)
    return op


def _attach(**extra: Any) -> dict[str, Any]:
    op = {
        "op": "attach_links",
        "op_id": "o2",
        "file": "notes/a.md",
        "anchor_text": "注意力机制",
        "targets": ["attention"],
    }
    op.update(extra)
    return op


def test_apply_upsert_kp_then_attach_links(kb: Path, service: DocumentService) -> None:
    """① 建点：sidecar 落地、md 不动、post.json 落盘、全库一致；同 id 再跑 = 更新（不重复）。"""
    md_before = _sha(kb / "notes" / "a.md")
    first = apply_plan(str(kb), _plan(_upsert()), session_id=SESSION, service=service)
    assert first["status"] == "ok", first
    assert first["backup"]["files"] and first["post_images"] is True
    assert (Path(first["dir"]) / "post.json").is_file()
    assert _sha(kb / "notes" / "a.md") == md_before  # 建点只动 sidecar，不动正文

    sidecar = _sidecar(kb)
    assert [kp["id"] for kp in sidecar["knowledge_points"]] == ["attention"]
    assert service.validate_kb()["errors"] == 0

    again = apply_plan(str(kb), _plan(_upsert(), txid="20260920T021101Z-08"), session_id=SESSION, service=service)
    assert again["status"] == "ok"
    assert [kp["id"] for kp in _sidecar(kb)["knowledge_points"]] == ["attention"]  # 幂等：仍只有一个


#: 曾经挂在这里的 `_XFAIL_MATCH_SPAN` 已**撤掉** —— 缺陷已修（2026-09-20）：
#: `link_text_search` 的纯文本分支把 **body 绝对偏移**当行内偏移用（`link_text_search.py:669-675`），
#: 导致匹配 span 整体右移、`apply_link_instances` 包裹到错误子串（实测曾产出
#: `注意力机制是核心[[。注意力机]]制也出现在别处。`）。修法：先换算成行内下标再查 `view_to_orig`
#: （`row_pos = pos - (body.rfind("\n", 0, pos) + 1)`）。两个用例现已直接通过。


def test_apply_attach_links_wraps_and_is_idempotent(kb: Path, service: DocumentService) -> None:
    """② 挂链接：正文包裹成 `[[锚文本]]`、sidecar 记路由；重复执行**不二次包裹**。"""
    assert apply_plan(str(kb), _plan(_upsert()), session_id=SESSION, service=service)["status"] == "ok"
    first = apply_plan(str(kb), _plan(_attach(), txid="20260920T021101Z-08"), session_id=SESSION, service=service)
    assert first["status"] == "ok", first

    body = (kb / "notes" / "a.md").read_text(encoding="utf-8")
    # 关键不变量（不是"包在哪一处"，而是**正文没被弄坏**）：把包裹去掉即逐字回到原文
    assert body.count("[[注意力机制]]") == 1
    assert body.replace("[[注意力机制]]", "注意力机制") == A_MD + "\n"
    link = _sidecar(kb)["links"][0]
    assert link["anchor_text"] == "注意力机制" and link["targets"] == ["attention"]
    # instances 是**按出现处**记的：本行有两处锚文本 ⇒ 实测会记两条 `{line: 3}`
    # （与"行粒度 + 只有一处被包裹"的行为一致），故这里只断言"行号集合"，不锁条数。
    assert {inst["line"] for inst in link["instances"]} == {3}
    assert service.validate_kb()["errors"] == 0

    second = apply_plan(str(kb), _plan(_attach(), txid="20260920T021102Z-09"), session_id=SESSION, service=service)
    assert second["status"] == "ok", second
    body2 = (kb / "notes" / "a.md").read_text(encoding="utf-8")
    assert body2.count("[[注意力机制]]") == 1  # 幂等：已挂接处不二次包裹
    assert "[[[[" not in body2


def test_attach_links_is_line_granular(kb: Path, service: DocumentService) -> None:
    """**行粒度限制（如实钉住）**：`apply_link_instances()` 只收 `selected_lines`（**没有列**），
    故同一行有多处出现时只能包裹其中一处（由 canonical 链路选定）—— 本用例把"只包一处、
    且正文完好"钉死；**设计稿的 `occurrences[].matched_text` 在 M3a 内落不到列级**
    （要列级得改原语签名，属后续批次，不在"唯一写者/不改原语"的约束内做）。
    """
    assert apply_plan(str(kb), _plan(_upsert()), session_id=SESSION, service=service)["status"] == "ok"
    res = apply_plan(str(kb), _plan(_attach(), txid="20260920T021101Z-08"), session_id=SESSION, service=service)
    assert res["status"] == "ok", res
    body = (kb / "notes" / "a.md").read_text(encoding="utf-8")
    assert body.count("[[注意力机制]]") == 1  # 一行两处出现 ⇒ 只包一处
    assert body.replace("[[注意力机制]]", "注意力机制") == A_MD + "\n"  # 正文逐字完好


def test_apply_detach_links_unwraps_and_excludes(kb: Path, service: DocumentService) -> None:
    """③ 解挂：正文回到纯文本、该行进 sidecar 的 `excluded`（路由保留）。"""
    apply_plan(str(kb), _plan(_upsert()), session_id=SESSION, service=service)
    apply_plan(str(kb), _plan(_attach(), txid="20260920T021101Z-08"), session_id=SESSION, service=service)
    detach = {
        "op": "detach_links",
        "op_id": "o3",
        "file": "notes/a.md",
        "anchor_text": "注意力机制",
        "occurrences": [{"line": 3}],
        "mode": "detach",
    }
    res = apply_plan(str(kb), _plan(detach, txid="20260920T021102Z-09"), session_id=SESSION, service=service)
    assert res["status"] == "ok", res
    body = (kb / "notes" / "a.md").read_text(encoding="utf-8")
    assert "[[" not in body
    assert body == A_MD + "\n"  # 解挂后正文逐字回到原文
    link = _sidecar(kb)["links"][0]
    excluded = link.get("excluded") or []
    # sidecar 的 excluded 条目形状是 `{line: N}`（不是裸 int）—— 按实际形状断言
    assert any((e == 3) or (isinstance(e, dict) and e.get("line") == 3) for e in excluded), excluded
    assert service.validate_kb()["errors"] == 0


def test_apply_rolls_back_whole_batch_when_a_primitive_fails(
    kb: Path, service: DocumentService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """④ **整批回滚**：op1 已写入的 sidecar 必须被 pre-image 还原，全库仍一致。"""

    def _boom(*_args: Any, **_kwargs: Any) -> dict:
        return {"status": "error", "message": "注入的失败"}

    monkeypatch.setattr(DocumentService, "apply_link_instances", _boom)
    md_before = _sha(kb / "notes" / "a.md")
    sidecar_path = Path(sidecar_path_for(str(kb / "notes" / "a.md"), str(kb)))
    sidecar_before = _sha(sidecar_path)

    res = apply_plan(str(kb), _plan(_upsert(), _attach()), session_id=SESSION, service=service)
    assert res["status"] == "error" and res["code"] == "apply_failed"
    assert res["rolled_back"] is True
    assert res["failed"]["primitive"] == "apply_link_instances"
    assert _sha(kb / "notes" / "a.md") == md_before
    assert _sha(sidecar_path) == sidecar_before  # op1 写下的 KP 被回滚掉
    assert not (Path(sidecar_path).is_file() and "attention" in Path(sidecar_path).read_text(encoding="utf-8"))
    assert service.validate_kb()["errors"] == 0


def test_apply_writes_nothing_when_backup_fails(
    kb: Path, service: DocumentService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⑤ 备份失败 ⇒ **零写入**（不降级为"无备份的写入"）。"""
    monkeypatch.setattr(
        backup,
        "snapshot_pre_images",
        lambda *_a, **_k: {"status": "error", "code": "batch_too_large", "message": "注入的备份失败"},
    )
    md_before = _sha(kb / "notes" / "a.md")
    res = apply_plan(str(kb), _plan(_upsert()), session_id=SESSION, service=service)
    assert res["status"] == "error" and res["code"] == "batch_too_large"
    assert res["applied"] == []
    assert _sha(kb / "notes" / "a.md") == md_before
    assert not Path(sidecar_path_for(str(kb / "notes" / "a.md"), str(kb))).is_file()


def test_compile_plan_orders_calls_and_lists_affected_files(kb: Path, service: DocumentService) -> None:
    """⑥ 编译产物：调用**有序**、受影响文件集含正文 + sidecar + manifest + pending。"""
    compiled = compile_plan(str(kb), _plan(_upsert(tags=["概念"]), _attach()), service=service)
    assert compiled["status"] == "ok", compiled
    assert [call["primitive"] for call in compiled["calls"]] == [
        "confirm_kp_range",
        "update_kp",
        "apply_link_instances",
    ]
    assert compiled["files"] == [
        "notes/a.md",
        ".memoria/sidecars/notes/a.memoria.yaml",
        ".memoria/manifest.yaml",
        ".memoria/pending.json",
    ]


def test_apply_rejects_invalid_plan_without_touching_disk(kb: Path, service: DocumentService) -> None:
    """⑦ 非法 plan：既不写盘，**也不建备份**（校验发生在 pre-image 之前）。"""
    before = {p: _sha(p) for p in kb.rglob("*") if p.is_file()}
    res = apply_plan(str(kb), _plan({"op": "delete_everything", "op_id": "x", "file": "notes/a.md"}), session_id=SESSION, service=service)
    assert res["status"] == "error" and res["code"] == "invalid_plan"
    assert not Path(backup.backups_root(str(kb))).exists()
    assert {p: _sha(p) for p in kb.rglob("*") if p.is_file()} == before
