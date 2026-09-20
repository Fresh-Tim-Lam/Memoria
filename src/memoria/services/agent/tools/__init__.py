# 语义移植自 deepseek-harness packages/core/tools（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""Agent 工具面（dsh 移植 M1 第二块）。

| 模块 | 上游 | 职责 |
|---|---|---|
| `registry.py` | `core/tools/src/{types,json-schema}.ts` | 工具定义、schema 投影、参数校验、调用与错误归一 |
| `kb.py` | —（Memoria 侧工具，接既有服务层） | 只读工具：检索/读文档（可分页）/读知识点/概览/校验/会话检索 + 上游读面 `glob`/`grep`/`read_image`（2026-09-20，见 `docs/design/dsh-agent-port.md §6.16`） |

M1 工具面**只读**：所有工具声明 `read_only=True`，写类调用由
`memoria.services.agent.approvals` 的默认策略拒绝。导入本包不联网、不打印。
"""

from __future__ import annotations

from memoria.services.agent.tools.kb import (
    DEFAULT_TOP_K,
    KB_TOOL_NAMES,
    build_kb_tools,
    kb_read_only,
)
from memoria.services.agent.tools.registry import (
    DENIED_CODE,
    INVALID_ARGUMENTS_CODE,
    TOOL_FAILED_CODE,
    UNKNOWN_TOOL_CODE,
    Tool,
    ToolOutput,
    ToolRegistry,
    ToolResult,
    error_text,
    parse_arguments,
    validate_arguments,
)

__all__ = [
    "DEFAULT_TOP_K",
    "DENIED_CODE",
    "INVALID_ARGUMENTS_CODE",
    "KB_TOOL_NAMES",
    "TOOL_FAILED_CODE",
    "Tool",
    "ToolOutput",
    "ToolRegistry",
    "ToolResult",
    "UNKNOWN_TOOL_CODE",
    "build_kb_tools",
    "error_text",
    "kb_read_only",
    "parse_arguments",
    "validate_arguments",
]
