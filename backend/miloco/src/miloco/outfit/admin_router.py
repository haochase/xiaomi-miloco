# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Authenticated read-only usage endpoint for Outfit administration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from fastapi import APIRouter, Depends, Response

from miloco.middleware import verify_token
from miloco.plugins.usage import UsageSnapshot


class UsageTodayReader(Protocol):
    """Read the injected service's current local-day snapshot."""

    async def get_today(self) -> UsageSnapshot: ...


def create_outfit_admin_usage_router(
    *,
    usage_service: UsageTodayReader,
    authentication_dependency: Callable[..., object] = verify_token,
) -> APIRouter:
    """Create a private header-authenticated router without write operations."""

    router = APIRouter()

    @router.get(
        "/api/outfit/admin/usage/today",
        dependencies=[Depends(authentication_dependency)],
        response_model=UsageSnapshot,
    )
    async def get_today_usage(response: Response) -> UsageSnapshot:
        response.headers["Cache-Control"] = "private, no-store"
        return await usage_service.get_today()

    return router
