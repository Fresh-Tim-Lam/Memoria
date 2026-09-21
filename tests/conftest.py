"""测试全局隔离：**任何测试都不得写真实 `config/**`**（autouse，无需各测试显式声明）。

**背景（2026-09-20 实测事故）**：`DocumentService(kb_path=...)` 打开库会走「记录最近打开」链路
（`storage/ui_settings.remember_last_kb_path`）⇒ 未隔离时会把**临时库路径**写进**真实**
`config/ui-settings.json`（`last_kb_path` 与 `recent_kbs` 被污染；该文件被 `.gitignore:7` 忽略
⇒ **无 git 兜底、不可回滚**）。此前仓库靠各测试自己 `monkeypatch.setenv("MEMORIA_CONFIG_DIR", …)`
（7 处），**漏一处就出事故** —— 本文件把这条约束提到全局默认。

口径：每个测试一个**独立的临时配置目录**（函数级 `tmp_path`）⇒ 测试之间也不串味。
各测试**仍可**自行 `monkeypatch.setenv` 覆盖（同一机制、后设者胜）；本 fixture 只保证
「默认不碰真实目录」。
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_memoria_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把 `MEMORIA_CONFIG_DIR` 指到本次测试专属的临时目录（`config/**` 的写入全部落在这里）。"""
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(tmp_path / "memoria-config"))
