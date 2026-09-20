# 语义移植自 deepseek-harness packages/core/system-prompt + packages/context/agent-instructions
# + packages/context/file-reference + packages/context/time-context（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""system prompt 组装：基础指令 + 知识库上下文 + 工具清单。

对照上游四处语义：

1. `dsh-system-prompt`：提示词是**有序段落的组装结果**，工具 schema 属于同一份
   组装产物（"模型获知自己能做什么"是一个整体）。本地按
   「基础身份 → 运行环境 → 知识库指令文件 → 可用工具 → 用户引用（`@路径`）→ 时间上下文 → 回答要求」
   的固定顺序拼接，工具段落由 `ToolSchema` 生成，工具集合为空时不产生该段（空段消失）。
2. `dsh-agent-instructions`：把工作区指令文件（`AGENTS.md` 兼容）作为**注入的
   上下文**送达模型——**只加上下文、不加工具**。本地读取知识库内的
   `.memoria/agent/{kb-spec.zh-CN.md, preview-formats.md, prompt.zh-CN.md}`
   （事实源仍是这些文件本身，本模块只负责"发现并注入"，不另立副本）。
3. `dsh-file-reference`：`@` 前缀 token 是用户**显式引用**的工作区路径，需要一份固定的
   模型可见说明（见 `FILE_REFERENCE_SECTION`）：上游做成**独立段落**并按「`read` 工具是否
   在场」门控，本地同构（上游另一半是编辑器补全服务 `file-reference-local`，本前端不用）。
4. `dsh-time-context`：上游按步骤注入「时间戳 + 浏览器时区策略 + 经过时长」读数；本地留**策略
   段**（`TIME_CONTEXT_SECTION`）与**时间戳读数**（`render_time_context()`），偏差见两处注释。

与上游的差异（已登记）：
- 上游把指令作为**持久 user 角色消息**写入会话日志（可回放、可压缩）；M1 直接
  拼进 system 段（无语义差，但不进入会话消息序列）；
- 上游跟随 `read`/`write`/`edit` 工具触发的嵌套目录发现；M1 只有库级指令文件；
- 上游按「宽泛先省略、最具体最后截断」处理字节预算；本地候选按
  kb-spec → preview-formats → prompt 顺序（宽泛在前），预算不足时先省略靠前的
  整文件，最后一个可截断；
- 上游注入的框架文本里的字面 `</system-reminder>` 会被转义；本地同样转义。

导入本模块不读文件；只有显式调用 `load_instructions` / `build_system_prompt`
才会读知识库（只读）。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from memoria.services.agent.llm.types import ToolSchema

logger = logging.getLogger(__name__)

__all__ = [
    "AGENT_DIR",
    "DEFAULT_MAX_INSTRUCTION_BYTES",
    "DEFAULT_MAX_SOURCE_BYTES",
    "FILE_REFERENCE_SECTION",
    "INSTRUCTION_FILENAMES",
    "InstructionSource",
    "build_system_prompt",
    "instruction_dir",
    "load_instructions",
    "prompt_debug_info",
    "render_instructions", "TIME_CONTEXT_SECTION", "format_time_context", "render_time_context",
    "MODEL_CHANGE_NOTICE", "render_model_change_notice", "FILE_REFERENCE_TOOLS"]

#: 知识库内指令文件所在目录（相对库根）。
AGENT_DIR = (".memoria", "agent")
#: 指令文件候选（顺序 = 从宽泛到具体；对齐上游 `instructionFileCandidates` 的角色）。
INSTRUCTION_FILENAMES = ("kb-spec.zh-CN.md", "preview-formats.md", "prompt.zh-CN.md")
#: 渲染后注入上限（字节）；上游 `dsh-base` 对同一参数的默认值即 65536。
DEFAULT_MAX_INSTRUCTION_BYTES = 65_536
#: 单个源文件上限（字节），对齐上游 `maxSourceBytes` 默认值。
DEFAULT_MAX_SOURCE_BYTES = 1_048_576

_REMINDER_OPEN = "<system-reminder>"
_REMINDER_CLOSE = "</system-reminder>"


@dataclass(frozen=True, slots=True)
class InstructionSource:
    """一份被加载的指令文件（或一次预算裁剪的结果）。"""

    name: str
    path: str
    text: str
    truncated: bool = False
    omitted: bool = False


def instruction_dir(kb_path: str) -> str:
    """知识库的指令文件目录绝对路径。"""
    return os.path.join(os.path.abspath(kb_path), *AGENT_DIR)


def _escape_fence(text: str) -> str:
    """转义指令内容里的框架结束标签，避免库内文本关闭本模块控制的框架。"""
    return text.replace(_REMINDER_CLOSE, "<\\/system-reminder>")


def load_instructions(
    kb_path: str,
    *,
    filenames: Sequence[str] = INSTRUCTION_FILENAMES,
    max_bytes: int = DEFAULT_MAX_INSTRUCTION_BYTES,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> tuple[InstructionSource, ...]:
    """读取知识库指令文件链；不存在/超单文件上限的候选被跳过。

    预算规则（对齐上游语义）：从**最宽泛**的候选开始整份省略，直到剩余内容能装进
    `max_bytes`；仍超预算时只截断**最后一个**（最具体）文件。返回的列表按原始
    顺序（宽泛 → 具体），被省略项带 `omitted=True` 且 `text=""`（便于诊断）。
    """
    directory = instruction_dir(kb_path)
    loaded: list[InstructionSource] = []
    for name in filenames:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as handle:
                raw = handle.read(max_source_bytes + 1)
        except OSError as exc:  # 权限/IO 失败：跳过该候选并记录（不阻断提问）
            logger.warning("[agent-prompt] 指令文件不可读，已跳过：%s（%r）", path, exc)
            continue
        if len(raw) > max_source_bytes:
            logger.warning("[agent-prompt] 指令文件超过单文件上限，已跳过：%s", path)
            continue
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            logger.warning("[agent-prompt] 指令文件不是 UTF-8，已跳过：%s（%r）", path, exc)
            continue
        if not text:
            continue
        loaded.append(InstructionSource(name=name, path=path, text=_escape_fence(text)))

    budget = max(0, int(max_bytes))
    kept = list(loaded)
    total = sum(len(source.text.encode("utf-8")) for source in kept)
    omitted: list[InstructionSource] = []
    while len(kept) > 1 and total > budget:
        dropped = kept.pop(0)
        total -= len(dropped.text.encode("utf-8"))
        omitted.append(InstructionSource(name=dropped.name, path=dropped.path, text="", omitted=True))
        logger.warning("[agent-prompt] 指令预算不足，已省略较宽泛的指令文件：%s", dropped.path)
    if kept:
        last = kept[-1]
        encoded = last.text.encode("utf-8")
        if len(encoded) > budget:
            raw_text = encoded[:budget]
            text = raw_text.decode("utf-8", errors="ignore")
            kept[-1] = InstructionSource(name=last.name, path=last.path, text=text, truncated=True)
            logger.warning("[agent-prompt] 最具体的指令文件被截断到预算上限：%s", last.path)

    ordered = sorted([*kept, *omitted], key=lambda source: list(filenames).index(source.name))
    return tuple(ordered)


def render_instructions(
    sources: Sequence[InstructionSource],
    *,
    kb_path: str | None = None,
) -> str:
    """把指令文件渲染成注入上下文的文本（框架文本对齐上游基线模板）。"""
    present = [source for source in sources if source.text]
    if not present:
        return ""
    header = (
        f"{_REMINDER_OPEN}\n"
        "以下知识库指令可能与你当前的工作相关，请在适用时作为指引。"
        "更具体的指令优先于更宽泛的指令；它们不覆盖系统、开发者或用户的直接指令。\n"
    )
    if kb_path:
        header += f"\n知识库根：{os.path.abspath(kb_path)}\n"
    blocks: list[str] = []
    for source in present:
        suffix = "（已按预算截断）" if source.truncated else ""
        blocks.append(f"\nInstructions from: {source.name}{suffix}\n\n{source.text}\n")
    return header + "".join(blocks) + _REMINDER_CLOSE


def _render_tools(tools: Sequence[ToolSchema]) -> str:
    if not tools:
        return ""
    rows = [f"- `{tool.name}`：{tool.description}" for tool in tools]
    return "\n".join(
        [
            "## 可用工具",
            "",
            *rows,
            "",
            "工具结果是唯一的事实来源：不确定的内容先用工具查证，不要凭记忆编造库内内容。",
        ]
    )


#: `@路径` 引用的模型可见说明。语义移植自上游 `context/file-reference` 的
#: `FILE_REFERENCE_PROMPT`（`packages/context/file-reference/src/index.ts:17`，pin `0d1f5000`）原文：
#:
#:   Tokens prefixed with @ are workspace paths the user explicitly referenced, relative to the
#:   workspace root. A trailing slash marks a directory: list it when its contents matter.
#:   Anything else is a file: use the read tool when its contents are needed, and do not claim to
#:   have inspected it before reading. @"..." quotes a path containing spaces.
#:
#: 逐条落为中文（与本文其余段落语言一致），四层语义一条不少：**明确引用** / 尾斜杠＝目录 /
#: 否则是文件且"读过之前不得声称看过" / `@"..."` 表示含空格。
#:
#: 门控对齐上游（`ctx.tools.get('read') === undefined ? '' : FILE_REFERENCE_PROMPT`）：
#: **任一读取工具在场即注入**（`read_document` / `glob` / `grep` / `read_image`，名单见文件末尾）—— 模型没有读取手段时，教它"去读"没有意义。
#: 语义偏差：上游目录一条是 "list it"（它有列目录工具），本地无列目录工具，故改指 `search_kb` 与 `glob`（后者即本地"按模式列文件"的手段）。
FILE_REFERENCE_SECTION = "\n".join(
    [
        "## 用户引用（`@路径`）",
        "",
        "用户消息里以 `@` 开头的 token 是他**明确圈定**的库内路径（相对知识库根）：",
        "",
        "1. 结尾带 `/` 表示**目录**：只在其内容确实相关时才去检索（`search_kb`），不要臆测目录内容；",
        "2. 其余表示**文件**：需要其内容时用 `read_document` 读取；**在真正读过之前，不得声称已经看过**；",
        '3. `@"..."` 表示路径中含空格，例如 `@"docs/IELTS vocab.md"`。',
    ]
)


def _has_tool(tools: Sequence[ToolSchema], name: str) -> bool:
    return any((tool.name or "") == name for tool in tools)


def build_system_prompt(
    kb_path: str,
    *,
    tools: Sequence[ToolSchema] = (),
    model: str = "",
    extra_sections: Sequence[str] = (),
    max_instruction_bytes: int = DEFAULT_MAX_INSTRUCTION_BYTES,
) -> str:
    """组装完整的 system prompt（段落顺序固定，空段消失）。"""
    sections: list[str] = [
        "\n".join(
            [
                "你是 Memoria 的本地知识库助手：面向当前打开的知识库回答用户的问题。",
                "你的知识来源只有两处：本地知识库内容（通过工具读取）与用户在本轮对话中给出的信息。",
                "当前能力是**只读**的：你可以检索与阅读知识库，但不能修改、创建或删除任何文件；",
                "如果用户要求写入，请明确说明本阶段不支持写入，并给出建议的改动清单。",
            ]
        ),
        "\n".join(
            [
                "## 运行环境",
                "",
                f"- 知识库根目录：{os.path.abspath(kb_path)}",
                f"- 模型：{model or '（未指定）'}",
            ]
        ),
    ]

    instructions = render_instructions(load_instructions(kb_path, max_bytes=max_instruction_bytes), kb_path=kb_path)
    if instructions:
        sections.append(instructions)

    tool_section = _render_tools(tools)
    if tool_section:
        sections.append(tool_section)

    if _has_read_tool(tools):  # `@路径` 说明：门控同上游「任一读取手段在场」（见 FILE_REFERENCE_SECTION）
        sections.append(FILE_REFERENCE_SECTION)
    sections.append(TIME_CONTEXT_SECTION)  # 时间上下文：对应上游「插件被挂载」，不按工具门控

    sections.append(
        "\n".join(
            [
                "## 回答要求",
                "",
                "1. 回答库内问题时，引用来源一律写成 `文件相对路径:行号`（例如 `neural-network.md:17`）；"
                "行号取工具结果给出的锚点，不要自行估算。",
                "2. 工具没有命中时，直接说明「知识库中没有找到相关内容」，不要编造知识点或出处。",
                "3. 用中文回答，先给结论，再给依据（引用锚点）。",
                "4. 不要输出工具调用过程的原始 JSON；只输出给用户看的答案。",
            ]
        )
    )

    for extra in extra_sections:
        if extra and extra.strip():
            sections.append(extra.strip())

    return "\n\n".join(section for section in sections if section.strip())


def prompt_debug_info(sources: Sequence[InstructionSource]) -> Mapping[str, Any]:
    """指令加载摘要（供 CLI/测试核对，不进入 prompt）。"""
    return {
        "loaded": [source.name for source in sources if source.text],
        "truncated": [source.name for source in sources if source.truncated],
        "omitted": [source.name for source in sources if source.omitted],
    }


#: 时间上下文的**固定**模型可见说明。语义移植自上游 `context/time-context` 的
#: `renderBrowserTimeZoneContext()`（`packages/context/time-context/src/request-zone.ts:66-80`，pin `0d1f5000`）原文：
#:
#:   Browser time zone for this request: <iana-zone>. Interpret otherwise-unqualified dates and times in this zone.
#:   Browser time zone for this request: mixed [...]. Ask the user to clarify otherwise-unqualified dates and times.
#:   Browser time zone for this request: unavailable. Ask the user to clarify otherwise-unqualified dates and times.
#:
#: 另见该包 README「仅限提示词来源信息」：这份上下文只指导自然语言解释，不会悄然填入另一工具所要求的时区字段。
#:
#: 上游把三态逐次写进**每条**读数（读数首行是时间戳、第二行才是这段策略）；本地没有「浏览器时区」这条通道
#: （宿主就是本机、时区唯一、也不会缺）⇒ 三态收敛为**一条固定说明**，动态的那一半（时间戳本体）见
#: `render_time_context()`。**静态说明进 system 段、动态读数进本轮请求末尾**：这样读数变化只追加在可复用
#: 前缀之后，不会让整段 system 每轮失效（对齐上游 README「KV Cache 影响：仅追加」）。
#: 门控：上游按「插件被挂载」启停（**不**按工具门控，与 `FILE_REFERENCE_SECTION` 不同）；本地对应
#: 「agent 功能已启用」—— 即 `build_system_prompt()` 被调用，"挂载"已经发生，故**无条件注入**。
TIME_CONTEXT_SECTION = "\n".join(
    [
        "## 时间上下文",
        "",
        "宿主会在本轮请求末尾给出一条本机时钟读数，形如 `2026-09-20T09:37:33+08:00`（含数字偏移）：",
        "",
        "1. 用户**未限定**时区的日期与时间，按该读数所在时区解释；",
        "2. 该读数**只**用于指导自然语言解释，**不要**替用户或工具参数假定时区；",
        "3. 读数缺失、或与用户明说的时区相冲突时，**先向用户澄清**，不要猜一个时区。",
    ]
)


def _local_now() -> datetime.datetime:
    """采样一次本机时钟（本模块**唯一**的时钟读取点；单测 monkeypatch 它来冻结时间）。

    局部导入：模块顶层 import 段被 `<文件>:<行号>` 锚点占用，本轮不动（见 §6.14）。
    """
    import datetime

    return datetime.datetime.now().astimezone()


def format_time_context(now: datetime.datetime) -> str:
    """把本机时刻渲染成上游 `formatTimestamp()` 的字段口径：`YYYY-MM-DDTHH:MM:SS±HH:MM`。

    上游（`src/timestamp.ts:10-36`）用 `Intl.DateTimeFormat('en-US', {hourCycle: 'h23',
    timeZoneName: 'longOffset'})` 产出同样的数字字段，末尾另附 `[IANA 时区名]`；本地**省略该括注**
    （标准库无法从 OS 可靠取到 IANA 名，且不引新依赖），数字偏移逐位一致 ⇒ 时区仍可解释。
    """
    if now.tzinfo is None:
        now = now.astimezone()
    offset = now.strftime("%z")
    colonized = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}{colonized}"


def render_time_context(now: datetime.datetime | None = None) -> str:
    """本轮请求末尾的时间读数（上游 `renderText()` 的本地落法，省略其 turn/step 与经过时长）。

    调用点是 `ask()`：在 `loop.run()` 之前追加到本轮请求文本末尾（与跨会话引用快照同位置），
    **不进 system 段**（KV 前缀理由见 `TIME_CONTEXT_SECTION` 注释），也**不落盘** ——
    会话 JSONL 里仍是用户输入的原文（与 §6.12 偏差 1 同口径）。
    """
    moment = _local_now() if now is None else now
    return f"当前本地时间：{format_time_context(moment)}"


# ── 模型切换告知（2026-09-20；`core/agent` 的 model-selection，见 §6.15）──────────
# 语义移植自上游 `packages/core/agent/src/model-selection.ts:41-56` 的 `modelSwitchNotice()`，
# 上游英文原文（逐字）：
#
#   [model changed: assistant turns above this point were generated by {from}; the session continues with {to}]
#
# 上游按 `routeLabel()` 标注模型：provider 相同只写 model，否则写 `provider/model`；
# 本地只有一个端点、没有 provider 概念 ⇒ 标签就是模型名（偏差见 §6.15）。
# 上游把它作为**一条 user 角色消息**追加进下一次请求并持久化；本地没有"插件消息"通道，
# 按 §6.14 同口径只加进**本轮请求文本**（不落盘、不改消息条数）。
MODEL_CHANGE_NOTICE = "[模型已更换：本轮之前的助手回复由 {previous} 生成；本会话此后由 {current} 继续]"


def render_model_change_notice(previous: str, current: str) -> str:
    """模型切换告知（`""` = 不追加）。

    只在**两边都非空且不相等**时产出：`previous` 取会话里**最后一条 `loop/end.model`**
    （旧版本落盘的老会话没有该字段 ⇒ 空串 ⇒ 不告知，见 §6.15 偏差 3）。
    调用点同样是 `ask()`：插在本轮请求文本之后、时间读数之前，**不进 system 段、不落盘**。
    """
    before = (previous or "").strip()
    after = (current or "").strip()
    if not before or not after or before == after:
        return ""
    return MODEL_CHANGE_NOTICE.format(previous=before, current=after)


# ── `@路径` 段的门控名单（2026-09-20；上游读面移植，见 dsh-agent-port.md §6.16）──────────
# 定义在文件末尾：`build_system_prompt()` 在**调用期**取用，故顶层 import 段与其上方
# `<文件>:<行号>` 锚点零漂移（同 §6.14 的 `_local_now()` 局部导入同款取舍）。
#: 任一在场即注入 `FILE_REFERENCE_SECTION`（上游口径 = `read` 工具在场；本地读取手段有四个）。
FILE_REFERENCE_TOOLS = ("read_document", "glob", "grep", "read_image")


def _has_read_tool(tools: Sequence[ToolSchema]) -> bool:
    """`@路径` 段的门控：工具集里**只要有一个读取手段**就注入说明。"""
    return any(_has_tool(tools, name) for name in FILE_REFERENCE_TOOLS)
