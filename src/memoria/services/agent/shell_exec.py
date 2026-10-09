r"""库内命令执行内核（第一期：`pwsh` / `cmd` 两把执行工具的共享实现）。

## 来源与拍板（人 2026-10-06）

设计见 `docs/design/agent-capabilities.md` **附录 Z**（Z.4.1 执行工具、Z.4.5 审批与边界、
Z.10 / Z.11 拍板记录）。上游 `dsh-src/packages/shell/**` 的 `ShellExecRequest → resolve() →
ShellExecSpec` 与 `ShellRunResult{exitCode, signal, timedOut, aborted, stdout, stderr}` 是**语义参照**
（`dsh-src/docs/subsystems/shell.md`），本模块**不移植上游 TS 实现**、**不引内核沙箱**（Z.11 Q4：
沙箱搁置）、**不引新依赖**（只用标准库 `subprocess`）。

## 本期边界（Z.11 拍板，写死在代码里，不是"建议"）

1. **cwd 限库内**：`workdir` 经 `realpath` 前缀校验，必须落在知识库根（含
   `<kb>/.memoria/agent/scratch/`）内；指向库外 ⇒ **拒绝**（`EXEC_CWD_OUTSIDE`），
   **绝不静默夹紧**、**绝不启动进程**；默认 `workdir` = 库根。
2. **超时**：默认 120s（`timeoutMs` 可覆盖，夹到 `[1s, 10min]`）；到点**杀死进程树**并
   返回 `timedOut=true`（**不是错误**，与上游同口径：非零退出/被杀是"结果"）。
3. **输出上限 200 KB**：stdout + stderr **合计** 200 KB，超出截断头部并标 `truncated=true`，
   `bytes` 为**原始总字节数**（继续读取丢弃，不杀进程 ⇒ 命令照常跑完、退出码为真）。
4. **非交互**：`stdin=DEVNULL`（不接输入）、**无 PTY**、**不做后台**、**并发 1**（模块级锁）。
5. **联网允许**（Z.11 Q4b）：不做网络限制；审批卡里显示完整命令（由 `approval_bridge` 的
   参数面呈现，本模块不额外遮蔽）。
6. **审批门在下游**：本模块**只做执行**；`read_only=False` 的两把工具由 `registry.invoke()`
   在**分发前**过审批策略（`approvals`/`approval_bridge`），无应答/拒绝 ⇒ 工具体根本不会被调用
   ⇒ 本模块的 `run_command()` 也就永远不会被触达（fail-closed）。

## 两把 shell 的映射（`cmd` 上游无对应物，本地定义）

- **`pwsh`**：`pwsh.exe -NoLogo -NoProfile -NonInteractive -Command <command>`；
  **解释器回退**（Z.10 工程风险）：`pwsh.exe`（PowerShell 7+）缺失 ⇒ 回退
  `powershell.exe`（Windows PowerShell 5.1），返回里**如实标注实际解释器与版本**
  （`$PSVersionTable.PSVersion`，与系统显示语言无关）。
- **`cmd`**：`cmd.exe /d /s /c "<command>"`。**转义口径（本地定义）**：整条命令作为**单个命令行
  字符串**交给 `CreateProcess`（`Popen(shell=False)` 收字符串 ⇒ 不走 Python 的 `list2cmdline`
  反斜杠转义），`/d` 跳过 AutoRun、`/s` 令 cmd 剥掉 `/c` 后的**首尾一对引号** ⇒ 命令体内自带的
  `"` 保持原样（例：`echo "hi"` 经 `/s` 剥壳后为 `echo "hi"`）。**已知不一致**：命令体内出现
  **未配对引号**或**结尾反斜杠+引号**等病态构造时，cmd 的解析与 PowerShell 方言**天然不同**
  （PowerShell 用 `\` 不转义、cmd 用 `^`）；本模块只保证"把命令**原样**交给解释器"，不替用户做
  shell 级改写。退出码取 `cmd.exe` 本身退出码（`exit /b N` / `exit N` ⇒ `N`）。

纯标准库；只在本模块内做文件系统与子进程动作；不联网（命令自己联网是命令的事）。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import time
from typing import Any

__all__ = [
    "CODE_BAD_REQUEST",
    "CODE_CWD_OUTSIDE",
    "CODE_NO_INTERPRETER",
    "CODE_SPAWN_FAILED",
    "DEFAULT_TIMEOUT_MS",
    "MAX_OUTPUT_BYTES",
    "MAX_TIMEOUT_MS",
    "MIN_TIMEOUT_MS",
    "SHELL_CMD",
    "SHELL_PWSH",
    "SHELLS",
    "ShellExecError",
    "resolve_interpreter",
    "resolve_workdir",
    "run_command",
]

#: 两把 shell（Z.10 Q2：`pwsh` + `cmd` 两个都要）。
SHELL_PWSH = "pwsh"
SHELL_CMD = "cmd"
SHELLS = (SHELL_PWSH, SHELL_CMD)

#: 超时默认与夹取区间（毫秒）。默认 120s（Z.4.1 建议值）。
DEFAULT_TIMEOUT_MS = 120_000
MIN_TIMEOUT_MS = 1_000
MAX_TIMEOUT_MS = 600_000

#: stdout + stderr **合计**输出上限（Z.11 Q3：200 KB）；超出截断头部并继续读取丢弃。
MAX_OUTPUT_BYTES = 200 * 1024

#: 稳定错误码（前端据 code 本地化；不解析 message 文本）。
CODE_BAD_REQUEST = "EXEC_BAD_REQUEST"
CODE_CWD_OUTSIDE = "EXEC_CWD_OUTSIDE"
CODE_NO_INTERPRETER = "EXEC_NO_INTERPRETER"
CODE_SPAWN_FAILED = "EXEC_SPAWN_FAILED"

#: 子进程环境变量白名单（**密钥类一律不传**：白名单是"只给这些"，不是"屏蔽这些"）。
_ENV_ALLOW = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "PSModulePath", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
)

#: 并发 1（Z.11 Q3）：同一进程内只允许一次库内执行。
_EXEC_LOCK = threading.Lock()

#: 解释器版本探测缓存（键 = 可执行文件绝对路径）——探测要起一次进程，故只做一次。
_VERSION_CACHE: dict[str, str] = {}
_VERSION_LOCK = threading.Lock()


class ShellExecError(RuntimeError):
    """库内执行失败（带稳定 code；调用方直接转给工具结果/界面）。"""

    def __init__(self, message: str, code: str = CODE_BAD_REQUEST) -> None:
        super().__init__(message)
        self.code = code


# ── 工作目录（cwd 限库内）────────────────────────────────────────────────────


def resolve_workdir(kb_path: str, workdir: Any = None) -> str:
    """把 `workdir` 归一为**库内绝对目录**；越界/不存在 ⇒ 抛 `ShellExecError`（不夹紧）。

    - 空 ⇒ 库根；相对路径 ⇒ 相对库根解析；绝对路径 ⇒ 原样（但仍须在库内）。
    - 校验：`realpath` 后必须等于库根或在其下（软链逃逸会被 `realpath` 抓出）。
    """
    if not str(kb_path or "").strip():
        raise ShellExecError("请先打开知识库", CODE_BAD_REQUEST)
    root = os.path.abspath(kb_path)
    real_root = os.path.realpath(root)
    raw = str(workdir if workdir is not None else "").strip()
    if not raw:
        candidate = root
    else:
        expanded = os.path.expanduser(raw)
        candidate = expanded if os.path.isabs(expanded) else os.path.join(root, expanded)
    if not os.path.exists(candidate):
        raise ShellExecError(f"workdir 不存在：{raw or root}", CODE_BAD_REQUEST)
    if not os.path.isdir(candidate):
        raise ShellExecError(f"workdir 不是目录：{raw}", CODE_BAD_REQUEST)
    real = os.path.realpath(candidate)
    if real != real_root and not real.startswith(real_root + os.sep):
        raise ShellExecError(f"workdir 必须在知识库内：{raw}", CODE_CWD_OUTSIDE)
    return real


# ── 解释器解析（pwsh → powershell 回退 / cmd）───────────────────────────────


def _child_env() -> dict[str, str]:
    """子进程环境（白名单）；密钥类变量一律不传。"""
    env = {name: os.environ[name] for name in _ENV_ALLOW if name in os.environ}
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _probe_version(exe: str, args: list[str]) -> str:
    """起一次解释器取版本串（失败返回空串，绝不外抛）。"""
    try:
        proc = subprocess.run(  # noqa: S603 —— 只探测本机解释器版本，命令固定
            [exe, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_child_env(),
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    text = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    return text.splitlines()[-1].strip() if text else ""


def _version_of(exe: str) -> str:
    """按 exe 缓存版本（`$PSVersionTable.PSVersion` / `cmd` 的 OS 版本）。"""
    with _VERSION_LOCK:
        cached = _VERSION_CACHE.get(exe)
    if cached is not None:
        return cached
    base = os.path.basename(exe).lower()
    if base.startswith("pwsh") or base.startswith("powershell"):
        version = _probe_version(exe, ["-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"])
    else:  # cmd.exe：取内建 `ver` 的输出（如 "Microsoft Windows [Version 10.0.26100.1]"）
        version = _probe_version(exe, ["/d", "/c", "ver"])
    with _VERSION_LOCK:
        _VERSION_CACHE[exe] = version
    return version


def resolve_interpreter(shell: str) -> dict[str, Any]:
    """`shell` → `{path, kind, version, fallback}`；拿不到解释器 ⇒ `EXEC_NO_INTERPRETER`。

    - `pwsh`：先找 `pwsh`/`pwsh.exe`（PowerShell 7+）；缺失 ⇒ 回退 `powershell`/`powershell.exe`
      （5.1），`fallback=True`（Z.10 工程风险：Windows 自带的是 5.1，未装 PS7 时直接失败不可接受）。
    - `cmd`：取 `%COMSPEC%`（`cmd.exe`），回退 `which("cmd")`。
    """
    name = str(shell or "").strip().lower()
    if name == SHELL_CMD:
        exe = os.environ.get("COMSPEC") or shutil.which("cmd") or ""
        if not exe:
            raise ShellExecError("未找到 cmd.exe（%COMSPEC% 为空且 PATH 里没有 cmd）", CODE_NO_INTERPRETER)
        return {"path": exe, "kind": "cmd", "version": _version_of(exe), "fallback": False}
    if name == SHELL_PWSH:
        for candidate in ("pwsh", "pwsh.exe"):
            found = shutil.which(candidate)
            if found:
                return {"path": found, "kind": "pwsh", "version": _version_of(found), "fallback": False}
        for candidate in ("powershell", "powershell.exe"):
            found = shutil.which(candidate)
            if found:
                return {"path": found, "kind": "powershell", "version": _version_of(found), "fallback": True}
        raise ShellExecError("未找到 PowerShell 解释器（pwsh / powershell 都不在 PATH）", CODE_NO_INTERPRETER)
    raise ShellExecError(f"不支持的 shell：{shell!r}（可选 {SHELLS}）", CODE_BAD_REQUEST)


# ── 执行 ────────────────────────────────────────────────────────────────────


def _clamp_timeout(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MS
    return int(min(MAX_TIMEOUT_MS, max(MIN_TIMEOUT_MS, number)))


def _invocation(shell: str, exe: str, command: str) -> list[str] | str:
    """构造给 `Popen(shell=False)` 的调用：`pwsh` 用 argv 列表，`cmd` 用整条命令行字符串。

    `cmd` 走字符串的原因见模块头「转义口径」：`list2cmdline` 的反斜杠转义不是 cmd 的语法；
    整条字符串直传 `CreateProcess` 才能把命令**原样**交给 cmd.exe。
    """
    if shell == SHELL_PWSH:
        return [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    return f'"{exe}" /d /s /c "{command}"'


class _Budget:
    """stdout+stderr 合一的输出预算（线程安全）：只留头部 `cap` 字节，计数**原始**总量。"""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.lock = threading.Lock()
        self.total = 0

    def take(self, chunk: bytes) -> bytes:
        with self.lock:
            kept = max(0, self.cap - self.total)  # 该 chunk 之前已留的字节 = total（尚未累加本 chunk）
            self.total += len(chunk)
            return chunk[:kept]


def _drain(stream: Any, sink: list[bytes], budget: _Budget) -> None:
    """把管道读干净；超出预算的部分**继续读取但不留存**（命令照常跑完）。"""
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            kept = budget.take(chunk)
            if kept:
                sink.append(kept)
    except (OSError, ValueError):
        return
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _terminate_tree(proc: subprocess.Popen) -> None:
    """杀掉进程**树**：Windows 用 `taskkill /F /T`（连子进程），失败再退回 `proc.kill()`。"""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def run_command(
    kb_path: str,
    *,
    shell: str,
    command: str,
    workdir: Any = None,
    timeout_ms: Any = None,
) -> dict[str, Any]:
    """在库内执行一条 `pwsh` / `cmd` 命令，返回结构化结果（**非零退出/超时都是结果，不抛**）。

    ⚠️ **不是沙箱**：命令以当前用户身份运行、能读写文件与网络（Z.11 Q4 沙箱搁置）。审批门在
    调用方（`registry.invoke()` 于分发前过 `approval_bridge`）—— 本函数**只负责执行**。

    返回 `{shell, command, workdir, interpreter, interpreterKind, interpreterVersion, fallback,
    exitCode, timedOut, durationMs, stdout, stderr, bytes, truncated, digest}`。
    编译期边界（cwd 越界 / 解释器缺失 / 启动失败）抛 `ShellExecError`。
    """
    text = str(command if command is not None else "")
    if not text.strip():
        raise ShellExecError("command 不能为空", CODE_BAD_REQUEST)
    name = str(shell or "").strip().lower()
    if name not in SHELLS:
        raise ShellExecError(f"不支持的 shell：{shell!r}（可选 {SHELLS}）", CODE_BAD_REQUEST)
    cwd = resolve_workdir(kb_path, workdir)
    resolved = resolve_interpreter(name)
    timeout = _clamp_timeout(timeout_ms)
    # 分派用**工具名**（`name`）而非实际解释器 kind：`pwsh` 工具回退到 powershell.exe 时，
    # 仍须走 `-Command` 方言（不能改走 cmd 的 `/d /s /c`）。
    invocation = _invocation(name, resolved["path"], text)
    budget = _Budget(MAX_OUTPUT_BYTES)
    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    started = time.perf_counter()
    with _EXEC_LOCK:  # 并发 1（Z.11 Q3）
        try:
            proc = subprocess.Popen(  # noqa: S603 —— 命令经审批门后方可达此处；审批卡显示完整命令
                invocation,
                shell=False,
                cwd=cwd,
                env=_child_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise ShellExecError(f"启动命令失败：{exc}", CODE_SPAWN_FAILED) from exc
        threads = [
            threading.Thread(target=_drain, args=(proc.stdout, out_chunks, budget), daemon=True),
            threading.Thread(target=_drain, args=(proc.stderr, err_chunks, budget), daemon=True),
        ]
        for thread in threads:
            thread.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout / 1000.0)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        for thread in threads:
            thread.join(timeout=2)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    stdout = b"".join(out_chunks).decode("utf-8", errors="replace")
    stderr = b"".join(err_chunks).decode("utf-8", errors="replace")
    exit_code = int(proc.returncode if proc.returncode is not None else -1)
    return {
        "shell": name,
        "command": text,
        "workdir": cwd,
        "interpreter": resolved["path"],
        "interpreterKind": resolved["kind"],
        "interpreterVersion": resolved["version"],
        "fallback": bool(resolved["fallback"]),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "durationMs": duration_ms,
        "stdout": stdout,
        "stderr": stderr,
        "bytes": int(budget.total),
        "truncated": int(budget.total) > MAX_OUTPUT_BYTES,
        "digest": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
    }
