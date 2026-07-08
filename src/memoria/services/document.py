"""文档加载与侧车写入（M0 应用服务）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from memoria.range.constants import SNIPPET_MAX_LEN
from memoria.graph.edge_types import normalize_link_edge_type, normalize_link_relevance, normalize_target_edges
from memoria.services.check_report import summarize_check_counts
from memoria.services.kp_index import build_kp_index
from memoria.services.kp_resolver import resolve_knowledge_points
from memoria.services.link_instances import (
    add_excluded_lines,
    audit_link_consistency,
    build_preview_body,
    migrate_link_instances,
    scan_link_text_matches,
    sync_instances_from_selection,
    unwrap_lines,
    wrap_plain_on_lines,
)
from memoria.services.link_text_search import (
    LinkTextSearchOptions,
    line_matched_spans,
    resolve_canonical_anchor,
    suggest_link_anchor_texts,
)
from memoria.services.link_relevance import suggest_link_relevance
from memoria.services.link_md import (
    format_wikilink,
    remove_wikilink,
    remove_wikilink_on_line,
    update_wikilink,
    wrap_plain_text,
)
from memoria.services.link_resolver import (
    build_link_overrides,
    build_target_lookup,
    collect_link_alias_anchors,
    resolve_link_target,
    resolve_link_targets,
    wikilink_label,
)
from memoria.services.range_proposals import merge_range_proposals
from memoria.storage.constants import SIDECAR_SCHEMA_VERSION
from memoria.storage.markdown import compose_markdown, strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import load_sidecar_for_md, save_sidecar_for_md
from memoria.storage.manifest import (
    audit_manifest_diff,
    ensure_manifest_baseline,
    filter_manifest_diff_for_path_moves,
    rebuild_manifest,
    touch_manifest_entry,
)
from memoria.storage.path_cascade import detect_path_moves, reconcile_path_cascade
from memoria.storage.pending import (
    dismiss_pending_item,
    summarize_kb_pending,
    sync_kb_pending,
)
from memoria.storage.sidecar_validate import validate_sidecar
from memoria.storage.ui_settings import remember_last_kb_path


def _normalize_tag_candidates(
    raw: list | None,
    *,
    exclude: set[str] | None = None,
) -> list[dict]:
    """侧车 KP tag_candidates：未应用 tag 提议（system / user）。"""
    exclude = exclude or set()
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw or []:
        tag = ""
        source = "user"
        score = None
        if isinstance(item, str):
            tag = item.strip()
        elif isinstance(item, dict):
            tag = str(item.get("tag") or "").strip()
            src = str(item.get("source") or "user").strip().lower()
            source = "system" if src == "system" else "user"
            if item.get("score") is not None:
                try:
                    score = round(float(item["score"]), 1)
                except (TypeError, ValueError):
                    score = None
        else:
            continue
        if not tag:
            continue
        key = tag.lower()
        if key in exclude or key in seen:
            continue
        seen.add(key)
        cand: dict = {"tag": tag, "source": source}
        if score is not None:
            cand["score"] = score
        out.append(cand)
    return out


@dataclass
class DocumentService:
    kb_path: str | None = None
    _cache: dict[str, dict] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.kb_path:
            self.set_kb_path(self.kb_path)

    def set_kb_path(self, path: str) -> None:
        if not os.path.isdir(path):
            raise FileNotFoundError(f"目录不存在: {path}")
        self.kb_path = path
        self._cache.clear()
        remember_last_kb_path(path)
        ensure_manifest_baseline(path)
        sync_kb_pending(path)
        try:
            from memoria.services.embedding_provider import warmup_embedding

            warmup_embedding(path)
        except Exception:
            pass

    def _write_sidecar(self, rel_path: str, sidecar: dict) -> None:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        rel_norm = rel_path.replace("\\", "/")
        full = os.path.join(self.kb_path, rel_norm)
        save_sidecar_for_md(full, self.kb_path, sidecar)
        touch_manifest_entry(self.kb_path, rel_norm)
        self._rebuild_lexical_index()

    def close_kb(self) -> None:
        kb = self.kb_path
        self.kb_path = None
        self._cache.clear()
        remember_last_kb_path(None)
        if kb:
            try:
                from memoria.services.embedding_provider import reset_warmup_state

                reset_warmup_state(kb)
            except Exception:
                pass

    def list_files(self) -> list[dict]:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        items: list[dict] = []
        for rel in collect_md_files(self.kb_path):
            full = os.path.join(self.kb_path, rel)
            sc = load_sidecar_for_md(full, self.kb_path)
            items.append({
                "path": rel,
                "has_sidecar": sc is not None,
                "description": (sc or {}).get("description", ""),
            })
        return items

    def _read_body(self, rel_path: str) -> tuple[str, dict | None, list[str]]:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        full = os.path.join(self.kb_path, rel_path)
        if not os.path.isfile(full):
            raise FileNotFoundError("文件不存在")
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, fm = strip_frontmatter(raw)
        return body, fm, body.splitlines()

    def load_document(self, rel_path: str) -> dict:
        body, fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path)
        if sidecar and sidecar.get("links"):
            migrated = False
            new_links = []
            for link in sidecar["links"]:
                if isinstance(link, dict) and link.get("anchor_text"):
                    ml = migrate_link_instances(body, link, lines)
                    if ml != link:
                        migrated = True
                    new_links.append(ml)
                else:
                    new_links.append(link)
            if migrated:
                sidecar = dict(sidecar)
                sidecar["links"] = new_links
                validation = validate_sidecar(sidecar, rel_path.replace("\\", "/"), lines)
                if validation["ok"]:
                    self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        kps = resolve_knowledge_points(body, sidecar)
        from memoria.services.range_proposals import propose_all_ranges
        from memoria.storage.pending import is_proposal_covered

        heading_live, mention_live, definition_live, _ = propose_all_ranges(body, fm)
        heading_proposals = [
            p for p in heading_live if not is_proposal_covered(p, kps)
        ]
        mention_proposals = [
            p for p in mention_live if not is_proposal_covered(p, kps)
        ]
        definition_proposals = [
            p for p in definition_live if not is_proposal_covered(p, kps)
        ]
        range_proposals = merge_range_proposals(
            heading_proposals, mention_proposals, definition_proposals
        )
        sidecar_validation = validate_sidecar(sidecar, rel_path.replace("\\", "/"), lines)
        link_overrides = build_link_overrides(sidecar, body)
        target_lookup = build_target_lookup(self.kb_path)
        resolved_targets = set(target_lookup.get("resolved_targets") or [])
        link_audit = audit_link_consistency(
            body,
            (sidecar or {}).get("links") or [],
            lines,
            resolved_targets=resolved_targets,
        )
        from memoria.graph.edge_derivation import build_target_kp_resolver
        from memoria.graph.link_audit import audit_file_graph_links

        graph_link_audit = audit_file_graph_links(
            rel_path.replace("\\", "/"),
            body,
            sidecar,
            resolve_target_kp=build_target_kp_resolver(self.kb_path),
        )

        doc = {
            "status": "ok",
            "path": rel_path,
            "body": body,
            "preview_body": build_preview_body(
                body, (sidecar or {}).get("links") or [], lines
            ),
            "frontmatter": fm,
            "sidecar": sidecar,
            "knowledge_points": kps,
            "heading_proposals": heading_proposals,
            "mention_proposals": mention_proposals,
            "definition_proposals": definition_proposals,
            "range_proposals": range_proposals,
            "sidecar_validation": sidecar_validation,
            "link_overrides": link_overrides,
            "link_audit": link_audit,
            "graph_link_audit": graph_link_audit,
            "lines": lines,
        }
        self._cache[rel_path] = doc
        return doc

    def confirm_kp_range(
        self,
        rel_path: str,
        kp_id: str,
        name: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        body, fm, lines = self._read_body(rel_path)
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            return {"status": "error", "message": "行号无效"}

        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path) or {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "file": rel_path.replace("\\", "/"),
            "knowledge_points": [],
        }

        start_snip = lines[start_line - 1].strip()[:SNIPPET_MAX_LEN]
        end_snip = lines[end_line - 1].strip()[:SNIPPET_MAX_LEN]
        if not start_snip:
            return {
                "status": "error",
                "message": f"起点第 {start_line} 行为空，请选择有内容的行",
            }
        if not end_snip:
            return {
                "status": "error",
                "message": f"终点第 {end_line} 行为空，请选择有内容的行",
            }
        range_data = {
            "start": {"snippet": start_snip, "line_hint": start_line},
            "end": {"snippet": end_snip, "line_hint": end_line},
        }

        kps = sidecar.setdefault("knowledge_points", [])
        is_update = False
        for kp in kps:
            if kp.get("id") == kp_id:
                is_update = True
                kp["name"] = name
                kp["range"] = range_data
                break
        if not is_update:
            index = build_kp_index(self.kb_path)
            if kp_id in index["by_id"]:
                return {
                    "status": "error",
                    "message": f"目标 id 已存在：{kp_id}",
                }
            kps.append({"id": kp_id, "name": name, "range": range_data})

        if fm and fm.get("description") and not sidecar.get("description"):
            sidecar["description"] = fm["description"]

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(validation["errors"]),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        sync_kb_pending(self.kb_path)
        self._cache.pop(rel_path, None)
        return self.load_document(rel_path)

    def check_kp_id(self, kp_id: str, rel_path: str | None = None) -> dict:
        """检查 KP id 是否可用于新建（全局唯一；本文件已有同 id 视为可更新）。"""
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        kp_id = (kp_id or "").strip()
        if not kp_id:
            return {
                "status": "error",
                "message": "id 不能为空",
                "available": False,
            }
        index = build_kp_index(self.kb_path)
        locs = index["by_id"].get(kp_id, [])
        if not locs:
            return {"status": "ok", "available": True, "kp_id": kp_id}
        rel_norm = (rel_path or "").replace("\\", "/")
        if rel_norm and all(e.file == rel_norm for e in locs):
            return {
                "status": "ok",
                "available": True,
                "kp_id": kp_id,
                "exists_in_file": True,
            }
        files = sorted({e.file for e in locs})
        return {
            "status": "ok",
            "available": False,
            "kp_id": kp_id,
            "message": f"目标 id 已存在：{kp_id}",
            "files": files,
        }

    def search_api(
        self,
        query: str,
        scope: str = "kb",
        limit: int = 20,
        modes: str | None = None,
        rel_path: str | None = None,
    ) -> dict:
        from memoria.services.search_kernel import search

        return search(
            query,
            scope=scope or "kb",
            limit=int(limit) if limit else 20,
            modes=modes,
            kb_path=self.kb_path,
            rel_path=rel_path or None,
        )

    def suggest_kp_merge_api(
        self,
        kp_id: str,
        rel_path: str | None = None,
    ) -> dict:
        from memoria.services.search_kernel import suggest_kp_merge

        return suggest_kp_merge(
            kp_id,
            kb_path=self.kb_path,
            rel_path=rel_path or None,
        )

    def suggest_group_labels_api(self, groups: list[dict]) -> dict:
        from memoria.services.search_kernel import suggest_group_labels

        return suggest_group_labels(kb_path=self.kb_path, groups=groups or [])

    def suggest_tags_api(
        self,
        rel_path: str,
        kp_id: str,
        limit: int = 8,
    ) -> dict:
        kp_id = (kp_id or "").strip()
        if not self.kb_path or not kp_id:
            raise RuntimeError("未打开知识库")
        doc = self.load_document(rel_path)
        if doc.get("status") != "ok":
            return doc
        kp = next((k for k in doc.get("knowledge_points") or [] if k.get("id") == kp_id), None)
        if not kp:
            return {"status": "error", "message": f"知识点不存在：{kp_id}"}
        from memoria.services.suggest_metadata import suggest_tags

        return suggest_tags(
            kb_path=self.kb_path,
            rel_path=rel_path,
            kp_id=kp_id,
            lines=doc.get("lines") or [],
            kp=kp,
            limit=int(limit) if limit else 8,
        )

    def suggest_description_api(self, rel_path: str, kp_id: str) -> dict:
        kp_id = (kp_id or "").strip()
        if not self.kb_path or not kp_id:
            raise RuntimeError("未打开知识库")
        doc = self.load_document(rel_path)
        if doc.get("status") != "ok":
            return doc
        kp = next((k for k in doc.get("knowledge_points") or [] if k.get("id") == kp_id), None)
        if not kp:
            return {"status": "error", "message": f"知识点不存在：{kp_id}"}
        from memoria.services.suggest_metadata import suggest_description

        return suggest_description(
            kb_path=self.kb_path,
            rel_path=rel_path,
            kp_id=kp_id,
            lines=doc.get("lines") or [],
            kp=kp,
        )

    def _rebuild_lexical_index(self) -> None:
        if not self.kb_path:
            return
        try:
            from memoria.services.lexical_index import rebuild_lexical_index

            rebuild_lexical_index(self.kb_path)
        except OSError:
            pass
        self._rebuild_embedding_index()

    def _rebuild_embedding_index(self) -> None:
        if not self.kb_path:
            return
        try:
            from memoria.services.embedding_provider import sync_embedding_index

            sync_embedding_index(self.kb_path, force=False)
        except OSError:
            pass

    def pick_snippet_line(
        self,
        rel_path: str,
        kp_id: str,
        which: str,
        line_number: int,
    ) -> dict:
        doc = self.load_document(rel_path)
        if doc.get("status") != "ok":
            return doc

        lines = doc["lines"]
        kp = next((k for k in doc["knowledge_points"] if k.get("id") == kp_id), None)
        if not kp:
            return {"status": "error", "message": "知识点不存在"}

        rng = dict(kp.get("range") or {})
        anchor_key = "start" if which == "start" else "end"
        rng[anchor_key] = {
            "line_hint": line_number,
            "snippet": lines[line_number - 1].strip()[:SNIPPET_MAX_LEN],
        }

        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path) or {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "file": rel_path.replace("\\", "/"),
            "knowledge_points": [],
        }
        for item in sidecar.setdefault("knowledge_points", []):
            if item.get("id") == kp_id:
                item["range"] = rng
                break
        else:
            sidecar["knowledge_points"].append({
                "id": kp_id,
                "name": kp.get("name", kp_id),
                "range": rng,
            })

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(validation["errors"]),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        return self.load_document(rel_path)

    def update_kp(
        self,
        rel_path: str,
        kp_id: str,
        *,
        name: str | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
        tag_candidates: list | None = None,
    ) -> dict:
        """更新侧车知识点元数据（名称、标签、描述、tag 候选）。"""
        kp_id = (kp_id or "").strip()
        if not kp_id:
            return {"status": "error", "message": "知识点 id 不能为空"}
        if (
            name is None
            and tags is None
            and description is None
            and tag_candidates is None
        ):
            return {"status": "error", "message": "无更新字段"}

        body, _fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path)
        if not sidecar:
            return {"status": "error", "message": "尚未创建配置"}

        entry = next(
            (k for k in (sidecar.get("knowledge_points") or []) if k.get("id") == kp_id),
            None,
        )
        if not entry:
            return {"status": "error", "message": f"知识点不存在：{kp_id}"}

        if name is not None:
            cleaned_name = name.strip()
            if not cleaned_name:
                return {"status": "error", "message": "名称不能为空"}
            entry["name"] = cleaned_name

        if tags is not None:
            cleaned_tags: list[str] = []
            seen: set[str] = set()
            for tag in tags:
                t = str(tag).strip()
                if t and t not in seen:
                    seen.add(t)
                    cleaned_tags.append(t)
            entry["tags"] = cleaned_tags

        if description is not None:
            entry["description"] = str(description).strip()

        if tag_candidates is not None:
            selected_lower = {
                str(t).strip().lower()
                for t in (entry.get("tags") or [])
                if str(t).strip()
            }
            entry["tag_candidates"] = _normalize_tag_candidates(
                tag_candidates,
                exclude=selected_lower,
            )

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(validation["errors"]),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        self._cache.pop(rel_path, None)
        return self.load_document(rel_path)

    def delete_kp(self, rel_path: str, kp_id: str) -> dict:
        """从侧车删除知识点；解除 links 上对该 KP 的 source_id 引用。"""
        kp_id = (kp_id or "").strip()
        if not kp_id:
            return {"status": "error", "message": "知识点 id 不能为空"}

        body, _fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path)
        if not sidecar:
            return {"status": "error", "message": "尚未创建配置"}

        kps = sidecar.get("knowledge_points") or []
        if not any(k.get("id") == kp_id for k in kps):
            return {"status": "error", "message": f"知识点不存在：{kp_id}"}

        sidecar["knowledge_points"] = [k for k in kps if k.get("id") != kp_id]
        for link in sidecar.get("links") or []:
            if not isinstance(link, dict):
                continue
            if str(link.get("source_id") or "").strip() == kp_id:
                link.pop("source_id", None)

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(validation["errors"]),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        sync_kb_pending(self.kb_path)
        self._cache.pop(rel_path, None)
        return self.load_document(rel_path)

    def sync_pending(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        summary = sync_kb_pending(self.kb_path)
        self._cache.clear()
        return {"status": "ok", **summary}

    def get_kb_pending(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        return {"status": "ok", **summarize_kb_pending(self.kb_path)}

    def dismiss_pending(self, pending_id: str) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        if not dismiss_pending_item(self.kb_path, pending_id):
            return {"status": "error", "message": "待确认项不存在"}
        self._cache.clear()
        return {"status": "ok", "pending_id": pending_id}

    def rename_kp_id(self, old_id: str, new_id: str) -> dict:
        """全库重命名知识点 id（侧车引用 + 正文 wikilink）。"""
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        from memoria.services.kp_rename import rename_kp_in_kb

        result = rename_kp_in_kb(self.kb_path, old_id, new_id)
        if result.get("status") == "ok" and result.get("changed"):
            self._cache.clear()
            self._rebuild_lexical_index()
        return result

    def resolve_link(self, target_id: str) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        return resolve_link_target(self.kb_path, target_id)

    def resolve_links(self, target_ids: list[str]) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        return resolve_link_targets(self.kb_path, target_ids)

    def get_link_targets(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        return {"status": "ok", **build_target_lookup(self.kb_path)}

    def get_graph_data(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        from memoria.graph.collector import collect_graph_data
        from memoria.graph.link_audit import audit_kb_graph_links

        data = collect_graph_data(self.kb_path)
        data["graph_audit"] = audit_kb_graph_links(self.kb_path)
        return data

    def build_kb(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        from memoria.graph.kb_build import build_knowledge_base

        result = build_knowledge_base(self.kb_path)
        self._cache.clear()
        if result.get("status") in ("ok", "partial"):
            payload = dict(result)
            payload.pop("graph_data", None)
            return payload
        return result

    def get_graph_audit(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        from memoria.graph.link_audit import audit_kb_graph_links

        return audit_kb_graph_links(self.kb_path)

    def validate_kb(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        files_report: list[dict] = []
        rel_paths = list(collect_md_files(self.kb_path))
        known_kp_ids = set(build_kp_index(self.kb_path)["by_id"].keys())
        from memoria.graph.link_audit import audit_kb_graph_links
        from memoria.storage.kb_integrity import audit_kb_integrity

        kb_integrity = audit_kb_integrity(self.kb_path)

        manifest_diff = audit_manifest_diff(self.kb_path)
        path_moves = detect_path_moves(self.kb_path)
        manifest_diff = filter_manifest_diff_for_path_moves(manifest_diff, path_moves)

        for rel in rel_paths:
            full = os.path.join(self.kb_path, rel)
            _, _, lines = self._read_body(rel)
            sidecar = load_sidecar_for_md(full, self.kb_path)
            if not sidecar:
                continue
            v = validate_sidecar(
                sidecar,
                rel.replace("\\", "/"),
                lines,
                known_kp_ids=known_kp_ids,
            )
            if v["errors"] or v["warnings"]:
                files_report.append({"path": rel, **v})

        graph_audit = audit_kb_graph_links(self.kb_path)
        total_errors, total_warnings = summarize_check_counts(
            kb_integrity=kb_integrity,
            manifest_diff=manifest_diff,
            path_moves=path_moves,
            files_report=files_report,
            graph_audit=graph_audit,
        )

        status = "ok" if total_errors == 0 else "error"
        return {
            "status": status,
            "files_checked": len(rel_paths),
            "issues_count": total_errors + total_warnings,
            "errors": total_errors,
            "warnings": total_warnings,
            "files": files_report,
            "kb_integrity": kb_integrity,
            "manifest_diff": manifest_diff,
            "path_moves": path_moves,
            "graph_audit": graph_audit,
        }

    def repair_path_cascade(self, *, apply: bool = False) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        result = reconcile_path_cascade(self.kb_path, apply=apply)
        if apply and result.get("status") in ("ok", "partial"):
            self._cache.clear()
        return result

    def _write_body(self, rel_path: str, body: str, fm: dict | None) -> None:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        full = os.path.join(self.kb_path, rel_path)
        text = compose_markdown(body, fm)
        tmp = full + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, full)
        touch_manifest_entry(self.kb_path, rel_path.replace("\\", "/"))
        self._rebuild_lexical_index()

    def sync_manifest(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        moves = detect_path_moves(self.kb_path)
        if moves:
            return {
                "status": "error",
                "message": "检测到路径变更，请先使用「修复路径」。直接更新文件清单会导致元数据路径无法恢复。",
                "path_moves": moves,
                "blocked": True,
            }
        return rebuild_manifest(self.kb_path)

    def _sidecar_entry_for_anchor(
        self, sidecar: dict, anchor_text: str, occurrence: int = 0
    ) -> dict | None:
        for link in sidecar.get("links") or []:
            if not isinstance(link, dict):
                continue
            if str(link.get("anchor_text") or "").strip() == anchor_text:
                if int(link.get("occurrence") or 0) == occurrence:
                    return link
        return None

    def _resolve_scan_link_entry(
        self,
        sidecar: dict | None,
        anchor_text: str,
        search_options: dict | LinkTextSearchOptions | None = None,
    ) -> dict | None:
        """扫描时关联侧车 entry（精确 anchor；改名时用 route_anchor 定位原跳转）。"""
        sidecar = sidecar or {}
        anchor_text = (anchor_text or "").strip()
        opts = (
            search_options
            if isinstance(search_options, LinkTextSearchOptions)
            else LinkTextSearchOptions.from_dict(search_options)
        )
        route = (opts.route_anchor or "").strip()

        if route and route != anchor_text:
            route_entry = self._sidecar_entry_for_anchor(sidecar, route)
            if route_entry:
                return route_entry

        entry = self._sidecar_entry_for_anchor(sidecar, anchor_text)
        if entry:
            return entry
        if route:
            return self._sidecar_entry_for_anchor(sidecar, route)
        return None

    @staticmethod
    def _resolve_target_edges(
        target_edges: dict | None,
        entry: dict,
        target_ids: list[str],
    ) -> dict[str, dict]:
        return normalize_target_edges(
            target_edges if target_edges is not None else entry.get("target_edges"),
            target_ids=target_ids,
            link=entry,
        )

    def save_link_route(
        self,
        rel_path: str,
        anchor_text: str,
        target_ids: list[str],
        *,
        display_text: str | None = None,
        edge_type: str | None = None,
        target_edges: dict | None = None,
        relevance: float | None = None,
        source_id: str | None = None,
        old_anchor_text: str | None = None,
        old_display_text: str | None = None,
        occurrence: int = 0,
        update_markdown: bool = True,
        pool_ids: list[str] | None = None,
    ) -> dict:
        """保存 sidecar links[] 路由，可选同步更新正文 [[]]。"""
        anchor_text = (anchor_text or "").strip()
        if not anchor_text:
            return {"status": "error", "message": "目标键不能为空"}
        cleaned = [str(t).strip() for t in (target_ids or []) if str(t).strip()]
        if not cleaned:
            return {"status": "error", "message": "至少需要一个跳转目标"}

        body, fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path) or {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "file": rel_path.replace("\\", "/"),
            "knowledge_points": [],
            "links": [],
        }
        links = sidecar.setdefault("links", [])

        canonical, alias_anchors = collect_link_alias_anchors(
            body, anchor_text, display_text
        )
        anchor_text = canonical
        lookup_keys = alias_anchors | {(old_anchor_text or "").strip(), anchor_text}

        needs_routing_record = len(cleaned) > 1 or (cleaned[0] != anchor_text)
        entry = None
        for key in lookup_keys:
            if not key:
                continue
            entry = self._sidecar_entry_for_anchor(sidecar, key, occurrence)
            if entry:
                break
        had_sidecar_entry = entry is not None
        old_anchor_saved = (old_anchor_text or "").strip()

        has_edge_metadata = (
            target_edges is not None
            or edge_type is not None
            or relevance is not None
        )
        should_persist = needs_routing_record or has_edge_metadata or had_sidecar_entry

        if should_persist:
            sidecar["links"] = [
                ln
                for ln in links
                if not (
                    isinstance(ln, dict)
                    and str(ln.get("anchor_text") or "").strip() in alias_anchors
                    and int(ln.get("occurrence") or 0) == occurrence
                )
            ]
            links = sidecar["links"]
            prev = dict(entry) if entry else {}
            norm_edge = normalize_link_edge_type(edge_type or prev.get("edge_type"))
            te_input = target_edges
            if te_input is None and relevance is not None:
                te_input = {
                    tid: {"edge_type": norm_edge, "relevance": relevance}
                    for tid in cleaned
                }
            entry = {
                "anchor_text": anchor_text,
                "occurrence": occurrence,
                "targets": cleaned,
                "edge_type": norm_edge,
                "target_edges": self._resolve_target_edges(te_input, prev, cleaned),
            }
            if prev.get("instances"):
                entry["instances"] = prev["instances"]
            if prev.get("excluded"):
                entry["excluded"] = prev["excluded"]
            if prev.get("source_id") and not source_id:
                entry["source_id"] = prev["source_id"]
            pool_cleaned: list[str] = []
            seen_pool: set[str] = set()
            for t in list(pool_ids or []) + cleaned:
                t = str(t).strip()
                if t and t not in seen_pool:
                    seen_pool.add(t)
                    pool_cleaned.append(t)
            if pool_cleaned:
                entry["pool"] = pool_cleaned
            links.append(entry)
            if source_id:
                entry["source_id"] = source_id
        else:
            sidecar["links"] = [
                ln
                for ln in links
                if not (
                    isinstance(ln, dict)
                    and str(ln.get("anchor_text") or "").strip() in lookup_keys
                    and int(ln.get("occurrence") or 0) == occurrence
                )
            ]

        body_changed = False
        if update_markdown:
            old_a = (old_anchor_text or canonical).strip()
            if old_a != anchor_text or display_text is not None:
                new_body, ok = update_wikilink(
                    body,
                    old_a if old_a in alias_anchors else anchor_text,
                    new_anchor=anchor_text,
                    display=display_text,
                    edge_hint=None,
                    old_display=old_display_text,
                    occurrence=occurrence,
                )
                if ok:
                    body = new_body
                    body_changed = True

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(validation["errors"]),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        if body_changed:
            self._write_body(rel_path, body, fm)

        self._cache.pop(rel_path, None)
        doc = self.load_document(rel_path)
        result: dict = {"status": "ok", "document": doc, "targets": cleaned}
        if update_markdown and not body_changed:
            visible = wikilink_label(anchor_text, display_text)
            result["warning"] = (
                f"已保存链接配置；正文未找到「{visible}」，"
                "请使用匹配确认面板挂接正文位置"
            )
        return result

    def scan_link_text_matches_api(
        self,
        rel_path: str,
        anchor_text: str,
        search_options: dict | None = None,
    ) -> dict:
        anchor_text = (anchor_text or "").strip()
        if not anchor_text:
            return {"status": "error", "message": "匹配文本不能为空"}
        body, _, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path)
        link_entry = self._resolve_scan_link_entry(
            sidecar or {}, anchor_text, search_options
        )
        opts = LinkTextSearchOptions.from_dict(search_options)
        matches = scan_link_text_matches(
            body,
            anchor_text,
            lines,
            link_entry=link_entry,
            search_options=opts.to_dict(),
            sidecar_links=sidecar.get("links") if sidecar else None,
        )
        attached = sum(1 for m in matches if m.get("attached") and not m.get("excluded"))
        return {
            "status": "ok",
            "matches": matches,
            "search_options": opts.to_dict(),
            "summary": {
                "total": len(matches),
                "attached": attached,
                "excluded": sum(1 for m in matches if m.get("excluded")),
            },
        }

    def suggest_link_anchor_texts_api(
        self,
        rel_path: str,
        query: str,
        search_options: dict | None = None,
    ) -> dict:
        query = (query or "").strip()
        if not query:
            return {"status": "ok", "suggestions": [], "search_options": {}}
        body, _, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path) or {}
        opts = LinkTextSearchOptions.from_dict(search_options)
        suggestions = suggest_link_anchor_texts(
            body,
            query,
            sidecar.get("links"),
            lines=lines,
            search_options=opts.to_dict(),
        )
        if self.kb_path and len(query) >= 2:
            search_res = self.search_api(
                query,
                scope="kb",
                limit=8,
                rel_path=None,
            )
            seen = {str(s.get("text") or "").strip().lower() for s in suggestions}
            for hit in search_res.get("results") or []:
                text = str(hit.get("name") or hit.get("label") or "").strip()
                if not text or text.lower() in seen:
                    continue
                seen.add(text.lower())
                suggestions.append({
                    "text": text,
                    "source": "kp",
                    "score": float(hit.get("score") or 0),
                })
            suggestions.sort(
                key=lambda x: (-float(x.get("score") or 0), str(x.get("text") or ""))
            )
        return {
            "status": "ok",
            "suggestions": suggestions,
            "search_options": opts.to_dict(),
        }

    def detach_link_instance(
        self,
        rel_path: str,
        anchor_text: str,
        line_number: int,
    ) -> dict:
        """从跳转入口移除此处：unwrap 单行 + excluded，保留 sidecar 路由。"""
        anchor_text = (anchor_text or "").strip()
        ln = int(line_number)
        if not anchor_text:
            return {"status": "error", "message": "匹配文本不能为空"}
        if ln < 1:
            return {"status": "error", "message": "行号无效"}

        body, fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path)
        if not sidecar:
            return {"status": "error", "message": "尚未创建配置"}

        entry = self._sidecar_entry_for_anchor(sidecar, anchor_text)
        if not entry:
            return {"status": "error", "message": "未找到跳转入口"}

        new_body, ok = remove_wikilink_on_line(body, anchor_text, ln)
        if not ok:
            for m in scan_link_text_matches(body, anchor_text, lines, link_entry=entry):
                if m["line"] == ln and not m.get("wrapped"):
                    break
            else:
                return {"status": "error", "message": "该位置未找到链接标记"}

        entry = add_excluded_lines(entry, [ln])
        inst = [
            x
            for x in (entry.get("instances") or [])
            if not (isinstance(x, dict) and int(x.get("line") or 0) == ln)
        ]
        entry["instances"] = inst

        links = sidecar.get("links") or []
        for i, link in enumerate(links):
            if (
                isinstance(link, dict)
                and str(link.get("anchor_text") or "").strip() == anchor_text
            ):
                links[i] = entry
                break

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(validation["errors"]),
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        if ok:
            self._write_body(rel_path, new_body, fm)

        self._cache.pop(rel_path, None)
        return {"status": "ok", "document": self.load_document(rel_path)}

    def apply_link_instances(
        self,
        rel_path: str,
        anchor_text: str,
        target_ids: list[str],
        selected_lines: list[int],
        *,
        old_anchor_text: str | None = None,
        display_text: str | None = None,
        edge_type: str | None = None,
        target_edges: dict | None = None,
        relevance: float | None = None,
        source_id: str | None = None,
        occurrence: int = 0,
        pool_ids: list[str] | None = None,
        search_options: dict | None = None,
    ) -> dict:
        """匹配确认后：写 instances、包裹/解除包裹。"""
        anchor_text = (anchor_text or "").strip()
        if not anchor_text:
            return {"status": "error", "message": "匹配文本不能为空"}
        cleaned = [str(t).strip() for t in (target_ids or []) if str(t).strip()]
        if not cleaned:
            return {"status": "error", "message": "至少需要一个跳转目标"}

        body, fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path) or {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "file": rel_path.replace("\\", "/"),
            "knowledge_points": [],
            "links": [],
        }

        opts = LinkTextSearchOptions.from_dict(search_options)
        old_a = (old_anchor_text or anchor_text).strip()
        if old_a != anchor_text and not opts.route_anchor:
            opts.route_anchor = old_a

        entry = self._resolve_scan_link_entry(sidecar, anchor_text, opts)
        if not entry and old_a != anchor_text:
            entry = self._sidecar_entry_for_anchor(sidecar, old_a, occurrence)

        matches = scan_link_text_matches(
            body,
            anchor_text,
            lines,
            link_entry=entry,
            search_options=opts.to_dict(),
            sidecar_links=sidecar.get("links"),
        )
        selected = [int(x) for x in selected_lines]
        match_by_line = {int(m["line"]): m for m in matches}

        invalid = [
            ln
            for ln in selected
            if ln not in match_by_line
            or match_by_line[ln].get("is_substring")
            or match_by_line[ln].get("blocked")
        ]
        if invalid:
            bad = ", ".join(f"L{ln}" for ln in invalid)
            reasons = [
                match_by_line[ln].get("block_reason")
                for ln in invalid
                if ln in match_by_line and match_by_line[ln].get("block_reason")
            ]
            msg = f"所选行 {bad} 无法挂接（无有效匹配、为子串或与其它跳转冲突）"
            if reasons:
                msg += "：" + reasons[0]
            return {
                "status": "error",
                "message": msg,
            }

        anchor_text = resolve_canonical_anchor(anchor_text, matches, selected)
        line_spans = line_matched_spans(matches, selected)

        if old_a and old_a != anchor_text:
            old_entry = self._sidecar_entry_for_anchor(sidecar, old_a, occurrence)
            if old_entry:
                old_inst = [
                    int(x.get("line") or 0)
                    for x in (old_entry.get("instances") or [])
                    if isinstance(x, dict)
                ]
                if old_inst:
                    body, _ = unwrap_lines(body, old_a, old_inst)
                else:
                    for m in scan_link_text_matches(body, old_a, lines, old_entry):
                        if m.get("wrapped"):
                            body, _ = unwrap_lines(body, old_a, [m["line"]])
            lines = body.splitlines()
            matches = scan_link_text_matches(
                body,
                anchor_text,
                lines,
                link_entry=entry,
                search_options=opts.to_dict(),
                sidecar_links=sidecar.get("links"),
            )
            match_by_line = {int(m["line"]): m for m in matches}
            line_spans = line_matched_spans(matches, selected)

        to_wrap = [ln for ln in selected if ln >= 1]
        to_unwrap = [
            m["line"]
            for m in matches
            if m.get("wrapped") and m["line"] not in set(to_wrap)
        ]
        body, _ = unwrap_lines(body, anchor_text, to_unwrap)
        need_wrap = sum(
            1
            for ln in to_wrap
            if ln in match_by_line and not match_by_line[ln].get("wrapped")
        )
        body, wrap_count = wrap_plain_on_lines(
            body, anchor_text, to_wrap, line_spans=line_spans
        )
        if need_wrap > 0 and wrap_count < need_wrap:
            return {
                "status": "error",
                "message": (
                    f"正文包裹失败（{wrap_count}/{need_wrap} 处）· "
                    "请检查匹配文本是否与正文一致，或开启「忽略空格」"
                ),
            }

        lines = body.splitlines()
        matches = scan_link_text_matches(
            body,
            anchor_text,
            lines,
            link_entry=entry,
            search_options=opts.to_dict(),
        )

        entry = self._sidecar_entry_for_anchor(sidecar, anchor_text, occurrence)
        if not entry and old_a != anchor_text:
            entry = self._sidecar_entry_for_anchor(sidecar, old_a, occurrence)
        if not entry:
            entry = {"anchor_text": anchor_text, "occurrence": occurrence, "targets": cleaned}
        else:
            entry = dict(entry)
            entry["anchor_text"] = anchor_text
            entry["targets"] = cleaned
        entry["edge_type"] = normalize_link_edge_type(
            edge_type or entry.get("edge_type")
        )
        te_input = target_edges
        if te_input is None and relevance is not None:
            te_input = {
                tid: {"edge_type": entry["edge_type"], "relevance": relevance}
                for tid in cleaned
            }
        entry["target_edges"] = self._resolve_target_edges(
            te_input, entry, cleaned
        )
        entry.pop("relevance", None)

        entry = sync_instances_from_selection(entry, to_wrap, matches)
        entry["excluded"] = [
            x
            for x in (entry.get("excluded") or [])
            if not (
                isinstance(x, dict)
                and int(x.get("line") or 0) in set(to_wrap)
            )
        ]

        pool_cleaned: list[str] = []
        seen_pool: set[str] = set()
        for t in list(pool_ids or []) + cleaned:
            t = str(t).strip()
            if t and t not in seen_pool:
                seen_pool.add(t)
                pool_cleaned.append(t)
        if pool_cleaned:
            entry["pool"] = pool_cleaned
        if source_id:
            entry["source_id"] = source_id

        links = sidecar.setdefault("links", [])
        sidecar["links"] = [
            ln
            for ln in links
            if not (
                isinstance(ln, dict)
                and str(ln.get("anchor_text") or "").strip()
                in {(old_a or "").strip(), anchor_text}
                and int(ln.get("occurrence") or 0) == occurrence
            )
        ]
        sidecar["links"].append(entry)

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(validation["errors"]),
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        self._write_body(rel_path, body, fm)
        self._cache.pop(rel_path, None)
        doc = self.load_document(rel_path)
        return {
            "status": "ok",
            "document": doc,
            "targets": cleaned,
            "wrapped": wrap_count,
        }

    def delete_link_route(
        self,
        rel_path: str,
        anchor_text: str,
        *,
        occurrence: int = 0,
    ) -> dict:
        """删除 sidecar 跳转入口，并解除正文中所有匹配的 [[anchor]]。"""
        anchor_text = (anchor_text or "").strip()
        if not anchor_text:
            return {"status": "error", "message": "匹配文本不能为空"}

        body, fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path)
        if not sidecar:
            return {"status": "error", "message": "尚未创建配置"}

        entry = self._sidecar_entry_for_anchor(sidecar, anchor_text, occurrence)
        if not entry:
            return {"status": "error", "message": f"未找到跳转入口：{anchor_text}"}

        wrapped_lines = [
            m["line"]
            for m in scan_link_text_matches(body, anchor_text, lines, link_entry=entry)
            if m.get("wrapped")
        ]
        body_changed = False
        if wrapped_lines:
            body, _ = unwrap_lines(body, anchor_text, wrapped_lines)
            body_changed = True
        while True:
            new_body, ok = remove_wikilink(body, anchor_text, occurrence=0)
            if not ok:
                break
            body = new_body
            body_changed = True

        links = sidecar.get("links") or []
        sidecar["links"] = [
            ln
            for ln in links
            if not (
                isinstance(ln, dict)
                and str(ln.get("anchor_text") or "").strip() == anchor_text
                and int(ln.get("occurrence") or 0) == occurrence
            )
        ]
        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(validation["errors"]),
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        if body_changed:
            self._write_body(rel_path, body, fm)

        self._cache.pop(rel_path, None)
        return {"status": "ok", "document": self.load_document(rel_path)}

    def remove_link(
        self,
        rel_path: str,
        anchor_text: str,
        *,
        display_text: str | None = None,
        edge_hint: str | None = None,
        occurrence: int = 0,
        remove_sidecar: bool = True,
    ) -> dict:
        """移除正文 [[]] 标记（保留显示文字），并删除 sidecar 路由。"""
        anchor_text = (anchor_text or "").strip()
        if not anchor_text:
            return {"status": "error", "message": "目标键不能为空"}

        body, fm, lines = self._read_body(rel_path)
        new_body, ok = remove_wikilink(
            body,
            anchor_text,
            display=display_text,
            edge_hint=edge_hint,
            occurrence=occurrence,
        )
        if not ok:
            return {"status": "error", "message": "正文中未找到匹配的 [[链接]]"}

        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path)
        _, alias_anchors = collect_link_alias_anchors(
            body, anchor_text, display_text
        )
        if remove_sidecar and sidecar:
            links = sidecar.get("links") or []
            sidecar["links"] = [
                ln
                for ln in links
                if not (
                    isinstance(ln, dict)
                    and str(ln.get("anchor_text") or "").strip() in alias_anchors
                    and int(ln.get("occurrence") or 0) == occurrence
                )
            ]
            self._write_sidecar(rel_path.replace("\\", "/"), sidecar)

        self._write_body(rel_path, new_body, fm)
        self._cache.pop(rel_path, None)
        return {"status": "ok", "document": self.load_document(rel_path)}

    def wrap_text_as_link(
        self,
        rel_path: str,
        selected_text: str,
        anchor_text: str,
        *,
        target_ids: list[str] | None = None,
        display_text: str | None = None,
        edge_type: str | None = None,
        target_edges: dict | None = None,
        relevance: float | None = None,
        source_id: str | None = None,
    ) -> dict:
        """选区创建链接：写 sidecar 路由，由匹配面板确认包裹位置。"""
        selected_text = (selected_text or "").strip()
        anchor_text = (anchor_text or "").strip()
        if not selected_text:
            return {"status": "error", "message": "选中文本为空"}
        if not anchor_text:
            anchor_text = selected_text

        disp = (display_text or selected_text).strip()
        targets = [str(t).strip() for t in (target_ids or []) if str(t).strip()]
        if not targets:
            return {"status": "error", "message": "至少需要一个跳转目标"}

        return self.save_link_route(
            rel_path,
            anchor_text,
            targets,
            display_text=disp if disp != anchor_text else None,
            edge_type=edge_type,
            target_edges=target_edges,
            relevance=relevance,
            source_id=source_id,
            update_markdown=False,
        )

    def suggest_link_relevance_api(
        self,
        rel_path: str,
        anchor_text: str,
        target_id: str = "",
        target_ids: list[str] | None = None,
        *,
        edge_type: str | None = None,
        source_id: str | None = None,
    ) -> dict:
        """链接编辑器：按目标推荐 relevance（M4 检索内核预留）。"""
        anchor_text = (anchor_text or "").strip()
        if not anchor_text:
            return {"status": "error", "message": "匹配文本不能为空"}
        tid = (target_id or "").strip()
        cleaned = [tid] if tid else [str(t).strip() for t in (target_ids or []) if str(t).strip()]
        return suggest_link_relevance(
            anchor_text=anchor_text,
            target_ids=cleaned,
            edge_type=edge_type,
            source_id=source_id,
            kb_path=self.kb_path,
        )
