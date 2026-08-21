# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Authenticated read-only capability endpoint for the Outfit plugin."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Response

from miloco.middleware import verify_token
from miloco.outfit.capability import OutfitCapabilitySnapshot, OutfitCapabilityState


def create_outfit_capability_router(
    *,
    state: OutfitCapabilityState,
    authentication_dependency: Callable[..., object] = verify_token,
) -> APIRouter:
    """Create a private, non-cacheable capability router with header-only auth."""

    router = APIRouter()

    @router.get(
        "/api/outfit/capability",
        dependencies=[Depends(authentication_dependency)],
        response_model=OutfitCapabilitySnapshot,
    )
    async def get_outfit_capability(response: Response) -> OutfitCapabilitySnapshot:
        response.headers["Cache-Control"] = "private, no-store"
        return state.snapshot()

    return router
