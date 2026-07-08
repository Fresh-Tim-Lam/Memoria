"""M0 pywebview API"""

from __future__ import annotations

import os

import webview

from .sidecar import (
    collect_md_files,
    load_sidecar,
    propose_ranges_from_headings,
    resolve_knowledge_points,
    save_sidecar,
    sidecar_path_for,
    strip_frontmatter,
)


class M0API:
    def __init__(self):
        self.kb_path: str | None = None

    def select_directory(self) -> str:
        result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        if result:
            self.kb_path = result[0]
            return self.kb_path
        return ""

    def set_kb_path(self, path: str) -> dict:
        if not os.path.isdir(path):
            return {"status": "error", "message": f"目录不存在: {path}"}
        self.kb_path = path
        return {"status": "ok", "path": path}

    def get_kb_path(self) -> str:
        return self.kb_path or ""

    def list_files(self) -> dict:
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        files = collect_md_files(self.kb_path)
        items = []
        for rel in files:
            full = os.path.join(self.kb_path, rel)
            sc = load_sidecar(sidecar_path_for(full))
            items.append({
                "path": rel,
                "has_sidecar": sc is not None,
                "description": (sc or {}).get("description", ""),
            })
        return {"status": "ok", "files": items}

    def load_document(self, rel_path: str) -> dict:
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        full = os.path.join(self.kb_path, rel_path)
        if not os.path.isfile(full):
            return {"status": "error", "message": "文件不存在"}

        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, fm = strip_frontmatter(raw)
        sidecar = load_sidecar(sidecar_path_for(full))
        kps = resolve_knowledge_points(body, sidecar)
        proposals = propose_ranges_from_headings(body) if not sidecar else []

        return {
            "status": "ok",
            "path": rel_path,
            "body": body,
            "frontmatter": fm,
            "sidecar": sidecar,
            "knowledge_points": kps,
            "heading_proposals": proposals,
            "lines": body.splitlines(),
        }

    def confirm_kp_range(
        self,
        rel_path: str,
        kp_id: str,
        name: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        """用户辅助：确认/修正 range 后写入侧车 snippet。"""
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        full = os.path.join(self.kb_path, rel_path)
        with open(full, "r", encoding="utf-8") as f:
            raw = f.read()
        body, fm = strip_frontmatter(raw)
        lines = body.splitlines()
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            return {"status": "error", "message": "行号无效"}

        sc_path = sidecar_path_for(full)
        sidecar = load_sidecar(sc_path) or {
            "schema_version": 1,
            "file": rel_path.replace("\\", "/"),
            "knowledge_points": [],
        }
        start_snip = lines[start_line - 1].strip()[:80]
        end_snip = lines[end_line - 1].strip()[:80]

        kps = sidecar.setdefault("knowledge_points", [])
        found = False
        for kp in kps:
            if kp.get("id") == kp_id:
                kp["name"] = name
                kp["range"] = {
                    "start": {"snippet": start_snip, "line_hint": start_line},
                    "end": {"snippet": end_snip, "line_hint": end_line},
                }
                found = True
                break
        if not found:
            kps.append({
                "id": kp_id,
                "name": name,
                "range": {
                    "start": {"snippet": start_snip, "line_hint": start_line},
                    "end": {"snippet": end_snip, "line_hint": end_line},
                },
            })

        if fm and fm.get("description") and not sidecar.get("description"):
            sidecar["description"] = fm["description"]

        save_sidecar(sc_path, sidecar)
        return self.load_document(rel_path)

    def pick_snippet_line(
        self,
        rel_path: str,
        kp_id: str,
        which: str,
        line_number: int,
    ) -> dict:
        """用户从候选列表选定 start/end 行。"""
        if not self.kb_path:
            return {"status": "error", "message": "未打开知识库"}
        doc = self.load_document(rel_path)
        if doc.get("status") != "ok":
            return doc
        lines = doc["lines"]
        kp = next((k for k in doc["knowledge_points"] if k.get("id") == kp_id), None)
        if not kp:
            return {"status": "error", "message": "知识点不存在"}
        rng = kp.get("range") or {}
        if which == "start":
            rng.setdefault("start", {})["line_hint"] = line_number
            rng["start"]["snippet"] = lines[line_number - 1].strip()[:80]
        else:
            rng.setdefault("end", {})["line_hint"] = line_number
            rng["end"]["snippet"] = lines[line_number - 1].strip()[:80]
        kp["range"] = rng

        full = os.path.join(self.kb_path, rel_path)
        sc_path = sidecar_path_for(full)
        sidecar = load_sidecar(sc_path) or {"schema_version": 1, "file": rel_path, "knowledge_points": []}
        for item in sidecar.setdefault("knowledge_points", []):
            if item.get("id") == kp_id:
                item["range"] = rng
                break
        else:
            sidecar["knowledge_points"].append({"id": kp_id, "name": kp.get("name", kp_id), "range": rng})
        save_sidecar(sc_path, sidecar)
        return self.load_document(rel_path)
