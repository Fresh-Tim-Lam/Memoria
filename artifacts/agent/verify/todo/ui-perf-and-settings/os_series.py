"""OS 级连续截图（PIL_PY 运行）：按窗口标题找 Memoria 窗口，40ms 一帧记录
{ t_wall, mean, near_black_ratio, non_bg_ratio, frame_path? }。

用法（用 bundled Pillow 的 python 跑）：python os_series.py <outdir> <duration_ms> <interval_ms>
输出：<outdir>/series.json
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

u32 = ctypes.WinDLL("user32")
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]


def find_rect():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _l):
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(hwnd, buf, 256)
        if "Memoria" in buf.value and u32.IsWindowVisible(hwnd):
            r = wintypes.RECT()
            u32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 300:
                found.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
                return False
        return True

    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def main() -> int:
    outdir = Path(sys.argv[1]); outdir.mkdir(parents=True, exist_ok=True)
    duration_ms = int(sys.argv[2]) if len(sys.argv) > 2 else 4000
    interval_ms = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    rect = None
    frames = []
    t_end = time.time() + duration_ms / 1000.0
    shot_idx = 0
    while time.time() < t_end:
        if rect is None:
            rect = find_rect()
        if rect is None:
            time.sleep(0.05)
            continue
        x, y, w, h = rect
        try:
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h), include_layered_windows=True)
        except Exception as e:  # noqa: BLE001
            frames.append({"t": time.time(), "error": str(e)})
            time.sleep(interval_ms / 1000.0)
            continue
        small = img.resize((48, 32))
        px = list(small.getdata())
        n = len(px)
        mean = sum((r + g + b) / 3 for r, g, b in px) / n
        near_black = sum(1 for r, g, b in px if r < 16 and g < 16 and b < 16) / n
        # 非背景占比：把出现次数最多的颜色当背景，其余像素视为"内容/logo 像素"
        from collections import Counter
        cnt = Counter(px)
        bg, _cnt = cnt.most_common(1)[0]
        non_bg = 1.0 - (cnt[bg] / n)
        rec = {"t": time.time(), "mean": round(mean, 2),
               "near_black": round(near_black, 3), "non_bg": round(non_bg, 3),
               "bg": list(bg)}
        # 关键时刻留原图：头 3 帧 + 每 10 帧
        if shot_idx < 3 or shot_idx % 10 == 0:
            p = outdir / f"frame_{shot_idx:03d}.png"
            img.save(p)
            rec["frame"] = str(p)
        frames.append(rec)
        shot_idx += 1
        time.sleep(interval_ms / 1000.0)
    (outdir / "series.json").write_text(json.dumps(frames, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"ok": True, "frames": len(frames), "dir": str(outdir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
