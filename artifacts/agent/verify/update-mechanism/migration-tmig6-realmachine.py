"""T-mig-6 真机：用【真实 Package/config】+【真实用户态】的副本模拟一次升级（task-179）。

## 为什么必须真机（不能只跑单测）

单测里的两个配置文件是**人造的**。真实场景的差异在于：
- 真实 `Package/config/agent.json` 的 **key 集合与用户态不同**（缺 enabled/script_use_bundled/transcript_mode）
- 真实 mtime 差距是 **一个多月**（10-26 18:13 vs 09-24 13:59），不是几秒
- 真实值不同（api_key 两个不同的 sk-）

## 安全边界（本脚本绝不改真实数据）

- `Package/config/**`：**只读复制**，不写不回写
- 真实 `%LOCALAPPDATA%\\Memoria\\config\\**`：**只读复制**，不写
- 全部操作在 `%TEMP%` 下的临时目录里做，结束即删

## 判定

升级后用户态 `agent.json` 的 `api_key` 必须等于 **Package 侧（18:13 那份）** 的值，
且用户态独有的 `enabled` / `transcript_mode` 等键必须**仍然存在**。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PKG_CFG = REPO / "Package" / "config"
USER_CFG = Path(os.environ.get("LOCALAPPDATA", "")) / "Memoria" / "config"

sys.path.insert(0, str(REPO / "src"))


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def main() -> int:
    if not PKG_CFG.is_dir():
        print(f"[SKIP] 未找到 {PKG_CFG}（本机无 Package 构建）")
        return 0
    if not USER_CFG.is_dir():
        print(f"[SKIP] 未找到 {USER_CFG}")
        return 0

    pkg_agent = PKG_CFG / "agent.json"
    usr_agent = USER_CFG / "agent.json"
    if not pkg_agent.is_file() or not usr_agent.is_file():
        print("[SKIP] 两侧 agent.json 不齐")
        return 0

    pkg = _load(pkg_agent)
    usr = _load(usr_agent)
    print("=== 升级前（真实数据，只读）===")
    print(f"  Package : mtime={pkg_agent.stat().st_mtime:.0f}  api_key={str(pkg.get('api_key'))[:14]}…")
    print(f"  用户态  : mtime={usr_agent.stat().st_mtime:.0f}  api_key={str(usr.get('api_key'))[:14]}…")
    print(f"  Package 更新: {pkg_agent.stat().st_mtime > usr_agent.stat().st_mtime}")
    print(f"  用户态独有键: {sorted(set(usr) - set(pkg))}")

    # ── 在 %TEMP% 里造假安装目录 + 假用户目录，用真实内容 ──────────────────
    root = Path(tempfile.mkdtemp(prefix="tmig6-"))
    fake_install = root / "fake-install"
    fake_local = root / "localappdata"
    fake_user_cfg = fake_local / "Memoria" / "config"
    fake_user_cfg.mkdir(parents=True, exist_ok=True)
    (fake_install / "config").mkdir(parents=True, exist_ok=True)

    # 复制真实文件（保留 mtime = shutil.copy2 默认行为）
    shutil.copy2(pkg_agent, fake_install / "config" / "agent.json")
    shutil.copy2(usr_agent, fake_user_cfg / "agent.json")

    # 把 ui-settings 也带上（更接近真实升级）
    for name in ("ui-settings.json",):
        s_pkg = PKG_CFG / name
        s_usr = USER_CFG / name
        if s_pkg.is_file():
            shutil.copy2(s_pkg, fake_install / "config" / name)
        if s_usr.is_file():
            shutil.copy2(s_usr, fake_user_cfg / name)

    before_api = _load(fake_user_cfg / "agent.json").get("api_key")
    before_keys = set(_load(fake_user_cfg / "agent.json"))

    # ── 驱动真实的迁移代码 ────────────────────────────────────────────────
    os.environ["LOCALAPPDATA"] = str(fake_local)
    os.environ.pop("MEMORIA_CONFIG_DIR", None)
    os.environ.pop("MEMORIA_AGENT_CONFIG", None)

    import memoria.app.runtime as rt

    orig_install_root = rt.install_root
    rt.install_root = lambda: fake_install  # 模拟"exe 在这个目录"
    try:
        from memoria.services.agent.llm import config as llm_config
        from memoria.storage import ui_settings

        # 让 ui_settings 的历史 legacy 迁移不干扰
        ui_settings._legacy_settings_path = lambda: root / "no-legacy" / "ui-settings.json"
        ui_settings.load_ui_settings()
        llm_config.config_file_path(env={})
    finally:
        rt.install_root = orig_install_root

    after = _load(fake_user_cfg / "agent.json")
    after_keys = set(after)
    after_api = after.get("api_key")

    print()
    print("=== 升级后（模拟结果）===")
    print(f"  用户态 api_key: {str(before_api)[:14]}… → {str(after_api)[:14]}…")
    print(f"  用户态键数: {len(before_keys)} → {len(after_keys)}")
    print(f"  Package 独有的键是否补入: {sorted(set(pkg) - before_keys)} → 现在有 {sorted(set(pkg) - before_keys & after_keys) or '全部有'}")

    ok_api = after_api == pkg.get("api_key")
    lost_user_keys = before_keys - after_keys
    lost_pkg_keys = set(pkg) - after_keys
    ok_keep_user = not lost_user_keys
    ok_adopt_pkg = not lost_pkg_keys
    # Package 侧文件必须仍在（copy-only）
    ok_pkg_intact = (fake_install / "config" / "agent.json").is_file()

    print()
    print(f"  [{'OK' if ok_api else 'FAIL'}] 采纳 Package 侧更新的 api_key（18:13 那次改动不丢）")
    print(f"  [{'OK' if ok_keep_user else 'FAIL'}] 用户态独有键全部保留 {sorted(lost_user_keys) or ''}")
    print(f"  [{'OK' if ok_adopt_pkg else 'FAIL'}] Package 独有的键补入 {sorted(lost_pkg_keys) or ''}")
    print(f"  [{'OK' if ok_pkg_intact else 'FAIL'}] Package 侧文件未被删除")

    all_ok = ok_api and ok_keep_user and ok_adopt_pkg and ok_pkg_intact
    print()
    print(f"== RESULT: {'PASS' if all_ok else 'FAIL'} ==")
    shutil.rmtree(root, ignore_errors=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
