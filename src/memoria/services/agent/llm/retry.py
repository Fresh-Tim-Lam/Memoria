# 语义移植自 deepseek-harness packages/llm/llm-retry + packages/llm/llm（MIT / BSD-3-Clause）
# 上游：https://github.com/deepseek-ai/deepseek-harness @ 0d1f50007f9bca3f52b06e1c3074fa14d5fb0720
# 版权归 DeepSeek；声明见仓库根 THIRD_PARTY_NOTICES.md

"""有界指数退避 + 对称抖动重试（仅对可重试失败）。

上游 `llm-retry` 在 agent 步骤边界重跑失败请求，退避公式与默认值来自
`llm/src/retry-policy.ts`：

- `localDelay`：`min(initial * 2 ** (retry - 1), max)` 再乘对称抖动
  `1 - jitter + 2 * jitter * random()`，最后仍不超过 `max`；
- 默认 `maxRetries = 5`、`initialDelayMs = 500`、`maxDelayMs = 10000`、
  `jitterRatio = 0.1`；默认可重试 code 为 `EMPTY_RESPONSE` / `RATE_LIMIT` /
  `SERVER` / `TIMEOUT` / `TRANSPORT`；
- 端点给出且不超过上限的 `Retry-After` 直接替换本地退避；超过上限时不重试
  （上游 normal 模式在此委派下游）。

本地新增（上游没有的取舍，见 `artifacts/dsh-port-llm/notes.md`）：

- `total_timeout_s`：重试总时限，退避后必然超时则提前放弃；
- `iter_with_retry`：流式调用只在**尚未产出任何事件**时重试——已经投递给调用方
  的分片无法撤回，重放会造成重复输出（上游把这件事交给回合级步骤重跑）。
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import TypeVar

from memoria.services.agent.llm.errors import RETRYABLE_CODES, ConfigError, is_retryable
from memoria.services.agent.llm.types import StreamEvent

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_INITIAL_DELAY_S",
    "DEFAULT_JITTER_RATIO",
    "DEFAULT_MAX_DELAY_S",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TOTAL_TIMEOUT_S",
    "RetryPolicy",
    "delay_for",
    "iter_with_retry",
    "local_delay",
    "run_with_retry",
]

DEFAULT_MAX_RETRIES = 5
DEFAULT_INITIAL_DELAY_S = 0.5
DEFAULT_MAX_DELAY_S = 10.0
DEFAULT_JITTER_RATIO = 0.1
DEFAULT_TOTAL_TIMEOUT_S = 120.0
#: 上游对指数上限的保护（`Math.min(retry - 1, 1024)`）。
_MAX_EXPONENT = 1024

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """一次调用的重试预算与退避参数。"""

    max_retries: int = DEFAULT_MAX_RETRIES
    initial_delay_s: float = DEFAULT_INITIAL_DELAY_S
    max_delay_s: float = DEFAULT_MAX_DELAY_S
    jitter_ratio: float = DEFAULT_JITTER_RATIO
    retryable_codes: frozenset[str] = RETRYABLE_CODES
    total_timeout_s: float | None = DEFAULT_TOTAL_TIMEOUT_S

    def __post_init__(self) -> None:
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ConfigError("retry.max_retries 必须是非负整数")
        if not 0 < self.initial_delay_s <= self.max_delay_s:
            raise ConfigError("retry.initial_delay_s 必须为正数且不超过 max_delay_s")
        if self.max_delay_s <= 0:
            raise ConfigError("retry.max_delay_s 必须为正数")
        if not 0 <= self.jitter_ratio <= 1:
            raise ConfigError("retry.jitter_ratio 必须介于 0 与 1 之间")
        if self.total_timeout_s is not None and self.total_timeout_s <= 0:
            raise ConfigError("retry.total_timeout_s 必须为正数或 None")
        if not self.retryable_codes:
            raise ConfigError("retry.retryable_codes 不能为空")

    def allows(self, error: BaseException) -> bool:
        """该失败是否属于本策略的可重试集合。"""
        code = getattr(error, "code", None)
        if isinstance(code, str):
            return code in self.retryable_codes
        return is_retryable(error)


def local_delay(attempt: int, policy: RetryPolicy, rand: Callable[[], float] = random.random) -> float:
    """本地退避秒数；`attempt` 为 1 起的第几次重试（对齐上游 `localDelay`）。"""
    exponent = min(attempt - 1, _MAX_EXPONENT)
    exponential = min(policy.initial_delay_s * 2**exponent, policy.max_delay_s)
    jitter = 1 - policy.jitter_ratio + 2 * policy.jitter_ratio * rand()
    return min(exponential * jitter, policy.max_delay_s)


def delay_for(
    error: BaseException,
    attempt: int,
    policy: RetryPolicy,
    rand: Callable[[], float] = random.random,
) -> float | None:
    """本次重试应等待的秒数；`None` 表示放弃重试。

    端点给出有效 `Retry-After` 时优先采用；超过 `max_delay_s` 则放弃（上游
    normal 模式同样在此停止重试）。
    """
    retry_after = getattr(error, "retry_after_s", None)
    if retry_after is not None and retry_after > 0:
        return retry_after if retry_after <= policy.max_delay_s else None
    return local_delay(attempt, policy, rand)


def run_with_retry(
    call: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    rand: Callable[[], float] = random.random,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
) -> T:
    """执行 `call`，按策略重试可重试失败；不可重试失败立即抛出。

    `policy.max_retries` 是首次请求**之后**的最大重试次数（与上游一致）。
    """
    active = policy or RetryPolicy()
    deadline = None if active.total_timeout_s is None else monotonic() + active.total_timeout_s
    attempt = 0
    while True:
        attempt += 1
        try:
            return call()
        except BaseException as exc:  # noqa: BLE001 — 只按策略判定，不吞掉错误
            if not active.allows(exc) or attempt > active.max_retries:
                raise
            delay = delay_for(exc, attempt, active, rand)
            if delay is None:
                raise
            if deadline is not None and monotonic() + delay > deadline:
                logger.warning("[agent-llm] 重试会超出总时限，放弃：%r", exc)
                raise
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            sleep(delay)


def iter_with_retry(
    factory: Callable[[], Iterable[StreamEvent]],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    rand: Callable[[], float] = random.random,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
) -> Iterator[StreamEvent]:
    """流式重试：仅在**尚未产出任何事件**时重试。

    一旦有事件投递给调用方，失败便原样抛出——重放已投递的分片会造成
    重复输出（上游把流式恢复交给回合级步骤重跑，而不是包装原始流）。
    """
    active = policy or RetryPolicy()
    deadline = None if active.total_timeout_s is None else monotonic() + active.total_timeout_s
    attempt = 0
    while True:
        attempt += 1
        emitted = False
        try:
            for event in factory():
                emitted = True
                yield event
            return
        except BaseException as exc:  # noqa: BLE001 — 只按策略判定，不吞掉错误
            if emitted or not active.allows(exc) or attempt > active.max_retries:
                raise
            delay = delay_for(exc, attempt, active, rand)
            if delay is None:
                raise
            if deadline is not None and monotonic() + delay > deadline:
                logger.warning("[agent-llm] 重试会超出总时限，放弃：%r", exc)
                raise
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            sleep(delay)
