"""临时诊断脚本：pywebview 内缩放/字号控制运行时检查。

用法：python scripts/diag_webview.py
结果写入 logs/webview-diag.json（若未输出则查看控制台/异常）。
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import webview
from memoria.app.shell.pywebview_host import PyWebViewHost
from memoria.app.shell.pywebview import _startup_kb_path
from memoria.presentation.api.ui import UIAPI
from memoria.presentation.static_server import create_app

OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
    "webview-diag.json",
)

# 返回对象（非字符串），edgechromium evaluate_js 会自动 JSON.parse
SCRIPT = r"""
(function () {
  function probe() {
    var el = document.createElement('div');
    el.style.width = '1rem';
    el.style.position = 'absolute';
    document.body.appendChild(el);
    var w = getComputedStyle(el).width;
    el.remove();
    return w;
  }
  var out = {
    readyState: document.readyState,
    url: location.href,
    hasDisplay: typeof window.MemoriaDisplaySettings !== 'undefined',
    hasBridge: typeof window.MemoriaBridge !== 'undefined',
    hasPywebview: typeof window.pywebview !== 'undefined',
    displayKeys: window.MemoriaDisplaySettings
      ? Object.keys(window.MemoriaDisplaySettings) : [],
    bodyUserSelect: getComputedStyle(document.body).userSelect,
    fontInline: document.documentElement.style.fontSize || '(empty)',
    fontComputed: getComputedStyle(document.documentElement).fontSize,
    remPx: probe(),
    previewExists: !!document.getElementById('preview'),
    lsKey: (function () {
      try { return localStorage.getItem('-display-settings') || '(none)'; }
      catch (e) { return 'ERR:' + e.message; }
    })(),
    resources: performance.getEntriesByType('resource')
      .map(function (r) { return r.name; })
      .filter(function (n) { return /app\.css|memoria\.css|display-settings|app\.js|index\.html/.test(n); }),
  };
  if (window.MemoriaDisplaySettings) {
    var before = getComputedStyle(document.documentElement).fontSize;
    window.MemoriaDisplaySettings.adjustUiScale(0.2);
    var after = getComputedStyle(document.documentElement).fontSize;
    out.zoomBefore = before;
    out.zoomAfter = after;
    out.zoomApplied = before !== after;
    window.MemoriaDisplaySettings.resetUiScale();

    var p = document.getElementById('preview');
    if (p) {
      var pfBefore = getComputedStyle(p).fontSize;
      window.MemoriaDisplaySettings.save({ previewFontSize: 18 });
      var pfAfter = getComputedStyle(p).fontSize;
      out.fontBefore = pfBefore;
      out.fontAfter = pfAfter;
      out.fontApplied = pfBefore !== pfAfter;
      window.MemoriaDisplaySettings.save({ previewFontSize: 14 });
    } else {
      out.fontApplied = 'no-preview';
    }
  }
  return out;
})()
"""


def main() -> None:
    host = PyWebViewHost(frameless=False)
    startup_kb = _startup_kb_path()
    api = UIAPI(host=host, kb_path=startup_kb)
    window = webview.create_window(
        title="Memoria diag",
        url=create_app(),
        js_api=api,
        width=1280,
        height=860,
        min_size=(900, 600),
        frameless=False,
        easy_drag=False,
    )

    def on_loaded():
        time.sleep(1.5)  # 等待 hydrateFromDisk / 各设置模块初始化完成
        result: dict = {}
        try:
            result["js"] = window.evaluate_js(SCRIPT)
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
        try:
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            result["write_error"] = str(exc)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        window.destroy()

    window.events.loaded += on_loaded
    webview.start()


if __name__ == "__main__":
    main()
