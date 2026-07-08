"""PyInstaller 入口：强制 PyQt6 发布壳。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MEMORIA_SHELL", "pyqt6")
os.environ.setdefault("MEMORIA_MODE", "release")

_root = Path(__file__).resolve().parents[1]
_src = _root / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from memoria.app.desktop import main

if __name__ == "__main__":
    main()
