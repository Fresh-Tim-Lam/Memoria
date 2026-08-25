# -*- coding: utf-8 -*-
"""浏览器复现 harness：bottle 静态服务 + UIAPI over HTTP(/rpc) + 注入 pywebview 桥。
用法: python _harness.py  →  http://127.0.0.1:8642/
"""
import sys
import os
import json
import traceback

sys.path.insert(0, r"d:\AAA_Jupyter\Memoria\src")

import bottle

from memoria.presentation.api.ui import UIAPI
from memoria.presentation import static_server
from memoria.presentation.paths import UI_STATIC_ROOT, UI_APP_INDEX

KB = r"d:\AAA_Jupyter\Memoria\docs\example\rich-content-test"
PORT = 8642

api = UIAPI(host=None, kb_path=KB)

# 把写日志 API 重定向到独立文件，避免污染 mapping-debug.log
REPRO_LOG = os.path.join(KB, "browser-repro.log")
if os.path.exists(REPRO_LOG):
    os.remove(REPRO_LOG)

app = bottle.Bottle()

BRIDGE_SCRIPT = """
<script>
(function () {
  var proxy = new Proxy({}, {
    get: function (_t, prop) {
      if (prop === "then") return undefined;
      return function () {
        var args = Array.prototype.slice.call(arguments);
        return fetch("/rpc", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ method: prop, args: args })
        }).then(function (r) { return r.text(); })
          .then(function (t) {
            // 容错：部分 RPC 返回裸字符串，先 text() 再单次解析
            try { return JSON.parse(t); } catch (_e) { return t; }
          });
      };
    }
  });
  window.pywebview = { api: proxy };
})();
</script>
"""


@app.post("/rpc")
def rpc():
    try:
        data = json.loads(bottle.request.body.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "message": "bad json: %s" % exc}
    method = data.get("method") or ""
    args = data.get("args") or []
    if not isinstance(args, list):
        args = [args]
    if method in ("write_map_log", "write_debug_log"):
        body = (list(args) + ["", ""])[1] if len(args) > 1 else ""
        with open(REPRO_LOG, "a", encoding="utf-8") as f:
            f.write(body)
        return {"status": "ok"}
    fn = getattr(api, method, None)
    if fn is None or not callable(fn):
        return {"status": "error", "message": "未知方法: %s" % method}
    try:
        return fn(*args)
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "trace": traceback.format_exc(limit=3),
        }


@app.get("/")
def root():
    with open(UI_APP_INDEX, encoding="utf-8") as f:
        html = f.read()
    if "</head>" in html:
        html = html.replace("</head>", BRIDGE_SCRIPT + "</head>")
    else:
        html = BRIDGE_SCRIPT + html
    return bottle.HTTPResponse(
        html, headers={"Content-Type": "text/html; charset=utf-8"}
    )


@app.get("/<path:path>")
def asset(path):
    if path.startswith("files/"):
        result = static_server._serve_kb_file(path[len("files/") :])
        if result is not None:
            return result
        return bottle.HTTPResponse(status=404, body="File not found in KB")
    if path == "_kb_root_diag":
        return {"kb_root": static_server.get_kb_root()}
    resp = bottle.static_file(path, root=str(UI_STATIC_ROOT))
    # 禁用静态资源缓存：浏览器自动化会话可能启发式缓存旧版 JS，导致调试代码不生效
    if isinstance(resp, bottle.HTTPResponse):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


if __name__ == "__main__":
    print(f"[harness] KB={KB}  ->  http://127.0.0.1:{PORT}/  (log -> {REPRO_LOG})")
    bottle.run(app, host="127.0.0.1", port=PORT, quiet=True)
