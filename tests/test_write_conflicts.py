"""写冲突保护（**文件版本令牌**）的离线单测 —— 口径见 `docs/design/agent-plugin-design.md §9`：

1. **盘上版本 = 唯一权威**：不一致就**拒写**，绝不基于过期版本写；
2. **人的当下操作最高**：agent 的整批写在校验之后若文件被改过 ⇒ 整批拒（不静默赢）；
3. **冲突由人明示决定**：返回结构化 `stale_write`（带期望/当前版本），由前端弹「重载 / 以我为准」；
4. 不传版本 ⇒ **旧行为逐字不变**（既有调用方零影响；前端未接上时不会误伤）。

落点在 `memoria/storage/file_version.py`：`ui.py` 的两个 RPC（`load_document` / `save_document`）
**等量委托**进来，`services/document.py` 一行未动（零行漂移）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent.apply import apply_plan, compile_plan
from memoria.services.agent.backup import backups_root
from memoria.services.agent.plan import preview_plan
from memoria.storage.file_version import file_version, rel_version

A_MD = "# A 文档\n\n注意力机制是核心。\n\n末尾一行。\n"
SESSION = "session-20260920T021100Z-abcd1234"


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
        "txid": "20260920T021100Z-07",
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


def test_file_version_is_content_sha256(kb: Path) -> None:
    """版本 = 文件**字节**的 sha256；不存在回 `""`（内容相同 ⇒ 不算冲突）。"""
    path = kb / "notes" / "a.md"
    # 注意按**盘上真实字节**算：Windows 上 `write_text` 会把 `\n` 翻成 `\r\n`
    expect = hashlib.sha256(path.read_bytes()).hexdigest()
    assert file_version(str(path)) == expect
    assert rel_version(str(kb), "notes/a.md") == expect
    assert file_version(str(kb / "notes" / "nope.md")) == ""
    assert rel_version(None, "notes/a.md") == ""


def test_load_document_carries_version(api: UIAPI, kb: Path) -> None:
    """`load_document` 追加 `version` 字段（只增不改）—— 前端据此带上"我读到的是这一版"。"""
    doc = api.load_document("notes/a.md")
    assert doc["status"] == "ok"
    assert doc["version"] == rel_version(str(kb), "notes/a.md")
    assert api.load_document("notes/nope.md")["status"] == "error"  # 错误路径不带 version，原样


def test_save_document_accepts_matching_version_and_returns_new_one(api: UIAPI, kb: Path) -> None:
    """版本对得上 ⇒ 正常写，并**回写后新版本**（前端据此滚动基线）。"""
    base = rel_version(str(kb), "notes/a.md")
    res = api.save_document("notes/a.md", A_MD + "新增一行。\n", base)
    assert res["status"] == "ok", res
    assert res["version"] == rel_version(str(kb), "notes/a.md") != base
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8").endswith("新增一行。\n")


def test_save_document_rejects_stale_version(api: UIAPI, kb: Path) -> None:
    """**核心用例**：别人（另一个窗口 / 智能体）先写过 ⇒ 我的过期保存被拒，**盘上内容不被覆盖**。"""
    base = rel_version(str(kb), "notes/a.md")
    external = "# A 文档（别的窗口改的）\n"
    (kb / "notes" / "a.md").write_text(external, encoding="utf-8")

    res = api.save_document("notes/a.md", "# 我的过期内容\n", base)
    assert res["status"] == "error" and res["code"] == "stale_write"
    assert res["expected_version"] == base
    assert res["current_version"] == rel_version(str(kb), "notes/a.md")
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == external  # 未被静默覆盖


def test_save_document_without_version_keeps_legacy_behaviour(api: UIAPI, kb: Path) -> None:
    """不传版本 ⇒ 旧行为逐字不变（前端还没接上时不会误伤既有保存链路）。"""
    (kb / "notes" / "a.md").write_text("# 外部先改\n", encoding="utf-8")
    res = api.save_document("notes/a.md", "# 不带版本照写\n")
    assert res["status"] == "ok"
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == "# 不带版本照写\n"


def test_preview_plan_hands_out_base_versions(kb: Path, api: UIAPI) -> None:
    """`preview_plan()` 返回 `base_versions`：这就是"用户看过的那一版"的凭据。"""
    preview = preview_plan(str(kb), _plan(), service=api._svc)
    assert preview["previewed"] is True
    assert preview["base_versions"] == {"notes/a.md": rel_version(str(kb), "notes/a.md")}


def test_apply_plan_rejects_when_file_changed_after_preview(kb: Path, api: UIAPI) -> None:
    """**冲突保护**：预览之后、落地之前文件被改过 ⇒ 整批拒，且**不建备份、不写盘**。"""
    preview = preview_plan(str(kb), _plan(), service=api._svc)
    # 外部改动要**保结构**（行数与锚文本都不动）—— 否则 plan 本身就非法（那是另一条路径）
    (kb / "notes" / "a.md").write_text(A_MD.replace("是核心", "是核心（人改的）"), encoding="utf-8")
    before = (kb / "notes" / "a.md").read_text(encoding="utf-8")

    res = apply_plan(
        str(kb),
        _plan(),
        session_id=SESSION,
        base_versions=preview["base_versions"],
        service=api._svc,
    )
    assert res["status"] == "error" and res["code"] == "stale_write"
    assert res["files"] == ["notes/a.md"] and res["applied"] == []
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == before
    assert not Path(backups_root(str(kb))).exists()  # 连备份都还没建 ⇒ 真·零写入
    assert not Path(str(kb) + "/.memoria/sidecars/notes/a.memoria.yaml").exists()


def test_apply_plan_proceeds_when_versions_match(kb: Path, api: UIAPI) -> None:
    """版本一致 ⇒ 正常落地（回归：冲突保护不误伤正常路径）。"""
    preview = preview_plan(str(kb), _plan(), service=api._svc)
    res = apply_plan(
        str(kb),
        _plan(),
        session_id=SESSION,
        base_versions=preview["base_versions"],
        service=api._svc,
    )
    assert res["status"] == "ok", res
    assert res["backup"]["txid"] == "20260920T021100Z-07"
    assert compile_plan(str(kb), _plan(), service=api._svc)["base_versions"]  # 编译产物也带基准
