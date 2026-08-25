from __future__ import annotations

import sys
from pathlib import Path


def _resolve_package_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "memoria"
    return Path(__file__).resolve().parents[1]


PACKAGE_ROOT = _resolve_package_root()
UI_STATIC_ROOT = PACKAGE_ROOT / "ui" / "static"
UI_APP_INDEX = UI_STATIC_ROOT / "app" / "index.html"
UI_THEME_CSS = UI_STATIC_ROOT / "theme" / "memoria.css"
UI_APP_ICON = UI_STATIC_ROOT / "icons" / "Memoria.ico"
