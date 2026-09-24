"""脚本工作区（库内 `<kb>/.memoria/agent/scratch/`）：模型写/读/删 + **人在场**才执行。

## 为什么有它（人 2026-09-24 拍板）

人：「web 搜索能力……涉及脚本，所以 agent 需要一个内置的临时脚本区给他工作，这样才是完整的联网
搜索能力」。联网工作（抓多页 → 抽表 → 聚合成报告）靠"模型读一遍正文"做不完整，需要**中间产物与脚本**
有个固定的家。人同时拍板了两件事（`AskUserQuestion` 三问）：

1. **能力面 = B**：agent 写脚本，**但执行必须由人在面板点「运行」**（不给模型任何执行工具）；
2. **落点 = 库内 `.memoria/agent/scratch/`**；
3. **解释器**：可在设置里显式指定 → 为空则在系统路径里找 → 也可切换**发布包内置**的那一份。

⇒ 这一条**突破了**原设计红线（`docs/design/agent-capabilities.md` 的「❌ 不做任意脚本/命令执行」）：
本模块与 `docs/design/agent-capabilities.md §3.4` 一起把"人点才跑"这一档写进规范；**"模型自动执行"
仍然不做**（那是 C 档，人没选）。

## 三条边界（写死在代码里，不是"建议"）

1. **写面限于工作区**：所有写/删路径过 `safe_rel()` + `realpath` 前缀校验 ⇒ 逃不出
   `<kb>/.memoria/agent/scratch/`（越界一律 `SCRATCH_BAD_PATH`，不静默截断）；
2. **执行不是沙箱**：脚本以**当前用户身份**跑、能读写整个文件系统与网络。因此
   - 只有 `ui.py` 的 RPC（人在面板点）能触发执行，**模型面没有执行工具**；
   - 子进程环境变量走**白名单**（`_child_env()`）：`MEMORIA_AGENT_API_KEY` 等一律不传 ⇒ 脚本
     读不到用户密钥；`cwd` 锁在脚本所在目录；
   - 超时（默认 60s）+ stdout/stderr 各 64 KiB 上限（超限即杀进程）。
3. **工作区是应用管理目录**（同 `.memoria/agent/attachments/` 的先例）：模型写入**不走** M3 的
   plan/审批管线，也不进 `pending.json`（避免被 `sync_kb_pending` 全量重算清掉）。

## 与既有模块的分工

- `tools/kb.py`：模型面四把工具（`scratch_list` / `scratch_read` / `scratch_write` / `scratch_delete`）；
- `ui.py`：面板面 RPC（列 / 读 / 删 / **运行** / 探解释器）；
- `audit.py`：每次执行落一条 `scratch/run`（**不含 stdout 全文**，只记脚本名/解释器/退出码/耗时/字节数）。

纯标准库、只在本模块内做文件系统与子进程动作；不联网（脚本自己联网是脚本的事）。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "BUNDLED_DIR_NAME",
    "CODE_BAD_PATH",
    "CODE_NO_INTERPRETER",
    "CODE_NOT_FOUND",
    "CODE_RUN_FAILED",
    "CODE_TIMEOUT",
    "DEFAULT_TIMEOUT_S",
    "MAX_FILES",
    "MAX_FILE_BYTES",
    "MAX_READ_CHARS",
    "MAX_RUN_OUTPUT_BYTES",
    "MAX_TOTAL_BYTES",
    "MAX_TIMEOUT_S",
    "MIN_TIMEOUT_S",
    "SCRATCH_DIR",
    "ScratchError",
    "bundled_dir",
    "delete_entry",
    "list_entries",
    "read_text",
    "resolve_interpreter",
    "run_status",
    "run_script",
    "scratch_root",
    "write_text",
]

#: 工作区在库内的相对路径（应用管理目录；随库走，换库不串）。
SCRATCH_DIR = ".memoria/agent/scratch"
#: 发布包内置解释器相对 `resources/` 的目录名（打包片落地前它不存在 ⇒ 自动回落到系统解释器）。
BUNDLED_DIR_NAME = "python"

#: 单文件写入上限（工具面口径；脚本自身写的东西不走这里）。
MAX_FILE_BYTES = 1024 * 1024
#: 工作区文件数上限与总量上限（防止脚本把库撑爆）。
MAX_FILES = 200
MAX_TOTAL_BYTES = 20 * 1024 * 1024
#: `read_text()` 回给模型/面板的字符上限（与 `read_document` 的预算同档）。
MAX_READ_CHARS = 20_000
#: 单次执行捕获的 stdout / stderr 各自上限（超限即杀进程）。
MAX_RUN_OUTPUT_BYTES = 64 * 1024
#: 执行默认与允许的超时（秒）。
DEFAULT_TIMEOUT_S = 60
MIN_TIMEOUT_S = 5
MAX_TIMEOUT_S = 300

#: 稳定错误码（前端据 code 本地化；不解析 message 文本）。
CODE_BAD_PATH = "SCRATCH_BAD_PATH"
CODE_NOT_FOUND = "SCRATCH_NOT_FOUND"
CODE_NO_INTERPRETER = "SCRATCH_NO_INTERPRETER"
CODE_TIMEOUT = "SCRATCH_TIMEOUT"
CODE_RUN_FAILED = "SCRATCH_RUN_FAILED"

#: 子进程环境变量白名单（**密钥类一律不传**：白名单是"只给这些"，不是"屏蔽这些"）。
_ENV_ALLOW = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "LANG", "LC_ALL", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
)


class ScratchError(RuntimeError):
    """工作区操作失败（带稳定 code；调用方直接转给界面/工具结果）。"""

    def __init__(self, message: str, code: str = CODE_RUN_FAILED) -> None:
        super().__init__(message)
        self.code = code


# ── 路径 ────────────────────────────────────────────────────────────────────


def scratch_root(kb_path: str) -> str:
    """工作区根目录（不存在则建）。`kb_path` 为空 ⇒ 抛 `ScratchError`（调用方先过「请先打开知识库」）。"""
    if not str(kb_path or "").strip():
        raise ScratchError("请先打开知识库", CODE_BAD_PATH)
    root = os.path.join(os.path.abspath(kb_path), *SCRATCH_DIR.split("/"))
    os.makedirs(root, exist_ok=True)
    return root


def _safe_rel(rel: Any) -> str:
    """相对路径归一：拒**绝对路径**（`/x`、`\\x`、`C:x`）、拒 `..`、拒空 / NUL；只留工作区内相对路径。

    注意顺序：**先判绝对性再剥分隔符** —— 反过来会把 `/etc/passwd` 悄悄变成 `etc/passwd` 写进工作区，
    看着像"写成功了"，实际写的不是模型/人以为的那个地方（测试当场抓到过一次）。
    """
    text = str(rel if rel is not None else "").strip().replace("\\", "/")
    if not text or "\x00" in text:
        raise ScratchError("路径不能为空", CODE_BAD_PATH)
    if text.startswith("/") or ":" in text.split("/")[0]:
        raise ScratchError(f"只能用工作区内的相对路径：{rel}", CODE_BAD_PATH)
    text = text.strip("/")
    if not text:
        raise ScratchError("路径不能为空", CODE_BAD_PATH)
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ScratchError(f"路径不许跳出工作区：{rel}", CODE_BAD_PATH)
    if len(parts) > 8 or any(len(part) > 80 for part in parts):
        raise ScratchError("路径太深或某一段过长", CODE_BAD_PATH)
    return "/".join(parts)


def _resolve(kb_path: str, rel: Any, *, must_exist: bool = False) -> tuple[str, str]:
    """`safe_rel` + `realpath` 前缀双校验 ⇒ 返回（归一相对路径, 绝对路径）。

    新建路径（目录还不存在）时校验**最近存在的祖先**仍在工作区内 —— 这样 `a/b/c.txt` 在 `a/`
    都还没有时也能安全判通过，而软链接指向库外时会被 `realpath` 抓出来。
    """
    clean = _safe_rel(rel)
    root = scratch_root(kb_path)
    path = os.path.join(root, *clean.split("/"))
    real_root = os.path.realpath(root)
    ancestor = path if os.path.exists(path) else os.path.dirname(path)
    while ancestor and not os.path.exists(ancestor):
        parent = os.path.dirname(ancestor)
        if parent == ancestor:
            break
        ancestor = parent
    probe = os.path.realpath(ancestor or root)
    if probe != real_root and not probe.startswith(real_root + os.sep):
        raise ScratchError(f"路径跳出了工作区：{rel}", CODE_BAD_PATH)
    if must_exist and not os.path.exists(path):
        raise ScratchError(f"工作区里没有这个文件：{clean}", CODE_NOT_FOUND)
    return clean, path


# ── 文件操作（模型面四把工具的内部实现）────────────────────────────────────


def list_entries(kb_path: str) -> list[dict[str, Any]]:
    """列出工作区全部文件（相对路径 / 字节数 / 修改时间）；按相对路径排序。"""
    root = scratch_root(kb_path)
    out: list[dict[str, Any]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, root).replace("\\", "/")
            out.append({"path": rel, "size": int(stat.st_size), "mtime": int(stat.st_mtime)})
    out.sort(key=lambda item: item["path"])
    return out


def read_text(kb_path: str, rel: Any) -> dict[str, Any]:
    """读工作区文本文件（UTF-8 有损兜底、按字符上限截断）。"""
    clean, path = _resolve(kb_path, rel, must_exist=True)
    if os.path.isdir(path):
        raise ScratchError(f"{clean} 是目录，不能当文件读", CODE_BAD_PATH)
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        raw = handle.read(min(size, MAX_READ_CHARS * 4) + 1)
    text = raw.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return {
        "path": clean,
        "size": int(size),
        "text": text[:MAX_READ_CHARS],
        "truncated": bool(size > len(text.encode("utf-8", errors="replace")) or len(text) > MAX_READ_CHARS),
    }


def _check_quota(kb_path: str, *, extra_bytes: int, replacing: str) -> None:
    entries = list_entries(kb_path)
    total = sum(int(item["size"]) for item in entries)
    if replacing:
        total -= sum(int(item["size"]) for item in entries if item["path"] == replacing)
    count = len([item for item in entries if item["path"] != replacing])
    if count + 1 > MAX_FILES:
        raise ScratchError(f"工作区文件数已达上限（{MAX_FILES}）⇒ 请先删掉一些", CODE_BAD_PATH)
    if total + extra_bytes > MAX_TOTAL_BYTES:
        raise ScratchError(
            f"工作区总量将超过上限（{MAX_TOTAL_BYTES // (1024 * 1024)} MiB）⇒ 请先删掉一些", CODE_BAD_PATH
        )


def write_text(kb_path: str, rel: Any, text: Any) -> dict[str, Any]:
    """写工作区文本文件（自动建中间目录；覆盖同路径）。返回 `{path,size,created}`。"""
    clean, path = _resolve(kb_path, rel)
    body = str(text if text is not None else "")
    data = body.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ScratchError(f"单文件上限 {MAX_FILE_BYTES // 1024} KiB，这次要写 {len(data) // 1024} KiB", CODE_BAD_PATH)
    created = not os.path.exists(path)
    _check_quota(kb_path, extra_bytes=len(data), replacing=clean)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return {"path": clean, "size": len(data), "created": created}


def delete_entry(kb_path: str, rel: Any) -> dict[str, Any]:
    """删工作区里的文件或目录（目录递归；不存在 ⇒ `SCRATCH_NOT_FOUND`）。"""
    clean, path = _resolve(kb_path, rel, must_exist=True)
    if os.path.isdir(path):
        shutil.rmtree(path)
        return {"path": clean, "kind": "dir"}
    os.remove(path)
    return {"path": clean, "kind": "file"}


# ── 解释器解析 ──────────────────────────────────────────────────────────────


def bundled_dir() -> str | None:
    """发布包内置解释器目录（`resources/python/`）；不存在 ⇒ `None`。

    源码态（开发）没有它 ⇒ 自动回落到系统解释器；打包片落地后由 `packaging/build.py` 登记。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "..", "resources", BUNDLED_DIR_NAME),  # src/memoria/services/agent → 仓库根
        os.path.join(os.path.dirname(sys.executable), "resources", BUNDLED_DIR_NAME),
    ]
    for candidate in candidates:
        exe = _exe_in(candidate)
        if exe:
            return os.path.normpath(candidate)
    return None


def _exe_in(folder: str) -> str | None:
    """目录里的解释器可执行文件（Windows 优先 `python.exe`）。"""
    if not folder or not os.path.isdir(folder):
        return None
    for name in ("python.exe", "python3.exe", "python"):
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def resolve_interpreter(*, explicit: str = "", use_bundled: bool = True) -> dict[str, str]:
    """解释器解析：**显式路径 > 内置（开关开且存在）> 系统 PATH / 当前解释器**。

    返回 `{path, source}`（`source ∈ explicit | bundled | system`）；都拿不到 ⇒ 空 path
    （`source="none"`，调用方据此禁用「运行」按钮）。
    """
    chosen = str(explicit or "").strip().strip('"')
    if chosen:
        if os.path.isfile(chosen):
            return {"path": chosen, "source": "explicit"}
        found = shutil.which(chosen)
        if found:
            return {"path": found, "source": "explicit"}
        raise ScratchError(f"设置里的解释器路径不存在：{chosen}", CODE_NO_INTERPRETER)
    if use_bundled:
        folder = bundled_dir()
        exe = _exe_in(folder or "")
        if exe:
            return {"path": exe, "source": "bundled"}
    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if found:
            return {"path": found, "source": "system"}
    if os.path.basename(sys.executable).lower().startswith("python"):
        return {"path": sys.executable, "source": "system"}
    return {"path": "", "source": "none"}


# ── 执行（**只能由人触发**：`ui.py::agent_scratch_run`）─────────────────────


def _child_env(root: str) -> dict[str, str]:
    """子进程环境（白名单 + UTF-8 + 工作区变量）——**密钥类变量一律不传**。"""
    env = {name: os.environ[name] for name in _ENV_ALLOW if name in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["MEMORIA_SCRATCH"] = root
    return env


def _drain(stream: Any, sink: list[bytes], cap: int, killer: Any) -> None:
    """把管道读到 `cap` 为止（超限置位并杀进程，避免"无限打印"把内存吃光）。"""
    total = 0
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            if total < cap:
                sink.append(chunk[: cap - total])
            total += len(chunk)
            if total > cap:
                killer()
    except (OSError, ValueError):
        return
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _clamp_timeout(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(DEFAULT_TIMEOUT_S)
    return float(min(MAX_TIMEOUT_S, max(MIN_TIMEOUT_S, number)))


def run_script(
    kb_path: str,
    rel: Any,
    *,
    interpreter: str = "",
    use_bundled: bool = True,
    timeout_s: Any = DEFAULT_TIMEOUT_S,
    arguments: Sequence[str] | None = None,
) -> dict[str, Any]:
    """在工作区里执行一个脚本：**不是沙箱**（见模块头 2），只做超时 + 输出上限 + 环境白名单。

    返回 `{path, interpreter, source, exit_code, stdout, stderr, timed_out, truncated, duration_ms}`；
    超时 ⇒ `exit_code=-1` + `timed_out=True`（不抛，让界面照常显示已捕获的输出）。
    """
    clean, path = _resolve(kb_path, rel, must_exist=True)
    if os.path.isdir(path):
        raise ScratchError(f"{clean} 是目录，不能执行", CODE_BAD_PATH)
    resolved = resolve_interpreter(explicit=interpreter, use_bundled=use_bundled)
    if not resolved["path"]:
        raise ScratchError("没有可用的脚本解释器：请在设置里指定路径，或安装 Python / 打包内置解释器", CODE_NO_INTERPRETER)
    timeout = _clamp_timeout(timeout_s)
    cmd = [resolved["path"], path] + [str(arg) for arg in (arguments or ())][:16]
    started = time.perf_counter()
    try:
        proc = subprocess.Popen(  # noqa: S603 —— 命令由**人**在面板上显式触发（模型没有执行工具）
            cmd,
            cwd=os.path.dirname(path),
            env=_child_env(scratch_root(kb_path)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ScratchError(f"启动脚本失败：{exc}", CODE_RUN_FAILED) from exc

    def _kill() -> None:
        try:
            proc.kill()
        except OSError:
            pass

    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    threads = [
        threading.Thread(target=_drain, args=(proc.stdout, out_chunks, MAX_RUN_OUTPUT_BYTES, _kill), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, err_chunks, MAX_RUN_OUTPUT_BYTES, _kill), daemon=True),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    for thread in threads:
        thread.join(timeout=2)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    stdout = b"".join(out_chunks).decode("utf-8", errors="replace")
    stderr = b"".join(err_chunks).decode("utf-8", errors="replace")
    return {
        "path": clean,
        "interpreter": resolved["path"],
        "source": resolved["source"],
        "exit_code": -1 if timed_out else int(proc.returncode if proc.returncode is not None else -1),
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "truncated": len(stdout.encode("utf-8")) >= MAX_RUN_OUTPUT_BYTES or len(stderr.encode("utf-8")) >= MAX_RUN_OUTPUT_BYTES,
        "duration_ms": duration_ms,
        "timeout_s": timeout,
        "digest": _file_digest(path),
    }


def _file_digest(path: str) -> str:
    """脚本内容指纹（审计里用它核对"跑的哪一版"；读不到 ⇒ 空串）。"""
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read(256 * 1024)).hexdigest()[:16]
    except OSError:
        return ""


def run_status(kb_path: str, *, interpreter: str = "", use_bundled: bool = True) -> dict[str, Any]:
    """面板初始化用：工作区是否就绪 + 解释器解析结果（不执行任何东西）。"""
    root = scratch_root(kb_path)
    try:
        resolved = resolve_interpreter(explicit=interpreter, use_bundled=use_bundled)
        error = ""
    except ScratchError as exc:
        resolved, error = {"path": "", "source": "none"}, str(exc)
    entries = list_entries(kb_path)
    return {
        "root": root,
        "rel_dir": SCRATCH_DIR,
        "files": entries,
        "total_bytes": sum(int(item["size"]) for item in entries),
        "max_files": MAX_FILES,
        "max_total_bytes": MAX_TOTAL_BYTES,
        "interpreter": resolved["path"],
        "source": resolved["source"],
        "bundled_dir": bundled_dir() or "",
        "timeout_s": DEFAULT_TIMEOUT_S,
        "error": error,
        "limits": {
            "file_bytes": MAX_FILE_BYTES,
            "output_bytes": MAX_RUN_OUTPUT_BYTES,
            "read_chars": MAX_READ_CHARS,
            "min_timeout_s": MIN_TIMEOUT_S,
            "max_timeout_s": MAX_TIMEOUT_S,
        },
    }
