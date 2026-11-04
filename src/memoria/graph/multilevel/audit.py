"""I-10 `AuditLog`：图谱审计的 append-only 落盘域（S6-8 / S8-11）。

## 契约

- 路径：``.memoria/agent/audit/graph/audit.jsonl``（append-only；不参与事实源）。
- 每条记录带 ``audit_id`` 与哈希链 ``prev``/``digest``；重算即可发现篡改。
- **只追加**：已有字节永不改写/截断；追加用 ``O_APPEND`` 单次写入。
- 审计不是事实源：删除审计不影响图谱事实；本模块不写 sidecar/registry/cache。
- 不记录正文/excerpt/PII；调用方只传 id/anchor/引用/计数类字段。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

AUDIT_SUBDIR = Path("agent") / "audit" / "graph"


class AuditError(Exception):
    """审计域错误（可见失败，不静默）。"""


def canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_canonical(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    kind: str
    actor: str
    ref: str
    decision: str
    at: str
    detail: dict
    prev: str
    digest: str

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "kind": self.kind,
            "actor": self.actor,
            "ref": self.ref,
            "decision": self.decision,
            "at": self.at,
            "detail": self.detail,
            "prev": self.prev,
            "digest": self.digest,
        }


class AuditLog:
    """``agent/audit/graph/audit.jsonl`` 的追加与链校验。"""

    def __init__(self, memoria_dir: str | Path, *, filename: str = "audit.jsonl") -> None:
        if not isinstance(filename, str) or "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
            raise AuditError(f"非法审计文件名：{filename!r}")
        self.memoria_dir = Path(memoria_dir)
        self.root = self.memoria_dir / AUDIT_SUBDIR
        self.path = self.root / filename
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def path_str(self) -> str:
        return str(self.path)

    def _records(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AuditError(f"审计第 {lineno} 行非法 JSON：{exc}") from exc
                if not isinstance(item, dict):
                    raise AuditError(f"审计第 {lineno} 行不是对象")
                out.append(item)
        return out

    def append(self, *, kind: str, actor: str, ref: str, decision: str,
               detail: dict | None = None, at: str | None = None) -> AuditRecord:
        if not all(isinstance(x, str) and x for x in (kind, actor, ref, decision)):
            raise AuditError("kind/actor/ref/decision 必须为非空字符串")
        detail = dict(detail or {})
        # 隐私防线：审计不落正文/excerpt/PII 类字段
        forbidden = {"body", "excerpt", "content", "text", "quote", "pii"}
        bad = sorted(k for k in detail if str(k).lower() in forbidden)
        if bad:
            raise AuditError(f"审计 detail 含禁止字段：{bad}")
        at = at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        prev = ""
        try:
            prev = str(self._records()[-1].get("digest", "")) if self.path.exists() else ""
        except AuditError:
            raise
        base = {"kind": kind, "actor": actor, "ref": ref, "decision": decision,
                "at": at, "detail": detail, "prev": prev}
        digest = sha256_canonical(base)
        audit_id = "aud_" + digest[:16]
        rec = dict(base, audit_id=audit_id, digest=digest)
        line = json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        # O_APPEND 单次写入；不重写已有字节
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return AuditRecord(audit_id, kind, actor, ref, decision, at, detail, prev, digest)

    def read_all(self) -> list[AuditRecord]:
        return [AuditRecord(**r) for r in self._records()]

    def verify_chain(self) -> dict:
        recs = self._records()
        prev = ""
        for idx, r in enumerate(recs, 1):
            for key in ("audit_id", "kind", "actor", "ref", "decision", "at", "detail", "prev", "digest"):
                if key not in r:
                    raise AuditError(f"审计第 {idx} 条缺字段 {key}")
            if r["prev"] != prev:
                raise AuditError(f"审计第 {idx} 条 prev 断链")
            base = {k: r[k] for k in ("kind", "actor", "ref", "decision", "at", "detail", "prev")}
            digest = sha256_canonical(base)
            if r["digest"] != digest:
                raise AuditError(f"审计第 {idx} 条 digest 不匹配")
            if r["audit_id"] != "aud_" + digest[:16]:
                raise AuditError(f"审计第 {idx} 条 audit_id 不匹配")
            prev = digest
        return {"records": len(recs), "head": prev, "ok": True}

    def tail(self, n: int = 20) -> list[dict]:
        return [r.to_dict() for r in self._records()[-max(0, int(n)):]]
