# 语义移植自 deepseek-harness packages/interaction/commands（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""斜杠命令（slash command）：**人类直呼、不进模型**的一条本地通路。

上游 `interaction/commands` 的形状：一个插件可注册的**命令注册表** + 一条 `execute()`：
整行以 `/name` 开头且**名字已注册** ⇒ 交给 handler **在宿主侧执行**（不产生模型消息）；
**名字没注册 ⇒ `execute()` 回 `undefined`**，调用方把那行当**普通文本**发出去（所以 `/usr/bin`、
`5/8` 这类不会被误判）。执行全程有**成对**的 log-only 生命周期事件 `command/run` → `command/done`
（按 `commandId` 配对，与 `tool/call`↔`tool/result` 同构）。

## 照搬的规则（逐条注明上游出处）

| 规则 | 上游 |
|---|---|
| 命令名语法 `^[a-z][a-z0-9_-]*$` | `src/index.ts:32` |
| 行解析 `/^\\/([a-z][a-z0-9_-]*)(?=$|[\t\n\r ])/`；`rawInput` = **其后原文**（含分隔空白） | `:125-132` |
| 未知名 ⇒ 回 `undefined`（**回落到普通文本**，不报错、不落任何事件） | `:367-370`（注释「Admission misses … log nothing」） |
| `command/run` `{commandId, name, args?, source:{kind:'user'}}` + `command/done` `{commandId, kind, text?}`，**都是 log-only**（不进模型上下文） | `src/types.ts:93-118` |
| `recordInput:false` ⇒ `command/run` 不带 `args`（避免与领域事件重复记载荷） | `:373-377`、`:71-75` |
| 结果只有两种：`{kind:'success', text?, sourceEventSeq?}` / `{kind:'error', text}`（error 文本必须非空） | `:228-256` |
| handler 抛异常 ⇒ 仍落一条 `command/done{kind:'error'}`，**再**把异常抛给调用方 | `:426-429`、`:433-443` |
| `commandId` = `cmd-<实例令牌>-<自增序号>`（跨进程重启也不重号，便于在恢复的日志里配对） | `:445-449` |
| 描述符（`{name, description, input?{hint}}`）按名字排序，供 UI 发现 | `:314-320` |

## 本地偏差（有意，逐条登记）

1. **不做注册表的"层"**：上游建在 Cordis `ScopedLayers` 上（全局层 + 每 agent scope 链可遮蔽同名）。
   本地只有一个 agent（`main`）⇒ 塌成**单层扁平注册表**（同 `skills.py` 的口径）。
2. **不做附件**（`input.attachments` / 图片与文件上传回执）：本地 composer 没有附件通道
   ⇒ 该字段与 `admitCommandAttachments()` 整块不移植；命令也不接受附件。
3. **不做 `/` 自动补全弹层**：上游把它留给"capable clients"；本地只提供 `descriptors()` 与
   `agent_command_list` RPC（面板可自行做），本轮**未做**输入框补全 UI。
4. **挂点在 `ask()`**（`services/agent/ask.py`）：上游的 `execute()` 是宿主 Remote 方法、由客户端调用；
   本地没有独立的 agent 运行时对象，而 `ask()` 恰好**已经**把上下文（会话 / provider / system / 工具集 /
   历史）组装好了 ⇒ 在那里分流最省、也不会与主回合的组装漂移。返回仍走 `AskResult`
   （`stop_reason="command"`、`iterations=0`、`usage={}`），前端据 `stop_reason` 渲染成本地气泡。
5. **`sourceEventSeq` 字段保留但本地暂无生产者**（上游用于让客户端定位更丰富的领域事件）。
6. **内建两条命令**（上游把命令留给各插件注册；本地先给两个"前置已就位"的）：
   `/compact` —— 手动压缩（复用**同一个** `ask._compact_if_needed(force=True)`，不另写一份压缩逻辑）；
   `/permission <档位>` —— 切本次会话的审批档（复用 `permission_presets.set_preset()`）。
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "EVENT_DONE",
    "EVENT_RUN",
    "CommandContext",
    "CommandDefinition",
    "CommandExecution",
    "CommandInvocation",
    "CommandLine",
    "CommandRegistry",
    "CommandResult",
    "default_registry",
    "err",
    "handle_command_line",
    "ok",
    "parse_command",
]

#: 命令名语法（上游 `src/index.ts:32` 逐字）。
COMMAND_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
#: 整行解析（上游 `:126` 逐字：**前瞻**不消费分隔符 ⇒ `rawInput` 自带分隔空白）。
_COMMAND_LINE_RE = re.compile(r"^\/([a-z][a-z0-9_-]*)(?=$|[\t\n\r ])")

#: 生命周期事件类型（log-only：回放/压缩预算/语义抽取一律跳过未知 type，见 `audit.py` 的同款理由）。
EVENT_RUN = "command/run"
EVENT_DONE = "command/done"


@dataclass(frozen=True, slots=True)
class CommandLine:
    """解析成功的斜杠命令行（上游 `ParsedCommand`）。"""

    name: str
    """小写命令名，**不带**前导斜杠。"""
    raw_input: str
    """命令名之后的原文（**含**分隔空白；上游 `rawInput` 同口径）。"""


def parse_command(line: str) -> CommandLine | None:
    """把整行解析成 `CommandLine`；不是命令行 ⇒ `None`（**不做任何归一化**）。"""
    match = _COMMAND_LINE_RE.match(str(line or ""))
    if match is None:
        return None
    return CommandLine(name=match.group(1), raw_input=str(line)[match.end() :])


@dataclass(frozen=True, slots=True)
class CommandResult:
    """handler 的归一化结果（上游 `CommandResult` 两态）。"""

    kind: str
    """`"success"` 或 `"error"`。"""
    text: str = ""
    source_event_seq: int | None = None
    """更丰富的领域事件位置（上游 `sourceEventSeq`；本地暂无生产者）。"""


def ok(text: str = "") -> CommandResult:
    """成功结果（`text` 可选）。"""
    return CommandResult(kind="success", text=str(text or ""))


def err(text: str) -> CommandResult:
    """失败结果（`text` 必须非空 —— 上游对空 error 文本直接报错）。"""
    body = str(text or "")
    if not body.strip():
        raise ValueError("命令失败结果必须带非空文本")
    return CommandResult(kind="error", text=body)


@dataclass(frozen=True, slots=True)
class CommandContext:
    """命令执行上下文：**由 `ask()` 注入**（上游对应"`agent` 对象"）。

    命令拿到的就是 `ask()` 已组装好的那一份：同一个会话（事件落进同一份 JSONL）、同一个 provider /
    system / 工具集（所以 `/compact` 的摘要调用与自动压缩**逐字同参**，不会漂移）。
    """

    kb_path: str
    session: Any
    history: Any = None
    provider: Any = None
    system: str = ""
    tools: Sequence[Any] = ()
    model: str = ""
    timeout_s: float | None = None
    retry_policy: Any = None
    cancel: Any = None


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    """一次调用交给 handler 的东西（上游 `CommandInvocation`，去掉附件与 signal）。"""

    command_id: str
    raw_input: str
    context: CommandContext


CommandHandler = Callable[[CommandInvocation], CommandResult]


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    """一条命令的注册体（上游 `CommandDefinition`）。"""

    name: str
    description: str
    handler: CommandHandler
    input_hint: str = ""
    """可选输入提示（上游 `input.hint`）；空串 = 不收输入。"""
    record_input: bool = True
    """是否把 `raw_input` 记进 `command/run.args`（上游 `recordInput`，默认 true）。"""


@dataclass(frozen=True, slots=True)
class CommandExecution:
    """一次已结算的执行（上游 `CommandExecution`）。"""

    command_id: str
    result: CommandResult


@dataclass
class CommandRegistry:
    """**单层扁平**命令注册表（上游的 `ScopedLayers` 在本地塌成一层，见模块头偏差 1）。"""

    _commands: dict[str, CommandDefinition] = field(default_factory=dict)

    def register(self, definition: CommandDefinition) -> None:
        """注册一条命令；名字/描述/handler 不合法或重名 ⇒ `ValueError`（对齐上游注册期即拒）。"""
        name = str(definition.name or "")
        if not COMMAND_NAME_RE.match(name):
            raise ValueError(f"命令名非法：{name!r}（须匹配 {COMMAND_NAME_RE.pattern}）")
        if not str(definition.description or "").strip():
            raise ValueError(f"命令 {name} 的 description 不能为空")
        if not callable(definition.handler):
            raise ValueError(f"命令 {name} 的 handler 必须可调用")
        if name in self._commands:
            raise ValueError(f"命令 {name} 已注册")
        self._commands[name] = definition

    def find(self, name: str) -> CommandDefinition | None:
        """按名取定义（未知名 ⇒ `None`）。"""
        return self._commands.get(str(name or ""))

    def descriptors(self) -> list[dict[str, Any]]:
        """按名字排序的**可展示描述符**（上游 `list()`：给 UI 发现用，不含 handler）。"""
        rows: list[dict[str, Any]] = []
        for name in sorted(self._commands):
            definition = self._commands[name]
            row: dict[str, Any] = {"name": name, "description": definition.description}
            if definition.input_hint:
                row["input"] = {"hint": definition.input_hint}
            rows.append(row)
        return rows


#: 命令 id 的实例令牌：同一进程内自增、跨进程重启也不重号（上游 `instanceToken` 同款用途）。
_INSTANCE_TOKEN = uuid.uuid4().hex[:8]
_SEQ = {"n": 0}


def _mint_command_id() -> str:
    """生成下一个 `commandId`（上游 `mintCommandId()`：`cmd-<实例令牌>-<序号>`）。"""
    _SEQ["n"] += 1
    return f"cmd-{_INSTANCE_TOKEN}-{_SEQ['n']}"


def _append_lifecycle(session: Any, event_type: str, payload: Mapping[str, Any]) -> None:
    """追加一条 log-only 生命周期事件；**不抛**（记 warning）—— 审计不该把命令本身搞挂。"""
    try:
        session.append(event_type, dict(payload))
    except Exception:  # noqa: BLE001 —— 会话盘不可写时命令仍应能跑完（与 audit 的 fail-open 同口径）
        logger.warning("[agent-command] %s 落盘失败（命令继续）", event_type, exc_info=True)


def execute(registry: CommandRegistry, context: CommandContext, line: str) -> CommandExecution | None:
    """解析并执行一行命令（上游 `execute()`）。

    **未注册的名字 ⇒ `None`**（不落任何事件、不报错 —— 调用方据此把该行当普通文本）。
    handler 抛异常 ⇒ 先落 `command/done{kind:'error'}`，**再**抛出（上游同序）。
    """
    parsed = parse_command(line)
    if parsed is None:
        return None
    definition = registry.find(parsed.name)
    if definition is None:
        return None
    command_id = _mint_command_id()
    payload: dict[str, Any] = {"commandId": command_id, "name": parsed.name, "source": {"kind": "user"}}
    if definition.record_input:
        payload["args"] = parsed.raw_input
    _append_lifecycle(context.session, EVENT_RUN, payload)

    invocation = CommandInvocation(command_id=command_id, raw_input=parsed.raw_input, context=context)
    try:
        result = definition.handler(invocation)
    except Exception as exc:  # noqa: BLE001 —— 先配对落 done，再把异常交回调用方（上游同序）
        _append_lifecycle(
            context.session, EVENT_DONE, {"commandId": command_id, "kind": "error", "text": str(exc)}
        )
        raise
    if not isinstance(result, CommandResult):
        result = err(f"命令 {parsed.name} 的 handler 没有返回 CommandResult")
    done: dict[str, Any] = {"commandId": command_id, "kind": result.kind}
    if result.text:
        done["text"] = result.text
    if result.kind == "success" and result.source_event_seq is not None:
        done["sourceEventSeq"] = result.source_event_seq
    _append_lifecycle(context.session, EVENT_DONE, done)
    return CommandExecution(command_id=command_id, result=result)


# ── 内建命令（本地新增，见模块头偏差 6）──────────────────────────────────────────────


def _compact_handler(invocation: CommandInvocation) -> CommandResult:
    """`/compact`：**手动**触发压缩（`force=True` 只跳过阈值判断，压缩逻辑与自动路径**同一份**）。"""
    context = invocation.context
    if context.history is None:
        return err("这个会话还没有历史可压（先聊几轮再试）。")
    from memoria.services.agent.ask import _compact_if_needed  # 延迟导入：避开模块级循环

    try:
        changed = _compact_if_needed(
            context.kb_path,
            context.session,
            history=context.history,
            provider=context.provider,
            system=context.system,
            tools=list(context.tools),
            model=context.model,
            timeout_s=context.timeout_s,
            retry_policy=context.retry_policy,
            cancel=context.cancel,
            force=True,
        )
    except Exception as exc:  # noqa: BLE001 —— 压缩失败如实回报，不假装成功
        return err(f"压缩失败：{exc}")
    if not changed:
        return ok("没有可压的区间（这段历史还选不出成对的切割点）。")
    return ok("已压缩：旧对话已摘成 checkpoint，之后的请求按摘要视图走（原始事件仍在会话记录里）。")


def _permission_handler(invocation: CommandInvocation) -> CommandResult:
    """`/permission <档位>`：切**本次会话**的审批档（复用 `permission_presets.set_preset()`）。"""
    from memoria.services.agent import permission_presets as pp  # 延迟导入：与本模块无循环

    raw = invocation.raw_input.strip()
    name = raw.split()[0].lower() if raw else ""
    choices = "、".join(f"`{item}`" for item in pp.PRESET_NAMES)
    if not name:
        return err(f"用法：`/permission <档位>`；可选：{choices}")
    if name not in pp.PRESETS:
        return err(f"未知档位：`{name}`；可选：{choices}")
    try:
        pp.set_preset(invocation.context.session, name)
    except Exception as exc:  # noqa: BLE001 —— 落盘失败如实回报
        return err(f"切换失败：{exc}")
    spec = pp.PRESETS[name]
    return ok(f"本次会话的审批档已切到「{spec.name}」——{spec.description}")


def default_registry() -> CommandRegistry:
    """本地内建命令集（`/compact` + `/permission`）。"""
    registry = CommandRegistry()
    registry.register(
        CommandDefinition(
            name="compact",
            description="把旧对话压成 checkpoint（与自动压缩同一套逻辑，只是不等到阈值）。",
            handler=_compact_handler,
        )
    )
    registry.register(
        CommandDefinition(
            name="permission",
            description="切换本次会话的审批档（写入前要不要逐条问你）。",
            handler=_permission_handler,
            input_hint="<档位>",
        )
    )
    return registry


def handle_command_line(
    kb_path: str,
    session: Any,
    line: str,
    *,
    history: Any = None,
    provider: Any = None,
    system: str = "",
    tools: Sequence[Any] = (),
    model: str = "",
    timeout_s: float | None = None,
    retry_policy: Any = None,
    cancel: Any = None,
    registry: CommandRegistry | None = None,
) -> Any:
    """`ask()` 的挂点：命中命令 ⇒ 执行并回 `AskResult`（`stop_reason="command"`）；否则 `None`。

    回 `None` 的两种情形都要**原样放行**给模型：① 不是命令行；② 是命令行但名字**没注册**
    （上游口径：未命中不落事件、不报错）。
    """
    active = registry if registry is not None else default_registry()
    context = CommandContext(
        kb_path=kb_path,
        session=session,
        history=history,
        provider=provider,
        system=system,
        tools=tuple(tools or ()),
        model=model,
        timeout_s=timeout_s,
        retry_policy=retry_policy,
        cancel=cancel,
    )
    execution = execute(active, context, line)
    if execution is None:
        return None
    try:
        session.flush()  # 命令是"即时可见"的：不等后续 checkpoint（同 audit.append 的屏障）
    except Exception:  # noqa: BLE001
        pass
    from memoria.services.agent.ask import AskResult  # 延迟导入：避开模块级循环

    return AskResult(
        answer=execution.result.text,
        anchors=(),
        tool_calls=(),
        usage={},
        session_id=str(getattr(session, "session_id", "") or ""),
        session_path=str(getattr(session, "path", "") or ""),
        stop_reason="command",
        iterations=0,
        error=execution.result.text if execution.result.kind == "error" else None,
    )
