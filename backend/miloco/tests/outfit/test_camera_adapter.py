# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contract tests for the one-frame Outfit camera adapter."""

import asyncio
import threading

import pytest
from miloco.outfit.camera_adapter import (
    CachedFrameUnavailableError,
    CameraFrameCaptureAdapter,
    TemporaryFrameStore,
)
from miloco.outfit.visual_ports import CapturedFrame


class _FakeLatestFrameReader:
    def __init__(self, frame: object | None) -> None:
        self.frame = frame
        self.calls: list[tuple[str, int]] = []

    def peek_latest_frame(self, did: str, *, window_ms: int = 2_000) -> object | None:
        self.calls.append((did, window_ms))
        return self.frame


class _FakeTemporaryFrameWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, str]] = []

    async def write_frame(
        self,
        *,
        decoded_frame: object,
        device_id: str,
        request_id: str,
    ) -> CapturedFrame:
        self.calls.append((decoded_frame, device_id, request_id))
        return CapturedFrame(
            request_id=request_id,
            device_id=device_id,
            media_token="opaque-captured-frame",
        )


class _FakeTemporaryFrameStore(_FakeTemporaryFrameWriter, TemporaryFrameStore):
    def __init__(self) -> None:
        super().__init__()
        self.deleted_tokens: list[str] = []

    async def delete_frame(self, *, frame: CapturedFrame) -> None:
        self.deleted_tokens.append(frame.media_token)


class _BlockingLatestFrameReader(_FakeLatestFrameReader):
    def __init__(self) -> None:
        super().__init__(object())
        self.started = threading.Event()
        self.release = threading.Event()

    def peek_latest_frame(self, did: str, *, window_ms: int = 2_000) -> object:
        self.calls.append((did, window_ms))
        self.started.set()
        if not self.release.wait(timeout=1):
            raise TimeoutError("test did not release reader")
        assert self.frame is not None
        return self.frame


class _SequencedBlockingReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.first_started = threading.Event()
        self.allow_first_to_finish = threading.Event()
        self.second_started = threading.Event()

    def peek_latest_frame(self, did: str, *, window_ms: int = 2_000) -> object:
        self.calls.append((did, window_ms))
        if len(self.calls) == 1:
            self.first_started.set()
            if not self.allow_first_to_finish.wait(timeout=1):
                raise TimeoutError("test did not release first reader")
            return {"frame": "cancelled-request"}
        self.second_started.set()
        return {"frame": "second-request"}


class _CancellableAtomicWriter(_FakeTemporaryFrameWriter):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.cancelled_and_rolled_back = False

    async def write_frame(
        self,
        *,
        decoded_frame: object,
        device_id: str,
        request_id: str,
    ) -> CapturedFrame:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled_and_rolled_back = True
            raise


@pytest.mark.asyncio
async def test_capture_reads_one_cached_frame_then_returns_only_opaque_token() -> None:
    decoded_frame = object()
    reader = _FakeLatestFrameReader(decoded_frame)
    writer = _FakeTemporaryFrameWriter()
    adapter = CameraFrameCaptureAdapter(
        latest_frame_reader=reader,
        temporary_frame_writer=writer,
    )

    captured = await adapter.capture_frame(device_id="camera-1", request_id="request-1")

    assert captured.media_token == "opaque-captured-frame"
    assert reader.calls == [("camera-1", 2_000)]
    assert writer.calls == [(decoded_frame, "camera-1", "request-1")]


@pytest.mark.asyncio
async def test_temporary_frame_store_can_delete_the_opaque_capture_after_review() -> (
    None
):
    decoded_frame = object()
    reader = _FakeLatestFrameReader(decoded_frame)
    store = _FakeTemporaryFrameStore()
    adapter = CameraFrameCaptureAdapter(
        latest_frame_reader=reader,
        temporary_frame_writer=store,
    )

    captured = await adapter.capture_frame(device_id="camera-1", request_id="request-1")
    await store.delete_frame(frame=captured)

    assert store.deleted_tokens == ["opaque-captured-frame"]


@pytest.mark.asyncio
async def test_capture_fails_without_writing_when_no_cached_frame_is_available() -> (
    None
):
    reader = _FakeLatestFrameReader(None)
    writer = _FakeTemporaryFrameWriter()
    adapter = CameraFrameCaptureAdapter(
        latest_frame_reader=reader,
        temporary_frame_writer=writer,
    )

    with pytest.raises(CachedFrameUnavailableError):
        await adapter.capture_frame(device_id="camera-1", request_id="request-1")

    assert reader.calls == [("camera-1", 2_000)]
    assert writer.calls == []


@pytest.mark.asyncio
async def test_sync_cached_frame_peek_runs_off_the_event_loop() -> None:
    reader = _BlockingLatestFrameReader()
    adapter = CameraFrameCaptureAdapter(
        latest_frame_reader=reader,
        temporary_frame_writer=_FakeTemporaryFrameWriter(),
    )

    loop = asyncio.get_running_loop()
    started_at = loop.time()
    capture_task = asyncio.create_task(
        adapter.capture_frame(device_id="camera-1", request_id="request-1")
    )
    await asyncio.sleep(0.02)
    event_loop_delay = loop.time() - started_at
    reader.release.set()
    await capture_task

    assert reader.started.is_set()
    assert event_loop_delay < 0.2


@pytest.mark.asyncio
async def test_cancelled_write_rolls_back_without_returning_a_media_token() -> None:
    writer = _CancellableAtomicWriter()
    adapter = CameraFrameCaptureAdapter(
        latest_frame_reader=_FakeLatestFrameReader(object()),
        temporary_frame_writer=writer,
    )
    capture_task = asyncio.create_task(
        adapter.capture_frame(device_id="camera-1", request_id="request-1")
    )
    await writer.started.wait()

    capture_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await capture_task
    assert writer.cancelled_and_rolled_back is True


@pytest.mark.asyncio
async def test_cancelled_reader_holds_device_lock_until_sync_read_really_finishes() -> (
    None
):
    reader = _SequencedBlockingReader()
    writer = _FakeTemporaryFrameWriter()
    adapter = CameraFrameCaptureAdapter(
        latest_frame_reader=reader,
        temporary_frame_writer=writer,
    )
    first = asyncio.create_task(
        adapter.capture_frame(device_id="camera-1", request_id="request-1")
    )
    await asyncio.to_thread(reader.first_started.wait)

    first.cancel()
    second = asyncio.create_task(
        adapter.capture_frame(device_id="camera-1", request_id="request-2")
    )
    await asyncio.sleep(0.02)

    assert reader.second_started.is_set() is False
    reader.allow_first_to_finish.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    captured = await second

    assert captured.request_id == "request-2"
    assert reader.second_started.is_set() is True
    assert writer.calls == [({"frame": "second-request"}, "camera-1", "request-2")]
