"""KP 级提议：sidecar 候选 ↔ search_aux 隐式内容同步（v1.5b）。"""

from __future__ import annotations

from typing import Any

from memoria.services.search_aux import generate_aux_for_kp, load_kp_aux, rebuild_search_aux
from memoria.storage.markdown import strip_frontmatter
from memoria.storage.sidecar import load_sidecar_for_md


def merge_aux_into_kp_proposals(
    *,
    kb_path: str,
    rel_path: str,
    kp: dict,
    lines: list[str],
    aux: dict[str, Any] | None = None,
) -> dict[str, list[dict]]:
    """从 aux 生成可并入 sidecar 候选区的条目（不写盘）。"""
    if aux is None:
        aux = load_kp_aux(kb_path, str(kp.get("id") or ""))
        if aux is None:
            aux = generate_aux_for_kp(
                kb_path=kb_path,
                rel_path=rel_path,
                kp=kp,
                lines=lines,
            )

    selected_tags = {str(t).strip().lower() for t in (kp.get("tags") or []) if str(t).strip()}
    selected_aliases = {
        str(a).strip().lower() for a in (kp.get("aliases") or []) if str(a).strip()
    }
    current_desc = str(kp.get("description") or "").strip()

    tag_rows = [
        {"tag": t, "source": "system", "status": "candidate"}
        for t in (aux.get("auto_tags") or [])
        if str(t).strip() and str(t).lower() not in selected_tags
    ]
    alias_rows = [
        {"alias": a, "source": "system", "status": "candidate"}
        for a in (aux.get("aliases") or [])
        if str(a).strip() and str(a).lower() not in selected_aliases
    ]
    desc_rows: list[dict] = []
    summary = str(aux.get("summary_1l") or "").strip()
    if summary and summary != current_desc:
        desc_rows.append({"text": summary, "source": "system", "status": "candidate"})

    return {
        "tag_candidates": tag_rows,
        "alias_candidates": alias_rows,
        "description_candidates": desc_rows,
    }


def sync_kp_implicit_proposals(
    *,
    kb_path: str,
    rel_path: str,
    kp_id: str,
    rebuild: bool = True,
    temp_kp: dict | None = None,
) -> dict:
    """读取 aux，返回与现有 sidecar 候选合并后的提议（供 UI 展示）。

    temp_kp 用于创建模式下 kp 尚未保存的场景：跳过 sidecar/aux 查找，
    直接基于 temp_kp 的 range 从文件内容生成建议。
    """
    kid = (kp_id or "").strip()
    if not kb_path or not kid:
        return {"status": "error", "message": "缺少 kb 或 kp_id", "available": False}

    if rebuild and not temp_kp:
        try:
            rebuild_search_aux(kb_path)
        except OSError:
            pass

    full = __import__("os").path.join(kb_path, rel_path.replace("\\", "/"))
    sidecar = load_sidecar_for_md(full, kb_path) or {}
    kp = next(
        (k for k in (sidecar.get("knowledge_points") or []) if k.get("id") == kid),
        None,
    )

    if not kp:
        if not temp_kp:
            return {"status": "error", "message": f"知识点不存在：{kid}", "available": False}
        start_line = int(temp_kp.get("start_line") or 1)
        end_line = int(temp_kp.get("end_line") or start_line)
        kp = {
            "id": kid,
            "name": str(temp_kp.get("name") or ""),
            "range": {
                "start": {"line_hint": start_line},
                "end": {"line_hint": end_line},
            },
            "tags": [],
            "aliases": [],
            "description": "",
            "tag_candidates": [],
            "alias_candidates": [],
            "description_candidates": [],
        }

    try:
        with open(full, encoding="utf-8") as f:
            body, _ = strip_frontmatter(f.read())
        lines = body.splitlines()
    except OSError:
        lines = []

    aux = None if temp_kp else load_kp_aux(kb_path, kid)
    fresh = merge_aux_into_kp_proposals(
        kb_path=kb_path,
        rel_path=rel_path.replace("\\", "/"),
        kp=kp,
        lines=lines,
        aux=aux,
    )

    def _merge_candidates(existing_raw, fresh_rows, normalizer, key_field):
        existing = normalizer(existing_raw)
        dismissed = {
            str(x.get(key_field) or "").strip().lower()
            for x in existing
            if str(x.get("status") or "") == "dismissed"
        }
        have = {str(x.get(key_field) or "").strip().lower() for x in existing}
        merged = list(existing)
        for row in fresh_rows:
            val = str(row.get(key_field) or "").strip()
            if not val:
                continue
            kl = val.lower()
            if kl in dismissed or kl in have:
                continue
            merged.append(row)
            have.add(kl)
        return merged

    from memoria.services.document import (
        _normalize_alias_candidates,
        _normalize_description_candidates,
        _normalize_tag_candidates,
    )

    tag_merged = _merge_candidates(
        kp.get("tag_candidates"),
        fresh["tag_candidates"],
        _normalize_tag_candidates,
        "tag",
    )
    alias_merged = _merge_candidates(
        kp.get("alias_candidates"),
        fresh["alias_candidates"],
        _normalize_alias_candidates,
        "alias",
    )
    desc_merged = _merge_candidates(
        kp.get("description_candidates"),
        fresh["description_candidates"],
        _normalize_description_candidates,
        "text",
    )

    return {
        "status": "ok",
        "available": True,
        "kp_id": kid,
        "file": rel_path.replace("\\", "/"),
        "aux_present": aux is not None,
        "tag_candidates": tag_merged,
        "alias_candidates": alias_merged,
        "description_candidates": desc_merged,
    }
