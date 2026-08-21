# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""One-frame adapter over the host's non-destructive cached-camera capability."""

from __future__ import annotations

import asyncio
from typing import Protocol

from miloco.outfit.visual_ports import (
    CapturedFrame,
    FrameCapturePort,
    TemporaryMediaStore,
)


class CachedFrameUnavailableError(RuntimeError):
    """The selected camera has no cached frame for an explicit review request."""


class LatestFrameReader(Protocol):
    """Cached-frame reader which must honor ``window_ms`` as a hard cooperative bound."""

    def peek_latest_frame(
        self, did: str, *, window_ms: int = 2_000
    ) -> object | None: ...


class TemporaryFrameWriter(Protocol):
    """Atomically persist one frame behind an opaque token.

    Cancellation must remove partial media before propagating ``CancelledError``.
    A token may be returned only after the complete frame is durable and deletable.
    """

    async def write_frame(
        self,
        *,
        decoded_frame: object,
        device_id: str,
        request_id: str,
    ) -> CapturedFrame: ...


class TemporaryFrameStore(TemporaryFrameWriter, TemporaryMediaStore, Protocol):
    """Combined host port for writing and deleting one temporary frame."""


class CameraFrameCaptureAdapter(FrameCapturePort):
    """Expose exactly one cached frame without opening a stream or running inference."""

    def __init__(
        self,
        *,
        latest_frame_reader: LatestFrameReader,
        temporary_frame_writer: TemporaryFrameWriter,
        peek_window_ms: int = 2_000,
    ) -> None:
        if peek_window_ms <= 0:
            raise ValueError("peek_window_ms must be positive")
        self._latest_frame_reader = latest_frame_reader
        self._temporary_frame_writer = temporary_frame_writer
        self._peek_window_ms = peek_window_ms
        self._device_locks: dict[str, asyncio.Lock] = {}

    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        """Read one existing cached frame and persist it as temporary opaque media."""

        device_lock = self._device_locks.setdefault(device_id, asyncio.Lock())
        async with device_lock:
            reader_task = asyncio.create_task(
                asyncio.to_thread(
                    self._latest_frame_reader.peek_latest_frame,
                    device_id,
                    window_ms=self._peek_window_ms,
                )
            )
            try:
                decoded_frame = await asyncio.shield(reader_task)
            except asyncio.CancelledError:
                await _await_reader_terminal(reader_task)
                raise
            if decoded_frame is None:
                raise CachedFrameUnavailableError("cached_frame_unavailable")
            return await self._temporary_frame_writer.write_frame(
                decoded_frame=decoded_frame,
                device_id=device_id,
                request_id=request_id,
            )


async def _await_reader_terminal(reader_task: asyncio.Task[object | None]) -> None:
    while True:
        try:
            await asyncio.shield(reader_task)
            return
        except asyncio.CancelledError:
            if reader_task.done():
                return
        except Exception:
            return
