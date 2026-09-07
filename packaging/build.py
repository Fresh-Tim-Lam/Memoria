#!/usr/bin/env python3
"""构建 Memoria 发布包 → Package/Memoria.exe + lib/ + resources/。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parent
SPEC = PKG / "memoria.spec"
DIST_STAGING = PKG / "dist" / "Memoria"
RELEASE = ROOT / "Package"
RELEASE_EXE = RELEASE / "Memoria.exe"
RELEASE_LIB = RELEASE / "lib"
RELEASE_RES = RELEASE / "resources"
TEMPLATES = PKG / "templates"
CONTENTS_DIR = "lib"
_RELEASE_PRESERVE_DIRS = frozenset({"config"})

# 语义/重排模型随包内置：构建时从本地 HuggingFace 缓存（hub/models--<org>--<name>）
# 拷到 Package/hf/hub/…；运行端把 HF_HOME 指向 Package/hf（见 embedding/rerank provider）。
RELEASE_HF = RELEASE / "hf"
BUNDLE_MODELS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)


def _default_hf_hub_src() -> Path:
    env = os.environ.get("MEMORIA_MODELS_SRC")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "huggingface" / "hub"


def _bundle_hf_models() -> list[str]:
    """拷贝离线模型快照到 Package/hf/hub/，返回实际内置的模型 id。"""
    src_hub = _default_hf_hub_src()
    if not src_hub.is_dir():
        print(f"[memoria.build] 未找到 HF 缓存 {src_hub}，跳过模型内置", file=sys.stderr)
        return []
    dest_hub = RELEASE_HF / "hub"
    dest_hub.mkdir(parents=True, exist_ok=True)
    bundled: list[str] = []
    for repo in BUNDLE_MODELS:
        src = src_hub / f"models--{repo.replace('/', '--')}"
        if not src.is_dir():
            print(f"[memoria.build] 模型未缓存，跳过内置: {repo}", file=sys.stderr)
            continue
        shutil.copytree(src, dest_hub / src.name, dirs_exist_ok=True)
        bundled.append(repo)
    return bundled


EXAMPLES_IGNORE = shutil.ignore_patterns(
    ".memoria",
    ".build",
    "__pycache__",
    "*.pyc",
    ".git",
)


def _read_version() -> str:
    """版本唯一事实源：src/memoria/__version__.py。

    构建产物（VERSION / manifest / README）与运行时 UI 显示的版本
    均由此而来。pyproject.toml 已声明 dynamic version（attr 指向本文件），
    无需（也无法）人工同步。
    """
    ver_file = ROOT / "src" / "memoria" / "__version__.py"
    match = re.search(
        r'__version__\s*=\s*"([^"]+)"',
        ver_file.read_text(encoding="utf-8"),
    )
    version = match.group(1) if match else "0.0.0"
    pyproj = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pymatch = re.search(r'^version\s*=\s*"([^"]+)"', pyproj, re.MULTILINE)
    if pymatch and pymatch.group(1) != version:
        raise SystemExit(
            f"[memoria.build] 版本不一致：src/memoria/__version__.py={version}，"
            f"但 pyproject.toml={pymatch.group(1)}。请先统一到 {version} 再构建。"
        )
    return version


def _sync_app_icons() -> None:
    """resources/icons → UI static，供 Web 顶栏与 favicon 使用。"""
    src_dir = ROOT / "resources" / "icons"
    if not src_dir.is_dir():
        return
    dest_dir = ROOT / "src" / "memoria" / "ui" / "static" / "icons"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, dest_dir / item.name)


def _run_pyinstaller(*, clean: bool) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm"]
    if clean:
        cmd.append("--clean")
    cmd += [
        "--distpath",
        str(PKG / "dist"),
        "--workpath",
        str(PKG / "build"),
    ]
    subprocess.check_call(cmd, cwd=str(ROOT))


def _resolve_contents_dir(staging: Path) -> Path:
    preferred = staging / CONTENTS_DIR
    if preferred.is_dir():
        return preferred
    legacy = staging / "_internal"
    if legacy.is_dir():
        return legacy
    raise FileNotFoundError(
        f"未找到依赖目录 {CONTENTS_DIR}/ 或 _internal/: {staging}"
    )


def _verify_release_bundle() -> None:
    dll = RELEASE_LIB / "python312.dll"
    if not dll.is_file():
        raise FileNotFoundError(f"发布包不完整，缺少: {dll}")
    exe_data = RELEASE_EXE.read_bytes()
    if b"pyi-contents-directory _internal" in exe_data:
        raise RuntimeError(
            "Memoria.exe 仍指向 _internal/，与 lib/ 布局不一致；"
            "请确认 spec 中 EXE/COLLECT 均设置 contents_directory='lib' 后重新 --clean 构建"
        )


def _clean_release_dir() -> None:
    RELEASE.mkdir(parents=True, exist_ok=True)
    for child in RELEASE.iterdir():
        if child.name.startswith(".") or child.name in _RELEASE_PRESERVE_DIRS:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


# 应用内文档白名单：docs/reference 下随包拷贝（弹窗"查看格式说明" get_reference_doc 发布态读取）
_REFERENCE_DOC_BUNDLE = ("preview-formats.md",)


def _stage_runtime_resources() -> None:
    """随包资源登记表：新增随包目录必须在此登记，并同步 packaging/README.md §随包资源登记。

    语义：
    - resources/icons、resources/agent-prompts：运行态 RPC（图标 / get_agent_prompt）直接读取，
      **必须**随包；漏拷会导致发布态功能缺失。
    - resources/docs（白名单 _REFERENCE_DOC_BUNDLE）：弹窗"查看格式说明"（get_reference_doc）
      发布态读取；**必须**随包。
    - examples / example-boonie：官方示例库（可选目录，缺失时跳过）。
    """
    targets = [
        (ROOT / "resources" / "icons", RELEASE_RES / "icons", None),
        (ROOT / "resources" / "agent-prompts", RELEASE_RES / "agent-prompts", None),
        (ROOT / "examples", RELEASE_RES / "examples", EXAMPLES_IGNORE),
        (ROOT / "example-boonie", RELEASE_RES / "example-boonie", EXAMPLES_IGNORE),
    ]
    for src, dest, ignore in targets:
        if src.is_dir():
            shutil.copytree(src, dest, ignore=ignore, dirs_exist_ok=True)
    # docs/reference 白名单单文件随包（保持目录结构与源码一致：docs/…）
    for name in _REFERENCE_DOC_BUNDLE:
        src_doc = ROOT / "docs" / "reference" / name
        if src_doc.is_file():
            docs_dest = RELEASE_RES / "docs"
            docs_dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_doc, docs_dest / name)


_REQUIRED_RELEASE_RESOURCES = (
    "agent-prompts/organize.zh-CN.md",  # 程序内 Agent 整理提示词（单一事实源，运行态 RPC 读取）
    "docs/preview-formats.md",  # 弹窗格式说明（get_reference_doc，发布态读取）
    "icons/Memoria.ico",
    "icons/Memoria.png",
)


def _verify_release_resources() -> None:
    """构建后自检：登记表内「必带」资源若缺失则终止，防止静默漏包。"""
    missing = [
        rel
        for rel in _REQUIRED_RELEASE_RESOURCES
        if not (RELEASE_RES / rel).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "发布包 resources/ 缺失必带资源: " + ", ".join(missing) +
            "。若为新增资源未登记，请补充 packaging/build.py _stage_runtime_resources 登记表。"
        )


def _stage_release(version: str) -> None:
    if not DIST_STAGING.is_dir():
        raise FileNotFoundError(f"PyInstaller 产物不存在: {DIST_STAGING}")

    exe_src = DIST_STAGING / "Memoria.exe"
    if not exe_src.is_file():
        raise FileNotFoundError(f"未找到可执行文件: {exe_src}")

    lib_src = _resolve_contents_dir(DIST_STAGING)

    _clean_release_dir()

    shutil.move(str(exe_src), str(RELEASE_EXE))
    dest_lib = RELEASE / lib_src.name
    shutil.move(str(lib_src), str(dest_lib))
    if dest_lib.name != CONTENTS_DIR:
        dest_lib.rename(RELEASE_LIB)
    RELEASE_RES.mkdir(parents=True, exist_ok=True)
    _stage_runtime_resources()
    bundled_models = _bundle_hf_models()

    meta = {
        "name": "Memoria",
        "version": version,
        "shell": "pywebview",
        "mode": "release",
        "built_at": datetime.now(UTC).isoformat(),
        "executable": "Memoria.exe",
        "layout": {
            "exe": "Memoria.exe",
            "lib": "lib/",
            "resources": "resources/",
            "config": "config/ui-settings.json",
            "hf": "hf/",
        },
        "semantic_models": bundled_models,
    }
    (RELEASE / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (RELEASE / "manifest.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    readme_tpl = TEMPLATES / "README.release.txt"
    if readme_tpl.is_file():
        readme = readme_tpl.read_text(encoding="utf-8").replace("{version}", version)
        (RELEASE / "README.txt").write_text(readme, encoding="utf-8")

    _verify_release_bundle()
    _ensure_release_config()
    _verify_release_resources()
    shutil.rmtree(PKG / "dist", ignore_errors=True)


def _ensure_release_config() -> None:
    """保留用户 config/ui-settings.json，并确保 config/ 目录与说明存在。"""
    config_dir = RELEASE / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    readme_tpl = TEMPLATES / "config" / "README.txt"
    if readme_tpl.is_file():
        shutil.copy2(readme_tpl, config_dir / "README.txt")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建 Memoria 发布包（输出到 Package/）")
    parser.add_argument("--no-clean", action="store_true", help="跳过 PyInstaller --clean")
    args = parser.parse_args(argv)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("需要 PyInstaller：pip install pyinstaller", file=sys.stderr)
        return 1

    version = _read_version()
    print(f"[memoria.build] version={version}")
    _sync_app_icons()
    _run_pyinstaller(clean=not args.no_clean)
    _stage_release(version)
    print(f"[memoria.build] done -> {RELEASE_EXE}")
    print(f"[memoria.build] distribute: {RELEASE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
