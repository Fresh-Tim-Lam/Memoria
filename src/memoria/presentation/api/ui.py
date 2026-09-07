"""前端 API 桥接层（与桌面壳解耦）。"""

from __future__ import annotations

import os

from typing import TYPE_CHECKING

from memoria import __version__
from memoria.services.document import DocumentService
from memoria.services.import_engine import (
    ImportConflict,
    ImportResult,
    ImportScanResult,
    execute_import,
    parse_flat_file,
    pre_scan_import,
)
from memoria.storage.ui_settings import load_ui_settings, save_ui_settings, settings_path

if TYPE_CHECKING:
    from memoria.app.shell.host import WindowHost


class UIAPI:
    """暴露给前端 JS 的 API；异常转为 status dict。"""

    def __init__(
        self, kb_path: str | None = None, host: WindowHost | None = None
    ) -> None:
        self._svc = DocumentService(kb_path=kb_path)
        self._host = host
        if kb_path:
            from memoria.presentation.static_server import set_kb_root
            set_kb_root(kb_path)

    @property
    def kb_path(self) -> str | None:
        return self._svc.kb_path

    @kb_path.setter
    def kb_path(self, path: str | None) -> None:
        if path:
            self._svc.set_kb_path(path)
        else:
            self._svc.kb_path = None

    @property
    def frameless(self) -> bool:
        return bool(self._host and self._host.frameless)

    def select_directory(self) -> str:
        if self._host is None:
            return ""
        path = self._host.pick_directory()
        if path:
            self._svc.set_kb_path(path)
            from memoria.presentation.static_server import set_kb_root
            set_kb_root(path)
            return path
        return ""

    def set_kb_path(self, path: str) -> dict:
        try:
            self._svc.set_kb_path(path)
            from memoria.presentation.static_server import set_kb_root
            set_kb_root(path)
            return {"status": "ok", "path": path}
        except FileNotFoundError as e:
            return {"status": "error", "message": str(e)}

    def ensure_kb_root(self, path: str) -> dict:
        """仅同步服务端 _kb_root，不触发其他副作用（如重载 KB）"""
        from memoria.presentation.static_server import set_kb_root
        set_kb_root(path)
        return {"status": "ok"}

    def get_kb_path(self) -> str:
        return self._svc.kb_path or ""

    def get_remembered_kb_path(self) -> str:
        """前端启动时询问“是否自动打开上次知识库”。

        「新窗口」（MEMORIA_NO_KB=1）进程返回空串：前端据此停在欢迎页，
        不触发 resolveStartupKbPath 的 remembered 自动打开分支。
        """
        from memoria.app.runtime import no_auto_kb_env
        from memoria.storage.ui_settings import resolve_last_kb_path

        if no_auto_kb_env():
            return ""
        path = resolve_last_kb_path()
        return path or ""

    def get_recent_kbs(self) -> dict:
        """最近打开的知识库（按上次打开时间降序，固定数量）。"""
        from pathlib import Path

        from memoria.storage.ui_settings import resolve_recent_kb_paths

        paths = resolve_recent_kb_paths()
        # 显示名默认取目录名；重名时附加父目录名以便区分
        by_name: dict[str, int] = {}
        for p in paths:
            by_name[Path(p).name] = by_name.get(Path(p).name, 0) + 1
        items = []
        for p in paths:
            path = Path(p)
            name = path.name or p
            if by_name.get(name, 0) > 1:
                name = f"{path.parent.name} / {name}"
            items.append({"path": p, "name": name})
        return {"status": "ok", "items": items}

    def open_new_window(self, kb_path: str = "") -> dict:
        """文件 → 新窗口 / 打开最近：启动独立的新 Memoria 窗口进程。

        kb_path 为空 → 新窗口不打开任何知识库（欢迎页）。
        """
        from memoria.app.runtime import spawn_window

        return spawn_window(kb_path=kb_path or None)

    def close_kb(self) -> dict:
        self._svc.close_kb()
        from memoria.presentation.static_server import set_kb_root
        set_kb_root(None)
        return {"status": "ok"}

    def list_files(self) -> dict:
        try:
            data = self._svc.list_files()
            return {"status": "ok", "files": data["files"], "dirs": data["dirs"]}
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def file_rename(self, old_rel: str, new_name: str) -> dict:
        try:
            return self._svc.rename_file(old_rel, new_name)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def file_delete(self, rel_path: str) -> dict:
        try:
            return self._svc.delete_file(rel_path)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def file_create(self, rel_path: str, body: str = "") -> dict:
        try:
            return self._svc.create_file(rel_path, body=body)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def dir_create(self, rel_path: str) -> dict:
        try:
            return self._svc.create_dir(rel_path)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def load_document(self, rel_path: str) -> dict:
        try:
            return self._svc.load_document(rel_path)
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def write_map_log(self, rel_path: str, body: str) -> dict:
        """写入映射调试日志到文件（追加模式）。"""
        import os
        if not self._svc.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        full = os.path.join(self._svc.kb_path, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        try:
            with open(full, "a", encoding="utf-8") as f:
                f.write(body)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def write_debug_log(self, filename: str, body: str) -> dict:
        """写入调试日志到 d:\\AAA_Jupyter\\Memoria\\logs\\ 目录（追加模式）。"""
        import os
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        full = os.path.join(logs_dir, filename)
        try:
            with open(full, "a", encoding="utf-8") as f:
                f.write(body)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def save_document(self, rel_path: str, body: str) -> dict:
        try:
            return self._svc.save_document(rel_path, body)
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def confirm_kp_range(
        self,
        rel_path: str,
        kp_id: str,
        name: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        try:
            return self._svc.confirm_kp_range(
                rel_path, kp_id, name, start_line, end_line
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def check_kp_id(self, kp_id: str, rel_path: str = "") -> dict:
        try:
            return self._svc.check_kp_id(kp_id, rel_path or None)
        except RuntimeError as e:
            return {"status": "error", "message": str(e), "available": False}

    def search(
        self,
        query: str,
        scope: str = "kb",
        limit: int = 20,
        modes: str | None = None,
        rel_path: str = "",
    ) -> dict:
        try:
            return self._svc.search_api(
                query,
                scope=scope,
                limit=limit,
                modes=modes,
                rel_path=rel_path or None,
            )
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def suggest_kp_merge(self, kp_id: str, rel_path: str = "") -> dict:
        try:
            return self._svc.suggest_kp_merge_api(kp_id, rel_path or None)
        except RuntimeError as e:
            return {"status": "error", "message": str(e), "available": False}

    def suggest_tags(self, rel_path: str, kp_id: str, limit: int = 8, temp_kp: dict | None = None) -> dict:
        try:
            return self._svc.suggest_tags_api(rel_path, kp_id, limit=limit, temp_kp=temp_kp)
        except RuntimeError as e:
            return {"status": "error", "message": str(e), "available": False}

    def suggest_description(self, rel_path: str, kp_id: str, temp_kp: dict | None = None) -> dict:
        try:
            return self._svc.suggest_description_api(rel_path, kp_id, temp_kp=temp_kp)
        except RuntimeError as e:
            return {"status": "error", "message": str(e), "available": False}

    def suggest_group_labels(self, groups: list) -> dict:
        try:
            return self._svc.suggest_group_labels_api(groups or [])
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def pick_snippet_line(
        self,
        rel_path: str,
        kp_id: str,
        which: str,
        line_number: int,
    ) -> dict:
        try:
            return self._svc.pick_snippet_line(rel_path, kp_id, which, line_number)
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def update_kp(
        self,
        rel_path: str,
        kp_id: str,
        name: str | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
        tag_candidates: list | None = None,
        alias_candidates: list | None = None,
        aliases: list[str] | None = None,
        description_candidates: list | None = None,
    ) -> dict:
        try:
            kwargs: dict = {}
            if name is not None:
                kwargs["name"] = name
            if tags is not None:
                kwargs["tags"] = tags
            if description is not None:
                kwargs["description"] = description
            if tag_candidates is not None:
                kwargs["tag_candidates"] = tag_candidates
            if alias_candidates is not None:
                kwargs["alias_candidates"] = alias_candidates
            if aliases is not None:
                kwargs["aliases"] = aliases
            if description_candidates is not None:
                kwargs["description_candidates"] = description_candidates
            if not kwargs:
                return {"status": "error", "message": "无更新字段"}
            return self._svc.update_kp(rel_path, kp_id, **kwargs)
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def sync_implicit_proposals(self, rel_path: str, kp_id: str, temp_kp: dict | None = None) -> dict:
        try:
            return self._svc.sync_implicit_proposals_api(rel_path, kp_id, temp_kp=temp_kp)
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def delete_kp(self, rel_path: str, kp_id: str) -> dict:
        try:
            return self._svc.delete_kp(rel_path, kp_id)
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def rename_kp_id(self, old_id: str, new_id: str) -> dict:
        try:
            return self._svc.rename_kp_id(old_id, new_id)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def resolve_link(self, target_id: str) -> dict:
        try:
            return self._svc.resolve_link(target_id)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def resolve_links(self, target_ids: list[str]) -> dict:
        try:
            return self._svc.resolve_links(target_ids)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def get_link_targets(self) -> dict:
        try:
            return self._svc.get_link_targets()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def get_graph_data(self) -> dict:
        try:
            return self._svc.get_graph_data()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def get_graph_audit(self) -> dict:
        try:
            return self._svc.get_graph_audit()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def build_kb(self) -> dict:
        try:
            return self._svc.build_kb()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def validate_kb(self) -> dict:
        try:
            return self._svc.validate_kb()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def sync_manifest(self) -> dict:
        try:
            return self._svc.sync_manifest()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def sync_pending(self) -> dict:
        try:
            return self._svc.sync_pending()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def repair_path_cascade(self, apply: bool = False) -> dict:
        try:
            return self._svc.repair_path_cascade(apply=apply)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def get_kb_pending(self) -> dict:
        try:
            return self._svc.get_kb_pending()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def dismiss_pending(self, pending_id: str) -> dict:
        try:
            return self._svc.dismiss_pending(pending_id)
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def save_link_route(
        self,
        rel_path: str,
        anchor_text: str,
        target_ids: list[str],
        display_text: str = "",
        edge_type: str = "",
        source_id: str = "",
        old_anchor_text: str = "",
        old_display_text: str = "",
        occurrence: int = 0,
        update_markdown: bool = True,
        pool_ids: list[str] | None = None,
        target_edges: dict | None = None,
        relevance: float | None = None,
    ) -> dict:
        try:
            return self._svc.save_link_route(
                rel_path,
                anchor_text,
                target_ids,
                display_text=display_text or None,
                edge_type=edge_type or None,
                target_edges=target_edges,
                relevance=relevance,
                source_id=source_id or None,
                old_anchor_text=old_anchor_text or None,
                old_display_text=old_display_text or None,
                occurrence=occurrence,
                update_markdown=update_markdown,
                pool_ids=pool_ids,
            )
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            return {"status": "error", "message": str(e)}

    def delete_link_route(
        self,
        rel_path: str,
        anchor_text: str,
        occurrence: int = 0,
    ) -> dict:
        try:
            return self._svc.delete_link_route(
                rel_path, anchor_text, occurrence=occurrence
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def remove_link(
        self,
        rel_path: str,
        anchor_text: str,
        display_text: str = "",
        edge_hint: str = "",
        occurrence: int = 0,
    ) -> dict:
        try:
            return self._svc.remove_link(
                rel_path,
                anchor_text,
                display_text=display_text or None,
                edge_hint=edge_hint or None,
                occurrence=occurrence,
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def scan_link_text_matches(
        self,
        rel_path: str,
        anchor_text: str,
        search_options: dict | None = None,
    ) -> dict:
        try:
            return self._svc.scan_link_text_matches_api(
                rel_path, anchor_text, search_options=search_options
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def suggest_link_anchor_texts(
        self,
        rel_path: str,
        query: str,
        search_options: dict | None = None,
    ) -> dict:
        try:
            return self._svc.suggest_link_anchor_texts_api(
                rel_path, query, search_options=search_options
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def detach_link_instance(
        self,
        rel_path: str,
        anchor_text: str,
        line_number: int,
    ) -> dict:
        try:
            return self._svc.detach_link_instance(rel_path, anchor_text, line_number)
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def format_text(
        self,
        rel_path: str,
        line_number: int,
        start_col: int,
        end_col: int,
        format_type: str,
        color: str | None = None,
    ) -> dict:
        try:
            return self._svc.format_text(
                rel_path, line_number, start_col, end_col, format_type, color
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def apply_link_instances(
        self,
        rel_path: str,
        anchor_text: str,
        target_ids: list[str],
        selected_lines: list[int],
        display_text: str = "",
        edge_type: str = "",
        source_id: str = "",
        old_anchor_text: str = "",
        occurrence: int = 0,
        pool_ids: list[str] | None = None,
        search_options: dict | None = None,
        target_edges: dict | None = None,
        relevance: float | None = None,
    ) -> dict:
        try:
            return self._svc.apply_link_instances(
                rel_path,
                anchor_text,
                target_ids,
                selected_lines,
                display_text=display_text or None,
                edge_type=edge_type or None,
                target_edges=target_edges,
                relevance=relevance,
                source_id=source_id or None,
                old_anchor_text=old_anchor_text or None,
                occurrence=occurrence,
                pool_ids=pool_ids,
                search_options=search_options,
            )
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            return {"status": "error", "message": str(e)}

    def wrap_text_as_link(
        self,
        rel_path: str,
        selected_text: str,
        anchor_text: str,
        target_ids: list[str] | None = None,
        display_text: str = "",
        edge_type: str = "",
        source_id: str = "",
        target_edges: dict | None = None,
        relevance: float | None = None,
    ) -> dict:
        try:
            return self._svc.wrap_text_as_link(
                rel_path,
                selected_text,
                anchor_text,
                target_ids=target_ids,
                display_text=display_text or None,
                edge_type=edge_type or None,
                target_edges=target_edges,
                source_id=source_id or None,
                relevance=relevance,
            )
        except (RuntimeError, FileNotFoundError, ValueError) as e:
            return {"status": "error", "message": str(e)}

    def suggest_link_relevance(
        self,
        rel_path: str,
        anchor_text: str,
        target_id: str = "",
        target_ids: list[str] | None = None,
        edge_type: str = "",
        source_id: str = "",
    ) -> dict:
        try:
            return self._svc.suggest_link_relevance_api(
                rel_path,
                anchor_text,
                target_id=target_id,
                target_ids=target_ids,
                edge_type=edge_type or None,
                source_id=source_id or None,
            )
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}

    def get_ui_settings(self) -> dict:
        try:
            path = settings_path()
            root = path.parent.parent
            rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
            return {
                "status": "ok",
                "settings": load_ui_settings(),
                "config_dir": str(path.parent),
                "settings_file": str(path),
                "settings_rel": rel,
            }
        except OSError as e:
            return {"status": "error", "message": str(e)}

    def get_window_chrome(self) -> dict:
        host = self._host
        return {
            "status": "ok",
            "frameless": bool(host and host.frameless),
            "maximized": bool(host and host.maximized),
            "shell": host.kind if host else "none",
            "version": __version__,
            "min_width": 900,
            "min_height": 600,
        }

    def window_resize_to(self, width: int, height: int, anchor: str) -> dict:
        if self._host is None:
            return {"status": "error", "message": "窗口不可用"}
        w = max(900, int(width))
        h = max(600, int(height))
        try:
            self._host.resize(w, h, str(anchor or "se"))
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def window_move_to(self, x: int, y: int) -> dict:
        if self._host is None:
            return {"status": "error", "message": "窗口不可用"}
        try:
            self._host.move_to(int(x), int(y))
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def window_start_move(self) -> dict:
        if self._host is None:
            return {"status": "error", "message": "窗口不可用"}
        try:
            self._host.start_move()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def window_begin_drag(self) -> dict:
        """前端检测到标题栏拖拽动作后调用：后端在 UI 线程发起原生
        标题栏拖动（ReleaseCapture + WM_NCLBUTTONDOWN HTCAPTION），
        鼠标捕获 / Aero Snap / 最大化下拉还原全部由 Windows 原生处理。"""
        if self._host is None:
            return {"status": "error", "message": "窗口不可用"}
        try:
            self._host.begin_drag()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def window_restore_from_drag(
        self, screen_x: float, screen_y: float, ratio_x: float
    ) -> dict:
        if self._host is None:
            return {"status": "error", "message": "窗口不可用"}
        if not self._host.maximized:
            return {"status": "ok", "maximized": False}
        try:
            px, py, w, h = self._host.restore_from_drag(
                screen_x, screen_y, ratio_x
            )
            return {
                "status": "ok",
                "maximized": False,
                "x": px,
                "y": py,
                "width": w,
                "height": h,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def window_minimize(self) -> dict:
        if self._host is None:
            return {"status": "error", "message": "窗口不可用"}
        try:
            self._host.minimize()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def window_toggle_maximize(self) -> dict:
        if self._host is None:
            return {"status": "error", "message": "窗口不可用"}
        try:
            maximized = self._host.toggle_maximize()
            return {"status": "ok", "maximized": maximized}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def window_close(self) -> dict:
        if self._host is None:
            return {"status": "error", "message": "窗口不可用"}
        try:
            self._host.close()
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def save_ui_settings(self, partial: dict) -> dict:
        try:
            if not isinstance(partial, dict):
                return {"status": "error", "message": "settings 须为对象"}
            merged = save_ui_settings(partial)
            return {"status": "ok", "settings": merged}
        except OSError as e:
            return {"status": "error", "message": str(e)}

    # ── U12: 纯边 & no_build 管理 ──────────────────────────────────

    def create_edge(
        self,
        rel_path: str,
        source_id: str,
        target_id: str,
        edge_type: str,
        relevance: float | None = None,
    ) -> dict:
        try:
            return self._svc.create_edge(
                rel_path, source_id, target_id, edge_type,
                relevance=relevance,
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def delete_edge(
        self,
        rel_path: str,
        source_id: str,
        target_id: str,
        edge_type: str,
    ) -> dict:
        try:
            return self._svc.delete_edge(
                rel_path, source_id, target_id, edge_type,
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    def set_contain_no_build(
        self,
        rel_path: str,
        parent_id: str,
        child_id: str,
        no_build: bool = True,
    ) -> dict:
        try:
            return self._svc.set_contain_no_build(
                rel_path, parent_id, child_id, no_build=no_build,
            )
        except (RuntimeError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    # ── R11: 平面文件导入 ──────────────────────────────────────────

    def select_import_files(self) -> list[dict]:
        """Open file picker and return list of {name, content} for selected files."""
        if self._host is None:
            return []
        paths = self._host.pick_import_files()
        if not paths:
            return []
        result = []
        for p in paths:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read()
                result.append({"name": os.path.basename(p), "content": content})
            except Exception:
                continue
        return result

    # ── 图片资产管理（复制入库 .memoria/images/） ──

    def select_image_file(self) -> str:
        """打开图片选择对话框，返回本地路径（取消返回空串）。"""
        if self._host is None:
            return ""
        return self._host.pick_image_file() or ""

    def import_image(self, local_path: str) -> dict:
        """复制本地图片到 .memoria/images/（重名自动去重），返回相对路径。"""
        try:
            return self._svc.import_image(local_path)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def list_images(self) -> dict:
        """列出 .memoria/images/ 全部图片资产（含注册状态：referenced / referencedBy）。"""
        try:
            return {"status": "ok", "images": self._svc.list_images()}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def unused_images(self) -> dict:
        """列出未被任何文档引用的图片资产（未注册图片）。"""
        try:
            return {"status": "ok", "images": self._svc.unused_images()}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def cleanup_unused_images(self, rel_paths: list[str] | None = None) -> dict:
        """清理未注册图片（图片管理器按钮显式触发）；rel_paths 为空时清理全部未引用图片。"""
        try:
            return self._svc.cleanup_unused_images(rel_paths)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def image_registry_auto_check(self) -> dict:
        """运行期轻量自动检查（打开知识库/定时触发）：基于磁盘注册表清理未引用图片。"""
        try:
            return self._svc.image_registry_auto_check()
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def diagnose_image_refs(self) -> dict:
        """诊断"被文档引用但未成功注册"的图片引用（图片管理 → 检查异常引用）。"""
        try:
            return self._svc.diagnose_image_refs()
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def fix_unregistered_image_refs(self) -> dict:
        """一键修复：把格式不可注册的 .memoria/images/ 图片引用改写为尖括号形式。"""
        try:
            return self._svc.fix_unregistered_image_refs()
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    # DEPRECATED(0.3.0): 统一入口请用 select_import_sources/import_scan/import_execute
    def pre_scan_import(self, file_contents: list[dict]) -> dict:
        """预扫描导入文件，检测 KP id 冲突。

        file_contents: [{"name": "batch1.txt", "content": "..."}]
        Returns ImportScanResult as dict.
        """
        try:
            if not self._svc.kb_path:
                return {"status": "error", "message": "未打开知识库"}
            sections: list = []
            for fc in file_contents or []:
                name = fc.get("name", "")
                content = fc.get("content", "")
                sections.extend(parse_flat_file(content, source_name=name))
            result = pre_scan_import(sections, self._svc.kb_path)
            return {
                "status": "ok",
                "total_files": result.total_files,
                "total_sections": result.total_sections,
                "total_kp_declarations": result.total_kp_declarations,
                "has_conflicts": result.has_conflicts,
                "conflict_report": result.conflict_report,
                "conflicts": [
                    {
                        "kp_id": c.kp_id,
                        "import_source": c.import_source,
                        "import_line": c.import_line,
                        "existing_file": c.existing_file,
                        "existing_name": c.existing_name,
                    }
                    for c in result.conflicts
                ],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # DEPRECATED(0.3.0): 统一入口请用 select_import_sources/import_scan/import_execute
    def execute_import(self, file_contents: list[dict], conflict_resolution: dict | None = None) -> dict:
        """执行导入。

        file_contents: [{"name": "batch1.txt", "content": "..."}]
        conflict_resolution: {"kp_id": "skip"|"overwrite"|"rename:new-id"}
        Returns ImportResult as dict.
        """
        try:
            if not self._svc.kb_path:
                return {"status": "error", "message": "未打开知识库"}
            sections: list = []
            for fc in file_contents or []:
                name = fc.get("name", "")
                content = fc.get("content", "")
                sections.extend(parse_flat_file(content, source_name=name))
            result = execute_import(
                sections, self._svc.kb_path, conflict_resolution=conflict_resolution or {}
            )
            return {
                "status": result.status,
                "files_written": result.files_written,
                "sidecars_written": result.sidecars_written,
                "kp_imported": result.kp_imported,
                "kp_skipped": result.kp_skipped,
                "kp_renamed": result.kp_renamed,
                "kp_overwritten": result.kp_overwritten,
                "errors": result.errors,
                "build_report": result.build_report,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── 0.3.0 统一导入（import-spec §10）：scan → preview → execute ──

    def select_import_sources(self, kind: str) -> dict:
        """按导入源类型弹选择框并返回 sources。

        flat_file → 多选文本并读取为 {name, content}；
        md_dir → 选择目录（后端递归收集 .md）；kb_bundle → 选择包目录。
        """
        from memoria.services.import_plan import FLAT_FILE, KB_BUNDLE, MD_DIR

        try:
            if kind == FLAT_FILE:
                if self._host is None:
                    return {"status": "ok", "kind": kind, "sources": []}
                paths = self._host.pick_import_files() or []
                sources: list[dict] = []
                for p in paths:
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            sources.append({"name": os.path.basename(p), "content": f.read()})
                    except OSError:
                        continue
                return {"status": "ok", "kind": kind, "sources": sources}
            if kind in (MD_DIR, KB_BUNDLE):
                if self._host is None or not hasattr(self._host, "pick_directory"):
                    return {"status": "error", "message": "当前壳不支持目录选择"}
                picked = self._host.pick_directory()
                if not picked:
                    return {"status": "ok", "kind": kind, "sources": []}
                return {"status": "ok", "kind": kind, "sources": [{"path": picked}]}
            return {"status": "error", "message": f"不支持的导入源 kind={kind!r}"}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def import_scan(self, kind: str, sources: list[dict]) -> dict:
        """0.3.0 统一扫描（只读）：返回 {status, preview(JSON), markdown}（import-spec §7/§8）。"""
        from memoria.services.import_plan import KINDS, build_import_preview

        try:
            if not self._svc.kb_path:
                return {"status": "error", "message": "请先打开知识库"}
            if kind not in KINDS:
                return {"status": "error", "message": f"不支持的导入源 kind={kind!r}"}
            if not sources:
                return {"status": "error", "message": "未选择导入源"}
            pv = build_import_preview(kind, sources, self._svc.kb_path)
            return {"status": "ok", "preview": pv.as_json(), "markdown": pv.as_markdown()}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def import_execute(self, kind: str, sources: list[dict], decisions: dict | None = None) -> dict:
        """0.3.0 统一执行：写 md/sidecar/图谱同步。

        decisions: {subject(rel_path 或 kp_id): "skip" | "overwrite" | "rename:<新名>"}
        """
        from memoria.services.import_executor import execute_import as execute_unified
        from memoria.services.import_plan import KINDS

        try:
            if not self._svc.kb_path:
                return {"status": "error", "message": "请先打开知识库"}
            if kind not in KINDS or not sources:
                return {"status": "error", "message": "kind/sources 无效"}
            decisions = decisions or {}
            bad = [
                k
                for k, v in decisions.items()
                if not (isinstance(v, str) and (v in ("skip", "overwrite") or v.startswith("rename:")))
            ]
            if bad:
                return {"status": "error", "message": f"非法 decisions: {', '.join(bad)}"}
            res = execute_unified(kind, sources, self._svc.kb_path, decisions)
            return {
                "status": res.status,
                "files_written": res.files_written,
                "files_unchanged": res.files_unchanged,
                "files_skipped": res.files_skipped,
                "files_renamed": res.files_renamed,
                "files_overwritten": res.files_overwritten,
                "sidecars_written": res.sidecars_written,
                "kp_imported": res.kp_imported,
                "kp_skipped": res.kp_skipped,
                "kp_renamed": res.kp_renamed,
                "kp_overwritten": res.kp_overwritten,
                "errors": res.errors,
                "build_report": res.build_report,
            }
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    def get_agent_prompt(self, lang: str = "zh-CN") -> dict:
        """读取程序内可复制的 Agent 整理提示词（单一事实源 resources/agent-prompts/）。"""
        from memoria.app.runtime import resources_dir

        try:
            res_root = resources_dir()
            candidates = [f"organize.{lang}.md", "organize.zh-CN.md"]
            for name in candidates:
                path = res_root / "agent-prompts" / name
                if path.is_file():
                    return {
                        "status": "ok",
                        "name": path.name,
                        "lang": lang,
                        "text": path.read_text(encoding="utf-8"),
                    }
            return {"status": "error", "message": "未找到整理提示词资源（agent-prompts/organize.*.md）"}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}

    # 文档白名单：可在「Agent 整理提示词」弹窗内查看的格式说明（docs/reference，单一事实源）
    REFERENCE_DOCS = {
        "preview-formats.md": "preview-formats.md",
    }

    def get_reference_doc(self, name: str = "preview-formats.md") -> dict:
        """读取应用内格式说明文档（供弹窗内查看/复制）。

        单一事实源 docs/reference/{name}：开发态直接读仓库文件；发布态读随包
        资源 resources/docs/{name}（白名单登记于 packaging/build.py
        _REFERENCE_DOC_BUNDLE，构建时随包拷贝）。仅放行白名单文件。
        """
        from memoria.app.runtime import is_frozen, repo_root, resources_dir

        try:
            real = self.REFERENCE_DOCS.get(str(name or ""))
            if not real:
                return {"status": "error", "message": f"不支持的文档: {name!r}"}
            if is_frozen():
                path = resources_dir() / "docs" / real
                note = f"resources/docs/{real}"
            else:
                path = repo_root() / "docs" / "reference" / real
                note = f"docs/reference/{real}"
            if not path.is_file():
                return {
                    "status": "error",
                    "message": f"文档不存在: {real}（{note}；发布包需在 build.py 登记随包）",
                }
            return {
                "status": "ok",
                "name": real,
                "text": path.read_text(encoding="utf-8"),
                "note": note,
            }
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)}
