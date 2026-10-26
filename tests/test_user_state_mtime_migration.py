"""用户态迁移策略：按 mtime 较新者胜（task-179）。

## 为什么改（Lead 实测的真缺陷）

task-160 的迁移策略是「copy-only-never-delete」+「两边都存在 ⇒ 以新为准」，
但"以新为准"**被实现成"以用户态为准"**，不是"以 mtime 较新者为准"：

    src/memoria/storage/ui_settings.py    if target.is_file(): return   ← 不看 mtime
    src/memoria/services/agent/llm/config.py   if target.is_file(): return

实测后果（2026-10-26 22:45）：

| 文件 | Package（安装目录） | 用户态 | 谁更新 |
|---|---|---|---|
| `agent.json` | **10-26 18:13** | 09-24 13:59 | **Package** |
| `ui-settings.json` | **10-26 19:41** | 10-25 01:28 | **Package** |

⇒ 用户当前跑的是 task-160 之前的旧构建，它一直在写 `install_root()/config`；
新构建首次启动时用户态已存在 ⇒ **旧构建里 18:13 那次改动（API key / 设置）静默丢失**。

## 为什么是 **per-key** 而不是 per-file（这是本任务最关键的设计判断）

实测两份 `agent.json` 的键集合**不同**：

```
Package : api_key, base_url, model, status_refresh_ms, timeout_s
用户态  : api_key, base_url, enabled, model, script_use_bundled,
          status_refresh_ms, timeout_s, transcript_mode
```

- `api_key`：Package **更新**（sk-18eb75f7… vs sk-7ac67dbd…）⇒ 必须采纳 Package
- `enabled` / `script_use_bundled` / `transcript_mode`：**只在用户态有** ⇒ 必须保留

⇒ **若按 per-file 整文件覆盖**：Package 更新就整文件盖过去 ⇒
**用户态独有的 3 个键全部丢失**（enabled / script_use_bundled / transcript_mode）——
这比原 bug 更糟。

⇒ **必须 per-key 合并**：逐键比较，值不同才看 mtime；只在一侧存在的键一律保留。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from memoria.services.agent.llm import config as llm_config
from memoria.storage import ui_settings


def _set_mtime(path: Path, ts: float) -> None:
    os.utime(path, (ts, ts))


def _write_json(path: Path, data: dict, *, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if mtime is not None:
        _set_mtime(path, mtime)
    return path


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """隔离：用户目录 + 伪安装目录 + 历史 legacy 路径，全部指到 tmp_path。"""
    user_dir = tmp_path / "Memoria" / "config"
    install_dir = tmp_path / "fake-install"
    install_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("MEMORIA_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MEMORIA_AGENT_CONFIG", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("memoria.app.runtime.install_root", lambda: install_dir, raising=True)
    monkeypatch.setattr(
        "memoria.storage.ui_settings._legacy_settings_path",
        lambda: tmp_path / "no-home-legacy" / "ui-settings.json",
        raising=True,
    )
    return user_dir, install_dir


# ── T-mig-1【核心，改动前必须红】Package 侧 mtime 更新 ⇒ 采用 Package 的值 ──────


def test_T_mig_1_package_newer_wins_ui_settings(env) -> None:
    """Package 侧更新且值不同 ⇒ 启动后用户态采用 Package 的值。"""
    user_dir, install_dir = env
    user_file = _write_json(user_dir / "ui-settings.json", {"theme": "light"}, mtime=1_000_000)
    pkg_file = _write_json(
        install_dir / "config" / "ui-settings.json", {"theme": "dark"}, mtime=2_000_000
    )

    ui_settings.load_ui_settings()  # 触发迁移

    got = json.loads(user_file.read_text(encoding="utf-8"))
    assert got["theme"] == "dark", (
        f"Package 侧 mtime({pkg_file.stat().st_mtime}) 更新 ⇒ 应采用 dark，实际 {got.get('theme')!r}"
    )


def test_T_mig_1b_package_newer_wins_agent_config(env) -> None:
    """agent.json 同理：Package 的 api_key 更新 ⇒ 采用 Package 的 key。"""
    user_dir, install_dir = env
    user_file = _write_json(
        user_dir / llm_config.CONFIG_FILENAME, {"api_key": "sk-OLD"}, mtime=1_000_000
    )
    _write_json(
        install_dir / "config" / llm_config.CONFIG_FILENAME,
        {"api_key": "sk-NEW"},
        mtime=2_000_000,
    )

    llm_config.config_file_path(env={})  # 触发迁移

    got = json.loads(user_file.read_text(encoding="utf-8"))
    assert got["api_key"] == "sk-NEW", f"应采用 Package 的新 key，实际 {got.get('api_key')!r}"


# ── T-mig-2 反过来：用户态 mtime 更新 ⇒ 采用用户态 ─────────────────────────────


def test_T_mig_2_user_newer_wins(env) -> None:
    user_dir, install_dir = env
    user_file = _write_json(user_dir / "ui-settings.json", {"theme": "light"}, mtime=2_000_000)
    _write_json(install_dir / "config" / "ui-settings.json", {"theme": "dark"}, mtime=1_000_000)

    ui_settings.load_ui_settings()

    got = json.loads(user_file.read_text(encoding="utf-8"))
    assert got["theme"] == "light", "用户态更新 ⇒ 应保留用户态（不得被旧的 Package 值覆盖）"


# ── T-mig-3 mtime 不可比较 ⇒ 保守：保留用户态 ────────────────────────────────


def test_T_mig_3_equal_mtime_keeps_user(env) -> None:
    user_dir, install_dir = env
    user_file = _write_json(user_dir / "ui-settings.json", {"theme": "light"}, mtime=1_500_000)
    _write_json(install_dir / "config" / "ui-settings.json", {"theme": "dark"}, mtime=1_500_000)

    ui_settings.load_ui_settings()

    got = json.loads(user_file.read_text(encoding="utf-8"))
    assert got["theme"] == "light", "mtime 相等无法判断 ⇒ 保守保留用户态"


def test_T_mig_3b_missing_pkg_mtime_keeps_user(env, monkeypatch: pytest.MonkeyPatch) -> None:
    """Package 侧 mtime 读取抛错（模拟 stat 失败）⇒ 保守保留用户态，不抛异常。"""
    user_dir, install_dir = env
    user_file = _write_json(user_dir / "ui-settings.json", {"theme": "light"}, mtime=1_000_000)
    _write_json(install_dir / "config" / "ui-settings.json", {"theme": "dark"}, mtime=2_000_000)

    real_stat = Path.stat

    def flaky_stat(self, *a, **kw):
        if self.name == "ui-settings.json" and "fake-install" in str(self):
            raise OSError("模拟 stat 失败")
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    ui_settings.load_ui_settings()  # 不得抛

    got = json.loads(user_file.read_text(encoding="utf-8"))
    assert got["theme"] == "light", "mtime 不可判 ⇒ 保守保留用户态"


# ── T-mig-4 两边都保留（copy-only，不删 Package 侧）────────────────────────────


def test_T_mig_4_package_side_never_deleted(env) -> None:
    user_dir, install_dir = env
    _write_json(user_dir / "ui-settings.json", {"theme": "light"}, mtime=1_000_000)
    pkg_file = _write_json(
        install_dir / "config" / "ui-settings.json", {"theme": "dark", "x": 1}, mtime=2_000_000
    )
    pkg_before = pkg_file.read_text(encoding="utf-8")

    ui_settings.load_ui_settings()

    assert pkg_file.is_file(), "【绝不删除任何一边】Package 侧文件必须保留"
    assert pkg_file.read_text(encoding="utf-8") == pkg_before, "Package 侧内容不得被改动"


# ── T-mig-5 幂等：连续启动 3 次结果稳定 ──────────────────────────────────────


def test_T_mig_5_idempotent_across_three_starts(env) -> None:
    user_dir, install_dir = env
    _write_json(user_dir / "ui-settings.json", {"theme": "light"}, mtime=1_000_000)
    _write_json(install_dir / "config" / "ui-settings.json", {"theme": "dark"}, mtime=2_000_000)

    results = []
    for _ in range(3):
        ui_settings.load_ui_settings()
        fp = user_dir / "ui-settings.json"
        results.append(json.loads(fp.read_text(encoding="utf-8")))

    assert results[0] == results[1] == results[2], f"三次启动结果必须稳定，实际 {results}"
    assert results[0]["theme"] == "dark"


# ── T-mig-7 迁移失败不阻断启动 ──────────────────────────────────────────────


def test_T_mig_7_migration_failure_does_not_raise(env, monkeypatch: pytest.MonkeyPatch) -> None:
    user_dir, install_dir = env
    _write_json(user_dir / "ui-settings.json", {"theme": "light"}, mtime=1_000_000)
    _write_json(install_dir / "config" / "ui-settings.json", {"theme": "dark"}, mtime=2_000_000)

    def boom(*_a, **_kw):
        raise OSError("模拟写失败（磁盘满/权限拒绝）")

    monkeypatch.setattr("memoria.storage.ui_settings.shutil.copy2", boom)

    # 不得抛异常
    data = ui_settings.load_ui_settings()
    assert isinstance(data, dict), "迁移失败必须返回可用的 dict（哪怕降级为旧值/默认值）"


# ── ★ per-key 合并：这是本任务最容易写错的地方（比 mtime 本身更容易）──────────


def test_per_key_merge_preserves_user_only_keys(env) -> None:
    """**Package 更新时，只覆盖它有的键；用户态独有的键必须保留。**

    实测真实数据：Package 的 agent.json 缺 `enabled` / `script_use_bundled` / `transcript_mode`，
    而用户态有。若按 per-file 整文件覆盖 ⇒ 这 3 个键全部丢失（比原 bug 更糟）。
    """
    user_dir, install_dir = env
    user_file = _write_json(
        user_dir / llm_config.CONFIG_FILENAME,
        {"api_key": "sk-OLD", "enabled": True, "transcript_mode": "normal"},
        mtime=1_000_000,
    )
    _write_json(
        install_dir / "config" / llm_config.CONFIG_FILENAME,
        {"api_key": "sk-NEW"},  # 注意：Package 侧没有 enabled / transcript_mode
        mtime=2_000_000,
    )

    llm_config.config_file_path(env={})

    got = json.loads(user_file.read_text(encoding="utf-8"))
    assert got["api_key"] == "sk-NEW", "Package 更新 ⇒ api_key 采用 Package"
    assert got.get("enabled") is True, "用户态独有的 enabled 必须保留（per-key 合并）"
    assert got.get("transcript_mode") == "normal", "用户态独有的 transcript_mode 必须保留"


def test_per_key_merge_pkg_only_keys_are_added(env) -> None:
    """Package 独有、用户态没有的键 ⇒ 补入（否则新版本新增的默认键永远到不了用户态）。"""
    user_dir, install_dir = env
    user_file = _write_json(
        user_dir / llm_config.CONFIG_FILENAME, {"api_key": "sk-same"}, mtime=1_000_000
    )
    _write_json(
        install_dir / "config" / llm_config.CONFIG_FILENAME,
        {"api_key": "sk-same", "new_feature_flag": 1},
        mtime=2_000_000,
    )

    llm_config.config_file_path(env={})

    got = json.loads(user_file.read_text(encoding="utf-8"))
    assert got.get("new_feature_flag") == 1, "Package 独有键应补入"


def test_same_value_different_mtime_no_needless_write(env) -> None:
    """值相同 ⇒ 不必因 mtime 而改写（减少无谓写盘与 churn）。"""
    user_dir, install_dir = env
    user_file = _write_json(user_dir / "ui-settings.json", {"theme": "dark"}, mtime=1_000_000)
    before = user_file.stat().st_mtime
    _write_json(install_dir / "config" / "ui-settings.json", {"theme": "dark"}, mtime=2_000_000)

    ui_settings.load_ui_settings()

    got = json.loads(user_file.read_text(encoding="utf-8"))
    assert got == {"theme": "dark"}
    assert user_file.stat().st_mtime == before, "值相同不应改写文件（避免无谓 churn）"


# ── 显式目录覆盖仍然优先（task-160 的既有约束不得回退）──────────────────────


def test_explicit_config_dir_still_skips_migration(env, monkeypatch: pytest.MonkeyPatch) -> None:
    user_dir, install_dir = env
    _write_json(install_dir / "config" / "ui-settings.json", {"theme": "dark"}, mtime=2_000_000)
    explicit = user_dir.parent / "explicit"
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(explicit))

    assert ui_settings.load_ui_settings() == {}
    assert not (explicit / "ui-settings.json").exists(), "显式目录模式不得被旧目录污染"
