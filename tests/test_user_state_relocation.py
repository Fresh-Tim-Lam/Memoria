"""用户态移出安装目录（task-160）：默认路径 + 一次性迁移 + 幂等。

## 背景（人报的真问题）

> 「用户拿到新的发行版本的压缩包，这个压缩包没有他旧的使用痕迹」

根因：`ui-settings.json` 与 `agent.json` 都存在 `<install_root>/config/` —— **安装目录内**。
⇒ 用户解压覆盖新包 ⇒ config 被覆盖 ⇒ 丢 LLM 配置（含 API key）+ 丢最近库列表。
⇒ 用户解压到新目录 ⇒ 旧 config 留在旧目录 ⇒ 同样丢。

`packaging/build.py` 的 `_RELEASE_PRESERVE_DIRS` 只保护**构建机**的 Package，对最终用户换包无效。

## 本文件守的四条不变量

1. **默认落点在用户目录**，不在安装目录；
2. **旧有/新无 ⇒ 迁移**（只复制不删）；
3. **两边都有 ⇒ 以新位置为准，绝不覆盖**（用户在新区改过的是最新的）← 最容易写错；
4. **迁移失败 ⇒ 应用不挂**（走默认值）。

以及：`MEMORIA_CONFIG_DIR` / `MEMORIA_AGENT_CONFIG` 覆盖仍然有效。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memoria.services.agent import llm
from memoria.services.agent.llm import config as llm_config
from memoria.storage import ui_settings


@pytest.fixture()
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """把「用户目录」与「安装目录」都指到 tmp_path 下的独立子目录。

    返回 `(user_dir, install_dir)` —— 两个目录互不包含，模拟真实布局。
    """
    user_dir = tmp_path / "user-config"
    install_dir = tmp_path / "fake-install"
    install_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("MEMORIA_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MEMORIA_AGENT_CONFIG", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # ⇒ user_config_dir() = tmp_path/Memoria/config

    # 让 install_root() 返回伪安装目录（两处迁移都从它读旧文件）
    monkeypatch.setattr("memoria.app.runtime.install_root", lambda: install_dir, raising=True)
    # 隔离更早的历史位置 `~/.memoria/ui-settings.json`（真机上它可能真实存在，
    # 不隔离会让"无旧配置"的用例读到它 —— 那是历史兼容迁移，不是本任务要测的行为）
    monkeypatch.setattr(
        "memoria.storage.ui_settings._legacy_settings_path",
        lambda: tmp_path / "no-such-home-legacy" / "ui-settings.json",
        raising=True,
    )
    return tmp_path / "Memoria" / "config", install_dir


# ── ① 默认落点不在安装目录 ─────────────────────────────────────────────────


def test_settings_dir_defaults_to_user_dir(isolated) -> None:
    user_dir, install_dir = isolated
    assert ui_settings.settings_path() == user_dir / "ui-settings.json"
    assert install_dir not in ui_settings.settings_path().parents, "不得落在安装目录内"


def test_agent_config_defaults_to_user_dir(isolated) -> None:
    user_dir, install_dir = isolated
    path = llm_config.config_file_path(env={})
    assert install_dir not in path.parents, "不得落在安装目录内"
    assert path.name == llm_config.CONFIG_FILENAME


def test_memoria_config_dir_override_still_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """显式覆盖仍然有效（测试/便携模式依赖它）。"""
    custom = tmp_path / "custom"
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(custom))
    assert ui_settings.settings_path() == custom / "ui-settings.json"
    assert llm_config.config_file_path(env={"MEMORIA_CONFIG_DIR": str(custom)}) == Path(
        custom
    ) / llm_config.CONFIG_FILENAME


def test_memoria_agent_config_override_still_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "my-agent.json"
    assert llm_config.config_file_path(env={"MEMORIA_AGENT_CONFIG": str(custom)}) == custom


# ── ② 迁移：旧有 / 新无 ⇒ 迁移 ─────────────────────────────────────────────


def test_migrates_ui_settings_from_install_dir(isolated) -> None:
    user_dir, install_dir = isolated
    old = install_dir / "config" / "ui-settings.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"last_kb_path": "/old/kb", "recent_kbs": ["/old/kb"]}), encoding="utf-8")

    data = ui_settings.load_ui_settings()

    assert data.get("last_kb_path") == "/old/kb", "旧安装目录的配置必须被迁移读入"
    assert (user_dir / "ui-settings.json").is_file(), "迁移后新位置应有文件"
    assert old.is_file(), "【只复制不删】旧文件必须保留（可能是用户唯一备份）"


def test_migrates_agent_config_from_install_dir(isolated) -> None:
    user_dir, install_dir = isolated
    old = install_dir / "config" / llm_config.CONFIG_FILENAME
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"provider": "legacy-provider"}), encoding="utf-8")

    path = llm_config.config_file_path(env={})
    assert path.is_file(), "迁移后新位置应有 agent.json"
    assert json.loads(path.read_text(encoding="utf-8"))["provider"] == "legacy-provider"
    assert old.is_file(), "【只复制不删】旧文件必须保留"


# ── ③【最关键】两边都有 ⇒ 以新位置为准，不覆盖 ─────────────────────────────


def test_both_exist_new_wins_for_ui_settings(isolated) -> None:
    """**两边都有时，绝不把用户在新区改过的配置回滚成旧值。**

    这是本任务最容易写错的地方：如果迁移逻辑写成"旧位置存在就复制过去"，
    用户在新版里改的设置会在下次启动时被旧安装目录的陈旧值覆盖，
    而且**用户看不出发生了什么**（改了设置，重启就变了）。
    """
    user_dir, install_dir = isolated
    user_file = user_dir / "ui-settings.json"
    user_file.parent.mkdir(parents=True, exist_ok=True)
    user_file.write_text(json.dumps({"last_kb_path": "/NEW/kb"}), encoding="utf-8")

    old = install_dir / "config" / "ui-settings.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"last_kb_path": "/OLD/kb"}), encoding="utf-8")

    data = ui_settings.load_ui_settings()

    assert data["last_kb_path"] == "/NEW/kb", "两边都有时必须以新位置为准（不得被旧值覆盖）"
    # 新文件内容必须**原封不动**（不只是读的时候对）
    assert json.loads(user_file.read_text(encoding="utf-8"))["last_kb_path"] == "/NEW/kb"
    # 旧文件也不能被改动
    assert json.loads(old.read_text(encoding="utf-8"))["last_kb_path"] == "/OLD/kb"


def test_both_exist_new_wins_for_agent_config(isolated) -> None:
    """`agent.json`：两边都有 ⇒ 以用户目录为准（不覆盖）。"""
    user_dir, install_dir = isolated
    new_file = user_dir / llm_config.CONFIG_FILENAME
    new_file.parent.mkdir(parents=True, exist_ok=True)
    new_file.write_text(json.dumps({"provider": "NEW-provider"}), encoding="utf-8")

    old = install_dir / "config" / llm_config.CONFIG_FILENAME
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"provider": "OLD-provider"}), encoding="utf-8")

    path = llm_config.config_file_path(env={})

    assert path == new_file
    assert json.loads(path.read_text(encoding="utf-8"))["provider"] == "NEW-provider", (
        "两边都有时必须以用户目录为准（不得被旧安装目录的值覆盖）"
    )
    # 旧文件不得被改动
    assert json.loads(old.read_text(encoding="utf-8"))["provider"] == "OLD-provider"


# ── ④ 幂等：反复启动不反复迁移 ─────────────────────────────────────────────


def test_repeated_load_is_idempotent(isolated) -> None:
    _user_dir, install_dir = isolated
    old = install_dir / "config" / "ui-settings.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"last_kb_path": "/old/kb"}), encoding="utf-8")

    first = ui_settings.load_ui_settings()
    second = ui_settings.load_ui_settings()
    third = ui_settings.load_ui_settings()

    assert first == second == third, "重复加载必须稳定"
    assert first["last_kb_path"] == "/old/kb"


def test_user_edits_after_migration_are_not_overwritten(isolated) -> None:
    """迁移一次后，用户在新区改的值必须保留 —— 不能每次启动又从旧值覆盖回来。"""
    user_dir, install_dir = isolated
    old = install_dir / "config" / "ui-settings.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"last_kb_path": "/old/kb"}), encoding="utf-8")

    ui_settings.load_ui_settings()  # 触发迁移
    ui_settings.save_ui_settings({"last_kb_path": "/CHANGED/in/new"})  # 用户在新区改

    again = ui_settings.load_ui_settings()
    assert again["last_kb_path"] == "/CHANGED/in/new", "旧位置的陈旧值不得覆盖用户在新区的修改"


# ── ⑤ 旧无/新无 ⇒ 默认值；迁移失败 ⇒ 不挂 ──────────────────────────────────


def test_no_legacy_no_new_yields_defaults(isolated) -> None:
    assert ui_settings.load_ui_settings() == {}
    assert ui_settings.resolve_last_kb_path() is None


def test_migration_failure_does_not_break_startup(isolated, monkeypatch: pytest.MonkeyPatch) -> None:
    """迁移抛异常 ⇒ 应用仍能起来（走默认值），不得把启动弄挂。"""
    _user_dir, install_dir = isolated
    old = install_dir / "config" / "ui-settings.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"last_kb_path": "/old/kb"}), encoding="utf-8")

    def boom(*_a, **_kw):
        raise OSError("模拟复制失败（磁盘满/权限拒绝）")

    monkeypatch.setattr("memoria.storage.ui_settings.shutil.copy2", boom)

    assert ui_settings.load_ui_settings() == {}, "迁移失败时按默认值返回，不得抛异常"


def test_agent_config_migration_failure_does_not_raise(isolated, monkeypatch: pytest.MonkeyPatch) -> None:
    _user_dir, install_dir = isolated
    old = install_dir / "config" / llm_config.CONFIG_FILENAME
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"provider": "x"}), encoding="utf-8")

    def boom(*_a, **_kw):
        raise OSError("模拟复制失败")

    monkeypatch.setattr("memoria.services.agent.llm.config.shutil.copy2", boom)

    path = llm_config.config_file_path(env={})  # 不得抛
    assert path.name == llm_config.CONFIG_FILENAME


def test_explicit_env_dir_skips_migration(isolated, monkeypatch: pytest.MonkeyPatch) -> None:
    """显式指定配置目录时不迁移（测试隔离/便携模式不该被旧目录污染）。"""
    _user_dir, install_dir = isolated
    old = install_dir / "config" / "ui-settings.json"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"last_kb_path": "/old/kb"}), encoding="utf-8")

    custom = isolated[0].parent / "explicit"
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(custom))

    assert ui_settings.load_ui_settings() == {}
    assert not (custom / "ui-settings.json").exists()
