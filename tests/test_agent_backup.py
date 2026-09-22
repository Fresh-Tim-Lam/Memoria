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
    AFTER_DIR,
    AFTER_ZIP,
    FILES_DIR,
    FORCE_SESSION,
    JOURNAL_NAME,
    ORIGIN_TXID,
    POST_NAME,
    after_paths,
    backups_root,
    batch_dir,
    compact_after_images,
    ensure_origin,
    list_batches,
    push_stack,
    read_after_images,
    read_journal,
    read_stack,
    record_post_images,
    redo_step,
    restore_batch,
    restore_session,
    snapshot_after_images,
    snapshot_pre_images,
    stack_state,
    trim_backups,
    undo_step,
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


# ── ⑨ 对话粒度撤销（人 2026-09-21：「撤销以对话为粒度，每次对话留一次撤回就 ok」）──────


def _two_batches(kb: Path) -> None:
    """造两批连续的写入（第二批的 pre-image 就是第一批写后的盘面），并按 `apply_plan()` 的做法固化起点。"""
    a = kb / "notes" / "a.md"
    snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md"])
    ensure_origin(str(kb), SESSION, _txid(1), ["notes/a.md"])  # 起点 = 第一批的 pre-image（对话开始前）
    a.write_text("# A\n\n第一行。\n第 1 批。\n", encoding="utf-8")
    record_post_images(str(kb), SESSION, _txid(1))
    snapshot_pre_images(str(kb), SESSION, _txid(2), ["notes/a.md"])
    ensure_origin(str(kb), SESSION, _txid(2), ["notes/a.md"])  # 起点里已有它 ⇒ 不动（先到者 = 更早那版）
    a.write_text("# A\n\n第一行。\n第 2 批。\n", encoding="utf-8")
    record_post_images(str(kb), SESSION, _txid(2))


def test_restore_session_returns_to_the_origin_state(kb: Path) -> None:
    """一次对话写了两批 ⇒ 一次 `restore_session()` 回到**对话开始前**。

    目标状态是**起点快照**（`<session>/origin/`，第一次写入前拍下）—— 既不逐批回放，也不受批次
    FIFO 淘汰影响（人 2026-09-21：「你的设计根本和 git 的机制不同」⇒ 改成"指向一个状态"）。
    """
    a = kb / "notes" / "a.md"
    original = a.read_bytes()
    _two_batches(kb)

    res = restore_session(str(kb), SESSION)

    assert res["status"] == "ok", res
    assert a.read_bytes() == original
    assert res["origin"] == {"notes/a.md": ORIGIN_TXID}
    assert (Path(backups_root(str(kb))) / SESSION / "origin" / JOURNAL_NAME).is_file()
    # 起点快照**不是批次** ⇒ 不会被 `list_batches` 当批次、也不会被 trim 淘汰
    assert [row["txid"] for row in list_batches(str(kb), SESSION)] == [_txid(1), _txid(2)]
    # 撤销留痕：**一条**汇总事件
    log = (kb / ".memoria" / "agent" / "sessions" / f"{SESSION}.jsonl").read_text(encoding="utf-8")
    assert log.count("capability/undo") == 1


def test_restore_session_never_blocks_and_keeps_a_safety_backup(kb: Path) -> None:
    """盘面被别的写者改过也**不拒绝**（人：「一键生效，不再有被阻止」）—— 但会先自动兜底那一版。

    真机场景：agent 写完 → 人跑产品「构建」（产品把 `links[]` 同步进 sidecar）⇒ 旧实现判
    `external_change` 整批拒（人连点两次都失败）。现在：覆盖前把**当前**版本另存 `manual-force`
    批次 ⇒ 覆盖 ≠ 丢数据，所以可以直接撤。
    """
    a = kb / "notes" / "a.md"
    original = a.read_bytes()
    _two_batches(kb)
    a.write_text("# A\n\n第一行。\n产品构建改的。\n", encoding="utf-8")
    built = a.read_bytes()

    res = restore_session(str(kb), SESSION)

    assert res["status"] == "ok", res  # 不再有 external_change
    assert a.read_bytes() == original  # 一次回到对话开始前
    backup = res["safety_backup"]
    assert backup["session_id"] == FORCE_SESSION and backup["txid"]
    again = restore_batch(str(kb), backup["session_id"], backup["txid"])
    assert again["status"] == "ok", again
    assert a.read_bytes() == built  # 被覆盖掉的那一版没丢，可原样拿回


def test_restore_session_reports_no_origin_for_a_legacy_session(kb: Path) -> None:
    """**旧版本写的对话**没有起点快照 ⇒ 明确回 `no_origin`（不假装成功，也不乱猜起点）。"""
    snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md"])
    record_post_images(str(kb), SESSION, _txid(1))
    before = (kb / "notes" / "a.md").read_bytes()

    res = restore_session(str(kb), SESSION)

    assert res["status"] == "error" and res["code"] == "no_origin"
    assert (kb / "notes" / "a.md").read_bytes() == before  # 零写入


# ── ⑩ 强制撤销（人 2026-09-21 真机撞出："agent 写完 → 我跑了「构建」→ 撤回被阻止"）────────


def test_force_restore_backs_up_the_current_revision_first(kb: Path) -> None:
    """强制撤销：先把**当前**那一版另存为 `manual-force` 批次，**再**还原 ⇒ 覆盖不等于丢数据。

    真机场景：agent 写完 → 用户跑产品「构建」（产品把 `links[]` 同步进 sidecar）⇒ 盘面 ≠ 该批
    post 哈希 ⇒ 普通撤销 fail-closed 拒（**这是对的**：不静默覆盖别人的写）。此时用户想要的是
    "撤，但别丢掉我刚构建出来的东西" ⇒ 强制撤销先兜底、再还原。
    """
    a = kb / "notes" / "a.md"
    original = a.read_bytes()
    snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md"])
    a.write_text("# A\n\n第一行。\nagent 写的。\n", encoding="utf-8")
    record_post_images(str(kb), SESSION, _txid(1))
    a.write_text("# A\n\n第一行。\n构建之后的。\n", encoding="utf-8")  # 另一个写者（产品「构建」）
    built = a.read_bytes()

    refused = restore_batch(str(kb), SESSION, _txid(1))
    assert refused["status"] == "error" and refused["code"] == "external_change"
    assert refused["stale"] == ["notes/a.md"]
    assert a.read_bytes() == built  # 拒就是拒：一个字节都不动

    forced = restore_batch(str(kb), SESSION, _txid(1), force=True)
    assert forced["status"] == "ok", forced
    assert forced["forced"] == ["notes/a.md"]
    assert a.read_bytes() == original  # 还原到写入前

    # 被覆盖掉的"构建之后那一版"没丢：另存为 manual-force 批次，且能原样还原回来
    backup = forced["force_backup"]
    assert backup["session_id"] == FORCE_SESSION and backup["txid"]
    again = restore_batch(str(kb), backup["session_id"], backup["txid"])
    assert again["status"] == "ok", again
    assert a.read_bytes() == built


def test_force_session_constant_matches_the_file_version_one() -> None:
    """`backup.FORCE_SESSION` 必须与 `storage/file_version.FORCE_SESSION` 同值（此处独立定义只为避开 import 环）。"""
    from memoria import storage

    assert FORCE_SESSION == storage.file_version.FORCE_SESSION


# ── ⑪ 栈式撤销 / 重做（人 2026-09-21 定稿："等等，近邻不压缩，深的压缩"）────────────────
#
# 口径：每次写入 = 栈里一步；撤销一步用该批 **pre-image**，重做一步用该批 **写后镜像**；
# 新写入从**当前指针**截断旧 redo 分支（批次目录不删，只是不再可达）；写后镜像**分层存储** ——
# 离栈顶 `AFTER_PLAIN_KEEP` 步以内保持原始文件（redo 零解压），更深的压成 `after.zip`。


def _write_batch(kb: Path, n: int, text: str, rel: str = "notes/a.md") -> str:
    """按 `apply_plan()` 的做法造一批（并压栈）：pre-image → 固化起点 → 改盘 → post → 写后镜像 → 压栈。

    返回该批 txid。需要造"当时没存写后镜像"的旧批次时，直接手写这几步、跳过 `snapshot_after_images()`。
    """
    txid = _txid(n)
    snapshot_pre_images(str(kb), SESSION, txid, [rel])
    ensure_origin(str(kb), SESSION, txid, [rel])
    (kb / rel).write_text(text, encoding="utf-8")
    record_post_images(str(kb), SESSION, txid)
    assert snapshot_after_images(str(kb), SESSION, txid)["status"] == "ok"
    assert push_stack(str(kb), SESSION, txid)["status"] == "ok"
    return txid


def test_after_images_keep_near_neighbours_plain_and_zip_the_deeper_ones(kb: Path) -> None:
    """**分层存储**：离栈顶 `keep_plain=2` 步以内的批次保持 `after/` 原始文件；更深的压成 `after.zip`。

    这是人 2026-09-21 那句话的字面落地："近邻不压缩（redo 零解压），深的压缩（省盘）"。
    """
    a = kb / "notes" / "a.md"
    for n in range(1, 5):
        _write_batch(kb, n, f"# A\n\n第 {n} 批。\n")

    out = compact_after_images(str(kb), SESSION, keep_plain=2)
    assert out["status"] == "ok" and out["compacted"] == [_txid(1), _txid(2)]

    for n in (1, 2):  # 深的：原始目录消失、zip 出现
        plain, packed, _meta = after_paths(str(kb), SESSION, _txid(n))
        assert not Path(plain).is_dir() and Path(packed).is_file()
    for n in (3, 4):  # 近邻：原样不动
        plain, packed, _meta = after_paths(str(kb), SESSION, _txid(n))
        assert Path(plain).is_dir() and not Path(packed).exists()

    # 形态变了但**读端不变**：两种载体都还能读出元数据，而且近邻那份就是盘上文件的字节
    for n in range(1, 5):
        entries = read_after_images(str(kb), SESSION, _txid(n))
        assert entries and entries["notes/a.md"]["existed"] is True
    assert read_after_images(str(kb), SESSION, _txid(4))["notes/a.md"]["sha256"] == _sha(a)

    # 幂等：再压一次不重复处理
    assert compact_after_images(str(kb), SESSION, keep_plain=2)["compacted"] == []


def test_redo_step_works_from_a_compacted_zip_image(kb: Path) -> None:
    """**被压缩过的那一步仍可重做** ⇒ 压缩只是省盘，不影响栈的可逆性。"""
    for n in range(1, 4):
        _write_batch(kb, n, f"# A\n\n第 {n} 批。\n")
    third = (kb / "notes" / "a.md").read_bytes()
    compact_after_images(str(kb), SESSION, keep_plain=1)  # 第 1、2 批压成 zip
    assert Path(after_paths(str(kb), SESSION, _txid(1))[1]).is_file()

    assert undo_step(str(kb), SESSION)["status"] == "ok"
    assert undo_step(str(kb), SESSION)["status"] == "ok"
    res = redo_step(str(kb), SESSION)
    assert res["status"] == "ok", res
    assert (kb / "notes" / "a.md").read_bytes() != third  # 只重做了一步（回到第 2 批）
    assert redo_step(str(kb), SESSION)["status"] == "ok"
    assert (kb / "notes" / "a.md").read_bytes() == third  # 再重做一步 ⇒ 追平最新


def test_undo_step_and_redo_step_are_byte_exact_inverses(kb: Path) -> None:
    """撤销一步 / 重做一步**互逆且逐字节**：撤销用 pre-image、重做用写后镜像。"""
    a = kb / "notes" / "a.md"
    original = a.read_bytes()
    _write_batch(kb, 1, "# A\n\n第一行。\n第 1 批。\n")
    written = a.read_bytes()

    state1 = stack_state(str(kb), SESSION)
    assert (state1["total"], state1["position"], state1["cursor"]) == (1, 1, 0)
    assert state1["can_undo"] is True and state1["can_redo"] is False
    assert state1["steps"][0]["current"] is True and state1["steps"][0]["has_after"] is True

    undone = undo_step(str(kb), SESSION)
    assert undone["status"] == "ok" and undone["direction"] == "undo"
    assert a.read_bytes() == original  # 逐字节回到写入前
    state0 = stack_state(str(kb), SESSION)
    assert (state0["position"], state0["can_undo"], state0["can_redo"]) == (0, False, True)

    redone = redo_step(str(kb), SESSION)
    assert redone["status"] == "ok" and redone["direction"] == "redo"
    assert a.read_bytes() == written
    assert stack_state(str(kb), SESSION)["position"] == 1

    # 撤销留痕：两次操作各一条事件（fail-open 但如实）
    log = (kb / ".memoria" / "agent" / "sessions" / f"{SESSION}.jsonl").read_text(encoding="utf-8")
    assert log.count("capability/undo") == 1 and log.count("capability/redo") == 1


def test_undo_step_on_a_new_file_removes_it_and_redo_brings_it_back(kb: Path) -> None:
    """新建文件那一步：撤销 = 删除（不留 0 字节），重做 = 原样写回。"""
    rel = "notes/new.md"
    _write_batch(kb, 1, "# NEW\n\n正文。\n", rel=rel)
    content = (kb / rel).read_bytes()

    assert undo_step(str(kb), SESSION)["status"] == "ok"
    assert not (kb / rel).exists()
    assert redo_step(str(kb), SESSION)["status"] == "ok"
    assert (kb / rel).read_bytes() == content


def test_undo_and_redo_report_the_two_ends_of_the_stack(kb: Path) -> None:
    """栈底 / 栈顶：撤销到头回 `stack_bottom`、重做到头回 `stack_top`（各自零写入）。"""
    empty_undo = undo_step(str(kb), SESSION)
    assert empty_undo["status"] == "error" and empty_undo["code"] == "stack_bottom"
    empty_redo = redo_step(str(kb), SESSION)
    assert empty_redo["status"] == "error" and empty_redo["code"] == "stack_top"

    _write_batch(kb, 1, "# A\n\n第 1 批。\n")
    assert undo_step(str(kb), SESSION)["status"] == "ok"
    bottom = undo_step(str(kb), SESSION)
    assert bottom["status"] == "error" and bottom["code"] == "stack_bottom"
    assert redo_step(str(kb), SESSION)["status"] == "ok"
    top = redo_step(str(kb), SESSION)
    assert top["status"] == "error" and top["code"] == "stack_top"


def test_redo_step_is_honest_when_the_batch_has_no_after_image(kb: Path) -> None:
    """旧批次没存写后镜像 ⇒ 如实回 `no_after`，**不假装成功**（撤销仍可用）。"""
    a = kb / "notes" / "a.md"
    snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md"])
    a.write_text("# A\n\n第 1 批。\n", encoding="utf-8")
    record_post_images(str(kb), SESSION, _txid(1))
    push_stack(str(kb), SESSION, _txid(1))
    written = a.read_bytes()

    assert undo_step(str(kb), SESSION)["status"] == "ok"
    res = redo_step(str(kb), SESSION)
    assert res["status"] == "error" and res["code"] == "no_after"
    assert a.read_bytes() != written  # 没重做成功就不该动盘


def test_push_stack_truncates_the_old_redo_branch_without_deleting_backups(kb: Path) -> None:
    """新写入从**当前指针**截断旧 redo 分支：批次目录仍在盘上，只是不再可达。"""
    first = _write_batch(kb, 1, "# A\n\n第 1 批。\n")
    second = _write_batch(kb, 2, "# A\n\n第 2 批。\n")
    assert undo_step(str(kb), SESSION)["status"] == "ok"  # 指针回到第 1 批

    third = _write_batch(kb, 3, "# A\n\n第 3 批。\n")  # 新写入 ⇒ 第 2 批成"废分支"

    stack = read_stack(str(kb), SESSION)
    assert stack["txids"] == [first, third] and stack["cursor"] == 1
    assert [row["txid"] for row in list_batches(str(kb), SESSION)] == [first, second, third]  # 没删
    assert Path(batch_dir(str(kb), SESSION, second)).is_dir()
    assert stack_state(str(kb), SESSION)["can_redo"] is False


def test_stack_json_is_not_mistaken_for_a_batch(kb: Path) -> None:
    """`stack.json` 落在会话目录里 ⇒ `list_batches()` 必须跳过它（否则 `_check_txid` 抛 ValueError）。"""
    _write_batch(kb, 1, "# A\n\n第 1 批。\n")
    stack_file = Path(backups_root(str(kb))) / SESSION / "stack.json"
    assert stack_file.is_file()
    payload = json.loads(stack_file.read_text(encoding="utf-8"))
    assert payload["v"] == 1 and payload["txids"] == [_txid(1)] and payload["cursor"] == 0
    assert [row["txid"] for row in list_batches(str(kb), SESSION)] == [_txid(1)]  # 不炸、也不多一行


def test_legacy_session_without_stack_json_still_undoes_step_by_step(kb: Path) -> None:
    """旧版本写的对话没有 `stack.json` ⇒ 按批次表**合成栈**（指针在最新一批），逐步撤销照常可用。"""
    a = kb / "notes" / "a.md"
    for n in (1, 2):
        snapshot_pre_images(str(kb), SESSION, _txid(n), ["notes/a.md"])
        a.write_text(f"# A\n\n第 {n} 批。\n", encoding="utf-8")
        record_post_images(str(kb), SESSION, _txid(n))
    latest = a.read_bytes()

    stack = read_stack(str(kb), SESSION)
    assert stack["txids"] == [_txid(1), _txid(2)] and stack["cursor"] == 1
    assert undo_step(str(kb), SESSION)["status"] == "ok"  # 撤销 = 第 2 批的 pre-image
    assert a.read_bytes() != latest
    assert undo_step(str(kb), SESSION)["status"] == "ok"  # 继续撤到第 1 批


def test_undo_step_backs_up_the_overwritten_revision_first(kb: Path) -> None:
    """撤销一步覆盖前**自动兜底**：当前版本另存 `manual-force` 批次 ⇒ 覆盖 ≠ 丢数据。"""
    a = kb / "notes" / "a.md"
    original = a.read_bytes()
    _write_batch(kb, 1, "# A\n\n第 1 批。\n")
    a.write_text("# A\n\n产品构建改的。\n", encoding="utf-8")  # 另一个写者
    built = a.read_bytes()

    res = undo_step(str(kb), SESSION)
    assert res["status"] == "ok", res
    assert a.read_bytes() == original
    backup = res["safety_backup"]
    assert backup and backup["session_id"] == FORCE_SESSION
    again = restore_batch(str(kb), backup["session_id"], backup["txid"])
    assert again["status"] == "ok", again
    assert a.read_bytes() == built  # 被覆盖的那一版可原样拿回


# ── ⑫ 备份 rename 的瞬时锁重试（人 2026-09-21 报「agent 没有做出行动」的真因之一）──────────


def _win_error(code: int, src: str = "a", dst: str = "b") -> OSError:
    """构造带 `winerror` 的 `OSError`（Windows 上 `os.replace` 的失败形态）。"""
    exc = OSError(13, "拒绝访问。", src, code)
    exc.winerror = code  # type: ignore[attr-defined]
    return exc


def test_batch_rename_survives_a_transient_winerror5(kb: Path, monkeypatch) -> None:
    """批次目录 rename 撞 Windows 瞬时锁 ⇒ **有界重试救回**，不再整批写入失败。

    真机（`AAA_Vocab`，2026-09-21）：`propose_write` 正是死在这一次
    `os.replace(tmp_dir, final_dir)`（`…-01.tmp-42604 → …-01`、`[WinError 5] 拒绝访问`）⇒ 整批
    被拒、库内**一个字节没变**；而前端当时也不显示工具失败 ⇒ 人看到的是"agent 说它要写入，然后
    什么都没有"，即"卡在思考、没有行动"。口径同 `storage/atomic_write.py`：只对 `WinError 5/32`
    有界重试，耗尽仍抛（fail-closed）。
    """
    import os as os_mod

    from memoria.storage import atomic_write

    calls: list[int] = []
    real_replace = os_mod.replace

    def flaky(src, dst):
        calls.append(1)
        if len(calls) <= 2:
            raise _win_error(5, str(src), str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os_mod, "replace", flaky)
    monkeypatch.setattr(atomic_write.time, "sleep", lambda _s: None)

    res = snapshot_pre_images(str(kb), SESSION, _txid(1), ["notes/a.md"])

    assert res["status"] == "ok", res
    assert len(calls) == 3, "应重试两次后成功"
    assert Path(batch_dir(str(kb), SESSION, _txid(1))).is_dir()
    assert not [p for p in Path(backups_root(str(kb))).rglob("*.tmp-*")], "不留临时目录"
