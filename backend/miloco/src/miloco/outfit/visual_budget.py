# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Fail-closed, in-memory session budgets for explicit Outfit visual review."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class VisualBudgetRejectReason(StrEnum):
    """Stable pre-capture rejection reasons without sensitive request details."""

    EXPLICIT_TRIGGER_REQUIRED = "explicit_trigger_required"
    SESSION_EXPIRED = "session_expired"
    CONCURRENT_REQUEST_LIMIT = "concurrent_request_limit"
    MODEL_CALL_LIMIT = "model_call_limit"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    USAGE_UNAVAILABLE = "usage_unavailable"
    PROVIDER_ERROR_LIMIT = "provider_error_limit"
    SESSION_START_IN_FUTURE = "session_start_in_future"
    SESSION_START_MISMATCH = "session_start_mismatch"


class VisualBudgetRequest(BaseModel):
    """Host-assembled budget evidence required before a frame can be captured."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    session_started_at_ms: int = Field(ge=0)
    now_ms: int = Field(ge=0)
    explicit_trigger: bool
    max_tokens: int = Field(gt=0)


@dataclass(frozen=True, slots=True)
class VisualBudgetLease:
    """One admitted attempt which must be completed to release concurrency."""

    session_id: str
    lease_id: str


@dataclass(frozen=True, slots=True)
class VisualBudgetAdmission:
    """Result of one pre-capture budget admission decision."""

    allowed: bool
    reason: VisualBudgetRejectReason | None = None
    lease: VisualBudgetLease | None = None


@dataclass(slots=True)
class _SessionState:
    session_started_at_ms: int
    active_token_reservations: dict[str, int] = field(default_factory=dict)
    model_calls: int = 0
    used_tokens: int = 0
    consecutive_provider_errors: int = 0
    token_budget_exhausted: bool = False
    usage_accounting_unavailable: bool = False


class VisualSessionBudgetGuard:
    """Reject unbounded visual sessions before calling capture or a model provider."""

    def __init__(
        self,
        *,
        ttl_ms: int,
        max_concurrent_requests: int,
        max_model_calls: int,
        max_total_tokens: int,
        max_consecutive_provider_errors: int,
    ) -> None:
        _require_positive("ttl_ms", ttl_ms)
        _require_positive("max_concurrent_requests", max_concurrent_requests)
        _require_positive("max_model_calls", max_model_calls)
        _require_positive("max_total_tokens", max_total_tokens)
        _require_positive(
            "max_consecutive_provider_errors",
            max_consecutive_provider_errors,
        )
        self._ttl_ms = ttl_ms
        self._max_concurrent_requests = max_concurrent_requests
        self._max_model_calls = max_model_calls
        self._max_total_tokens = max_total_tokens
        self._max_consecutive_provider_errors = max_consecutive_provider_errors
        self._sessions: dict[str, _SessionState] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, *, request: VisualBudgetRequest) -> VisualBudgetAdmission:
        """Reserve one bounded attempt, or reject before any capture/provider I/O."""

        reason = _preflight_reason(request, ttl_ms=self._ttl_ms)
        if reason is not None:
            return VisualBudgetAdmission(allowed=False, reason=reason)

        async with self._lock:
            self._evict_expired_inactive_sessions(now_ms=request.now_ms)
            state = self._sessions.get(request.session_id)
            if state is None:
                state = _SessionState(
                    session_started_at_ms=request.session_started_at_ms
                )
                self._sessions[request.session_id] = state
            elif state.session_started_at_ms != request.session_started_at_ms:
                return VisualBudgetAdmission(
                    allowed=False,
                    reason=VisualBudgetRejectReason.SESSION_START_MISMATCH,
                )
            if state.token_budget_exhausted:
                return VisualBudgetAdmission(
                    allowed=False,
                    reason=VisualBudgetRejectReason.TOKEN_BUDGET_EXCEEDED,
                )
            if state.usage_accounting_unavailable:
                return VisualBudgetAdmission(
                    allowed=False,
                    reason=VisualBudgetRejectReason.USAGE_UNAVAILABLE,
                )
            if (
                state.consecutive_provider_errors
                >= self._max_consecutive_provider_errors
            ):
                return VisualBudgetAdmission(
                    allowed=False,
                    reason=VisualBudgetRejectReason.PROVIDER_ERROR_LIMIT,
                )
            if len(state.active_token_reservations) >= self._max_concurrent_requests:
                return VisualBudgetAdmission(
                    allowed=False,
                    reason=VisualBudgetRejectReason.CONCURRENT_REQUEST_LIMIT,
                )
            if state.model_calls >= self._max_model_calls:
                return VisualBudgetAdmission(
                    allowed=False,
                    reason=VisualBudgetRejectReason.MODEL_CALL_LIMIT,
                )
            if (
                state.used_tokens
                + sum(state.active_token_reservations.values())
                + request.max_tokens
                > self._max_total_tokens
            ):
                return VisualBudgetAdmission(
                    allowed=False,
                    reason=VisualBudgetRejectReason.TOKEN_BUDGET_EXCEEDED,
                )

            lease_id = uuid4().hex
            state.active_token_reservations[lease_id] = request.max_tokens
            state.model_calls += 1
            return VisualBudgetAdmission(
                allowed=True,
                lease=VisualBudgetLease(
                    session_id=request.session_id,
                    lease_id=lease_id,
                ),
            )

    async def complete(
        self,
        *,
        lease: VisualBudgetLease,
        provider_error: bool | None,
        actual_tokens: int | None,
    ) -> VisualBudgetRejectReason | None:
        """Release a lease and reconcile its reservation to finite actual usage."""

        async with self._lock:
            state = self._sessions.get(lease.session_id)
            if state is None or lease.lease_id not in state.active_token_reservations:
                raise ValueError("visual budget lease is not active")
            reserved_tokens = state.active_token_reservations.pop(lease.lease_id)
            usage_reject_reason = _usage_reject_reason(
                actual_tokens=actual_tokens,
                reserved_tokens=reserved_tokens,
                used_tokens=state.used_tokens,
                max_total_tokens=self._max_total_tokens,
                provider_error=provider_error,
            )
            if state.token_budget_exhausted:
                usage_reject_reason = VisualBudgetRejectReason.TOKEN_BUDGET_EXCEEDED
            elif state.usage_accounting_unavailable:
                usage_reject_reason = VisualBudgetRejectReason.USAGE_UNAVAILABLE
            if provider_error is True or usage_reject_reason is not None:
                state.consecutive_provider_errors += 1
            elif provider_error is False:
                state.consecutive_provider_errors = 0
            if type(actual_tokens) is int and actual_tokens >= 0:
                state.used_tokens += actual_tokens
            if usage_reject_reason is VisualBudgetRejectReason.TOKEN_BUDGET_EXCEEDED:
                state.token_budget_exhausted = True
            elif usage_reject_reason is VisualBudgetRejectReason.USAGE_UNAVAILABLE:
                state.usage_accounting_unavailable = True
            return usage_reject_reason

    def _evict_expired_inactive_sessions(self, *, now_ms: int) -> None:
        expired_session_ids = [
            session_id
            for session_id, state in self._sessions.items()
            if not state.active_token_reservations
            and now_ms - state.session_started_at_ms > self._ttl_ms
        ]
        for session_id in expired_session_ids:
            del self._sessions[session_id]


def _preflight_reason(
    request: VisualBudgetRequest,
    *,
    ttl_ms: int,
) -> VisualBudgetRejectReason | None:
    if not request.explicit_trigger:
        return VisualBudgetRejectReason.EXPLICIT_TRIGGER_REQUIRED
    if request.session_started_at_ms > request.now_ms:
        return VisualBudgetRejectReason.SESSION_START_IN_FUTURE
    if request.now_ms - request.session_started_at_ms > ttl_ms:
        return VisualBudgetRejectReason.SESSION_EXPIRED
    return None


def _usage_reject_reason(
    *,
    actual_tokens: int | None,
    reserved_tokens: int,
    used_tokens: int,
    max_total_tokens: int,
    provider_error: bool | None,
) -> VisualBudgetRejectReason | None:
    if actual_tokens is None:
        if provider_error is not None:
            return VisualBudgetRejectReason.USAGE_UNAVAILABLE
        return None
    if type(actual_tokens) is not int or actual_tokens < 0:
        return VisualBudgetRejectReason.USAGE_UNAVAILABLE
    if (
        actual_tokens > reserved_tokens
        or used_tokens + actual_tokens > max_total_tokens
    ):
        return VisualBudgetRejectReason.TOKEN_BUDGET_EXCEEDED
    return None


def _require_positive(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
