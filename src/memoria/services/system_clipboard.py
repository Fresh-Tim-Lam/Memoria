"""系统剪贴板直读/直写（Windows，ctypes，不依赖 pywin32）。

## 为什么需要这个模块（2026-10-24）

前端 `app.js` 的右键「粘贴」原先走 `navigator.clipboard.readText()`。WebView2 下该 API：

1. 需要 `clipboard-read` **权限**（首次调用会弹「是否允许」对话框 ⇒ **界面卡住**）；
2. 需要**瞬时用户激活（transient user activation）**，而右键菜单里的读取发生在异步回调中，
   用户手势多已过期 ⇒ 有时直接抛异常，被 `catch` 吞掉后表现为「粘贴没反应」（静默失败）。

桌面应用不该经浏览器权限层访问剪贴板。本模块用 Win32 剪贴板 API 直读直写：
**无权限弹窗、无用户手势要求、同步可靠**。

## 边界

- 仅 Windows（`ctypes.WinDLL`）；其它平台 `available()` 返回 False，调用方回退到浏览器 API。
- 只处理 **Unicode 文本**（`CF_UNICODETEXT`）；图片/HTML 等富格式不在范围内。
- 读失败（剪贴板被其它进程占用）会**有限重试**后返回空串 —— 调用方必须区分
  「剪贴板确实为空」与「读取失败」时，用 `read_text_with_status()`。

## 64 位注意

`GetClipboardData` 返回 HANDLE、`GlobalLock` 返回 LPVOID，**都是指针宽度**。
必须显式声明 `restype`，否则 ctypes 默认按 `c_int` 截断高 32 位 ⇒ 访问违例或读到垃圾。
"""

from __future__ import annotations

import sys
import time

__all__ = [
    "available",
    "read_text",
    "read_text_with_status",
    "write_text",
]

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# 剪贴板被占用时重试（每次之间让出时间片，总等待约 150ms 上限）
_OPEN_RETRIES = 10
_OPEN_RETRY_SLEEP_S = 0.015


def available() -> bool:
    """当前平台是否支持系统剪贴板直读。"""
    return sys.platform == "win32"


def _load_api():  # noqa: ANN202 - 内部用，返回值类型依赖 ctypes
    """按需加载并声明 Win32 API 原型（只加载一次）。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # —— 指针宽度关键：HANDLE / HGLOBAL / LPVOID 均为指针，必须声明 restype ——
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    return ctypes, user32, kernel32


_CTYPES = None
_USER32 = None
_KERNEL32 = None


def _api():  # noqa: ANN202
    global _CTYPES, _USER32, _KERNEL32
    if _USER32 is None:
        _CTYPES, _USER32, _KERNEL32 = _load_api()
    return _CTYPES, _USER32, _KERNEL32


def _open_clipboard(user32) -> bool:  # noqa: ANN001
    """打开剪贴板并重试（其它进程可能在用）。"""
    for _ in range(_OPEN_RETRIES):
        if user32.OpenClipboard(None):
            return True
        time.sleep(_OPEN_RETRY_SLEEP_S)
    return False


def read_text_with_status() -> tuple[str, str]:
    """读取剪贴板 Unicode 文本。

    返回 `(text, status)`：
    - `("文本", "ok")`      读到内容（可能为空串 = 剪贴板确实没有文本）
    - `("", "unsupported")` 非 Windows
    - `("", "busy")`        剪贴板被占用，重试后仍打不开
    - `("", "unavailable")` 打开成功但没有 CF_UNICODETEXT（例如复制的是图片）
    - `("", "error")`       其它异常（已捕获，不抛给上层）
    """
    if not available():
        return "", "unsupported"
    try:
        ctypes, user32, kernel32 = _api()
    except OSError:
        return "", "unsupported"

    if not _open_clipboard(user32):
        return "", "busy"
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return "", "unavailable"
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return "", "error"
        try:
            text = ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
        return text, "ok"
    except Exception:  # noqa: BLE001 - 剪贴板读取失败绝不向上抛
        return "", "error"
    finally:
        user32.CloseClipboard()


def read_text() -> str:
    """读取剪贴板 Unicode 文本；任何失败都返回空串（调用方只关心内容时用）。"""
    text, _status = read_text_with_status()
    return text


def write_text(text: str) -> bool:
    """把 `text` 写入系统剪贴板。成功返回 True。

    失败（剪贴板被占用 / 非 Windows）返回 False，不抛异常 —— 调用方应回退到浏览器 API。
    """
    if not available():
        return False
    try:
        ctypes, user32, kernel32 = _api()
    except OSError:
        return False

    payload = (text or "").encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
    if not handle:
        return False
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        return False
    try:
        ctypes.memmove(ptr, payload, len(payload))
    finally:
        kernel32.GlobalUnlock(handle)

    if not _open_clipboard(user32):
        kernel32.GlobalFree(handle)
        return False
    try:
        if not user32.EmptyClipboard():
            kernel32.GlobalFree(handle)
            return False
        # 成功后所有权移交系统：不能再 GlobalFree（否则系统里留悬空句柄）
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    except Exception:  # noqa: BLE001
        kernel32.GlobalFree(handle)
        return False
    finally:
        user32.CloseClipboard()
