# 语义移植自 deepseek-harness packages/interaction/permission-presets 与
# packages/interaction/user-approval（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720

"""审批档位（会话级三档）+ 逐条确认的离线单测：不联网、不写知识库正文。

覆盖（对应任务验收项）：
① 旋钮折叠：`permission/preset` / `approval/policy` 各取**最后一条**覆盖，词汇外取值忽略；
② 生效值 `derive()`：单旋钮反查档位名，无匹配 ⇒ 派生态 `custom`；
③ 切换 `set_preset()`：先落用户意图、再落变化的旋钮；已是生效档 ⇒ **零事件**（幂等）；
   `custom` 与未知名**不可作切换目标**；
④ 钉盘 `pin_and_current()`：缺事实才补，第二次调用零事件；
⑤ 按 agent 的默认档：读 `config/agent.json: permission.<agent>`，未知名回落 `DEFAULT_PRESET`；
⑥ 三档策略：`manual` ⇒ `AskPolicy`、`auto` ⇒ `GuardedPolicy`、`all-access` ⇒ 全放行；
⑦ 风险判据：破坏性 op / 形状不认识 ⇒ 要问；常规写入 ⇒ 免问；
⑧ 逐条确认桥：未挂载即无应答者、回填裁决唤醒等待线程、超时 ⇒ `unavailable`、取消 ⇒ `cancelled`；
⑨ 轮询载荷新增 `pending_approvals`（只增不改）；
⑩ 四个 RPC：读档位面、切会话档、改默认档、回填裁决（含各自的拒法）；
⑪ 前端接线不变量（JS/HTML/语言包字符串）与 i18n 键成对。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent import approval_bridge, permission_presets as pp
from memoria.services.agent.approvals import (
    ALLOWED_ONCE,
    DEFAULT_POLICY,
    ApprovalOutcome,
    ApprovalRequest,
    AskPolicy,
    DefaultApprovalPolicy,
    GuardedPolicy,
    write_is_risky,
)
from memoria.services.agent.ask import ask
from memoria.services.agent.ask_stream import AskJob
from memoria.services.agent.llm.config import ConfigError, permission_presets_map, save_config
from memoria.services.agent.llm.types import FinishEvent, FinishReason, TextDelta, ToolCall
from memoria.services.agent.session.store import SessionStore, read_session, session_file


class _ScriptedRenameProvider:
    """只演两幕的假 provider：① 发一次 `rename_file` 的 `propose_write`（**风险写** ⇒ 会过审批闸）；② 收尾。

    没有工具 schema 的调用（标题 / 压缩）回纯文本，避免辅助调用也被脚本化。
    """

    name = "scripted"

    def __init__(self) -> None:
        self.requests: list[object] = []

    def stream(self, request):
        self.requests.append(request)
        if not tuple(getattr(request, "tools", ()) or ()):
            yield TextDelta("辅助调用")
            yield FinishEvent(FinishReason.STOP)
            return
        roles = [str(getattr(getattr(m, "role", ""), "value", getattr(m, "role", "")) or "") for m in request.messages]
        if "tool" in roles:
            yield TextDelta("已按你的确认处理完这一批。")
            yield FinishEvent(FinishReason.STOP)
            return
        yield TextDelta("我准备给演示文件改名。")
        yield FinishEvent(
            FinishReason.TOOL_CALLS,
            tool_calls=(
                ToolCall(
                    id="call-1",
                    name="propose_write",
                    arguments='{"intent": "改名", "ops": [{"op": "rename_file", "op_id": "o1", "file": "notes/a.md", "new_name": "b.md"}]}',
                ),
            ),
        )

A_MD = "# A 文档\n\n注意力机制是核心。\n\n末尾一行。\n"
SESSION = "session-20260922T180000Z-perm1"

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "src" / "memoria" / "ui" / "static" / "app"
_PANEL_JS = _APP / "js" / "agent-panel.js"
_INDEX_HTML = _APP / "index.html"
_LOCALES = [_APP / "i18n" / "zh-CN.js", _APP / "i18n" / "en.js"]

#: 本模块新增的全部 i18n 键（中英必须成对；缺一个界面就会漏出裸 key）
_PERMISSION_KEYS = (
    "permission.sessionTitle",
    "permission.needSession",
    "permission.failed",
    "permission.switched",
    "permission.defaultSaved",
    "permission.manual.name",
    "permission.manual.desc",
    "permission.auto.name",
    "permission.auto.desc",
    "permission.all.name",
    "permission.all.desc",
    "permission.custom.name",
    "permission.custom.desc",
    "approve.title",
    "approve.ops",
    "approve.noIntent",
    "approve.allow",
    "approve.deny",
    "approve.sending",
    "approve.done",
    "approve.allowed",
    "approve.denied",
    "approve.failed",
    "settings.permissionLabel",
)


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8")
    return root


@pytest.fixture()
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 `config/agent.json` 指到临时目录（默认档测试不改仓库里的真配置）。"""
    path = tmp_path / "agent.json"
    monkeypatch.setenv("MEMORIA_AGENT_CONFIG", str(path))
    return path


@pytest.fixture()
def api(kb: Path) -> UIAPI:
    return UIAPI(kb_path=str(kb))


def _preset_event(name: str) -> dict:
    return {"type": pp.EVENT_PRESET, "data": {"preset": name}}


def _policy_event(value: str) -> dict:
    return {"type": pp.EVENT_APPROVAL_POLICY, "data": {"policy": value}}


def _request(tool: str = "propose_write", **kwargs) -> ApprovalRequest:
    """一次**写类**调用（本模块的被测对象几乎全是写路径 ⇒ `read_only` 默认 False）。"""
    arguments = kwargs.pop("arguments", {"intent": "精简一节", "ops": [{"op": "upsert_kp"}]})
    kwargs.setdefault("read_only", False)
    return ApprovalRequest(tool=tool, call_id=kwargs.pop("call_id", "c1"), arguments=arguments, **kwargs)


# ── ① 折叠 ─────────────────────────────────────────────────────────────────────


def test_fold_takes_the_last_override_per_knob_and_ignores_junk() -> None:
    events = [
        _preset_event("manual-approval"),
        _policy_event("ask"),
        _preset_event("all-access"),
        _policy_event("allow-all"),
        # 词汇外取值 / 派生态 / 空值 / 形状不对：一律忽略，绝不覆盖已知取值
        _preset_event("custom"),
        _policy_event("yolo"),
        _preset_event(""),
        {"type": pp.EVENT_PRESET, "data": "not-a-mapping"},
        "not-a-record",
    ]
    state = pp.fold(events)
    assert (state.preset, state.approval) == ("all-access", "allow-all")


def test_fold_of_empty_stream_is_all_none() -> None:
    assert pp.fold([]) == pp.KnobState(None, None)


def test_legacy_never_is_read_as_allow_all() -> None:
    """**只读兼容**：旧会话事件里的 `never` 读成 `allow-all`（人 2026-09-22：「改 never 命名避歧义」）。

    改名理由：本地这一档是「不询问 ⇒ 一律放行」，而上游 `never` 恰好相反（「不询问 ⇒ 需审批者一律拒绝」），
    同名反义会误导读上游文档的人。会话日志是 append-only 的事实源 ⇒ 旧值**照原样读**、不改写。
    """
    state = pp.fold([_preset_event("all-access"), _policy_event("never")])
    assert state.approval == "allow-all"
    assert pp.derive(state) == "all-access"
    assert "never" not in pp.APPROVAL_POLICIES and pp.LEGACY_APPROVAL_POLICIES["never"] == "allow-all"
    assert pp.policy_value("all-access") == "allow-all"


# ── ② 生效值 ───────────────────────────────────────────────────────────────────


def test_derive_reverse_looks_up_the_knob_and_returns_custom_when_unmatched() -> None:
    assert pp.derive(pp.KnobState(None, None)) == pp.DEFAULT_PRESET  # 无覆盖 ⇒ 默认档
    assert pp.derive(pp.KnobState(None, "ask")) == "manual-approval"
    assert pp.derive(pp.KnobState(None, "allow-all")) == "all-access"
    # 上次选择与旋钮一致 ⇒ 用上次选择（上游 `derive()` 的先认上次选择）
    assert pp.derive(pp.KnobState("auto-approval", "auto")) == "auto-approval"
    # 旋钮在词汇内但表里没有对应档（档位表被改小）⇒ 派生态
    assert pp.derive(pp.KnobState(None, "auto"), "manual-approval") == "auto-approval"
    assert pp.derive(pp.KnobState("all-access", "auto"), "manual-approval") == "auto-approval"


def test_catalog_lists_three_selectable_tiers_plus_derived_custom() -> None:
    values = [row["value"] for row in pp.catalog()]
    assert values == ["manual-approval", "auto-approval", "all-access", pp.CUSTOM_PRESET]
    assert pp.PRESET_NAMES == ("manual-approval", "auto-approval", "all-access")
    assert pp.DEFAULT_PRESET == "auto-approval"
    assert pp.policy_value(pp.DEFAULT_PRESET) == "auto"


# ── ③ 切换 ─────────────────────────────────────────────────────────────────────


def test_set_preset_appends_intent_then_changed_knob_only_once(kb: Path, config_file: Path) -> None:
    session = SessionStore(str(kb), SESSION)
    pp.set_preset(session, "manual-approval")
    rows = [row for row in read_session(str(kb), SESSION) if row["type"].startswith(("permission/", "approval/"))]
    assert [row["type"] for row in rows] == [pp.EVENT_PRESET, pp.EVENT_APPROVAL_POLICY]
    assert rows[0]["data"] == {"preset": "manual-approval"}
    assert rows[1]["data"] == {"policy": "ask"}

    # 再切一次同一个档：**零事件**（幂等，对齐上游 `if (current !== name)`）
    pp.set_preset(session, "manual-approval")
    again = [row for row in read_session(str(kb), SESSION) if row["type"].startswith(("permission/", "approval/"))]
    assert len(again) == 2

    # 切到别的档：只补一条 preset + 一条变化了的旋钮
    pp.set_preset(session, "all-access")
    rows = [row for row in read_session(str(kb), SESSION) if row["type"].startswith(("permission/", "approval/"))]
    assert [row["data"] for row in rows[-2:]] == [{"preset": "all-access"}, {"policy": "allow-all"}]
    assert pp.current(read_session(str(kb), SESSION)) == "all-access"


@pytest.mark.parametrize("bad", [pp.CUSTOM_PRESET, "yolo", "", None, "MANUAL-APPROVAL"])
def test_custom_and_unknown_are_never_switch_targets(kb: Path, config_file: Path, bad: object) -> None:
    session = SessionStore(str(kb), SESSION)
    with pytest.raises(ValueError):
        pp.set_preset(session, bad)  # type: ignore[arg-type]
    assert [row for row in read_session(str(kb), SESSION) if row["type"].startswith("permission/")] == []


# ── ④ 钉盘 ─────────────────────────────────────────────────────────────────────


def test_pin_and_current_writes_defaults_once(kb: Path, config_file: Path) -> None:
    session = SessionStore(str(kb), SESSION)
    assert pp.pin_and_current(session) == "auto-approval"
    first = [row for row in read_session(str(kb), SESSION) if row["type"].startswith(("permission/", "approval/"))]
    assert [row["data"] for row in first] == [{"preset": "auto-approval"}, {"policy": "auto"}]

    assert pp.pin_and_current(session) == "auto-approval"
    second = [row for row in read_session(str(kb), SESSION) if row["type"].startswith(("permission/", "approval/"))]
    assert len(second) == 2  # 事实已齐 ⇒ 不再补


def test_pin_and_current_respects_an_existing_session_choice(kb: Path, config_file: Path) -> None:
    session = SessionStore(str(kb), SESSION)
    pp.set_preset(session, "all-access")
    assert pp.pin_and_current(session) == "all-access"
    rows = [row for row in read_session(str(kb), SESSION) if row["type"].startswith(("permission/", "approval/"))]
    assert len(rows) == 2  # 已有覆盖 ⇒ 只保留那两条，不追加默认档


# ── ⑤ 按 agent 的默认档 ────────────────────────────────────────────────────────


def test_default_preset_follows_config_per_agent_and_falls_back(config_file: Path) -> None:
    assert pp.default_preset() == pp.DEFAULT_PRESET  # 没有配置 ⇒ 出厂默认
    save_config({"permission": {"main": "manual-approval", "reviewer": "all-access"}})
    assert pp.default_preset() == "manual-approval"
    assert pp.default_preset("reviewer") == "all-access"
    assert pp.default_preset("nobody") == pp.DEFAULT_PRESET  # 该 agent 没配 ⇒ 默认
    save_config({"permission": {"main": "yolo"}})  # 手改坏值 ⇒ 回落，不抛
    assert pp.default_preset() == pp.DEFAULT_PRESET


def test_permission_config_rejects_non_mapping(config_file: Path) -> None:
    with pytest.raises(ConfigError):
        save_config({"permission": ["main"]})


def test_permission_config_round_trip_keeps_other_keys(config_file: Path) -> None:
    save_config({"model": "deepseek-chat"})
    save_config({"permission": {"main": "all-access"}})
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["model"] == "deepseek-chat"
    assert permission_presets_map() == {"main": "all-access"}


# ── ⑥⑦ 三档策略与风险判据 ─────────────────────────────────────────────────────


def test_policy_for_maps_the_three_tiers(kb: Path) -> None:
    assert isinstance(pp.policy_for("all-access"), DefaultApprovalPolicy)
    assert isinstance(pp.policy_for("manual-approval"), AskPolicy)
    assert isinstance(pp.policy_for("auto-approval"), GuardedPolicy)
    with pytest.raises(ValueError):
        pp.policy_for(pp.CUSTOM_PRESET)


def test_manual_tier_fails_closed_without_an_answerer(kb: Path) -> None:
    policy = pp.policy_for("manual-approval", str(kb))  # 没挂载审批信道 ⇒ 无应答者
    decision = policy.decide(_request())
    assert decision.allowed is False
    assert decision.outcome is ApprovalOutcome.UNAVAILABLE
    # 读类调用在任何档都免审批
    assert policy.decide(_request("read_document", read_only=True)).outcome is ApprovalOutcome.ALLOWED_ONCE


def test_all_access_tier_allows_everything() -> None:
    assert pp.policy_for("all-access").decide(_request()).allowed is True


def test_guarded_policy_allows_plain_writes_and_never_waits_without_answerer(kb: Path) -> None:
    policy = pp.policy_for("auto-approval", str(kb))  # 未挂载审批信道 ⇒ 无应答者
    plain = _request(arguments={"intent": "补一节", "ops": [{"op": "upsert_kp"}, {"op": "attach_links"}]})
    assert policy.decide(plain).allowed is True  # 常规写：自动放行（零等待）

    risky = _request(arguments={"intent": "删掉这篇", "ops": [{"op": "delete_file"}]})
    started = time.monotonic()
    decision = policy.decide(risky)  # 风险写要问，但没人应答 ⇒ 立刻按拒绝关闭（不等超时）
    assert decision.allowed is False
    assert decision.outcome is ApprovalOutcome.UNAVAILABLE
    assert time.monotonic() - started < 5


def test_guarded_policy_risky_write_waits_for_the_answer(kb: Path) -> None:
    approval_bridge.attach(str(kb))
    policy = pp.policy_for("auto-approval", str(kb))
    box: dict = {}
    risky = _request(arguments={"intent": "删掉这篇", "ops": [{"op": "delete_file"}]})
    thread = threading.Thread(target=lambda: box.update(decision=policy.decide(risky)), daemon=True)
    thread.start()
    try:
        _wait_pending(str(kb), "c1")  # 挂起中 ⇒ 面板能看到、能点
        assert approval_bridge.answer(str(kb), "c1", ApprovalOutcome.ALLOWED_ONCE) is True
        thread.join(5)
    finally:
        approval_bridge.detach(str(kb))
    assert box["decision"].allowed is True


def test_write_is_risky_treats_unknown_shapes_as_risky() -> None:
    assert write_is_risky(_request(arguments={"intent": "x", "ops": [{"op": "rename_file"}]})) is True
    assert write_is_risky(_request(arguments={"intent": "x", "ops": [{"op": "delete_file"}]})) is True
    assert write_is_risky(_request(arguments={"intent": "x", "ops": [{"op": "move_file"}]})) is True
    # 改正文的三个 op 都**不算**风险：逐字 `expect` + 写前备份 + 可整批撤销（2026-09-22 订正，
    # 见 `approvals.RISKY_OPS` 上方注释：删行与"整段替换成空串"可逆性没有区别）
    assert write_is_risky(_request(arguments={"intent": "x", "ops": [{"op": "delete_lines"}]})) is False
    assert write_is_risky(_request(arguments={"intent": "x", "ops": [{"op": "replace_lines"}]})) is False
    # 认不出（缺 ops / 空表 / 项不是对象 / 项没 op）⇒ 一律按风险
    assert write_is_risky(_request(arguments={})) is True
    assert write_is_risky(_request(arguments={"ops": []})) is True
    assert write_is_risky(_request(arguments={"ops": ["oops"]})) is True
    assert write_is_risky(_request(arguments={"ops": [{}]})) is True
    assert write_is_risky(_request("some_new_write_tool", arguments={"whatever": 1})) is True


def test_default_policy_is_still_the_legacy_allow_all() -> None:
    assert isinstance(DEFAULT_POLICY, DefaultApprovalPolicy)
    assert DEFAULT_POLICY.decide(_request()).allowed is True
    assert ALLOWED_ONCE.allowed is True


# ── ⑧ 逐条确认桥 ───────────────────────────────────────────────────────────────


def test_answerer_requires_attach(kb: Path) -> None:
    assert approval_bridge.answerer_for(str(kb)) is None
    approval_bridge.attach(str(kb))
    try:
        assert callable(approval_bridge.answerer_for(str(kb)))
    finally:
        approval_bridge.detach(str(kb))
    assert approval_bridge.answerer_for(str(kb)) is None


def test_wait_for_answer_resolves_on_answer_and_clears_pending(kb: Path) -> None:
    approval_bridge.attach(str(kb))
    box: dict = {}
    thread = threading.Thread(
        target=lambda: box.update(outcome=approval_bridge.wait_for_answer(str(kb), _request())), daemon=True
    )
    thread.start()
    try:
        rows = _wait_pending(str(kb), "c1")
        # 只暴露工具名与参数（**没有**任何密钥面）
        assert rows == [
            {
                "id": "c1",
                "tool": "propose_write",
                "arguments": {"intent": "精简一节", "ops": [{"op": "upsert_kp"}]},
                "reason": "",
                "created_at": rows[0]["created_at"],
            }
        ]
        assert approval_bridge.answer(str(kb), "c1", ApprovalOutcome.ALLOWED_ONCE) is True
        assert approval_bridge.answer(str(kb), "c1", ApprovalOutcome.REJECTED) is False  # 幂等
        thread.join(5)
    finally:
        approval_bridge.detach(str(kb))
    assert box["outcome"] is ApprovalOutcome.ALLOWED_ONCE
    assert approval_bridge.pending_for(str(kb)) == []


def test_wait_for_answer_times_out_as_unavailable(kb: Path) -> None:
    approval_bridge.attach(str(kb))
    started = time.monotonic()
    try:
        outcome = approval_bridge.wait_for_answer(str(kb), _request(), timeout_s=0.05)
    finally:
        approval_bridge.detach(str(kb))
    assert outcome is ApprovalOutcome.UNAVAILABLE
    assert time.monotonic() - started < 5


def test_abort_resolves_pending_as_cancelled(kb: Path) -> None:
    approval_bridge.attach(str(kb))
    box: dict = {}
    thread = threading.Thread(
        target=lambda: box.update(outcome=approval_bridge.wait_for_answer(str(kb), _request())), daemon=True
    )
    thread.start()
    try:
        _wait_pending(str(kb), "c1")
        approval_bridge.abort(str(kb))
        thread.join(5)
    finally:
        approval_bridge.detach(str(kb))
    assert box["outcome"] is ApprovalOutcome.CANCELLED


def test_detach_resolves_pending_as_unavailable(kb: Path) -> None:
    approval_bridge.attach(str(kb))
    box: dict = {}
    thread = threading.Thread(
        target=lambda: box.update(outcome=approval_bridge.wait_for_answer(str(kb), _request())), daemon=True
    )
    thread.start()
    try:
        _wait_pending(str(kb), "c1")
        approval_bridge.detach(str(kb))  # 作业结束：未决项按拒绝关闭（fail-closed）
        thread.join(5)
    finally:
        approval_bridge.detach(str(kb))
    assert box["outcome"] is ApprovalOutcome.UNAVAILABLE


def _wait_pending(kb_path: str, call_id: str, *, tries: int = 300) -> list[dict]:
    for _ in range(tries):
        rows = approval_bridge.pending_for(kb_path)
        if rows and rows[0]["id"] == call_id:
            return rows
        time.sleep(0.01)
    raise AssertionError("待批项没有在预期时间内登记")


# ── ⑧b 审批审计事件（`approval/asked` / `approval/decided`，log-only）─────────────────


def test_approval_audit_logs_exactly_one_decided_per_ask(kb: Path) -> None:
    """一次人工确认恰落 `asked` + 一条 `decided`（对齐上游；载荷 `{id, tool, reason}` / `{id, outcome}`）。"""
    rows: list[tuple[str, dict]] = []
    approval_bridge.attach(str(kb))
    approval_bridge.attach_audit(str(kb), lambda event_type, data: rows.append((event_type, dict(data))))
    box: dict = {}
    thread = threading.Thread(
        target=lambda: box.update(outcome=approval_bridge.wait_for_answer(str(kb), _request())), daemon=True
    )
    thread.start()
    try:
        _wait_pending(str(kb), "c1")
        assert approval_bridge.answer(str(kb), "c1", ApprovalOutcome.ALLOWED_ONCE) is True
        thread.join(5)
    finally:
        approval_bridge.detach(str(kb))
    assert [row[0] for row in rows] == [approval_bridge.EVENT_ASKED, approval_bridge.EVENT_DECIDED]
    assert rows[0][1] == {"id": "c1", "tool": "propose_write", "reason": ""}
    assert rows[1][1] == {"id": "c1", "outcome": "allowed-once"}


def test_approval_audit_decided_covers_timeout_and_cancel(kb: Path) -> None:
    """超时 ⇒ `decided{unavailable}`；取消 ⇒ `decided{cancelled}` —— 每次 ask 恰一条。"""
    rows: list[tuple[str, dict]] = []
    approval_bridge.attach(str(kb))
    approval_bridge.attach_audit(str(kb), lambda event_type, data: rows.append((event_type, dict(data))))
    try:
        assert approval_bridge.wait_for_answer(str(kb), _request(), timeout_s=0.05) is ApprovalOutcome.UNAVAILABLE
        assert rows[-1][1] == {"id": "c1", "outcome": "unavailable"}

        box: dict = {}
        thread = threading.Thread(
            target=lambda: box.update(outcome=approval_bridge.wait_for_answer(str(kb), _request())), daemon=True
        )
        thread.start()
        _wait_pending(str(kb), "c1")
        approval_bridge.abort(str(kb))
        thread.join(5)
    finally:
        approval_bridge.detach(str(kb))
    assert rows[-1][1] == {"id": "c1", "outcome": "cancelled"}
    assert [row[0] for row in rows] == [
        approval_bridge.EVENT_ASKED,
        approval_bridge.EVENT_DECIDED,
        approval_bridge.EVENT_ASKED,
        approval_bridge.EVENT_DECIDED,
    ]


def test_approval_audit_never_breaks_the_decision(kb: Path) -> None:
    """审计是**旁路**：回调抛错也要照常裁决（吞异常 + warning），没装回调也照常跑。"""
    def boom(event_type: str, data: dict) -> None:
        raise RuntimeError("disk full")

    approval_bridge.attach(str(kb))
    approval_bridge.attach_audit(str(kb), boom)
    try:
        assert approval_bridge.wait_for_answer(str(kb), _request(), timeout_s=0.05) is ApprovalOutcome.UNAVAILABLE
    finally:
        approval_bridge.detach(str(kb))
    # 没装回调的库（另一条 kb 路径）同样不报错
    other = str(kb) + "-nosink"
    approval_bridge.attach(other)
    try:
        assert approval_bridge.wait_for_answer(other, _request(), timeout_s=0.05) is ApprovalOutcome.UNAVAILABLE
    finally:
        approval_bridge.detach(other)


def test_ask_turn_writes_the_approval_audit_into_the_session(kb: Path, config_file: Path) -> None:
    """**端到端**：真实 `ask()` 回合里人工放行一次风险写 ⇒ 会话 JSONL 里能回放 `approval/asked` + `decided`。

    这条是审计面的验收钉子：`_bind_permission()` 把本会话的 `session.append` 装给审批桥。
    """
    provider = _ScriptedRenameProvider()
    approval_bridge.attach(str(kb))

    def _answer_when_pending() -> None:
        for _ in range(600):
            rows = approval_bridge.pending_for(str(kb))
            if rows:
                approval_bridge.answer(str(kb), rows[0]["id"], ApprovalOutcome.ALLOWED_ONCE)
                return
            time.sleep(0.01)

    thread = threading.Thread(target=_answer_when_pending, daemon=True)
    thread.start()
    try:
        result = ask(str(kb), "把演示文件改个名", provider=provider, session_id=SESSION)
    finally:
        thread.join(5)
        approval_bridge.detach(str(kb))

    assert "改名" not in (result.error or "")  # 回合本身正常结束
    rows = [
        row
        for row in read_session(str(kb), SESSION)
        if row["type"] in (approval_bridge.EVENT_ASKED, approval_bridge.EVENT_DECIDED)
    ]
    assert [row["type"] for row in rows] == ["approval/asked", "approval/decided"]
    assert rows[0]["data"]["tool"] == "propose_write"
    assert rows[1]["data"]["outcome"] == "allowed-once"
    assert rows[0]["data"]["id"] == rows[1]["data"]["id"], "asked / decided 必须同 id"
    # 审计事件是 log-only：不进模型请求（`build_history` 只读 user/assistant/tool）
    from memoria.services.agent.session.history import build_history

    kinds = [str(message.role) for message in build_history(str(kb), SESSION)]
    assert not any("approval" in kind for kind in kinds)


# ── ⑨ 轮询载荷 ─────────────────────────────────────────────────────────────────


def test_snapshot_carries_pending_approvals(kb: Path) -> None:
    approval_bridge.attach(str(kb))
    job = AskJob(job_id="j1", kb_path=str(kb), question="q")
    thread = threading.Thread(
        target=lambda: approval_bridge.wait_for_answer(str(kb), _request()), daemon=True
    )
    thread.start()
    try:
        rows = _wait_pending(str(kb), "c1")
        snap = job.snapshot(0)
        assert snap["pending_approvals"] == rows
        assert snap["status"] == "running"  # 既有字段一个没动
        assert approval_bridge.answer(str(kb), "c1", ApprovalOutcome.REJECTED) is True
    finally:
        thread.join(5)
        approval_bridge.detach(str(kb))


# ── ⑩ 四个 RPC ─────────────────────────────────────────────────────────────────


def test_permission_get_returns_default_before_any_session(api: UIAPI, config_file: Path) -> None:
    view = api.agent_permission_get()
    assert view["status"] == "ok"
    assert view["current"] == "auto-approval"  # 没有会话 ⇒ 该 agent 的默认档
    assert view["agent"] == "main"
    assert [row["value"] for row in view["options"]][-1] == pp.CUSTOM_PRESET


def test_permission_set_session_persists_and_switches(api: UIAPI, kb: Path, config_file: Path) -> None:
    SessionStore(str(kb), SESSION)  # 会话先存在（RPC 只切已存在的会话）
    res = api.agent_permission_set_session("manual-approval", str(kb), SESSION)
    assert res["status"] == "ok"
    assert res["current"] == "manual-approval"
    types = [
        row["type"]
        for row in read_session(str(kb), SESSION)
        if row["type"].startswith(("permission/", "approval/"))
    ]
    assert types == [pp.EVENT_PRESET, pp.EVENT_APPROVAL_POLICY]
    assert api.agent_permission_get(str(kb), SESSION)["current"] == "manual-approval"


def test_permission_set_session_rejects_unknown_tier_and_missing_session(
    api: UIAPI, kb: Path, config_file: Path
) -> None:
    res = api.agent_permission_set_session("yolo", str(kb), SESSION)
    assert (res["status"], res["code"]) == ("error", "bad_preset")
    res = api.agent_permission_set_session(pp.CUSTOM_PRESET, str(kb), SESSION)
    assert (res["status"], res["code"]) == ("error", "bad_preset")
    res = api.agent_permission_set_session("all-access", str(kb), SESSION)
    assert (res["status"], res["code"]) == ("error", "no_session")
    assert not Path(session_file(str(kb), SESSION)).exists()  # 拒得干净：没留下半个会话文件
    res = api.agent_permission_set_session("all-access", str(kb), "")
    assert (res["status"], res["code"]) == ("error", "no_session")


def test_permission_set_default_writes_config_only(api: UIAPI, config_file: Path) -> None:
    res = api.agent_permission_set_default("all-access")
    assert res["status"] == "ok"
    assert res["preset"] == "all-access"
    assert permission_presets_map() == {"main": "all-access"}
    assert pp.default_preset() == "all-access"
    res = api.agent_permission_set_default("all-access", "reviewer")
    assert permission_presets_map() == {"main": "all-access", "reviewer": "all-access"}
    res = api.agent_permission_set_default("yolo")
    assert (res["status"], res["code"]) == ("error", "bad_preset")


def test_approval_answer_rpcs_validation_and_effect(api: UIAPI, kb: Path) -> None:
    res = api.agent_approval_answer("c1", "maybe", str(kb))
    assert (res["status"], res["code"]) == ("error", "bad_outcome")
    res = api.agent_approval_answer("c1", "unavailable", str(kb))
    assert (res["status"], res["code"]) == ("error", "bad_outcome")
    res = api.agent_approval_answer("c1", "allowed-once", str(kb))
    assert res == {"status": "ok", "answered": False}  # 没有待批项：幂等、不抛

    approval_bridge.attach(str(kb))
    thread = threading.Thread(
        target=lambda: approval_bridge.wait_for_answer(str(kb), _request()), daemon=True
    )
    thread.start()
    try:
        _wait_pending(str(kb), "c1")
        res = api.agent_approval_answer("c1", "allowed-once", str(kb))
        assert res == {"status": "ok", "answered": True}
        thread.join(5)
    finally:
        approval_bridge.detach(str(kb))


# ── ⑪ 前端接线不变量 ───────────────────────────────────────────────────────────


def test_panel_wires_the_permission_surface() -> None:
    src = _PANEL_JS.read_text(encoding="utf-8")
    for token in (
        'call("agent_permission_get"',
        'call("agent_permission_set_session"',
        'call("agent_permission_set_default"',
        'call("agent_approval_answer"',
        'res.pending_approvals',
        '"manual-approval"',
        '"auto-approval"',
        '"all-access"',
        'PERMISSION_CUSTOM',
    ):
        assert token in src, f"agent-panel.js 缺少接线：{token}"
    # 派生态只展示、不可选：必须给派生态那一个 option 打 disabled
    assert "el.disabled = true" in src
    # 终态必须禁用按钮（否则会留"点了没反应"的卡）
    assert "btn.disabled = true" in src
    # 待批卡的键必须**含 `created_at`**：call id 只保证一轮内唯一，跨轮复用同一个 id 时若按 id
    # 去重，新的待批项会被静默跳过 ⇒ 无人应答 ⇒ 挂起 120s 后被判拒绝（L4 实测到的写入事故）。
    assert 'data-approval-key' in src
    assert 'String(row && row.created_at ? row.created_at : "")' in src
    # 已写下的终态文案不得被下一帧的通用「已处理」覆盖
    assert 'if (el.classList.contains("-agent-approve--done")) return;' in src


def test_settings_html_exposes_the_default_tier_select() -> None:
    html = _INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="agent-permission-default"' in html
    assert 'data-i18n="agent.settings.permissionLabel"' in html


@pytest.mark.parametrize("locale", _LOCALES, ids=lambda p: p.stem)
def test_locales_have_every_new_key(locale: Path) -> None:
    text = locale.read_text(encoding="utf-8")
    for key in _PERMISSION_KEYS:
        leaf = key.rsplit(".", 1)[-1]
        assert leaf + ":" in text, f"{locale.name} 缺少键：{key}"
