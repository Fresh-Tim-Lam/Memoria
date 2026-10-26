"""版本更新机制（task-180）：检查更新 / 下载安装包 / 完整性校验（**不含数字签名**）。

## 三条硬纪律

1. **出网关闭 ⇒ 零请求**：`check_for_update()` / `start_update_download()` 在
   `services.agent.llm.config.is_enabled()` 为 False 时**在发起任何网络调用之前**返回
   `offline`/`disabled`；测试通过可注入 opener 证明"一次都没调用"。
2. **启动性能**：自动检查由前端 `setTimeout` 延迟触发；本模块本身不在应用启动路径上。
3. **隐私**：只发标准 `GET` + `User-Agent`（+ GitHub 要求的 `Accept`），不携带任何本地数据。

## 完整性校验的诚实边界（task-181 裁决）

发布包内（或资产旁）若带 `release-manifest.json`，则逐文件核对 sha256/bytes、zip 条目集合、
重复条目、路径穿越、EOCD 尾随数据；**不做数字签名验证**。
因此 UI 只能写「**已校验包结构与完整性（不含数字签名）**」；
**禁止**出现「防篡改 / 安全 / 已签名」这类会造成假安全感的措辞。
没有清单时退化为「体积 + zip 可打开 + 条目数合理」，UI 明确写「未校验完整性」。

## 公开入口（被 `presentation/api/ui.py` 的 RPC 调用）

- `check_for_update(manual=False)` -> 检查结果（fail-open，永不抛异常）
- `get_update_state()` -> 当前版本 / 出网开关 / 自动检查配置 / 上次检查缓存
- `start_update_download(asset_name)` -> {job_id}
- `get_update_download_status(job_id)` / `cancel_update_download(job_id)`
- `open_download_folder()`
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memoria import __version__
from memoria.util.proc import no_window_kwargs

logger = logging.getLogger(__name__)

# ── 发布源 / 隐私 ───────────────────────────────────────────────────────────
GITHUB_REPO = "Fresh-Tim-Lam/Memoria"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"Memoria/{__version__} (update-check)"
HTTP_TIMEOUT_S = 10.0
#: 自动检查限频（手动检查不受限）
AUTO_CHECK_INTERVAL_S = 24 * 3600
CHUNK = 256 * 1024
MAX_NOTES_CHARS = 20000
STATE_FILE = "update-state.json"

_ALLOWED_DOWNLOAD_HOSTS = (
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
)


def _allowed_download_hosts() -> tuple[str, ...]:
    """允许的资产下载 host。`MEMORIA_UPDATE_ALLOWED_HOSTS` 仅用于本地 mock 的端到端验证
    （生产 UI 不暴露该开关；真实下载只允许 GitHub 域名）。"""
    extra = [
        h.strip().lower()
        for h in (os.environ.get("MEMORIA_UPDATE_ALLOWED_HOSTS") or "").split(",")
        if h.strip()
    ]
    return tuple(_ALLOWED_DOWNLOAD_HOSTS) + tuple(extra)

_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════════


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_dir() -> Path:
    """复用 task-160 的用户态目录（`%LOCALAPPDATA%\\Memoria\\config`）。"""
    override = os.environ.get("MEMORIA_CONFIG_DIR")
    if override:
        return Path(override)
    try:
        from memoria.util.user_state import user_config_dir

        return user_config_dir()
    except Exception:  # noqa: BLE001 - 目录只是锦上添花
        return Path.home() / ".memoria" / "config"


def state_path() -> Path:
    return _config_dir() / STATE_FILE


def _load_state(path: Path | None = None) -> dict[str, Any]:
    p = path or state_path()
    try:
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:  # noqa: BLE001
        logger.debug("[update] state read failed: %r", exc)
    return {}


def _save_state(state: dict[str, Any], path: Path | None = None) -> None:
    p = path or state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    except Exception as exc:  # noqa: BLE001 - 状态缓存失败不能影响更新检查
        logger.debug("[update] state write failed: %r", exc)


def _version_key(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", str(text or ""))
    return tuple(int(n) for n in nums[:4]) if nums else (0,)


def is_newer(latest: str, current: str) -> bool:
    """纯数字版本比较（`v0.4.10 > v0.4.9`）；预发布后缀不参与（发布资产是正式 release）。"""
    a, b = _version_key(latest), _version_key(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def human_size(num: int | float | None) -> str:
    try:
        n = float(num or 0)
    except (TypeError, ValueError):
        n = 0.0
    if n <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB"]
    idx = 0
    while n >= 1024 and idx < len(units) - 1:
        n /= 1024.0
        idx += 1
    return f"{n:.1f} {units[idx]}" if idx else f"{int(n)} {units[idx]}"


def _outbound_enabled() -> bool:
    """与 balance/agent 同一个「出网」开关；读取失败时按**最保守**处理（不出网）。"""
    try:
        from memoria.services.agent.llm.config import is_enabled

        return bool(is_enabled())
    except Exception as exc:  # noqa: BLE001
        logger.debug("[update] outbound config unavailable: %r", exc)
        return False


def _http_json(url: str, *, timeout_s: float = HTTP_TIMEOUT_S) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 - 固定 GitHub API
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("release payload 不是对象")
    return data


def _asset_kind(name: str) -> str:
    n = str(name or "").lower()
    if n.endswith("-lite.zip") or "-lite" in n:
        return "lite"
    if n.endswith("-win64.zip") or (n.endswith(".zip") and "lite" not in n):
        return "full"
    if n.endswith(".json"):
        return "manifest"
    return "other"


def _sha_from_digest(digest: Any) -> str:
    text = str(digest or "")
    return text[7:] if text.startswith("sha256:") else ""


def parse_release(release: dict[str, Any], *, current_version: str = __version__) -> dict[str, Any]:
    """把 GitHub Releases API 的 `releases/latest` 响应转成 UI 友好的结构（纯函数，便于单测）。"""
    tag = str(release.get("tag_name") or "").strip()
    latest = tag[1:] if tag.lower().startswith("v") else tag
    assets: list[dict[str, Any]] = []
    for item in release.get("assets") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        kind = _asset_kind(name)
        if kind == "other":
            continue
        size = int(item.get("size") or 0)
        digest = _sha_from_digest(item.get("digest"))
        assets.append(
            {
                "name": name,
                "kind": kind,
                "bytes": size,
                "size_human": human_size(size),
                "url": str(item.get("browser_download_url") or ""),
                "sha256": digest,
                "recommended": kind == "lite",
                # full 包必须显式选择（人要求：lite 默认，full 1180MB 需明确）
                "requires_explicit_choice": kind == "full",
            }
        )
    assets.sort(key=lambda a: (a["kind"] != "lite", a["kind"] != "full", a["name"]))
    notes = str(release.get("body") or "")[:MAX_NOTES_CHARS]
    update_available = bool(latest) and is_newer(latest, current_version)
    return {
        "current_version": current_version,
        "latest_version": latest,
        "tag_name": tag,
        "update_available": update_available,
        "published_at": str(release.get("published_at") or ""),
        "release_url": str(release.get("html_url") or ""),
        "notes": notes,
        "assets": assets,
        "checked_at": _now_iso(),
    }


def _default_latest_url() -> str:
    # 仅测试用：显式覆盖 API 地址（例如本地 mock server）；生产固定 GitHub。
    return os.environ.get("MEMORIA_UPDATE_API_URL") or RELEASES_LATEST_URL


def check_for_update(
    *,
    manual: bool = False,
    http_get: Callable[[str], dict[str, Any]] | None = None,
    state_file: Path | None = None,
    current_version: str | None = None,
) -> dict[str, Any]:
    """检查更新。**fail-open**：网络/解析失败只能返回 error，绝不抛异常。

    出网关闭 ⇒ 在调用 `http_get` 之前返回 `offline`（T-upd-1：证明没发出去）。
    `manual=False` 时 24h 内复用上次成功结果（T-upd-2 的自动检查限频）。
    """
    current = current_version or __version__
    state = _load_state(state_file)
    if not _outbound_enabled():
        return {
            "status": "offline",
            "outbound_enabled": False,
            "current_version": current,
            "update_available": False,
            "message": "outbound disabled",
        }

    last = state.get("last_check_at") or ""
    if not manual and state.get("release") and last:
        try:
            last_ts = datetime.fromisoformat(last).timestamp()
            if time.time() - last_ts < AUTO_CHECK_INTERVAL_S:
                release = parse_release(state["release"], current_version=current)
                release.update({"status": "ok", "cached": True, "manual": False})
                return release
        except Exception as exc:  # noqa: BLE001
            logger.debug("[update] cached ts parse failed: %r", exc)

    get = http_get or _http_json
    try:
        release_raw = get(_default_latest_url())
        parsed = parse_release(release_raw, current_version=current)
    except Exception as exc:  # noqa: BLE001 - fail-open
        logger.info("[update] check failed (fail-open): %r", exc)
        state["last_attempt_at"] = _now_iso()
        _save_state(state, state_file)
        return {
            "status": "error",
            "outbound_enabled": True,
            "current_version": current,
            "update_available": False,
            "code": "network_error",
            "message": "检查失败，稍后再试",
            "detail": str(exc)[:300],
        }

    parsed.update({"status": "ok", "cached": False, "manual": bool(manual)})
    state.update(
        {
            "last_check_at": _now_iso(),
            "last_attempt_at": _now_iso(),
            "release": release_raw,
        }
    )
    _save_state(state, state_file)
    return parsed


def get_update_state(*, state_file: Path | None = None) -> dict[str, Any]:
    """UI 初始化读取（只读；不发任何网络请求）。"""
    state = _load_state(state_file)
    try:
        from memoria.storage.ui_settings import load_ui_settings

        settings = load_ui_settings() or {}
    except Exception:  # noqa: BLE001
        settings = {}
    update_cfg = settings.get("update") if isinstance(settings.get("update"), dict) else {}
    auto = update_cfg.get("autoCheck")
    auto_enabled = True if auto is None else bool(auto)
    cached: dict[str, Any] | None = None
    if state.get("release"):
        try:
            cached = parse_release(state["release"])
            cached.update({"status": "ok", "cached": True, "manual": False})
        except Exception:  # noqa: BLE001
            cached = None
    return {
        "status": "ok",
        "current_version": __version__,
        "outbound_enabled": _outbound_enabled(),
        "auto_check": auto_enabled,
        "last_check_at": state.get("last_check_at") or "",
        "config_dir": str(_config_dir()),
        "downloads_dir": str(_downloads_dir()),
        "cached": cached,
    }


# ══════════════════════════════════════════════════════════════════════════
# 下载 + 校验
# ══════════════════════════════════════════════════════════════════════════


class _Cancelled(Exception):
    pass


def _downloads_dir() -> Path:
    override = os.environ.get("MEMORIA_DOWNLOAD_DIR")
    if override:
        return Path(override)
    home = Path.home()
    for candidate in (home / "Downloads", home / "下载"):
        if candidate.is_dir():
            return candidate
    return _config_dir() / "updates"


def _unique_target(directory: Path, name: str) -> Path:
    safe = re.sub(r"[\\/:*?\"<>|]+", "_", Path(name).name) or "Memoria-update.zip"
    target = directory / safe
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for i in range(1, 1000):
        candidate = directory / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return directory / f"{stem}-{int(time.time())}{suffix}"


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_zip_entry(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    h = hashlib.sha256()
    with zf.open(info, "r") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _unsafe_zip_name(name: str) -> bool:
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[A-Za-z]:", n):
        return True
    return any(part == ".." for part in n.split("/"))


def _trailing_data_after_eocd(path: Path) -> bool:
    try:
        from memoria.services.verify.manifest import _has_trailing_data_after_eocd

        return bool(_has_trailing_data_after_eocd(path))
    except Exception:  # noqa: BLE001
        try:
            data = path.read_bytes()[-66000:]
            return data.rfind(b"PK\x05\x06") < 0
        except Exception:  # noqa: BLE001
            return False


def _read_manifest_from_zip(zf: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> dict[str, Any] | None:
    for info in infos:
        if info.filename.replace("\\", "/").rsplit("/", 1)[-1] != "release-manifest.json":
            continue
        try:
            payload = json.loads(zf.read(info).decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 清单读不出来 = 包已损坏，必须失败
            raise ValueError(f"release-manifest.json 无法读取：{exc}") from exc
        return payload if isinstance(payload, dict) else None
    return None


def verify_downloaded_package(
    path: str | Path,
    *,
    expected_version: str = "",
    expected_sha256: str = "",
    expected_bytes: int = 0,
) -> dict[str, Any]:
    """校验下载到的安装包（真源：包内 `release-manifest.json`，没有则退化为 zip 卫生检查）。

    返回 `{ok, mode, failures, verified_label, file_count, version}`：
    - `mode="manifest"`：逐文件 sha256/bytes + 条目集合双向 + zip 卫生；
    - `mode="zip-only"`：只有 zip 卫生（UI 必须写「未校验完整性」）；
    - `mode="size-only"`：连 zip 都打不开时（fail）。

    **不做数字签名验证**；正确表述「已校验包结构与完整性（不含数字签名）」。
    """
    target = Path(path)
    failures: list[str] = []
    if not target.is_file():
        return {
            "ok": False,
            "mode": "failed",
            "failures": [f"文件不存在：{target}"],
            "verified_label": "",
            "file_count": 0,
            "version": "",
        }
    actual_bytes = target.stat().st_size
    if expected_bytes and actual_bytes != int(expected_bytes):
        failures.append(f"文件大小不符：发布声明 {expected_bytes} 字节，实际 {actual_bytes} 字节")
    actual_sha = _sha256_path(target) if expected_sha256 else ""
    if expected_sha256 and actual_sha != expected_sha256:
        failures.append("文件 sha256 与发布声明不一致（可能下载损坏/不完整）")

    if _trailing_data_after_eocd(target):
        failures.append("zip 末尾存在 EOCD 之后的尾随数据（可能被追加内容或传输损坏）")

    try:
        with zipfile.ZipFile(target) as zf:
            infos = zf.infolist()
            files = [i for i in infos if not i.is_dir()]
            names = [i.filename for i in files]
            seen: set[str] = set()
            dupes = []
            for name in names:
                if name in seen:
                    dupes.append(name)
                seen.add(name)
            if dupes:
                failures.append(f"zip 存在同名重复条目：{sorted(set(dupes))}")
            unsafe = sorted({n for n in names if _unsafe_zip_name(n)})
            if unsafe:
                failures.append(f"zip 存在不安全路径（路径穿越/绝对路径）：{unsafe}")
            if not files:
                failures.append("zip 是空的（没有任何文件条目）")
            manifest = _read_manifest_from_zip(zf, files)
            if manifest is None:
                return {
                    "ok": not failures,
                    "mode": "zip-only" if not failures else "failed",
                    "failures": failures,
                    "verified_label": "",
                    "file_count": len(files),
                    "version": "",
                }

            # task-181 已交付客户端可复用入口：下载场景用 `check_asset_bytes=False`
            # （只校验包内文件内容/结构；是否与发布资产字节完全一致由前面的 GitHub assets
            #  size/sha256 另做校验，且重打包不应导致内容校验失败）。
            from memoria.services.verify.manifest import verify_package as _verify_package

            checked = _verify_package(
                target,
                manifest,
                expected_version=expected_version,
                check_asset_bytes=False,
            )
            if not checked.ok:
                failures.extend(checked.failures)
            version = str(manifest.get("version") or "")
            if expected_version and version and version != expected_version:
                failures.append(f"清单版本 {version} 与发布版本 {expected_version} 不一致")
            declared = manifest.get("files") if isinstance(manifest.get("files"), list) else []
            return {
                "ok": not failures,
                "mode": "manifest" if not failures else "failed",
                "failures": failures,
                "verified_label": "已校验包结构与完整性（不含数字签名）" if not failures else "",
                "file_count": len(declared),
                "version": version,
            }
    except zipfile.BadZipFile as exc:
        failures.append(f"不是合法 zip：{exc}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"校验失败：{exc}")
    return {
        "ok": False,
        "mode": "failed",
        "failures": failures,
        "verified_label": "",
        "file_count": 0,
        "version": "",
    }


def _update_job(job_id: str, **fields: Any) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.update(fields)
        job["updated_at"] = time.time()


def _download_worker(job_id: str, asset: dict[str, Any], target: Path, cancel: threading.Event) -> None:
    part = target.with_suffix(target.suffix + ".part")
    expected = int(asset.get("bytes") or 0)
    try:
        req = urllib.request.Request(
            str(asset.get("url")),
            headers={"User-Agent": USER_AGENT},
            method="GET",
        )
        received = 0
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp, part.open("wb") as fh:  # noqa: S310
            total = int(resp.headers.get("Content-Length") or expected or 0)
            _update_job(job_id, total=total, status="downloading")
            while True:
                if cancel.is_set():
                    raise _Cancelled()
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                received += len(chunk)
                _update_job(job_id, received=received, total=total or received)
                if total and received > total:
                    raise ValueError("下载字节数超过发布声明大小")
        if cancel.is_set():
            raise _Cancelled()
        _update_job(job_id, status="verifying", received=received)
        result = verify_downloaded_package(
            part,
            expected_version=str(asset.get("version") or ""),
            expected_sha256=str(asset.get("sha256") or ""),
            expected_bytes=expected,
        )
        if not result.get("ok"):
            raise ValueError("; ".join(result.get("failures") or ["包校验失败"]))
        os.replace(part, target)
        _CANCEL_EVENTS.pop(str(job_id), None)
        _update_job(
            job_id,
            status="done",
            path=str(target),
            filename=target.name,
            received=target.stat().st_size,
            total=target.stat().st_size,
            verification=result,
            failures=[],
        )
    except _Cancelled:
        _cleanup(part)
        _CANCEL_EVENTS.pop(str(job_id), None)
        _update_job(job_id, status="cancelled", failures=[], progress=0)
    except Exception as exc:  # noqa: BLE001
        _cleanup(part)
        _CANCEL_EVENTS.pop(str(job_id), None)
        _update_job(
            job_id,
            status="failed",
            failures=[str(exc)[:500]],
            error=str(exc)[:500],
        )
        logger.info("[update] download failed: %r", exc)


def _cleanup(part: Path) -> None:
    try:
        if part.exists():
            part.unlink()
    except Exception as exc:  # noqa: BLE001
        logger.debug("[update] cleanup failed: %r", exc)


def start_update_download(
    asset_name: str,
    *,
    state_file: Path | None = None,
    download_dir: Path | None = None,
) -> dict[str, Any]:
    """下载一个 release 资产到 Downloads；后台线程 + 轮询进度 + 可取消。

    **只接受检查更新缓存过的 release 资产名**（不信任前端传来的任意 URL）。
    """
    if not _outbound_enabled():
        return {"status": "disabled", "message": "出网已关闭：不发起下载请求"}
    state = _load_state(state_file)
    release = state.get("release") if isinstance(state.get("release"), dict) else None
    if not release:
        return {"status": "error", "code": "no_release", "message": "请先检查更新"}
    parsed = parse_release(release)
    asset = next((a for a in parsed["assets"] if a["name"] == asset_name), None)
    if not asset:
        return {"status": "error", "code": "unknown_asset", "message": "发布中没有这个资产"}
    if asset["kind"] not in ("lite", "full"):
        return {"status": "error", "code": "not_downloadable", "message": "该资产不是安装包"}
    try:
        host = (urllib.parse.urlparse(asset.get("url") or "").hostname or "").lower()
    except Exception:  # noqa: BLE001
        host = ""
    if not host or not any(host == h or host.endswith("." + h) for h in _allowed_download_hosts()):
        return {"status": "error", "code": "bad_url", "message": "资产下载地址不是 GitHub 域名"}

    directory = download_dir or _downloads_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "code": "download_dir", "message": f"下载目录不可用：{exc}"}
    target = _unique_target(directory, asset["name"])
    asset = dict(asset)
    asset["version"] = parsed["latest_version"]
    job_id = uuid.uuid4().hex[:12]
    cancel = threading.Event()
    _remember_cancel(job_id, cancel)
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "starting",
            "asset": asset,
            "target": str(target),
            "received": 0,
            "total": int(asset.get("bytes") or 0),
            "failures": [],
            "updated_at": time.time(),
        }
        _prune_jobs()
    threading.Thread(
        target=_download_worker,
        args=(job_id, asset, target, cancel),
        name=f"memoria-update-{job_id}",
        daemon=True,
    ).start()
    return {"status": "ok", "job_id": job_id, "asset": asset, "path": str(target)}


def _prune_jobs() -> None:
    if len(_JOBS) <= 12:
        return
    old = sorted(_JOBS.values(), key=lambda j: j.get("updated_at") or 0)[: len(_JOBS) - 12]
    for job in old:
        if job.get("status") in ("done", "failed", "cancelled"):
            _JOBS.pop(str(job.get("job_id")), None)


def get_update_download_status(job_id: str) -> dict[str, Any]:
    with _JOBS_LOCK:
        job = _JOBS.get(str(job_id))
        if job is None:
            return {"status": "error", "code": "unknown_job", "message": "未知下载作业"}
        snapshot = json.loads(json.dumps(job))
    received = int(snapshot.get("received") or 0)
    total = int(snapshot.get("total") or 0)
    snapshot["progress"] = round(received / total * 100, 1) if total else 0
    snapshot["received_human"] = human_size(received)
    snapshot["total_human"] = human_size(total)
    return snapshot


def cancel_update_download(job_id: str) -> dict[str, Any]:
    # 作业里没有直接保存 Event（避免序列化）；用再次设置状态的轻量约定：
    with _JOBS_LOCK:
        job = _JOBS.get(str(job_id))
        if job is None:
            return {"status": "error", "code": "unknown_job", "message": "未知下载作业"}
        if job.get("status") in ("done", "failed", "cancelled"):
            return {"status": "ok", "cancelled": False, "job_status": job.get("status")}
        job["cancel_requested"] = True
    # 实际 Event 在 worker 闭包里，通过私有映射触发
    cancel = _CANCEL_EVENTS.pop(str(job_id), None)
    if cancel:
        cancel.set()
    return {"status": "ok", "cancelled": bool(cancel), "job_status": "cancelling"}


_CANCEL_EVENTS: dict[str, threading.Event] = {}


def _remember_cancel(job_id: str, event: threading.Event) -> None:
    _CANCEL_EVENTS[job_id] = event


def open_download_folder() -> dict[str, Any]:
    directory = _downloads_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(directory))  # type: ignore[attr-defined]  # noqa: S606
        else:
            import subprocess
            import sys

            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(directory)], **no_window_kwargs())  # noqa: S603,S607
        return {"status": "ok", "path": str(directory)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": f"打开下载目录失败：{exc}", "path": str(directory)}
