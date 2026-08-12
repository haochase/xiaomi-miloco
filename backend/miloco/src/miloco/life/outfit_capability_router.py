# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Authenticated capability snapshot for the optional Outfit panel."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, FastAPI

from miloco.life.outfit_installation import is_outfit_plugin_installed
from miloco.schema.common_schema import NormalResponse

_OUTFIT_CAPABILITY = {"id": "outfit_v2", "enabled": True, "api_version": "v1"}


def build_outfit_capability_router(
    app: FastAPI,
    *,
    authenticate: Callable[..., object],
) -> APIRouter:
    """Build a service-authenticated, low-sensitivity plugin capability API."""
    router = APIRouter(
        prefix="/outfit",
        tags=["Outfit"],
        dependencies=[Depends(authenticate)],
    )

    @router.get("/capabilities", response_model=NormalResponse)
    def list_capabilities() -> NormalResponse:
        capabilities = [_OUTFIT_CAPABILITY] if is_outfit_plugin_installed(app) else []
        return NormalResponse(code=0, message="ok", data=capabilities)

    return router
