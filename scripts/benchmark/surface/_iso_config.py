"""共用配置隔离助手 —— 测试密封性（task-53/54）。

════════════════════════════════════════════════════════════════════════════
为什么需要它（真实事故）
════════════════════════════════════════════════════════════════════════════
开发机的 `config/ui-settings.json` 会被真机/无头测量脚本**隐式继承**（ambient）。
实测证据（task-53）：该文件 `search.embedding_enabled=true` 时，S11 的搜索（modes=both）
会在单线程 harness 内**同步构建 embedding 索引**（BERT 编码数百段），阻塞 >45s，
导致 S11 在 `07169792` / `045bbb6e` 上稳定红 —— 但这是**机器级配置泄漏**，
不是产品/剧本逻辑缺陷。

同样的泄漏也会污染**冻结基线**：如果 `S_render_frozen` 或 `p5_perf_frozen` 是在
ambient 配置下测的，它们的数值就依赖于开发机当时的 UI 设置（nav 策略、预览模式、
搜索模式…），换台机器/改个设置就漂移。

════════════════════════════════════════════════════════════════════════════
契约
════════════════════════════════════════════════════════════════════════════
· **默认隔离**：每次 run 创建一个**唯一的空**配置目录，设 `MEMORIA_CONFIG_DIR` 指向它。
  空目录 ⇒ 应用走默认值（如 search 默认 lexical），不读开发机 ui-settings.json。
· **诊断模式**（`ambient=True`）：完全不设 `MEMORIA_CONFIG_DIR`，行为与修复前一致
  （用于复现"配置泄漏导致的假红"、自证判别力）。
· **清理策略**：默认**保留**目录供事后诊断（体积很小：仅一个 json），
  并在 `manifest` 里记录路径。传 `cleanup=True` 可删。

════════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════════
Python:
    from _iso_config import isolate_config
    iso = isolate_config(script="run_fidelity", label=args.label,
                         ambient=getattr(args, "ambient_config", False))
    print(iso.describe())
    ...
    iso.cleanup_if_requested()

PowerShell（见 _iso_config.ps1）:
    Import-Module ./safe-kill.psm1
    . ./_iso_config.ps1
    $iso = Initialize-MemoriaConfigIsolation -Script 'run_domwrites' -Label $Label -Ambient:$AmbientConfig
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

# 仓库根（本文件位于 scripts/benchmark/surface/）
REPO_ROOT = Path(__file__).resolve().parents[3]

#: 与配置隔离相关的环境变量（应用侧读取这些决定配置目录）
CONFIG_ENV_VARS = (
    "MEMORIA_CONFIG_DIR",
    "MEMORIA_UI_SETTINGS",
)

#: 会把 ambient 配置带进来的环境变量前缀（诊断时提示用）
AMBIENT_HINTS = (
    "MEMORIA_",
    "DSH_",
)


class ConfigIsolation:
    """一次 run 的配置隔离句柄。"""

    def __init__(
        self,
        script: str,
        label: str,
        ambient: bool,
        config_dir: Path | None,
        *,
        keep: bool = True,
        previous: dict[str, str | None] | None = None,
    ) -> None:
        self.script = script
        self.label = label
        self.ambient = ambient
        self.config_dir = config_dir
        self.keep = keep
        self._previous = previous or {}
        self._cleaned = False

    # ── 状态 ──────────────────────────────────────────────────────────────
    @property
    def isolated(self) -> bool:
        return not self.ambient

    def describe(self) -> str:
        if self.ambient:
            leaked = {k: v for k, v in os.environ.items()
                      if any(k.startswith(p) for p in AMBIENT_HINTS)}
            return ("[iso] DIAG: ambient 配置（不隔离）—— 会继承开发机 ui-settings.json；"
                    f"当前相关环境变量 {len(leaked)} 个")
        return f"[iso] 密封配置目录: {self.config_dir}"

    def manifest(self) -> dict[str, Any]:
        """写进产物的密封性元数据。"""
        return {
            "isolated": self.isolated,
            "ambient": self.ambient,
            "config_dir": str(self.config_dir) if self.config_dir else None,
            "config_env": {k: os.environ.get(k) for k in CONFIG_ENV_VARS},
            "keep": self.keep,
            # 空配置目录 ⇒ 应用用默认值，不读开发机设置
            "config_dir_empty": (
                None if self.config_dir is None
                else not any(Path(self.config_dir).iterdir())
            ),
        }

    # ── 清理 ──────────────────────────────────────────────────────────────
    def cleanup_if_requested(self) -> None:
        """按 keep 策略清理；同时恢复本进程原有的环境变量。"""
        if self._cleaned:
            return
        self._cleaned = True
        # 恢复环境变量（避免同一进程内多次 run 互相影响）
        for k, v in self._previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if self.keep or self.config_dir is None:
            return
        shutil.rmtree(self.config_dir, ignore_errors=True)

    def __enter__(self) -> "ConfigIsolation":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.cleanup_if_requested()


def isolate_config(
    script: str,
    label: str = "run",
    ambient: bool = False,
    *,
    keep: bool = True,
    base: Path | None = None,
) -> ConfigIsolation:
    """为一次 run 建立配置隔离（默认隔离；`ambient=True` 仅诊断）。

    Parameters
    ----------
    script:
        脚本标识（用于目录命名与产物记录），如 ``run_fidelity``。
    label:
        本次 run 的 label（通常来自 ``--label``）。
    ambient:
        ``True`` ⇒ **不隔离**，继承开发机配置（仅用于诊断/自证判别力）。
    keep:
        ``True``（默认）⇒ 保留空配置目录供诊断；``False`` ⇒ 结束时删除。
    base:
        配置目录的父目录（默认仓库根）。目录形如
        ``artifacts/_<script>_config_<label>_<pid>``。

    Returns
    -------
    ConfigIsolation
        句柄；调用方应把 ``iso.manifest()`` 写进产物，并在结束时
        ``iso.cleanup_if_requested()``（或用 ``with``）。
    """
    previous = {k: os.environ.get(k) for k in CONFIG_ENV_VARS}

    if ambient:
        # 诊断模式：清掉可能由外层脚本设的隔离变量，确保"真的 ambient"
        for k in CONFIG_ENV_VARS:
            os.environ.pop(k, None)
        return ConfigIsolation(script, label, True, None, keep=keep, previous=previous)

    parent = (base or REPO_ROOT) / "artifacts"
    parent.mkdir(parents=True, exist_ok=True)
    # 用 tempfile.mkdtemp 保证唯一（并发安全）；前缀满足可读性要求
    safe_label = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(label))[:40]
    cfg_dir = Path(tempfile.mkdtemp(
        prefix=f"_{script}_config_{safe_label}_{os.getpid()}_",
        dir=str(parent),
    ))

    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg_dir)
    # UI 设置走 config 目录下的默认值；显式清掉可能覆盖它的变量
    os.environ.pop("MEMORIA_UI_SETTINGS", None)

    return ConfigIsolation(script, label, False, cfg_dir, keep=keep, previous=previous)


def add_isolation_arg(parser: Any, *, flag: str = "--ambient-config") -> Any:
    """给 argparse parser 加统一的诊断开关（默认隔离）。"""
    parser.add_argument(
        flag,
        dest="ambient_config",
        action="store_true",
        help="DIAG：不设 MEMORIA_CONFIG_DIR，继承开发机 config/ui-settings.json"
             "（用于复现配置泄漏导致的问题；正常验收不要打开）",
    )
    return parser


__all__ = [
    "ConfigIsolation",
    "isolate_config",
    "add_isolation_arg",
    "CONFIG_ENV_VARS",
    "REPO_ROOT",
]
