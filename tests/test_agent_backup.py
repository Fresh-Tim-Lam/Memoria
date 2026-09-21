"""写模块**备份子系统**（`services/agent/backup.py`）的离线单测：写前 pre-image / 保留 / 撤销。

口径来源：`docs/design/agent-capabilities.md` §2.3.2（人已拍板 `agent-plugin-design.md` §4 Q5 = ①）。
覆盖：① 原字节保真与"只动备份目录"；② 新建文件记 `existed:false` 且不留字节；
③ 单文件 / 单批超限 ⇒ 预检失败且**不留半个批次**；④ 路径越界 / 非法 id / 非法 txid；
⑤ 撤销往返（字节级）；⑥ **外部改动保护**（apply 之后被手改 ⇒ 拒绝撤销且不覆盖）；
⑦ 无 `post.json` 默认拒（fail-closed）；⑧ 保留口径（FIFO、最新批次永不淘汰）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from memoria.services.agent.backup import (
    FILES_DIR,
    JOURNAL_NAME,
    POST_NAME,
    backups_root,
    batch_dir,
    list_batches,
    read_journal,
    record_post_images,
    restore_batch,
    snapshot_pre_images,
    trim_backups,
)

SESSION = "session-20260920T021100Z-abcd1234"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text("# A\n\n第一行。\n", encoding="utf-8")
    (root / "notes" / "b.md").write_text("# B\n\n第二行。\n", encoding="utf-8")
    (root / ".memoria" / "manifest.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    return root


def _txid(n: int) -> str:
    return f"20260920T0211{n:02d}Z-{n:02d}"


def test_snapshot_is_byte_identical_and_touches_only_backups(kb: Path) -> None:
    """① 逐字节保真；除 `.memoria/agent/backups/**` 外**一个文件都不动**。"""
    before = {p: _sha(p) for p in kb.rglob("*") if p.is_file()}
    res = snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md", ".memoria/manifest.yaml"], tool_id="upsert_kp")
    # 注意：Windows 上 `write_text` 会把 `\n` 翻成 `\r\n`，故"字节数"一律按盘上实际大小算（不硬编码）
    expected_bytes = (kb / "notes/a.md").stat().st_size + (kb / ".memoria" / "manifest.yaml").stat().st_size
    assert res["status"] == "ok" and res["bytes"] == expected_bytes

    root = Path(batch_dir(str(kb), SESSION, _txid(1)))
    assert (root / "journal.json").is_file()
    assert _sha(root / FILES_DIR / "notes" / "a.md") == before[kb / "notes" / "a.md"]
    assert _sha(root / FILES_DIR / ".memoria" / "manifest.yaml") == before[kb / ".memoria" / "manifest.yaml"]

    journal = read_journal(str(kb), SESSION, _txid(1))
    assert journal["txid"] == _txid(1) and journal["session_id"] == SESSION and journal["tool_id"] == "upsert_kp"
    assert [f["rel_path"] for f in journal["files"]] == ["notes/a.md", ".memoria/manifest.yaml"]
    assert all(f["existed"] and f["sha256"] for f in journal["files"])

    after = {p: _sha(p) for p in kb.rglob("*") if p.is_file()}
    untouched = {p: v for p, v in after.items() if not str(p).startswith(str(Path(backups_root(str(kb)))))}
    assert untouched == before  # 事实源逐字节不变


def test_snapshot_records_new_files_without_bytes(kb: Path) -> None:
    """② 新建文件：记 `existed:false`、**不留 0 字节副本**（撤销时按"删除"处理）。"""
    res = snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/new.md"])
    assert res["status"] == "ok" and res["files"] == [{"rel_path": "notes/new.md", "existed": False, "sha256": None, "bytes": 0}]
    assert not (Path(batch_dir(str(kb), SESSION, _txid(1))) / FILES_DIR / "notes" / "new.md").exists()
    assert not (Path(backups_root(str(kb))) / SESSION / f"{_txid(1)}.tmp-0").exists()


def test_snapshot_fails_closed_on_size_limits(kb: Path) -> None:
    """③ 单文件 / 单批超限 ⇒ 预检失败，**不留半个批次**（不降级为"无备份的写入"）。"""
    big = kb / "notes" / "big.md"
    big.write_text("x" * 64, encoding="utf-8")
    too_big = snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/big.md"], max_file_bytes=32)
    assert too_big["status"] == "error" and too_big["code"] == "file_too_large"
    assert not Path(batch_dir(str(kb), SESSION, _txid(1))).exists()

    over_batch = snapshot_pre_images(
        str(kb), SESSION, _txid(2), ["notes/a.md", "notes/big.md"], max_file_bytes=1000, max_batch_bytes=30
    )
    assert over_batch["status"] == "error" and over_batch["code"] == "batch_too_large"
    assert not Path(batch_dir(str(kb), SESSION, _txid(2))).exists()
    assert not [p for p in Path(backups_root(str(kb))).rglob("*.tmp-*")]  # 无临时残留


def test_snapshot_rejects_escape_and_bad_ids(kb: Path) -> None:
    """④ 路径越界 / 非法会话 id / 非法 txid 一律结构化拒绝，且不写盘。"""
    outside = snapshot_pre_images(str(kb), SESSION, _txid(1), ["../outside.md"])
    assert outside["code"] == "path_rejected"
    absolute = snapshot_pre_images(str(kb), SESSION, _txid(1), ["/etc/passwd"])
    assert absolute["code"] == "path_rejected"  # 绝对路径**拒**，不当相对路径用
    bad_sid = snapshot_pre_images(str(kb), "../evil", _txid(1), ["notes/a.md"])
    assert bad_sid["status"] == "error" and bad_sid["code"] == "backup_failed"
    bad_txid = snapshot_pre_images(str(kb), SESSION, "not-a-txid", ["notes/a.md"])
    assert bad_txid["status"] == "error"
    assert not Path(backups_root(str(kb))).exists() or not any(Path(backups_root(str(kb))).iterdir())


def test_restore_round_trip_is_byte_identical(kb: Path) -> None:
    """⑤ 撤销往返：pre-image → 模拟 apply 改写 → 撤销 ⇒ 逐字节回到原样；新建文件被删。"""
    original = {p: p.read_bytes() for p in (kb / "notes" / "a.md", kb / "notes" / "b.md")}
    assert snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md", "notes/b.md", "notes/new.md"])["status"] == "ok"
    # 模拟 apply：改写 a.md、删除 b.md、新建 new.md
    (kb / "notes" / "a.md").write_text("# A\n\n改写后的正文。\n", encoding="utf-8")
    (kb / "notes" / "b.md").unlink()
    (kb / "notes" / "new.md").write_text("# NEW\n", encoding="utf-8")
    assert record_post_images(str(kb), SESSION, _txid(1))["status"] == "ok"

    res = restore_batch(str(kb), SESSION, _txid(1))
    assert res["status"] == "ok" and res["verified"] is True
    assert (kb / "notes" / "a.md").read_bytes() == original[kb / "notes" / "a.md"]
    assert (kb / "notes" / "b.md").read_bytes() == original[kb / "notes" / "b.md"]
    assert not (kb / "notes" / "new.md").exists()  # 新建 ⇒ 撤销 = 删除
    actions = {row["rel_path"]: row["action"] for row in res["files"]}
    assert actions == {"notes/a.md": "restored", "notes/b.md": "restored", "notes/new.md": "removed"}


def test_restore_refuses_when_file_changed_after_apply(kb: Path) -> None:
    """⑥ **外部改动保护**：apply 之后被手改 ⇒ 拒绝撤销，且**不覆盖**用户手改。"""
    assert snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md"])["status"] == "ok"
    (kb / "notes" / "a.md").write_text("# A\n\nagent 写的。\n", encoding="utf-8")
    record_post_images(str(kb), SESSION, _txid(1))
    (kb / "notes" / "a.md").write_text("# A\n\n用户手改的。\n", encoding="utf-8")

    res = restore_batch(str(kb), SESSION, _txid(1))
    assert res["status"] == "error" and res["code"] == "external_change"
    assert res["rel_path"] == "notes/a.md"
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8").endswith("用户手改的。\n")  # 未被覆盖


def test_restore_requires_post_images_by_default(kb: Path) -> None:
    """⑦ 无 `post.json`（未经 apply 入口）⇒ 默认拒（fail-closed）；显式人工处置才放行并如实标记。"""
    snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md"])
    (kb / "notes" / "a.md").write_text("changed\n", encoding="utf-8")
    refused = restore_batch(str(kb), SESSION, _txid(1))
    assert refused["status"] == "error" and refused["code"] == "unverified"
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8") == "changed\n"

    forced = restore_batch(str(kb), SESSION, _txid(1), allow_unverified=True)
    assert forced["status"] == "ok" and forced["verified"] is False
    assert (kb / "notes" / "a.md").read_text(encoding="utf-8").startswith("# A")


def test_trim_keeps_newest_and_evicts_fifo(kb: Path) -> None:
    """⑧ 保留口径：每会话只留最新 5 批、FIFO 淘汰最旧，且**最新批次永不淘汰**。"""
    for n in range(1, 8):
        (kb / "notes" / "a.md").write_text(f"# A 第 {n} 版\n", encoding="utf-8")
        assert snapshot_pre_images(str(kb), SESSION, _txid(n), ["notes/a.md"])["status"] == "ok"
    assert [row["txid"] for row in list_batches(str(kb), SESSION)] == [_txid(n) for n in range(1, 8)]

    out = trim_backups(str(kb), SESSION)
    assert out["status"] == "ok" and out["kept"] == 5
    left = [row["txid"] for row in list_batches(str(kb), SESSION)]
    assert left == [_txid(n) for n in range(3, 8)]  # 最旧两批被淘汰
    assert _txid(7) in left and _txid(1) not in left

    out2 = trim_backups(str(kb), SESSION, keep=1)
    assert [row["txid"] for row in list_batches(str(kb), SESSION)] == [_txid(7)]  # 最新永不淘汰
    assert out2["kept"] == 1


def test_journal_and_post_files_are_valid_json(kb: Path) -> None:
    """落盘形状可核对：journal / post 都是合法 JSON 且带版本号。"""
    snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md"], plugin="demo-plugin")
    record_post_images(str(kb), SESSION, _txid(1))
    root = Path(batch_dir(str(kb), SESSION, _txid(1)))
    journal = json.loads((root / JOURNAL_NAME).read_text(encoding="utf-8"))
    post = json.loads((root / POST_NAME).read_text(encoding="utf-8"))
    assert journal["v"] == 1 and journal["plugin"] == "demo-plugin"
    assert post["v"] == 1 and post["files"]["notes/a.md"]["existed"] is True
