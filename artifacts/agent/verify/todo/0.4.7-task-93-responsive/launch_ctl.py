"""task-93 真机 harness：原样启动真实 Memoria + 打开 CDP + 提供一个「改真实窗口尺寸」的本地控制口。

控制口 = `%TEMP%\\memoria_t93\\cmd.json`（读）+ `ack.json`（写回执）。轮询线程调用
`webview.windows[0].resize(w, h)` —— 真实 OS 窗口尺寸变化（不是 CDP 视口模拟），
这样 CSS 断点 / ResizeObserver / WebView2 重排都走真实路径。
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import webview

_port = os.environ.get("T93_CDP_PORT", "").strip()
if _port:
    webview.settings["REMOTE_DEBUGGING_PORT"] = int(_port)
webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False

WORK = Path(os.environ.get("T93_WORK", "."))
CMD = WORK / "cmd.json"
ACK = WORK / "ack.json"


def _control_loop() -> None:
    last = None
    while True:
        try:
            raw = CMD.read_text(encoding="utf-8")
        except OSError:
            time.sleep(0.2)
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            time.sleep(0.2)
            continue
        if data == last:
            time.sleep(0.2)
            continue
        last = data
        try:
            wins = webview.windows
            if not wins:
                ACK.write_text(json.dumps({"ok": False, "err": "no window"}, ensure_ascii=False), encoding="utf-8")
                continue
            wins[0].resize(int(data["w"]), int(data["h"]))
            ACK.write_text(
                json.dumps({"ok": True, "req": data, "at": time.time()}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            ACK.write_text(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.2)


threading.Thread(target=_control_loop, daemon=True).start()

from memoria.app.desktop import main  # noqa: E402

if __name__ == "__main__":
    main()
