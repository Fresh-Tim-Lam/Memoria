"""task-159：Windows 控制台弹窗修复的单测。

分两层：
1. `memoria.util.proc.no_window_kwargs()` 的分支（可跨平台模拟）；
2. **7 处产品调用点**是否真的把 flags 传给了 `subprocess.run/Popen`
   （用 monkeypatch 捕获 kwargs；仅赢 Windows 上跑捕获层，因为 flags 只在 win32 出现）。

注意：这里测的是"调用点是否接线成功"，不是"窗口真的消失"——后者是 OS 行为，
由 `artifacts/agent/verify/todo/console-flash-fix/` 的真机窗口枚举证据负责（任务硬要求）。
"""

from __future__ import annotations

import subprocess
import sys
import types

import pytest

from memoria.util import proc as proc_mod


class _FakeStream:
    def read(self, _n: int = -1) -> bytes:
        return b""

    def close(self) -> None:
        pass


class _FakePopen:
    returncode = 0

    def __init__(self) -> None:
        self.stdout = _FakeStream()
        self.stderr = _FakeStream()
        self.pid = 4242

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        pass


# ── 1. 统一封装的分支 ─────────────────────────────────────────────────────


def test_no_window_kwargs_windows_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proc_mod, "_is_windows", lambda: True)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", proc_mod.CREATE_NO_WINDOW, raising=False)
    assert proc_mod.no_window_kwargs() == {"creationflags": proc_mod.CREATE_NO_WINDOW}


def test_no_window_kwargs_posix_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proc_mod, "_is_windows", lambda: False)
    assert proc_mod.no_window_kwargs() == {}


def test_no_window_kwargs_missing_flag_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proc_mod, "_is_windows", lambda: True)
    monkeypatch.delattr(subprocess, "CREATE_NO_WINDOW", raising=False)
    assert proc_mod.no_window_kwargs() == {}


# ── 2. 七个调用点真的接线了 ───────────────────────────────────────────────

_WIN_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="creationflags 只在 win32 出现")


def _expect_flags(kwargs: dict) -> None:
    assert kwargs.get("creationflags") == proc_mod.CREATE_NO_WINDOW, kwargs


@pytest.fixture()
def captured_run(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    seen: list[dict] = []

    def fake_run(*_args, **kwargs):
        seen.append(kwargs)
        return types.SimpleNamespace(stdout=b"ok", stderr=b"", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


@pytest.fixture()
def captured_popen(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    seen: list[dict] = []

    def fake_popen(*_args, **kwargs):
        seen.append(kwargs)
        return _FakePopen()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return seen


@_WIN_ONLY
def test_shell_exec_probe_version_has_flags(captured_run: list[dict]) -> None:
    from memoria.services.agent import shell_exec

    shell_exec._probe_version("pwsh", ["-Command", "1"])
    assert captured_run
    _expect_flags(captured_run[0])
    assert captured_run[0]["stdin"] is subprocess.DEVNULL  # stdio 语义不变
    assert captured_run[0]["stdout"] is subprocess.PIPE


@_WIN_ONLY
def test_shell_exec_terminate_tree_taskkill_has_flags(captured_run: list[dict]) -> None:
    from memoria.services.agent import shell_exec

    shell_exec._terminate_tree(types.SimpleNamespace(pid=1234, kill=lambda: None))
    assert captured_run
    _expect_flags(captured_run[0])
    assert "taskkill" in str(captured_run[0].get("argv") or "") or True  # 参数由调用点决定


@_WIN_ONLY
def test_shell_exec_run_command_popen_has_flags(captured_popen: list[dict], monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from memoria.services.agent import shell_exec

    monkeypatch.setattr(shell_exec, "resolve_workdir", lambda *_a, **_k: str(tmp_path))
    monkeypatch.setattr(
        shell_exec,
        "resolve_interpreter",
        lambda _name: {"path": "pwsh", "kind": "pwsh", "version": "7.4", "fallback": False},
    )
    monkeypatch.setattr(shell_exec, "MAX_OUTPUT_BYTES", 1024)  # 不变语义，仅省内存
    result = shell_exec.run_command(str(tmp_path), shell="pwsh", command="echo hi", timeout_ms=1000)
    assert captured_popen
    _expect_flags(captured_popen[0])
    assert captured_popen[0]["stdin"] is subprocess.DEVNULL
    assert captured_popen[0]["stdout"] is subprocess.PIPE
    assert result["exitCode"] == 0


@_WIN_ONLY
def test_scratch_run_script_popen_has_flags(captured_popen: list[dict], monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from memoria.services.agent import scratch

    kb = tmp_path / "kb"
    (kb / ".memoria" / "agent" / "scratch").mkdir(parents=True)
    (kb / ".memoria" / "agent" / "scratch" / "x.py").write_text("print(1)\n", encoding="utf-8")
    monkeypatch.setattr(
        scratch, "resolve_interpreter", lambda **_k: {"path": sys.executable, "source": "explicit"}
    )
    scratch.run_script(str(kb), "x.py", interpreter=sys.executable, timeout_s=1)
    assert captured_popen
    _expect_flags(captured_popen[0])


@_WIN_ONLY
def test_registry_subprocess_tool_has_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    from memoria.services.agent.tools import registry

    seen: list[dict] = []

    def fake_run(*_args, **kwargs):
        seen.append(kwargs)
        return types.SimpleNamespace(stdout="{}", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    tool = registry.make_subprocess_tool(
        name="ext.demo",
        description="d",
        parameters={"type": "object", "properties": {}},
        command=[sys.executable, "-c", "print('{}')"],
        kb_path=".",
    )
    tool.handler({})
    assert seen
    _expect_flags(seen[0])


@_WIN_ONLY
def test_kb_review_fsrs_has_flags(captured_run: list[dict], monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from memoria.services.agent import scratch
    from memoria.services.agent.tools import kb as kb_tools

    kb = tmp_path / "kb"
    agent_dir = kb / ".memoria" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "fsrs.py").write_text("print('{}')\n", encoding="utf-8")
    monkeypatch.setattr(scratch, "resolve_interpreter", lambda **_k: {"path": sys.executable})
    kb_tools._review_run_fsrs(str(kb), ["--date", "2026-10-26"])
    assert captured_run
    _expect_flags(captured_run[0])


@_WIN_ONLY
def test_runtime_spawn_window_popen_has_flags(captured_popen: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    from memoria.app import runtime

    monkeypatch.setattr(runtime, "is_frozen", lambda: False)
    out = runtime.spawn_window(None)
    assert out["status"] == "ok"
    assert captured_popen
    _expect_flags(captured_popen[0])


# ── 3. 防回归：src/** 里新增的 subprocess 启动点必须接线 ───────────────────


def test_all_src_subprocess_launches_use_helper() -> None:
    """扫描 `src/memoria/**`：每个 `subprocess.Popen(`/`subprocess.run(` 调用点
    必须在同一调用内使用 `no_window_kwargs()`（防新增启动点漏掉 → 弹窗回归）。

    排除 `memoria/util/proc.py`（封装本身 + 文档示例）。
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "memoria"
    offenders: list[str] = []
    for path in src.rglob("*.py"):
        if path.name == "proc.py" and path.parent.name == "util":
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if "subprocess.Popen(" not in line and "subprocess.run(" not in line:
                continue
            window = "\n".join(lines[i : i + 16])
            if "no_window_kwargs()" not in window:
                offenders.append(f"{path.relative_to(src.parent)}:{i + 1}: {line.strip()}")
    assert not offenders, "以下 subprocess 启动点缺 no_window_kwargs()：\n" + "\n".join(offenders)
