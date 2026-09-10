"""知识库全局 KP 索引（M1 链接跳转）。"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from memoria.services.kp_resolver import resolve_knowledge_points
from memoria.storage.constants import MEMORIA_DIR
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar, load_sidecar_for_md, resolve_sidecar_path


@dataclass(frozen=True)
class KpIndexEntry:
    file: str
    kp_id: str
    name: str
    range_ok: bool
    start_line: int | None
    end_line: int | None


def _read_body(kb_path: str, rel: str) -> tuple[str, list[str]]:
    full = os.path.join(kb_path, rel)
    with open(full, "r", encoding="utf-8") as f:
        raw = f.read()
    body, _ = strip_frontmatter(raw)
    lines = body.splitlines()
    return body, lines


def build_kp_index(kb_path: str) -> dict:
    """构建 { by_id, file_stems, entries }。"""
    by_id: dict[str, list[KpIndexEntry]] = {}
    file_stems: dict[str, str] = {}
    entries: list[KpIndexEntry] = []

    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        stem = os.path.splitext(os.path.basename(rel_norm))[0]
        file_stems[stem] = rel_norm

        full = os.path.join(kb_path, rel)
        body, _ = _read_body(kb_path, rel)
        sidecar = load_sidecar_for_md(full, kb_path)
        kps = resolve_knowledge_points(body, sidecar)

        for kp in kps:
            kp_id = kp.get("id") or ""
            if not kp_id:
                continue
            rr = kp.get("range_resolved") or {}
            entry = KpIndexEntry(
                file=rel_norm,
                kp_id=kp_id,
                name=kp.get("name") or kp_id,
                range_ok=bool(rr.get("ok")),
                start_line=rr.get("start_line") if rr.get("ok") else None,
                end_line=rr.get("end_line") if rr.get("ok") else None,
            )
            entries.append(entry)
            by_id.setdefault(kp_id, []).append(entry)

    return {
        "by_id": by_id,
        "file_stems": file_stems,
        "entries": entries,
    }


def entry_to_dict(entry: KpIndexEntry) -> dict:
    return {
        "file": entry.file,
        "kp_id": entry.kp_id,
        "name": entry.name,
        "range_ok": entry.range_ok,
        "start_line": entry.start_line,
        "end_line": entry.end_line,
    }


# ── G5：全库 KP id / 文件 stem / (文件, KP id) 对的轻量快照 ──────────────────
# 触发点约束（docs/to-dolist.md §12）：维护动作只允许「后台调度」或「用户显式」；
# 交互热路径（切换文件/开文档）只读快照，绝不构建。集合仅取自 sidecar，
# 不读正文、不做范围解析——旧的 build_kp_index 为拿 id 顺带解析全库范围，代价过高。

_target_cache: dict[str, dict] = {}
_target_ver: dict[str, int] = {}
_target_lock = threading.RLock()
_target_pending: dict[str, int] = {}
_target_thread: dict[str, threading.Thread] = {}

# 逐 sidecar 的 id 缓存：键为 sidecar 路径，按 (mtime_ns, size) 判新。
# 写路径走原子替换 → mtime 变化 → 自动失效；由此重建只解析变化的文件（增量）。
_file_ids_cache: dict[str, tuple[int, int, list[str]]] = {}
_file_ids_lock = threading.RLock()


def _ids_from_sidecar(sc_path: str) -> list[str]:
    try:
        st = os.stat(sc_path)
    except OSError:
        return []
    with _file_ids_lock:
        cached = _file_ids_cache.get(sc_path)
        if cached is not None and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return cached[2]
    sidecar = load_sidecar(sc_path)
    ids = [
        kp["id"]
        for kp in (sidecar or {}).get("knowledge_points") or []
        if isinstance(kp, dict) and kp.get("id")
    ]
    with _file_ids_lock:
        _file_ids_cache[sc_path] = (st.st_mtime_ns, st.st_size, ids)
    return ids


def collect_kp_targets(kb_path: str) -> dict:
    """轻量收集：只读 sidecar 的 KP id + 文件名 stem + (文件, KP id) 对（含逐文件增量缓存）。"""
    ids: set[str] = set()
    stems: dict[str, str] = {}
    pairs: set[tuple[str, str]] = set()
    for rel in collect_md_files(kb_path):
        rel_norm = rel.replace("\\", "/")
        stems[os.path.splitext(os.path.basename(rel_norm))[0]] = rel_norm
        sc_path = resolve_sidecar_path(os.path.join(kb_path, rel), kb_path)
        for kid in _ids_from_sidecar(sc_path):
            ids.add(kid)
            pairs.add((rel_norm, kid))
    return {"ids": ids, "stems": stems, "pairs": pairs}


def kp_targets_snapshot(kb_path: str) -> dict:
    """读路径：绝不构建。未命中返回空集 + ready=False（最终一致，交由后台补齐）。"""
    with _target_lock:
        c = _target_cache.get(kb_path)
        if c is None:
            return {"ids": set(), "stems": {}, "pairs": set(), "ready": False}
        return {
            "ids": c["ids"],
            "stems": c["stems"],
            "pairs": c["pairs"],
            "ready": bool(c["ready"]),
        }


def invalidate_kp_targets(kb_path: str) -> None:
    """写后失效（write-invalidate）：bump 版本、标记陈旧；旧快照保留供读路径兜底。"""
    with _target_lock:
        _target_ver[kb_path] = _target_ver.get(kb_path, 0) + 1
        c = _target_cache.get(kb_path)
        if c is not None:
            c["ready"] = False


def _kp_targets_file(kb_path: str) -> str:
    return os.path.join(kb_path, MEMORIA_DIR, "kp_targets.json")


def _save_persisted(kb_path: str, data: dict) -> None:
    """派生索引持久化（tmp + os.replace 原子替换）；失败降级，不影响内存快照。"""
    try:
        path = _kp_targets_file(kb_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "schema_version": 1,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "ids": sorted(data["ids"]),
            "stems": dict(data["stems"]),
            "pairs": [[f, k] for f, k in sorted(data["pairs"])],
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def load_persisted_kp_targets(kb_path: str) -> bool:
    """打开库时秒读上次持久化快照（避免同步全量扫描）；装载成功返回 True。"""
    try:
        path = _kp_targets_file(kb_path)
        if not os.path.isfile(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        ids = {str(x) for x in (payload.get("ids") or [])}
        stems = {str(k): str(v) for k, v in (payload.get("stems") or {}).items()}
        pairs = {
            (str(p[0]), str(p[1]))
            for p in (payload.get("pairs") or [])
            if isinstance(p, list) and len(p) == 2
        }
    except (OSError, ValueError):
        return False
    with _target_lock:
        _target_cache[kb_path] = {
            "ids": ids,
            "stems": stems,
            "pairs": pairs,
            "ver": _target_ver.get(kb_path, 0),
            "ready": True,
        }
    return True


def rebuild_kp_targets(kb_path: str) -> bool:
    """显式/后台重建（幂等）。构建期间若被再次失效则放弃本轮，返回 False。"""
    with _target_lock:
        ver = _target_ver.get(kb_path, 0)
    data = collect_kp_targets(kb_path)
    with _target_lock:
        if _target_ver.get(kb_path, 0) != ver:
            return False
        _target_cache[kb_path] = {**data, "ver": ver, "ready": True}
    _save_persisted(kb_path, data)  # 锁外写盘（不持锁做 IO）
    return True


def _kp_targets_worker(kb_path: str) -> None:
    try:
        while True:
            with _target_lock:
                _target_pending[kb_path] = 0
            rebuild_kp_targets(kb_path)
            with _target_lock:
                if _target_pending.get(kb_path, 0) > 0:
                    continue  # 构建期间又有写入 → 补一轮（合并语义）
                _target_thread[kb_path] = None
                break
    finally:
        with _target_lock:
            _target_thread[kb_path] = None


def schedule_kp_targets_rebuild(kb_path: str) -> None:
    """后台合并重建：同库单线程，构建期间再失效则补一轮；不阻塞写路径。"""
    with _target_lock:
        _target_pending[kb_path] = _target_pending.get(kb_path, 0) + 1
        th = _target_thread.get(kb_path)
        if th is not None and th.is_alive():
            return
        th = threading.Thread(
            target=_kp_targets_worker, args=(kb_path,), name="kp-targets-rebuild", daemon=True
        )
        _target_thread[kb_path] = th
    th.start()


def wait_kp_targets(kb_path: str, timeout: float = 20.0) -> None:
    """同步点（切库/关库前）：等待进行中的后台重建结束。"""
    th = _target_thread.get(kb_path)
    if th is not None and th.is_alive():
        th.join(timeout=timeout)

