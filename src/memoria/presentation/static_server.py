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

# Current KB root path (set by UIAPI when KB is opened)
_kb_root: str | None = None


def _log(msg: str) -> None:
    """带 [STATIC] 前缀的日志输出。

    Windows 下管道/重定向 stdout 常为 cp1252 编码，中文路径或消息会触发
    UnicodeEncodeError（打包态窗口应用 stdout 甚至为 None）；统一在此静默降级。
    """
    try:
        print(f"[STATIC] {msg}")
    except (UnicodeEncodeError, OSError):
        pass


def set_kb_root(path: str) -> None:
    global _kb_root
    _kb_root = path
    _log(f"set_kb_root: _kb_root 设为 {path}")


def get_kb_root() -> str | None:
    return _kb_root


def _serve_kb_file(filepath: str) -> bottle.HTTPResponse | None:
    """Try to serve a KB file. Returns None if not applicable."""
    kb = _kb_root
    if not kb:
        _log(f"_serve_kb_file: _kb_root 为 None，无法提供 /files/{filepath}")
        return None
    # Decode each path segment individually (since / was not encoded)
    decoded = "/".join(urllib.parse.unquote(s) for s in filepath.split("/"))
    # Resolve relative to KB root
    full = os.path.normpath(os.path.join(kb, decoded))
    kb_norm = os.path.normpath(kb)
    # On Windows, normalize case for comparison
    if os.name == "nt":
        full_cmp = full.lower()
        kb_cmp = kb_norm.lower()
    else:
        full_cmp = full
        kb_cmp = kb_norm
    if not full_cmp.startswith(kb_cmp):
        _log(f"_serve_kb_file: 路径逃逸 {full} 不在 {kb_norm} 下")
        return None
    # 边界校验：仅 startswith 前缀匹配会把 "C:\kb-evil" 误判为 "C:\kb" 之下；
    # 要求 full 等于 KB 根，或严格位于 "kb + 分隔符" 之后（堵住兄弟目录前缀绕过）
    if full_cmp != kb_cmp and not full_cmp.startswith(kb_cmp + os.sep):
        _log(f"_serve_kb_file: 路径逃逸 {full} 不在 {kb_norm} 下（前缀边界）")
        return None
    if not os.path.isfile(full):
        _log(f"_serve_kb_file: 文件不存在 {full} (请求: /files/{filepath})")
        return None
    ext = os.path.splitext(full)[1].lower()
    mime = _IMG_MIME.get(ext, "application/octet-stream")
    fsize = os.path.getsize(full)
    _log(f"_serve_kb_file: 提供文件 {full} (MIME: {mime}, {fsize} bytes)")
    with open(full, "rb") as f:
        data = f.read()
    return bottle.HTTPResponse(status=200, body=data, headers={"Content-Type": mime, "Content-Length": str(len(data))})


_NO_STORE = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


def create_app() -> bottle.Bottle:
    """以 ui/static/ 为根目录，使 app/ 与 theme/ 均可访问。"""
    app = bottle.Bottle()

    @app.get("/")
    def root() -> bottle.HTTPResponse:
        resp = bottle.static_file("app/index.html", root=_STATIC_ROOT)
        if isinstance(resp, bottle.HTTPResponse):
            for k, v in _NO_STORE.items():
                resp.set_header(k, v)
        return resp

    @app.get("/<path:path>")
    def asset(path: str) -> bottle.HTTPResponse:
        # Intercept /files/ prefix for KB file serving
        if path.startswith("files/"):
            kb_path = path[len("files/"):]
            result = _serve_kb_file(kb_path)
            if result is not None:
                return result
            return bottle.HTTPResponse(status=404, body="File not found in KB")
        # Diagnostic: check KB root
        if path == "_kb_root_diag":
            return {"kb_root": _kb_root}
        # Static asset serving
        ext = os.path.splitext(path)[1].lower()
        mime = _JS_MIME.get(ext)
        if mime:
            resp = bottle.static_file(path, root=_STATIC_ROOT, mimetype=mime)
        else:
            resp = bottle.static_file(path, root=_STATIC_ROOT)
        # 静态资源禁用缓存：开发迭代改 JS/HTML 后重启应用必须拿到最新文件，
        # 避免 WebView2 启发式缓存旧版本（harness 同款策略）
        if isinstance(resp, bottle.HTTPResponse):
            for k, v in _NO_STORE.items():
                resp.set_header(k, v)
        return resp

    return app
