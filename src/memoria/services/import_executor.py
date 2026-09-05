"""0.3.0 统一导入执行器（import-spec §6/§9）。

把 import_plan 的预览 + 用户 decisions（skip / overwrite / rename:<新名>，
subject = rel_path 或 kp_id）应用到三源：写 .md、建 sidecar、图谱同步。
幂等：unchanged 文件直接跳过；失败逐项收集 → status partial。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from memoria.graph.kb_build import build_knowledge_base
from memoria.services.import_engine import (
    _apply_renames_to_body,
    _apply_renames_to_frontmatter,
    _normalize_import_path,
    auto_generate_sidecar,
    parse_flat_file,
)
from memoria.services.import_plan import (
    FLAT_FILE,
    KB_BUNDLE,
    MD_DIR,
    _bundle_sidecar_for,
    _split_frontmatter,
    expand_md_source_pairs,
)
from memoria.storage.markdown import compose_markdown
from memoria.storage.sidecar import save_sidecar_for_md, sidecar_path_for


@dataclass
class ImportExecuteResult:
    status: str = "ok"
    files_written: int = 0
    files_unchanged: int = 0
    files_skipped: int = 0
    files_renamed: int = 0
    files_overwritten: int = 0
    sidecars_written: int = 0
    kp_imported: int = 0
    kp_skipped: int = 0
    kp_renamed: int = 0
    kp_overwritten: int = 0
    errors: list[str] = field(default_factory=list)
    build_report: dict | None = None


# ── 决策解析 ─────────────────────────────────────────────────────────


def _decision(decisions: dict | None, subject: str) -> str:
    value = (decisions or {}).get(subject, "")
    return str(value or "").strip()


def _is_skip(decision: str) -> bool:
    return decision == "skip"


def _rename_target(decision: str) -> str | None:
    return decision[len("rename:") :].strip() if decision.startswith("rename:") else None


# ── 源读取（与 import_plan 视角一致，独立重建内容以便写盘） ──────────


@dataclass
class _SourceItem:
    rel_path: str
    content: str
    kp_ids: list[str] = field(default_factory=list)
    concepts: list[dict] = field(default_factory=list)  # frontmatter concepts 声明
    bundle_sidecar: dict | None = None  # kb_bundle 源的 sidecar 原文
    plain_file: bool = False  # md_dir 纯文件（无 concepts）
    range_scan: bool = False  # flat：按 body 标题自动生成 KP range


def _flat_items(sources: list[dict]) -> list[_SourceItem]:
    items: list[_SourceItem] = []
    for src in sources:
        for section in parse_flat_file(src.get("content") or "", source_name=src.get("name") or ""):
            concepts = [c for c in (section.frontmatter.get("concepts") or []) if isinstance(c, dict)]
            active = [c for c in concepts if c.get("id")]
            if not active:
                continue
            rel_dir = ""
            try:
                rel_dir = _normalize_import_path(section.frontmatter.get("path") or "")
            except ValueError:
                rel_dir = ""
            rel = f"{rel_dir}/{active[0].get('id')}.md" if rel_dir else f"{active[0].get('id')}.md"
            out_fm = {k: v for k, v in section.frontmatter.items() if k != "path"}
            items.append(
                _SourceItem(
                    rel_path=rel,
                    content=compose_markdown(section.body, out_fm),
                    kp_ids=[c.get("id") for c in active],
                    concepts=active,
                    range_scan=True,
                )
            )
    return items


def _md_items(sources: list[dict]) -> list[_SourceItem]:
    items: list[_SourceItem] = []
    for abs_path, rel_path in expand_md_source_pairs(sources):
        p = Path(abs_path)
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise FileNotFoundError(f"{p}: {exc}") from exc
        fm, _body = _split_frontmatter(raw)
        concepts = [c for c in (fm.get("concepts") or []) if isinstance(c, dict) and c.get("id")]
        items.append(
            _SourceItem(
                rel_path=rel_path,
                content=raw,
                kp_ids=[c.get("id") for c in concepts],
                concepts=concepts,
                plain_file=not concepts,
            )
        )
    return items


def _bundle_items(sources: list[dict]) -> list[_SourceItem]:
    items: list[_SourceItem] = []
    for src in sources:
        root = Path(src["path"])
        if not root.is_dir():
            raise FileNotFoundError(f"{root}: 不是目录")
        sidecar_dir = root / ".memoria" / "sidecars"
        for md in sorted(root.rglob("*.md")):
            if ".memoria" in md.parts:
                continue
            rel = md.relative_to(root).as_posix()
            try:
                raw = md.read_text(encoding="utf-8")
            except OSError as exc:
                raise FileNotFoundError(f"{md}: {exc}") from exc
            sc = _bundle_sidecar_for(sidecar_dir, rel)
            kp_ids = [str(k.get("id") or "") for k in ((sc or {}).get("knowledge_points") or []) if k.get("id")]
            items.append(
                _SourceItem(
                    rel_path=rel,
                    content=raw,
                    kp_ids=kp_ids,
                    bundle_sidecar=sc,
                )
            )
    return items


_ITEM_BUILDERS = {
    FLAT_FILE: _flat_items,
    MD_DIR: _md_items,
    KB_BUNDLE: _bundle_items,
}


# ── sidecar 内容构造 ────────────────────────────────────────────────


def _sidecar_for_item(
    item: _SourceItem,
    rel_path: str,
    rename_map: dict[str, str],
    skip_ids: set[str],
) -> dict | None:
    """构造落库 sidecar：bundle→改写包侧车；flat→按标题自动 range；md(concepts)→无 range KP。"""
    if item.bundle_sidecar is not None:
        return _rewrite_bundle_sidecar(item.bundle_sidecar, rel_path, rename_map)
    if item.plain_file or not item.concepts:
        return None
    concepts: list[dict] = []
    for concept in item.concepts:
        kid = str(concept.get("id") or "")
        if kid in skip_ids:
            continue
        c = dict(concept)
        if kid in rename_map:
            c["id"] = rename_map[kid]
        concepts.append(c)
    if not concepts:
        return None
    if item.range_scan:
        # flat：正文经过重命名改写，需用最终正文扫描标题生成 range
        body = _split_frontmatter(item.content)[1] if item.content.startswith("---") else item.content
        return auto_generate_sidecar(rel_path, body, concepts)
    kps = []
    for c in concepts:
        entry = {"id": str(c.get("id")), "name": str(c.get("name") or c.get("id"))}
        if c.get("weight") is not None:
            entry["weight"] = c["weight"]
        if c.get("tags") is not None:
            entry["tags"] = c["tags"]
        kps.append(entry)
    return {
        "schema_version": 1,
        "file": rel_path,
        "knowledge_points": kps,
        "links": [],
        "edges": [],
    }


def _rewrite_bundle_sidecar(sc: dict, rel_path: str, rename_map: dict[str, str]) -> dict:
    out = dict(sc)
    out["file"] = rel_path
    kps = []
    for kp in sc.get("knowledge_points") or []:
        k = dict(kp)
        old = str(k.get("id") or "")
        if old in rename_map:
            k["id"] = rename_map[old]
        kps.append(k)
    out["knowledge_points"] = kps
    # links/edges 涉及 id 的目标一并改写（key 语义保持与库内一致）
    links = []
    for link in sc.get("links") or []:
        l = dict(link)
        tgt = l.get("target")
        if isinstance(tgt, str) and tgt in rename_map:
            l["target"] = rename_map[tgt]
        links.append(l)
    out["links"] = links
    edges = []
    for edge in sc.get("edges") or []:
        e = dict(edge)
        for key in ("source_id", "target_id"):
            val = e.get(key)
            if isinstance(val, str) and val in rename_map:
                e[key] = rename_map[val]
        edges.append(e)
    out["edges"] = edges
    return out


# ── 主入口 ──────────────────────────────────────────────────────────


def execute_import(
    kind: str,
    sources: list[dict],
    kb_path: str,
    decisions: dict | None = None,
) -> ImportExecuteResult:
    result = ImportExecuteResult()
    decisions = decisions or {}
    if kind not in _ITEM_BUILDERS:
        result.status = "error"
        result.errors.append(f"不支持的导入源 kind={kind!r}")
        return result

    os.makedirs(kb_path, exist_ok=True)
    (Path(kb_path) / ".memoria" / "sidecars").mkdir(parents=True, exist_ok=True)

    try:
        items = _ITEM_BUILDERS[kind](sources)
    except (OSError, FileNotFoundError) as exc:
        result.status = "error"
        result.errors.append(str(exc))
        return result

    for item in items:
        try:
            _apply_item(item, kb_path, decisions, result)
        except Exception as exc:  # noqa: BLE001 单文件失败不阻断整体
            result.errors.append(f"{item.rel_path}: {exc}")

    try:
        result.build_report = build_knowledge_base(kb_path)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"构建知识库失败: {exc}")

    if result.errors:
        result.status = "partial"
    return result


def _apply_item(
    item: _SourceItem,
    kb_path: str,
    decisions: dict,
    result: ImportExecuteResult,
) -> None:
    # 1) 文件级决策
    file_decision = _decision(decisions, item.rel_path)
    if _is_skip(file_decision):
        result.files_skipped += 1
        result.kp_skipped += len(item.kp_ids)
        return
    new_rel = _rename_target(file_decision)

    # 2) KP 级决策（subject=kp_id）
    skip_ids: set[str] = set()
    rename_map: dict[str, str] = {}
    for kid in item.kp_ids:
        d = _decision(decisions, kid)
        if _is_skip(d):
            skip_ids.add(kid)
        elif _rename_target(d):
            rename_map[kid] = _rename_target(d)
    active = [k for k in item.kp_ids if k not in skip_ids]
    if not active and item.kp_ids:
        result.files_skipped += 1
        result.kp_skipped += len(item.kp_ids)
        return

    # 3) 目标文件
    rel_path = new_rel or item.rel_path
    content = item.content

    if rename_map:
        # 平面/md 的 frontmatter concepts 与 body [[]]；bundle 侧写 sidecar 处统一改写
        if item.bundle_sidecar is None and not item.plain_file:
            fm, body = _split_frontmatter(content)
            if fm.get("concepts") is not None or item.concepts:
                new_fm = _apply_renames_to_frontmatter(fm, rename_map)
                new_body = _apply_renames_to_body(body, rename_map)
                content = compose_markdown(new_body, new_fm)
        else:
            content = _apply_renames_to_body(content, rename_map)

    wrote = _write_md(kb_path, rel_path, content, result)

    sidecar = _sidecar_for_item(item, rel_path, rename_map, skip_ids)
    md_path = os.path.join(kb_path, rel_path)
    sidecar_missing = not os.path.isfile(sidecar_path_for(md_path, kb_path))
    materialized = False
    if sidecar is not None and (wrote or sidecar_missing):
        save_sidecar_for_md(md_path, kb_path, sidecar)
        result.sidecars_written += 1
        materialized = True
    elif wrote:
        materialized = True
    if materialized:
        # KP 计数按决策归类：覆盖→kp_overwritten、重命名→kp_renamed、
        # 部分跳过→kp_skipped、无决策（新导入）→kp_imported
        for kid in item.kp_ids:
            if kid in skip_ids:
                result.kp_skipped += 1
                continue
            d = _decision(decisions, kid)
            if d == "overwrite":
                result.kp_overwritten += 1
            elif _rename_target(d):
                result.kp_renamed += 1
            else:
                result.kp_imported += 1
    if new_rel:
        result.files_renamed += 1


def _write_md(kb_path: str, rel_path: str, content: str, result: ImportExecuteResult) -> bool:
    """写入 md；返回是否实际写入（False = 内容未变化）。"""
    target = Path(kb_path) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and target.read_text(encoding="utf-8") == content:
        result.files_unchanged += 1
        return False
    existed = target.is_file()
    target.write_text(content, encoding="utf-8")
    result.files_written += 1
    if existed:
        result.files_overwritten += 1
    return True
