"""前端 UI 偏好（图谱设置、侧栏分割等）磁盘持久化。"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "ui-settings.json"


def _legacy_settings_path() -> Path:
    return Path.home() / ".memoria" / _SETTINGS_FILE


def _install_config_dir() -> Path:
    """**旧**位置：`<install_root>/config`（task-160 前用户态就存这里，换包即丢）。"""
    from memoria.app.runtime import install_root

    return install_root() / "config"


def _settings_dir() -> Path:
    """当前用户态目录。

    优先级：`MEMORIA_CONFIG_DIR` > `%LOCALAPPDATA%\\Memoria\\config` > `<install_root>/config`。

    第三档**只是兼容旧读**（旧版本把 `ui-settings.json` 留在安装目录里，
    见 `_migrate_from_install_dir`）；新写入永远不落安装目录。
    """
    base = os.environ.get("MEMORIA_CONFIG_DIR")
    if base:
        return Path(base)
    from memoria.util.user_state import user_config_dir

    return user_config_dir()


def settings_path() -> Path:
    return _settings_dir() / _SETTINGS_FILE


def _migrate_from_install_dir(target: Path) -> None:
    """把**旧安装目录**里的 `ui-settings.json` 一次性搬到用户目录（task-160）。

    ## 只复制不删（`shutil.copy2`，不 `unlink` 源文件）

    旧位置可能是用户**唯一的备份**：若将来用户清了 `%LOCALAPPDATA%`，
    安装目录里的那份还在，还能救回来。代价是旧位置残留一份可能过期的副本
    —— 但它**不再被读取**（下次启动会因新位置已存在而跳过迁移），
    所以不会造成"新旧两份互相打架"，只是可能在旧发行包里看到一个陈旧文件。

    ## 三条不变量（关闭条件 2）

    1. **新位置已有 ⇒ 绝不覆盖**（用户在新区改过的配置是更新的，不能回滚成旧值）；
    2. 旧位置无 ⇒ 什么都不做（走默认值）；
    3. **任何异常都吞掉**（记日志后返回）—— 迁移是"锦上添花"，
       它失败不能让应用起不来；此时 `settings_path()` 已指向新位置，
       读不到就是空配置（默认值），**不会**回落去读旧目录，
       因为回落会让"用户在新区改过的值"被旧值取代（违反不变量 1）。
    """
    if os.environ.get("MEMORIA_CONFIG_DIR"):
        return  # 显式指定目录时不迁移（测试/便携模式）
    try:
        if target.is_file():
            return  # 不变量 1：新位置已有 ⇒ 以新为准，不覆盖
        legacy = _install_config_dir() / _SETTINGS_FILE
        if not legacy.is_file():
            return  # 不变量 2：旧位置无 ⇒ 无迁移
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, target)  # 只复制，不删源
        logger.info(
            "ui-settings 已从旧安装目录迁移到用户目录：%s → %s（旧文件保留未删）",
            legacy,
            target,
        )
    except Exception as exc:  # noqa: BLE001 - 迁移绝不能影响启动
        logger.warning("ui-settings 迁移失败（不影响启动，使用默认值）：%s", exc)


def _migrate_legacy_settings(target: Path) -> None:
    """旧 `~/.memoria/ui-settings.json` → 当前目录（历史兼容，早于 task-160）。"""
    if os.environ.get("MEMORIA_CONFIG_DIR"):
        return
    legacy = _legacy_settings_path()
    if target.is_file() or not legacy.is_file():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, target)
        logger.info("ui-settings 已从 %s 迁移到 %s", legacy, target)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ui-settings 历史迁移失败（不影响启动）：%s", exc)


def load_ui_settings() -> dict[str, Any]:
    path = settings_path()
    # 顺序有讲究：先做**安装目录 → 用户目录**的一次性迁移（task-160 的主迁移），
    # 再做历史 `~/.memoria` 兼容迁移（只在用户目录仍无文件时才生效）。
    _migrate_from_install_dir(path)
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
    # 原子写（M1，A7）：tmp + os.replace，避免半程崩溃留下损坏的 ui-settings
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)
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
