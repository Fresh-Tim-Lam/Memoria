# 语义移植自 deepseek-harness packages/core/system-prompt 与 packages/context/agent-instructions（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""system prompt 组装：基础指令 + 知识库上下文 + 工具清单。

对照上游两处语义：

1. `dsh-system-prompt`：提示词是**有序段落的组装结果**，工具 schema 属于同一份
   组装产物（"模型获知自己能做什么"是一个整体）。本地按
   「基础身份 → 运行环境 → 知识库指令文件 → 可用工具 → 回答要求」的固定顺序拼接，
   工具段落由 `ToolSchema` 生成，工具集合为空时不产生该段（空段消失）。
2. `dsh-agent-instructions`：把工作区指令文件（`AGENTS.md` 兼容）作为**注入的
   上下文**送达模型——**只加上下文、不加工具**。本地读取知识库内的
   `.memoria/agent/{kb-spec.zh-CN.md, preview-formats.md, prompt.zh-CN.md}`
   （事实源仍是这些文件本身，本模块只负责"发现并注入"，不另立副本）。

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
    "INSTRUCTION_FILENAMES",
    "InstructionSource",
    "build_system_prompt",
    "instruction_dir",
    "load_instructions",
    "prompt_debug_info",
    "render_instructions",
]

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
                "用户消息里的 `@相对路径` 表示他明确圈定了某个库内文件（目录以 `/` 结尾）；"
                "这类引用应优先用 `read_document` 读取该文件后再回答，不要忽略。",
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
