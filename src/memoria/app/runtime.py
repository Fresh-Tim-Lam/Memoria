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
        repo_root() / "docs" / "example" / "showcase",
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


# ── 派生窗口 / 启动参数 ──────────────────────────────────────────────
# 新窗口通过新进程承载（“文件 → 新窗口 / 打开最近”）：
#   MEMORIA_NO_KB=1   → 空知识库窗口（不自动打开上次）；
#   MEMORIA_KB=<dir>  → 启动即打开指定知识库（并记入最近列表）。
_NO_KB_ENV = "MEMORIA_NO_KB"
_KB_ENV = "MEMORIA_KB"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def no_auto_kb_env() -> bool:
    """当前进程以“不自动打开知识库”模式启动（新窗口）。"""
    return _env_flag(_NO_KB_ENV)


def explicit_kb_env() -> str | None:
    """启动参数指定的知识库目录（MEMORIA_KB）；目录无效返回 None。"""
    raw = os.environ.get(_KB_ENV, "").strip()
    if not raw:
        return None
    p = Path(raw)
    return str(p.resolve()) if p.is_dir() else None


def resolve_startup_kb_path() -> str | None:
    """壳启动时应打开的知识库：
    1. MEMORIA_KB 显式指定（存在）→ 直接打开；
    2. MEMORIA_NO_KB=1（“新窗口”）→ None（显示欢迎页）；
    3. 默认 → 上次打开（last_kb_path）。
    """
    explicit = explicit_kb_env()
    if explicit:
        return explicit
    if no_auto_kb_env():
        return None
    from memoria.storage.ui_settings import resolve_last_kb_path

    return resolve_last_kb_path()


def spawn_window(kb_path: str | None) -> dict:
    """启动一个派生 Memoria 窗口（独立进程）。

    - kb_path 为目录 → 新窗口打开该知识库（MEMORIA_KB）；
    - kb_path 为 None/空 → 新窗口不打开任何知识库（MEMORIA_NO_KB）。
    返回 {"status": "ok"} 或 {"status": "error", "message": ...}。
    """
    import subprocess

    env = dict(os.environ)
    env.pop(_KB_ENV, None)
    env.pop(_NO_KB_ENV, None)
    if kb_path:
        env[_KB_ENV] = str(Path(kb_path).resolve())
    else:
        env[_NO_KB_ENV] = "1"

    try:
        if is_frozen():
            cmd = [sys.executable]
        else:
            # 开发态：用当前解释器运行仓库根 app.py（与手动 python app.py 一致）
            cmd = [sys.executable, str(repo_root() / "app.py")]
        subprocess.Popen(
            cmd,
            env=env,
            cwd=str(install_root()),
        )
        return {"status": "ok"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": f"启动新窗口失败: {e}"}
