# 语义移植自 deepseek-harness packages/compaction/compaction-tool-result-pruner
# （MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""工具结果裁剪（M2）：把超预算的旧工具输出换成「头 + 中间标记 + 尾」的定长形态。

对照上游 `dsh-compaction-tool-result-pruner` 的可观察语义：

- **只在压力已确认时才裁**（由调用方 `ask._compact_if_needed()` 判定），**本身不调模型**；
  裁完可能已低于阈值 ⇒ **可以免除一次摘要调用**（上游原话：*trimming may relieve enough token
  pressure to skip summarization*）；
- **确定性单遍收敛**：按 **Unicode 码点**切片、预算固定 ⇒ 产出恒为「`head` + 标记 + `tail`」，
  且**不超过阈值**、**严格小于**原文本 —— 故重复运行不会二次改写（不回环、不增长）；
- **回放安全**：原事件**逐字留在日志里**（append-only），裁剪只在**回放期**生效 ⇒ 检索、导出、
  事后审计看到的仍是原文；
- **标记**：`PRUNE_MARKER`（上游同名常量逐字照抄）。

## 本地适配与偏差（登记进 `docs/design/dsh-agent-port.md §6.10`）

- **内容模型**：上游工具结果是 `ContentBlock[]`（可含图片等富块，富块**零成本直通**、相对顺序不变）；
  本地工具结果是**纯字符串**（M1 只有只读文本工具）⇒ 切片退化为对整串切分，无富块通路。
- **触发时机与落盘**：上游由 `compaction-basic` 在压力确认后、选择压缩区间**之前**调用，并把替换
  事件追加进会话（新 `tool/result` + `surfaceOp: replace` + 紧随其前的 `compaction/prune` 影子定价
  事件，`sourceEventSeqs` 指向被替换的原事件）。本地没有「表面替换」设施，也不能为同一个
  `tool_call_id` 追加第二条 `tool/result`（回放会把同一调用配成两条工具消息、端点 400）⇒ 改为**一条
  `compaction/prune` 记录**列出被裁的 `seq` 与其**实际使用的预算**，由 `history.py` 回放时**就地**
  重建裁剪后的正文；原事件仍在日志里 ⇒ 与上游同等的「回放安全」。
- **不移植**：影子定价（`shadowedTokenCount` —— 本地没有 token 计量服务；改用字符量 `chars_before` /
  `chars_after`，与 `compaction.shadowed_chars` 同口径）、`Session.surface` / `surfaceOp` 抽象、
  以及「替换写入失败 ⇒ 整轮同步失败」（本地是 fail-open：记不进就按原样继续，见 `ask.py`）。
- **与检索的关系**：`session/query.py` 在**原始事件**上检索 ⇒ 被裁掉的中间段**仍可被搜到**
  （本地取舍：宁可搜得全，也不让裁剪把历史从检索面抹掉）。上游检索走的是裁剪后的表面。
- **码点口径**：Python `str` 本就是码点序列（无 UTF-16 代理对），故 `len(text)` 即上游
  `codePointLength()`；但**字素簇仍可能被切开**（上游同样如此，并已列为已知限制）。

## 不写盘

本模块**不写盘、不联网、不调模型**：全是纯函数，落盘由调用方 `ask.py` 完成。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_BUDGETS",
    "PRUNE",
    "PRUNE_HEAD_CHARS",
    "PRUNE_MARKER",
    "PRUNE_TAIL_CHARS",
    "PRUNE_THRESHOLD_CHARS",
    "PruneBudgets",
    "PruneError",
    "applied_chars",
    "apply_budget",
    "prune_applied",
    "prune_plan",
    "prune_records",
    "prune_text",
]

#: 承载裁剪记录的会话事件类型（对齐上游 `compaction/prune` 事件名）。
PRUNE = "compaction/prune"
#: 替换被删中段用的固定标记（上游同名字面量，含前后各一个空行）。
PRUNE_MARKER = "\n\n[... tool result middle pruned ...]\n\n"
#: 超过该码点数就裁（对齐上游 `thresholdChars` 默认值）。
PRUNE_THRESHOLD_CHARS = 8_192
#: 保留的前导码点数（对齐上游 `headChars` 默认值）。
PRUNE_HEAD_CHARS = 4_096
#: 保留的末尾码点数（对齐上游 `tailChars` 默认值）。
PRUNE_TAIL_CHARS = 1_024

#: 本地会话事件里承载工具输出的类型（与 `history.TOOL_RESULT` 同值；此处写字面量以避免反向依赖）。
_TOOL_RESULT = "tool/result"


class PruneError(ValueError):
    """裁剪预算非法（对齐上游 `resolveConfig` 的**构造期**拒绝）。"""


def _positive(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PruneError(f"裁剪预算 {name}（{value!r}）必须是正整数")


def _non_negative(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PruneError(f"裁剪预算 {name}（{value!r}）必须是非负整数")


@dataclass(frozen=True, slots=True)
class PruneBudgets:
    """一次裁剪使用的字符预算（对齐上游 `ResolvedConfig`）。

    构造即校验：`threshold` 为正整数，`head` / `tail` 为非负整数，且
    **`head` + 标记 + `tail` 不得超过 `threshold`** —— 后者保证裁剪永远**不会变长**。
    """

    threshold: int = PRUNE_THRESHOLD_CHARS
    head: int = PRUNE_HEAD_CHARS
    tail: int = PRUNE_TAIL_CHARS

    def __post_init__(self) -> None:
        _positive("threshold", self.threshold)
        _non_negative("head", self.head)
        _non_negative("tail", self.tail)
        emitted = self.head + len(PRUNE_MARKER) + self.tail
        if emitted > self.threshold:
            raise PruneError(
                f"裁剪预算 head + 标记 + tail（{emitted}）不得超过 threshold（{self.threshold}）"
            )


DEFAULT_BUDGETS = PruneBudgets()


def apply_budget(text: str, head: int, tail: int) -> str:
    """按给定预算重建正文：`head` 个前导码点 + 标记 + `tail` 个末尾码点。

    **回放用**：调用方传的是记录里落盘的预算，故回放结果与当次请求所见**逐字一致**
    （即便将来默认预算变了，旧会话也照旧）。
    """
    lead = text[:head] if head > 0 else ""
    trail = text[len(text) - tail :] if tail > 0 else ""
    return f"{lead}{PRUNE_MARKER}{trail}"


def applied_chars(head: int, tail: int) -> int:
    """裁剪后正文的码点数（`head` + 标记 + `tail`）—— 供区域选择按**有效视图**计账。"""
    return head + len(PRUNE_MARKER) + tail


def prune_text(
    text: str, *, budgets: PruneBudgets = DEFAULT_BUDGETS
) -> str | None:
    """超预算则返回裁剪后的正文；未超则返回 `None`（= 无需改动）。

    不变量（对齐上游 `pruneContent`，由 `PruneBudgets` 的构造校验兜住）：产出
    **不超过 `budgets.threshold`** 且**严格小于**输入，故裁剪**单调收敛**。
    """
    body = str(text or "")
    if len(body) <= budgets.threshold:
        return None
    return apply_budget(body, budgets.head, budgets.tail)


def _records(event: Mapping[str, Any]) -> Sequence[Any]:
    """一条 `compaction/prune` 记录里的逐项清单（形状不对则视作空）。"""
    if event.get("type") != PRUNE:
        return ()
    data = event.get("data")
    raw = data.get("pruned") if isinstance(data, Mapping) else None
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return raw
    return ()


def prune_records(events: Sequence[Mapping[str, Any]]) -> set[int]:
    """**已被裁过**的 `seq`（幂等判据：不重复记录、不二次改写）。"""
    done: set[int] = set()
    for event in events:
        for item in _records(event):
            if isinstance(item, Mapping) and isinstance(item.get("seq"), int):
                done.add(int(item["seq"]))
    return done


def prune_applied(events: Sequence[Mapping[str, Any]]) -> dict[int, tuple[int, int]]:
    """**回放用**：`seq -> (head, tail)`；**后写覆盖**（与 `compaction` 的链式口径一致）。

    形状不全的记录（缺 `head`/`tail`、类型不对）**整条忽略** —— fail-safe：宁可当没裁过
    （让模型看到原文），也不要拿一个半截预算去切正文。
    """
    applied: dict[int, tuple[int, int]] = {}
    for event in events:
        for item in _records(event):
            if not isinstance(item, Mapping):
                continue
            seq, head, tail = item.get("seq"), item.get("head"), item.get("tail")
            if (
                isinstance(seq, int)
                and isinstance(head, int)
                and isinstance(tail, int)
                and head >= 0
                and tail >= 0
            ):
                applied[seq] = (head, tail)
    return applied


def prune_plan(
    events: Sequence[Mapping[str, Any]],
    *,
    budgets: PruneBudgets = DEFAULT_BUDGETS,
    skip: set[int] | None = None,
) -> list[dict[str, Any]]:
    """扫出**需要裁剪**的 `tool/result` 事件，产出待落盘的逐项清单（按 `seq` 升序）。

    - `skip`：**不要裁**的 `seq`（调用方传入「已被 `compaction` 覆盖」的那些 —— 它们本来就不进
      请求，裁了纯属浪费记录）；
    - 已被既有 `compaction/prune` 记录裁过的 `seq` 自动跳过（幂等）；
    - 每条含 `seq` / `id` / `chars_before` / `chars_after` / `head` / `tail`：前四项供核对收益，
      后两项让**回放**不依赖当时的默认预算。
    """
    done = prune_records(events)
    plan: list[dict[str, Any]] = []
    for event in events:
        seq = event.get("seq")
        if not isinstance(seq, int) or seq in done or (skip and seq in skip):
            continue
        if event.get("type") != _TOOL_RESULT:
            continue
        data = event.get("data")
        content = str(data.get("content") or "") if isinstance(data, Mapping) else ""
        pruned = prune_text(content, budgets=budgets)
        if pruned is None:
            continue
        plan.append(
            {
                "seq": seq,
                "id": str(data.get("id") or "") if isinstance(data, Mapping) else "",
                "chars_before": len(content),
                "chars_after": len(pruned),
                "head": budgets.head,
                "tail": budgets.tail,
            }
        )
    return plan
