# 语义移植自 deepseek-harness packages/interaction/user-questions 与 packages/interaction/tool-ask-user（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""向用户提问的 seam（上游 `user-questions`）：模型中途挂起、等人作答、把答案当**普通工具结果**送回循环。

模型面的消费者是 `tools/kb.py` 的 `ask_user_question` 工具（上游同名包 `tool-ask-user`）；
本模块只负责**服务语义**：问题批次的规范化、结果词汇、失败码与等待出口。

| 上游 | 本地 |
|---|---|
| `ctx.userQuestions.ask(request)`（UI 能力 seam） | `questions.ask(kb_path, …)`（走 `approval_bridge` 末尾的**待答信道**） |
| `AskUserQuestionItem`：`id` / `question` / `header` / `options[].label|description` / `multiSelect` | 同名同义（工具 schema 逐字段照搬，仅文案本地化；工具参数用上游的 `multi_select` 拼写，线上结构用 `multiSelect`，与上游 `execute` 的映射逐字一致） |
| 工具结果 = `{answers:[{id, selected[], custom?}]}` 的 **JSON 文本** | 同名同义（`ToolOutput.text` 就是该 JSON） |
| `NO_PROVIDER`（无应答者）/ `EMPTY_QUESTIONS`（空批次）/ `ASK_ABORTED`（提问前已中止） | 同名同义（`QuestionError.code`）；`ASK_ABORTED` 本地兼表"本轮被取消"（上游该码就是 abort 语义） |
| `CALLER_NOT_LIVE` / `DELEGATED_CALLER`（agent 归属校验） | **不适用**：本地无多 agent 归属模型（单一会话 + 单飞作业，不存在"子 agent 无人可问"） |
| `BAD_INTENT` / `detail` / `intent`（plan-review 展示意图） | **未移植**：本地计划确认走 M3a 自己的卡片（`js/plan-confirm.js`），不引第二条计划审批路径；按上游口径"不认识的 intent 走通用流程"，这里就是不认它（收到也忽略） |
| 无超时（只等 `signal`） | **本地新增** `NO_ANSWER`：等待上限 `approval_bridge.QUESTION_TIMEOUT_S`（180s），超时按 fail-closed 收成错误结果，模型可再问一次 |
| 工具**只读**、不走审批 | 同（唯一"副作用"是本轮挂起等人；故与审批共用 `attach`/`detach`/`abort` 生命周期） |

**模型可见文本**：成功 = `{"answers": [{"id": …, "selected": […], "custom": …}]}`（上游 `render` 就是
`JSON.stringify(value)`）；失败 = `Error: ask_user_question: <reason> (<CODE>)`（稳定码见上表）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "ASK_ABORTED",
    "EMPTY_QUESTIONS",
    "NO_ANSWER",
    "NO_PROVIDER",
    "QuestionError",
    "ask",
    "wire_questions",
]

#: 稳定失败码（前三者与上游 `UserQuestionError` 的 code 逐字同名；`NO_ANSWER` 为本地新增，见上表）。
NO_PROVIDER = "NO_PROVIDER"
EMPTY_QUESTIONS = "EMPTY_QUESTIONS"
ASK_ABORTED = "ASK_ABORTED"
NO_ANSWER = "NO_ANSWER"


class QuestionError(RuntimeError):
    """提问失败（无应答者 / 空批次 / 被取消 / 超时）；`code` 是上表的稳定码。"""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def _option(raw: Any) -> dict[str, Any] | None:
    """一个候选项 → `{label, description?}`；没有可用 `label` 的项**丢弃**（不编造标签）。"""
    if not isinstance(raw, Mapping):
        return None
    label = str(raw.get("label") or "").strip()
    if not label:
        return None
    out: dict[str, Any] = {"label": label}
    description = str(raw.get("description") or "").strip()
    if description:
        out["description"] = description
    return out


def wire_questions(rows: Sequence[Any]) -> list[dict[str, Any]]:
    """把工具参数里的一批问题规范成**线上结构**（`AskUserQuestionItem` 的 JSON 形态）。

    只搬已知键：`id` / `question` / `header?` / `options?[{label, description?}]` / `multiSelect?`。
    工具参数已在注册表按 JSON Schema 校验过（`id`/`question` 必填且非空），故这里只做规范化，
    不重复报错；`options` 里缺 `label` 的项直接丢弃。
    """
    out: list[dict[str, Any]] = []
    for row in rows or ():
        item: dict[str, Any] = {}
        if isinstance(row, Mapping):
            item["id"] = str(row.get("id") or "").strip()
            item["question"] = str(row.get("question") or "").strip()
            header = str(row.get("header") or "").strip()
            if header:
                item["header"] = header
            options = [_option(opt) for opt in (row.get("options") or ())]
            options = [opt for opt in options if opt is not None]
            if options:
                item["options"] = options
            if row.get("multi_select") is True:
                item["multiSelect"] = True
        else:
            item["id"] = ""
            item["question"] = ""
        out.append(item)
    return out


def ask(
    kb_path: str,
    questions: Sequence[Any],
    *,
    timeout_s: float | None = None,
) -> list[dict[str, Any]]:
    """问一批问题并**阻塞**等人作答；返回上游形状的答案列表 `[{id, selected[], custom?}]`。

    四条失败路径全部 fail-closed（对齐上游「Callers fail closed on `unavailable`」）：
    空批次 ⇒ `EMPTY_QUESTIONS`；没有面板在轮询（CLI / 未挂载）或本轮已结束 ⇒ `NO_PROVIDER`；
    本轮被取消 ⇒ `ASK_ABORTED`；等人超时 ⇒ `NO_ANSWER`。**任何一种都不会返回空答案冒充"问过了"**。
    """
    from memoria.services.agent import approval_bridge

    batch = wire_questions(questions)
    if not batch:
        raise QuestionError("ask_user_question requires at least one question", EMPTY_QUESTIONS)
    status, answers = approval_bridge.wait_for_question_answer(
        kb_path,
        batch,
        timeout_s=approval_bridge.QUESTION_TIMEOUT_S if timeout_s is None else float(timeout_s),
    )
    if status == "answered":
        return answers
    if status == "aborted":
        raise QuestionError("本轮已取消，提问未获作答", ASK_ABORTED)
    if status == "timeout":
        raise QuestionError("用户未在等待上限内作答", NO_ANSWER)
    raise QuestionError("没有可用的问答面（面板未在轮询本库）", NO_PROVIDER)
