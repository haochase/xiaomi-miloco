# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tests for reusable life-agent resource lease coordination."""

from __future__ import annotations


async def test_resource_lease_manager_rejects_same_resource_until_released():
    from miloco.life.resource_lease import ResourceLeaseManager

    manager = ResourceLeaseManager()

    first = await manager.try_acquire("camera", "camera_01")
    second = await manager.try_acquire("camera", "camera_01")

    assert first.acquired is True
    assert first.resource_type == "camera"
    assert first.resource_id == "camera_01"
    assert second.acquired is False
    assert second.release_reason == "busy"
    assert manager.active_count == 1

    await first.release(reason="completed")
    third = await manager.try_acquire("camera", "camera_01")

    assert third.acquired is True
    assert manager.active_count == 1
    await third.release(reason="completed")
    assert manager.active_count == 0


async def test_resource_lease_manager_allows_different_resource_ids():
    from miloco.life.resource_lease import ResourceLeaseManager

    manager = ResourceLeaseManager()

    camera = await manager.try_acquire("camera", "camera_01")
    speaker = await manager.try_acquire("speaker", "camera_01")
    other_camera = await manager.try_acquire("camera", "camera_02")

    assert camera.acquired is True
    assert speaker.acquired is True
    assert other_camera.acquired is True
    assert manager.active_count == 3

    await camera.release(reason="completed")
    await speaker.release(reason="completed")
    await other_camera.release(reason="completed")
    assert manager.active_count == 0


async def test_resource_lease_release_is_idempotent():
    from miloco.life.resource_lease import ResourceLeaseManager

    manager = ResourceLeaseManager()
    lease = await manager.try_acquire("mimo", "vision")

    assert lease.acquired is True
    await lease.release(reason="failed")
    await lease.release(reason="completed")

    assert manager.active_count == 0
