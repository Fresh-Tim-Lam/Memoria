"""侧车 M0 校验：写入前拒绝、加载时报告 warnings。"""

from __future__ import annotations

from memoria.graph.edge_types import EDGE_EXTEND, EDGE_REFERENCE, EDGE_TYPES, normalize_edge_type
from memoria.range.locator import resolve_range
from memoria.storage.constants import SIDECAR_SCHEMA_VERSION


def _norm_path(p: str) -> str:
    return p.replace("\\", "/")


def _link_first_line(link: dict, lines: list[str] | None) -> int | None:
    """计算链接在正文中第一次出现的行号（1-based）。

    优先级：
    1. ``link.instances`` 中最小的行号
    2. 扫描正文 ``lines`` 查找 ``anchor_text`` 第一次出现的行
    3. 都找不到返回 ``None``
    """
    instances = link.get("instances") if isinstance(link, dict) else None
    if isinstance(instances, list):
        inst_lines: list[int] = []
        for inst in instances:
            if isinstance(inst, dict) and inst.get("line"):
                try:
                    inst_lines.append(int(inst["line"]))
                except (TypeError, ValueError):
                    pass
        if inst_lines:
            return min(inst_lines)
    if not lines:
        return None
    anchor = str(link.get("anchor_text") or "").strip() if isinstance(link, dict) else ""
    if not anchor:
        return None
    for i, row in enumerate(lines):
        if anchor in row:
            return i + 1
    return None


def _normalize_edge_targets(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if isinstance(t, str) and str(t).strip()]
    return []


def _validate_candidate_list(
    raw: object,
    *,
    kp_id: str,
    field_name: str,
    value_key: str,
    errors: list[dict],
    allowed_sources: frozenset[str],
) -> None:
    if raw is None:
        return
    if not isinstance(raw, list):
        errors.append({"message": f"KP {kp_id} {field_name} 必须为列表", "kp_id": kp_id, "kind": "kp"})
        return
    for j, cand in enumerate(raw):
        if not isinstance(cand, dict):
            errors.append({"message": f"KP {kp_id} {field_name}[{j}] 格式无效", "kp_id": kp_id, "kind": "kp"})
            continue
        if not str(cand.get(value_key) or "").strip():
            errors.append({"message": f"KP {kp_id} {field_name}[{j}] 缺少 {value_key}", "kp_id": kp_id, "kind": "kp"})
        src = str(cand.get("source") or "user").strip().lower()
        if src not in allowed_sources:
            errors.append({"message": f"KP {kp_id} {field_name}[{j}] source 无效", "kp_id": kp_id, "kind": "kp"})
        status = cand.get("status")
        if status is not None and str(status).strip().lower() not in (
            "candidate",
            "selected",
            "dismissed",
        ):
            errors.append({"message": f"KP {kp_id} {field_name}[{j}] status 无效", "kp_id": kp_id, "kind": "kp"})


def validate_sidecar(
    data: dict | None,
    rel_path: str,
    lines: list[str] | None = None,
    known_kp_ids: set[str] | None = None,
) -> dict:
    """返回 {ok, errors[], warnings[]}。

    errors/warnings 中每个元素是 ``{message, kp_id?, line?, kind?}``：
    - ``kp_id``：知识点 id（仅知识点相关问题）
    - ``line``：相关行号（1-based，用于前端跳转定位）
    - ``kind``：``"kp"`` / ``"link"`` / ``"edge"`` / ``"file"``
    """

    def issue(msg: str, *, kp_id: str | None = None, line: int | None = None, kind: str | None = None) -> dict:
        d: dict = {"message": msg}
        if kp_id:
            d["kp_id"] = kp_id
        if line is not None:
            d["line"] = line
        if kind:
            d["kind"] = kind
        return d

    errors: list[dict] = []
    warnings: list[dict] = []

    if not data:
        return {"ok": True, "errors": [], "warnings": []}

    if not isinstance(data, dict):
        return {"ok": False, "errors": [issue("配置文件格式无效", kind="file")], "warnings": []}

    ver = data.get("schema_version")
    if ver is None:
        warnings.append(issue("缺少 schema_version，将按 1 处理", kind="file"))
    elif ver != SIDECAR_SCHEMA_VERSION:
        errors.append(issue(f"不支持的 schema_version: {ver}", kind="file"))

    file_field = data.get("file")
    if file_field and _norm_path(str(file_field)) != _norm_path(rel_path):
        warnings.append(issue(f"配置中的 file 路径 ({file_field}) 与文件位置 ({rel_path}) 不一致", kind="file"))

    kps = data.get("knowledge_points")
    if kps is None:
        warnings.append(issue("缺少 knowledge_points", kind="file"))
        kps = []
    elif not isinstance(kps, list):
        errors.append(issue("knowledge_points 必须为列表", kind="file"))
        kps = []

    seen_ids: set[str] = set()
    for i, kp in enumerate(kps):
        if not isinstance(kp, dict):
            errors.append(issue(f"knowledge_points[{i}] 格式无效", kind="kp"))
            continue
        kp_id = kp.get("id")
        if not kp_id:
            errors.append(issue(f"knowledge_points[{i}] 缺少 id", kind="kp"))
        elif kp_id in seen_ids:
            errors.append(issue(f"重复的知识点 id: {kp_id}", kp_id=str(kp_id), kind="kp"))
        else:
            seen_ids.add(kp_id)

        if not kp.get("name"):
            warnings.append(issue(f"KP {kp_id or i} 缺少 name", kp_id=str(kp_id) if kp_id else None, kind="kp"))

        tags = kp.get("tags")
        if tags is not None:
            if not isinstance(tags, list):
                errors.append(issue(f"KP {kp_id or i} tags 必须为列表", kp_id=str(kp_id) if kp_id else None, kind="kp"))
            else:
                for j, tag in enumerate(tags):
                    if not isinstance(tag, str) or not str(tag).strip():
                        errors.append(issue(f"KP {kp_id or i} tags[{j}] 无效", kp_id=str(kp_id) if kp_id else None, kind="kp"))

        aliases = kp.get("aliases")
        if aliases is not None:
            if not isinstance(aliases, list):
                errors.append(issue(f"KP {kp_id or i} aliases 必须为列表", kp_id=str(kp_id) if kp_id else None, kind="kp"))
            else:
                for j, alias in enumerate(aliases):
                    if not isinstance(alias, str) or not str(alias).strip():
                        errors.append(issue(f"KP {kp_id or i} aliases[{j}] 无效", kp_id=str(kp_id) if kp_id else None, kind="kp"))

        tc = kp.get("tag_candidates")
        if tc is not None:
            if not isinstance(tc, list):
                errors.append(issue(f"KP {kp_id or i} tag_candidates 必须为列表", kp_id=str(kp_id) if kp_id else None, kind="kp"))
            else:
                for j, cand in enumerate(tc):
                    if not isinstance(cand, dict):
                        errors.append(issue(f"KP {kp_id or i} tag_candidates[{j}] 格式无效", kp_id=str(kp_id) if kp_id else None, kind="kp"))
                        continue
                    if not str(cand.get("tag") or "").strip():
                        errors.append(issue(f"KP {kp_id or i} tag_candidates[{j}] 缺少 tag", kp_id=str(kp_id) if kp_id else None, kind="kp"))
                    src = cand.get("source")
                    if src is not None and str(src).strip().lower() not in (
                        "system",
                        "user",
                        "feedback",
                    ):
                        errors.append(
                            issue(f"KP {kp_id or i} tag_candidates[{j}] source 无效", kp_id=str(kp_id) if kp_id else None, kind="kp")
                        )

        _validate_candidate_list(
            kp.get("alias_candidates"),
            kp_id=str(kp_id or i),
            field_name="alias_candidates",
            value_key="alias",
            errors=errors,
            allowed_sources=frozenset({"system", "user", "feedback"}),
        )
        _validate_candidate_list(
            kp.get("description_candidates"),
            kp_id=str(kp_id or i),
            field_name="description_candidates",
            value_key="text",
            errors=errors,
            allowed_sources=frozenset({"system", "user", "feedback"}),
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
                issue(f"KP {kp_id or i} range 缺少 {'/'.join(missing)} snippet", kp_id=str(kp_id) if kp_id else None, kind="kp")
            )
            continue

        if lines:
            rr = resolve_range(lines, start, end)
            if not rr.get("ok"):
                warnings.append(issue(f"KP {kp_id}: range 无法重定位 ({rr.get('error')})", kp_id=str(kp_id), kind="kp"))
            else:
                sl, el = rr.get("start_line"), rr.get("end_line")
                if sl and el and sl > el:
                    errors.append(issue(f"KP {kp_id}: 起点行晚于终点行", kp_id=str(kp_id), line=sl, kind="kp"))

    edges = data.get("edges")
    if edges is not None:
        if not isinstance(edges, list):
            errors.append(issue("edges 必须为列表", kind="edge"))
        else:
            local_ids = seen_ids
            for i, edge in enumerate(edges):
                if not isinstance(edge, dict):
                    errors.append(issue(f"edges[{i}] 格式无效", kind="edge"))
                    continue
                raw_type = edge.get("type")
                edge_type = normalize_edge_type(str(raw_type) if raw_type is not None else None)
                if not edge_type:
                    errors.append(issue(f"edges[{i}] 无效 type: {raw_type!r}（允许: {', '.join(sorted(EDGE_TYPES))}）", kind="edge"))
                    continue
                if raw_type != edge_type and str(raw_type).strip().lower() not in EDGE_TYPES:
                    warnings.append(issue(f"edges[{i}] type {raw_type!r} 将归一化为 {edge_type}", kind="edge"))

                source_id = edge.get("source_id")
                if not source_id or not str(source_id).strip():
                    errors.append(issue(f"edges[{i}] 缺少 source_id", kind="edge"))
                else:
                    sid = str(source_id).strip()
                    if sid not in local_ids:
                        warnings.append(issue(f"edges[{i}] source_id {sid!r} 不在本文件 KP 列表中", kp_id=sid, kind="edge"))
                    if known_kp_ids is not None and sid not in known_kp_ids:
                        errors.append(issue(f"edges[{i}] source_id 不存在: {sid}", kp_id=sid, kind="edge"))

                targets = _normalize_edge_targets(edge.get("targets"))
                if edge_type != "reference" and not targets:
                    warnings.append(issue(f"edges[{i}] ({edge_type}) targets 为空", kind="edge"))
                for tid in targets:
                    if known_kp_ids is not None and tid not in known_kp_ids:
                        errors.append(issue(f"edges[{i}] target 不存在: {tid}", kp_id=tid, kind="edge"))

                rel = edge.get("relevance")
                if rel is not None:
                    try:
                        rv = float(rel)
                        if rv < 0 or rv > 1:
                            errors.append(issue(f"edges[{i}] relevance 须在 0～1 之间", kind="edge"))
                    except (TypeError, ValueError):
                        errors.append(issue(f"edges[{i}] relevance 无效", kind="edge"))

    links = data.get("links")
    if links is not None:
        if not isinstance(links, list):
            errors.append(issue("links 必须为列表", kind="link"))
        else:
            for i, link in enumerate(links):
                if not isinstance(link, dict):
                    errors.append(issue(f"links[{i}] 格式无效", kind="link"))
                    continue
                # 计算链接第一次出现的行号，用于前端跳转定位
                link_line = _link_first_line(link, lines)
                # 局部收集该 link 的问题，最后统一注入 line 字段
                link_errors: list[dict] = []
                link_warnings: list[dict] = []
                anchor = link.get("anchor_text")
                if not anchor or not str(anchor).strip():
                    link_errors.append(issue(f"links[{i}] 缺少 anchor_text", kind="link"))
                raw_edge_type = link.get("edge_type")
                if raw_edge_type is not None and str(raw_edge_type).strip():
                    normalized = normalize_edge_type(str(raw_edge_type))
                    if normalized not in (EDGE_REFERENCE, EDGE_EXTEND):
                        link_errors.append(
                            issue(f"links[{i}] edge_type 无效: {raw_edge_type!r}（允许: {EDGE_REFERENCE}, {EDGE_EXTEND}）", kind="link")
                        )
                targets = _normalize_edge_targets(link.get("targets"))
                if not targets:
                    link_warnings.append(issue(f"links[{i}] 未绑定跳转目标（不参与图谱建边）", kind="link"))
                for tid in targets:
                    if known_kp_ids is not None and tid not in known_kp_ids:
                        link_errors.append(issue(f"links[{i}] target 不存在: {tid}", kp_id=tid, kind="link"))
                instances = link.get("instances")
                if instances is not None and not isinstance(instances, list):
                    link_errors.append(issue(f"links[{i}] instances 必须为列表", kind="link"))
                rel = link.get("relevance")
                if rel is not None:
                    try:
                        rv = float(rel)
                        if rv < 0 or rv > 1:
                            link_errors.append(issue(f"links[{i}] relevance 须在 0～1 之间", kind="link"))
                    except (TypeError, ValueError):
                        link_errors.append(issue(f"links[{i}] relevance 无效", kind="link"))
                    else:
                        link_warnings.append(
                            issue(f"links[{i}] relevance 已弃用，请改用 target_edges", kind="link")
                        )
                te = link.get("target_edges")
                if te is not None:
                    if not isinstance(te, dict):
                        link_errors.append(issue(f"links[{i}] target_edges 必须为对象", kind="link"))
                    else:
                        for tid, props in te.items():
                            if not str(tid or "").strip():
                                link_errors.append(issue(f"links[{i}] target_edges 含空 target id", kind="link"))
                                continue
                            if not isinstance(props, dict):
                                link_errors.append(
                                    issue(f"links[{i}] target_edges[{tid!r}] 必须为对象", kind="link")
                                )
                                continue
                            pet = props.get("edge_type")
                            if pet is not None and str(pet).strip():
                                normalized = normalize_edge_type(str(pet))
                                if normalized not in (EDGE_REFERENCE, EDGE_EXTEND):
                                    link_errors.append(
                                        issue(f"links[{i}] target_edges[{tid!r}] edge_type 无效", kind="link")
                                    )
                            prel = props.get("relevance")
                            if prel is not None:
                                try:
                                    prv = float(prel)
                                    if prv < 0 or prv > 1:
                                        link_errors.append(
                                            issue(f"links[{i}] target_edges[{tid!r}] relevance 须在 0～1", kind="link")
                                        )
                                except (TypeError, ValueError):
                                    link_errors.append(
                                        issue(f"links[{i}] target_edges[{tid!r}] relevance 无效", kind="link")
                                    )
                # 统一注入 link_line（仅当 issue 自身未指定 line 时）
                if link_line is not None:
                    for d in link_errors:
                        d.setdefault("line", link_line)
                    for d in link_warnings:
                        d.setdefault("line", link_line)
                errors.extend(link_errors)
                warnings.extend(link_warnings)

    return {"ok": not errors, "errors": errors, "warnings": warnings}
