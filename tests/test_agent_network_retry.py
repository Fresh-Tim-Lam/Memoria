"""断网/瞬断重试：`Remote end closed` 等 TRANSPORT 失败在**未投递任何分片**时应重试。

约束（不因重试而改变）：
- 已经有分片投递给调用方后不再重放（避免重复输出）；
- DNS / 证书 / 连接被拒等确定性失败不重试；
- 重试预算有上限与总时限。
"""

from __future__ import annotations

import http.client

import pytest

from memoria.services.agent.ask import NETWORK_RETRY_POLICY
from memoria.services.agent.llm.errors import TRANSPORT_CODE, ProviderError, is_retryable
from memoria.services.agent.llm.retry import RetryPolicy, iter_with_retry


def test_network_policy_is_more_patient_than_upstream_default() -> None:
    assert NETWORK_RETRY_POLICY.max_retries == 6
    assert NETWORK_RETRY_POLICY.total_timeout_s == 240.0
    assert NETWORK_RETRY_POLICY.max_delay_s <= 15.0


def test_remote_disconnected_is_retryable_and_retried_before_first_event() -> None:
    # 真实断连异常：http.client.RemoteDisconnected 是 OSError 子类，不是确定性不可达。
    exc = http.client.RemoteDisconnected("Remote end closed connection without response")
    assert is_retryable(exc) is True

    attempts = []

    def factory():
        attempts.append(1)
        raise ProviderError("Remote end closed connection without response", code=TRANSPORT_CODE)
        yield  # pragma: no cover — generator 语法，永不产出

    policy = RetryPolicy(max_retries=3, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0)
    with pytest.raises(ProviderError):
        list(iter_with_retry(factory, policy=policy, sleep=lambda _s: None))
    assert len(attempts) == 4  # 首次 + 3 次重试


def test_retry_does_not_replay_after_first_event() -> None:
    calls = []

    def factory():
        calls.append(1)
        yield "chunk"
        raise ProviderError("Remote end closed", code=TRANSPORT_CODE)

    policy = RetryPolicy(max_retries=3, initial_delay_s=0.001, max_delay_s=0.01, jitter_ratio=0.0)
    with pytest.raises(ProviderError):
        list(iter_with_retry(factory, policy=policy, sleep=lambda _s: None))
    assert len(calls) == 1
