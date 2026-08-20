"""开发态 / 发布态：路径解析与默认壳选择。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def repo_root() -> Path:
    """源码仓库根目录（非 frozen）。"""
    return Path(__file__).resolve().parents[3]


def install_root() -> Path:
    """发布包根目录：`Package/`（Memoria.exe 与 lib/、resources/ 同级）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return repo_root()


def resources_dir() -> Path:
    if is_frozen():
        return install_root() / "resources"
    return repo_root() / "resources"


def default_examples_dir() -> Path | None:
    for candidate in (
        resources_dir() / "examples",
        install_root() / "examples",
        repo_root() / "examples",
    ):
        if candidate.is_dir():
            return candidate
    return None


def resolve_mode() -> str:
    raw = os.environ.get("MEMORIA_MODE", "").strip().lower()
    if raw in ("dev", "release"):
        return raw
    return "release" if is_frozen() else "dev"


def resolve_shell_kind() -> str:
    explicit = os.environ.get("MEMORIA_SHELL", "").strip().lower()
    if explicit:
        return explicit
    # 发布态与开发态统一走 pywebview（WebView2）：新 Chromium 内核稳定、
    # 支持原生窗口动画；需要 PyQt6 壳时可显式 MEMORIA_SHELL=pyqt6
    return "pywebview"
