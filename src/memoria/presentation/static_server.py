"""本地静态资源 HTTP 服务（pywebview WSGI 入口）。"""

from __future__ import annotations

import os

import bottle

from memoria.presentation.paths import UI_STATIC_ROOT

_STATIC_ROOT = str(UI_STATIC_ROOT)
_JS_MIME = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
}


def create_app() -> bottle.Bottle:
    """以 ui/static/ 为根目录，使 m0/ 与 theme/ 均可访问。"""
    app = bottle.Bottle()

    @app.get("/")
    def root() -> bottle.HTTPResponse:
        return bottle.static_file("m0/index.html", root=_STATIC_ROOT)

    @app.get("/<path:path>")
    def asset(path: str) -> bottle.HTTPResponse:
        ext = os.path.splitext(path)[1].lower()
        mime = _JS_MIME.get(ext)
        if mime:
            return bottle.static_file(path, root=_STATIC_ROOT, mimetype=mime)
        return bottle.static_file(path, root=_STATIC_ROOT)

    return app
