"""YAML 原子写入与最新备份（M3 L2）。"""

from __future__ import annotations

import logging
import os
import shutil
import stat
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

BACKUP_SUFFIX = ".bak"


def backup_path(path: Path) -> Path:
    return path.with_name(path.name + BACKUP_SUFFIX)


def write_backup(path: Path) -> Path | None:
    """若目标已存在，复制为同目录 `.bak`（仅保留最新一版）。

    备份是尽力而为的冗余操作：目标被占用 / 置为只读 / 权限受限时降级跳过
    并记录日志，不阻断主写入（此前该处 PermissionError 会让发布态首次启动
    直接崩溃）。
    """
    if not path.is_file():
        return None
    bak = backup_path(path)
    try:
        if bak.is_file():
            # 解除可能存在的只读属性（杀毒 / 同步工具可能置位）
            try:
                bak.chmod(bak.stat().st_mode | stat.S_IWRITE)
            except OSError:
                pass
        shutil.copy2(path, bak)
        return bak
    except OSError as exc:
        logger.warning("write_backup skipped %s: %s", bak, exc)
        return None


def atomic_write_yaml(path: str | Path, data: dict) -> None:
    """写入前备份 → `.tmp` → fsync → replace。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_backup(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def restore_from_backup(path: str | Path) -> bool:
    """从 `.bak` 恢复；成功返回 True。"""
    path = Path(path)
    bak = backup_path(path)
    if not bak.is_file():
        return False
    shutil.copy2(bak, path)
    return True
