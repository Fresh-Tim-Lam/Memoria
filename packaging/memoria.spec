# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec → 输出到 Package/Memoria.exe + lib/ + resources/。"""

from pathlib import Path

PKG = Path(SPECPATH).resolve()
ROOT = PKG.parent
SRC = ROOT / "src"
ICON = ROOT / "resources" / "icons" / "Memoria.ico"

_HEAVY_EXCLUDES = [
    "PyQt6",
    "PySide6",
    "PySide2",
    "PyQt5",
    "gi",
    "tensorflow",
    "keras",
    "sklearn",
    "scipy",
    "pandas",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "pygame",
    "OpenGL",
    "altair",
    "gradio",
    "datasets",
    "tensorboard",
    "onnxruntime",
    "cv2",
    "PIL.ImageQt",
]

block_cipher = None

a = Analysis(
    [str(PKG / "app_release.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        (str(SRC / "memoria" / "ui" / "static"), "memoria/ui/static"),
    ],
    hiddenimports=[
        "memoria.app.runtime",
        "memoria.app.shell.pywebview",
        "memoria.app.shell.pywebview_host",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "bottle",
        "jieba",
        "yaml",
        # Embedding 检索层依赖
        "torch",
        "transformers",
        "transformers.models.auto",
        "transformers.models.auto.modeling_auto",
        "transformers.models.auto.tokenization_auto",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(PKG / "pyi_rth_memoria.py")],
    excludes=_HEAVY_EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Memoria",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="lib",
    manifest=str(PKG / "memoria.manifest"),
    icon=str(ICON) if ICON.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Memoria",
    contents_directory="lib",
)
