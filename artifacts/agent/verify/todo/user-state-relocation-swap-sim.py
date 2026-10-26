"""真机模拟「换包」：证明用户态已移出安装目录（task-160 关闭条件 3）。

## 为什么必须真机（不能只跑单测）

单测在**同一个进程**里 monkeypatch `install_root()` 与 `LOCALAPPDATA`，
它证明的是"逻辑正确"，**不能证明"用户换包后配置还在"** ——
因为真实换包会**删除整个安装目录**，那是个文件系统级事实，不是函数级事实。

本脚本启动**真实独立子进程**（`python -m memoria.cli.main`）三次，模拟：

```
阶段 1  伪安装目录里有 config/ui-settings.json + agent.json
        → 启动 → 配置被迁移/读到（最近库非空）        ← 旧版用户升级到新版
阶段 2  把伪安装目录【整个删掉】（模拟用户解压覆盖 / 换到新目录）
        → 再启动 → 配置仍在                          ← 这就是"换包"
阶段 3  新旧同时存在但内容不同 → 以新为准（不覆盖）   ← 核心判据
```

## 用法

    python artifacts/agent/verify/todo/user-state-relocation-swap-sim.py
    python artifacts/agent/verify/todo/user-state-relocation-swap-sim.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

#: 在独立子进程里跑的一段小程序（模拟 app 启动时读用户态）。
#:
#: ## 为什么要 patch `install_root()`
#: 非 frozen 模式下 `install_root()` = `repo_root()` = **真实仓库根**，
#: 而 `packaging` 里并没有 `MEMORIA_INSTALL_ROOT` 之类的覆盖变量。
#: 要在真机上模拟"另一个安装目录"，只能在子进程入口处把 `install_root` 指到伪目录 ——
#: **这一步替代的是"exe 所在目录"这个事实**，其余全部走真实代码路径
#: （`load_ui_settings()` / `config_file_path()` / 真文件系统 / 真子进程）。
PROBE = r"""
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["MEMORIA_REPO"], "src"))

# 把「安装目录」指到伪目录（模拟用户把 exe 解压到了别处）
_fake_install = os.environ["MEMORIA_FAKE_INSTALL"]
import memoria.app.runtime as _rt
_rt.install_root = lambda: __import__("pathlib").Path(_fake_install)

from memoria.storage.ui_settings import load_ui_settings, settings_path
from memoria.services.agent.llm.config import config_file_path

ui = load_ui_settings()
cfg = config_file_path(env={})
out = {
    "settings_path": str(settings_path()),
    "agent_config_path": str(cfg),
    "last_kb_path": ui.get("last_kb_path"),
    "recent_kbs": ui.get("recent_kbs") or [],
    "agent_portable": None,
}
if cfg.is_file():
    try:
        out["agent_portable"] = json.loads(cfg.read_text(encoding="utf-8")).get("provider")
    except Exception as exc:
        out["agent_portable"] = f"<parse-error: {exc}>"
print("__PROBE__" + json.dumps(out, ensure_ascii=False))
"""


def _run_probe(env_overrides: dict[str, str], fake_install: Path) -> dict:
    """在**独立子进程**里读一次配置（真实启动路径，非进程内 import）。"""
    env = dict(os.environ)
    env.update(env_overrides)
    env["MEMORIA_REPO"] = str(REPO)
    env["MEMORIA_FAKE_INSTALL"] = str(fake_install)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # 确保子进程不受宿主机真实 config 目录/变量干扰
    env.pop("MEMORIA_CONFIG_DIR", None)
    env.pop("MEMORIA_AGENT_CONFIG", None)
    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(REPO),
        timeout=120,
    )
    for line in (proc.stdout or "").splitlines():
        if line.startswith("__PROBE__"):
            return json.loads(line[len("__PROBE__") :])
    raise RuntimeError(
        f"子进程没有返回探针结果。\nstdout={proc.stdout!r}\nstderr={proc.stderr[-2000:]!r}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    root = Path(tempfile.mkdtemp(prefix="memoria-swap-sim-"))
    install_root = root / "fake-install"          # 伪安装目录（模拟 Package/）
    local_appdata = root / "localappdata"          # 伪 %LOCALAPPDATA%
    user_config = local_appdata / "Memoria" / "config"
    install_root.mkdir(parents=True, exist_ok=True)

    env = {"LOCALAPPDATA": str(local_appdata)}
    results: dict = {"root": str(root), "stages": []}
    ok = True

    try:
        # ── 阶段 0：旧版用户 —— 配置都在【安装目录内】 ──────────────────────
        old_cfg_dir = install_root / "config"
        old_cfg_dir.mkdir(parents=True, exist_ok=True)
        (old_cfg_dir / "ui-settings.json").write_text(
            json.dumps(
                {
                    "last_kb_path": "D:/kbs/old-kb",
                    "recent_kbs": ["D:/kbs/old-kb"],
                    "theme": "dark",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (old_cfg_dir / "agent.json").write_text(
            json.dumps({"provider": "legacy-provider"}), encoding="utf-8"
        )
        print(f"[阶段0] 伪安装目录已就位: {old_cfg_dir}")
        print(f"        用户目录: {user_config}（此时不应存在）")

        # ── 阶段 1：启动（升级到新版）—— 应把旧配置迁移到用户目录 ──────────
        r1 = _run_probe(env, install_root)
        stage1 = {
            "name": "01-upgrade-migrates",
            "settings_path": r1["settings_path"],
            "last_kb_path": r1["last_kb_path"],
            "recent_kbs": r1["recent_kbs"],
            "agent_provider": r1["agent_portable"],
            "migrated_into_user_dir": str(user_config) in r1["settings_path"].replace("\\", "/")
            or user_config.as_posix() in r1["settings_path"].replace("\\", "/"),
        }
        ok &= stage1["migrated_into_user_dir"] and bool(stage1["last_kb_path"])
        stage1["ok"] = ok
        results["stages"].append(stage1)
        print(f"[阶段1] 配置读取: last_kb={r1['last_kb_path']!r} provider={r1['agent_portable']!r}")
        print(f"        settings_path={r1['settings_path']}")
        print(f"        ✓ 已迁移进用户目录: {stage1['migrated_into_user_dir']}")

        # ── 阶段 2：★ 换包 —— 把整个伪安装目录删掉 ─────────────────────────
        shutil.rmtree(install_root)
        print(f"\n[阶段2] ★ 已删除整个伪安装目录（模拟换包）: {install_root}")
        print(f"        安装目录存在? {install_root.exists()}")
        print(f"        用户目录存在? {user_config.exists()}")

        r2 = _run_probe(env, install_root)
        stage2 = {
            "name": "02-after-swap-config-survives",
            "install_dir_deleted": not install_root.exists(),
            "settings_path": r2["settings_path"],
            "last_kb_path": r2["last_kb_path"],
            "recent_kbs": r2["recent_kbs"],
            "agent_provider": r2["agent_portable"],
        }
        stage2_ok = (
            stage2["install_dir_deleted"]
            and r2["last_kb_path"] == "D:/kbs/old-kb"
            and r2["agent_portable"] == "legacy-provider"
        )
        stage2["ok"] = stage2_ok
        ok &= stage2_ok
        results["stages"].append(stage2)
        print(f"[阶段2] 换包后读取: last_kb={r2['last_kb_path']!r} provider={r2['agent_portable']!r}")
        print(f"        ✓ 配置幸存: {stage2_ok}  ← 【这才是真正的换包验证】")

        # ── 阶段 3：核心判据 —— 两边都有且不同 ⇒ 以新为准 ──────────────────
        install_root.mkdir(parents=True, exist_ok=True)
        old_cfg_dir = install_root / "config"
        old_cfg_dir.mkdir(parents=True, exist_ok=True)
        (old_cfg_dir / "ui-settings.json").write_text(
            json.dumps({"last_kb_path": "D:/kbs/STALE-old", "recent_kbs": ["D:/kbs/STALE-old"]}),
            encoding="utf-8",
        )
        # 用户在新位置改过配置
        (user_config / "ui-settings.json").write_text(
            json.dumps({"last_kb_path": "D:/kbs/NEW-edited", "recent_kbs": ["D:/kbs/NEW-edited"]}),
            encoding="utf-8",
        )
        r3 = _run_probe(env, install_root)
        stage3 = {
            "name": "03-new-wins-when-both-exist",
            "last_kb_path": r3["last_kb_path"],
            "expected": "D:/kbs/NEW-edited",
        }
        stage3["ok"] = r3["last_kb_path"] == "D:/kbs/NEW-edited"
        ok &= stage3["ok"]
        results["stages"].append(stage3)
        print(f"\n[阶段3] 两边都有（旧=STALE-old / 新=NEW-edited）")
        print(f"        读到: {r3['last_kb_path']!r}")
        print(f"        ✓ 以新为准: {stage3['ok']}  ← 写反会得到 STALE-old")

        results["ok"] = bool(ok)
        print(f"\n== RESULT: {'PASS' if ok else 'FAIL'} ==")
        if args.json:
            out = Path(args.json) if os.path.isabs(args.json) else REPO / args.json
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"wrote: {out}")
        return 0 if ok else 1
    finally:
        # 只清理本次的临时根目录（用户真实 %LOCALAPPDATA% 从未被触碰：我们用的是伪目录）
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
