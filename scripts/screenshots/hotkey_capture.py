#!/usr/bin/env python3
"""按热键抓取应用窗口客户区截图（README / 文档演示图工具）。

工作流：先把界面切到要拍的样子，按一下触发键（默认 F9）抓一张，按 `--names` 顺序落盘。
若这一张与上一张几乎一样（16x16 亮度指纹 RMS 低于 `--dup-rms`），判为**重复帧**：
播错误音、不占号、不覆盖旧文件，仍在等同一张 —— 避免"切页面没生效"污染素材。

    python scripts/screenshots/hotkey_capture.py
    python scripts/screenshots/hotkey_capture.py --names demo-graph-2d.png --out resources/screenshots

单张补拍：`--names` 只给一个名字时，去重参照物改为**磁盘上已有的同名文件**，
即"和上次那张比，没变就别覆盖"。

依赖：Pillow（仅本脚本需要，非运行时依赖）；其余为 Windows 自带 ctypes / winsound。
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import math
import os
import sys
import time
from pathlib import Path

if sys.platform != "win32":
    raise SystemExit("本脚本依赖 Windows API（user32 / winsound），仅支持 Windows。")

try:
    from PIL import Image, ImageGrab
except ImportError:
    raise SystemExit("缺少 Pillow，抓图需要它：\n    pip install Pillow\n")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "resources" / "screenshots"
DEFAULT_NAMES = "demo-split.png,demo-preview.png,demo-math.png,demo-settings.png,demo-check.png"

# 抓的是屏幕像素（CopyFromScreen 语义）：窗口被遮挡会拍到遮挡物，所以要求目标窗口在最前。
WAV_OK = "Windows Notify.wav"
WAV_DUP = "Windows Critical Stop.wav"

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetClientRect.restype = wt.BOOL
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.ClientToScreen.restype = wt.BOOL


def parse_key(text: str) -> int:
    """'F9' / 'f9' / '0x78' / '120' -> 虚拟键码。"""
    t = text.strip().lower()
    if t.startswith("f") and t[1:].isdigit() and 1 <= int(t[1:]) <= 24:
        return 0x6F + int(t[1:])  # VK_F1 = 0x70
    return int(t, 0)


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def wait_release(vk: int) -> None:
    while key_down(vk):
        time.sleep(0.04)


def find_window(title: str, pid: int | None = None) -> tuple[int, str] | None:
    """找可见、有客户区、标题匹配（或被 pid 命中）的顶层窗口。

    排序键是「标题以匹配串开头」优先、其次客户区最大 —— 否则 IDE 一类标题里恰好含同名工程的
    窗口（如 `app.py - Memoria - TraeCode CN`）会把真正要拍的应用窗口挤掉。
    """
    hits: list[tuple[int, str, int, int]] = []

    def _enum(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        prefix = 0
        if pid is not None:
            wpid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
            if wpid.value != pid:
                return True
        else:
            if title.lower() not in buf.value.lower():
                return True
            prefix = 1 if buf.value.lower().startswith(title.lower()) else 0
        rect = wt.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return True
        area = (rect.right - rect.left) * (rect.bottom - rect.top)
        if area > 0:
            hits.append((hwnd, buf.value, prefix, area))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)(_enum), 0)
    if not hits:
        return None
    hwnd, name, _prefix, _area = max(hits, key=lambda h: (h[2], h[3]))
    return hwnd, name


def capture_client(hwnd: int) -> tuple[Image.Image, int, int]:
    """抓窗口**客户区**（不含标题栏/边框）：PrintWindow 对 WebView2 内容是空的，只能抓屏幕像素。"""
    rect = wt.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetClientRect 失败")
    origin = wt.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise OSError("ClientToScreen 失败")
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise OSError(f"客户区尺寸异常：{w}x{h}")
    return ImageGrab.grab(bbox=(origin.x, origin.y, origin.x + w, origin.y + h)), w, h


def fingerprint(img: Image.Image, size: int = 16) -> bytes:
    """16x16 亮度指纹：够粗，抗抗锯齿/光标抖动，又够敏，能区分不同视图。"""
    return img.convert("L").resize((size, size), Image.BICUBIC).tobytes()


def rms(a: bytes, b: bytes) -> float:
    if not a or len(a) != len(b):
        return float("inf")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / len(a))


def play(ok: bool) -> None:
    try:
        import winsound
    except ImportError:
        return
    wav = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Media" / (WAV_OK if ok else WAV_DUP)
    try:
        if wav.is_file():
            winsound.PlaySound(str(wav), winsound.SND_FILENAME)  # 同步播放，等它响完
        else:
            winsound.MessageBeep(winsound.MB_ICONASTERISK if ok else winsound.MB_ICONHAND)
    except (OSError, RuntimeError):
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="热键触发的窗口客户区抓图（带重复帧识别）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python scripts/screenshots/hotkey_capture.py\n"
            "  python scripts/screenshots/hotkey_capture.py --names demo-graph-2d.png\n"
        ),
    )
    ap.add_argument("--out", default=None, help=f"输出目录（默认 {DEFAULT_OUT}）")
    ap.add_argument("--names", default=DEFAULT_NAMES, help="按拍摄顺序落盘的文件名，逗号分隔")
    ap.add_argument("--key", default="F9", help="触发键：F1-F24 或键码（如 0x78），默认 F9")
    ap.add_argument("--title", default="Memoria", help="目标窗口标题需包含的字符串（默认 Memoria）")
    ap.add_argument("--pid", type=int, default=None, help="按进程号定位窗口（给了就不看标题）")
    ap.add_argument("--dup-rms", type=float, default=3.0, help="重复帧阈值，0 = 关闭去重（默认 3.0）")
    args = ap.parse_args(argv)

    vk = parse_key(args.key)
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if not names:
        ap.error("--names 不能为空")
    out = Path(args.out).expanduser() if args.out else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    print(f"输出目录：{out}")
    print(f"共 {len(names)} 张，按 {args.key.upper()} 抓图；重复帧会被忽略（改完界面再按）")
    print(f"第 1 张 -> {names[0]}")

    prev_sig: bytes | None = None
    prev_label = ""
    i = 0
    while i < len(names):
        if not key_down(vk):
            time.sleep(0.06)
            continue
        wait_release(vk)

        win = find_window(args.title, args.pid)
        if win is None:
            print(f"找不到窗口（标题含 {args.title!r}）；确认应用已启动并置于最前", file=sys.stderr)
            continue
        hwnd, title = win

        try:
            img, w, h = capture_client(hwnd)
        except OSError as exc:
            print(f"抓图失败：{exc}", file=sys.stderr)
            continue

        dest = out / names[i]
        sig = fingerprint(img)
        ref_sig, ref_label = prev_sig, prev_label
        if ref_sig is None and args.dup_rms > 0 and dest.is_file():
            with Image.open(dest) as old:
                ref_sig, ref_label = fingerprint(old), f"磁盘上的 {names[i]}"
        delta = rms(ref_sig, sig) if (ref_sig and args.dup_rms > 0) else float("inf")

        if delta < args.dup_rms:
            play(False)
            print(
                f"重复帧（与 {ref_label} 的 RMS {delta:.2f} < {args.dup_rms}）："
                f"未保存，仍在等 {names[i]} —— 切换界面后再按"
            )
            continue

        img.save(dest)
        prev_sig, prev_label = sig, names[i]
        i += 1
        play(True)
        nxt = names[i] if i < len(names) else "(全部完成)"
        print(f"{i}/{len(names)}  {names[i - 1]}  {w}x{h}  {title!r}  RMS {delta:.2f}  下一张：{nxt}")

    play(True)
    print("完成：全部截图已落盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
