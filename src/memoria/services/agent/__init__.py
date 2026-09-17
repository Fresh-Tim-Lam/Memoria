# 语义移植自 deepseek-harness packages/llm/* 与 packages/core/*（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""产品内对话 Agent 的服务层（dsh 代码级移植落点）。

上游能力**逐块**以 Python 语义重写（方案见 `docs/design/dsh-agent-port.md`），
当前进度：

| 子包 | 状态 | 说明 |
|---|---|---|
| `llm/` | ✅ M1 第一块 | provider 中立的模型调用：流式、用量、重试、OpenAI 兼容适配 |

后续块（agent 循环、prompt 组装、工具注册表、会话持久化、审批）按同一落点
继续追加，绝不新增独立进程或运行时。本包自身不导入任何子模块，避免在只用到
某一子包时付出多余导入成本；库代码不联网、不打印。
"""

from __future__ import annotations

__all__: list[str] = []
