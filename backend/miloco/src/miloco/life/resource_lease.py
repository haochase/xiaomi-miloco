# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Reusable short-lived resource leases for on-demand life agents."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

LeaseReleaseReason = Literal["completed", "failed", "busy", "timeout", "cancelled"]


@dataclass
class ResourceLease:
    """A single acquired or rejected resource lease."""

    resource_type: str
    resource_id: str
    acquired: bool
    _manager: ResourceLeaseManager | None = field(repr=False, default=None)
    release_reason: LeaseReleaseReason | None = None
    _released: bool = field(repr=False, default=False)

    async def release(self, *, reason: LeaseReleaseReason) -> None:
        """Release this lease once; repeated releases are ignored."""
        if not self.acquired or self._released or self._manager is None:
            return
        await self._manager.release(self.resource_type, self.resource_id)
        self.release_reason = reason
        self._released = True


class ResourceLeaseManager:
    """Coordinates single-flight leases for named resources in one process."""

    def __init__(self) -> None:
        self._guard = asyncio.Lock()
        self._active: set[tuple[str, str]] = set()

    @property
    def active_count(self) -> int:
        return len(self._active)

    async def try_acquire(self, resource_type: str, resource_id: str) -> ResourceLease:
        key = (resource_type, resource_id)
        async with self._guard:
            if key in self._active:
                return ResourceLease(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    acquired=False,
                    release_reason="busy",
                )
            self._active.add(key)
            return ResourceLease(
                resource_type=resource_type,
                resource_id=resource_id,
                acquired=True,
                _manager=self,
            )

    async def release(self, resource_type: str, resource_id: str) -> None:
        async with self._guard:
            self._active.discard((resource_type, resource_id))
