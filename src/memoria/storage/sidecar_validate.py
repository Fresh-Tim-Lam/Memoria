"""侧车 M0 校验：写入前拒绝、加载时报告 warnings。"""

from __future__ import annotations

from memoria.graph.edge_types import EDGE_EXTEND, EDGE_REFERENCE, EDGE_TYPES, normalize_edge_type
from memoria.range.locator import resolve_range
from memoria.storage.constants import SIDECAR_SCHEMA_VERSION


def _norm_path(p: str) -> str:
    return p.replace("\\", "/")


def _normalize_edge_targets(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if isinstance(t, str) and str(t).strip()]
    return []


def validate_sidecar(
    data: dict | None,
    rel_path: str,
    lines: list[str] | None = None,
    known_kp_ids: set[str] | None = None,
) -> dict:
    """返回 {ok, errors[], warnings[]}。有 errors 时不可写入。"""
    errors: list[str] = []
    warnings: list[str] = []

    if not data:
        return {"ok": True, "errors": [], "warnings": []}

    if not isinstance(data, dict):
        return {"ok": False, "errors": ["配置文件格式无效"], "warnings": []}

    ver = data.get("schema_version")
    if ver is None:
        warnings.append("缺少 schema_version，将按 1 处理")
    elif ver != SIDECAR_SCHEMA_VERSION:
        errors.append(f"不支持的 schema_version: {ver}")

    file_field = data.get("file")
    if file_field and _norm_path(str(file_field)) != _norm_path(rel_path):
        warnings.append(f"配置中的 file 路径 ({file_field}) 与文件位置 ({rel_path}) 不一致")

    kps = data.get("knowledge_points")
    if kps is None:
        warnings.append("缺少 knowledge_points")
        kps = []
    elif not isinstance(kps, list):
        errors.append("knowledge_points 必须为列表")
        kps = []

    seen_ids: set[str] = set()
    for i, kp in enumerate(kps):
        if not isinstance(kp, dict):
            errors.append(f"knowledge_points[{i}] 格式无效")
            continue
        kp_id = kp.get("id")
        if not kp_id:
            errors.append(f"knowledge_points[{i}] 缺少 id")
        elif kp_id in seen_ids:
            errors.append(f"重复的知识点 id: {kp_id}")
        else:
            seen_ids.add(kp_id)

        if not kp.get("name"):
            warnings.append(f"KP {kp_id or i} 缺少 name")

        tags = kp.get("tags")
        if tags is not None:
            if not isinstance(tags, list):
                errors.append(f"KP {kp_id or i} tags 必须为列表")
            else:
                for j, tag in enumerate(tags):
                    if not isinstance(tag, str) or not str(tag).strip():
                        errors.append(f"KP {kp_id or i} tags[{j}] 无效")

        tc = kp.get("tag_candidates")
        if tc is not None:
            if not isinstance(tc, list):
                errors.append(f"KP {kp_id or i} tag_candidates 必须为列表")
            else:
                for j, cand in enumerate(tc):
                    if not isinstance(cand, dict):
                        errors.append(f"KP {kp_id or i} tag_candidates[{j}] 格式无效")
                        continue
                    if not str(cand.get("tag") or "").strip():
                        errors.append(f"KP {kp_id or i} tag_candidates[{j}] 缺少 tag")
                    src = cand.get("source")
                    if src is not None and str(src).strip().lower() not in (
                        "system",
                        "user",
                    ):
                        errors.append(
                            f"KP {kp_id or i} tag_candidates[{j}] source 无效"
                        )

        rng = kp.get("range") or {}
        start = rng.get("start") or {}
        end = rng.get("end") or {}
        if not start.get("snippet") or not end.get("snippet"):
            missing = []
            if not start.get("snippet"):
                missing.append("start")
            if not end.get("snippet"):
                missing.append("end")
            errors.append(
                f"KP {kp_id or i} range 缺少 {'/'.join(missing)} snippet"
            )
            continue

        if lines:
            rr = resolve_range(lines, start, end)
            if not rr.get("ok"):
                warnings.append(f"KP {kp_id}: range 无法重定位 ({rr.get('error')})")
            else:
                sl, el = rr.get("start_line"), rr.get("end_line")
                if sl and el and sl > el:
                    errors.append(f"KP {kp_id}: 起点行晚于终点行")

    edges = data.get("edges")
    if edges is not None:
        if not isinstance(edges, list):
            errors.append("edges 必须为列表")
        else:
            local_ids = seen_ids
            for i, edge in enumerate(edges):
                if not isinstance(edge, dict):
                    errors.append(f"edges[{i}] 格式无效")
                    continue
                raw_type = edge.get("type")
                edge_type = normalize_edge_type(str(raw_type) if raw_type is not None else None)
                if not edge_type:
                    errors.append(f"edges[{i}] 无效 type: {raw_type!r}（允许: {', '.join(sorted(EDGE_TYPES))}）")
                    continue
                if raw_type != edge_type and str(raw_type).strip().lower() not in EDGE_TYPES:
                    warnings.append(f"edges[{i}] type {raw_type!r} 将归一化为 {edge_type}")

                source_id = edge.get("source_id")
                if not source_id or not str(source_id).strip():
                    errors.append(f"edges[{i}] 缺少 source_id")
                else:
                    sid = str(source_id).strip()
                    if sid not in local_ids:
                        warnings.append(f"edges[{i}] source_id {sid!r} 不在本文件 KP 列表中")
                    if known_kp_ids is not None and sid not in known_kp_ids:
                        errors.append(f"edges[{i}] source_id 不存在: {sid}")

                targets = _normalize_edge_targets(edge.get("targets"))
                if edge_type != "reference" and not targets:
                    warnings.append(f"edges[{i}] ({edge_type}) targets 为空")
                for tid in targets:
                    if known_kp_ids is not None and tid not in known_kp_ids:
                        errors.append(f"edges[{i}] target 不存在: {tid}")

                rel = edge.get("relevance")
                if rel is not None:
                    try:
                        rv = float(rel)
                        if rv < 0 or rv > 1:
                            errors.append(f"edges[{i}] relevance 须在 0～1 之间")
                    except (TypeError, ValueError):
                        errors.append(f"edges[{i}] relevance 无效")

    links = data.get("links")
    if links is not None:
        if not isinstance(links, list):
            errors.append("links 必须为列表")
        else:
            for i, link in enumerate(links):
                if not isinstance(link, dict):
                    errors.append(f"links[{i}] 格式无效")
                    continue
                anchor = link.get("anchor_text")
                if not anchor or not str(anchor).strip():
                    errors.append(f"links[{i}] 缺少 anchor_text")
                raw_edge_type = link.get("edge_type")
                if raw_edge_type is not None and str(raw_edge_type).strip():
                    normalized = normalize_edge_type(str(raw_edge_type))
                    if normalized not in (EDGE_REFERENCE, EDGE_EXTEND):
                        errors.append(
                            f"links[{i}] edge_type 无效: {raw_edge_type!r}"
                            f"（允许: {EDGE_REFERENCE}, {EDGE_EXTEND}）"
                        )
                targets = _normalize_edge_targets(link.get("targets"))
                if not targets:
                    warnings.append(f"links[{i}] 未绑定跳转目标（不参与图谱建边）")
                for tid in targets:
                    if known_kp_ids is not None and tid not in known_kp_ids:
                        errors.append(f"links[{i}] target 不存在: {tid}")
                instances = link.get("instances")
                if instances is not None and not isinstance(instances, list):
                    errors.append(f"links[{i}] instances 必须为列表")
                rel = link.get("relevance")
                if rel is not None:
                    try:
                        rv = float(rel)
                        if rv < 0 or rv > 1:
                            errors.append(f"links[{i}] relevance 须在 0～1 之间")
                    except (TypeError, ValueError):
                        errors.append(f"links[{i}] relevance 无效")
                    else:
                        warnings.append(
                            f"links[{i}] relevance 已弃用，请改用 target_edges"
                        )
                te = link.get("target_edges")
                if te is not None:
                    if not isinstance(te, dict):
                        errors.append(f"links[{i}] target_edges 必须为对象")
                    else:
                        for tid, props in te.items():
                            if not str(tid or "").strip():
                                errors.append(f"links[{i}] target_edges 含空 target id")
                                continue
                            if not isinstance(props, dict):
                                errors.append(
                                    f"links[{i}] target_edges[{tid!r}] 必须为对象"
                                )
                                continue
                            pet = props.get("edge_type")
                            if pet is not None and str(pet).strip():
                                normalized = normalize_edge_type(str(pet))
                                if normalized not in (EDGE_REFERENCE, EDGE_EXTEND):
                                    errors.append(
                                        f"links[{i}] target_edges[{tid!r}] edge_type 无效"
                                    )
                            prel = props.get("relevance")
                            if prel is not None:
                                try:
                                    prv = float(prel)
                                    if prv < 0 or prv > 1:
                                        errors.append(
                                            f"links[{i}] target_edges[{tid!r}] relevance 须在 0～1"
                                        )
                                except (TypeError, ValueError):
                                    errors.append(
                                        f"links[{i}] target_edges[{tid!r}] relevance 无效"
                                    )

    return {"ok": not errors, "errors": errors, "warnings": warnings}
