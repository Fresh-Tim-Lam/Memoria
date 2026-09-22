# 语义移植自 deepseek-harness packages/fs/fs-observation-policy（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720

"""「读后写」守卫的离线单测（`services/agent/observation.py` + `tools/kb.py` 的写闸）。

上游口径（`fs/fs-observation-policy/README.md`）：观察态是"先验观察记录"（`unseen` / `confirmed absent` /
`present at a version`）；`edit` 未读 ⇒ `FS_NOT_OBSERVED`、读到"不存在" ⇒ `FS_NOT_FOUND`、读后被改 ⇒
`FS_STALE_VERSION`；**读一个不存在的路径 = 确认不存在**（授权之后的 guarded create）；**不跨会话存活**。

覆盖：
① 未读就写 ⇒ `FS_NOT_OBSERVED`，且**一个字节都没写**；
② 先 `read_document` 再写 ⇒ 通过（真实回合的顺序）；
③ 读后被外部改动 ⇒ `FS_STALE_VERSION`（内容级 sha256 比对）；
④ 读到"不存在" ⇒ 之后的 `create_file` 放行（guarded create）；
⑤ 读到"不存在"却用非 create op 去改 ⇒ `FS_NOT_FOUND`；
⑥ `create_file` 本身**不要求**先读（新建路径），**本批自己新建出来的文件**同样不要求（同批给它建点 / 挂链 / 删掉都放行）；
⑦ 观察**不跨会话**：换 `session_id` ⇒ 又是未读；`clear()` 后同会话也须重读；
⑧ `read_kp` 也算一次观察；`write_targets()` 只收非 `create_file` 的目标。
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from memoria.services.agent import observation
from memoria.services.agent.backup import session_dir
from memoria.services.agent.llm import ToolCall
from memoria.services.agent.tools import ToolRegistry, build_kb_tools
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME

A_MD = "# A 文档\n\n第一段。\n\n第二段。\n"

SESSION = "session-20260922T190000Z-obs1"


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _clean_observations(kb: Path):
    """观察表是**进程内**状态：每个用例前后清干净，免得串味。"""
    observation.clear(str(kb))
    yield
    observation.clear(str(kb))


def registry_for(kb: Path, session_id: str | None = SESSION) -> ToolRegistry:
    return ToolRegistry(build_kb_tools(str(kb), session_id=session_id))


def invoke(kb: Path, name: str, session_id: str | None = SESSION, **arguments: Any):
    return registry_for(kb, session_id).invoke(
        ToolCall(id="c1", name=name, arguments=json.dumps(arguments, ensure_ascii=False))
    )


def write(kb: Path, ops: list[dict], session_id: str | None = SESSION):
    return registry_for(kb, session_id).invoke(
        ToolCall(id="c1", name=PROPOSE_TOOL_NAME, arguments=json.dumps({"intent": "测试用", "ops": ops}, ensure_ascii=False))
    )


def body_edit(text: str = "改写后的正文。", expect: str = "第一段。") -> dict:
    return {
        "op": "replace_lines",
        "op_id": "o1",
        "file": "notes/a.md",
        "range": {"start": {"line": 3}, "end": {"line": 3}},
        "expect": expect,
        "text": text,
    }


# ── ① 未读就写 ────────────────────────────────────────────────────────────────


def test_write_without_reading_is_rejected_and_nothing_is_written(kb: Path) -> None:
    before = (kb / "notes" / "a.md").read_bytes()

    result = write(kb, [body_edit()])

    assert result.is_error and result.output.code == observation.CODE_NOT_OBSERVED
    assert "read_document" in result.content, "必须给出可照做的恢复指引"
    assert "notes/a.md" in result.content
    assert (kb / "notes" / "a.md").read_bytes() == before, "拒了就是**一个字节都没写**"
    assert not (kb / ".memoria" / "agent" / "backups").exists(), "连备份都不该建"


# ── ② 先读再写 ────────────────────────────────────────────────────────────────


def test_read_then_write_passes(kb: Path) -> None:
    assert invoke(kb, "read_document", path="notes/a.md").is_error is False

    result = write(kb, [body_edit()])

    assert result.is_error is False, result.content
    assert "改写后的正文。" in (kb / "notes" / "a.md").read_text(encoding="utf-8")


def test_read_kp_also_counts_as_an_observation(kb: Path) -> None:
    """`read_kp` 给的是该文件的正文片段 ⇒ 也算"看过这个文件"（本地口径，见模块头偏差 ③）。"""
    assert invoke(kb, "read_document", path="notes/a.md").is_error is False
    # 建一个 KP 才能用 read_kp 读它
    assert write(kb, [
        {
            "op": "upsert_kp",
            "op_id": "o1",
            "file": "notes/a.md",
            "kp_id": "first",
            "name": "第一段",
            "range": {"start": {"line": 3}, "end": {"line": 3}},
        }
    ]).is_error is False

    observation.clear(str(kb))  # 清掉"读过"的证据，只留 read_kp 这条路
    assert invoke(kb, "read_kp", id="first").is_error is False

    assert write(kb, [body_edit()]).is_error is False, "read_kp 之后应当放行"


# ── ③ 读后被改 ────────────────────────────────────────────────────────────────


def test_write_after_external_change_is_stale(kb: Path) -> None:
    assert invoke(kb, "read_document", path="notes/a.md").is_error is False
    # 外部（人或别的程序）改了内容 ⇒ 我们观察到的那一版已经过期
    (kb / "notes" / "a.md").write_text(A_MD + "\n外部新增的一行。\n", encoding="utf-8")

    result = write(kb, [body_edit()])

    assert result.is_error and result.output.code == observation.CODE_STALE_VERSION
    assert "重新" in result.content and "read_document" in result.content
    assert "外部新增的一行。" in (kb / "notes" / "a.md").read_text(encoding="utf-8")


def test_re_reading_after_a_change_clears_the_stale_state(kb: Path) -> None:
    assert invoke(kb, "read_document", path="notes/a.md").is_error is False
    (kb / "notes" / "a.md").write_text("# A 文档\n\n第一段。\n\n第二段。\n\n第三段。\n", encoding="utf-8")
    assert write(kb, [body_edit()]).is_error is True

    assert invoke(kb, "read_document", path="notes/a.md").is_error is False  # 重读

    assert write(kb, [body_edit()]).is_error is False, "重读之后必须放行"


# ── ④⑤ 读到"不存在" ──────────────────────────────────────────────────────────


def test_reading_a_missing_path_authorizes_a_guarded_create(kb: Path) -> None:
    assert invoke(kb, "read_document", path="notes/new.md").is_error is True  # NOT_FOUND ⇒ 记"确认不存在"

    result = write(kb, [{"op": "create_file", "op_id": "o1", "file": "notes/new.md", "body": "# 新文件\n"}])

    assert result.is_error is False, result.content
    assert (kb / "notes" / "new.md").is_file()


def test_editing_a_path_observed_absent_is_not_found(kb: Path) -> None:
    assert invoke(kb, "read_document", path="notes/new.md").is_error is True

    result = write(kb, [
        {
            "op": "replace_lines",
            "op_id": "o1",
            "file": "notes/new.md",
            "range": {"start": {"line": 1}, "end": {"line": 1}},
            "expect": "x",
            "text": "y",
        }
    ])

    assert result.is_error and result.output.code == observation.CODE_NOT_FOUND
    assert "create_file" in result.content, "要新建就得用 create_file（上游同口径）"


# ── ⑥ create_file 不走闸 ──────────────────────────────────────────────────────


def test_create_file_needs_no_prior_read(kb: Path) -> None:
    result = write(kb, [{"op": "create_file", "op_id": "o1", "file": "notes/fresh.md", "body": "# 全新\n"}])

    assert result.is_error is False, result.content
    assert (kb / "notes" / "fresh.md").is_file()


def test_mixed_batch_requires_reading_only_the_edited_file(kb: Path) -> None:
    """一批里同时有 `create_file` 与改既有文件：**只**要求读过被改的那一个。"""
    result = write(kb, [
        {"op": "create_file", "op_id": "o1", "file": "notes/fresh.md", "body": "# 全新\n"},
        body_edit(),
    ])
    assert result.is_error and result.output.code == observation.CODE_NOT_OBSERVED
    assert not (kb / "notes" / "fresh.md").exists(), "整批 all-or-nothing：被拦就是两个都没写"


def test_writes_to_a_file_created_in_the_same_batch_are_allowed(kb: Path) -> None:
    """**本批自己新建的文件不算"没读过"**（回归钉子）。

    真机报障（2026-09-22）：同批「先 `create_file` → 再给它建点 / 挂链」被闸挡成 `FS_NOT_OBSERVED`，
    而工具说明恰恰**推荐**这么写（"不要拆批"）—— 根因是 `write_targets()` 只跳过了 `create_file`
    那一行，没跳过**它建出来的那个文件** ⇒ 同批后续 op 被当成"没读过就写的既有文件"。
    """
    result = write(kb, [
        {"op": "create_file", "op_id": "o1", "file": "notes/fresh.md", "body": "# 全新\n\n正文一段。\n"},
        {
            "op": "upsert_kp",
            "op_id": "o2",
            "file": "notes/fresh.md",
            "kp_id": "fresh",
            "name": "全新",
            "range": {"start": {"line": 1}, "end": {"line": 3}},
        },
    ])
    assert result.is_error is False, result.content
    assert (kb / "notes" / "fresh.md").is_file()


def test_deleting_a_file_created_in_the_same_batch_is_rejected_by_the_plan_not_the_gate(kb: Path) -> None:
    """同批「先建后删」= **净零**，被**计划校验**（不是观察闸）如实拒成 `file_not_found`。

    分层原因：`delete_file` 的预演（`file_ops.delete_plan()`）读的是**盘上**真实文件，而本批新建的文件
    此刻只在批内视图里（尚未落盘）⇒ 它如实说"不存在"。观察闸**不**为它背锅（`write_targets()` 已把
    本批新建的文件排除，见下一节纯函数用例）。真要"建了再删"分两批即可；而**同批「新建 → 给它建点 /
    挂链」**（真正常用的那种）闸与计划两侧都放行。
    """
    result = write(kb, [
        {"op": "create_file", "op_id": "o1", "file": "notes/tmp.md", "body": "# 临时\n"},
        {"op": "delete_file", "op_id": "o2", "file": "notes/tmp.md"},
    ])

    assert result.is_error and result.output.code == "INVALID_PLAN"
    assert "file_not_found" in result.content
    assert not (kb / "notes" / "tmp.md").exists(), "整批 all-or-nothing：拒了就是净零"


def test_deleting_an_existing_file_still_requires_reading_it(kb: Path) -> None:
    """既有文件的删除**照样要求先读**（放宽的只是"本批自己新建出来的那个"）。"""
    result = write(kb, [{"op": "delete_file", "op_id": "o1", "file": "notes/a.md"}])

    assert result.is_error and result.output.code == observation.CODE_NOT_OBSERVED
    assert (kb / "notes" / "a.md").is_file()


# ── ⑦ 不跨会话 ────────────────────────────────────────────────────────────────


def test_observation_does_not_leak_across_sessions(kb: Path) -> None:
    assert invoke(kb, "read_document", path="notes/a.md").is_error is False

    other = write(kb, [body_edit()], session_id="session-other")

    assert other.is_error and other.output.code == observation.CODE_NOT_OBSERVED, "换会话 ⇒ 等于没读过"
    assert observation.session_owner(None) == observation.AUTO_OWNER, "无会话 id 的调用方也有 owner"


def test_clear_drops_the_observation(kb: Path) -> None:
    assert invoke(kb, "read_document", path="notes/a.md").is_error is False
    observation.clear(str(kb), SESSION)

    assert write(kb, [body_edit()]).is_error is True, "清掉观察 ⇒ 必须重读（模拟 resume 新进程）"


# ── ⑧ 纯函数面 ────────────────────────────────────────────────────────────────


def test_write_targets_skips_create_file_and_dedupes() -> None:
    ops: list[Mapping[str, Any]] = [
        {"op": "create_file", "file": "notes/new.md"},
        {"op": "upsert_kp", "file": "notes/a.md"},
        {"op": "attach_links", "file": "notes/a.md"},
        {"op": "rename_file", "file": "notes/b.md"},
        {"op": "upsert_kp", "file": "notes/new.md"},  # 本批新建的 ⇒ 不算"要读过"
        {"op": "upsert_kp"},  # 没 file ⇒ 忽略
        "not-a-mapping",  # 形状不对 ⇒ 忽略
    ]
    assert observation.write_targets(ops) == ["notes/a.md", "notes/b.md"]


def test_write_targets_ignores_files_created_by_the_same_batch() -> None:
    """批内视图：`create_file` 之后针对**同一个新文件**的 op 不进观察表（真机报障的回归钉子）。"""
    ops: list[Mapping[str, Any]] = [
        {"op": "create_file", "file": "notes/tmp.md"},
        {"op": "delete_file", "file": "notes/tmp.md"},
    ]
    assert observation.write_targets(ops) == []


def test_gate_reports_stale_when_the_file_disappears(kb: Path) -> None:
    """读过、但现在读不到（被删/改名走）⇒ 也按 `FS_STALE_VERSION` 拒（不假装放行）。"""
    observation.record_read(str(kb), SESSION, "notes/a.md", present=True, version="deadbeef")

    verdict = observation.gate_ops(
        str(kb), SESSION, [{"op": "upsert_kp", "file": "notes/a.md"}], current_version=lambda rel: ""
    )

    assert verdict is not None and verdict[0] == observation.CODE_STALE_VERSION


def test_our_own_write_refreshes_the_observation(kb: Path) -> None:
    """**写成功会刷新观察版本**（上游 `fs/observed` 同口径）：不刷新的话模型改完接着改会撞自己造成的 STALE。"""
    assert invoke(kb, "read_document", path="notes/a.md").is_error is False

    first = write(kb, [body_edit("第一次改。")])
    assert first.is_error is False, first.content
    # **不重读**直接再改同一文件：应当放行（观察已被我们自己的写刷新到新版本）；`expect` 按新内容给
    second = write(kb, [body_edit("第二次改。", expect="第一次改。")])
    assert second.is_error is False, second.content
    assert "第二次改。" in (kb / "notes" / "a.md").read_text(encoding="utf-8")
    # 外部改动依然拦得住（刷新的是"我们自己写后的版本"，不是"放行一切"）
    (kb / "notes" / "a.md").write_text("外部把内容换掉了。\n", encoding="utf-8")
    assert write(kb, [body_edit("第三次改。", expect="第二次改。")]).output.code == observation.CODE_STALE_VERSION


def test_two_writes_in_the_same_second_do_not_collide(kb: Path) -> None:
    """连写三批**不撞**批次目录（原先 txid 写死 `-01` ⇒ `WRITE_FAILED (backup_failed)：批次已存在`）。

    断言只看**真正的那个不变量**（三个批次目录互不相同），**不看**"三批落在同一秒"——
    那取决于墙钟（跑满全量套件时这三笔完全可能跨秒，2026-09-22 实测到过一次假失败）。
    """
    assert invoke(kb, "read_document", path="notes/a.md").is_error is False
    first = write(kb, [body_edit("甲。")])
    second = write(kb, [body_edit("乙。", expect="甲。")])
    third = write(kb, [body_edit("丙。", expect="乙。")])

    for result in (first, second, third):
        assert result.is_error is False, result.content
    stamps = sorted(name for name in os.listdir(session_dir(str(kb), SESSION)) if name[:8].isdigit())
    assert len(stamps) == 3, stamps
    assert len(set(stamps)) == 3, f"三批必须是三个不同目录（撞了就会缺一个）：{stamps}"
