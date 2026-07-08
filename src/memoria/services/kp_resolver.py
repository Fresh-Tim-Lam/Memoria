"""知识点 range 解析。"""

from __future__ import annotations

from memoria.range.locator import resolve_range


def resolve_knowledge_points(body: str, sidecar: dict | None) -> list[dict]:
    lines = body.splitlines()
    kps = (sidecar or {}).get("knowledge_points") or []
    resolved: list[dict] = []
    for kp in kps:
        item = dict(kp)
        rng = kp.get("range") or {}
        start_spec = rng.get("start") or {}
        end_spec = rng.get("end") or {}
        if start_spec.get("snippet") and end_spec.get("snippet"):
            item["range_resolved"] = resolve_range(lines, start_spec, end_spec)
        else:
            item["range_resolved"] = {"ok": False, "error": "missing_snippet"}
        resolved.append(item)
    return resolved
