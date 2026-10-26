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

    ## 合并策略（task-179 起：**per-key + mtime 较新者胜**）

    早期实现是「新位置有文件 ⇒ 直接 return」（不看 mtime），后果是：
    用户升级后，旧构建在安装目录里改过的设置（API key / 主题 / 窗口位置）**静默丢失**。
    实测 2026-10-26：安装目录 `ui-settings.json` 是 19:41，用户态是前一天 01:28 ⇒ 该更新被丢弃。

    现在：逐键合并，冲突键取 **mtime 较新**的一方；mtime 相等/不可判 ⇒ **保守保留用户态**；
    任一侧独有的键一律保留（并集）。详见 `memoria.util.user_state.merge_by_mtime`。

    ## 只复制不删

    旧位置可能是用户**唯一的备份**：若将来用户清了 `%LOCALAPPDATA%`，
    安装目录里的那份还在，还能救回来。迁移**只改用户态文件的内容**，**不删不动**旧文件。

    ## 异常一律吞掉

    迁移是"锦上添花"，失败不能让应用起不来；此时按用户态现有内容（或默认值）继续。
    """
    if os.environ.get("MEMORIA_CONFIG_DIR"):
        return  # 显式指定目录时不迁移（测试/便携模式）
    try:
        legacy = _install_config_dir() / _SETTINGS_FILE
        if not legacy.is_file():
            return  # 旧位置无 ⇒ 无迁移

        from memoria.util.user_state import file_mtime, merge_by_mtime

        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, target)  # 只复制，不删源
            logger.info(
                "ui-settings 已从旧安装目录迁移到用户目录：%s → %s（旧文件保留未删）",
                legacy,
                target,
            )
            return

        # ── 两侧都有 ⇒ per-key 合并 ────────────────────────────────────
        try:
            current = json.loads(target.read_text(encoding="utf-8-sig"))
            incoming = json.loads(legacy.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("ui-settings 合并跳过（解析失败，保留用户态现有内容）：%s", exc)
            return
        if not isinstance(current, dict) or not isinstance(incoming, dict):
            logger.warning("ui-settings 合并跳过（顶层不是对象，保留用户态现有内容）")
            return

        merged, adopted = merge_by_mtime(
            current=current,
            incoming=incoming,
            current_mtime=file_mtime(target),
            incoming_mtime=file_mtime(legacy),
        )
        if merged == current:
            return  # 无变化 ⇒ 不写盘（避免无谓 churn）
        _write_json_atomic(target, merged)
        logger.info(
            "ui-settings 合并完成：从旧安装目录采纳 %d 项 %s（旧文件保留未删）",
            len(adopted),
            adopted,
        )
    except Exception as exc:  # noqa: BLE001 - 迁移绝不能影响启动
        logger.warning("ui-settings 迁移失败（不影响启动，使用现有值）：%s", exc)


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """原子写（tmp + os.replace），避免半程崩溃留下损坏的配置文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".migrate-tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


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
