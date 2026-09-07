"""前端 UI 偏好（图谱设置、侧栏分割等）磁盘持久化。"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

_SETTINGS_FILE = "ui-settings.json"


def _legacy_settings_path() -> Path:
    return Path.home() / ".memoria" / _SETTINGS_FILE


def _settings_dir() -> Path:
    base = os.environ.get("MEMORIA_CONFIG_DIR")
    if base:
        return Path(base)
    from memoria.app.runtime import install_root

    return install_root() / "config"


def settings_path() -> Path:
    return _settings_dir() / _SETTINGS_FILE


def _migrate_legacy_settings(target: Path) -> None:
    if os.environ.get("MEMORIA_CONFIG_DIR"):
        return
    from memoria.app.runtime import install_root

    expected = (install_root() / "config" / _SETTINGS_FILE).resolve()
    if target.resolve() != expected:
        return
    legacy = _legacy_settings_path()
    if target.is_file() or not legacy.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, target)


def load_ui_settings() -> dict[str, Any]:
    path = settings_path()
    _migrate_legacy_settings(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_ui_settings(partial: dict[str, Any]) -> dict[str, Any]:
    """浅合并写入；返回合并后的完整对象。"""
    current = load_ui_settings()
    for key, val in partial.items():
        if isinstance(val, dict) and isinstance(current.get(key), dict):
            current[key] = {**current[key], **val}
        else:
            current[key] = val
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return current


def resolve_last_kb_path() -> str | None:
    """上次打开的知识库目录；不存在或无效时返回 None。"""
    raw = load_ui_settings().get("last_kb_path")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    path = Path(text)
    if path.is_dir():
        return str(path.resolve())
    return None


# 「打开最近」固定展示数量（最新在前）
RECENT_KB_MAX = 8


def remember_last_kb_path(path: str | None) -> None:
    """记录上次打开的知识库，并维护「最近打开」列表（去重、最新在前）。

    - path 非空：写入 last_kb_path，并把该路径移到 recent 列表头部（截断 RECENT_KB_MAX）；
    - path 为 None：仅清空 last_kb_path（关闭窗口），recent 列表保留供其它窗口使用。
    """
    if not path:
        save_ui_settings({"last_kb_path": ""})
        return
    resolved = str(Path(path).resolve())
    recent = _load_recent_raw()
    recent = [p for p in recent if p != resolved]
    recent.insert(0, resolved)
    recent = recent[:RECENT_KB_MAX]
    save_ui_settings({"last_kb_path": resolved, "recent_kbs": recent})


def _load_recent_raw() -> list[str]:
    raw = load_ui_settings().get("recent_kbs")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def resolve_recent_kb_paths() -> list[str]:
    """最近打开的知识库（存在目录、最新在前，最多 RECENT_KB_MAX）。

    旧版本设置没有 recent_kbs 键：以 last_kb_path 作为种子初始化一次。
    """
    recent = _load_recent_raw()
    if not recent:
        last = resolve_last_kb_path()
        if last:
            recent = [last]
    seen: set[str] = set()
    out: list[str] = []
    for p in recent:
        try:
            rp = str(Path(p).resolve())
        except OSError:
            continue
        if rp in seen:
            continue
        if Path(rp).is_dir():
            seen.add(rp)
            out.append(rp)
        if len(out) >= RECENT_KB_MAX:
            break
    return out
