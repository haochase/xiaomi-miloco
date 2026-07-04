# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""FastAPI lifecycle wiring for the low-frequency device-state watcher."""

from __future__ import annotations

import logging
from typing import Any

from miloco.life.device_state_watcher import (
    DeviceStateWatcherLoop,
    read_device_state_watcher_config,
)
from miloco.voice.router import (
    enqueue_life_scene_trigger_service,
    set_device_state_watcher_loop_service,
)

logger = logging.getLogger(__name__)


async def _maybe_start_device_state_watcher_loop(app: Any, manager: Any) -> None:
    config = read_device_state_watcher_config()
    if not config.autostart_allowed:
        logger.info(
            "Device-state watcher autostart skipped: missing=%s enabled=%s",
            config.diagnostics()["missing"],
            config.enabled,
        )
        set_device_state_watcher_loop_service(None)
        return

    loop = DeviceStateWatcherLoop(
        config=config,
        miot_service=manager.miot_service,
        enqueue_scene_trigger=enqueue_life_scene_trigger_service,
    )
    await loop.start()
    app.state.device_state_watcher_loop = loop
    set_device_state_watcher_loop_service(loop)
    logger.info("Device-state watcher loop started")


async def _stop_device_state_watcher_loop(app: Any) -> None:
    loop = getattr(app.state, "device_state_watcher_loop", None)
    if loop is not None:
        try:
            await loop.stop()
        except Exception:  # noqa: BLE001
            logger.exception("Device-state watcher loop stop failed")
    set_device_state_watcher_loop_service(None)
    if hasattr(app.state, "device_state_watcher_loop"):
        delattr(app.state, "device_state_watcher_loop")
