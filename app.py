#!/usr/bin/env python3
"""Memoria 桌面应用入口（当前里程碑：M0）。"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from memoria.app.desktop import main

if __name__ == "__main__":
    main()
    
    