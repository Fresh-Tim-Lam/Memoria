# 设计来源（权威）：`docs/design/agent-capabilities.md` §2.3.2「备份（写前 pre-image）与撤销的数据面」；
# 口径已由人拍板（2026-09-20）：`agent-plugin-design.md` §4 Q5 = ①写前快照 + 会话内撤销。

"""写模块的**备份子系统**：写前 pre-image、保留/淘汰、以及**撤销**的数据面（§2.3.2）。

**它在写路径上的位置**：apply 入口的**第一步**（获批后、任何落盘之前）。本模块自身
**只写 `<kb>/.memoria/agent/backups/**`** —— 除 `restore_batch()`（撤销）外，它不碰任何
事实源；而 `restore_batch()` 写的正是"把备份写回原处"，且**默认 fail-closed**（见下）。

口径要点（逐条对应 §2.3.2）：

| 项 | 值 | 出处 |
|---|---|---|
| 目录 | `<kb>/.memoria/agent/backups/<session_id>/<txid>/{journal.json, files/<原相对路径>}` | §2.3.2 第 2 条 |
| 粒度 | 一次确认 = 一个事务 = 一个 `txid`；批内 = 该事务**受影响文件集**的逐文件整字节副本 | 第 1 条 |
| 新建文件 | 记 `{"existed": false}`、**不留字节**（撤销 = 删除该文件） | 第 1 条 |
| 格式 | **原字节复制**（不存 diff/patch；diff 只进 dry-run） | 第 2 条 |
| 上限 | 单文件 > **8 MiB** 或单批 > **32 MiB** ⇒ **预检失败、不落盘**（不降级为"无备份的写入"） | 第 2 条 |
| 保留 | 每会话 **5** 批 / 每库 **10** 个会话目录 / 每库 **64 MiB**，FIFO；**永不淘汰当前会话最新批次** | 第 3 条 |
| 不静默 | 淘汰产出被调用方记事件；**备份失败即不写**（fail-closed） | 第 3/4 条 |
| 撤销 | 按批次；**外部改动保护**：撤销前必须校验目标文件当前 sha256 == apply 时记录的 sha256，不符即**拒绝**（不静默覆盖用户手改） | 第 5 条 |

**本模块相对 §2.3.2 的两点本地补充（已登记，等设计稿同步）**：

1. **批次目录整体原子落位**：先在 `<session>/<txid>.tmp-<pid>` 下建好 `files/**` 与
   `journal.json`，再用 `os.replace()` 整目录改名到 `<txid>` ⇒ 任何一步失败都只需删临时
   目录，**不会留下半个批次**（比"先建目录再逐文件写"更强）。
2. **`post.json`（外部改动保护的依据）**：§2.3.2 第 2 条列的 journal 字段只有 pre-image 的
   `sha256`，但第 5 条又要求"撤销前校验当前 sha256 == **apply 时**记录的 sha256" —— apply
   发生在 journal 落盘**之后**，故 pre-image 哈希无法充当该凭据。本模块因此增加
   `record_post_images()`：apply 四原语跑完后由 apply 入口调用一次，把**写后**逐文件
   `{sha256, bytes, existed}` 落到同批次的 `post.json`（tmp + `os.replace`）。
   `restore_batch()` 自动读取它做校验；**没有 `post.json` 就拒绝撤销**（fail-closed），
   除非调用方显式 `allow_unverified=True`（用于人工处置，仍会如实回报 `verified: false`）。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from memoria.services.agent.plan import TXID_RE
from memoria.services.agent.session.store import session_file

#: 单文件上限（超出即预检失败，不落盘）
MAX_FILE_BYTES = 8 * 1024 * 1024
#: 单批上限（超出即预检失败，不落盘）
MAX_BATCH_BYTES = 32 * 1024 * 1024
#: 每个会话保留的批次数
KEEP_BATCHES_PER_SESSION = 5
#: 每个库保留的会话备份目录数
KEEP_SESSIONS_PER_KB = 10
#: 每个库备份总字节上限
MAX_KB_BYTES = 64 * 1024 * 1024

JOURNAL_NAME = "journal.json"
POST_NAME = "post.json"
FILES_DIR = "files"
JOURNAL_VERSION = 1


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backups_root(kb_path: str) -> str:
    """备份根目录（**随库走**，与 `.memoria/agent/**` 既有布局对齐；不是事实源）。"""
    return os.path.join(kb_path, ".memoria", "agent", "backups")


def _dir_bytes(path: str) -> int:
    total = 0
    for base, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(base, name))
            except OSError:
                continue
    return total


def _check_session_id(kb_path: str, session_id: str) -> str:
    """会话 id 校验：**复用会话存储的唯一 id 正则**（非法即被拒），不另写一份。"""
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("会话 id 为空")
    session_file(kb_path, sid)  # 非法 id（含目录穿越）会抛 ValueError —— 这里只借它的校验
    return sid


def _check_txid(txid: str) -> str:
    value = (txid or "").strip()
    if not TXID_RE.match(value):
        raise ValueError(f"txid 形态非法：{txid!r}（应形如 20260920T021100Z-07）")
    return value


def session_dir(kb_path: str, session_id: str) -> str:
    """某会话的备份目录（`<backups_root>/<session_id>`）。"""
    return os.path.join(backups_root(kb_path), _check_session_id(kb_path, session_id))


def batch_dir(kb_path: str, session_id: str, txid: str) -> str:
    """某批次的备份目录（`<session_dir>/<txid>`）。"""
    return os.path.join(session_dir(kb_path, session_id), _check_txid(txid))


def _inside_kb(kb_path: str, rel_path: str) -> str | None:
    """把库内相对路径解析成绝对路径；越界（绝对路径 / `..` / 软链逃逸）返回 `None`。

    与 §2.4 同口径：两侧 `realpath` 后要求前缀命中 —— 这是备份**唯一**的路径闸门。
    **绝对路径一律拒**（而不是 `lstrip("/")` 后当相对路径用 —— 那会把 `/etc/x` 悄悄
    解释成 `<kb>/etc/x`，属"静默改语义"）。
    """
    raw = (rel_path or "").strip()
    if not raw or raw.startswith(("/", "\\")) or (len(raw) > 1 and raw[1] == ":"):
        return None
    rel = raw.replace("\\", "/")
    if rel.split("/")[0] == "..":
        return None
    root = os.path.realpath(kb_path)
    full = os.path.realpath(os.path.join(kb_path, rel))
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


def _batch_bytes(kb_path: str, session_id: str, txid: str) -> int:
    total = 0
    files_root = os.path.join(batch_dir(kb_path, session_id, txid), FILES_DIR)
    for base, _dirs, names in os.walk(files_root):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(base, name))
            except OSError:
                continue
    return total


def snapshot_pre_images(
    kb_path: str,
    session_id: str,
    txid: str,
    rel_paths: Iterable[str],
    *,
    plugin: str | None = None,
    tool_id: str | None = None,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_batch_bytes: int = MAX_BATCH_BYTES,
) -> dict:
    """把"该事务将碰的文件"**原字节**抄一份进 `<session>/<txid>/`，返回批次清单。

    **fail-closed**：越界路径、单文件超限、单批超限、IO 失败 —— 任一发生都**不留下任何
    批次**（整目录原子落位 + 失败即清临时目录），调用方必须因此**放弃本次 apply**。
    返回 `{status, txid, dir, files:[{rel_path, existed, sha256, bytes}], bytes}`；
    失败返回 `{status:"error", code, message}`（`path_rejected` / `file_too_large` /
    `batch_too_large` / `backup_failed`）。
    """
    try:
        sid = _check_session_id(kb_path, session_id)
        clean_txid = _check_txid(txid)
    except ValueError as e:
        return {"status": "error", "code": "backup_failed", "message": str(e)}

    rels: list[str] = []
    for raw in rel_paths:
        # 不做任何"宽容"归一化：原样交给 `_inside_kb()` 判（它会把绝对路径 / `..` / 越界一律拒）
        text = str(raw or "")
        if text.strip() and text not in rels:
            rels.append(text)
    if not rels:
        return {"status": "error", "code": "backup_failed", "message": "受影响文件集为空"}

    entries: list[dict] = []
    total = 0
    for rel_in in rels:
        full = _inside_kb(kb_path, rel_in)
        if full is None:
            return {"status": "error", "code": "path_rejected", "message": f"路径越界：{rel_in}"}
        rel = os.path.relpath(full, os.path.realpath(kb_path)).replace("\\", "/")
        if not os.path.isfile(full):
            entries.append({"rel_path": rel, "existed": False, "sha256": None, "bytes": 0})
            continue
        size = os.path.getsize(full)
        if size > max_file_bytes:
            return {
                "status": "error",
                "code": "file_too_large",
                "message": f"单文件超过上限（{size} > {max_file_bytes} 字节）：{rel}",
            }
        total += size
        if total > max_batch_bytes:
            return {
                "status": "error",
                "code": "batch_too_large",
                "message": f"本批备份超过上限（> {max_batch_bytes} 字节）",
            }
        entries.append(
            {"rel_path": rel, "existed": True, "sha256": _sha256_file(full), "bytes": size, "source": full}
        )

    final_dir = batch_dir(kb_path, sid, clean_txid)
    if os.path.exists(final_dir):
        return {"status": "error", "code": "backup_failed", "message": f"批次已存在：{clean_txid}"}
    os.makedirs(os.path.dirname(final_dir), exist_ok=True)
    tmp_dir = f"{final_dir}.tmp-{os.getpid()}"
    try:
        os.makedirs(tmp_dir, exist_ok=True)  # 整批全是新建文件时也必须建出目录（否则 journal 写不进）
        for entry in entries:
            if not entry["existed"]:
                continue
            dest = os.path.join(tmp_dir, FILES_DIR, entry["rel_path"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # 原字节复制：不做任何编码/换行规范化（撤销要求逐字节回滚）
            shutil.copyfile(entry.pop("source"), dest)
        journal = {
            "v": JOURNAL_VERSION,
            "txid": clean_txid,
            "session_id": sid,
            "ts": int(time.time() * 1000),
            "plugin": plugin,
            "tool_id": tool_id,
            "files": [
                {k: e[k] for k in ("rel_path", "existed", "sha256", "bytes")}
                for e in entries
            ],
        }
        with open(os.path.join(tmp_dir, JOURNAL_NAME), "w", encoding="utf-8") as handle:
            json.dump(journal, handle, ensure_ascii=False, indent=1)
            handle.flush()
        os.replace(tmp_dir, final_dir)  # 整目录原子落位 ⇒ 不会留下半个批次
    except OSError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"status": "error", "code": "backup_failed", "message": str(e)}

    return {
        "status": "ok",
        "txid": clean_txid,
        "dir": final_dir,
        "files": [{k: e[k] for k in ("rel_path", "existed", "sha256", "bytes")} for e in entries],
        "bytes": total,
    }


def read_journal(kb_path: str, session_id: str, txid: str) -> dict | None:
    """读某批次的 `journal.json`（不存在或损坏回 `None`，不抛）。"""
    path = os.path.join(batch_dir(kb_path, session_id, txid), JOURNAL_NAME)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def record_post_images(kb_path: str, session_id: str, txid: str) -> dict:
    """apply 的**最后一步**（四原语之后）由 apply 入口调用：记"写后"逐文件哈希。

    撤销的外部改动保护（§2.3.2 第 5 条）靠它落盘：撤销时比对**当前**文件与本文件的哈希，
    不符即拒（说明 apply 之后有人动过）。写 `post.json` 走 tmp + `os.replace`。
    """
    journal = read_journal(kb_path, session_id, txid)
    if journal is None:
        return {"status": "error", "code": "unknown_batch", "message": f"批次不存在：{txid}"}
    out: dict[str, dict] = {}
    for entry in journal.get("files", []):
        if not isinstance(entry, Mapping):
            continue
        rel = str(entry.get("rel_path") or "")
        full = _inside_kb(kb_path, rel)
        if full is None or not os.path.isfile(full):
            out[rel] = {"existed": False, "sha256": None, "bytes": 0}
            continue
        out[rel] = {"existed": True, "sha256": _sha256_file(full), "bytes": os.path.getsize(full)}
    target = os.path.join(batch_dir(kb_path, session_id, txid), POST_NAME)
    tmp = f"{target}.tmp-{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"v": JOURNAL_VERSION, "txid": txid, "files": out}, handle, ensure_ascii=False, indent=1)
        os.replace(tmp, target)
    except OSError as e:
        return {"status": "error", "code": "backup_failed", "message": str(e)}
    return {"status": "ok", "txid": txid, "files": out}


def read_post_images(kb_path: str, session_id: str, txid: str) -> dict | None:
    path = os.path.join(batch_dir(kb_path, session_id, txid), POST_NAME)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    files = data.get("files") if isinstance(data, dict) else None
    return files if isinstance(files, Mapping) else None


def list_batches(kb_path: str, session_id: str) -> list[dict]:
    """列某会话的批次（**按目录名字典序 = FIFO 顺序**，即 txid 单调递增序）。"""
    try:
        root = session_dir(kb_path, session_id)
    except ValueError:
        return []
    if not os.path.isdir(root):
        return []
    rows: list[dict] = []
    for name in sorted(os.listdir(root)):
        if name.endswith(".tmp") or ".tmp-" in name:
            continue
        journal = read_journal(kb_path, session_id, name)
        if journal is None:
            continue
        rows.append(
            {
                "txid": name,
                "ts": journal.get("ts"),
                "files": len(journal.get("files", []) or []),
                "bytes": _batch_bytes(kb_path, session_id, name),
                "dir": os.path.join(root, name),
            }
        )
    return rows


def _session_dirs(kb_path: str) -> list[tuple[str, float]]:
    root = backups_root(kb_path)
    if not os.path.isdir(root):
        return []
    out: list[tuple[str, float]] = []
    for name in os.listdir(root):
        full = os.path.join(root, name)
        if os.path.isdir(full):
            out.append((full, os.path.getmtime(full)))
    return out


def trim_backups(kb_path: str, session_id: str, *, keep: int = KEEP_BATCHES_PER_SESSION) -> dict:
    """按 §2.3.2 第 3 条的三个数字口径机会式清理，返回 `{evicted, bytes_freed}`。

    三条规则依次执行：① 当前会话只留最新 `keep` 批（**`keep` 至少为 1** ⇒ **永不淘汰
    当前会话的最新批次**，这是撤销可用性的底线）；② 每库最多 10 个会话备份目录（按
    目录 mtime，最旧先删）；③ 每库总字节 ≤ 64 MiB（FIFO 淘汰最旧批次，**仍不碰当前
    会话最新批次**）。**只列备份目录、不扫库**（不进读/查询热路径）。
    """
    evicted: list[str] = []
    freed = 0
    keep_n = max(1, int(keep))
    rows = list_batches(kb_path, session_id)
    newest = rows[-1]["txid"] if rows else None
    for row in rows[:-keep_n] if len(rows) > keep_n else []:
        if row["txid"] == newest:
            continue
        freed += row["bytes"]
        shutil.rmtree(row["dir"], ignore_errors=True)
        evicted.append(f"{os.path.basename(os.path.dirname(row['dir']))}/{row['txid']}")

    known = {s.replace("\\", "/") for s in (session_id,)}
    dirs = _session_dirs(kb_path)
    if len(dirs) > KEEP_SESSIONS_PER_KB:
        for full, _mtime in sorted(dirs, key=lambda item: item[1])[: len(dirs) - KEEP_SESSIONS_PER_KB]:
            if os.path.basename(full) in known:
                continue  # 不淘汰当前会话（它可能正被撤销）
            size = _dir_bytes(full)
            freed += size
            shutil.rmtree(full, ignore_errors=True)
            evicted.append(os.path.basename(full))

    total = sum(_dir_bytes(full) for full, _mtime in _session_dirs(kb_path))
    if total > MAX_KB_BYTES:
        candidates: list[tuple[str, str, int, str]] = []  # (txid, dir, bytes, session)
        for full, _mtime in _session_dirs(kb_path):
            sid = os.path.basename(full)
            for row in list_batches(kb_path, sid):
                candidates.append((row["txid"], row["dir"], row["bytes"], sid))
        candidates.sort(key=lambda item: item[0])  # FIFO：txid 升序
        for txid, full, size, sid in candidates:
            if total <= MAX_KB_BYTES:
                break
            if sid == session_id and txid == newest:
                continue
            shutil.rmtree(full, ignore_errors=True)
            evicted.append(f"{sid}/{txid}")
            freed += size
            total -= size

    return {"status": "ok", "evicted": evicted, "bytes_freed": freed, "kept": len(list_batches(kb_path, session_id))}


def restore_batch(
    kb_path: str,
    session_id: str,
    txid: str | None = None,
    *,
    rel_paths: Sequence[str] | None = None,
    allow_unverified: bool = False,
    audit: bool = True,
) -> dict:
    """撤销一个批次（**把 pre-image 逐字节写回**）；`txid` 缺省 = 该会话最新批次。

    **外部改动保护（fail-closed）**：对每个要回滚的文件，把**当前**盘上 sha256 与
    `post.json` 里 apply 时记录的写后 sha256 比对；任一不符即**拒绝整批**（不静默覆盖
    用户手改）。没有 `post.json`（例如批次来自更早版本 / 未经 apply 入口）时**默认拒**，
    只有显式 `allow_unverified=True` 才继续，并在返回值里标 `verified: false`。

    本函数是 M3 写路径上**唯一**会覆盖事实源的入口；`approval=confirm` 与
    `capability/undo` 审计由上层（apply 网关）负责 —— 本层只保证数据面正确与拒绝语义。
    """
    try:
        sid = _check_session_id(kb_path, session_id)
    except ValueError as e:
        return {"status": "error", "code": "unknown_batch", "message": str(e)}
    rows = list_batches(kb_path, sid)
    if not rows:
        return {"status": "error", "code": "unknown_batch", "message": "该会话没有备份批次"}
    target_txid = _check_txid(txid) if txid else rows[-1]["txid"]
    if target_txid not in {row["txid"] for row in rows}:
        return {"status": "error", "code": "unknown_batch", "message": f"批次不存在：{target_txid}"}
    journal = read_journal(kb_path, sid, target_txid)
    if journal is None:
        return {"status": "error", "code": "unknown_batch", "message": f"批次清单不可读：{target_txid}"}

    posts = read_post_images(kb_path, sid, target_txid)
    if posts is None and not allow_unverified:
        return {
            "status": "error",
            "code": "unverified",
            "message": "缺少写后哈希（post.json）⇒ 无法确认文件未被外部改动；默认拒绝撤销（可用 allow_unverified 人工处置）",
        }

    wanted = {str(x).replace("\\", "/") for x in rel_paths} if rel_paths else None
    plan_rows: list[tuple[dict, str, str | None, dict | None]] = []
    for entry in journal.get("files", []):
        if not isinstance(entry, Mapping):
            continue
        rel = str(entry.get("rel_path") or "")
        if wanted is not None and rel not in wanted:
            continue
        full = _inside_kb(kb_path, rel)
        if full is None:
            return {"status": "error", "code": "path_rejected", "message": f"路径越界：{rel}"}
        plan_rows.append((dict(entry), rel, full, (posts or {}).get(rel)))

    for _entry, rel, full, post in plan_rows:
        expected = (post or {}).get("sha256")
        current = _sha256_file(full) if os.path.isfile(full) else None
        if allow_unverified and posts is None:
            continue
        if current != expected:
            return {
                "status": "error",
                "code": "external_change",
                "message": f"文件在 apply 之后被改动，拒绝撤销：{rel}",
                "rel_path": rel,
                "expected_sha256": expected,
                "current_sha256": current,
            }

    written: list[dict] = []
    try:
        for entry, rel, full, _post in plan_rows:
            if not entry.get("existed"):
                # 新建文件 ⇒ 撤销 = 删除（不出现 0 字节副本与"空文件"的歧义）
                if full and os.path.isfile(full):
                    os.remove(full)
                written.append({"rel_path": rel, "action": "removed"})
                continue
            source = os.path.join(batch_dir(kb_path, sid, target_txid), FILES_DIR, rel)
            if not os.path.isfile(source):
                return {"status": "error", "code": "backup_corrupt", "message": f"备份副本缺失：{rel}"}
            os.makedirs(os.path.dirname(full or ""), exist_ok=True)
            tmp = f"{full}.restore-{os.getpid()}"
            shutil.copyfile(source, tmp)
            os.replace(tmp, full)  # 覆盖走 replace：不重新编码、不规范化换行
            written.append({"rel_path": rel, "action": "restored", "sha256": entry.get("sha256")})
    except OSError as e:
        return {"status": "error", "code": "restore_failed", "message": str(e), "written": written}

    result = {
        "status": "ok",
        "txid": target_txid,
        "verified": posts is not None,
        "files": written,
    }
    if audit:
        # 审计（§2.3.2 第 5 条）：撤销**同样要留痕**；写已完成 ⇒ 审计失败不回滚，只如实带回
        from memoria.services.agent import audit as audit_mod

        result["audit"] = audit_mod.append(kb_path, sid, audit_mod.EVENT_UNDO, result)
    return result
