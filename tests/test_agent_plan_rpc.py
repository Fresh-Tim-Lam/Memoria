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
    "undo",
    "undoTitle",
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


def test_undo_returns_to_the_conversation_start(kb: Path, api: UIAPI) -> None:
    """一键撤销：一次对话写两批 ⇒ 一次撤销回到**对话开始前**（起点快照），且**幂等**。

    人 2026-09-21 定稿：「一键生效，不再有被阻止」⇒ 后端只保留"回到起点"这一种语义（`txid` 参数
    留给调试）。`apply_plan` 会在**第一次写入前**把那一版固化进 `<session>/origin/`。
    """
    before = _tracked(kb)
    first = api.agent_plan_apply(_plan(), None, None, None)
    assert first["status"] == "ok", first

    second_plan = _plan()
    second_plan["txid"] = "20260920T021200Z-08"
    second_plan["ops"] = [
        {
            "op": "upsert_kp",
            "op_id": "o1",
            "file": "notes/a.md",
            "kp_id": "tail",
            "name": "末尾",
            "range": {"start": {"line": 5}, "end": {"line": 5}},
        }
    ]
    second = api.agent_plan_apply(second_plan, None, None, None)
    assert second["status"] == "ok", second
    assert first["session_id"] == second["session_id"] == UI_SESSION
    assert _tracked(kb) != before
    assert (Path(backups_root(str(kb))) / UI_SESSION / "origin" / "journal.json").is_file()

    undone = api.agent_plan_undo(None, UI_SESSION, None)
    assert undone["status"] == "ok", undone
    assert _tracked(kb) == before  # 逐字节回到**对话开始前**
    assert undone["recover"]["errors"] == 0

    # 幂等：再点一次仍然成功（回到同一个状态），不会出现"没有批次 / 被拒绝"
    again = api.agent_plan_undo(None, UI_SESSION, None)
    assert again["status"] == "ok", again
    assert _tracked(kb) == before


def test_undo_never_blocks_even_after_external_change(kb: Path, api: UIAPI) -> None:
    """盘上被别的写者改过 ⇒ 撤销**仍然成功**（自动先兜底那一版），不再有 `external_change` 拒绝。

    真机路径（人："仍然撤销失败"）：agent 写完 → 人跑产品「构建」（产品改 sidecar / pending）⇒
    旧实现判 `external_change` 整批拒、连点两次都失败。现在覆盖前先把当前版本另存 `manual-force`
    批次 ⇒ 可以直接撤，且那份改动没丢。
    """
    before = _tracked(kb)
    done = api.agent_plan_apply(_plan(), None, None, None)
    assert done["status"] == "ok", done
    changed = (kb / "notes" / "a.md").read_text(encoding="utf-8") + "\n产品构建改的一行。\n"
    (kb / "notes" / "a.md").write_text(changed, encoding="utf-8")

    undone = api.agent_plan_undo(None, UI_SESSION, None)

    assert undone["status"] == "ok", undone
    assert _tracked(kb) == before  # 回到对话开始前
    assert undone["safety_backup"]["txid"]  # 被覆盖掉的那一版已另存（覆盖 ≠ 丢数据）


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
        "preview.base_versions || null",  # §9 规则 ①：人看过的那一版原样回传
        "ops: (plan.ops || []).filter(",  # 勾选 = 编译前的选择（未勾的 op 直接去掉）
        "WR().setBusy?.(true)",  # §9 规则 ② 的另一半：写期间人机保存 deferIfBusy 让路
        "WR().setBusy?.(false)",
        "__memoriaHasPendingEdits",  # 当前编辑未落盘 ⇒ 先等（有界）再拒写
        'code: "editing"',
        'r.code === "stale_write"',  # stale_write 时给「重新预览」这条明路（§9 规则 ①）
        "function renderInto(el, inner, state)",  # 一份计划一张卡：确认后**原地**换成结果
        "showResult(res, plan, root)",  # apply 后原地推进（不留能重复点的旧卡）
        "drainProposals(res.session_id)",  # 这批提议属于**这次对话** ⇒ 审计也落这里
        "agent_plan_apply\", cropped, null, sessionId",  # 应用时带上会话 id（不是 ui-plan 伪会话）
        # 撤销 / 重做：**栈语义**（人 2026-09-21 定稿「撤销一步 / 重做一步」「采用 stack 设计」）
        'agent_plan_undo_step", null, sid',  # 撤销**一步**（指针 −1，用该批 pre-image）
        'agent_plan_redo", null, sid',  # 重做**一步**（指针 +1，用该批写后镜像）
        'agent_plan_stack", null, sid',  # 取栈现状 ⇒ 状态栏显示"栈 p/t"与按钮可用性
        "async function undoWrite(sessionId)",
        "async function redoWrite(sessionId)",
        "async function refreshStack(sessionId)",
        "async function afterStep(res, sessionId)",  # 一步之后：同步界面 + 重取栈 + 重绘状态栏
        # **栈里还有步骤 ⇒ 状态栏必须留着**（人 2026-09-21：「撤销之后栈状态栏就没了，我无法重做」）。
        # 曾经的条件是 `stack.cursor < 0 → markWriteUndone()`：撤到最底时把整条状态栏连同重做入口一起
        # 收掉。现在只有"栈里真的没有步骤"（total === 0）才清；`markWriteUndone` 已整体删除。
        "if (stack && !stack.total)",
        "panel?.setWriteState?.(null)",
        # 写入回执 ⇒ 交给对话栏**顶部副标题行**的写入状态栏（撤销只在那里出现一次）
        "function publishWriteState(rec, sessionId)",
        "function publishRecord(rec, sessionId)",
        "panel.setWriteState({",
        'esc(roleLabel(state))',  # 手动预览卡的角色标签
        # 写 / 撤销后的**界面同步**（人："agent 对话之后自动刷新渲染"）：文件树 + 当前文件重载 +
        # 待确认摘要 + 图谱 ⇒ 不必手动重开或切页
        "async function syncAfterWrite(files)",
        "await app.refreshFiles?.()",
        "await app.openFile?.(cur, { skipNav: true })",  # 重开当前文件（不产生新的导航栈条目）
        "await app.refreshKbPendingSummary?.()",
        "await app.loadGraphData?.()",
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
    # 反向：**不许**再用「已撤销」短显态把状态栏收掉 —— 它会连重做入口一起收（人 2026-09-21 报障）。
    assert "panel?.markWriteUndone?.()" not in src
    assert "stack.cursor < 0" not in src, "撤到最底 ≠ 该收起来：那时 can_redo 才刚变成可用"
    # **手动应用**这条路径也要把回执交给状态栏（否则没有栈位置、也没有重做入口），且会话 id 必须
    # 回落到后端同一个伪会话 `ui-plan`（少这一环 ⇒ 查不到栈 ⇒ 状态栏空有壳）。
    assert "publishWriteState({ preview: preview, result: res || {} }, root.__session || null);" in src
    assert 'const sid = sessionId || (rec && rec.session_id) || result.session_id || "ui-plan";' in src
    # 卡片上的撤销入口与状态栏**同一语义**（都是"一步"）：不许再出现"回到对话开始前"那种措辞
    # （它做的是 `agent_plan_undo_step`，说出来就是谎）。
    zh = (_APP / "i18n" / "zh-CN.js").read_text(encoding="utf-8")
    en = (_APP / "i18n" / "en.js").read_text(encoding="utf-8")
    assert "撤销这次对话的改动" not in zh and "this conversation's writes" not in en


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
    """走**真注册表**调用（含参数校验与审批）—— 保证"工具在场 + 默认策略放行"这条链是通的。

    2026-09-22 起多了一道**读后写闸**（`fs-observation-policy` 端口，`services/agent/observation.py`）⇒
    这里按**真实回合**的顺序，先把本批要改的文件各读一遍（模型也是先读后写）。
    """
    registry = ToolRegistry(build_kb_tools(str(kb)))
    targets = {
        str(op.get("file") or "")
        for op in (args.get("ops") or [])
        if isinstance(op, dict) and str(op.get("op") or "") != "create_file"
    }
    for rel in sorted(targets - {""}):
        registry.invoke(ToolCall(id="r", name="read_document", arguments=json.dumps({"path": rel})))
    return registry.invoke(ToolCall(id="c1", name=PROPOSE_TOOL_NAME, arguments=json.dumps(args)))


def test_propose_tool_is_a_write_tool_and_default_policy_allows_it(kb: Path) -> None:
    """按 `read_only=False` 声明（它**确实会落盘**）⇒ 默认策略**全线放行**（人 2026-09-21 拍板）。

    旧口径是"它不改动知识库、落盘权在人"，故声明 `read_only=True`；写机制放开后不再成立。
    """
    tools = {tool.name: tool for tool in build_kb_tools(str(kb))}
    assert PROPOSE_TOOL_NAME in tools
    assert tools[PROPOSE_TOOL_NAME].read_only is False
    assert DEFAULT_POLICY.decide(ApprovalRequest(tool=PROPOSE_TOOL_NAME, read_only=False)).allowed


def test_propose_tool_writes_immediately_and_queues_a_receipt(kb: Path) -> None:
    """提议成功 ⇒ **当场落盘**（侧车写了、备份批次与审计都在），并排一条**回执**进信箱供前端展示。"""
    before = _facts(kb, with_audit=True)
    result = _invoke_propose(kb, _propose_args())
    assert result.is_error is False, result.content
    assert result.content.startswith("**已写入**")

    after = _facts(kb, with_audit=True)
    sidecar = ".memoria/sidecars/notes/a.memoria.yaml"
    assert sidecar not in before and sidecar in after  # 知识点（侧车）真的写进去了
    assert after != before

    records = take_proposals(str(kb))
    assert len(records) == 1
    rec = records[0]
    plan = rec["plan"]
    assert plan["v"] == 1 and plan["intent"] == "给「注意力机制」建档"
    assert re.match(r"^\d{8}T\d{6}Z-\d+$", plan["txid"])
    assert plan["ops"][0]["op_id"] == "o1"  # 模型没写 op_id 时由程序补齐
    assert rec["result"]["status"] == "ok" and rec["result"]["auto"] is True
    assert rec["session_id"] == "agent-auto"  # 调用方没给会话 id ⇒ 审计落 auto 会话
    assert rec["preview"]["previewed"] is True
    assert take_proposals(str(kb)) == []  # 取走即清空


def test_propose_tool_rejects_bad_op_without_queueing(kb: Path) -> None:
    """越界路径 ⇒ 被**读后写闸**更早拦下（fail-closed），且**不进信箱**。

    2026-09-22 起 `propose_write` 先在工具处理器过「读后写闸」（`fs-observation-policy` 端口）：
    `../escape.md` 连"读过"都做不到 ⇒ 直接 `FS_NOT_OBSERVED`，比计划编译器更早关门（恢复指引照旧：
    先 `read_document`、再重提整批）。编译器那一层仍由下一个用例覆盖。
    """
    bad = _propose_args(ops=[{**_propose_args()["ops"][0], "file": "../escape.md"}])
    result = _invoke_propose(kb, bad)
    assert result.is_error is True
    assert result.output.code == "FS_NOT_OBSERVED"
    assert "read_document" in result.content
    assert take_proposals(str(kb)) == []


def test_propose_tool_rejects_bad_plan_with_guidance(kb: Path) -> None:
    """**过闸之后**的语义错误仍由计划编译器拦：`INVALID_PLAN` + 按 `op_id` 定位 + 「别把它删掉」的恢复指引。

    用"引用了文件里不存在的原文"（最常见的真机错误：模型照着旧内容写 `expect`）来触发。
    """
    bad = _propose_args(
        ops=[
            {
                "op": "replace_lines",
                "file": "notes/a.md",
                "range": {"start": {"line": 3}, "end": {"line": 3}},
                "expect": "这句原文在文件里根本不存在",
                "text": "改后的正文。",
            }
        ]
    )
    result = _invoke_propose(kb, bad)
    assert result.is_error is True
    assert result.output.code == "INVALID_PLAN"
    assert "o1" in result.content and "什么都没写" in result.content
    # 恢复指引（真机取证后补）：先重新读一遍拿当前行号，再**重提整批**、别把出错的 op 删掉
    assert "read_document" in result.content
    assert "别把它删掉" in result.content
    assert take_proposals(str(kb)) == []


def test_propose_tool_text_reports_the_write(kb: Path) -> None:
    """回文必须**如实报结果**：写明「已写入 … txid …」与撤销入口，并提醒别重复提同一批。"""
    result = _invoke_propose(kb, _propose_args())
    assert "已写入" in result.content and "txid" in result.content
    assert "撤销" in result.content
    assert "重复" in result.content


def test_plan_pending_rpc_drains_once(kb: Path, api: UIAPI) -> None:
    """RPC 取走即清空（第二次为空表）；没有记录时也回 `ok`（不是错误）。"""
    assert api.agent_plan_pending() == {"status": "ok", "records": [], "plans": []}
    _invoke_propose(kb, _propose_args())
    first = api.agent_plan_pending()
    assert first["status"] == "ok" and len(first["records"]) == 1
    assert first["records"][0]["result"]["status"] == "ok"
    assert first["plans"][0]["intent"] == "给「注意力机制」建档"
    assert api.agent_plan_pending()["records"] == []


def test_capability_self_report_follows_tool_presence(kb: Path) -> None:
    """提示词的"只读"那句按**工具是否在场**二选一：没有写工具时逐字保持原口径。"""
    registry = ToolRegistry(build_kb_tools(str(kb)))
    assert "不能修改、创建或删除任何文件" in build_system_prompt(str(kb), tools=())

    tool = registry.get(PROPOSE_TOOL_NAME)
    assert tool is not None
    write_prompt = build_system_prompt(str(kb), tools=(tool.schema(),))
    assert "不能修改、创建或删除任何文件" not in write_prompt
    assert "你可以**直接写入**知识库" in write_prompt
    assert "以工具回文为准" in write_prompt

