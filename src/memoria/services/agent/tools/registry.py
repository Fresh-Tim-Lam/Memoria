# 语义移植自 deepseek-harness packages/core/tools（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""工具注册表：schema 投影、参数校验与调用语义。

对应上游 `dsh-tools` 的核心约定（不含 PTC mode、Host 展示与并行调度）：

- **注册即发布**：注册进注册表的工具，其 schema 会随每次模型请求一起发出
  （`schemas()` → `LlmRequest.tools`）；
- **参数在执行前校验**：模型参数先过 JSON Schema 子集校验，无效输入变成
  **普通错误结果**（`Error: …`），绝不抛异常结束轮次；
- **失败也是结果**：未知工具（`UNKNOWN_TOOL`）、参数非法（`INVALID_ARGUMENTS`）、
  审批拒绝（`DENIED`）、工具体抛异常（`TOOL_FAILED`）都转成带稳定 code 的
  工具结果文本，循环据此继续下一步；
- **审批在分发前**：`invoke()` 在调用工具体之前向审批策略询问；策略不可用
  或拒绝即拒绝（fail-closed，见 `approvals.py`）。

本模块不联网、不打印；导入时不导入任何知识库服务（工具体自带惰性导入）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from memoria.services.agent.llm.types import ToolCall, ToolSchema

if TYPE_CHECKING:  # 仅类型引用：运行期不导入审批模块，避免与 approvals 形成环
    from memoria.services.agent.approvals import ApprovalPolicy

logger = logging.getLogger(__name__)

__all__ = [
    "DENIED_CODE",
    "INVALID_ARGUMENTS_CODE",
    "TOOL_FAILED_CODE",
    "UNKNOWN_TOOL_CODE",
    "Tool",
    "ToolOutput",
    "ToolRegistry",
    "ToolResult",
    "error_text",
    "parse_arguments",
    "validate_arguments",
]

#: 稳定错误 code（对齐上游结构化错误词汇；文本前缀恒为 `Error: `）。
UNKNOWN_TOOL_CODE = "UNKNOWN_TOOL"
INVALID_ARGUMENTS_CODE = "INVALID_ARGUMENTS"
TOOL_FAILED_CODE = "TOOL_FAILED"
DENIED_CODE = "DENIED"

#: 模型可见结果的错误前缀；上游约定所有失败调用都归一到该前缀。
ERROR_PREFIX = "Error: "


def error_text(message: str, code: str) -> str:
    """构造模型可见的错误文本：`Error: <message> (<CODE>)`。"""
    return f"{ERROR_PREFIX}{message} ({code})"


@dataclass(frozen=True, slots=True)
class ToolOutput:
    """一次工具执行的产出：面向模型的文本 + 结构化锚点。

    `anchors` 是 `{file, line, …}` 形式的来源锚点，供上层汇总成回答的
    `文件:行号` 引用；`text` 是回填给模型的唯一内容（上游把工具结果投影为
    文本块，此处保持一致）。
    """

    text: str
    error: bool = False
    code: str | None = None
    anchors: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class ToolResult:
    """一次工具调用的最终结果（模型可见内容 + 归属信息）。"""

    call_id: str
    name: str
    output: ToolOutput

    @property
    def content(self) -> str:
        """回填给模型的消息内容。"""
        return self.output.text

    @property
    def is_error(self) -> bool:
        return self.output.error


ToolHandler = Callable[[Mapping[str, Any]], ToolOutput]


@dataclass(frozen=True, slots=True)
class Tool:
    """一个工具定义：模型可见的声明 + 本地执行体。

    `read_only=True` 表示该工具不改动知识库；审批策略据此免审批
    （见 `approvals.DefaultApprovalPolicy`）。M1 阶段所有工具都是只读的。
    """

    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: ToolHandler
    read_only: bool = True

    def schema(self) -> ToolSchema:
        """投影为发给模型的工具声明。"""
        return ToolSchema(name=self.name, description=self.description, parameters=self.parameters)


def parse_arguments(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """解析模型给出的工具参数；返回 `(参数, 错误)`，二者恰有一个非 None。"""
    text = (raw or "").strip()
    if not text:
        return {}, None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"arguments 不是合法 JSON：{exc.msg}"
    if not isinstance(value, dict):
        return None, "arguments 必须是 JSON 对象"
    return value, None


_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _validate_value(value: Any, schema: Mapping[str, Any], path: str, errors: list[str]) -> None:
    type_name = schema.get("type")
    if isinstance(type_name, str) and type_name in _TYPE_CHECKS:
        if not _TYPE_CHECKS[type_name](value):
            errors.append(f"{path} 类型应为 {type_name}")
            return
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path} 取值必须是 {enum!r} 之一")

    if type_name == "object" and isinstance(value, dict):
        properties = schema.get("properties") or {}
        for key in schema.get("required") or []:
            if key not in value:
                errors.append(f"缺少必填参数 {path}.{key}")
        for key, item in value.items():
            child = properties.get(key)
            if isinstance(child, Mapping):
                _validate_value(item, child, f"{path}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"不接受的参数 {path}.{key}")
    elif type_name == "array" and isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                _validate_value(item, items, f"{path}[{index}]", errors)
    elif type_name in ("integer", "number") and isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum, maximum = schema.get("minimum"), schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path} 不得小于 {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{path} 不得大于 {maximum}")
    elif type_name == "string" and isinstance(value, str):
        min_length, max_length = schema.get("minLength"), schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{path} 长度不得小于 {min_length}")
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append(f"{path} 长度不得大于 {max_length}")


def validate_arguments(schema: Mapping[str, Any], arguments: Mapping[str, Any]) -> list[str]:
    """按 JSON Schema 子集校验参数；返回问题清单（空表示通过）。

    支持的子集：`type`（object/array/string/integer/number/boolean/null）、
    `properties` / `required` / `additionalProperties: false`、`items`、
    `enum`、数值边界与字符串长度。与上游一致：不认识的约束被忽略，
    不因工具作者写了扩展关键字而拒绝调用。
    """
    errors: list[str] = []
    _validate_value(arguments, schema, "参数", errors)
    return errors


class ToolRegistry:
    """工具集合：按名解析、投影 schema、执行调用并归一错误。"""

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        """注册工具；重名直接报错（上游注册表同样拒绝重复定义）。"""
        key = (tool.name or "").strip()
        if not key:
            raise ValueError("工具名不能为空")
        if key in self._tools:
            raise ValueError(f"工具 {key!r} 已注册")
        self._tools[key] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get((name or "").strip())

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def schemas(self) -> tuple[ToolSchema, ...]:
        """当前可见工具声明（顺序即注册顺序）。"""
        return tuple(tool.schema() for tool in self._tools.values())

    def invoke(self, call: ToolCall, *, approval: "ApprovalPolicy | None" = None) -> ToolResult:
        """执行一次工具调用；任何失败都转成带错误文本的结果。

        `approval` 省略时视为「无需审批」（测试与内部调用）；生产入口
        （`ask.py`）总会传入默认策略。
        """
        tool = self.get(call.name)
        if tool is None:
            return ToolResult(
                call.id,
                call.name,
                ToolOutput(text=error_text(f"未注册的工具 {call.name!r}", UNKNOWN_TOOL_CODE), error=True, code=UNKNOWN_TOOL_CODE),
            )

        arguments, parse_error = parse_arguments(call.arguments)
        if parse_error is not None or arguments is None:
            return ToolResult(
                call.id,
                tool.name,
                ToolOutput(
                    text=error_text(f"{tool.name}: {parse_error}", INVALID_ARGUMENTS_CODE),
                    error=True,
                    code=INVALID_ARGUMENTS_CODE,
                ),
            )

        problems = validate_arguments(tool.parameters, arguments)
        if problems:
            detail = "；".join(problems)
            return ToolResult(
                call.id,
                tool.name,
                ToolOutput(
                    text=error_text(f"{tool.name}: 参数非法 —— {detail}", INVALID_ARGUMENTS_CODE),
                    error=True,
                    code=INVALID_ARGUMENTS_CODE,
                ),
            )

        if approval is not None:
            from memoria.services.agent.approvals import ApprovalRequest

            decision = approval.decide(
                ApprovalRequest(
                    tool=tool.name,
                    call_id=call.id,
                    arguments=arguments,
                    read_only=tool.read_only,
                )
            )
            if not decision.allowed:
                return ToolResult(
                    call.id,
                    tool.name,
                    ToolOutput(
                        text=error_text(
                            f"{tool.name}: 调用被拒绝（{decision.outcome.value}）—— {decision.reason}".rstrip(" ——"),
                            DENIED_CODE,
                        ),
                        error=True,
                        code=DENIED_CODE,
                    ),
                )

        try:
            output = tool.handler(arguments)
        except Exception as exc:  # noqa: BLE001 — 工具体失败一律降级为错误结果，不结束轮次
            logger.warning("[agent-tools] 工具 %s 执行失败：%r", tool.name, exc)
            return ToolResult(
                call.id,
                tool.name,
                ToolOutput(
                    text=error_text(f"{tool.name}: 执行失败（{type(exc).__name__}）—— {exc}", TOOL_FAILED_CODE),
                    error=True,
                    code=TOOL_FAILED_CODE,
                ),
            )
        if not isinstance(output, ToolOutput):
            output = ToolOutput(text=str(output))
        return ToolResult(call.id, tool.name, output)
