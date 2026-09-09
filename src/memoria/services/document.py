"""文档加载与侧车写入"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field

from memoria.range.constants import SNIPPET_MAX_LEN
from memoria.graph.edge_types import normalize_link_edge_type, normalize_link_relevance, normalize_target_edges

logger = logging.getLogger(__name__)
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
from memoria.services.kp_rename import (
    migrate_sidecar_kp_refs,
    replace_link_id_in_markdown,
)
from memoria.services.range_proposals import merge_range_proposals
from memoria.range.constants import SNIPPET_MAX_LEN
from memoria.range.locator import resolve_range
from memoria.storage.constants import MEMORIA_DIR, SIDECAR_SCHEMA_VERSION
from memoria.storage.markdown import compose_markdown, strip_frontmatter
from memoria.storage.scanner import collect_md_files
from memoria.storage.sidecar import (
    legacy_sidecar_path_for,
    load_sidecar_for_md,
    save_sidecar_for_md,
    sidecar_path_for,
)
from memoria.storage.manifest import (
    audit_manifest_diff,
    ensure_manifest_baseline,
    filter_manifest_diff_for_path_moves,
    rebuild_manifest,
    touch_manifest_entry,
)
from memoria.storage.path_cascade import (
    apply_path_move,
    detect_path_moves,
    reconcile_path_cascade,
)
from memoria.storage.pending import (
    dismiss_pending_item,
    load_pending,
    save_pending,
    summarize_kb_pending,
    sync_kb_pending,
    sync_pending_for_file,
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
        if isinstance(item, dict) and item.get("status"):
            cand["status"] = str(item.get("status"))
        out.append(cand)
    return out


def _normalize_alias_candidates(
    raw: list | None,
    *,
    exclude: set[str] | None = None,
) -> list[dict]:
    exclude = exclude or set()
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw or []:
        alias = ""
        source = "user"
        if isinstance(item, str):
            alias = item.strip()
        elif isinstance(item, dict):
            alias = str(item.get("alias") or "").strip()
            src = str(item.get("source") or "user").strip().lower()
            source = src if src in ("system", "user", "feedback") else "user"
        else:
            continue
        if not alias:
            continue
        key = alias.lower()
        if key in exclude or key in seen:
            continue
        seen.add(key)
        row: dict = {"alias": alias, "source": source}
        if isinstance(item, dict) and item.get("status"):
            row["status"] = str(item.get("status"))
        out.append(row)
    return out


def _normalize_description_candidates(raw: list | None) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw or []:
        text = ""
        source = "user"
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            src = str(item.get("source") or "user").strip().lower()
            source = src if src in ("system", "user", "feedback") else "user"
        else:
            continue
        if not text or text in seen:
            continue
        seen.add(text)
        row: dict = {"text": text, "source": source}
        if isinstance(item, dict) and item.get("status"):
            row["status"] = str(item.get("status"))
        out.append(row)
    return out


def _normalize_targets_list(raw: object) -> list[str]:
    """将 targets 字段归一化为字符串列表（用于边匹配）。"""
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if isinstance(t, str) and str(t).strip()]
    return []


def _fsync_mode() -> str:
    """正文保存的 fsync 模式（docs/design/durable-flush.md，G4 M6a）。

    - inline：每次保存 tmp+fsync+replace（M1 旧行为，最稳、~20ms/次）；
    - barrier（默认）：tmp+replace 写系统缓存立即返回，fsync 由 durable_flush
      在屏障/防抖兜底批量执行。
    A/B 用环境变量 MEMORIA_FSYNC_MODE=inline|barrier。
    """
    return (os.environ.get("MEMORIA_FSYNC_MODE") or "barrier").strip().lower() or "barrier"


@dataclass
class DocumentService:
    kb_path: str | None = None
    _cache: dict[str, dict] = field(default_factory=dict, repr=False)
    # M6a：barrier 模式下待刷盘的正文路径集（rel_norm）；manifest pending 在 manifest.py 模块级
    _dirty_fsync: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if self.kb_path:
            self.set_kb_path(self.kb_path)

    def set_kb_path(self, path: str) -> None:
        if not os.path.isdir(path):
            raise FileNotFoundError(f"目录不存在: {path}")
        if self.kb_path and os.path.normpath(self.kb_path) != os.path.normpath(path):
            # 切库前先把上一个 KB 的 pending manifest / dirty fsync 落盘（M6a）
            try:
                self.durable_flush()
            except Exception:  # noqa: BLE001
                pass
        self.kb_path = path
        self._cache.clear()
        remember_last_kb_path(path)
        # manifest 基线 / pending 同步为启动辅助动作：失败降级（记录日志），
        # 不应阻断应用启动（此前 .bak 备份 PermissionError 会让发布态启动崩溃）
        try:
            ensure_manifest_baseline(path)
        except Exception:  # noqa: BLE001
            logger.warning("ensure_manifest_baseline failed for %s", path, exc_info=True)
        try:
            sync_kb_pending(path)
        except Exception:  # noqa: BLE001
            logger.warning("sync_kb_pending failed for %s", path, exc_info=True)
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
        self._sort_kps_by_start_line(sidecar)
        save_sidecar_for_md(full, self.kb_path, sidecar)
        touch_manifest_entry(self.kb_path, rel_norm)
        self._rebuild_lexical_index()

    @staticmethod
    def _sort_kps_by_start_line(sidecar: dict) -> None:
        """按 range.start.line_hint 升序排序 knowledge_points，便于维护。"""
        kps = sidecar.get("knowledge_points")
        if not isinstance(kps, list) or len(kps) <= 1:
            return
        def sort_key(kp: dict) -> tuple[int, str]:
            if not isinstance(kp, dict):
                return (1 << 30, "")
            rng = kp.get("range") or {}
            start = rng.get("start") or {}
            hint = start.get("line_hint")
            try:
                line = int(hint) if hint is not None else 0
            except (TypeError, ValueError):
                line = 0
            return (line, str(kp.get("id") or ""))
        sidecar["knowledge_points"] = sorted(kps, key=sort_key)

    def save_document(self, rel_path: str, body: str) -> dict:
        """将编辑后的正文写回 .md 文件（保留原有 frontmatter）。

        注意：保存**不**触发图片清理。图片资产清理（按全库引用扫描）
        只在用户于「图片管理器」主动点击清理/删除时执行（RPC cleanup_unused_images），
        避免编辑/预览中间态导致误删仍被引用的图片。
        """
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        rel_norm = rel_path.replace("\\", "/")
        if not rel_norm.lower().endswith(".md"):
            return {"status": "error", "message": "只允许保存 .md 文件"}
        full = os.path.join(self.kb_path, rel_norm)
        if not os.path.isfile(full):
            return {"status": "error", "message": "文件不存在"}
        # 读取原始文件以保留 frontmatter
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        from memoria.storage.markdown import strip_frontmatter, compose_markdown

        _, fm = strip_frontmatter(raw)
        new_content = compose_markdown(body, fm)
        # 原子写 + fsync 策略（M1 原子写扩展为 durable_flush，见 durable-flush.md）
        mode = _fsync_mode()
        tmp_full = full + ".tmp"
        with open(tmp_full, "w", encoding="utf-8") as f:
            f.write(new_content)
            f.flush()
            if mode == "inline":
                os.fsync(f.fileno())
        os.replace(tmp_full, full)
        if mode != "inline":
            self._dirty_fsync.add(rel_norm)
        # 清除缓存，下次 load 时重新解析
        self._cache.pop(rel_norm, None)
        if mode == "inline":
            # M1 旧行为：manifest 单条即时落盘
            touch_manifest_entry(self.kb_path, rel_norm)
        else:
            # M6a：manifest 单条更新延迟落盘（入模块 pending，屏障批量写一次）
            from memoria.storage.manifest import defer_manifest_touch

            defer_manifest_touch(self.kb_path, rel_norm)
        # 保存后增量维护图片注册表（只重扫该文档；删除仅在用户显式触发时进行）
        bench = os.environ.get("MEMORIA_BENCH_TIMING") == "1"
        ms = {"registry": None, "resync": None}
        t = time.perf_counter()
        try:
            self._update_registry_for_doc(rel_norm)
        except Exception:  # noqa: BLE001
            # 注册表维护失败不影响保存结果
            pass
        if bench:
            ms["registry"] = round((time.perf_counter() - t) * 1000, 2)
        # 保存后重新锚定 KP range：正文换行/行号漂移会导致 line_hint 失效甚至
        # end 锚点行被拆成两行而解析失败（识别失败）。见 _resync_kp_ranges_after_edit。
        resynced = 0
        t = time.perf_counter()
        try:
            resynced = self._resync_kp_ranges_after_edit(rel_norm)
        except Exception:  # noqa: BLE001
            pass
        if bench:
            ms["resync"] = round((time.perf_counter() - t) * 1000, 2)
        result = {"status": "ok", "ranges_resynced": resynced}
        if bench:
            result["bench_ms"] = ms
        return result

    def durable_flush(self) -> dict:
        """屏障持久化（docs/design/durable-flush.md，G4 M6a）。

        1) manifest pending 批量落盘（读侧已由 overlay 保证一致）；2) dirty 正文集
        逐个 fsync（失败保留待重试）。前端在显式保存/切文件/关库/退出与自动保存后
        ~3s 防抖兜底时调用。
        """
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        from memoria.storage.manifest import flush_manifest_deferred

        out = {"status": "ok", "flushed": 0, "manifest": 0, "pending": 0}
        t0 = time.perf_counter()
        try:
            out["manifest"] = flush_manifest_deferred(self.kb_path)
        except Exception as e:  # noqa: BLE001
            out["status"] = "error"
            out["message"] = f"manifest flush 失败: {e}"
        remaining: set[str] = set()
        for rel in sorted(self._dirty_fsync):
            full = os.path.join(self.kb_path, rel)
            try:
                with open(full, "r+b") as f:
                    os.fsync(f.fileno())
                out["flushed"] += 1
            except OSError:
                remaining.add(rel)
        self._dirty_fsync = remaining
        out["pending"] = len(remaining)
        out["ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return out

    _HEADING_RE = re.compile(r"^(#{1,6})\s+")

    def _resync_kp_ranges_after_edit(self, rel_norm: str) -> int:
        """正文保存后重新锚定该文档的 KP range，返回改动数。

        - 解析成功：仅把漂移的 line_hint 更新为实际解析到的行号；
        - 解析失败且为 end 锚点丢失（如“在结尾行中间回车”把锚点行拆成两行）：
          从已定位的 start 起，按下一条 `#{1,6} ` 标题前（或文末）重建 end，
          同步 snippet 为重建行内容截断——避免 KP 因锚点断裂而无法识别。
        """
        full = os.path.join(self.kb_path, rel_norm)
        sc = load_sidecar_for_md(full, self.kb_path)
        if not sc:
            return 0
        try:
            with open(full, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            return 0
        body, _ = strip_frontmatter(raw)
        lines = body.splitlines()
        if not lines:
            return 0
        kps = sc.get("knowledge_points")
        if not isinstance(kps, list):
            return 0
        changed = 0
        for kp in kps:
            if not isinstance(kp, dict) or not isinstance(kp.get("range"), dict):
                continue
            rng = kp["range"]
            start = dict(rng.get("start") or {})
            end = dict(rng.get("end") or {})
            rr = resolve_range(lines, start, end)
            if rr.get("ok"):
                ns, ne = rr["start_line"], rr["end_line"]
                if start.get("line_hint") != ns or end.get("line_hint") != ne:
                    start["line_hint"] = ns
                    end["line_hint"] = ne
                    rng["start"] = start
                    rng["end"] = end
                    changed += 1
                continue
            # 结构修复：start 已定位、end 锚点断裂 → 按标题结构重建 end
            if rr.get("error") == "end_snippet_not_found" and rr.get("start_line"):
                si = rr["start_line"] - 1
                nxt = None
                for i in range(si + 1, len(lines)):
                    if self._HEADING_RE.match(lines[i]):
                        nxt = i
                        break
                ei = len(lines) - 1 if nxt is None else nxt - 1
                end["line_hint"] = ei + 1
                end["snippet"] = lines[ei].strip()[:SNIPPET_MAX_LEN]
                rng["end"] = end
                changed += 1
        if changed:
            self._write_sidecar(rel_norm, sc)
        return changed

    def close_kb(self) -> None:
        kb = self.kb_path
        if kb:
            # 关库屏障：pending manifest / dirty fsync 落盘（M6a，尽力而为）
            try:
                self.durable_flush()
            except Exception:  # noqa: BLE001
                pass
        self.kb_path = None
        self._cache.clear()
        remember_last_kb_path(None)
        if kb:
            try:
                from memoria.services.embedding_provider import reset_warmup_state

                reset_warmup_state(kb)
            except Exception:
                pass

    def list_files(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        items: list[dict] = []
        dirs: set[str] = set()
        for rel in collect_md_files(self.kb_path):
            full = os.path.join(self.kb_path, rel)
            sc = load_sidecar_for_md(full, self.kb_path)
            items.append({
                "path": rel,
                "has_sidecar": sc is not None,
                "description": (sc or {}).get("description", ""),
            })
            parts = rel.split("/")
            for i in range(1, len(parts)):
                dirs.add("/".join(parts[:i]))
        # 收集磁盘上存在的目录（含空目录），保证新建的空文件夹在文件树可见；
        # 跳过隐藏目录（.memoria/.git 等）
        for dirpath, dirnames, _ in os.walk(self.kb_path):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for d in dirnames:
                rel_d = os.path.relpath(
                    os.path.join(dirpath, d), self.kb_path
                ).replace("\\", "/")
                if rel_d != ".":
                    dirs.add(rel_d)
        return {"files": items, "dirs": sorted(dirs)}

    # ── 文件树操作（重命名/删除/新建） ──────────────────────────

    def _resolve_rel_path(self, rel_path: str) -> str:
        """规范化相对路径（正斜杠）并防止目录穿越。"""
        rel = (rel_path or "").replace("\\", "/").lstrip("/")
        norm = os.path.normpath(rel).replace(os.sep, "/")
        if norm == ".." or norm.startswith("../"):
            raise RuntimeError("路径越界")
        return norm

    def _full_path(self, rel: str) -> str:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        full = os.path.abspath(os.path.join(self.kb_path, rel))
        root = os.path.abspath(self.kb_path)
        if full != root and not full.startswith(root + os.sep):
            raise RuntimeError("路径越界")
        return full

    def _move_sidecar(self, old_md_full: str, new_md_full: str) -> None:
        """重命名 md 时联动侧车（镜像布局 + 旧版同目录布局）。"""
        pairs = (
            (
                legacy_sidecar_path_for(old_md_full),
                legacy_sidecar_path_for(new_md_full),
            ),
            (
                sidecar_path_for(old_md_full, self.kb_path),
                sidecar_path_for(new_md_full, self.kb_path),
            ),
        )
        for old_sc, new_sc in pairs:
            if old_sc and new_sc and old_sc != new_sc and os.path.isfile(old_sc):
                os.makedirs(os.path.dirname(new_sc), exist_ok=True)
                os.rename(old_sc, new_sc)

    def _remove_sidecar(self, md_full: str) -> None:
        """删除 md 时联动删除侧车（两种布局）。"""
        for sc in (
            legacy_sidecar_path_for(md_full),
            sidecar_path_for(md_full, self.kb_path),
        ):
            if sc and os.path.isfile(sc):
                try:
                    os.remove(sc)
                except OSError:
                    pass

    def rename_file(self, old_rel: str, new_name: str) -> dict:
        """重命名 .md 文件（仅文件名，保持所在目录），联动侧车、manifest 与全库引用。

        引用同步规则：
        - 若旧文件名不是任何 KP id（纯文件 stem 引用），把所有正文
          [[oldStem]] / [[oldStem#type]] / [[oldStem|text]] 改写为
          [[newStem|原文]]，并迁移各侧车中对该 stem 的链接/边目标与候选池；
        - 若旧文件名恰是某 KP id（如 a.md 内含 id=a 的知识点），则
          [[oldStem]] 解析到 KP 而非文件，KP id 不随文件改名变化，无需改写
          （避免把 KP 引用降级成文件跳转）。
        - 新文件名 stem 若已被其他文件占用 → 全局 id 唯一性冲突，拒绝。
        """
        old = self._resolve_rel_path(old_rel)
        name = (new_name or "").strip().replace("\\", "/").strip("/")
        if not name or name in (".", "..") or "/" in name:
            return {"status": "error", "message": "文件名无效"}
        if not name.lower().endswith(".md"):
            name += ".md"
        parent = old.rsplit("/", 1)[0] if "/" in old else ""
        new_rel = f"{parent}/{name}" if parent else name
        old_full = self._full_path(old)
        new_full = self._full_path(new_rel)
        if not os.path.isfile(old_full):
            return {"status": "error", "message": "文件不存在"}
        if os.path.exists(new_full):
            return {"status": "error", "message": "目标文件已存在"}

        old_stem = os.path.splitext(os.path.basename(old))[0]
        new_stem = os.path.splitext(os.path.basename(name))[0]
        index = build_kp_index(self.kb_path)
        other = index["file_stems"].get(new_stem)
        if other and other != old:
            return {
                "status": "error",
                "message": f"重命名后文件名 id『{new_stem}』与 {other} 冲突",
            }
        # 旧 stem 若被某 KP id 遮蔽（[[oldStem]] 解析到知识点而非文件），
        # 则文件重命名不影响这些引用，无需改写
        kp_shadow = bool(index["by_id"].get(old_stem))

        os.rename(old_full, new_full)
        self._move_sidecar(old_full, new_full)

        md_files: list[str] = []
        md_replacements = 0
        sidecar_files: list[str] = []
        for rel in collect_md_files(self.kb_path):
            rel_norm = rel.replace("\\", "/")
            full = os.path.join(self.kb_path, rel)
            touched = False
            if not kp_shadow:
                with open(full, "r", encoding="utf-8") as f:
                    raw = f.read()
                body, fm = strip_frontmatter(raw)
                new_body, n = replace_link_id_in_markdown(body, old_stem, new_stem)
                if n:
                    text = compose_markdown(new_body, fm)
                    tmp = full + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write(text)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, full)
                    md_replacements += n
                    md_files.append(rel_norm)
                    touched = True
            sidecar = load_sidecar_for_md(full, self.kb_path)
            if sidecar:
                sc_changed = 0
                if not kp_shadow:
                    sc_changed += migrate_sidecar_kp_refs(sidecar, old_stem, new_stem)
                if rel_norm == new_rel and str(sidecar.get("file") or "") != new_rel:
                    sidecar["file"] = new_rel
                    sc_changed += 1
                if sc_changed:
                    save_sidecar_for_md(full, self.kb_path, sidecar)
                    sidecar_files.append(rel_norm)
                    touched = True
            if touched:
                touch_manifest_entry(self.kb_path, rel_norm)
                self._cache.pop(rel_norm, None)

        self._cache.pop(old, None)
        self._cache.pop(new_rel, None)
        # 旧路径条目已失效 → touch 会因文件不存在而移除；再写入新路径条目
        touch_manifest_entry(self.kb_path, old)
        touch_manifest_entry(self.kb_path, new_rel)
        # 级联：pending 项路径 & 图片注册表增量（与 rename_dir pipeline 一致）
        try:
            data = load_pending(self.kb_path) or {}
            changed = 0
            for item in data.get("items") or []:
                if isinstance(item, dict) and str(item.get("file") or "").replace("\\", "/") == old:
                    item["file"] = new_rel
                    changed += 1
            if changed:
                save_pending(self.kb_path, data)
        except Exception:  # noqa: BLE001
            pass
        try:
            # 旧文件已不存在 → 剔除旧引用；按新路径重扫引用
            self._update_registry_for_doc(old)
            self._update_registry_for_doc(new_rel)
        except Exception:  # noqa: BLE001
            pass
        return {
            "status": "ok",
            "path": new_rel,
            "synced": bool(md_files or sidecar_files),
            "md_replacements": md_replacements,
            "md_files": md_files,
            "sidecar_files": sidecar_files,
        }

    def rename_dir(self, old_rel: str, new_name: str) -> dict:
        """重命名文件夹（相对 KB 根，保持所在父目录），并完成内部注册信息级联。

        自维护 pipeline（与 rename_file 语义对齐，保证安全/一致）：
        1) 校验：目录存在于 KB 内、非 KB 根/系统目录（.memoria）；新名合法且不冲突；
        2) 移动前收集受影响 .md（旧前缀下全部，含子目录）；
        3) 物理移动整个目录（md + 目录内非 md 资产一并移动）；
        4) 逐文件级联 path_cascade.apply_path_move：侧车镜像迁移 + sidecar.file 字段
           + pending 项路径 + manifest files_by_path；
        5) 图片注册表按文档增量刷新（旧路径剔除 / 新路径重扫）；
        6) 内存缓存失效，汇总 files/sidecars/pending 并上报错误（部分成功不清零）。
        """
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        old = self._resolve_rel_path(old_rel).strip("/")
        if not old:
            return {"status": "error", "message": "目录无效"}
        if old == MEMORIA_DIR or old.startswith(MEMORIA_DIR + "/") or old.startswith("."):
            return {"status": "error", "message": "不能重命名系统/隐藏目录"}
        name = (new_name or "").strip().replace("\\", "/").strip("/")
        if not name or name in (".", "..") or "/" in name:
            return {"status": "error", "message": "文件夹名无效"}
        parent = old.rsplit("/", 1)[0] if "/" in old else ""
        new_rel = f"{parent}/{name}" if parent else name
        if old == new_rel:
            return {"status": "ok", "path": new_rel, "synced": False, "files": 0}
        old_full = self._full_path(old)
        new_full = self._full_path(new_rel)
        if not os.path.isdir(old_full):
            return {"status": "error", "message": "目录不存在"}
        if os.path.exists(new_full):
            return {"status": "error", "message": "目标文件夹已存在"}
        prefix = old + "/"
        moved = [
            r.replace("\\", "/")
            for r in collect_md_files(self.kb_path)
            if r.replace("\\", "/").startswith(prefix)
        ]
        try:
            os.rename(old_full, new_full)
        except OSError as e:  # noqa: BLE001
            return {"status": "error", "message": f"移动文件夹失败: {e}"}
        if not os.path.isdir(new_full):
            return {"status": "error", "message": "移动后目录不存在（可能被占用），请检查后重试"}
        sidecar_files: list[str] = []
        pending_updated = 0
        errors: list[dict] = []
        for old_md in moved:
            new_md = new_rel + old_md[len(old):]
            self._cache.pop(old_md, None)
            self._cache.pop(new_md, None)
            try:
                res = apply_path_move(self.kb_path, old_md, new_md)
                if res.get("status") != "ok":
                    errors.append({"from": old_md, "to": new_md, "error": res.get("message", "级联失败")})
                    continue
                if res.get("sidecar_moved") or res.get("sidecar_updated"):
                    sidecar_files.append(new_md)
                pending_updated += int(res.get("pending_updated") or 0)
            except Exception as e:  # noqa: BLE001
                errors.append({"from": old_md, "to": new_md, "error": str(e)})
            try:
                # 图片注册表增量：旧路径引用剔除（文件已移动），新路径重扫
                self._update_registry_for_doc(old_md)
                self._update_registry_for_doc(new_md)
            except Exception:  # noqa: BLE001
                pass
        message = ""
        if errors:
            head = errors[0]
            message = (
                f"部分文档级联失败（{len(errors)} 项）；首项 {head.get('from')} → "
                f"{head.get('to')}: {head.get('error', '未知')}"
            )
        return {
            "status": "ok" if not errors else "partial",
            "path": new_rel,
            "files": len(moved),
            "synced": bool(sidecar_files or pending_updated),
            "sidecar_files": sidecar_files,
            "pending_updated": pending_updated,
            "errors": errors,
            "message": message or None,
        }

    def delete_file(self, rel_path: str) -> dict:
        """删除 .md 文件及其侧车。"""
        rel = self._resolve_rel_path(rel_path)
        full = self._full_path(rel)
        if not os.path.isfile(full):
            return {"status": "error", "message": "文件不存在"}
        os.remove(full)
        self._remove_sidecar(full)
        self._cache.pop(rel, None)
        touch_manifest_entry(self.kb_path, rel)
        return {"status": "ok"}

    def create_file(self, rel_path: str, body: str = "") -> dict:
        """新建 .md 文件（父目录自动创建，缺 .md 后缀自动补齐），返回相对路径。"""
        rel = self._resolve_rel_path(rel_path)
        if not rel.lower().endswith(".md"):
            rel += ".md"
        full = self._full_path(rel)
        if os.path.exists(full):
            return {"status": "error", "message": "文件已存在"}
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(body or "")
        self._cache.pop(rel, None)
        touch_manifest_entry(self.kb_path, rel)
        return {"status": "ok", "path": rel}

    def create_dir(self, rel_path: str) -> dict:
        """新建文件夹（相对知识库根）。"""
        rel = self._resolve_rel_path(rel_path)
        full = self._full_path(rel)
        if os.path.exists(full):
            return {"status": "error", "message": "目录已存在"}
        os.makedirs(full, exist_ok=True)
        return {"status": "ok", "path": rel}

    # ── 图片资产管理（.memoria/images/，文件树不可见） ──

    _IMAGE_EXTENSIONS = frozenset({
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    })

    def images_dir(self) -> str:
        """知识库图片资产目录（KB 根/.memoria/images/）。"""
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        return os.path.join(self.kb_path, MEMORIA_DIR, "images")

    def import_image(self, local_path: str) -> dict:
        """把本地图片复制到 .memoria/images/（内容去重 + 重名自动追加序号）。

        - 仅接受白名单扩展名，防止任意文件混入
        - **内容去重**：若 .memoria/images/ 已存在内容完全相同（MD5 一致）的图片，
          直接复用已有副本（返回其 relPath，`deduped=true`），不产生新副本
        - 重名策略：x.png → x-1.png → x-2.png（不覆盖、不报错，仅在同名且内容不同时触发）
        - 相对路径统一正斜杠：.memoria/images/x.png
        """
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        if not local_path:
            return {"status": "error", "message": "未选择图片"}
        ext = os.path.splitext(local_path)[1].lower()
        if ext not in self._IMAGE_EXTENSIONS:
            return {"status": "error", "message": f"不支持的图片格式: {ext or '(无扩展名)'}"}
        if not os.path.isfile(local_path):
            return {"status": "error", "message": "源文件不存在"}
        target_dir = self.images_dir()
        os.makedirs(target_dir, exist_ok=True)
        digest = self._file_md5(local_path)
        # 内容去重：已有相同内容图片则直接复用
        for entry in os.listdir(target_dir):
            full = os.path.join(target_dir, entry)
            if not os.path.isfile(full):
                continue
            if os.path.splitext(entry)[1].lower() not in self._IMAGE_EXTENSIONS:
                continue
            if self._file_md5(full) == digest:
                rel_path = f"{MEMORIA_DIR}/images/{entry}"
                return {
                    "status": "ok",
                    "relPath": rel_path,
                    "name": entry,
                    "deduped": True,
                }
        stem = os.path.splitext(os.path.basename(local_path))[0]
        name = stem + ext
        index = 1
        while os.path.exists(os.path.join(target_dir, name)):
            name = f"{stem}-{index}{ext}"
            index += 1
        shutil.copy2(local_path, os.path.join(target_dir, name))
        rel_path = f"{MEMORIA_DIR}/images/{name}"
        return {
            "status": "ok",
            "relPath": rel_path,
            "name": name,
            "deduped": False,
        }

    @staticmethod
    def _file_md5(full: str) -> str:
        """文件 MD5（流式读取，避免大图占满内存）；读取失败返回空串。"""
        h = hashlib.md5()
        try:
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()

    def list_images(self) -> list[dict]:
        """列出 .memoria/images/ 全部图片（含注册状态：referenced=是否被文档引用）。

        打开图片管理器即为「全量扫描 + 维护注册表」触发点：重建并落盘 registry.json，
        使按钮确认列表、注册表与磁盘三方一致。
        """
        target_dir = self.images_dir()
        if not os.path.isdir(target_dir):
            return []
        reg = self.rebuild_image_registry()
        refs = reg["refs"]
        out = []
        for entry in sorted(os.listdir(target_dir)):
            full = os.path.join(target_dir, entry)
            if not os.path.isfile(full):
                continue
            ext = os.path.splitext(entry)[1].lower()
            if ext not in self._IMAGE_EXTENSIONS:
                continue
            out.append({
                "name": entry,
                "relPath": f"{MEMORIA_DIR}/images/{entry}",
                "size": os.path.getsize(full),
                "referenced": entry in refs,
                "referencedBy": refs.get(entry, []),
            })
        return out

    # 图片引用识别（主正则 + 提及兜底）与注册表机制
    # 主正则：![alt](url) 或 ![alt](url "title")；url 可为裸路径（不含空白），
    # 也可用尖括号 <...> 包裹（含中文/空格等需编码字符）。
    _IMG_REF_RE = re.compile(
        r"!\[[^\]]*\]\(\s*(?:<([^>]*)>|([^)\s]+))(?:\s+\"[^\"]*\")?\s*\)"
    )
    # 提及兜底：凡正文出现 `.memoria/images/<名>`（尖括号/裸路径，含 /files/ 前缀）
    # 即视为被引用，避免解析漏判导致清理误删（data-loss 防线）。
    _IMG_MENTION_RE = re.compile(
        r"<(?:\/files)?\.memoria\/images\/([^>]*)>|"
        r"(?:\/files)?\.memoria\/images\/([^)\s\"'<>]+)"
    )

    def _doc_image_names_from_body(self, body: str) -> set[str]:
        """从单个文档正文提取指向本库 .memoria/images/ 的图片资产名（去重）。"""
        prefix = f"{MEMORIA_DIR}/images/"
        names: set[str] = set()
        for m in self._IMG_REF_RE.finditer(body):
            url = (m.group(1) or m.group(2) or "").strip()
            norm = url[8:] if url.startswith("/files/") else url
            if not norm.startswith(prefix):
                continue
            name = norm[len(prefix):].split("#", 1)[0].split("?", 1)[0]
            if name and "/" not in name and "\\" not in name:
                names.add(name)
        for m in self._IMG_MENTION_RE.finditer(body):
            name = (m.group(1) or m.group(2) or "").strip()
            name = name.split("#", 1)[0].split("?", 1)[0]
            if name and "/" not in name and "\\" not in name:
                names.add(name)
        return names

    def _doc_image_names(self, rel: str) -> set[str]:
        """读取 KB 内单个 md 文档，返回其引用的图片资产名。"""
        full = os.path.join(self.kb_path, rel)
        try:
            with open(full, "r", encoding="utf-8") as f:
                body = f.read()
        except (OSError, UnicodeDecodeError):
            return set()
        return self._doc_image_names_from_body(body)

    def _scan_image_refs(self) -> dict[str, list[str]]:
        """全量扫描 KB 全部 md 文档，返回 {.memoria/images 资产名: [引用文档相对路径]}。"""
        refs: dict[str, set[str]] = {}
        if not self.kb_path:
            return {}
        for rel in collect_md_files(self.kb_path):
            for name in self._doc_image_names(rel):
                refs.setdefault(name, set()).add(rel)
        return {k: sorted(v) for k, v in refs.items()}

    # ── 图片注册表（磁盘 .memoria/images/registry.json）：轻量，供运行期自动检查 ──
    _REGISTRY_FILE = "registry.json"
    # 自动清理宽限期：文件导入 6 小时内即使注册表暂无引用也绝不自动删，
    # 覆盖「插入→编辑→样式应用→尚未落盘」的编辑窗口，杜绝样式瞬间误删。
    _AUTO_CLEAN_GRACE_SEC = 6 * 3600

    def _image_registry_path(self) -> str | None:
        if not self.kb_path:
            return None
        return os.path.join(self.kb_path, MEMORIA_DIR, "images", self._REGISTRY_FILE)

    def _load_image_registry(self) -> dict:
        path = self._image_registry_path()
        if not path or not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        refs = data.get("refs") if isinstance(data, dict) else None
        if not isinstance(refs, dict):
            return {}
        return {"refs": refs}

    def _save_image_registry(self, reg: dict) -> None:
        path = self._image_registry_path()
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(reg, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except OSError:
            pass

    def rebuild_image_registry(self) -> dict:
        """全量扫描重建注册表并落盘（打开库时缺表/图片管理器按钮对账用）。"""
        reg = {"refs": self._scan_image_refs()}
        self._save_image_registry(reg)
        return reg

    def _registry_ensure(self) -> dict:
        """注册表缺失时用一次全量扫描重建；否则直接读盘（轻）。"""
        path = self._image_registry_path()
        if not path or not os.path.isfile(path):
            return self.rebuild_image_registry()
        return self._load_image_registry()

    def _update_registry_for_doc(self, rel: str) -> None:
        """保存单个文档后增量更新注册表：只重扫该文档，不触发删除（轻）。"""
        if not self.kb_path or not rel:
            return
        reg = self._registry_ensure()
        refs = reg.setdefault("refs", {})
        for name in list(refs.keys()):
            docs = refs[name]
            if rel in docs:
                rest = [d for d in docs if d != rel]
                if rest:
                    refs[name] = rest
                else:
                    del refs[name]
        for name in self._doc_image_names(rel):
            lst = refs.setdefault(name, [])
            if rel not in lst:
                lst.append(rel)
        self._save_image_registry(reg)

    def image_registry_auto_check(self) -> dict:
        """运行期轻量自动检查：以注册表为准，删除「注册表内无任何引用」的图片。

        触发点：打开知识库 / 定时（长间隔）由前端调用；注册表缺失时自动全量重建一次。
        """
        if not self.kb_path:
            return {"status": "ok", "deleted": [], "mode": "registry"}
        reg = self._registry_ensure()
        refs = reg.get("refs") or {}
        target_dir = os.path.join(self.kb_path, MEMORIA_DIR, "images")
        deleted: list[dict] = []
        if not os.path.isdir(target_dir):
            return {"status": "ok", "deleted": [], "mode": "registry"}
        now = time.time()
        for entry in sorted(os.listdir(target_dir)):
            full = os.path.join(target_dir, entry)
            if not os.path.isfile(full):
                continue
            if os.path.splitext(entry)[1].lower() not in self._IMAGE_EXTENSIONS:
                continue
            if entry in refs:
                continue
            # 宽限期：刚导入/编辑中尚未落盘引用的图片不自动删（用户显式清理不受此限）
            try:
                if now - os.path.getmtime(full) < self._AUTO_CLEAN_GRACE_SEC:
                    continue
            except OSError:
                continue
            try:
                os.remove(full)
            except OSError:
                continue
            deleted.append({"name": entry, "relPath": f"{MEMORIA_DIR}/images/{entry}"})
        return {"status": "ok", "deleted": deleted, "mode": "registry"}

    def unused_images(self) -> list[dict]:
        """返回未被任何文档引用的图片资产（未注册图片）。"""
        target_dir = self.images_dir()
        if not os.path.isdir(target_dir):
            return []
        refs = self._scan_image_refs()
        out = []
        for entry in sorted(os.listdir(target_dir)):
            full = os.path.join(target_dir, entry)
            if not os.path.isfile(full):
                continue
            ext = os.path.splitext(entry)[1].lower()
            if ext not in self._IMAGE_EXTENSIONS:
                continue
            if entry not in refs:
                out.append({
                    "name": entry,
                    "relPath": f"{MEMORIA_DIR}/images/{entry}",
                    "size": os.path.getsize(full),
                })
        return out

    def cleanup_unused_images(self, rel_paths: list[str] | None = None) -> dict:
        """图片管理器按钮触发（用户显式）：全量扫描 → 重建注册表 → 删除未引用图片。

        rel_paths 为 None 时清理全部未引用图片；否则仅清理列表中属于
        未引用集合的图片（不误删已引用资产）。返回删除清单。
        """
        target_dir = self.images_dir()
        if not os.path.isdir(target_dir):
            return {"status": "ok", "deleted": []}
        reg = self.rebuild_image_registry()
        refs = reg["refs"]
        prefix = f"{MEMORIA_DIR}/images/"
        unused = {
            e for e in os.listdir(target_dir)
            if os.path.isfile(os.path.join(target_dir, e))
            and os.path.splitext(e)[1].lower() in self._IMAGE_EXTENSIONS
            and e not in refs
        }
        if rel_paths:
            names: set[str] = set()
            for rp in rel_paths:
                norm = (rp or "").replace("\\", "/")
                if norm.startswith(prefix):
                    names.add(norm[len(prefix):])
                elif "/" not in norm and norm:
                    names.add(norm)
            targets = names & unused
        else:
            targets = unused
        deleted = []
        for name in sorted(targets):
            full = os.path.join(target_dir, name)
            try:
                os.remove(full)
            except OSError:
                continue
            deleted.append({
                "name": name,
                "relPath": f"{MEMORIA_DIR}/images/{name}",
            })
        return {"status": "ok", "deleted": deleted}

    # ── 图片引用诊断与修复（触发入口：图片管理 → 检查异常引用） ──────
    # 注册机制基于全库扫描 md 引用；若 md 里的引用格式无法被 _scan_image_refs
    # 识别（典型：文件名含空格/中文的裸 URL，如 `![x](.memoria/images/屏幕截图 2026.png)`，
    # 未用尖括号包裹），该图片即使存在也会被判为"未引用"，保存时被自动清理误删。
    # 以下方法用于发现并修复这类"已引用但未注册"的图片引用。

    @staticmethod
    def _parse_image_ref_url(raw: str) -> tuple[str | None, bool]:
        """解析图片引用括号内文本，返回 (意图URL, 是否可被注册规则识别)。

        - `<url>` 尖括号形式：可注册（允许含空格/中文）
        - 裸 URL：去掉尾部 `"title"` 后若仍含空白 → 不可注册（URL 在空格处被截断）
        """
        m = re.match(r"^<([^>]*)>", raw)
        if m:
            return (m.group(1).strip(), True)
        intent = re.sub(r'\s+"[^"]*"$', "", raw).strip()
        token = re.match(r"^([^)\s]+)", intent)
        if not token:
            return (None, False)
        return (intent, token.group(1) == intent)

    def diagnose_image_refs(self) -> dict:
        """诊断"文档引用了图片但未成功注册"的情况。

        - unregistered: 引用指向 .memoria/images/ 但格式不可注册（可一键修复）
        - missing:      引用格式可注册但 .memoria/images/ 下无对应文件
        """
        out: dict[str, list[dict]] = {"unregistered": [], "missing": []}
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        prefix = f"{MEMORIA_DIR}/images/"
        img_dir = self.images_dir()
        for rel in collect_md_files(self.kb_path):
            full = os.path.join(self.kb_path, rel)
            try:
                with open(full, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for ln, line in enumerate(lines, 1):
                if "![" not in line:
                    continue
                for m in re.finditer(r"!\[[^\]]*\]\(([^)]*)\)", line):
                    url, registrable = self._parse_image_ref_url(m.group(1).strip())
                    if url is None:
                        continue
                    norm = url[8:] if url.startswith("/files/") else url
                    if not norm.startswith(prefix):
                        continue
                    name = norm[len(prefix):].split("#", 1)[0].split("?", 1)[0]
                    if not name or "/" in name or "\\" in name:
                        continue
                    item = {
                        "doc": rel,
                        "line": ln,
                        "src": m.group(0),
                        "url": norm,
                        "exists": os.path.isfile(os.path.join(img_dir, name)),
                    }
                    if not registrable:
                        out["unregistered"].append(item)
                    elif not item["exists"]:
                        out["missing"].append(item)
        return {"status": "ok", **out}

    @staticmethod
    def _rewrite_bare_space_refs(text: str, prefix: str) -> tuple[str, int]:
        """把指向 prefix 的"裸 URL 含空格"图片引用改写为尖括号形式。"""
        count = 0

        def repl(m: re.Match) -> str:
            nonlocal count
            raw = m.group(1).strip()
            url, registrable = DocumentService._parse_image_ref_url(raw)
            if url is None or registrable:
                return m.group(0)
            norm = url[8:] if url.startswith("/files/") else url
            if not norm.startswith(prefix):
                return m.group(0)
            alt_m = re.match(r"!\[([^\]]*)\]", m.group(0))
            alt = alt_m.group(1) if alt_m else ""
            title_m = re.search(r'"[^"]*"\s*$', raw)
            suffix = f" {title_m.group(0).strip()}" if title_m else ""
            count += 1
            return f"![{alt}](<{norm}>{suffix})"

        new_text = re.sub(r"!\[[^\]]*\]\(([^)]*)\)", repl, text)
        return (new_text, count)

    def fix_unregistered_image_refs(self) -> dict:
        """一键修复：把格式不可注册的 .memoria/images/ 图片引用改写为尖括号形式。"""
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        prefix = f"{MEMORIA_DIR}/images/"
        changed: list[dict] = []
        total = 0
        for rel in collect_md_files(self.kb_path):
            full = os.path.join(self.kb_path, rel)
            try:
                with open(full, "r", encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            new_text, n = self._rewrite_bare_space_refs(text, prefix)
            if n:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(new_text)
                touch_manifest_entry(self.kb_path, rel)
                changed.append({"doc": rel, "fixed": n})
                total += n
        return {"status": "ok", "fixed": total, "changed": changed}

    def _read_body(self, rel_path: str) -> tuple[str, dict | None, list[str]]:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        full = os.path.join(self.kb_path, rel_path)
        if not os.path.isfile(full):
            raise FileNotFoundError("文件不存在")
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, fm = strip_frontmatter(raw)
        # 空文件保证至少一行，否则前端编辑器渲染 0 行（无行号、不可编辑）
        return body, fm, body.splitlines() or [""]

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
            err_msgs = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in validation["errors"]
            ]
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(err_msgs),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        sync_pending_for_file(self.kb_path, rel_path.replace("\\", "/"))
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
        temp_kp: dict | None = None,
    ) -> dict:
        kp_id = (kp_id or "").strip()
        if not self.kb_path or not kp_id:
            raise RuntimeError("未打开知识库")
        doc = self.load_document(rel_path)
        if doc.get("status") != "ok":
            return doc
        kp = next((k for k in doc.get("knowledge_points") or [] if k.get("id") == kp_id), None)
        if not kp:
            if not temp_kp:
                return {"status": "error", "message": f"知识点不存在：{kp_id}"}
            kp = self._build_temp_kp(kp_id, temp_kp)
        from memoria.services.suggest_metadata import suggest_tags

        return suggest_tags(
            kb_path=self.kb_path,
            rel_path=rel_path,
            kp_id=kp_id,
            lines=doc.get("lines") or [],
            kp=kp,
            limit=int(limit) if limit else 8,
        )

    def suggest_description_api(self, rel_path: str, kp_id: str, temp_kp: dict | None = None) -> dict:
        kp_id = (kp_id or "").strip()
        if not self.kb_path or not kp_id:
            raise RuntimeError("未打开知识库")
        doc = self.load_document(rel_path)
        if doc.get("status") != "ok":
            return doc
        kp = next((k for k in doc.get("knowledge_points") or [] if k.get("id") == kp_id), None)
        if not kp:
            if not temp_kp:
                return {"status": "error", "message": f"知识点不存在：{kp_id}"}
            kp = self._build_temp_kp(kp_id, temp_kp)
        from memoria.services.suggest_metadata import suggest_description

        return suggest_description(
            kb_path=self.kb_path,
            rel_path=rel_path,
            kp_id=kp_id,
            lines=doc.get("lines") or [],
            kp=kp,
        )

    @staticmethod
    def _build_temp_kp(kp_id: str, temp_kp: dict) -> dict:
        """从前端临时信息构造 kp 对象（用于创建模式未保存时的建议）。"""
        start_line = int(temp_kp.get("start_line") or 1)
        end_line = int(temp_kp.get("end_line") or start_line)
        return {
            "id": kp_id,
            "name": str(temp_kp.get("name") or ""),
            "range": {
                "start": {"line_hint": start_line},
                "end": {"line_hint": end_line},
            },
            "tags": [],
            "aliases": [],
            "description": "",
        }

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
            err_msgs = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in validation["errors"]
            ]
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(err_msgs),
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
        alias_candidates: list | None = None,
        aliases: list[str] | None = None,
        description_candidates: list | None = None,
    ) -> dict:
        """更新侧车知识点元数据（名称、标签、描述、各类候选）。"""
        kp_id = (kp_id or "").strip()
        if not kp_id:
            return {"status": "error", "message": "知识点 id 不能为空"}
        if (
            name is None
            and tags is None
            and description is None
            and tag_candidates is None
            and alias_candidates is None
            and aliases is None
            and description_candidates is None
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

        if aliases is not None:
            cleaned_aliases: list[str] = []
            seen_a: set[str] = set()
            for alias in aliases:
                a = str(alias).strip()
                if a and a.lower() not in seen_a:
                    seen_a.add(a.lower())
                    cleaned_aliases.append(a)
            entry["aliases"] = cleaned_aliases

        if alias_candidates is not None:
            alias_exclude = {
                str(a).strip().lower()
                for a in (entry.get("aliases") or [])
                if str(a).strip()
            }
            name_lower = str(entry.get("name") or "").strip().lower()
            if name_lower:
                alias_exclude.add(name_lower)
            entry["alias_candidates"] = _normalize_alias_candidates(
                alias_candidates,
                exclude=alias_exclude,
            )

        if description_candidates is not None:
            entry["description_candidates"] = _normalize_description_candidates(
                description_candidates
            )

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            err_msgs = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in validation["errors"]
            ]
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(err_msgs),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        self._cache.pop(rel_path, None)

        if self.kb_path:
            from memoria.services.search_aux import mark_aux_promoted

            promoted_tags = [
                t for t in (entry.get("tags") or [])
                if isinstance(t, str) and t.strip()
            ]
            promoted_aliases = [
                a for a in (entry.get("aliases") or [])
                if isinstance(a, str) and a.strip()
            ]
            if promoted_tags or promoted_aliases:
                try:
                    mark_aux_promoted(
                        self.kb_path,
                        kp_id,
                        auto_tags=promoted_tags if tags is not None else None,
                        aliases=promoted_aliases if aliases is not None else None,
                    )
                except OSError:
                    pass

        return self.load_document(rel_path)

    def sync_implicit_proposals_api(self, rel_path: str, kp_id: str, temp_kp: dict | None = None) -> dict:
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库", "available": False}
        from memoria.services.proposals import sync_kp_implicit_proposals

        return sync_kp_implicit_proposals(
            kb_path=self.kb_path,
            rel_path=rel_path,
            kp_id=kp_id,
            temp_kp=temp_kp,
        )

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
            err_msgs = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in validation["errors"]
            ]
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(err_msgs),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        sync_pending_for_file(self.kb_path, rel_path.replace("\\", "/"))
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

    def format_text(
        self,
        rel_path: str,
        line_number: int,
        start_col: int,
        end_col: int,
        format_type: str,
        color: str | None = None,
    ) -> dict:
        """在源码指定行、列范围包裹格式语法，写回文件，返回更新后的文档。"""
        body, fm, lines = self._read_body(rel_path)
        idx = line_number - 1
        if idx < 0 or idx >= len(lines):
            return {"status": "error", "message": f"行号 {line_number} 超出范围"}
        line = lines[idx]
        if start_col < 0 or end_col > len(line) or start_col > end_col:
            return {"status": "error", "message": f"列范围 [{start_col},{end_col}) 无效 (行长 {len(line)})"}

        selected = line[start_col:end_col]

        if format_type == "bold":
            prefix, suffix = "**", "**"
        elif format_type == "italic":
            prefix, suffix = "*", "*"
        elif format_type == "highlight":
            c = color or "yellow"
            if c == "yellow":
                prefix, suffix = "[[\\h|", "]]"
            else:
                prefix, suffix = f"[[\\h:{c}|", "]]"
        elif format_type == "fontcolor":
            c = color or "red"
            prefix, suffix = f"[[\\c:{c}|", "]]"
        else:
            return {"status": "error", "message": f"未知格式类型: {format_type}"}

        new_line = line[:start_col] + prefix + selected + suffix + line[end_col:]
        lines[idx] = new_line
        new_body = "\n".join(lines)
        self._write_body(rel_path, new_body, fm)
        return self.load_document(rel_path)

    def sync_manifest(self) -> dict:
        if not self.kb_path:
            raise RuntimeError("未打开知识库")
        moves = detect_path_moves(self.kb_path)
        if moves:
            return {
                "status": "error",
                "code": "manifest_blocked_by_path_moves",
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
            err_msgs = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in validation["errors"]
            ]
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(err_msgs),
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

    # ── U12: 纯边 & no_build 管理 ──────────────────────────────────

    def create_edge(
        self,
        rel_path: str,
        source_id: str,
        target_id: str,
        edge_type: str,
        *,
        relevance: float | None = None,
    ) -> dict:
        """在 sidecar edges[] 中创建纯边。"""
        from memoria.graph.edge_types import normalize_edge_type, default_relevance

        source_id = (source_id or "").strip()
        target_id = (target_id or "").strip()
        et = normalize_edge_type(edge_type)
        if not source_id or not target_id or not et:
            return {"status": "error", "message": "source_id、target_id、edge_type 均不能为空"}
        if source_id == target_id:
            return {"status": "error", "message": "source_id 与 target_id 不能相同"}

        # 验证 source_id 存在于该文件 KP
        body, _fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path) or {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "file": rel_path.replace("\\", "/"),
            "knowledge_points": [],
        }
        kps = sidecar.get("knowledge_points") or []
        if not any(k.get("id") == source_id for k in kps):
            return {"status": "error", "message": f"source_id 不存在：{source_id}"}

        # 验证 target_id 可解析
        from memoria.graph.edge_derivation import build_target_kp_resolver
        resolve = build_target_kp_resolver(self.kb_path)
        if not resolve(target_id):
            return {"status": "error", "message": f"target_id 无法解析：{target_id}"}

        edges = sidecar.setdefault("edges", [])
        # 检查是否已存在相同边
        for e in edges:
            if not isinstance(e, dict):
                continue
            if (
                e.get("type") == et
                and (e.get("source_id") or "").strip() == source_id
                and target_id in _normalize_targets_list(e.get("targets"))
                and not e.get("no_build")
            ):
                return {"status": "error", "message": "该边已存在"}

        rel_val = (
            max(0.0, min(1.0, float(relevance)))
            if relevance is not None
            else default_relevance(et)
        )
        edges.append({
            "type": et,
            "source_id": source_id,
            "targets": [target_id],
            "relevance": rel_val,
        })

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            err_msgs = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in validation["errors"]
            ]
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(err_msgs),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        self._cache.pop(rel_path, None)
        return {"status": "ok", "edge": {
            "type": et,
            "source_id": source_id,
            "targets": [target_id],
            "relevance": rel_val,
        }}

    def delete_edge(
        self,
        rel_path: str,
        source_id: str,
        target_id: str,
        edge_type: str,
    ) -> dict:
        """删除/切换一条边。
        - 纯 sidecar edges[] 边：直接移除
        - 自动推导的 contain 边：添加 no_build=True 标记
        """
        from memoria.graph.edge_types import normalize_edge_type, EDGE_CONTAIN

        source_id = (source_id or "").strip()
        target_id = (target_id or "").strip()
        et = normalize_edge_type(edge_type)
        if not source_id or not target_id or not et:
            return {"status": "error", "message": "source_id、target_id、edge_type 均不能为空"}

        body, _fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path) or {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "file": rel_path.replace("\\", "/"),
            "knowledge_points": [],
        }
        edges = sidecar.setdefault("edges", [])

        # 尝试从 edges[] 中找到并删除纯边
        found_pure = False
        new_edges = []
        for e in edges:
            if not isinstance(e, dict):
                new_edges.append(e)
                continue
            if (
                e.get("type") == et
                and (e.get("source_id") or "").strip() == source_id
                and target_id in _normalize_targets_list(e.get("targets"))
                and not e.get("no_build")
            ):
                found_pure = True
                continue  # 跳过即删除
            new_edges.append(e)
        sidecar["edges"] = new_edges

        # 如果没找到纯边，且是 contain 类型，则添加 no_build 标记
        if not found_pure and et == EDGE_CONTAIN:
            sidecar["edges"].append({
                "type": EDGE_CONTAIN,
                "source_id": source_id,
                "targets": [target_id],
                "no_build": True,
            })

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            err_msgs = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in validation["errors"]
            ]
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(err_msgs),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        self._cache.pop(rel_path, None)
        return {
            "status": "ok",
            "deleted_pure": found_pure,
            "no_build_added": not found_pure and et == EDGE_CONTAIN,
        }

    def set_contain_no_build(
        self,
        rel_path: str,
        parent_id: str,
        child_id: str,
        *,
        no_build: bool = True,
    ) -> dict:
        """标记/取消标记 contain 边的 no_build。"""
        from memoria.graph.edge_types import EDGE_CONTAIN

        parent_id = (parent_id or "").strip()
        child_id = (child_id or "").strip()
        if not parent_id or not child_id:
            return {"status": "error", "message": "parent_id 和 child_id 不能为空"}

        body, _fm, lines = self._read_body(rel_path)
        full = os.path.join(self.kb_path, rel_path)
        sidecar = load_sidecar_for_md(full, self.kb_path) or {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "file": rel_path.replace("\\", "/"),
            "knowledge_points": [],
        }
        edges = sidecar.setdefault("edges", [])

        if no_build:
            # 添加 no_build 条目（幂等：如果已存在则不重复添加）
            exists = False
            for e in edges:
                if not isinstance(e, dict):
                    continue
                if (
                    e.get("type") == EDGE_CONTAIN
                    and (e.get("source_id") or "").strip() == parent_id
                    and child_id in _normalize_targets_list(e.get("targets"))
                    and e.get("no_build")
                ):
                    exists = True
                    break
            if not exists:
                edges.append({
                    "type": EDGE_CONTAIN,
                    "source_id": parent_id,
                    "targets": [child_id],
                    "no_build": True,
                })
        else:
            # 移除 no_build 条目
            sidecar["edges"] = [
                e for e in edges
                if not (
                    isinstance(e, dict)
                    and e.get("type") == EDGE_CONTAIN
                    and (e.get("source_id") or "").strip() == parent_id
                    and child_id in _normalize_targets_list(e.get("targets"))
                    and e.get("no_build")
                )
            ]

        sidecar["schema_version"] = SIDECAR_SCHEMA_VERSION
        sidecar["file"] = rel_path.replace("\\", "/")
        validation = validate_sidecar(sidecar, sidecar["file"], lines)
        if not validation["ok"]:
            err_msgs = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in validation["errors"]
            ]
            return {
                "status": "error",
                "message": "配置校验失败: " + "; ".join(err_msgs),
                "validation": validation,
            }

        self._write_sidecar(rel_path.replace("\\", "/"), sidecar)
        self._cache.pop(rel_path, None)
        return {"status": "ok", "no_build": no_build}
