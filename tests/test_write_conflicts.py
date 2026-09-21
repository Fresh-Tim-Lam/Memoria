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
from memoria.services.agent.backup import backups_root, restore_batch
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


def test_force_save_backs_up_disk_version_before_overwriting(api: UIAPI, kb: Path) -> None:
    """「以我为准」（`force=True`）：**先把盘上那一版抄进备份**（可撤销），再覆盖写。"""
    external = "# 别的窗口写的这一版\n"
    (kb / "notes" / "a.md").write_text(external, encoding="utf-8")

    res = api.save_document("notes/a.md", "# 我的这一版\n", "", True)
    assert res["status"] == "ok", res
    assert res["version"] == rel_version(str(kb), "notes/a.md")
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == "# 我的这一版\n"

    info = res["force_backup"]
    assert info["session_id"] == "manual-force"
    batch = Path(info["dir"])
    assert (batch / "journal.json").is_file() and (batch / "post.json").is_file()
    # 备份里存的是**被覆盖掉的那一版**，且能直接回滚（复用备份子系统的撤销）
    copied = (batch / "files" / "notes" / "a.md").read_text(encoding="utf-8")
    assert copied == external
    undone = restore_batch(str(kb), "manual-force", info["txid"])
    assert undone["status"] == "ok", undone
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == external


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


# ── 前端接线不变量（JS）：这套令牌"通没通电"全靠这几行，回归时最容易被静默改坏 ──

_ROOT = Path(__file__).resolve().parents[1]
_APP_JS = _ROOT / "src" / "memoria" / "ui" / "static" / "app" / "js" / "app.js"
_LOCALES = [
    _ROOT / "src" / "memoria" / "ui" / "static" / "app" / "i18n" / "zh-CN.js",
    _ROOT / "src" / "memoria" / "ui" / "static" / "app" / "i18n" / "en.js",
]
_CONFLICT_KEYS = ("title", "body", "reload", "force", "later", "reloaded", "forced", "forceFail")


def test_frontend_wires_version_token_and_conflict_dialog() -> None:
    """`app.js`：保存带版本 + 成功后滚动基线 + `stale_write` 走三选一 + apply 忙位让路。"""
    src = _APP_JS.read_text(encoding="utf-8")
    assert 'call("save_document", state.currentPath, body, state.doc?.version || "")' in src
    assert "if (state.doc && res.version) state.doc.version = res.version;" in src
    assert "window.MemoriaWriteGuard?.onSaveFailed?.(res, state.currentPath, body)" in src
    assert "window.MemoriaWriteGuard?.deferIfBusy?.(markDirty)" in src

    block = src[src.index("(function memoriaWriteGuard()") :]
    for needle in (
        'data-act="reload"',
        'data-act="force"',
        'data-act="later"',
        'A().call?.("save_document", path, body, "", true)',  # 「以我为准」= force（后端先备份）
        "setBusy: (v) => { busy = !!v; }",
    ):
        assert needle in block, f"冲突保护块缺少：{needle}"


@pytest.mark.parametrize("locale", _LOCALES, ids=lambda p: p.name)
def test_conflict_dialog_keys_exist_in_every_locale(locale: Path) -> None:
    """中英必须成对（缺一个键 ⇒ 弹窗会出现裸 key）。"""
    src = locale.read_text(encoding="utf-8")
    assert "writeConflict: {" in src
    for key in _CONFLICT_KEYS:
        assert f"{key}:" in src, f"{locale.name} 缺 writeConflict.{key}"


# --- `os.replace` 的有界退避重试（写路径的瞬时锁；口径见 atomic_write.py 模块 docstring）---


def _win_error(code: int, src: str = "a", dst: str = "b") -> OSError:
    """构造带 `winerror` 的 `OSError`（Windows 上 `os.replace` 的失败形态）。"""
    exc = OSError(13, "拒绝访问。", src, code)
    exc.winerror = code  # type: ignore[attr-defined]
    return exc


def test_replace_with_retry_survives_transient_winerror(monkeypatch: pytest.MonkeyPatch) -> None:
    """`WinError 5` 是该重试的（瞬时锁）：前两次失败、第三次成功 ⇒ 不抛出、最终替换完成。"""
    from memoria.storage import atomic_write

    calls: list[tuple[str, str]] = []
    sleeps: list[float] = []

    def flaky(src: str, dst: str) -> None:
        calls.append((src, dst))
        if len(calls) < 3:
            raise _win_error(5)

    monkeypatch.setattr(atomic_write.os, "replace", flaky)
    monkeypatch.setattr(atomic_write.time, "sleep", lambda s: sleeps.append(s))

    atomic_write.replace_with_retry("t.tmp", "t.md")  # 不抛 = 救回来了

    assert len(calls) == 3 and sleeps == [atomic_write.DELAY] * 2


def test_replace_with_retry_raises_non_transient_without_retrying(monkeypatch: pytest.MonkeyPatch) -> None:
    """非瞬时错误（如 `WinError 3` 路径不存在）**立刻抛**，不被重试掩盖。"""
    from memoria.storage import atomic_write

    calls: list[int] = []

    def boom(src: str, dst: str) -> None:
        calls.append(1)
        raise _win_error(3)

    monkeypatch.setattr(atomic_write.os, "replace", boom)
    monkeypatch.setattr(atomic_write.time, "sleep", lambda s: pytest.fail("不该重试"))

    with pytest.raises(OSError):
        atomic_write.replace_with_retry("t.tmp", "t.md")
    assert len(calls) == 1


def test_replace_with_retry_gives_up_after_bounded_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """重试**有界**：一直 `WinError 32` ⇒ 用满次数后**仍然抛**（绝不吞成静默失败）。"""
    from memoria.storage import atomic_write

    calls: list[int] = []

    def always_locked(src: str, dst: str) -> None:
        calls.append(1)
        raise _win_error(32)

    monkeypatch.setattr(atomic_write.os, "replace", always_locked)
    monkeypatch.setattr(atomic_write.time, "sleep", lambda s: None)

    with pytest.raises(OSError):
        atomic_write.replace_with_retry("t.tmp", "t.md")
    assert len(calls) == atomic_write.ATTEMPTS
