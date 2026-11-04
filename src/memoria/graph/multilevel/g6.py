"""I-11 `G6Snapshot` + G7 agent 指标快照（S6-11 / S8-2 / S8-6）。

## G6（唯一事实源 = ``.memoria/agent/audit/graph/g6/``）

- 字段严格等于 S6 ``G6_SNAPSHOT``；不允许额外键（fail-closed）。
- ``snapshot_id = sha256(canonical(G6_SNAPSHOT without snapshot_id))``。
- 写入后**不可变**：同 id 文件已存在 ⇒ 拒绝覆盖（即使字节相同）。
- 单份 ≤1MB；``replay`` 2× 结果 sha 必须一致。
- 基线更新必须给 ``decision_id``，旧快照保留（不删除）。

## G7（agent 指标；只存 id/anchor/引用/counts）

- 禁止正文/excerpt/PII；``write_attempts=0``、``read_only_ratio=1.0``。
- G7 引用 G6 的 ``run_ids/frame_ids``，不复制事实。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from memoria.graph.multilevel.audit import AUDIT_SUBDIR, AuditLog, canonical_bytes, sha256_canonical

G6_SUBDIR = AUDIT_SUBDIR / "g6"
G7_SUBDIR = AUDIT_SUBDIR / "g7"
G6_MAX_BYTES = 1 * 1024 * 1024
G7_MAX_BYTES = 64 * 1024 * 1024
G6_VERSION = 1
G7_VERSION = 1

G6_FIELDS: tuple[str, ...] = (
    "g6_version", "data_source_sha", "run_ids", "registry_sha", "vm_sha",
    "frame_ids", "frame_sha", "nav_sha", "rule_histogram", "node_count",
    "edge_count", "subset_ok", "determinism_sha", "closure_violations",
    "behind_violations", "history_signed",
)
G7_FIELDS: tuple[str, ...] = (
    "g7_version", "data_source_sha", "run_ids", "frame_ids", "tool_calls",
    "tokens", "write_attempts", "read_only_ratio", "reference_completeness",
    "unknown_ratio", "degraded_count",
)
G7_FORBIDDEN_KEYS = frozenset({"body", "excerpt", "content", "text", "quote", "pii"})
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class SnapshotError(Exception):
    """快照域错误（可见失败）。"""


def _sha_ok(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.match(value))


def _clean_ids(values: object, name: str) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
        raise SnapshotError(f"{name} 必须为字符串数组")
    if len(set(values)) != len(values):
        raise SnapshotError(f"{name} 不允许重复")
    return sorted(values)


def _check_no_forbidden(obj: object, path: str = "$") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in G7_FORBIDDEN_KEYS:
                raise SnapshotError(f"G7 禁止字段 {path}.{k}（正文/excerpt/PII）")
            _check_no_forbidden(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _check_no_forbidden(v, f"{path}[{i}]")


@dataclass(frozen=True)
class G6Snapshot:
    g6_version: int
    data_source_sha: str
    run_ids: list[str]
    registry_sha: str
    vm_sha: str
    frame_ids: list[str]
    frame_sha: str
    nav_sha: str
    rule_histogram: dict[str, int]
    node_count: int
    edge_count: int
    subset_ok: bool
    determinism_sha: str
    closure_violations: int
    behind_violations: int
    history_signed: bool

    def payload(self) -> dict:
        return {
            "g6_version": self.g6_version,
            "data_source_sha": self.data_source_sha,
            "run_ids": self.run_ids,
            "registry_sha": self.registry_sha,
            "vm_sha": self.vm_sha,
            "frame_ids": self.frame_ids,
            "frame_sha": self.frame_sha,
            "nav_sha": self.nav_sha,
            "rule_histogram": self.rule_histogram,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "subset_ok": self.subset_ok,
            "determinism_sha": self.determinism_sha,
            "closure_violations": self.closure_violations,
            "behind_violations": self.behind_violations,
            "history_signed": self.history_signed,
        }

    @property
    def snapshot_id(self) -> str:
        return sha256_canonical(self.payload())


def normalize_g6(data: dict) -> G6Snapshot:
    if not isinstance(data, dict):
        raise SnapshotError("G6 必须是对象")
    extra = sorted(set(data) - set(G6_FIELDS) - {"snapshot_id"})
    missing = sorted(set(G6_FIELDS) - set(data))
    if extra:
        raise SnapshotError(f"G6 含未冻结字段：{extra}")
    if missing:
        raise SnapshotError(f"G6 缺字段：{missing}")
    if data["g6_version"] != G6_VERSION:
        raise SnapshotError(f"g6_version 必须为 {G6_VERSION}")
    for key in ("data_source_sha", "registry_sha", "vm_sha", "frame_sha", "nav_sha", "determinism_sha"):
        if not _sha_ok(data[key]):
            raise SnapshotError(f"{key} 必须是 sha256")
    run_ids = _clean_ids(data["run_ids"], "run_ids")
    frame_ids = _clean_ids(data["frame_ids"], "frame_ids")
    hist = data["rule_histogram"]
    if not isinstance(hist, dict) or any(not isinstance(k, str) or not isinstance(v, int) or v < 0 for k, v in hist.items()):
        raise SnapshotError("rule_histogram 必须为 {rule_id: 非负整数}")
    for key in ("node_count", "edge_count", "closure_violations", "behind_violations"):
        if not isinstance(data[key], int) or isinstance(data[key], bool) or data[key] < 0:
            raise SnapshotError(f"{key} 必须为非负整数")
    for key in ("subset_ok", "history_signed"):
        if not isinstance(data[key], bool):
            raise SnapshotError(f"{key} 必须为 bool")
    if data["closure_violations"] != 0 or data["behind_violations"] != 0:
        # 冻结值：G6 里必须为 0；非 0 只允许出现在失败报告，不能写快照
        raise SnapshotError("closure/behind violations 必须为 0（S8 P0）")
    return G6Snapshot(G6_VERSION, data["data_source_sha"], run_ids, data["registry_sha"],
                      data["vm_sha"], frame_ids, data["frame_sha"], data["nav_sha"],
                      dict(sorted(hist.items())), data["node_count"], data["edge_count"],
                      data["subset_ok"], data["determinism_sha"],
                      data["closure_violations"], data["behind_violations"], data["history_signed"])


class G6Store:
    """G6 快照/基线存储（audit/g6，唯一域）。"""

    def __init__(self, memoria_dir: str | Path) -> None:
        self.memoria_dir = Path(memoria_dir)
        self.root = self.memoria_dir / G6_SUBDIR
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, snapshot_id: str) -> Path:
        if not _sha_ok(snapshot_id):
            raise SnapshotError("snapshot_id 必须是 sha256")
        return self.root / f"{snapshot_id}.json"

    def snapshot_bytes(self, snap: G6Snapshot) -> bytes:
        doc = dict(snap.payload(), snapshot_id=snap.snapshot_id)
        data = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(data) > G6_MAX_BYTES:
            raise SnapshotError(f"G6 快照超过 {G6_MAX_BYTES} 字节")
        return data

    def write(self, data: dict) -> dict:
        snap = normalize_g6(data)
        sid = snap.snapshot_id
        path = self.path_for(sid)
        if path.exists():
            raise SnapshotError(f"G6 不可变：快照已存在 {sid}")
        raw = self.snapshot_bytes(snap)
        tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
        with tmp.open("wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return {"snapshot_id": sid, "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw)}

    def load(self, snapshot_id: str) -> dict:
        path = self.path_for(snapshot_id)
        if not path.exists():
            raise SnapshotError(f"G6 快照不存在：{snapshot_id}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("snapshot_id") != snapshot_id:
            raise SnapshotError("G6 快照 snapshot_id 不匹配")
        snap = normalize_g6(doc)
        if snap.snapshot_id != snapshot_id:
            raise SnapshotError("G6 快照 id 不可复算（被篡改）")
        return doc

    def replay(self, snapshot_id: str, *, times: int = 2) -> dict:
        """重复读取/复算；2× sha 必须一致。"""
        seen = []
        for _ in range(max(2, int(times))):
            doc = self.load(snapshot_id)
            snap = normalize_g6(doc)
            seen.append({"snapshot_id": snap.snapshot_id,
                         "sha256": sha256_canonical(doc), "bytes": len(self.snapshot_bytes(snap))})
        if len({x["snapshot_id"] for x in seen}) != 1 or len({x["sha256"] for x in seen}) != 1:
            raise SnapshotError("G6 replay 2× 不一致")
        return {"snapshot_id": snapshot_id, "sha256": seen[0]["sha256"], "runs": len(seen), "ok": True}

    # ── 基线 ──────────────────────────────────────────────────────────
    @property
    def baseline_path(self) -> Path:
        return self.root / "baseline.json"

    def update_baseline(self, snapshot_id: str, *, decision_id: str) -> dict:
        if not decision_id:
            raise SnapshotError("基线更新必须提供 decision_id")
        self.load(snapshot_id)  # 必须存在且可验证
        doc = {"snapshot_id": snapshot_id, "decision_id": decision_id}
        self.baseline_path.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True,
                                                 separators=(",", ":")) + "\n", encoding="utf-8")
        return doc

    def verify_baseline(self, baseline_path: str | Path | None = None) -> dict:
        path = Path(baseline_path) if baseline_path else self.baseline_path
        if not path.exists():
            raise SnapshotError(f"G6 基线不存在：{path}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        sid = doc.get("snapshot_id") if isinstance(doc, dict) else None
        if not _sha_ok(sid):
            raise SnapshotError("G6 基线缺 snapshot_id")
        snap = self.load(sid)
        rep = self.replay(sid)
        return {"ok": True, "baseline": str(path), "snapshot_id": sid,
                "decision_id": doc.get("decision_id", ""), "replay": rep}


@dataclass(frozen=True)
class G7Snapshot:
    g7_version: int
    data_source_sha: str
    run_ids: list[str]
    frame_ids: list[str]
    tool_calls: int
    tokens: int
    write_attempts: int
    read_only_ratio: float
    reference_completeness: float
    unknown_ratio: float
    degraded_count: int

    def payload(self) -> dict:
        return {
            "g7_version": self.g7_version,
            "data_source_sha": self.data_source_sha,
            "run_ids": self.run_ids,
            "frame_ids": self.frame_ids,
            "tool_calls": self.tool_calls,
            "tokens": self.tokens,
            "write_attempts": self.write_attempts,
            "read_only_ratio": self.read_only_ratio,
            "reference_completeness": self.reference_completeness,
            "unknown_ratio": self.unknown_ratio,
            "degraded_count": self.degraded_count,
        }

    @property
    def snapshot_id(self) -> str:
        return sha256_canonical(self.payload())


def normalize_g7(data: dict) -> G7Snapshot:
    if not isinstance(data, dict):
        raise SnapshotError("G7 必须是对象")
    extra = sorted(set(data) - set(G7_FIELDS) - {"snapshot_id"})
    missing = sorted(set(G7_FIELDS) - set(data))
    if extra:
        raise SnapshotError(f"G7 含未冻结字段：{extra}")
    if missing:
        raise SnapshotError(f"G7 缺字段：{missing}")
    _check_no_forbidden(data)
    if data["g7_version"] != G7_VERSION:
        raise SnapshotError(f"g7_version 必须为 {G7_VERSION}")
    if not _sha_ok(data["data_source_sha"]):
        raise SnapshotError("data_source_sha 必须是 sha256")
    run_ids = _clean_ids(data["run_ids"], "run_ids")
    frame_ids = _clean_ids(data["frame_ids"], "frame_ids")
    for key in ("tool_calls", "tokens", "write_attempts", "degraded_count"):
        if not isinstance(data[key], int) or isinstance(data[key], bool) or data[key] < 0:
            raise SnapshotError(f"{key} 必须为非负整数")
    for key in ("read_only_ratio", "reference_completeness", "unknown_ratio"):
        v = data[key]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= float(v) <= 1.0):
            raise SnapshotError(f"{key} 必须在 [0,1]")
    return G7Snapshot(G7_VERSION, data["data_source_sha"], run_ids, frame_ids,
                      data["tool_calls"], data["tokens"], data["write_attempts"],
                      float(data["read_only_ratio"]), float(data["reference_completeness"]),
                      float(data["unknown_ratio"]), data["degraded_count"])


class G7Store:
    """G7 指标快照/门禁（audit/g7）。"""

    def __init__(self, memoria_dir: str | Path) -> None:
        self.memoria_dir = Path(memoria_dir)
        self.root = self.memoria_dir / G7_SUBDIR
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, snapshot_id: str) -> Path:
        if not _sha_ok(snapshot_id):
            raise SnapshotError("snapshot_id 必须是 sha256")
        return self.root / f"{snapshot_id}.json"

    def write(self, data: dict) -> dict:
        snap = normalize_g7(data)
        raw = json.dumps(dict(snap.payload(), snapshot_id=snap.snapshot_id),
                         ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > G7_MAX_BYTES:
            raise SnapshotError(f"G7 超过 {G7_MAX_BYTES} 字节")
        path = self.path_for(snap.snapshot_id)
        if path.exists():
            raise SnapshotError(f"G7 不可变：快照已存在 {snap.snapshot_id}")
        path.write_bytes(raw)
        return {"snapshot_id": snap.snapshot_id, "path": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def load(self, snapshot_id: str) -> dict:
        path = self.path_for(snapshot_id)
        if not path.exists():
            raise SnapshotError(f"G7 快照不存在：{snapshot_id}")
        doc = json.loads(path.read_text(encoding="utf-8"))
        snap = normalize_g7(doc)
        if snap.snapshot_id != doc.get("snapshot_id"):
            raise SnapshotError("G7 snapshot_id 不匹配")
        return doc

    def assert_g_g7(self, data: dict, *, g6: G6Store | None = None) -> dict:
        """G-G7 P0：write_attempts=0、read_only=100%、引用 G6、无正文/excerpt/PII。"""
        snap = normalize_g7(data)
        if snap.write_attempts != 0:
            raise SnapshotError("G-G7: write_attempts 必须为 0")
        if abs(snap.read_only_ratio - 1.0) > 1e-9:
            raise SnapshotError("G-G7: read_only_ratio 必须为 1.0")
        if g6 is not None:
            baseline = g6.verify_baseline()
            g6doc = g6.load(baseline["snapshot_id"])
            if not set(snap.run_ids) <= set(g6doc["run_ids"]):
                raise SnapshotError("G-G7: run_ids 不在 G6 引用内")
            if not set(snap.frame_ids) <= set(g6doc["frame_ids"]):
                raise SnapshotError("G-G7: frame_ids 不在 G6 引用内")
        return {"ok": True, "g_g7": {"write_attempts": 0, "read_only_ratio": 1.0},
                "snapshot_id": snap.snapshot_id}
