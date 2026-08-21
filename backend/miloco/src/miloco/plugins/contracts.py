# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Neutral contracts for optional in-process host plugins."""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter


class HostPluginContribution(Protocol):
    """A contribution whose lifecycle is owned by the host registry."""

    id: str

    async def start(self) -> None:
        """Start the contribution before it is published."""

    async def stop(self) -> None:
        """Stop the contribution during host shutdown."""

    def routers(self) -> tuple[APIRouter, ...]:
        """Return the contribution's HTTP routers."""

    def panel_capabilities(self) -> tuple[str, ...]:
        """Return stable panel capability identifiers."""
