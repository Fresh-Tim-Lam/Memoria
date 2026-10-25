"""task-133 真机验证：**原样启动真实 Memoria**，只做一件事 —— 打开 WebView2 远程调试端口。

为什么要这个包装（而不是 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`）：
当前 venv 里的 pywebview 在 `platforms/edgechromium.py:82` **自行赋值**
`props.AdditionalBrowserArguments = '--disable-features=ElasticOverscroll'`，
一旦它显式设置该属性，WebView2 就**忽略** `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 环境变量
（实测：设了环境变量但 9577 不监听）。pywebview 自己的开关是 `webview.settings['REMOTE_DEBUGGING_PORT']`，
它是 `ImmutableDict`（只允许改已存在的键）⇒ 在这里改这一项，然后走产品同一条启动路径。

不改 `src/**`：本文件只是 harness，先改 pywebview 的全局设置，再调用 `memoria.app.desktop.main()`。
"""

from __future__ import annotations

import os

import webview

_port = os.environ.get("T133_CDP_PORT", "").strip()
if _port:
    webview.settings["REMOTE_DEBUGGING_PORT"] = int(_port)
# 真机验证不需要 devtools 面板（多一个 target 会干扰 /json/list 选取）
webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False

from memoria.app.desktop import main  # noqa: E402  （必须在改完 webview 设置之后导入）

if __name__ == "__main__":
    main()
