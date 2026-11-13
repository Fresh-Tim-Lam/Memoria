"""一键自动更新：下载完成后的受控替换（helper + staging + backup + rollback）。

与 `memoria.services.update` 分工：
- `update.py` 负责检查/下载/校验（已有行为不动）；
- 本模块只消费“已 done 的下载 job”，准备 job JSON，并在用户确认后启动 helper。
- helper 是 `resources/updater/apply_update.ps1`，在 Memoria 退出后运行。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memoria import __version__
from memoria.services.update import (
    _JOBS,
    _JOBS_LOCK,
    _config_dir,
    _now_iso,
    verify_downloaded_package,
)
from memoria.util.proc import no_window_kwargs

# ── 一键自动更新（C10 后续；显式用户确认后的受控替换）────────────────────────
#
# 约束（见 docs/design/auto-update.md）：
#   · 只在 frozen + Windows 下可用；开发态直接返回 unsupported；
#   · 只接受本进程内“下载已完成”的 job（不信任前端任意路径/URL）；
#   · helper 在 Memoria 退出后运行，staging/backup/rollback 全部由 helper 做；
#   · 不删除知识库，不碰 %LOCALAPPDATA%\\Memoria\\config；lite 保留 hf/。
AUTO_JOB_FILE = "update-job.json"
AUTO_RESULT_FILE = "update-result.json"


def _app_root() -> Path:
    """发布态应用根目录（exe 所在目录）；开发态返回仓库根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def auto_update_supported() -> dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "code": "unsupported_os", "message": "自动更新目前只支持 Windows"}
    if not getattr(sys, "frozen", False):
        return {"ok": False, "code": "unsupported_dev", "message": "开发态不支持自动替换应用目录"}
    app = _app_root()
    if not (app / "Memoria.exe").is_file():
        return {"ok": False, "code": "unsupported_layout", "message": "应用目录结构不支持自动更新"}
    return {"ok": True, "app_dir": str(app)}


def _auto_job_path() -> Path:
    return _config_dir() / AUTO_JOB_FILE


def _auto_result_path() -> Path:
    return _config_dir() / AUTO_RESULT_FILE


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def prepare_auto_update(job_id: str) -> dict[str, Any]:
    """校验已下载完成的 job，写 job JSON；不启动 helper、不退出应用。"""
    support = auto_update_supported()
    if not support.get("ok"):
        return {"status": "unsupported", "code": support.get("code"), "message": support.get("message")}

    with _JOBS_LOCK:
        job = json.loads(json.dumps(_JOBS.get(str(job_id)) or {}))
    if not job:
        return {"status": "error", "code": "unknown_job", "message": "未知下载作业，请重新下载"}
    if job.get("status") != "done":
        return {"status": "error", "code": "not_done", "message": "下载尚未完成"}

    zip_path = Path(str(job.get("path") or ""))
    asset = job.get("asset") if isinstance(job.get("asset"), dict) else {}
    expected_version = str(asset.get("version") or "")
    expected_sha = str(asset.get("sha256") or "")
    expected_bytes = int(asset.get("bytes") or 0)
    if not zip_path.is_file():
        return {"status": "error", "code": "missing_file", "message": "下载文件不存在，请重新下载"}
    if not expected_sha:
        return {"status": "error", "code": "no_sha256", "message": "发布资产缺少 sha256，拒绝自动更新"}

    checked = verify_downloaded_package(
        zip_path,
        expected_version=expected_version,
        expected_sha256=expected_sha,
        expected_bytes=expected_bytes,
    )
    if not checked.get("ok"):
        return {
            "status": "error",
            "code": "verify_failed",
            "message": "下载包校验失败，拒绝自动更新",
            "failures": checked.get("failures") or [],
        }

    app_dir = Path(support["app_dir"])
    # 应用目录必须可写；Program Files 等只读安装应退化为手动替换。
    try:
        with tempfile.NamedTemporaryFile(dir=str(app_dir), prefix=".memoria-update-write-test-", delete=True):
            pass
    except Exception as exc:  # noqa: BLE001
        return {"status": "unsupported", "code": "app_dir_readonly", "message": f"应用目录不可写，请用手动更新：{exc}"}

    # staging + 备份都需要空间；保守按 zip 的 2.5 倍估计。
    try:
        free = shutil.disk_usage(app_dir).free
        if free < max(64 * 1024 * 1024, int(zip_path.stat().st_size * 2.5)):
            return {"status": "error", "code": "not_enough_space", "message": "磁盘空间不足，无法安全解压并保留备份"}
    except Exception:
        pass

    helper = _app_root() / "resources" / "updater" / "apply_update.ps1"
    if not helper.is_file():
        return {"status": "unsupported", "code": "helper_missing", "message": "自动更新 helper 未随包安装"}
    temp_dir = Path(tempfile.mkdtemp(prefix="memoria-update-helper-"))
    helper_copy = temp_dir / "apply_update.ps1"
    shutil.copy2(helper, helper_copy)

    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    backup_dir = app_dir.parent / f"{app_dir.name}.backup-{__version__}-{stamp}"
    if backup_dir.exists():
        backup_dir = app_dir.parent / f"{app_dir.name}.backup-{__version__}-{stamp}-{uuid.uuid4().hex[:4]}"
    auto_job = {
        "job_id": str(job_id),
        "parent_pid": os.getpid(),
        "zip_path": str(zip_path),
        "target_dir": str(app_dir),
        "exe_name": "Memoria.exe",
        "variant": str(asset.get("kind") or ""),
        "from_version": __version__,
        "to_version": expected_version,
        "sha256": expected_sha,
        "backup_dir": str(backup_dir),
        "result_path": str(_auto_result_path()),
        "log_path": str(_config_dir() / "auto-update.log"),
        "helper_path": str(helper_copy),
        "created_at": now.isoformat(),
    }
    job_path = _auto_job_path()
    _write_json_atomic(job_path, auto_job)
    return {
        "status": "ok",
        "job_id": str(job_id),
        "job_file": str(job_path),
        "from_version": __version__,
        "to_version": expected_version,
        "variant": auto_job["variant"],
        "backup_dir": str(backup_dir),
        "app_dir": str(app_dir),
        "verify_mode": checked.get("mode"),
    }


def _destroy_window_later() -> None:
    try:
        import webview  # type: ignore

        for window in list(getattr(webview, "windows", []) or []):
            try:
                window.destroy()
            except Exception:
                pass
    except Exception:  # noqa: BLE001
        pass


def start_auto_update(job_id: str) -> dict[str, Any]:
    """启动 helper 并在短暂延迟后关闭本应用；helper 等待本进程退出后替换目录。"""
    support = auto_update_supported()
    if not support.get("ok"):
        return {"status": "unsupported", "code": support.get("code"), "message": support.get("message")}
    job_path = _auto_job_path()
    if not job_path.is_file():
        return {"status": "error", "code": "no_job", "message": "没有待执行的更新作业，请先准备更新"}
    try:
        auto_job = json.loads(job_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "bad_job", "message": f"更新作业损坏：{exc}"}
    if str(auto_job.get("job_id") or "") != str(job_id or ""):
        return {"status": "error", "code": "job_mismatch", "message": "更新作业与下载作业不匹配"}
    if int(auto_job.get("parent_pid") or 0) != os.getpid():
        return {"status": "error", "code": "stale_job", "message": "更新作业已过期，请重新准备"}
    helper = Path(str(auto_job.get("helper_path") or ""))
    if not helper.is_file():
        return {"status": "error", "code": "helper_missing", "message": "自动更新 helper 不存在"}

    powershell = shutil.which("powershell.exe") or str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    cmd = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(helper),
        "-JobFile",
        str(job_path),
    ]
    creation = no_window_kwargs()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(tempfile.gettempdir())),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **creation,
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "spawn_failed", "message": f"无法启动更新 helper：{exc}"}
    auto_job["helper_pid"] = proc.pid
    auto_job["started_at"] = _now_iso()
    _write_json_atomic(job_path, auto_job)
    # 给 RPC 一个返回窗口，再销毁窗口；helper 会等待本进程退出。
    threading.Timer(1.0, _destroy_window_later).start()
    return {"status": "ok", "helper_pid": proc.pid, "message": "正在退出并应用更新"}


def get_auto_update_result() -> dict[str, Any] | None:
    path = _auto_result_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None
