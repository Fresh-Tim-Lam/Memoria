#!/usr/bin/env python3
"""图标流水线：把 resources/icons/*.png 生成多尺寸 .ico，并同步到运行时 web 图标目录。

用法：
    python scripts/icons/build_icons.py            # 增量生成（源图没变就跳过）
    python scripts/icons/build_icons.py --force    # 强制重建
    python scripts/icons/build_icons.py --check    # 只检查是否过期（CI/提交前用，过期退出码 1）
    python scripts/icons/build_icons.py --list     # 列出会处理哪些源图

约定（"指定名称即生效"）：
    · 源图放在 resources/icons/，文件名去掉 .png 就是图标名
      例：Memoria.png  →  Memoria.ico + Memoria-big.ico
    · 源图建议为正方形且边长 ≥ 256（会自动跳过大于源图的尺寸，避免放大糊掉）
    · 应用图标名（默认 Memoria）的 ico+png 会同步到 src/memoria/ui/static/icons/，
      供 index.html 的 favicon 与顶栏 logo 使用；换图标只改这一处源图。
    · 其他名字的图标只生成在 resources/icons/（打包或后续用途）。

消费方（都不需要改动，路径已固定）：
    · packaging/memoria.spec  → resources/icons/Memoria.ico（打包进 exe）
    · memoria.app.shell.app_icon → resources/icons/Memoria.ico 优先（窗口/任务栏）
    · index.html favicon + .logo-icon → /icons/<应用图标名>.ico

依赖：Pillow（仅本脚本需要，不是运行时依赖）。缺失时给出安装提示。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = REPO_ROOT / "resources" / "icons"
STATIC_ICON_DIR = REPO_ROOT / "src" / "memoria" / "ui" / "static" / "icons"

# 应用图标名：其 ico/png 会同步到运行时静态目录（index.html 写死了 /icons/Memoria.ico）
APP_ICON_NAME = "Memoria"

# 标准尺寸：Windows 常用的一组；按源图上限截断
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
BIG_SIZE = 256


def _require_pillow():
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        sys.exit(
            "缺少 Pillow，图标流水线需要它：\n"
            "    pip install Pillow\n"
            "（只是本脚本的开发期依赖，不写进运行时依赖）"
        )
    return Image


def discover_sources() -> list[Path]:
    """源图 = resources/icons/ 下的 *.png。

    忽略两类文件名（避免把草稿/备份也生成成 ico）：
      · 下划线开头（`_draft.png`）
      · 含 copy / 副本 / backup / bak / orig / old 等字样（Windows 复制/备份的常见命名）
    """
    if not SOURCE_DIR.is_dir():
        sys.exit(f"源目录不存在：{SOURCE_DIR}")
    skip_words = ("copy", "副本", "backup", "bak", "orig", "old")
    out = []
    for p in sorted(SOURCE_DIR.glob("*.png")):
        if p.name.startswith("_"):
            continue
        low = p.stem.lower()
        if any(w in low for w in skip_words):
            continue
        out.append(p)
    return out


def _is_stale(outputs: list[Path], source: Path) -> bool:
    """任一产物缺失或比源图旧 → 需要重建。"""
    for out in outputs:
        if not out.is_file() or out.stat().st_mtime < source.stat().st_mtime:
            return True
    return False


def build_one(Image, source: Path, force: bool) -> list[str]:
    """生成 <Name>.ico（多尺寸）与 <Name>-big.ico（仅 256）；返回动作说明列表。"""
    name = source.stem
    ico = SOURCE_DIR / f"{name}.ico"
    big = SOURCE_DIR / f"{name}-big.ico"
    actions: list[str] = []

    img = Image.open(source).convert("RGBA")
    if img.width != img.height:
        actions.append(f"警告：{source.name} 不是正方形（{img.width}×{img.height}），图标会被拉伸")
    max_side = max(img.size)
    sizes = [s for s in ICON_SIZES if s <= max_side] or [max_side]

    if force or _is_stale([ico, big], source):
        img.save(ico, format="ICO", sizes=[(s, s) for s in sizes])
        img.resize((BIG_SIZE, BIG_SIZE), Image.LANCZOS).save(
            big, format="ICO", sizes=[(BIG_SIZE, BIG_SIZE)]
        )
        actions.append(f"{name}: 生成 {ico.name} {sizes} + {big.name} [{BIG_SIZE}]")
    else:
        actions.append(f"{name}: 已是最新（跳过）")

    # 应用图标：同步到运行时静态目录（favicon / 顶栏 logo）
    if name == APP_ICON_NAME:
        STATIC_ICON_DIR.mkdir(parents=True, exist_ok=True)
        static_ico = STATIC_ICON_DIR / f"{name}.ico"
        static_png = STATIC_ICON_DIR / f"{name}.png"
        shutil.copy2(ico, static_ico)
        shutil.copy2(source, static_png)
        actions.append(f"{name}: 已同步到 {static_ico.parent.relative_to(REPO_ROOT)}/")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description="图标流水线（png → 多尺寸 ico + 同步运行时图标）")
    parser.add_argument("--force", action="store_true", help="忽略时间戳，强制重建")
    parser.add_argument("--check", action="store_true", help="只检查是否过期，过期退出码 1")
    parser.add_argument("--list", action="store_true", help="只列出会处理的源图")
    args = parser.parse_args()

    sources = discover_sources()
    if not sources:
        sys.exit(f"{SOURCE_DIR} 下没有 .png 源图")

    if args.list:
        for p in sources:
            print(f"{p.name}  ({SOURCE_DIR.relative_to(REPO_ROOT)})")
        return 0

    Image = _require_pillow()

    if args.check:
        stale = []
        for src in sources:
            outs = [SOURCE_DIR / f"{src.stem}.ico", SOURCE_DIR / f"{src.stem}-big.ico"]
            if src.stem == APP_ICON_NAME:
                outs.append(STATIC_ICON_DIR / f"{APP_ICON_NAME}.ico")
            if _is_stale(outs, src):
                stale.append(src.name)
        if stale:
            print("图标已过期，请运行 python scripts/icons/build_icons.py：")
            for n in stale:
                print(f"  · {n}")
            return 1
        print(f"图标均为最新（{len(sources)} 个源图）")
        return 0

    for src in sources:
        for line in build_one(Image, src, args.force):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
