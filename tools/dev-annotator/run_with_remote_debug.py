"""Dev launcher: enable WebView2 remote debugging without touching product code."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import webview  # noqa: E402

webview.settings.data["REMOTE_DEBUGGING_PORT"] = int(os.environ.get("MEMORIA_CDP_PORT", "9222"))

if __name__ == "__main__":
    os.environ.setdefault("MEMORIA_MODE", "dev")
    os.environ.setdefault("MEMORIA_SHELL", "pywebview")
    os.environ.setdefault("MEMORIA_DEBUG", "1")
    from memoria.app.desktop import main

    main()
