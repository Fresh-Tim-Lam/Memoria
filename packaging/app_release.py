"""PyInstaller 入口：强制 PyQt6 发布壳。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MEMORIA_SHELL", "pywebview")
os.environ.setdefault("MEMORIA_MODE", "release")

_root = Path(__file__).resolve().parents[1]
_src = _root / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from memoria.app.desktop import main


def _dump_crash_log() -> None:
    """windowed 模式 stderr 不可见，异常写入 exe 同目录 crash.log 便于定位。"""
    import traceback

    try:
        target = os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)), "crash.log"
        )
        with open(target, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        _dump_crash_log()
        raise
