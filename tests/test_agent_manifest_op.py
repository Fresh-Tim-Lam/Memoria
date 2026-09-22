"""库级 op：`rebuild_manifest`（§7 的 6.3 / 原语 `kb.manifest.rebuild`）。

真机来源（2026-09-22，产品内 agent 报告）："剩下 49 条 + 2 个错误全是清单（manifest）陈旧，
**只能点「构建」**" —— 它当时一个能碰 manifest 的 op 都没有。本轮补成 op，口径与界面「构建」**同一份**：

1. **复用** `DocumentService.sync_manifest()`（→ `manifest.rebuild_manifest()`），不另写重建逻辑；
2. **前置硬闸**：有未修复的**路径变更** ⇒ 拒（`manifest_blocked_by_path_moves`）—— `detect_path_moves()`
   按内容 hash 把"清单里有、盘上没了"与"盘上有、清单里没有"配对成 rename/move，那种状态下重建
   等于把"文件搬到哪儿去了"这条元数据抹掉。挡在**计划期**，模型能拿着错误改意图；
3. **必须收尾**（`manifest_must_be_last`）：它记的是"这一刻的文件集"，后继任何改文件集的 op 都让它过期；
4. **无 `file`** ⇒ 天然豁免读后写闸；**不进** `RISKY_OPS`（可再生索引 + 自带前置硬闸）；
5. 可**整批撤销**（备份集由 `affected_files()` 自带的 manifest + pending 承担）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent.apply import apply_plan, compile_plan
from memoria.services.agent.backup import restore_batch
from memoria.services.agent.llm import ToolCall
from memoria.services.agent.plan import validate_plan
from memoria.services.agent.tools import ToolRegistry, build_kb_tools
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME
from memoria.services.document import DocumentService
from memoria.storage.manifest import audit_manifest_diff, manifest_path

A_MD = "# A 文档\n\n第一段。\n"
B_MD = "# B 文档\n\n乙。\n"
SESSION = "session-20260922T130000Z-mm11bb22"
TXID = "20260922T130000Z-01"

#: 一条"指纹过期"的 sha（永远对不上真实内容）
STALE_SHA = "0" * 64


def _manifest_yaml(rows: list[tuple[str, str]]) -> str:
    """手写一份 manifest（`load_manifest()` 认的形状：`files: [{path, md_sha256, …}]`）。"""
    lines = ["schema_version: 1", "updated_at: '2026-09-01T00:00:00+00:00'", "files:"]
    for rel, sha in rows:
        lines += [
            f"- path: {rel}",
            "  md_mtime: 1.0",
            "  md_size: 3",
            f"  md_sha256: {sha}",
            "  sidecar_mtime: null",
            "  sidecar_sha256: null",
        ]
    return "\n".join(lines) + "\n"


def _write_kb(root: Path, manifest: str, *, also_b: bool = True) -> Path:
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir(exist_ok=True)
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8", newline="")
    if also_b:
        (root / "notes" / "b.md").write_text(B_MD, encoding="utf-8", newline="")
    (root / ".memoria" / "manifest.yaml").write_text(manifest, encoding="utf-8", newline="")
    return root


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    """清单陈旧：`a.md` 指纹对不上、`ghost.md` 已不存在、`b.md` 从没记进去。"""
    return _write_kb(
        tmp_path / "kb",
        _manifest_yaml([("notes/a.md", STALE_SHA), ("notes/ghost.md", STALE_SHA)]),
    )


@pytest.fixture()
def service(kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DocumentService:
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(tmp_path / "cfg"))
    return DocumentService(kb_path=str(kb))


def _plan(*ops: dict) -> dict:
    return {"v": 1, "txid": TXID, "intent": "库级改动（测试）", "ops": list(ops)}


def _facts(root: Path) -> dict[str, str]:
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
    return apply_plan(
        str(kb), plan, session_id=SESSION, txid=TXID,
        base_versions=compiled["base_versions"], service=service,
    )


# ── ① 正常路径：清掉陈旧清单 + 撤销 ──────────────────────────────────────────


def test_rebuild_manifest_clears_stale_entries_and_undoes(kb: Path, service: DocumentService) -> None:
    before = _facts(kb)
    stale = audit_manifest_diff(str(kb))
    assert stale["summary"]["warning_count"] > 0, "修前确实有陈旧项（指纹过期 / ghost / 未记入）"

    plan = _plan({"op": "rebuild_manifest", "op_id": "o1"})
    compiled = compile_plan(str(kb), plan, service=service)
    assert [call["primitive"] for call in compiled["calls"]] == ["rebuild_manifest"]
    assert _facts(kb) == before, "校验 / 编译**零落盘**"

    done = _apply(kb, service, plan)
    assert done["status"] == "ok", done
    fresh = audit_manifest_diff(str(kb))
    assert fresh["summary"]["warning_count"] == 0 and fresh["summary"]["error_count"] == 0
    text = Path(manifest_path(str(kb))).read_text(encoding="utf-8")
    assert "notes/b.md" in text and "notes/ghost.md" not in text and STALE_SHA not in text

    assert restore_batch(str(kb), SESSION, TXID)["status"] == "ok"
    assert _facts(kb) == before, "撤销把 manifest 逐字节还原"


# ── ② 前置硬闸：未修复的路径变更 ─────────────────────────────────────────────


def test_rebuild_manifest_is_blocked_by_unrepaired_path_moves(tmp_path: Path) -> None:
    """清单里记着 `notes/old.md`，盘上只有内容相同的 `notes/a.md` ⇒ `detect_path_moves()` 判成一次移动。

    （`md_sha256` 按**当前 a.md 的真实内容**算 ⇒ 与"清单里的 old.md"哈希相同 ⇒ 配对成 rename。）
    """
    sha = hashlib.sha256(A_MD.encode("utf-8")).hexdigest()
    root = _write_kb(tmp_path / "kb2", _manifest_yaml([("notes/old.md", sha)]))
    service = DocumentService(kb_path=str(root))

    checked = validate_plan(str(root), _plan({"op": "rebuild_manifest", "op_id": "o1"}), service=service)
    assert checked["status"] == "error", checked
    assert _codes(checked["errors"]) == ["manifest_blocked_by_path_moves"]
    assert "修复路径" in checked["errors"][0]["message"], "必须给出可照做的恢复指引"


# ── ③ 顺序规矩：必须收尾 ────────────────────────────────────────────────────


def test_rebuild_manifest_must_be_the_last_op(kb: Path, service: DocumentService) -> None:
    new_file = {"op": "create_file", "op_id": "o2", "file": "notes/新篇.md", "body": "# 新篇\n"}
    bad = _plan({"op": "rebuild_manifest", "op_id": "o1"}, new_file)
    checked = validate_plan(str(kb), bad, service=service)
    assert _codes(checked["errors"]) == ["manifest_must_be_last"]

    good = _plan({**new_file, "op_id": "o1"}, {"op": "rebuild_manifest", "op_id": "o2"})
    checked_good = validate_plan(str(kb), good, service=service)
    assert checked_good["status"] == "ok", checked_good
    assert [call["primitive"] for call in compile_plan(str(kb), good, service=service)["calls"]] == [
        "create_file",
        "rebuild_manifest",
    ]


# ── ④ 真实工具入口 ──────────────────────────────────────────────────────────


def _tool_registry(kb: Path) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb), session_id=SESSION))


def _invoke(kb: Path, name: str, **arguments: Any):
    return _tool_registry(kb).invoke(
        ToolCall(id="c1", name=name, arguments=json.dumps(arguments, ensure_ascii=False))
    )


def test_rebuild_manifest_round_trip_through_the_real_tool(kb: Path) -> None:
    """它**没有 `file`** ⇒ 不必先读（读后写闸按 `file` 收目标）；一次调用即落盘。"""
    written = _invoke(
        kb, PROPOSE_TOOL_NAME, intent="清单陈旧，重建一次",
        ops=[{"op": "rebuild_manifest", "op_id": "o1"}],
    )
    assert written.is_error is False, written.content
    assert written.content.startswith("**已写入**"), written.content
    assert audit_manifest_diff(str(kb))["summary"]["warning_count"] == 0


def test_propose_tool_documents_rebuild_manifest(kb: Path) -> None:
    tool = _tool_registry(kb).get(PROPOSE_TOOL_NAME)
    assert tool is not None
    for needle in ("rebuild_manifest", "manifest_blocked_by_path_moves", "收尾"):
        assert needle in tool.description, f"提议工具说明里缺 {needle}"
