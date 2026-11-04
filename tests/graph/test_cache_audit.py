"""B5：I-09 CacheStore / I-10 AuditLog（S6-8）。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from memoria.graph.multilevel.audit import AuditError, AuditLog
from memoria.graph.multilevel.cache import CacheError, CacheStore


# ── CacheStore ──────────────────────────────────────────────────────

def test_cache_path_and_roundtrip(tmp_path):
    store = CacheStore(tmp_path)
    e = store.put("L1", "fam-a", "run_001", {"a": 1})
    assert e.path == tmp_path / "cache" / "graph" / "L1" / "fam-a" / "run_001.json"
    assert store.get("L1", "fam-a", "run_001") == {"a": 1}
    assert store.delete("L1", "fam-a", "run_001") is True
    assert store.get("L1", "fam-a", "run_001") is None


@pytest.mark.parametrize("bad", ["..", "../x", "a/b", "/abs", "", "."])
def test_cache_rejects_unsafe_components(tmp_path, bad):
    store = CacheStore(tmp_path)
    with pytest.raises(CacheError):
        store.path_for(bad, "fam", "run_1")


def test_cache_gc_only_cache_and_keeps_20_recent(tmp_path):
    store = CacheStore(tmp_path)
    # 25 个 run，mtime 递减（run_00 最新）
    now = time.time()
    for i in range(25):
        store.put("L1", "fam-a", f"run_{i:02d}", {"i": i})
        p = store.path_for("L1", "fam-a", f"run_{i:02d}")
        os.utime(p, (now - i * 10, now - i * 10))
    # 一个 100 天前的文件（即使最近也要被 GC）
    store.put("L1", "fam-a", "run_old", {"old": True})
    os.utime(store.path_for("L1", "fam-a", "run_old"), (now - 100 * 86400, now - 100 * 86400))
    # 相邻域哨兵：GC 不得触碰 config/audit
    sentinel_cfg = tmp_path / "config" / "graph" / "keep.json"
    sentinel_cfg.parent.mkdir(parents=True, exist_ok=True)
    sentinel_cfg.write_text("{}", encoding="utf-8")
    sentinel_audit = tmp_path / "agent" / "audit" / "graph" / "audit.jsonl"
    sentinel_audit.parent.mkdir(parents=True, exist_ok=True)
    sentinel_audit.write_text("x\n", encoding="utf-8")

    rep = store.gc(now=now)
    remaining = store.entries()
    assert len(remaining) == 20
    assert all("run_old" not in e.path.name for e in remaining)
    assert sentinel_cfg.exists() and sentinel_audit.exists()
    # deleted 为 cache 域内相对路径；不得越界
    assert rep["deleted"] and all(not Path(d).is_absolute() and ".." not in Path(d).parts
                                  and (store.root / d).exists() is False for d in rep["deleted"])


def test_cache_clear_is_rebuildable(tmp_path):
    store = CacheStore(tmp_path)
    for i in range(3):
        store.put("L1", "f", f"r{i}", {"i": i})
    assert store.clear() == 3
    assert store.entries() == []


# ── AuditLog ────────────────────────────────────────────────────────

def test_audit_append_only_and_chain(tmp_path):
    log = AuditLog(tmp_path)
    r1 = log.append(kind="g6", actor="se", ref="snap_1", decision="write")
    raw1 = log.path.read_bytes()
    r2 = log.append(kind="g7", actor="se", ref="g7_1", decision="gate",
                    detail={"write_attempts": 0})
    raw2 = log.path.read_bytes()
    # append-only：第二次只追加，前 N 字节不变
    assert raw2[:len(raw1)] == raw1
    assert r1.prev == "" and r2.prev == r1.digest
    assert log.verify_chain()["ok"] is True
    assert [x.audit_id for x in log.read_all()] == [r1.audit_id, r2.audit_id]


def test_audit_tamper_detected(tmp_path):
    log = AuditLog(tmp_path)
    log.append(kind="g6", actor="se", ref="snap_1", decision="write")
    data = log.path.read_text(encoding="utf-8")
    log.path.write_text(data.replace('"decision":"write"', '"decision":"tampered"'), encoding="utf-8")
    with pytest.raises(AuditError):
        log.verify_chain()


def test_audit_location_and_forbidden_detail(tmp_path):
    log = AuditLog(tmp_path)
    assert log.path.parent == tmp_path / "agent" / "audit" / "graph"
    with pytest.raises(AuditError):
        log.append(kind="g6", actor="se", ref="x", decision="d", detail={"body": "正文"})
    with pytest.raises(AuditError):
        AuditLog(tmp_path, filename="../x.jsonl")


def test_audit_is_not_fact_source(tmp_path):
    """审计文件不进入 cache/registry/sidecar；删除不影响事实。"""
    log = AuditLog(tmp_path)
    log.append(kind="g6", actor="se", ref="snap_1", decision="write")
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "config").exists()
    log.path.unlink()
    assert log.read_all() == []
