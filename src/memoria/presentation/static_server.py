"""本地静态资源 HTTP 服务（pywebview WSGI 入口）。"""

from __future__ import annotations

import os
import urllib.parse

import bottle

from memoria.presentation.paths import UI_STATIC_ROOT

_STATIC_ROOT = str(UI_STATIC_ROOT)
_JS_MIME = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
}
_IMG_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
}

# Current KB root path (set by M0API when KB is opened)
_kb_root: str | None = None


def set_kb_root(path: str | None) -> None:
    global _kb_root
    _kb_root = path


def get_kb_root() -> str | None:
    return _kb_root


def _serve_kb_file(filepath: str) -> bottle.HTTPResponse | None:
    """Try to serve a KB file. Returns None if not applicable."""
    kb = _kb_root
    if not kb:
        print(f"[files] no KB root set")
        return None
    # Decode each path segment individually (since / was not encoded)
    decoded = "/".join(urllib.parse.unquote(s) for s in filepath.split("/"))
    # Resolve relative to KB root
    full = os.path.normpath(os.path.join(kb, decoded))
    kb_norm = os.path.normpath(kb)
    print(f"[files] kb_root={kb!r}, filepath={filepath!r}, decoded={decoded!r}, full={full!r}")
    # On Windows, normalize case for comparison
    if os.name == "nt":
        full_cmp = full.lower()
        kb_cmp = kb_norm.lower()
    else:
        full_cmp = full
        kb_cmp = kb_norm
    if not full_cmp.startswith(kb_cmp):
        print(f"[files] access denied: full={full_cmp!r} not under kb={kb_cmp!r}")
        return None
    if not os.path.isfile(full):
        print(f"[files] file not found: {full!r}")
        return None
    ext = os.path.splitext(full)[1].lower()
    mime = _IMG_MIME.get(ext, "application/octet-stream")
    print(f"[files] serving: {full!r} mime={mime}")
    return bottle.static_file(os.path.basename(full), root=os.path.dirname(full), mimetype=mime)


def create_app() -> bottle.Bottle:
    """以 ui/static/ 为根目录，使 m0/ 与 theme/ 均可访问。"""
    app = bottle.Bottle()

    @app.get("/")
    def root() -> bottle.HTTPResponse:
        return bottle.static_file("m0/index.html", root=_STATIC_ROOT)

    @app.get("/<path:path>")
    def asset(path: str) -> bottle.HTTPResponse:
        # Intercept /files/ prefix for KB file serving
        if path.startswith("files/"):
            kb_path = path[len("files/"):]
            result = _serve_kb_file(kb_path)
            if result is not None:
                return result
            return bottle.HTTPResponse(status=404, body="File not found in KB")
        # Static asset serving
        ext = os.path.splitext(path)[1].lower()
        mime = _JS_MIME.get(ext)
        if mime:
            return bottle.static_file(path, root=_STATIC_ROOT, mimetype=mime)
        return bottle.static_file(path, root=_STATIC_ROOT)

    return app
