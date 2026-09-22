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
   `journal.json`，再用 `replace_with_retry()` 整目录改名到 `<txid>` ⇒ 任何一步失败都只需删临时
   目录，**不会留下半个批次**（比"先建目录再逐文件写"更强）。**2026-09-21**：改名改走
   `storage/atomic_write.replace_with_retry`（对 `WinError 5/32` 有界退避重试）—— 真机
   `AAA_Vocab` 会话里 `propose_write` 就是死在这一次 `os.replace` 上（`[WinError 5] 拒绝访问：
   …-01.tmp-42604 → …-01`），整批写入被拒，人看到的却是"agent 什么都没做"。本模块**所有**
   写路径的 `os.replace`（目录 / journal / post / after / stack）统一换成该带重试的版本。
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
from memoria.storage.atomic_write import replace_with_retry

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
    # 统计**整批**（`files/` + 写后镜像 `after/` 或 `after.zip` + 清单）⇒ 份额判据不再漏算重做所需的那份
    for base, _dirs, names in os.walk(os.path.dirname(files_root)):
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
        replace_with_retry(tmp_dir, final_dir)  # 整目录原子落位 ⇒ 不会留下半个批次
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
        replace_with_retry(tmp, target)
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


#: 会话**起点快照**目录名（`<session>/origin/`）：把"这次对话开始前"的版本固化一份。
#: 它**不参与批次 FIFO 淘汰** —— 否则"回到对话开始前"会随批次淘汰而失效（人 2026-09-21：
#: 撤销要像 git 一样有个**稳定的 base** 可回退，而不是"最多回退到保留窗口"。）
ORIGIN_DIR = "origin"
ORIGIN_TXID = "origin"


def origin_dir(kb_path: str, session_id: str) -> str:
    """会话起点快照目录（`<session>/origin/`）—— **不是批次**，不参与 FIFO 淘汰。"""
    return os.path.join(session_dir(kb_path, session_id), ORIGIN_DIR)


def read_origin(kb_path: str, session_id: str) -> dict | None:
    """读会话起点快照；没有就回 `None`（旧版本写的对话没有它）。形状 `{rel: {existed, sha256, bytes}}`。"""
    path = os.path.join(origin_dir(kb_path, session_id), JOURNAL_NAME)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, Mapping):
        return None
    return {str(rel): dict(row) for rel, row in files.items() if isinstance(row, Mapping)}


def ensure_origin(kb_path: str, session_id: str, txid: str, rels: Iterable[str]) -> dict:
    """确保"对话开始前那一版"已固化进**起点快照**（撤销的稳定 base）。

    时机：`apply_plan()` 在 `snapshot_pre_images()` **之后、任何写盘之前**调用。
    规则：对每个 `rel`，若起点里**还没有**它 ⇒ 用**本批的 pre-image** 作为它的起点版本
    （第一次碰它时，盘上正是"对话开始前"的样子）；`existed:false`（本批之前不存在 ⇒ 对话中
    新建的）也照记一条 ⇒ 撤销 = 删除。已在起点里的一律**不动**（先到者 = 更早那一版）。

    **fail-closed**：写不进去就回错误，调用方必须放弃本次 apply —— 否则会出现"能写、却撤不回"。
    顺序：**先复制文件、后原子更新 journal**（中途失败最多留下多余副本，下次重跑覆盖即可）。
    """
    try:
        sid = _check_session_id(kb_path, session_id)
        clean_txid = _check_txid(txid)
    except ValueError as e:
        return {"status": "error", "code": "backup_failed", "message": str(e)}

    batch = batch_dir(kb_path, sid, clean_txid)
    journal = read_journal(kb_path, sid, clean_txid)
    if journal is None:
        return {"status": "error", "code": "backup_failed", "message": f"批次不可读：{clean_txid}"}
    known: dict[str, dict] = read_origin(kb_path, sid) or {}
    entries = {str(row.get("rel_path") or ""): row for row in journal.get("files", []) if isinstance(row, Mapping)}

    added: list[str] = []
    root = origin_dir(kb_path, sid)
    try:
        for raw in rels:
            rel = str(raw or "")
            if not rel or rel in known:
                continue
            entry = entries.get(rel)
            if entry is None:
                continue  # 本批没碰它 ⇒ 起点里也不需要（它不在本次事务面上）
            if entry.get("existed"):
                source = os.path.join(batch, FILES_DIR, rel)
                if not os.path.isfile(source):
                    return {"status": "error", "code": "backup_corrupt", "message": f"批内副本缺失：{rel}"}
                dest = os.path.join(root, FILES_DIR, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(source, dest)
            known[rel] = {
                "existed": bool(entry.get("existed")),
                "sha256": entry.get("sha256"),
                "bytes": entry.get("bytes") or 0,
            }
            added.append(rel)
        if added:
            os.makedirs(root, exist_ok=True)
            target = os.path.join(root, JOURNAL_NAME)
            tmp = f"{target}.tmp-{os.getpid()}"
            payload = {"v": JOURNAL_VERSION, "session_id": sid, "txid": ORIGIN_TXID, "files": known}
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=1)
                handle.flush()
            replace_with_retry(tmp, target)
    except OSError as e:
        return {"status": "error", "code": "backup_failed", "message": f"起点快照写入失败：{e}"}
    return {"status": "ok", "session_id": sid, "added": added, "files": len(known)}


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
        if name == ORIGIN_DIR or not _is_txid_name(name):
            continue  # 会话"起点快照"不是批次（它不参与 FIFO 淘汰，见 `ensure_origin()`）
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


#: 强制撤销前的"当前状态"兜底批次落在哪个会话。**与 `storage/file_version.FORCE_SESSION` 同值**
#: （那边是"以我为准"强制保存用的）；此处独立定义是为了避开 import 环（`file_version` 反过来要用
#: 本模块做覆盖前备份），一致性由测试钉住。
FORCE_SESSION = "manual-force"


def _next_free_txid(kb_path: str, session_id: str) -> str:
    """给"临时兜底批次"取一个还没被占用的 txid（同秒内连拍两份也不会撞目录）。"""
    base = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for n in range(1, 100):
        candidate = f"{base}-{n:02d}"
        if not os.path.exists(batch_dir(kb_path, session_id, candidate)):
            return candidate
    return f"{base}-99"


def _snapshot_current(kb_path: str, rels: Sequence[str]) -> dict:
    """强制撤销前先把**当前**盘上这几份文件另存一个批次 ⇒ **覆盖 ≠ 丢数据**（那份改动仍可再撤销）。

    记在 `manual-force` 会话下（与"以我为准"的覆盖备份同一处，便于人工统一处置）。

    **`post.json` 不在这里记**：这份批次的语义是"如果你对还原结果不满意，可以把当前这版拿回来"，
    所以它的"写后哈希"必须等于**还原之后**的盘面 —— 由 `restore_batch()` 在写完盘后补记
    （否则回头再撤它时，会因"当前 ≠ post"被自己的外部改动保护挡住）。
    """
    txid = _next_free_txid(kb_path, FORCE_SESSION)
    snapshot = snapshot_pre_images(kb_path, FORCE_SESSION, txid, rels, tool_id="force-undo")
    if snapshot.get("status") != "ok":
        return snapshot
    return {
        "status": "ok",
        "session_id": FORCE_SESSION,
        "txid": txid,
        "files": [row["rel_path"] for row in snapshot["files"]],
    }


def restore_batch(
    kb_path: str,
    session_id: str,
    txid: str | None = None,
    *,
    rel_paths: Sequence[str] | None = None,
    allow_unverified: bool = False,
    audit: bool = True,
    force: bool = False,
) -> dict:
    """撤销一个批次（**把 pre-image 逐字节写回**）；`txid` 缺省 = 该会话最新批次。

    **外部改动保护（fail-closed）**：对每个要回滚的文件，把**当前**盘上 sha256 与
    `post.json` 里 apply 时记录的写后 sha256 比对；任一不符即**拒绝整批**（不静默覆盖
    用户手改）。没有 `post.json`（例如批次来自更早版本 / 未经 apply 入口）时**默认拒**，
    只有显式 `allow_unverified=True` 才继续，并在返回值里标 `verified: false`。

    `force=True`（人 2026-09-21 追加，UI 上是「强制撤销」）：保护判定失败时**不直接放弃**，
    而是先把**当前**那几份文件另存一个 `manual-force` 批次（见 `_snapshot_current()`）**再**还原
    ⇒ "我要撤，但盘上又被别的写者改过（例如产品「构建」同步了 sidecar）"这条路上的数据不丢。
    返回值带 `forced`（被覆盖掉外部改动的那几个文件）与 `force_backup`（兜底批次坐标）。

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

    stale: list[tuple[str, str | None, str | None]] = []
    for _entry, rel, full, post in plan_rows:
        expected = (post or {}).get("sha256")
        current = _sha256_file(full) if os.path.isfile(full) else None
        if allow_unverified and posts is None:
            continue
        if current != expected:
            stale.append((rel, expected, current))

    force_backup: dict | None = None
    if stale:
        if not force:
            rel, expected, current = stale[0]
            return {
                "status": "error",
                "code": "external_change",
                "message": (
                    f"这批写完之后 {rel} 又被改过（常见来源：产品「构建」/「检查」同步了 sidecar，"
                    "或人手改过），拒绝撤销以免覆盖那些改动。"
                    "要么先处理那份改动；要么用**强制撤销**（会先把**当前**这一版另存为一个备份批次，"
                    "再还原到写入前 —— 覆盖不等于丢数据）。"
                ),
                "rel_path": rel,
                "expected_sha256": expected,
                "current_sha256": current,
                "stale": [row[0] for row in stale],
            }
        # force：先把**当前**这一版存下来，再跳过保护还原
        force_backup = _snapshot_current(kb_path, [row[0] for row in stale])
        if force_backup.get("status") != "ok":
            return {
                "status": "error",
                "code": force_backup.get("code") or "backup_failed",
                "message": f"强制撤销前的兜底备份失败，已放弃（不覆盖任何东西）：{force_backup.get('message') or ''}",
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
            replace_with_retry(tmp, full)  # 覆盖走 replace：不重新编码、不规范化换行
            written.append({"rel_path": rel, "action": "restored", "sha256": entry.get("sha256")})
    except OSError as e:
        return {"status": "error", "code": "restore_failed", "message": str(e), "written": written}

    if force_backup:
        # 兜底批次的"写后哈希"在**还原之后**补记：它记录的语义是"撤销后的盘面"
        # ⇒ 用户若对结果不满意，回头撤这一批（拿回被覆盖的那一版）仍能过外部改动保护。
        record_post_images(kb_path, force_backup["session_id"], force_backup["txid"])

    result = {
        "status": "ok",
        "txid": target_txid,
        "verified": posts is not None,
        "files": written,
        # 强制撤销的痕迹（只增字段）：普通撤销时 `forced` 为空表、`force_backup` 为 None
        "forced": [row[0] for row in stale],
        "force_backup": force_backup,
    }
    if audit:
        # 审计（§2.3.2 第 5 条）：撤销**同样要留痕**；写已完成 ⇒ 审计失败不回滚，只如实带回
        from memoria.services.agent import audit as audit_mod

        result["audit"] = audit_mod.append(kb_path, sid, audit_mod.EVENT_UNDO, result)
    return result


def restore_session(kb_path: str, session_id: str, *, audit: bool = True) -> dict:
    """回到**这次对话开始前**：按会话**起点快照**一次写回（人 2026-09-21 定稿：「一键生效，不再有被阻止」）。

    **为什么不再"逐批回放 / 看向批次"**（人：「你的设计根本和 git 的机制不同」）：那两种做法都要求
    "当时盘面 == 某批 `post.json`" ⇒ 中间任何一批之后被别的写者改过（产品「构建」同步 sidecar 就是
    这一类），整条链就卡住。git 的 `revert` 是**指向一个状态**，不是回放路径 ⇒ 这里同样：

    - **目标状态** = `<session>/origin/`（**起点快照**：第一次写入前拍下、且**不参与 FIFO 淘汰**）；
    - **覆盖前自动兜底**：把将被覆盖 / 删除的当前版本另存为 `manual-force` 批次 ⇒ 覆盖 ≠ 丢数据；
    - ⇒ **不再有 `external_change` 这种"被阻止"**：人点撤销本身就是明示决定（§9 规则 ③），
      而"不静默"由"自动兜底 + 审计留痕"承担。

    返回 `{status, session_id, files, safety_backup, undone}`；没有起点快照（旧版本写的对话）时回
    `no_origin` 并如实说明。
    """
    try:
        sid = _check_session_id(kb_path, session_id)
    except ValueError as e:
        return {"status": "error", "code": "unknown_batch", "message": str(e)}
    rows = list_batches(kb_path, sid)
    if not rows:
        return {"status": "error", "code": "unknown_batch", "message": "该会话没有备份批次"}

    origin = read_origin(kb_path, sid)
    if not origin:
        return {
            "status": "error",
            "code": "no_origin",
            "message": (
                "这次对话没有**起点快照**（它由新版本在第一次写入前拍下）⇒ 无法一键回到对话开始前。"
                "这次对话是旧版本写的；可改用逐批回退（`restore_batch`）。"
            ),
            "session_id": sid,
        }

    fulls: dict[str, str] = {}
    for rel in origin:
        full = _inside_kb(kb_path, rel)
        if full is None:
            return {"status": "error", "code": "path_rejected", "message": f"路径越界：{rel}"}
        fulls[rel] = full

    # **自动兜底**（人：「一键生效，不再有被阻止」）：把将被覆盖 / 删除的**当前版本**先另存一份
    # ⇒ 覆盖 ≠ 丢数据。因此这里**不再**做"外部改动检测"与拒绝 —— 人点撤销 = 明示决定（§9 规则 ③），
    # "不静默"改由"兜底备份 + 审计留痕"承担。
    present = [rel for rel, full in fulls.items() if full and os.path.isfile(full)]
    safety_backup: dict | None = None
    if present:
        safety_backup = _snapshot_current(kb_path, present)
        if safety_backup.get("status") != "ok":
            return {
                "status": "error",
                "code": safety_backup.get("code") or "backup_failed",
                "message": f"撤销前的兜底备份失败，已放弃（不覆盖任何东西）：{safety_backup.get('message') or ''}",
                "session_id": sid,
            }

    written: list[dict] = []
    root = origin_dir(kb_path, sid)
    try:
        for rel, info in origin.items():
            full = fulls[rel]
            if not info.get("existed"):
                # 对话期间**新建**的文件 ⇒ 撤销 = 删除（与 `restore_batch` 同口径，不留 0 字节副本）
                if full and os.path.isfile(full):
                    os.remove(full)
                written.append({"rel_path": rel, "action": "removed"})
                continue
            source = os.path.join(root, FILES_DIR, rel)
            if not os.path.isfile(source):
                return {
                    "status": "error",
                    "code": "backup_corrupt",
                    "message": f"起点快照的文件副本缺失：{rel}",
                    "written": written,
                }
            os.makedirs(os.path.dirname(full), exist_ok=True)
            tmp = f"{full}.restore-{os.getpid()}"
            shutil.copyfile(source, tmp)
            replace_with_retry(tmp, full)  # 覆盖走 replace：不重新编码、不规范化换行
            written.append({"rel_path": rel, "action": "restored", "sha256": info.get("sha256")})
    except OSError as e:
        return {"status": "error", "code": "restore_failed", "message": str(e), "written": written}

    if safety_backup:
        # 兜底批次的"写后哈希"在**还原之后**补记：它记录的语义是"撤销后的盘面"
        record_post_images(kb_path, safety_backup["session_id"], safety_backup["txid"])

    result = {
        "status": "ok",
        "session_id": sid,
        "txid": str(rows[-1].get("txid") or ""),  # 最新一批（前端沿用该字段做展示）
        "undone": [str(row.get("txid") or "") for row in reversed(rows)],  # 覆盖到的批次（降序，供 UI 计数）
        "verified": True,
        "files": written,
        "safety_backup": safety_backup,  # 被覆盖掉的那一版存在哪（覆盖 ≠ 丢数据）
        "origin": {rel: ORIGIN_TXID for rel in origin},  # 目标状态来自起点快照
    }
    if audit:
        from memoria.services.agent import audit as audit_mod

        result["audit"] = audit_mod.append(kb_path, sid, audit_mod.EVENT_UNDO, result)
    return result


# ── 栈式撤销 / 重做（人 2026-09-21 定稿：「采用 stack 设计，这样可以 undo/redo」「近邻不压缩，深的压缩」）──
#
# `restore_session()` 是"一键回到对话开始前"（相当于 git 里退到 base）。人还要**逐步**回退与**前进**：
# 每次写入 = 栈里的一步 ⇒ 撤销一步 = 用该批的 **pre-image** 写回；重做一步 = 用该批的 **写后镜像**。
# 后者以前没有 ⇒ 本轮补上。
#
# 存储分层（人：「近邻不压缩，深的压缩」）：
#   · 最近 `AFTER_PLAIN_KEEP` 步 ⇒ **原始文件**（`<txid>/after/<rel>`）：redo 零解压，也便于人工直接比对；
#   · 更深的步 ⇒ `compact_after_images()` 压成 `<txid>/after.zip`（ZIP_DEFLATED），原始目录删除。
# 两种形态共用一份元数据 `<txid>/after.json`（`existed:false` 也要记 ⇒ 重做 = 删除，与撤销同口径）。
#
# 栈落盘 `<session>/stack.json`：`{txids: [...], cursor: int}`，`cursor = -1` 表示"全部已撤销"。
# 新写入**从当前指针处截断**再压入（人：「如果产生新对话，就在当前栈指针上新加…限制 redo 范围」）。

AFTER_DIR = "after"
AFTER_ZIP = "after.zip"
AFTER_META = "after.json"
STACK_NAME = "stack.json"
STACK_VERSION = 1
#: 靠近栈顶的**几步**保留未压缩的写后镜像（redo 快、能直接看）。
AFTER_PLAIN_KEEP = 2


def after_paths(kb_path: str, session_id: str, txid: str) -> tuple[str, str, str]:
    """写后镜像的三个路径：`(原始目录, zip 文件, 元数据)`。"""
    base = batch_dir(kb_path, session_id, txid)
    return os.path.join(base, AFTER_DIR), os.path.join(base, AFTER_ZIP), os.path.join(base, AFTER_META)


def read_after_images(kb_path: str, session_id: str, txid: str) -> dict | None:
    """读某批的写后元数据 `{rel: {existed, sha256, bytes}}`（不存在 / 损坏 ⇒ `None`，不抛）。"""
    _dir, _zip, meta = after_paths(kb_path, session_id, txid)
    try:
        with open(meta, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    files = data.get("files") if isinstance(data, dict) else None
    return files if isinstance(files, Mapping) else None


def _after_source(kb_path: str, session_id: str, txid: str) -> tuple[str, str] | None:
    """写后镜像的载体：`("dir", <after/…>)` 或 `("zip", <after.zip>)`；两者都没有 ⇒ `None`。"""
    plain, packed, _meta = after_paths(kb_path, session_id, txid)
    if os.path.isdir(plain):
        return ("dir", plain)
    if os.path.isfile(packed):
        return ("zip", packed)
    return None


def snapshot_after_images(
    kb_path: str,
    session_id: str,
    txid: str,
    *,
    rel_paths: Iterable[str] | None = None,
) -> dict:
    """给某批存一份**写后镜像**（"写完之后的样子"）—— 栈里「重做一步」的依据。

    **fail-open**：它在写**之后**才跑（此时写已成功、无法回滚），失败只如实回错误并由调用方记进
    `warnings` —— 后果是"这一步不可重做"，而**撤销仍然可用**（撤销靠 pre-image）。
    近邻保持原始文件、更深的由 `compact_after_images()` 压缩（见本块顶部说明）。
    """
    try:
        sid = _check_session_id(kb_path, session_id)
        clean_txid = _check_txid(txid)
    except ValueError as e:
        return {"status": "error", "code": "backup_failed", "message": str(e)}
    journal = read_journal(kb_path, sid, clean_txid)
    if journal is None:
        return {"status": "error", "code": "unknown_batch", "message": f"批次不存在：{clean_txid}"}
    wanted = {str(x).replace("\\", "/") for x in rel_paths} if rel_paths else None

    plain, _packed, meta_path = after_paths(kb_path, sid, clean_txid)
    entries: dict[str, dict] = {}
    total = 0
    try:
        for row in journal.get("files", []):
            if not isinstance(row, Mapping):
                continue
            rel = str(row.get("rel_path") or "")
            if not rel or (wanted is not None and rel not in wanted):
                continue
            full = _inside_kb(kb_path, rel)
            if full is None:
                return {"status": "error", "code": "path_rejected", "message": f"路径越界：{rel}"}
            if not os.path.isfile(full):
                # 写完之后它不在盘上（例如这批删掉了它）⇒ 只记"不存在"，重做时同样删除
                entries[rel] = {"existed": False, "sha256": None, "bytes": 0}
                continue
            size = os.path.getsize(full)
            dest = os.path.join(plain, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(full, dest)  # 原字节（与 pre-image 同口径：不做编码 / 换行规范化）
            entries[rel] = {"existed": True, "sha256": _sha256_file(full), "bytes": size}
            total += size
        # 先落文件、后落元数据（中途失败最多留下多余副本，下次重跑覆盖即可）
        tmp = f"{meta_path}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(
                {"v": STACK_VERSION, "txid": clean_txid, "session_id": sid, "plain": True, "files": entries},
                handle,
                ensure_ascii=False,
                indent=1,
            )
            handle.flush()
        replace_with_retry(tmp, meta_path)
    except OSError as e:
        return {"status": "error", "code": "backup_failed", "message": f"写后镜像失败：{e}"}
    return {"status": "ok", "txid": clean_txid, "files": entries, "bytes": total, "plain": True}


def compact_after_images(
    kb_path: str,
    session_id: str,
    *,
    keep_plain: int = AFTER_PLAIN_KEEP,
) -> dict:
    """把**更深**（离栈顶超过 `keep_plain` 步）的写后镜像压成 zip，近邻保持不变。

    顺序按 `list_batches()`（txid 升序 = FIFO）⇒ 最后 `keep_plain` 个批次原样保留。
    幂等：已经是 zip 形态的批次会被跳过。压完删掉原始目录（元数据 `after.json` 保留，
    并补记 `plain: false`）⇒ 读端按 `_after_source()` 自适应。
    """
    import zipfile  # 局部导入：文件顶部插入 import 会让下方所有行号 +N（锚点漂移）

    try:
        sid = _check_session_id(kb_path, session_id)
    except ValueError as e:
        return {"status": "error", "code": "unknown_batch", "message": str(e)}
    rows = list_batches(kb_path, sid)
    keep_n = max(0, int(keep_plain))
    compacted: list[str] = []
    freed = 0
    for row in rows[: len(rows) - keep_n] if len(rows) > keep_n else []:
        txid = str(row.get("txid") or "")
        plain, packed, meta_path = after_paths(kb_path, sid, txid)
        if not os.path.isdir(plain):
            continue  # 没有原始目录（已压缩 / 本来就没存）⇒ 跳过
        try:
            before = _dir_bytes(plain)
            tmp = f"{packed}.tmp-{os.getpid()}"
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                for base, _dirs, names in os.walk(plain):
                    for name in names:
                        full = os.path.join(base, name)
                        zf.write(full, arcname=os.path.relpath(full, plain).replace("\\", "/"))
            replace_with_retry(tmp, packed)
            # 元数据补记 `plain: false`（写端不读它，只为人排查用）
            try:
                with open(meta_path, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
                if isinstance(meta, dict):
                    meta["plain"] = False
                    tmp_meta = f"{meta_path}.tmp-{os.getpid()}"
                    with open(tmp_meta, "w", encoding="utf-8") as handle:
                        json.dump(meta, handle, ensure_ascii=False, indent=1)
                    replace_with_retry(tmp_meta, meta_path)
            except (OSError, ValueError):
                pass
            shutil.rmtree(plain, ignore_errors=True)
            after = os.path.getsize(packed) if os.path.isfile(packed) else 0
            freed += max(0, before - after)
            compacted.append(txid)
        except (OSError, zipfile.BadZipFile):
            continue  # 单个批次压缩失败不影响其它批次（下一步仍可用）
    return {"status": "ok", "compacted": compacted, "bytes_freed": freed, "keep_plain": keep_n}


def stack_path(kb_path: str, session_id: str) -> str:
    """会话栈文件 `<session>/stack.json`。"""
    return os.path.join(session_dir(kb_path, session_id), STACK_NAME)


def read_stack(kb_path: str, session_id: str) -> dict:
    """读会话栈 `{txids, cursor}`；**没有 stack.json（旧版本写的对话）⇒ 按批次表合成**
    （全部视为"已应用"、指针在最新一批）—— 保证老对话也能用逐步撤销。"""
    try:
        sid = _check_session_id(kb_path, session_id)
    except ValueError:
        return {"txids": [], "cursor": -1}
    path = stack_path(kb_path, sid)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict) and isinstance(data.get("txids"), list):
        known = {str(row.get("txid") or "") for row in list_batches(kb_path, sid)}
        txids = [str(item) for item in data["txids"] if str(item) in known]
        cursor = int(data.get("cursor", len(txids) - 1)) if txids else -1
        return {"txids": txids, "cursor": max(-1, min(cursor, len(txids) - 1))}
    rows = list_batches(kb_path, sid)
    txids = [str(row.get("txid") or "") for row in rows]
    return {"txids": txids, "cursor": len(txids) - 1}


def write_stack(kb_path: str, session_id: str, txids: Sequence[str], cursor: int) -> dict:
    """原子写会话栈（tmp + `os.replace`）。"""
    path = stack_path(kb_path, session_id)
    payload = {
        "v": STACK_VERSION,
        "session_id": session_id,
        "txids": [str(item) for item in txids],
        "cursor": int(cursor),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
            handle.flush()
        replace_with_retry(tmp, path)
    except OSError as e:
        return {"status": "error", "code": "backup_failed", "message": str(e)}
    return {"status": "ok", "cursor": int(cursor), "total": len(payload["txids"])}


def push_stack(kb_path: str, session_id: str, txid: str) -> dict:
    """新写入压栈：**从当前指针处截断**（丢掉旧的 redo 分支）再压入 ⇒ 指针 = 最新一步。

    这正是人说的"旧的栈顶可以不实际删" —— 批次目录与备份**都保留**，只是不再可达
    （`read_stack` 只认 `txids` 列表里的条目）⇒ 限制 redo 范围而不毁数据。
    """
    try:
        sid = _check_session_id(kb_path, session_id)
        clean = _check_txid(txid)
    except ValueError as e:
        return {"status": "error", "code": "backup_failed", "message": str(e)}
    stack = read_stack(kb_path, sid)
    kept = list(stack["txids"][: stack["cursor"] + 1])
    dropped = [item for item in stack["txids"][stack["cursor"] + 1 :] if item not in kept]
    if clean in kept:  # 防御：同一 txid 重复压入
        kept = kept[: kept.index(clean)]
    kept.append(clean)
    written = write_stack(kb_path, sid, kept, len(kept) - 1)
    if written.get("status") != "ok":
        return written
    return {
        "status": "ok",
        "cursor": len(kept) - 1,
        "total": len(kept),
        "dropped": dropped,  # 被截断的"未来分支"（备份仍在盘上，只是不再可达）
    }


def stack_state(kb_path: str, session_id: str) -> dict:
    """给 UI 的栈现状：`{cursor, position, total, can_undo, can_redo, steps[]}`。"""
    try:
        sid = _check_session_id(kb_path, session_id)
    except ValueError as e:
        return {"status": "error", "code": "unknown_batch", "message": str(e)}
    stack = read_stack(kb_path, sid)
    rows = {str(row.get("txid") or ""): row for row in list_batches(kb_path, sid)}
    steps: list[dict] = []
    for index, txid in enumerate(stack["txids"]):
        row = rows.get(txid) or {}
        steps.append(
            {
                "txid": txid,
                "ts": row.get("ts"),
                "files": row.get("files") or 0,
                "applied": index <= stack["cursor"],
                "current": index == stack["cursor"],
                "has_after": _after_source(kb_path, sid, txid) is not None,
            }
        )
    return {
        "status": "ok",
        "session_id": sid,
        "cursor": stack["cursor"],
        "position": stack["cursor"] + 1,
        "total": len(stack["txids"]),
        "can_undo": stack["cursor"] >= 0,
        "can_redo": stack["cursor"] + 1 < len(stack["txids"]),
        "steps": steps,
    }


def _write_back(
    kb_path: str,
    entries: Mapping[str, Mapping],
    *,
    dir_root: str | None = None,
    zip_file: str | None = None,
) -> tuple[list[dict], dict | None]:
    """把 `entries`（`{rel: {existed, sha256}}`）描述的**目标状态**写回盘。

    `existed:false` ⇒ 删除（不留 0 字节副本）；否则从 `dir_root/<rel>` 或 `zip_file` 内的同名条目
    逐字节复制（`os.replace` 落位，不重新编码、不规范化换行）。返回 `(written, error_or_None)`。
    """
    import zipfile

    blobs: dict[str, bytes] = {}
    if zip_file is not None:
        try:
            with zipfile.ZipFile(zip_file) as zf:  # 总量受 MAX_BATCH_BYTES 约束 ⇒ 一次读入内存
                for rel, info in entries.items():
                    if info.get("existed"):
                        blobs[rel] = zf.read(rel)
        except (OSError, KeyError, zipfile.BadZipFile) as e:
            return [], {"status": "error", "code": "backup_corrupt", "message": f"写后镜像不可读：{e}"}

    written: list[dict] = []
    try:
        for rel, info in entries.items():
            full = _inside_kb(kb_path, rel)
            if full is None:
                return written, {"status": "error", "code": "path_rejected", "message": f"路径越界：{rel}"}
            if not info.get("existed"):
                if os.path.isfile(full):
                    os.remove(full)
                written.append({"rel_path": rel, "action": "removed"})
                continue
            dest_dir = os.path.dirname(full)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            tmp = f"{full}.restore-{os.getpid()}"
            if dir_root is not None:
                source = os.path.join(dir_root, rel)
                if not os.path.isfile(source):
                    return written, {"status": "error", "code": "backup_corrupt", "message": f"备份副本缺失：{rel}"}
                shutil.copyfile(source, tmp)
            else:
                with open(tmp, "wb") as handle:
                    handle.write(blobs.get(rel, b""))
            replace_with_retry(tmp, full)
            written.append({"rel_path": rel, "action": "restored", "sha256": info.get("sha256")})
    except OSError as e:
        return written, {"status": "error", "code": "restore_failed", "message": str(e), "written": written}
    return written, None


def _undo_redo_common(
    kb_path: str,
    resp,
    session_id: str,
    *,
    audit: bool,
    direction: str,
) -> dict:
    """撤销一步 / 重做一步的公共流程（差别只在"目标状态从哪来"）。

    `resp` 是调用方给的执行体：`resp() -> (written, error, target_txid, new_cursor, extra)`。
    覆盖前**一律先自动兜底**（把人当前那一版另存 `manual-force` 批次）⇒ 覆盖 ≠ 丢数据，
    因此这里与 `restore_session()` 同口径：**不做外部改动拒绝**（人点按钮 = 明示决定）。
    """
    written, error, txid, new_cursor, extra = resp()
    if error:
        return error
    if extra.get("safety_backup"):
        # 兜底批次的"写后哈希"在**还原之后**补记：它记录的语义是"这一步之后（被覆盖前）的盘面"
        record_post_images(kb_path, extra["safety_backup"]["session_id"], extra["safety_backup"]["txid"])
    stack = read_stack(kb_path, session_id)
    written_stack = write_stack(kb_path, session_id, stack["txids"], new_cursor)
    result = {
        "status": "ok",
        "session_id": session_id,
        "txid": txid,
        "direction": direction,
        "cursor": new_cursor,
        "total": len(stack["txids"]),
        "files": written,
        "safety_backup": extra.get("safety_backup"),
    }
    if written_stack.get("status") != "ok":
        result["stack_warning"] = written_stack.get("message")
    if audit:
        from memoria.services.agent import audit as audit_mod

        event = audit_mod.EVENT_REDO if direction == "redo" else audit_mod.EVENT_UNDO
        result["audit"] = audit_mod.append(kb_path, session_id, event, result)
    return result


def undo_step(kb_path: str, session_id: str, *, audit: bool = True) -> dict:
    """**撤销一步**：把当前指针那一批的 pre-image 写回，指针 −1（栈语义，人 2026-09-21 定稿）。"""
    try:
        sid = _check_session_id(kb_path, session_id)
    except ValueError as e:
        return {"status": "error", "code": "unknown_batch", "message": str(e)}
    stack = read_stack(kb_path, sid)
    txids, cursor = stack["txids"], stack["cursor"]
    if not txids or cursor < 0:
        return {"status": "error", "code": "stack_bottom", "message": "已经在最早一步：没有可撤销的步骤"}

    def run() -> tuple[list[dict], dict | None, str, int, dict]:
        txid = txids[cursor]
        journal = read_journal(kb_path, sid, txid)
        if journal is None:
            return [], {"status": "error", "code": "unknown_batch", "message": f"批次清单不可读：{txid}"}, txid, cursor, {}
        entries = {
            str(row.get("rel_path") or ""): row
            for row in journal.get("files", [])
            if isinstance(row, Mapping) and str(row.get("rel_path") or "")
        }
        present = [rel for rel in entries if os.path.isfile(_inside_kb(kb_path, rel) or "")]
        safety = _snapshot_current(kb_path, present) if present else None
        if safety is not None and safety.get("status") != "ok":
            return [], {
                "status": "error",
                "code": safety.get("code") or "backup_failed",
                "message": f"撤销前的兜底备份失败，已放弃（不覆盖任何东西）：{safety.get('message') or ''}",
            }, txid, cursor, {}
        written, error = _write_back(
            kb_path, entries, dir_root=os.path.join(batch_dir(kb_path, sid, txid), FILES_DIR)
        )
        return written, error, txid, cursor - 1, {"safety_backup": safety}

    return _undo_redo_common(kb_path, run, sid, audit=audit, direction="undo")


def redo_step(kb_path: str, session_id: str, *, audit: bool = True) -> dict:
    """**重做一步**：把指针 +1 那一批的**写后镜像**写回，指针 +1（栈语义）。

    该批没有写后镜像（旧批次 / 当时存失败）⇒ 如实回 `no_after`，不假装成功。
    """
    try:
        sid = _check_session_id(kb_path, session_id)
    except ValueError as e:
        return {"status": "error", "code": "unknown_batch", "message": str(e)}
    stack = read_stack(kb_path, sid)
    txids, cursor = stack["txids"], stack["cursor"]
    target = cursor + 1
    if not txids or target >= len(txids):
        return {"status": "error", "code": "stack_top", "message": "已经在最新一步：没有可重做的步骤"}
    if _after_source(kb_path, sid, txids[target]) is None:
        return {
            "status": "error",
            "code": "no_after",
            "message": f"这一步没有写后镜像（{txids[target]}）⇒ 无法重做；可用「撤销」回退。",
        }

    def run() -> tuple[list[dict], dict | None, str, int, dict]:
        txid = txids[target]
        entries = read_after_images(kb_path, sid, txid)
        if not entries:
            return [], {"status": "error", "code": "no_after", "message": f"写后镜像元数据不可读：{txid}"}, txid, cursor, {}
        source = _after_source(kb_path, sid, txid)
        assert source is not None
        present = [rel for rel in entries if os.path.isfile(_inside_kb(kb_path, rel) or "")]
        safety = _snapshot_current(kb_path, present) if present else None
        if safety is not None and safety.get("status") != "ok":
            return [], {
                "status": "error",
                "code": safety.get("code") or "backup_failed",
                "message": f"重做前的兜底备份失败，已放弃（不覆盖任何东西）：{safety.get('message') or ''}",
            }, txid, cursor, {}
        kind, path = source
        written, error = _write_back(
            kb_path,
            entries,
            dir_root=path if kind == "dir" else None,
            zip_file=path if kind == "zip" else None,
        )
        return written, error, txid, target, {"safety_backup": safety}

    return _undo_redo_common(kb_path, run, sid, audit=audit, direction="redo")


def _is_txid_name(name: str) -> bool:
    """目录名是否像一个批次 txid（`20260920T021100Z-07`）。

    `list_batches()` 用它跳过会话目录里的**非批次条目** —— 尤其是本块新增的 `stack.json`
    （否则 `batch_dir()` → `_check_txid()` 会抛 `ValueError`，把"列批次"这种只读操作炸掉）。
    """
    try:
        _check_txid(name)
    except ValueError:
        return False
    return True
