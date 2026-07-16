"""Ensure repo ``src/`` is on ``sys.path`` for ``memoria`` imports."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
_src = str(SRC)
if _src not in sys.path:
    sys.path.insert(0, _src)
