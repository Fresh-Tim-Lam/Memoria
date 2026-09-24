"""脚本工作区（`services/agent/scratch.py`）的离线单测：**不联网、不触用户库**（临时库 + 临时解释器）。

覆盖四组：

① **路径边界**：绝对路径 / `..` / 盘符 / NUL / 过深一律 `SCRATCH_BAD_PATH`；写删只在
   `<kb>/.memoria/agent/scratch/` 之内；
② **文件面**：列 / 读（截断）/ 写（覆盖、建中间目录）/ 删（文件与目录）；单文件上限与总量上限；
③ **模型面四把工具**：注册进 `KB_TOOL_NAMES` 末四位、`read_only=True`（免审批的依据见 `kb.py` 块注）、
   参数 schema 收口；工具结果里**没有执行能力**（那只能由人点面板的「运行」）；
④ **执行面**（只由 `agent_scratch_run` 触发）：cwd 锁在工作区、**环境变量白名单**（密钥不进子进程）、
   超时、输出上限、审计事件 `scratch/run`、解释器解析三档（显式 / 内置 / 系统）。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent import audit as audit_mod
from memoria.services.agent import scratch as scratch_mod
from memoria.services.agent.llm.types import ToolCall
from memoria.services.agent.tools import KB_TOOL_NAMES, ToolRegistry, build_kb_tools

SESSION_ID = "session-scratch-0001"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / ".memoria" / "agent").mkdir(parents=True)
    return root


@pytest.fixture()
def api(kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UIAPI:
    monkeypatch.setenv("MEMORIA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("MEMORIA_AGENT_CONFIG", raising=False)
    return UIAPI(kb_path=str(kb))


def _registry(kb: Path) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb), session_id=SESSION_ID))


def _invoke(kb: Path, name: str, **arguments: Any) -> Any:
    return _registry(kb).invoke(ToolCall(id="c1", name=name, arguments=json.dumps(arguments)))


def _write_script(kb: Path, rel: str, body: str) -> None:
    scratch_mod.write_text(str(kb), rel, body)


# ── ① 路径边界 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    ["../escape.txt", "a/../../b.txt", "/etc/passwd", "C:/Windows/win.ini", "a\\..\\..\\b", "\x00.txt", "", "   "],
)
def test_paths_cannot_escape_the_workspace(kb: Path, bad: str) -> None:
    with pytest.raises(scratch_mod.ScratchError) as caught:
        scratch_mod.write_text(str(kb), bad, "x")
    assert caught.value.code == scratch_mod.CODE_BAD_PATH


def test_deep_and_long_segments_are_rejected(kb: Path) -> None:
    with pytest.raises(scratch_mod.ScratchError):
        scratch_mod.write_text(str(kb), "/".join(["a"] * 9) + "/f.txt", "x")
    with pytest.raises(scratch_mod.ScratchError):
        scratch_mod.write_text(str(kb), "a" * 81 + ".txt", "x")


def test_everything_lands_under_the_scratch_dir(kb: Path) -> None:
    saved = scratch_mod.write_text(str(kb), "fetch/page.md", "正文")
    root = scratch_mod.scratch_root(str(kb))
    assert saved["path"] == "fetch/page.md" and saved["created"] is True
    assert Path(root, "fetch", "page.md").read_text(encoding="utf-8") == "正文"
    assert scratch_mod.SCRATCH_DIR == ".memoria/agent/scratch"


# ── ② 文件面 ────────────────────────────────────────────────────────────────


def test_write_read_list_delete_round_trip(kb: Path) -> None:
    assert scratch_mod.list_entries(str(kb)) == []
    scratch_mod.write_text(str(kb), "a.py", "print(1)")
    scratch_mod.write_text(str(kb), "fetch/x.json", '{"a":1}')

    entries = scratch_mod.list_entries(str(kb))
    assert [item["path"] for item in entries] == ["a.py", "fetch/x.json"]

    again = scratch_mod.write_text(str(kb), "a.py", "print(2)")
    assert again["created"] is False
    assert scratch_mod.read_text(str(kb), "a.py")["text"] == "print(2)"

    assert scratch_mod.delete_entry(str(kb), "fetch")["kind"] == "dir"
    assert [item["path"] for item in scratch_mod.list_entries(str(kb))] == ["a.py"]

    with pytest.raises(scratch_mod.ScratchError) as caught:
        scratch_mod.read_text(str(kb), "gone.py")
    assert caught.value.code == scratch_mod.CODE_NOT_FOUND


def test_read_truncates_and_write_enforces_limits(kb: Path) -> None:
    long_text = "字" * (scratch_mod.MAX_READ_CHARS + 500)
    scratch_mod.write_text(str(kb), "big.txt", long_text)
    data = scratch_mod.read_text(str(kb), "big.txt")
    assert data["truncated"] is True and len(data["text"]) == scratch_mod.MAX_READ_CHARS

    with pytest.raises(scratch_mod.ScratchError) as caught:
        scratch_mod.write_text(str(kb), "huge.bin", "x" * (scratch_mod.MAX_FILE_BYTES + 1))
    assert caught.value.code == scratch_mod.CODE_BAD_PATH


def test_total_size_quota_is_enforced(kb: Path) -> None:
    fill = "x" * (scratch_mod.MAX_FILE_BYTES // 2)
    needed = scratch_mod.MAX_TOTAL_BYTES // len(fill) + 2
    for index in range(needed):
        try:
            scratch_mod.write_text(str(kb), f"f{index}.bin", fill)
        except scratch_mod.ScratchError as exc:
            assert "总量" in str(exc)
            return
    raise AssertionError("总量上限没有生效")


# ── ③ 模型面四把工具 ────────────────────────────────────────────────────────


def test_scratch_tools_are_registered_read_only_and_closed(kb: Path) -> None:
    assert KB_TOOL_NAMES[-4:] == ("scratch_list", "scratch_read", "scratch_write", "scratch_delete")
    registry = _registry(kb)
    for name in ("scratch_list", "scratch_read", "scratch_write", "scratch_delete"):
        tool = registry.get(name)
        assert tool is not None, name
        assert tool.read_only, f"{name} 声明只读（不改知识库 ⇒ 免审批；依据见 kb.py 块注）"
        assert tool.parameters["additionalProperties"] is False
    assert registry.get("scratch_run") is None, "模型面**没有**执行工具（执行只由人点面板触发）"


def test_tools_write_read_and_report_the_workspace(kb: Path) -> None:
    written = _invoke(kb, "scratch_write", path="fetch/parse.py", text="print('hi')")
    assert not written.is_error and "已新建" in written.content and "面板点「运行」" in written.content

    listed = _invoke(kb, "scratch_list")
    assert not listed.is_error and "fetch/parse.py" in listed.content

    read = _invoke(kb, "scratch_read", path="fetch/parse.py")
    assert not read.is_error and "print('hi')" in read.content

    removed = _invoke(kb, "scratch_delete", path="fetch/parse.py")
    assert not removed.is_error and "已删除" in removed.content


def test_tools_surface_bad_paths_as_tool_errors(kb: Path) -> None:
    result = _invoke(kb, "scratch_write", path="../../evil.py", text="x")
    assert result.is_error and result.output.code == scratch_mod.CODE_BAD_PATH


# ── ④ 执行面（只由人触发）────────────────────────────────────────────────────


def test_interpreter_resolution_order(kb: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 显式路径优先
    assert scratch_mod.resolve_interpreter(explicit=sys.executable)["source"] == "explicit"
    # 显式路径不存在 ⇒ 报错（fail-closed，不静默回落）
    with pytest.raises(scratch_mod.ScratchError) as caught:
        scratch_mod.resolve_interpreter(explicit=str(tmp_path / "nope" / "python.exe"))
    assert caught.value.code == scratch_mod.CODE_NO_INTERPRETER
    # 内置目录（用当前解释器所在目录冒充"发布包内置"）⇒ source=bundled
    fake_bundled = tmp_path / "resources" / "python"
    fake_bundled.mkdir(parents=True)
    (fake_bundled / "python.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(scratch_mod, "bundled_dir", lambda: str(fake_bundled))
    assert scratch_mod.resolve_interpreter()["source"] == "bundled"
    # 关掉内置 ⇒ 回落到系统
    assert scratch_mod.resolve_interpreter(use_bundled=False)["source"] == "system"


def test_run_script_captures_output_and_locks_cwd(kb: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_script(kb, "hi.py", "import os, sys\nprint('cwd=', os.getcwd())\nprint('argv=', sys.argv[1:])\nopen('side.txt','w').write('ok')\n")
    result = scratch_mod.run_script(str(kb), "hi.py", interpreter=sys.executable)

    assert result["exit_code"] == 0 and result["timed_out"] is False
    assert result["source"] == "explicit"
    assert "cwd=" in result["stdout"] and "argv= []" in result["stdout"]
    # cwd 锁在脚本所在目录 ⇒ 相对路径产物落在工作区内
    assert Path(scratch_mod.scratch_root(str(kb)), "side.txt").read_text(encoding="utf-8") == "ok"


def test_run_script_never_leaks_agent_secrets_to_the_child(kb: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEMORIA_AGENT_API_KEY", "sk-must-not-leak")
    monkeypatch.setenv("SOME_RANDOM_SECRET", "also-not")
    _write_script(
        kb,
        "env.py",
        "import os\nprint('key=', os.environ.get('MEMORIA_AGENT_API_KEY', 'missing'))\n"
        "print('secret=', os.environ.get('SOME_RANDOM_SECRET', 'missing'))\n"
        "print('utf8=', os.environ.get('PYTHONUTF8', 'missing'))\n"
        "print('scratch=', bool(os.environ.get('MEMORIA_SCRATCH')))\n",
    )
    result = scratch_mod.run_script(str(kb), "env.py", interpreter=sys.executable)
    assert "key= missing" in result["stdout"] and "secret= missing" in result["stdout"]
    assert "utf8= 1" in result["stdout"] and "scratch= True" in result["stdout"]


def test_run_script_enforces_timeout_and_output_cap(kb: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scratch_mod, "MIN_TIMEOUT_S", 0.2)  # 免等 5 秒：只改本测试里的下界
    _write_script(kb, "sleep.py", "import time\ntime.sleep(5)\nprint('never')\n")
    timed = scratch_mod.run_script(str(kb), "sleep.py", interpreter=sys.executable, timeout_s=0.3)
    assert timed["timed_out"] is True and timed["exit_code"] == -1

    _write_script(kb, "loud.py", "print('x' * 200000)\n")
    loud = scratch_mod.run_script(str(kb), "loud.py", interpreter=sys.executable)
    assert loud["truncated"] is True
    assert len(loud["stdout"]) <= scratch_mod.MAX_RUN_OUTPUT_BYTES


def test_run_script_reports_missing_interpreter(kb: Path) -> None:
    _write_script(kb, "x.py", "print(1)")
    with pytest.raises(scratch_mod.ScratchError) as caught:
        scratch_mod.run_script(str(kb), "x.py", interpreter="definitely-not-a-real-interpreter-xyz")
    assert caught.value.code == scratch_mod.CODE_NO_INTERPRETER


# ── 面板面 RPC ──────────────────────────────────────────────────────────────


def test_status_rpc_reports_files_and_interpreter(api: UIAPI, kb: Path) -> None:
    _write_script(kb, "a.py", "print(1)")
    res = api.agent_scratch_status()
    assert res["status"] == "ok"
    assert res["rel_dir"] == scratch_mod.SCRATCH_DIR
    assert [item["path"] for item in res["files"]] == ["a.py"]
    assert res["total_bytes"] > 0 and res["limits"]["output_bytes"] == scratch_mod.MAX_RUN_OUTPUT_BYTES
    assert res["interpreter"], "本机应有可用解释器（系统 python）"


def test_run_rpc_requires_a_human_click_and_writes_an_audit_event(api: UIAPI, kb: Path) -> None:
    """`agent_scratch_run` 是**唯一**执行入口（模型面没有执行工具）⇒ 顺带钉住审计落盘。"""
    _write_script(kb, "hello.py", "print('hello from scratch')\n")
    res = api.agent_scratch_run("hello.py", session_id=SESSION_ID)

    assert res["status"] == "ok" and res["exit_code"] == 0
    assert "hello from scratch" in res["stdout"]
    assert res["audit"]["status"] == "ok"

    session_file = kb / ".memoria" / "agent" / "sessions" / f"{SESSION_ID}.jsonl"
    events = [json.loads(line) for line in session_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    runs = [event for event in events if event.get("type") == audit_mod.EVENT_SCRATCH_RUN]
    assert len(runs) == 1
    payload = runs[0]["data"]
    assert payload["script"] == "hello.py" and payload["exit_code"] == 0
    assert "hello from scratch" not in json.dumps(payload, ensure_ascii=False), "审计不含 stdout 全文"
    assert os.sep not in payload["script"], "审计里的脚本路径是工作区内相对路径"


def test_panel_rpcs_read_write_delete(api: UIAPI, kb: Path) -> None:
    assert api.agent_scratch_write("note.md", "内容")["status"] == "ok"
    assert api.agent_scratch_read("note.md")["text"] == "内容"
    assert api.agent_scratch_delete("note.md")["status"] == "ok"
    assert api.agent_scratch_status()["files"] == []
    bad = api.agent_scratch_read("../escape.md")
    assert bad["status"] == "error" and bad["code"] == scratch_mod.CODE_BAD_PATH
