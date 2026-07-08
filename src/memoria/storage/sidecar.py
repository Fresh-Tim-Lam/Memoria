"""侧车 .memoria.yaml 读写与路径解析。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from memoria.storage.atomic_yaml import atomic_write_yaml
from memoria.storage.constants import MEMORIA_DIR, SIDECARS_DIR, SIDECAR_SUFFIX


def _normalize_range_endpoint(ep: object) -> dict:
    """修复 YAML 折行/[[…]] 导致的 snippet 丢失或错位。"""
    if not isinstance(ep, dict):
        return {}
    out = dict(ep)
    snip = out.get("snippet")
    if isinstance(snip, str) and snip.strip():
        out["snippet"] = snip.strip()
        return out
    if snip is not None and not isinstance(snip, str):
        out["snippet"] = str(snip).strip()
        return out
    parts: list[str] = []
    for key, val in list(out.items()):
        if key == "line_hint":
            continue
        if key == "snippet":
            continue
        if val is None or val == "":
            parts.append(str(key).strip())
            del out[key]
    if parts:
        prefix = str(snip).strip() if isinstance(snip, str) else ""
        merged = " ".join(p for p in [prefix, *parts] if p)
        out["snippet"] = merged
    return out


def normalize_sidecar_data(data: dict | None) -> dict | None:
    if not data or not isinstance(data, dict):
        return data
    out = dict(data)
    kps = out.get("knowledge_points")
    if not isinstance(kps, list):
        return out
    fixed_kps: list = []
    for kp in kps:
        if not isinstance(kp, dict):
            fixed_kps.append(kp)
            continue
        kp = dict(kp)
        rng = kp.get("range")
        if isinstance(rng, dict):
            rng = dict(rng)
            rng["start"] = _normalize_range_endpoint(rng.get("start"))
            rng["end"] = _normalize_range_endpoint(rng.get("end"))
            kp["range"] = rng
        fixed_kps.append(kp)
    out["knowledge_points"] = fixed_kps
    return out


def _md_stem_rel(md_path: Path, kb_root: Path) -> Path:
    """md 相对知识库的路径 stem → sidecar 相对 sidecars/ 的路径。"""
    try:
        rel = md_path.resolve().relative_to(kb_root.resolve())
    except ValueError:
        rel = Path(md_path.name)
    return rel.with_suffix(SIDECAR_SUFFIX)


def sidecar_path_for(md_path: str | Path, kb_root: str | Path | None = None) -> str:
    """侧车路径：{kb}/.memoria/sidecars/{mirror_rel}.memoria.yaml"""
    md = Path(md_path)
    if kb_root:
        kb = Path(kb_root)
        rel = _md_stem_rel(md, kb)
        return str(kb / MEMORIA_DIR / SIDECARS_DIR / rel)
    return str(md.with_suffix(SIDECAR_SUFFIX))


def legacy_sidecar_path_for(md_path: str | Path) -> str:
    """旧版：与 md 同目录 `<stem>.memoria.yaml`（只读兼容）。"""
    return str(Path(md_path).with_suffix(SIDECAR_SUFFIX))


def resolve_sidecar_path(md_path: str | Path, kb_root: str | Path | None = None) -> str:
    """读取时：优先 .memoria/sidecars/，回退同目录旧路径；写入用 canonical。"""
    canonical = sidecar_path_for(md_path, kb_root)
    if os.path.isfile(canonical):
        return canonical
    legacy = legacy_sidecar_path_for(md_path)
    if os.path.isfile(legacy):
        return legacy
    return canonical


def load_sidecar(path: str | Path) -> dict | None:
    path = str(path)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return None
    return normalize_sidecar_data(data)


def load_sidecar_for_md(md_path: str | Path, kb_root: str | Path | None = None) -> dict | None:
    return load_sidecar(resolve_sidecar_path(md_path, kb_root))


def save_sidecar(path: str | Path, data: dict) -> None:
    atomic_write_yaml(path, data)


def save_sidecar_for_md(md_path: str | Path, kb_root: str | Path, data: dict) -> str:
    path = sidecar_path_for(md_path, kb_root)
    save_sidecar(path, data)
    return path


def collect_sidecar_md_rels(kb_root: str) -> list[str]:
    """`.memoria/sidecars/` 下侧车对应的 md 相对路径。"""
    root = Path(kb_root) / MEMORIA_DIR / SIDECARS_DIR
    if not root.is_dir():
        return []
    out: list[str] = []
    for path in root.rglob(f"*{SIDECAR_SUFFIX}"):
        rel_sc = path.relative_to(root)
        name = str(rel_sc).replace("\\", "/")
        if not name.endswith(SIDECAR_SUFFIX):
            continue
        stem = name[: -len(SIDECAR_SUFFIX)]
        md_rel = stem if stem.endswith(".md") else f"{stem}.md"
        out.append(md_rel)
    return sorted(out)
