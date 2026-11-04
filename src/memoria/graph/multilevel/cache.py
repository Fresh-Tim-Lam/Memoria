"""I-09 `CacheStore`：图谱派生缓存的唯一落盘域（S6-8）。

## 契约（S6-8 / S8-11 / task-352）

- 路径：``.memoria/cache/graph/{level}/{view_family}/{run_id}.json``。
- **可删除、可重建**；缓存**不是事实源**，删除不影响事实（``.md`` + sidecar + manifest）。
- GC：只清 ``cache/graph`` 下的派生文件 —— 保留最近 ``max_runs``（默认 20）或 ``max_age_days``
  （默认 90 天），两者先到者；**绝不**触碰 ``config/graph``（registry/history）与
  ``agent/audit/graph``（审计/G6），也绝不触碰 KB 事实。
- 原子写（tmp + ``os.replace``），崩溃不会留下半个 JSON。
- 路径分量做安全校验，拒绝 ``..``/绝对路径/分隔符注入。

本模块只写缓存域；所有写操作在 :class:`CacheStore` 内，默认根为 KB 的 ``.memoria`` 目录。
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CACHE_SUBDIR = Path("cache") / "graph"
DEFAULT_MAX_RUNS = 20
DEFAULT_MAX_AGE_DAYS = 90
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class CacheError(Exception):
    """缓存域错误；调用方应把它作为可见失败处理（不静默）。"""


@dataclass(frozen=True)
class CacheEntry:
    path: Path
    level: str
    view_family: str
    run_id: str
    size: int
    mtime: float


def _component(value: str, name: str) -> str:
    if not isinstance(value, str) or not _COMPONENT_RE.match(value) or value in {".", ".."}:
        raise CacheError(f"非法缓存路径分量 {name}={value!r}")
    return value


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


class CacheStore:
    """``.memoria/cache/graph`` 的读写、删除、GC。"""

    def __init__(self, memoria_dir: str | Path, *, max_runs: int = DEFAULT_MAX_RUNS,
                 max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> None:
        self.memoria_dir = Path(memoria_dir)
        self.root = self.memoria_dir / CACHE_SUBDIR
        self.max_runs = int(max_runs)
        self.max_age_days = int(max_age_days)
        if self.max_runs < 0 or self.max_age_days < 0:
            raise CacheError("max_runs/max_age_days 必须为非负整数")

    # ── 路径 ──────────────────────────────────────────────────────────
    def path_for(self, level: str, view_family: str, run_id: str) -> Path:
        level = _component(level, "level")
        view_family = _component(view_family, "view_family")
        run_id = _component(run_id, "run_id")
        return self.root / level / view_family / f"{run_id}.json"

    # ── 写/读/删 ──────────────────────────────────────────────────────
    def put(self, level: str, view_family: str, run_id: str, payload: object) -> CacheEntry:
        """原子写一个派生 JSON；同键覆盖（缓存可再生）。"""
        path = self.path_for(level, view_family, run_id)
        # canonical 编码，便于复算与 diff
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        _atomic_write(path, data)
        st = path.stat()
        return CacheEntry(path, level, view_family, run_id, st.st_size, st.st_mtime)

    def get(self, level: str, view_family: str, run_id: str) -> dict | None:
        path = self.path_for(level, view_family, run_id)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise CacheError(f"缓存损坏：{path}：{exc}") from exc

    def delete(self, level: str, view_family: str, run_id: str) -> bool:
        path = self.path_for(level, view_family, run_id)
        if not path.exists():
            return False
        path.unlink()
        # 清空目录（只清本缓存域；不向上越界）
        for parent in (path.parent, path.parent.parent):
            try:
                parent.rmdir()
            except OSError:
                break
        return True

    # ── 枚举/GC ───────────────────────────────────────────────────────
    def entries(self) -> list[CacheEntry]:
        if not self.root.exists():
            return []
        out: list[CacheEntry] = []
        for p in sorted(self.root.rglob("*.json")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.root)
            if len(rel.parts) != 3:
                continue  # 只认 {level}/{view_family}/{run_id}.json；其它忽略（不删）
            level, family, name = rel.parts
            st = p.stat()
            out.append(CacheEntry(p, level, family, name[: -len(".json")], st.st_size, st.st_mtime))
        return out

    def gc(self, *, now: float | None = None) -> dict:
        """只清缓存：保留最近 max_runs 或 max_age_days 内的文件；返回删除清单。"""
        now = time.time() if now is None else float(now)
        entries = sorted(self.entries(), key=lambda e: e.mtime, reverse=True)
        keep: set[Path] = set()
        deleted: list[str] = []
        for idx, e in enumerate(entries):
            fresh = (now - e.mtime) <= self.max_age_days * 86400
            if idx < self.max_runs and fresh:
                keep.add(e.path)
            else:
                e.path.unlink()
                deleted.append(str(e.path.relative_to(self.root)))
        # 清空目录（仅 cache/graph 下）
        for d in sorted((p for p in self.root.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
            try:
                d.rmdir()
            except OSError:
                pass
        return {"deleted": deleted, "kept": len(keep), "max_runs": self.max_runs,
                "max_age_days": self.max_age_days}

    def clear(self) -> int:
        """删除全部缓存（可重建）；只动 cache/graph。"""
        n = 0
        for e in self.entries():
            e.path.unlink()
            n += 1
        self.gc()
        return n

    # ── 边界自证 ──────────────────────────────────────────────────────
    def assert_only_cache(self, paths: Iterable[str | Path]) -> None:
        """断言给定路径都在 cache/graph 域内（用于测试/审计）。"""
        root = self.root.resolve()
        for p in paths:
            rp = Path(p).resolve()
            if root != rp and root not in rp.parents:
                raise CacheError(f"路径越出缓存域：{rp}")
