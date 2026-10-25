"""task-136 OS 级截图：用 bundled Pillow 抓真实屏幕区域（原生 title tooltip 不在 Page 截图里）。

用法：python grab.py <x> <y> <w> <h> <out.png>
"""

from __future__ import annotations

import ctypes
import json
import sys

from PIL import ImageGrab

try:  # 与窗口进程一致按物理像素取坐标（否则缩放 125% 下会错位）
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass

x, y, w, h = (int(v) for v in sys.argv[1:5])
out = sys.argv[5]
img = ImageGrab.grab(bbox=(x, y, x + w, y + h), include_layered_windows=True)
img.save(out)
print(json.dumps({"ok": True, "path": out, "size": list(img.size)}))
