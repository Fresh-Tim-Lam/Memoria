"""脚本工作区（`services/agent/scratch.py`）的离线单测：**不联网、不触用户库**（临时库 + 临时解释器）。

覆盖四组：

① **路径边界**：绝对路径 / `..` / 盘符 / NUL / 过深一律 `SCRATCH_BAD_PATH`；写删只在
   `<kb>/.memoria/agent/scratch/` 之内；
② **文件面**：列 / 读（截断）/ 写（覆盖、建中间目录）/ 删（文件与目录）；单文件上限与总量上限；
③ **模型面四把工具**：注册进 `KB_TOOL_NAMES`（其后另接执行两把 `pwsh`/`cmd`）、`read_only=True`（免审批的依据见 `kb.py` 块注）、
   参数 schema 收口；这四把工作区工具**自身不执行**（执行改由过审批门的 `pwsh`/`cmd` 承担）；
④ **执行面**（直接测 `scratch.run_script()` 内核）：cwd 锁在工作区、**环境变量白名单**（密钥不进子进程）、
   超时、输出上限、解释器解析三档（显式 / 内置 / 系统）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent import scratch as scratch_mod
from memoria.services.agent.llm.types import ToolCall
from memoria.services.agent.tools import KB_TOOL_NAMES, ToolRegistry, build_kb_tools

SESSION_ID = "session-scratch-0001"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / ".memoria" / "agent").mkdir(parents=True)
    return root


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
    assert KB_TOOL_NAMES[-12:-8] == ("scratch_list", "scratch_read", "scratch_write", "scratch_delete")
    registry = _registry(kb)
    for name in ("scratch_list", "scratch_read", "scratch_write", "scratch_delete"):
        tool = registry.get(name)
        assert tool is not None, name
        assert tool.read_only, f"{name} 声明只读（不改知识库 ⇒ 免审批；依据见 kb.py 块注）"
        assert tool.parameters["additionalProperties"] is False
    assert registry.get("scratch_run") is None, "模型面没有 `scratch_run`（Python 直跑脚本）；执行改由 `pwsh`/`cmd` 承担（过审批门，附录 Z）"


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


# ── ⑤ `review_grade` 硬校验：不存在的 card_id 必须被拒（R2 增补②）─────────────


def test_review_grade_rejects_unknown_card_id(kb: Path) -> None:
    """工具层：card_id 不在 cards.json ⇒ **拒绝评分**（挡"拼错 id ⇒ fsrs.py 静默建幻影卡"）。"""
    import json as _json

    from memoria.app.runtime import resources_dir
    from memoria.services.agent.tools.kb import _review_grade

    agent_dir = kb / ".memoria" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "fsrs.py").write_bytes((resources_dir() / "agent-prompts" / "fsrs.py").read_bytes())
    review_dir = agent_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "cards.json").write_text(
        _json.dumps(
            {"schema_version": 1, "cards": [
                {"card_id": "real1", "kp_id": "", "file": "", "type": "basic", "front": "f", "back": "b", "source": "t"},
            ]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    out = _review_grade(str(kb), None, {"card_id": "NOT_EXIST", "grade": 3})

    assert out.error is True
    assert "不在 cards.json" in out.text
    assert not (review_dir / "progress.json").exists(), "被拒的评分不得建幻影卡 / 写 progress.json"


# ── ⑥ `review_due_list` 直出卡面（R2 增补①）：整个返回即 JSON ──────────────────


def test_review_due_list_returns_json_with_card_faces(kb: Path) -> None:
    """工具层：`review_due_list` **整个返回值就是一段 JSON**（整串可 `json.loads`，不是"文本里夹一段"）。

    顶层 `{date, due, count, filtered_disabled, cards}`；每张卡**直出卡面**（存在的
    `front`/`back`/`type`/`kp_id`/`file`/`source`）+ 调度状态。缺字段**如实缺省**（源没有该键 ⇒
    结果也不加该键，不编造）；`cards.json` 找不到的 id **不静默丢弃**（带 `missing_in_cards: true`）。
    默认滤掉禁卡并计入 `filtered_disabled`；`include_disabled=true` 则禁卡回到 `due` 且计数归 0。
    **只读**：不得写 progress.json / cards.json。
    """
    import json as _json

    from memoria.services.agent.tools.kb import _review_due_list

    agent_dir = kb / ".memoria" / "agent"
    review_dir = agent_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    # 该库 fsrs.py 桩件：只回到期 id（工具侧不判日期）；含一张不在 cards.json 的 ghost、一张禁卡 off1
    (agent_dir / "fsrs.py").write_text(
        "import json\n"
        "print(json.dumps({'status': 'ok', 'date': '2026-01-02', 'due': ['ok1', 'nofront', 'ghost', 'off1'], 'count': 4}))\n",
        encoding="utf-8",
    )
    (review_dir / "cards.json").write_text(
        _json.dumps({"schema_version": 1, "cards": [
            {"card_id": "ok1", "kp_id": "kp1", "file": "a.md", "type": "basic", "front": "F1", "back": "B1", "source": "t"},
            {"card_id": "nofront", "kp_id": "", "file": "", "type": "basic", "back": "B2", "source": "t"},  # 缺 front
            {"card_id": "off1", "kp_id": "kp2", "file": "b.md", "type": "basic", "front": "F3", "back": "B3", "source": "t", "disabled": True},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (review_dir / "progress.json").write_text(
        _json.dumps({"schema_version": 1, "cards": {
            "ok1": {"state": "review", "due": "2026-01-01", "stability": 1.5, "difficulty": 5.0, "reps": 3, "lapses": 1, "last_review": "2025-12-30"},
            "ghost": {"state": "new", "due": "2026-01-02", "reps": 0, "lapses": 0},  # 只在 progress.json
        }}, ensure_ascii=False),
        encoding="utf-8",
    )
    before = {p.name: p.read_bytes() for p in review_dir.iterdir() if p.is_file()}

    out = _review_due_list(str(kb), None, {"date": "2026-01-02"})

    assert out.error is False
    # 整个返回值就是 JSON：整串直接 loads（不是"文本里夹一段 JSON"）
    payload = _json.loads(out.text)
    assert payload["date"] == "2026-01-02"
    # 默认滤掉禁卡：due 里没有 off1，filtered_disabled 记下被滤数
    assert payload["due"] == ["ok1", "nofront", "ghost"] and payload["count"] == 3
    assert payload["filtered_disabled"] == 1
    assert [c["card_id"] for c in payload["cards"]] == ["ok1", "nofront", "ghost"]
    # 卡面齐全（每张含 front/back/type/kp_id/file/source）
    ok1 = payload["cards"][0]
    assert ok1["front"] == "F1" and ok1["back"] == "B1" and ok1["type"] == "basic"
    assert ok1["kp_id"] == "kp1" and ok1["file"] == "a.md" and ok1["source"] == "t"
    # 调度状态齐全（只读自 progress.json）
    assert ok1["due"] == "2026-01-01" and ok1["state"] == "review" and ok1["stability"] == 1.5
    assert ok1["difficulty"] == 5.0 and ok1["reps"] == 3 and ok1["lapses"] == 1 and ok1["last_review"] == "2025-12-30"
    # 缺字段如实缺省：nofront 无 front 键（不编造）、无调度状态 ⇒ 无 state/reps 键
    nofront = payload["cards"][1]
    assert "front" not in nofront
    assert "state" not in nofront and "reps" not in nofront
    # 找不到的 id 如实标记、不丢弃
    ghost = payload["cards"][2]
    assert ghost["card_id"] == "ghost" and ghost["missing_in_cards"] is True and "front" not in ghost

    # include_disabled=true：禁卡回到 due、filtered_disabled 归 0、卡面含 disabled
    all_out = _review_due_list(str(kb), None, {"date": "2026-01-02", "include_disabled": True})
    all_payload = _json.loads(all_out.text)
    assert all_payload["due"] == ["ok1", "nofront", "ghost", "off1"] and all_payload["count"] == 4
    assert all_payload["filtered_disabled"] == 0
    assert [c["card_id"] for c in all_payload["cards"]] == ["ok1", "nofront", "ghost", "off1"]
    assert all_payload["cards"][3]["disabled"] is True

    # 只读：cards.json / progress.json 逐字节未变
    after = {p.name: p.read_bytes() for p in review_dir.iterdir() if p.is_file()}
    assert before == after, "review_due_list 不得写盘"


# ── ⑦ R4：题型扩型（7 种）+ 判分字段（2026-10-11，P0 解阻塞）───────────────────────
# `type` 放开为 7 种；新增可选 `judge`/`options`/`answer`/`accept`/`explain`/`input`；
# `judge` 缺省按规则派生；按类型硬校验（任一张坏 ⇒ 拒绝整批）；同一 `kp_id` 多卡**不设上限**。


def _cards_file(kb: Path) -> Path:
    return kb / ".memoria" / "agent" / "review" / "cards.json"


def test_review_cards_upsert_accepts_seven_types_and_derives_judge(kb: Path) -> None:
    """7 种 type 一次写入全部成功；`judge` 缺省按裁定派生（mcq/gapfill/带 accept 的 cloze ⇒ auto；
    short/produce ⇒ agent；basic/reverse ⇒ self），`input` 缺省仅 short⇒single、produce⇒multi。"""
    cards = [
        {"card_id": "t-basic", "kp_id": "k", "file": "", "type": "basic", "front": "f", "back": "b", "source": "t"},
        {"card_id": "t-cloze", "kp_id": "k", "file": "", "type": "cloze", "front": "{{c1::x}} y", "back": "x y", "source": "t"},
        {"card_id": "t-reverse", "kp_id": "k", "file": "", "type": "reverse", "front": "x", "back": "y", "source": "t"},
        {"card_id": "t-mcq", "kp_id": "k", "file": "", "type": "mcq", "front": "f", "back": "b", "source": "t", "options": ["a", "b"], "answer": "a"},
        {"card_id": "t-gapfill", "kp_id": "k", "file": "", "type": "gapfill", "front": "f", "back": "b", "source": "t", "accept": ["a"]},
        {"card_id": "t-short", "kp_id": "k", "file": "", "type": "short", "front": "f", "back": "b", "source": "t"},
        {"card_id": "t-produce", "kp_id": "k", "file": "", "type": "produce", "front": "f", "back": "b", "source": "t"},
    ]
    out = _invoke(kb, "review_cards_upsert", cards=cards)
    assert out.output.error is False, out.output.text

    rows = {c["card_id"]: c for c in json.loads(_cards_file(kb).read_text(encoding="utf-8"))["cards"]}
    assert set(rows) == {"t-basic", "t-cloze", "t-reverse", "t-mcq", "t-gapfill", "t-short", "t-produce"}
    assert rows["t-mcq"]["judge"] == "auto"
    assert rows["t-gapfill"]["judge"] == "auto"
    assert rows["t-cloze"]["judge"] == "self"  # 无 answer/accept ⇒ 维持自评
    assert rows["t-basic"]["judge"] == "self" and rows["t-reverse"]["judge"] == "self"
    assert rows["t-short"]["judge"] == "agent" and rows["t-short"]["input"] == "single"
    assert rows["t-produce"]["judge"] == "agent" and rows["t-produce"]["input"] == "multi"
    assert "input" not in rows["t-mcq"]  # 非 short/produce 不派生 input


def test_review_cards_upsert_cloze_with_accept_derives_auto(kb: Path) -> None:
    out = _invoke(kb, "review_cards_upsert", cards=[
        {"card_id": "c-accept", "kp_id": "k", "file": "", "type": "cloze", "front": "{{c1::x}} y", "back": "x y", "source": "t", "accept": ["x"]},
    ])
    assert out.output.error is False, out.output.text
    row = json.loads(_cards_file(kb).read_text(encoding="utf-8"))["cards"][0]
    assert row["judge"] == "auto"


@pytest.mark.parametrize(
    "cards",
    [
        [{"card_id": "b1", "kp_id": "", "file": "", "type": "typo", "front": "f", "back": "b", "source": "t"}],
        [{"card_id": "b2", "kp_id": "", "file": "", "type": "mcq", "front": "f", "back": "b", "source": "t", "answer": "x"}],
        [{"card_id": "b3", "kp_id": "", "file": "", "type": "mcq", "front": "f", "back": "b", "source": "t", "options": ["a", "b"], "answer": "z"}],
        [{"card_id": "b4", "kp_id": "", "file": "", "type": "mcq", "front": "f", "back": "b", "source": "t", "options": ["only"], "answer": "only"}],
        [{"card_id": "b5", "kp_id": "", "file": "", "type": "mcq", "front": "f", "back": "b", "source": "t", "options": ["a", "a"], "answer": "a"}],
        [{"card_id": "b6", "kp_id": "", "file": "", "type": "gapfill", "front": "f", "back": "b", "source": "t"}],
        [{"card_id": "b7", "kp_id": "", "file": "", "type": "cloze", "front": "no mark", "back": "b", "source": "t"}],
    ],
)
def test_review_cards_upsert_rejections_are_all_or_nothing(kb: Path, cards: list[dict[str, Any]]) -> None:
    """坏卡（非法 type / mcq 缺 options / answer 不在 options / options <2 / options 重复 /
    gapfill 无 answer 也无 accept / cloze 无挖空标记）⇒ 拒绝整批，**一张都不写**（先写一张好卡再比对哈希）。"""
    good = _invoke(kb, "review_cards_upsert", cards=[
        {"card_id": "good", "kp_id": "", "file": "", "type": "basic", "front": "f", "back": "b", "source": "t"},
    ])
    assert good.output.error is False
    before = _cards_file(kb).read_bytes()
    out = _invoke(kb, "review_cards_upsert", cards=cards)
    assert out.output.error is True and out.output.code == "INVALID_ARGUMENTS"
    assert _cards_file(kb).read_bytes() == before, "拒绝整批 ⇒ cards.json 逐字节不变"


def test_review_cards_upsert_same_kp_many_cards_no_cap(kb: Path) -> None:
    """同一 `kp_id` 连写 5 张 ⇒ 全部成功（`kp_id` 天然支持多卡，**不设数量上限**）。"""
    cards = [{"card_id": f"m-{i}", "kp_id": "samekp", "file": "", "type": "basic", "front": f"f{i}", "back": f"b{i}", "source": "t"} for i in range(5)]
    out = _invoke(kb, "review_cards_upsert", cards=cards)
    assert out.output.error is False, out.output.text
    rows = json.loads(_cards_file(kb).read_text(encoding="utf-8"))["cards"]
    assert len([c for c in rows if c["kp_id"] == "samekp"]) == 5


def test_review_due_list_returns_new_card_fields(kb: Path) -> None:
    """`review_due_list` 把新增字段一并返回（`judge`/`options`/`answer`/`accept`/`explain`/`input`）。"""
    import json as _json

    from memoria.services.agent.tools.kb import _review_due_list

    agent_dir = kb / ".memoria" / "agent"
    review_dir = agent_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "fsrs.py").write_text(
        "import json\nprint(json.dumps({'status': 'ok', 'date': '2026-01-02', 'due': ['m1', 'g1'], 'count': 2}))\n",
        encoding="utf-8",
    )
    (review_dir / "cards.json").write_text(
        _json.dumps({"schema_version": 1, "cards": [
            {"card_id": "m1", "kp_id": "k", "file": "", "type": "mcq", "front": "f", "back": "b", "source": "t",
             "judge": "auto", "options": ["a", "b"], "answer": "a", "explain": "e"},
            {"card_id": "g1", "kp_id": "k", "file": "", "type": "gapfill", "front": "f", "back": "b", "source": "t",
             "judge": "auto", "accept": ["a"], "input": "single"},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    out = _review_due_list(str(kb), None, {"date": "2026-01-02"})
    assert out.error is False
    payload = _json.loads(out.text)
    m1 = payload["cards"][0]
    assert m1["options"] == ["a", "b"] and m1["answer"] == "a" and m1["explain"] == "e" and m1["judge"] == "auto"
    g1 = payload["cards"][1]
    assert g1["accept"] == ["a"] and g1["input"] == "single" and g1["judge"] == "auto"


