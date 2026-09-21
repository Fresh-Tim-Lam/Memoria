"""M3a ④ 的两个可测面：**计划 API 的 RPC 暴露**（四个只读面 + apply + undo）与**前端接线不变量**。

口径（`docs/design/agent-plugin-design.md §9`、`docs/design/agent-capabilities.md §2.3.3`）：

1. 四个只读面（`agent_plan_validate` / `_preview` / `_resolve` / `_audit`）**零落盘** ——
   只允许碰可再生缓存 `.memoria/cache/**`；
2. `preview` 下发的 `base_versions` 就是"人看过的那一版"；盘上一变 ⇒ apply **整批拒**
   （`stale_write`）且此刻**尚未建备份**、**未写盘**（§9 规则 ①）；
3. apply 之后可 `agent_plan_undo` 撤销，文件**逐字节**回到写入前（§2.3.2 第 5 条）；
4. 前端确认卡（`js/plan-confirm.js`）：勾选在**编译前**做（未勾的 op 从 `plan.ops` 去掉）、
   apply 期间 `setBusy(true)` 让人机保存让路、当前编辑未落盘就**拒写**（§9 规则 ②）。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from memoria.presentation.api.ui import UIAPI
from memoria.services.agent.backup import backups_root
from memoria.services.agent.llm.types import ToolCall
from memoria.services.agent.prompt import build_system_prompt
from memoria.services.agent.session.store import session_file
from memoria.services.agent.tools.kb import PROPOSE_TOOL_NAME, build_kb_tools, take_proposals
from memoria.services.agent.tools.registry import ToolRegistry
from memoria.services.agent.approvals import DEFAULT_POLICY, ApprovalRequest

A_MD = "# A 文档\n\n注意力机制是核心。\n\n末尾一行。\n"
UI_SESSION = "ui-plan"  # RPC 未给 session_id 时的伪会话（备份/审计都落它名下）

_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "src" / "memoria" / "ui" / "static" / "app"
_PLAN_JS = _APP / "js" / "plan-confirm.js"
_INDEX_HTML = _APP / "index.html"
_LOCALES = [_APP / "i18n" / "zh-CN.js", _APP / "i18n" / "en.js"]

#: 确认卡用到的全部 i18n 键（中英必须成对，缺一个界面就会漏出裸 key）
_PLAN_KEYS = (
    "role",
    "summary",
    "apply",
    "applying",
    "needSelect",
    "discard",
    "dirty",
    "done",
    "failed",
    "undone",
    "undo",
    "undoFail",
    "rollback",
    "rejected",
    "rePreview",
    "rePreviewTitle",
    "close",
    "errorsTitle",
    "warningsTitle",
    "noDiff",
    "empty",
    "badJson",
    "entry",
    "entryTitle",
    "pasteTitle",
    "pasteHint",
    "preview",
)


@pytest.fixture()
def kb(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "notes").mkdir(parents=True)
    (root / ".memoria").mkdir()
    (root / "notes" / "a.md").write_text(A_MD, encoding="utf-8")
    return root


@pytest.fixture()
def api(kb: Path) -> UIAPI:
    return UIAPI(kb_path=str(kb))


def _plan() -> dict:
    return {
        "v": 1,
        "txid": "20260920T021100Z-07",
        "intent": "测试用 plan",
        "ops": [
            {
                "op": "upsert_kp",
                "op_id": "o1",
                "file": "notes/a.md",
                "kp_id": "attention",
                "name": "注意力机制",
                "range": {"start": {"line": 1}, "end": {"line": 3}},
            }
        ],
    }


def _facts(root: Path, *, with_audit: bool = False) -> dict[str, str]:
    """事实源指纹：全库逐文件 sha256。

    **排除**：① `.memoria/cache/**`（可再生缓存，[AGENTS.md §1](../../AGENTS.md)）；
    ② `.memoria/agent/sessions/**`（**审计流**）—— 除非 `with_audit=True`。审计是"过了校验的
    落地尝试**必须**留痕"（§2.3.2 第 8 步）⇒ 它本来就该变；而"零写入"说的是**正文 / sidecar /
    manifest / pending** 一个字节都不动。
    """
    facts: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".memoria/cache/"):
            continue
        if not with_audit and rel.startswith(".memoria/agent/sessions/"):
            continue
        facts[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return facts


# ── ① 四个只读面：都在、都零落盘 ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("agent_plan_validate", (_plan(),)),
        ("agent_plan_preview", (_plan(),)),
        ("agent_plan_resolve", ("attention",)),
        ("agent_plan_audit", ()),
    ],
)
def test_read_only_faces_write_nothing(kb: Path, api: UIAPI, name: str, args: tuple) -> None:
    """四个只读面都是 public RPC（壳层靠反射暴露），且跑完**事实源逐文件不变**。"""
    before = _facts(kb, with_audit=True)
    result = getattr(api, name)(*args)
    assert isinstance(result, dict) and result.get("status") in ("ok", "error", "not_found", "ambiguous")
    assert _facts(kb, with_audit=True) == before, f"{name} 动了事实源（只读面必须零落盘）"


def test_read_only_faces_report_no_kb_without_open_kb(tmp_path: Path) -> None:
    """未开库 ⇒ 结构化 `no_kb`（不抛裸异常），且不误报其他错误。"""
    api = UIAPI(kb_path=None)
    for name, args in (
        ("agent_plan_validate", (_plan(),)),
        ("agent_plan_preview", (_plan(),)),
        ("agent_plan_resolve", ("attention",)),
        ("agent_plan_audit", ()),
        ("agent_plan_apply", (_plan(),)),
        ("agent_plan_undo", ()),
    ):
        res = getattr(api, name)(*args)
        assert res.get("status") == "error" and res.get("code") == "no_kb", (name, res)


# ── ② preview ↔ apply 的版本契约（§9 规则 ①）──────────────────────────────


#: "写→撤销逐字节还原"要比对的那几条**事实源**（正文 + sidecar + manifest + pending）
_TRACKED = (
    "notes/a.md",
    ".memoria/sidecars/notes/a.memoria.yaml",
    ".memoria/manifest.yaml",
    ".memoria/pending.json",
)


def _tracked(root: Path) -> dict[str, str]:
    """只取 `_TRACKED` 那几条事实源的 sha256。

    不整树比对的四个**有意例外**（都不是"这次写动的正文事实源"）：
    ① `.memoria/agent/backups/**` —— 批次按保留策略留着（撤销不删备份，5 批 FIFO 才淘汰）；
    ② `.memoria/agent/sessions/**` —— 审计流（本来就该追加）；
    ③ `*.bak`（manifest / pending 的原子写旁路副本）—— 既有写路径的既有行为；
    ④ `.memoria/kp_targets.json` / `.memoria/cache/**` —— **派生索引**，payload 里带 `built_at`
       时间戳 ⇒ 即便内容等价字节也不同（[AGENTS.md §1](../../AGENTS.md)：派生/缓存不是事实源）。
    """
    return {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest() for rel in _TRACKED if (root / rel).is_file()}


def test_preview_then_apply_round_trips_and_undo_restores_bytes(kb: Path, api: UIAPI) -> None:
    """preview 的 `base_versions` 原样回传 ⇒ 落地成功；撤销后**逐字节**回到写入前。"""
    before = _tracked(kb)
    api.load_document("notes/a.md")  # 模拟"人正开着这个文件"⇒ 应用侧 `_cache` 里有写入前的解析
    preview = api.agent_plan_preview(_plan())
    assert preview["status"] == "ok" and preview["previewed"] is True
    assert preview["base_versions"]["notes/a.md"]  # 版本令牌非空

    done = api.agent_plan_apply(_plan(), None, None, preview["base_versions"])
    assert done["status"] == "ok", done
    assert done["session_id"] == UI_SESSION and done["txid"] == "20260920T021100Z-07"
    assert done["audit"]["status"] == "ok"  # 审计留痕（log-only）
    assert Path(backups_root(str(kb))) / UI_SESSION / done["txid"]  # 写前备份确实落盘
    assert (kb / ".memoria" / "sidecars" / "notes" / "a.memoria.yaml").is_file()  # sidecar 真的写了
    assert _tracked(kb) != before

    undone = api.agent_plan_undo(None, UI_SESSION, done["txid"])
    assert undone["status"] == "ok", undone
    assert _tracked(kb) == before  # 逐字节还原（正文 + sidecar + manifest + pending）
    # 撤销是**直接写盘**、不走 save_document ⇒ 事后必须没有"写入前的旧解析"残留（§2.3.2 第 5 条）
    rec = undone["recover"]
    assert rec["errors"] == 0 and isinstance(rec["cache_cleared"], list)
    assert "notes/a.md" not in getattr(api._svc, "_cache", {})


def test_apply_refuses_when_disk_changed_after_preview(kb: Path, api: UIAPI) -> None:
    """§9 规则 ①：看过预览之后文件被改过 ⇒ **整批拒**、**未建备份**、**零写入**。"""
    preview = api.agent_plan_preview(_plan())
    (kb / "notes" / "a.md").write_text(A_MD + "\n人写的尾巴。\n", encoding="utf-8")
    after_human_edit = _facts(kb)

    res = api.agent_plan_apply(_plan(), None, None, preview["base_versions"])

    assert res["status"] == "error" and res["code"] == "stale_write"
    assert res["files"] == ["notes/a.md"] and res["audit"]["status"] == "ok"  # 拒也要留痕
    assert _facts(kb) == after_human_edit  # 正文 / sidecar / manifest / pending 零写入
    assert _facts(kb, with_audit=True) != after_human_edit  # 变的**只有**审计流
    assert not (Path(backups_root(str(kb))) / UI_SESSION).exists()  # 拒批发生在建备份之前


def test_apply_rejects_invalid_plan_without_backup(kb: Path, api: UIAPI) -> None:
    """校验不过 ⇒ `invalid_plan`（错误按 `op_id` 定位），**未建备份、未写盘**（含审计也不写）。

    "无 silent 写"（§2.6 安全门第 1 条）的严格口径：**校验期拒绝 = 零字节变化**；
    只有**过了校验的落地尝试**才一律留痕。
    """
    bad = _plan()
    bad["ops"][0]["file"] = "../escape.md"
    before = _facts(kb, with_audit=True)
    res = api.agent_plan_apply(bad)
    assert res["status"] == "error" and res["code"] == "invalid_plan"
    assert res["errors"] and res["errors"][0]["op_id"] == "o1"
    assert _facts(kb, with_audit=True) == before
    assert not (Path(backups_root(str(kb))) / UI_SESSION).exists()


def test_undo_requires_session_id(kb: Path, api: UIAPI) -> None:
    """撤销必须显式给 `session_id`（apply 的返回值里有）—— 不给就明确报错，不猜。"""
    res = api.agent_plan_undo()
    assert res == {
        "status": "error",
        "code": "no_session",
        "message": "撤销需要 session_id（apply 的返回值里有）",
    }


# ── ③ 审计落在会话流里（RPC 路径同样）────────────────────────────────────


def test_rpc_apply_writes_capability_event_into_session(kb: Path, api: UIAPI) -> None:
    """RPC 走的也是同一条审计通道：`capability/apply` 追加进 `ui-plan` 会话文件。"""
    assert api.agent_plan_apply(_plan())["status"] == "ok"
    path = Path(session_file(str(kb), UI_SESSION))
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kinds = [e["type"] for e in events]
    assert kinds == ["session/header", "capability/apply"]
    # `files` = 编译期算出的**受影响文件集**（正文 + sidecar + manifest + pending）
    assert events[-1]["data"]["files"][0] == "notes/a.md"
    assert events[-1]["data"]["backup"]["txid"] == "20260920T021100Z-07"


# ── ④ 前端确认卡的接线不变量（源码级，避免"写完没接上"）───────────────────


def test_plan_card_is_loaded_by_index_html() -> None:
    assert '/app/js/plan-confirm.js' in _INDEX_HTML.read_text(encoding="utf-8")


def test_plan_card_wiring_invariants() -> None:
    """卡片必须同时满足：**挂在对话栏里**、dry-run 先行、勾选在编译前、忙位包住 apply、脏编辑拒写、可撤销。

    "挂在对话栏里"= 渲染进 `#agent-messages` 的一条聊天项（`.-agent-msg`），对话栏不可用才回落弹窗；
    "长文本悬浮看全"= 被截断的文本都带 `title`（`cursor: help` 由 CSS 给）。
    """
    src = _PLAN_JS.read_text(encoding="utf-8")
    for needle in (
        'document.getElementById("agent-messages")',  # ① 卡片落在对话栏，不是盖住界面的弹窗
        '"-agent-msg -agent-msg--assistant -agent-plan-msg"',
        "box.scrollTop = box.scrollHeight",  # 与问答流同款：新卡片滚进视野
        '"-modal-backdrop"',  # ② 对话栏不可用时的回落
        '"agent_plan_preview"',  # ③ 先预览（零落盘）
        '"agent_plan_apply"',
        '"agent_plan_undo"',
        "preview.base_versions || null",  # §9 规则 ①：人看过的那一版原样回传
        "ops: (plan.ops || []).filter(",  # 勾选 = 编译前的选择（未勾的 op 直接去掉）
        "WR().setBusy?.(true)",  # §9 规则 ② 的另一半：写期间人机保存 deferIfBusy 让路
        "WR().setBusy?.(false)",
        "__memoriaHasPendingEdits",  # 当前编辑未落盘 ⇒ 先等（有界）再拒写
        'code: "editing"',
        'r.code === "stale_write"',  # stale_write 时给「重新预览」这条明路（§9 规则 ①）
        "function renderInto(el, inner, state)",  # 一份计划一张卡：确认后**原地**换成结果
        "showResult(res, plan, root)",  # apply/undo 都原地推进（不留能重复点的旧卡）
        "showResult(undone, root.__plan || null, root)",
        "openFile?.(cur, { skipNav: true })",  # 写后重开当前文件（不产生新的导航栈条目）
        'clipped("plan-file-path"',  # ④ 长文本"单行省略 + 悬浮看全"
        'clipped("plan-diff-line plan-diff-del"',
        "title=\"${esc(full)}\"",
        'actions.querySelector("#agent-plan-open")',  # ⑤ 对话栏输入区的入口按钮（幂等）
        '"agent_plan_pending"',  # ⑥ 智能体自己提的计划：问答收尾时取一次
        "const inner = app.call;",  # 包装门面 `call`（与 agent-panel.js 同款做法）
        "installProposalDrain()",
        'res.status === "done" || res.status === "error"',  # 只在轮次收尾取，不额外轮询
        "global.MemoriaBridge?.onReady?.(",  # 门面就绪后才装入口（否则拿到裸 i18n key）
        "global.MemoriaI18n?.addRefresh?.(",
    ):
        assert needle in src, f"plan-confirm.js 缺接线：{needle}"


@pytest.mark.parametrize("locale", _LOCALES, ids=lambda p: p.name)
def test_plan_card_keys_exist_in_every_locale(locale: Path) -> None:
    """中英必须成对（缺键 ⇒ 卡片会出现裸 key）。"""
    src = locale.read_text(encoding="utf-8")
    assert "plan: {" in src
    for key in _PLAN_KEYS:
        assert f"{key}:" in src, f"{locale.name} 缺 plan.{key}"
    for op in ("upsert_kp", "attach_links", "detach_links"):
        assert f"{op}:" in src, f"{locale.name} 缺 plan.op.{op}"


def test_plan_card_css_truncates_with_a_tooltip() -> None:
    """CSS 侧：被截断的那几类文本必须"单行 + 省略号 + 可悬浮"，且卡片在聊天气泡里不继承 `pre-wrap`。"""
    css = (_APP / "css" / "app.css").read_text(encoding="utf-8")
    for needle in (
        ".-agent-plan-msg { white-space: normal;",
        ".plan-file-path,",
        "text-overflow: ellipsis;",
        "cursor: help;",
        ".plan-actions {",
    ):
        assert needle in css, f"app.css 缺计划卡样式：{needle}"


# ── ⑤ 工具面（W 线第一步）：`propose_write` 只提议、不落盘 ──────────────────────────


def _propose_args(**over: object) -> dict:
    args: dict = {
        "intent": "给「注意力机制」建档",
        "ops": [
            {
                "op": "upsert_kp",
                "file": "notes/a.md",
                "kp_id": "attention",
                "name": "注意力机制",
                "range": {"start": {"line": 1}, "end": {"line": 3}},
            }
        ],
    }
    args.update(over)
    return args


def _invoke_propose(kb: Path, args: dict):
    """走**真注册表**调用（含参数校验与审批）—— 保证"工具在场 + 默认策略放行"这条链是通的。"""
    registry = ToolRegistry(build_kb_tools(str(kb)))
    return registry.invoke(ToolCall(id="c1", name=PROPOSE_TOOL_NAME, arguments=json.dumps(args)))


def test_propose_tool_present_and_read_only_by_declaration(kb: Path) -> None:
    """工具在场、按 `read_only=True` 声明（口径：它**不改动知识库**，落盘权在人）⇒ 默认策略放行。"""
    tools = {tool.name: tool for tool in build_kb_tools(str(kb))}
    assert PROPOSE_TOOL_NAME in tools
    assert tools[PROPOSE_TOOL_NAME].read_only is True
    assert DEFAULT_POLICY.decide(ApprovalRequest(tool=PROPOSE_TOOL_NAME, read_only=True)).allowed


def test_propose_tool_queues_a_plan_and_writes_nothing(kb: Path) -> None:
    """提议成功 ⇒ 排进信箱（程序补 `v`/`txid`/`op_id`），而**知识库逐字节不变**。"""
    before = _facts(kb, with_audit=True)
    result = _invoke_propose(kb, _propose_args())
    assert result.is_error is False, result.content
    assert _facts(kb, with_audit=True) == before  # 零落盘（提议还没到写那一步）

    plans = take_proposals(str(kb))
    assert len(plans) == 1
    plan = plans[0]
    assert plan["v"] == 1 and plan["intent"] == "给「注意力机制」建档"
    assert re.match(r"^\d{8}T\d{6}Z-\d+$", plan["txid"])
    assert plan["ops"][0]["op_id"] == "o1"  # 模型没写 op_id 时由程序补齐
    assert take_proposals(str(kb)) == []  # 取走即清空


def test_propose_tool_rejects_bad_op_without_queueing(kb: Path) -> None:
    """越界路径 ⇒ `INVALID_PLAN` + 按 `op_id` 定位，且**不进信箱**（让模型重写整批再提）。"""
    bad = _propose_args(ops=[{**_propose_args()["ops"][0], "file": "../escape.md"}])
    result = _invoke_propose(kb, bad)
    assert result.is_error is True
    assert result.output.code == "INVALID_PLAN"
    assert "o1" in result.content and "什么都没写" in result.content
    assert take_proposals(str(kb)) == []


def test_propose_tool_text_forbids_claiming_a_write(kb: Path) -> None:
    """提示词纪律：工具结果必须写明「尚未写入」，并禁止模型谎称已写入。"""
    result = _invoke_propose(kb, _propose_args())
    assert "尚未写入" in result.content and "不要声称已经写入" in result.content


def test_plan_pending_rpc_drains_once(kb: Path, api: UIAPI) -> None:
    """RPC 取走即清空（第二次为空表）；没有提议时也回 `ok`（不是错误）。"""
    assert api.agent_plan_pending() == {"status": "ok", "plans": []}
    _invoke_propose(kb, _propose_args())
    first = api.agent_plan_pending()
    assert first["status"] == "ok" and len(first["plans"]) == 1
    assert api.agent_plan_pending()["plans"] == []


def test_capability_self_report_follows_tool_presence(kb: Path) -> None:
    """提示词的"只读"那句按**工具是否在场**二选一：没有提议工具时逐字保持原口径。"""
    registry = ToolRegistry(build_kb_tools(str(kb)))
    assert "不能修改、创建或删除任何文件" in build_system_prompt(str(kb), tools=())

    tool = registry.get(PROPOSE_TOOL_NAME)
    assert tool is not None
    write_prompt = build_system_prompt(str(kb), tools=(tool.schema(),))
    assert "不能修改、创建或删除任何文件" not in write_prompt
    assert "你可以**提议**对知识库的修改" in write_prompt
    assert "你自己没有落盘权" in write_prompt

