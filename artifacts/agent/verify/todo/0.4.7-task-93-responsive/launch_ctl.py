"""task-93 真机 harness：原样启动真实 Memoria + 打开 CDP + 提供一个「改真实窗口尺寸」的本地控制口。

控制口 = `%TEMP%\\memoria_t93\\cmd.json`（读）+ `ack.json`（写回执）。轮询线程调用
`webview.windows[0].resize(w, h)` —— 真实 OS 窗口尺寸变化（不是 CDP 视口模拟），
这样 CSS 断点 / ResizeObserver / WebView2 重排都走真实路径。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import threading
import time
from pathlib import Path

import webview

_user32 = ctypes.windll.user32


def _own_hwnd() -> int | None:
    """本进程的主窗口句柄（pywebview 的标题含 "Memoria"）。"""
    found: list[int] = []

    def _cb(hwnd, _lp):
        pid = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            n = _user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                _user32.GetWindowTextW(hwnd, buf, n + 1)
                if "Memoria" in buf.value:
                    found.append(hwnd)
        return True

    _user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(_cb), 0)
    return found[0] if found else None


def _window_rect(hwnd: int) -> dict:
    r = wt.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(r))
    return {"x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top}


def _own_windows() -> dict:
    """本进程所有顶层窗口（诊断用：确认 _own_hwnd 选中了可见主窗口）。"""
    rows = []

    def _cb(hwnd, _lp):
        pid = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            n = _user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(max(n + 1, 512))
            if n > 0:
                _user32.GetWindowTextW(hwnd, buf, len(buf))
            cls = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, cls, 256)
            rows.append(
                {
                    "hwnd": int(hwnd),
                    "title": buf.value,
                    "class": cls.value,
                    "visible": bool(_user32.IsWindowVisible(hwnd)),
                    "rect": _window_rect(hwnd) if _user32.IsWindowVisible(hwnd) else None,
                }
            )
        return True

    _user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(_cb), 0)
    return {"ok": True, "windows": rows}


def _force_foreground(hwnd: int) -> bool:
    """把窗口真正切到前台（DSH/harness 是前台时裸 SetForegroundWindow 会被 Windows 拒绝）。

    手段：① 真实鼠标点一下本窗口标题栏（真实输入 ⇒ 允许切前台，不会触发拖动）；
          ② 仍不行则 AttachThreadInput 到前台线程再 SetForegroundWindow。
    """
    fg = _user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    r = _window_rect(hwnd)
    _user32.SetCursorPos(r["x"] + 120, r["y"] + 12)  # 标题栏
    _user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    _user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    time.sleep(0.2)
    if _user32.GetForegroundWindow() == hwnd:
        return True
    try:
        fg_thread = _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), None)
        my_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        _user32.AttachThreadInput(my_thread, fg_thread, True)
        _user32.SetForegroundWindow(hwnd)
        _user32.AttachThreadInput(my_thread, fg_thread, False)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.3)
    return _user32.GetForegroundWindow() == hwnd


def _foreground() -> dict:
    hwnd = _own_hwnd()
    if not hwnd:
        return {"ok": False, "err": "no hwnd"}
    _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    _user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0003 | 0x0040)  # HWND_TOPMOST, NOMOVE|NOSIZE|SHOWWINDOW
    ok = _force_foreground(hwnd)
    time.sleep(0.3)
    return {
        "ok": True,
        "foreground_ok": ok,
        "hwnd": int(hwnd),
        "foreground_hwnd": int(_user32.GetForegroundWindow()),
        "rect": _window_rect(hwnd),
    }


def _clear_topmost() -> dict:
    hwnd = _own_hwnd()
    if not hwnd:
        return {"ok": False, "err": "no hwnd"}
    _user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0003)  # HWND_NOTOPMOST, NOMOVE|NOSIZE
    return {"ok": True}


def _hover(x: int, y: int) -> dict:
    """把**真实 OS 光标**移过 (x,y) 并产生真实鼠标移动事件（SetCursorPos 不会给窗口发
    WM_MOUSEMOVE，Chromium 的 title tooltip 悬停定时器不会被触发）。

    用 SendInput 风格的绝对 mouse_event（MOUSEEVENTF_MOVE|ABSOLUTE，坐标归一到 0..65535），
    再走几步相对 MOVE ⇒ 与真人移动鼠标同路径。
    """
    sw = max(1, _user32.GetSystemMetrics(0))
    sh = max(1, _user32.GetSystemMetrics(1))
    ax = int(round(int(x) * 65535 / sw))
    ay = int(round(int(y) * 65535 / sh))
    _user32.mouse_event(0x0001 | 0x8000, ax, ay, 0, 0)  # MOVE|ABSOLUTE
    time.sleep(0.05)
    _user32.mouse_event(0x0001, 6, 0, 0, 0)  # 相对微移，确保产生 WM_MOUSEMOVE 流
    _user32.mouse_event(0x0001, 4, 0, 0, 0)
    pos = wt.POINT()
    _user32.GetCursorPos(ctypes.byref(pos))
    return {"ok": True, "cursor": [pos.x, pos.y]}


def _client_origin() -> dict:
    """窗口客户区左上角的屏幕坐标（viewport (0,0) 的屏幕位置）。"""
    hwnd = _own_hwnd()
    if not hwnd:
        return {"ok": False, "err": "no hwnd"}
    pt = wt.POINT(0, 0)
    _user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return {"ok": True, "x": pt.x, "y": pt.y}


def _tooltip_scan(needles: list[str]) -> dict:
    """扫描**所有进程**的顶层窗口文本，找出含指定子串的可见窗口（WebView2 的 tooltip 可能属
    msedgewebview2.exe 而非本进程）。"""
    hits: list[dict] = []

    def _cb(hwnd, _lp):
        if not _user32.IsWindowVisible(hwnd):
            return True
        n = _user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        _user32.GetWindowTextW(hwnd, buf, n + 1)
        cls = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, cls, 256)
        text = buf.value
        for needle in needles or []:
            if needle and needle in text:
                r = wt.RECT()
                _user32.GetWindowRect(hwnd, ctypes.byref(r))
                hits.append({"text": text, "class": cls.value, "rect": [r.left, r.top, r.right - r.left, r.bottom - r.top]})
                break
        return True

    _user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(_cb), 0)
    return {"ok": True, "hits": hits}

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
            op = data.get("op") or "resize"
            if op == "foreground":
                res = _foreground()
            elif op == "windows":
                res = _own_windows()
            elif op == "normal":
                res = _clear_topmost()
            elif op == "tooltips":
                res = _tooltip_scan(data.get("needles") or [])
            elif op == "clientorigin":
                res = _client_origin()
            elif op == "hover":
                res = _hover(int(data["x"]), int(data["y"]))
            elif op == "rect":
                hwnd = _own_hwnd()
                res = {"ok": bool(hwnd), "rect": _window_rect(hwnd) if hwnd else None}
            else:
                wins[0].resize(int(data["w"]), int(data["h"]))
                res = {"ok": True}
            res["req"] = data
            res["at"] = time.time()
            ACK.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            ACK.write_text(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.2)


threading.Thread(target=_control_loop, daemon=True).start()

from memoria.app.desktop import main  # noqa: E402

if __name__ == "__main__":
    main()
