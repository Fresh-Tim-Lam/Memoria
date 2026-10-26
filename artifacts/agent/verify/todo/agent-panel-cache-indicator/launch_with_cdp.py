"""task-183 探针用启动器：设置 pywebview 的 REMOTE_DEBUGGING_PORT 后再跑生产入口。

为什么需要它：本仓 pywebview 在 `EdgeChrome.__init__` 里**显式设置** WebView2 的
`AdditionalBrowserArguments`（含 `--disable-features=ElasticOverscroll`），
而 WebView2 仅在"属性未设置"时才读 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 环境变量
⇒ 只设环境变量拿不到 CDP 端口。pywebview 自己提供了 `settings['REMOTE_DEBUGGING_PORT']`
（edgechromium.py:87-90）——在这里设它，生产代码一行不改。
"""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

port = os.environ.get("MEMORIA_PROBE_CDP_PORT", "").strip()
if port:
    import webview

    webview.settings["REMOTE_DEBUGGING_PORT"] = int(port)

from memoria.app.desktop import main  # noqa: E402  (生产入口)

if __name__ == "__main__":
    main()