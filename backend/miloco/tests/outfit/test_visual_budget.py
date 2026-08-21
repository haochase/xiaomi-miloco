# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Fail-closed session-budget contracts for Outfit visual review."""

import pytest
from miloco.outfit.visual_budget import (
    VisualBudgetRequest,
    VisualSessionBudgetGuard,
)


def _request(**overrides: object) -> VisualBudgetRequest:
    values: dict[str, object] = {
        "session_id": "session-1",
        "session_started_at_ms": 1_000,
        "now_ms": 1_100,
        "explicit_trigger": True,
        "max_tokens": 10,
    }
    values.update(overrides)
    return VisualBudgetRequest(**values)


def _guard(**overrides: object) -> VisualSessionBudgetGuard:
    values: dict[str, object] = {
        "ttl_ms": 1_000,
        "max_concurrent_requests": 1,
        "max_model_calls": 2,
        "max_total_tokens": 30,
        "max_consecutive_provider_errors": 2,
    }
    values.update(overrides)
    return VisualSessionBudgetGuard(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("budget_request", "reason"),
    [
        (_request(explicit_trigger=False), "explicit_trigger_required"),
        (_request(now_ms=2_001), "session_expired"),
        (_request(max_tokens=31), "token_budget_exceeded"),
        (_request(now_ms=999), "session_start_in_future"),
    ],
)
async def test_guard_rejects_unsafe_session_before_any_capture_or_provider(
    budget_request: VisualBudgetRequest,
    reason: str,
) -> None:
    admission = await _guard().acquire(request=budget_request)

    assert admission.allowed is False
    assert admission.reason == reason
    assert admission.lease is None


@pytest.mark.asyncio
async def test_guard_rejects_second_concurrent_request_until_first_completes() -> None:
    guard = _guard()
    first = await guard.acquire(request=_request())
    second = await guard.acquire(request=_request())

    assert first.allowed is True
    assert first.lease is not None
    assert second.allowed is False
    assert second.reason == "concurrent_request_limit"

    await guard.complete(lease=first.lease, provider_error=False, actual_tokens=5)
    next_request = _request(now_ms=1_200)
    next_admission = await guard.acquire(request=next_request)

    assert next_admission.allowed is True


@pytest.mark.asyncio
async def test_guard_enforces_model_call_and_reserved_token_limits() -> None:
    guard = _guard(max_model_calls=1, max_total_tokens=10)
    first = await guard.acquire(request=_request(max_tokens=10))
    assert first.lease is not None
    await guard.complete(lease=first.lease, provider_error=False, actual_tokens=5)

    second = await guard.acquire(request=_request(now_ms=1_200, max_tokens=1))

    assert second.allowed is False
    assert second.reason == "model_call_limit"


@pytest.mark.asyncio
async def test_guard_rejects_a_later_call_when_reserved_tokens_reach_budget() -> None:
    guard = _guard(max_model_calls=2, max_total_tokens=15)
    first = await guard.acquire(request=_request(max_tokens=10))
    assert first.lease is not None
    await guard.complete(lease=first.lease, provider_error=False, actual_tokens=10)

    second = await guard.acquire(request=_request(now_ms=1_200, max_tokens=10))

    assert second.allowed is False
    assert second.reason == "token_budget_exceeded"


@pytest.mark.asyncio
async def test_guard_rejects_after_configured_consecutive_provider_errors() -> None:
    guard = _guard(max_consecutive_provider_errors=1)
    first = await guard.acquire(request=_request())
    assert first.lease is not None
    await guard.complete(lease=first.lease, provider_error=True, actual_tokens=0)

    next_admission = await guard.acquire(request=_request(now_ms=1_200))

    assert next_admission.allowed is False
    assert next_admission.reason == "provider_error_limit"


@pytest.mark.asyncio
async def test_guard_reconciles_reserved_tokens_to_finite_actual_usage() -> None:
    guard = _guard(max_model_calls=2, max_total_tokens=15)
    first = await guard.acquire(request=_request(max_tokens=10))
    assert first.lease is not None

    reason = await guard.complete(
        lease=first.lease,
        provider_error=False,
        actual_tokens=5,
    )
    second = await guard.acquire(request=_request(now_ms=1_200, max_tokens=10))

    assert reason is None
    assert second.allowed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actual_tokens", "reason"),
    [
        (None, "usage_unavailable"),
        (-1, "usage_unavailable"),
        (11, "token_budget_exceeded"),
    ],
)
async def test_guard_fails_closed_for_missing_invalid_or_over_budget_actual_usage(
    actual_tokens: int | None,
    reason: str,
) -> None:
    guard = _guard()
    admission = await guard.acquire(request=_request(max_tokens=10))
    assert admission.lease is not None

    completion_reason = await guard.complete(
        lease=admission.lease,
        provider_error=False,
        actual_tokens=actual_tokens,
    )

    assert completion_reason == reason


@pytest.mark.asyncio
async def test_session_start_is_immutable_while_session_is_active_or_unexpired() -> (
    None
):
    guard = _guard()
    first = await guard.acquire(request=_request())
    assert first.lease is not None
    await guard.complete(lease=first.lease, provider_error=False, actual_tokens=5)

    inconsistent = await guard.acquire(
        request=_request(session_started_at_ms=1_050, now_ms=1_200)
    )

    assert inconsistent.allowed is False
    assert inconsistent.reason == "session_start_mismatch"


@pytest.mark.asyncio
async def test_expired_inactive_session_is_evicted_and_can_restart_cleanly() -> None:
    guard = _guard(max_model_calls=1)
    first = await guard.acquire(request=_request())
    assert first.lease is not None
    await guard.complete(lease=first.lease, provider_error=False, actual_tokens=5)

    restarted = await guard.acquire(
        request=_request(session_started_at_ms=2_500, now_ms=2_600)
    )

    assert restarted.allowed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("actual_tokens", [11, 31])
async def test_over_budget_actual_usage_permanently_exhausts_session(
    actual_tokens: int,
) -> None:
    guard = _guard(
        max_model_calls=3,
        max_total_tokens=30,
        max_consecutive_provider_errors=3,
    )
    first = await guard.acquire(request=_request(max_tokens=10))
    assert first.lease is not None

    reason = await guard.complete(
        lease=first.lease,
        provider_error=False,
        actual_tokens=actual_tokens,
    )
    next_admission = await guard.acquire(request=_request(now_ms=1_200, max_tokens=1))

    assert reason == "token_budget_exceeded"
    assert guard._sessions["session-1"].used_tokens == actual_tokens
    assert next_admission.allowed is False
    assert next_admission.reason == "token_budget_exceeded"


@pytest.mark.asyncio
async def test_exhaustion_rejects_completion_of_an_already_admitted_lease() -> None:
    guard = _guard(
        max_concurrent_requests=2,
        max_model_calls=3,
        max_total_tokens=30,
        max_consecutive_provider_errors=3,
    )
    over_budget = await guard.acquire(request=_request(max_tokens=10))
    already_admitted = await guard.acquire(request=_request(max_tokens=10))
    assert over_budget.lease is not None
    assert already_admitted.lease is not None

    first_reason = await guard.complete(
        lease=over_budget.lease,
        provider_error=False,
        actual_tokens=11,
    )
    second_reason = await guard.complete(
        lease=already_admitted.lease,
        provider_error=False,
        actual_tokens=10,
    )

    assert first_reason == "token_budget_exceeded"
    assert second_reason == "token_budget_exceeded"
    assert guard._sessions["session-1"].used_tokens == 21


@pytest.mark.asyncio
async def test_missing_actual_usage_after_provider_error_closes_session() -> None:
    guard = _guard(max_consecutive_provider_errors=3)
    admission = await guard.acquire(request=_request())
    assert admission.lease is not None

    reason = await guard.complete(
        lease=admission.lease,
        provider_error=True,
        actual_tokens=None,
    )
    next_admission = await guard.acquire(request=_request(now_ms=1_200))

    assert reason == "usage_unavailable"
    assert next_admission.allowed is False
    assert next_admission.reason == "usage_unavailable"
