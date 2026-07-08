"""知识库级完整性校验（M3 L3/L4）。"""

from __future__ import annotations

import os
from pathlib import Path

from memoria.services.kp_index import build_kp_index
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import collect_sidecar_md_rels, load_sidecar, sidecar_path_for

CODE_DUPLICATE_KP_ID = "duplicate_kp_id_global"
CODE_ORPHAN_MD = "orphan_md"
CODE_ORPHAN_SIDECAR = "orphan_sidecar"


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _issue(code: str, message: str, *, severity: str, paths: list[str] | None = None) -> dict:
    row: dict = {"code": code, "message": message, "severity": severity}
    if paths:
        row["paths"] = paths
    return row


def audit_kb_integrity(kb_path: str) -> dict:
    """全库级检查：跨文件重复 id、orphan md/sidecar。"""
    kb = str(kb_path)
    md_rels = {_norm(p) for p in collect_md_files(kb)}
    sidecar_rels = {_norm(p) for p in collect_sidecar_md_rels(kb)}

    errors: list[dict] = []
    warnings: list[dict] = []

    index = build_kp_index(kb)
    for kp_id, entries in index["by_id"].items():
        if len(entries) <= 1:
            continue
        paths = sorted({e.file for e in entries})
        errors.append(
            _issue(
                CODE_DUPLICATE_KP_ID,
                f"知识点 id「{kp_id}」在 {len(paths)} 个文件中重复",
                severity="error",
                paths=paths,
            )
        )

    orphan_md = sorted(md_rels - sidecar_rels)
    for rel in orphan_md:
        warnings.append(
            _issue(
                CODE_ORPHAN_MD,
                f"文档缺少元数据配置：{rel}",
                severity="warning",
                paths=[rel],
            )
        )

    orphan_sc = sorted(sidecar_rels - md_rels)
    for rel in orphan_sc:
        sc_path = sidecar_path_for(os.path.join(kb, rel), kb)
        sidecar = load_sidecar(sc_path)
        file_field = (sidecar or {}).get("file")
        warnings.append(
            _issue(
                CODE_ORPHAN_SIDECAR,
                f"配置文件找不到对应文档：{rel}"
                + (f"（file: {file_field}）" if file_field else ""),
                severity="warning",
                paths=[rel],
            )
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "error_count": len(errors),
            "warning_count": len(warnings),
            "md_count": len(md_rels),
            "sidecar_count": len(sidecar_rels),
        },
    }
