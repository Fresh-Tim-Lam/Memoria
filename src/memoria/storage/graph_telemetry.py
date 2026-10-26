"""图谱埋点 E1/E2（KGViz D-KGV-08）—— 本地 append-only JSONL。

## 为什么在这里（而不是另起一个存储）

task-160 已把用户态统一到 `%LOCALAPPDATA%\\Memoria\\config\\`（见 `memoria.util.user_state`）。
本模块只调用该既有目录解析（并尊重 `MEMORIA_CONFIG_DIR` 测试覆盖），**不新增第二条用户态路径规则**。

## 采什么（设计 §5，冻结）

- **E1** `nodeRadius` 变化：`{ts, from, to}`（+ style/zoom/语料上下文）
- **E2** `graphStyle` 切换：`{ts, from, to}`
- 明确不采：`node_radius_px`（映射产出，改映射后历史值不可比）、`labelHover` 逐事件（per-frame 反模式）。

## 三条硬要求（Lead task-178）

1. **埋点失败不影响主功能**：所有写失败都吞掉并计数（`record_events` 永不 raise）；
2. **本地、append-only、不上传**：本模块无任何网络调用；
3. **损坏行不影响后续追加**：写入只追加；读取逐行容错并统计 `bad_lines`。
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR_NAME = "Memoria"
TELEMETRY_FILE = "graph-telemetry.jsonl"
EVENT_NODE_RADIUS = "nodeRadius_change"
EVENT_GRAPH_STYLE = "graphStyle_change"
_ALLOWED_EVENTS = {EVENT_NODE_RADIUS, EVENT_GRAPH_STYLE}
#: 明确禁采的字段（命中即丢弃事件，防止将来"顺手"加回来）
_FORBIDDEN_FIELDS = {"node_radius_px", "labelHover"}
#: 单事件允许的额外上下文字段白名单（只记拓扑/事件事实）
_CONTEXT_FIELDS = {
    "kb_path",
    "node_count",
    "edge_count",
    "style",
    "zoom",
    "zoom_kind",
    "source",
    "app_version",
}

#: 写失败计数（可观测；summary 里返回，不打断主流程）
_WRITE_FAILURES = 0
_LAST_WRITE_ERROR: str | None = None
_IDENTITY_CACHE: dict[str, dict[str, Any]] = {}


def telemetry_path() -> Path:
    """图谱埋点文件路径：与 ui-settings.json 同目录（既有用户态目录）。"""
    base = os.environ.get("MEMORIA_CONFIG_DIR")
    if base:
        return Path(base) / TELEMETRY_FILE
    from memoria.util.user_state import user_config_dir

    return user_config_dir() / TELEMETRY_FILE


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _kb_identity(kb_path: str | None) -> dict[str, Any]:
    """语料上下文：manifest sha256 / HEAD sha。计算失败一律返回 None 字段（绝不抛错）。"""
    if not kb_path:
        return {"kb_path": None, "manifest_sha256": None, "head": None}
    key = str(kb_path)
    cached = _IDENTITY_CACHE.get(key)
    if cached is not None:
        return dict(cached)
    manifest_sha = None
    head = None
    try:
        p = Path(kb_path)
        manifest = p / ".memoria" / "manifest.yaml"
        if manifest.is_file():
            import hashlib

            manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
        head = _git_head(p)
    except Exception:
        pass
    ident = {
        "kb_path": key,
        "manifest_sha256": manifest_sha,
        "head": head,
        "measured_at": _now_utc(),
    }
    _IDENTITY_CACHE[key] = dict(ident)
    return ident


def _git_head(path: Path) -> str | None:
    """KB 位于 git 仓库内时取 HEAD sha；否则 None。失败静默。"""
    try:
        from memoria.util.proc import no_window_kwargs

        p = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            **no_window_kwargs(),
        )
        if p.returncode == 0:
            out = (p.stdout or "").strip()
            return out or None
    except Exception:
        pass
    return None


def _sanitize_event(raw: Any, context: dict[str, Any] | None) -> dict[str, Any] | None:
    """校验/白名单化一条事件；不合法返回 None（不 raise）。"""
    if not isinstance(raw, dict):
        return None
    event = raw.get("event")
    if event not in _ALLOWED_EVENTS:
        return None
    if any(k in raw for k in _FORBIDDEN_FIELDS):
        return None
    frm = raw.get("from")
    to = raw.get("to")
    # E1 数值 / E2 字符串；from == to 不记录（不是"变化"）
    if event == EVENT_NODE_RADIUS:
        if not isinstance(frm, (int, float)) or not isinstance(to, (int, float)):
            return None
    if frm == to:
        return None
    rec: dict[str, Any] = {
        "v": 1,
        "ts": raw.get("ts") if isinstance(raw.get("ts"), (int, float)) else None,
        "ts_utc": _now_utc(),
        "event": event,
        "from": frm,
        "to": to,
    }
    for k in _CONTEXT_FIELDS:
        if k in raw and raw[k] is not None:
            rec[k] = raw[k]
    if context:
        for k, v in context.items():
            if k in _CONTEXT_FIELDS and v is not None and k not in rec:
                rec[k] = v
    ident = _kb_identity(rec.get("kb_path") if isinstance(rec.get("kb_path"), str) else None)
    rec["corpus"] = ident
    return rec


def record_events(events: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """追加一条/多条事件。**永不 raise**；失败返回 status=degraded + 可观测计数。"""
    global _WRITE_FAILURES, _LAST_WRITE_ERROR
    if events is None:
        return {"status": "ok", "appended": 0, "skipped": 0, "write_failures": _WRITE_FAILURES}
    if isinstance(events, dict):
        events = [events]
    if not isinstance(events, list):
        events = []
    clean: list[dict[str, Any]] = []
    skipped = 0
    for raw in events:
        rec = _sanitize_event(raw, context)
        if rec is None:
            skipped += 1
        else:
            clean.append(rec)
    if not clean:
        return {
            "status": "ok",
            "appended": 0,
            "skipped": skipped,
            "write_failures": _WRITE_FAILURES,
            "path": str(telemetry_path()),
        }
    appended = 0
    try:
        path = telemetry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            for rec in clean:
                f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
                appended += 1
            f.flush()
            os.fsync(f.fileno())
        _LAST_WRITE_ERROR = None
    except Exception as exc:  # noqa: BLE001 - 埋点失败必须静默（T-tel-7）
        _WRITE_FAILURES += 1
        _LAST_WRITE_ERROR = f"{type(exc).__name__}: {exc}"[:300]
        return {
            "status": "degraded",
            "appended": 0,
            "skipped": skipped,
            "write_failures": _WRITE_FAILURES,
            "error": _LAST_WRITE_ERROR,
            "path": str(telemetry_path()),
        }
    return {
        "status": "ok",
        "appended": appended,
        "skipped": skipped,
        "write_failures": _WRITE_FAILURES,
        "path": str(telemetry_path()),
    }


def read_events() -> dict[str, Any]:
    """逐行读取（坏行跳过并计数）；文件不存在 ⇒ 空。只读，不重写。"""
    path = telemetry_path()
    events: list[dict[str, Any]] = []
    bad_lines = 0
    if not path.is_file():
        return {"events": events, "bad_lines": bad_lines, "path": str(path), "exists": False}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    rec = json.loads(s)
                except Exception:
                    bad_lines += 1
                    continue
                if not isinstance(rec, dict) or rec.get("event") not in _ALLOWED_EVENTS:
                    bad_lines += 1
                    continue
                events.append(rec)
    except Exception:
        # 读失败也不抛：返回已读部分 + 可观测状态
        return {
            "events": events,
            "bad_lines": bad_lines,
            "path": str(path),
            "exists": True,
            "read_error": True,
        }
    return {"events": events, "bad_lines": bad_lines, "path": str(path), "exists": True}


def summary() -> dict[str, Any]:
    """读取接口：回答两个问题（不改历史、不联网）。"""
    data = read_events()
    events = data.get("events") or []
    e1 = [e for e in events if e.get("event") == EVENT_NODE_RADIUS]
    e2 = [e for e in events if e.get("event") == EVENT_GRAPH_STYLE]

    radius_changes = []
    radius_transition_counts: dict[str, int] = {}
    radius_from_counts: dict[str, int] = {}
    radius_to_counts: dict[str, int] = {}
    for e in e1:
        frm, to = e.get("from"), e.get("to")
        radius_changes.append({"ts_utc": e.get("ts_utc"), "from": frm, "to": to})
        key = f"{frm}->{to}"
        radius_transition_counts[key] = radius_transition_counts.get(key, 0) + 1
        radius_from_counts[str(frm)] = radius_from_counts.get(str(frm), 0) + 1
        radius_to_counts[str(to)] = radius_to_counts.get(str(to), 0) + 1

    style_transition_counts: dict[str, int] = {}
    style_to_counts: dict[str, int] = {}
    for e in e2:
        frm, to = e.get("from"), e.get("to")
        key = f"{frm}->{to}"
        style_transition_counts[key] = style_transition_counts.get(key, 0) + 1
        style_to_counts[str(to)] = style_to_counts.get(str(to), 0) + 1

    return {
        "status": "ok",
        "path": data.get("path"),
        "exists": data.get("exists", False),
        "events_total": len(events),
        "bad_lines": data.get("bad_lines", 0),
        "write_failures": _WRITE_FAILURES,
        "last_write_error": _LAST_WRITE_ERROR,
        "E1_nodeRadius": {
            "count": len(e1),
            "changed_count": len([e for e in e1 if e.get("from") != e.get("to")]),
            "transitions": radius_changes,
            "transition_counts": radius_transition_counts,
            "from_counts": radius_from_counts,
            "to_counts": radius_to_counts,
        },
        "E2_graphStyle": {
            "count": len(e2),
            "distribution": style_to_counts,
            "transition_counts": style_transition_counts,
        },
    }


def reset_for_tests() -> None:
    """仅测试用：清空写失败计数（不删文件）。"""
    global _WRITE_FAILURES, _LAST_WRITE_ERROR
    _WRITE_FAILURES = 0
    _LAST_WRITE_ERROR = None
    _IDENTITY_CACHE.clear()
