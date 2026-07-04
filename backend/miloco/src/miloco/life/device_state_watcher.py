# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Configuration and diagnostics for low-frequency MiOT device-state triggers."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Protocol

from miloco.life.scene_trigger import LifeSceneIntent, LifeSceneTriggerPayload

_TRUTHY_ENV = {"1", "true", "yes", "on"}
_VALID_INTENTS: set[LifeSceneIntent] = {
    "outfit_check",
    "outfit_suggest",
    "cooking_check",
    "cooking_suggest",
}


@dataclass(frozen=True)
class DeviceStateWatcherConfig:
    """Safe-to-log watcher configuration snapshot.

    ``did``, ``iid``, and ``target_value`` remain on the object for the watcher
    runtime, but diagnostics only expose whether each binding exists.
    """

    enabled: bool
    audit_passed: bool
    did: str | None
    iid: str | None
    target_value: str | None
    intent: LifeSceneIntent
    poll_interval_ms: int
    cooldown_ms: int
    error_backoff_ms: int
    trigger_source: Literal["device_state"] = "device_state"

    @property
    def ready(self) -> bool:
        return not self._missing_required()

    @property
    def autostart_allowed(self) -> bool:
        return bool(self.enabled and self.ready)

    def diagnostics(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "autostart_allowed": self.autostart_allowed,
            "trigger_source": self.trigger_source,
            "intent": self.intent,
            "did_configured": bool(self.did),
            "iid_configured": bool(self.iid),
            "target_value_configured": self.target_value is not None,
            "poll_interval_ms": self.poll_interval_ms,
            "cooldown_ms": self.cooldown_ms,
            "edge_trigger": True,
            "baseline_required": True,
            "rearm_required": True,
            "error_backoff_enabled": True,
            "polls_device_status_only": True,
            "forbidden_during_idle_poll": [
                "camera",
                "speaker",
                "mimo",
                "life_agent",
            ],
            "missing": self._missing_required(),
        }

    def _missing_required(self) -> list[str]:
        missing: list[str] = []
        if not self.audit_passed:
            missing.append("audit_passed")
        if not self.did:
            missing.append("did")
        if not self.iid:
            missing.append("iid")
        if self.target_value is None:
            missing.append("target_value")
        return missing


def read_device_state_watcher_config() -> DeviceStateWatcherConfig:
    intent = _env_text("MILOCO_LIFE_DEVICE_STATE_INTENT") or "outfit_suggest"
    if intent not in _VALID_INTENTS:
        intent = "outfit_suggest"

    return DeviceStateWatcherConfig(
        enabled=_env_bool("MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED", False),
        audit_passed=_env_bool(
            "MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED",
            False,
        ),
        did=_env_text("MILOCO_LIFE_DEVICE_STATE_DID"),
        iid=_env_text("MILOCO_LIFE_DEVICE_STATE_IID"),
        target_value=_env_text("MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE"),
        intent=intent,
        poll_interval_ms=_env_int(
            "MILOCO_LIFE_DEVICE_STATE_POLL_INTERVAL_MS",
            default=30000,
            minimum=30000,
        ),
        cooldown_ms=_env_int(
            "MILOCO_LIFE_DEVICE_STATE_COOLDOWN_MS",
            default=120000,
            minimum=30000,
        ),
        error_backoff_ms=_env_int(
            "MILOCO_LIFE_DEVICE_STATE_ERROR_BACKOFF_MS",
            default=60000,
            minimum=30000,
        ),
    )


def _env_text(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUTHY_ENV


def _env_int(
    name: str,
    *,
    default: int,
    minimum: int,
) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, parsed)


class DeviceStatusReader(Protocol):
    async def get_device_status(self, did: str, iids: list[str]) -> dict[str, Any]: ...


class DeviceStateWatcher:
    """One-device, low-frequency MiOT state watcher.

    The watcher only reads MiOT property state during polling. It calls the
    provided scene enqueue function after a configured state edge is observed.
    """

    def __init__(
        self,
        *,
        config: DeviceStateWatcherConfig,
        miot_service: DeviceStatusReader,
        enqueue_scene_trigger: Callable[[LifeSceneTriggerPayload], object],
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        if not config.enabled:
            raise ValueError("device-state watcher is disabled")
        if not config.ready:
            raise ValueError("device-state watcher is missing safety/config gates")
        self._config = config
        self._miot_service = miot_service
        self._enqueue_scene_trigger = enqueue_scene_trigger
        self._now_ms = now_ms or _system_now_ms
        self._baseline_seen = False
        self._last_value: object | None = None
        self._armed = False
        self._last_triggered_at_ms: int | None = None
        self._next_poll_after_ms = self._now_ms()

    async def poll_once(self) -> dict[str, object]:
        now_ms = self._now_ms()
        try:
            response = await self._miot_service.get_device_status(
                str(self._config.did),
                [str(self._config.iid)],
            )
        except Exception as exc:  # noqa: BLE001
            self._next_poll_after_ms = now_ms + self._config.error_backoff_ms
            return {
                "action": "error_backoff",
                "triggered": False,
                "error": str(exc),
                "next_poll_after_ms": self._next_poll_after_ms,
            }

        current_value = _extract_property_value(response, str(self._config.iid))
        current_matches = _value_matches(current_value, self._config.target_value)

        if not self._baseline_seen:
            self._baseline_seen = True
            self._last_value = current_value
            self._armed = not current_matches
            self._next_poll_after_ms = now_ms + self._config.poll_interval_ms
            return self._result("baseline", current_value, triggered=False)

        previous_matches = _value_matches(self._last_value, self._config.target_value)
        self._last_value = current_value

        if not current_matches:
            self._armed = True
            self._next_poll_after_ms = now_ms + self._config.poll_interval_ms
            return self._result(
                "rearmed" if previous_matches else "idle",
                current_value,
                triggered=False,
            )

        if not self._armed:
            self._next_poll_after_ms = now_ms + self._config.poll_interval_ms
            return self._result("held", current_value, triggered=False)

        if self._last_triggered_at_ms is not None:
            cooldown_until = self._last_triggered_at_ms + self._config.cooldown_ms
            if now_ms < cooldown_until:
                self._next_poll_after_ms = min(
                    cooldown_until,
                    now_ms + self._config.poll_interval_ms,
                )
                return self._result("cooldown", current_value, triggered=False)

        payload = LifeSceneTriggerPayload(
            intent=self._config.intent,
            trigger_source="device_state",
            source_id=f"device_state:{self._config.did}:{self._config.iid}",
        )
        self._enqueue_scene_trigger(payload)
        self._armed = False
        self._last_triggered_at_ms = now_ms
        self._next_poll_after_ms = now_ms + self._config.cooldown_ms
        return self._result("triggered", current_value, triggered=True)

    @property
    def next_poll_after_ms(self) -> int:
        return self._next_poll_after_ms

    def _result(
        self,
        action: str,
        current_value: object,
        *,
        triggered: bool,
    ) -> dict[str, object]:
        return {
            "action": action,
            "triggered": triggered,
            "current_value": current_value,
            "next_poll_after_ms": self._next_poll_after_ms,
        }


class DeviceStateWatcherLoop:
    """Background runner for a configured device-state watcher."""

    def __init__(
        self,
        *,
        config: DeviceStateWatcherConfig,
        miot_service: DeviceStatusReader,
        enqueue_scene_trigger: Callable[[LifeSceneTriggerPayload], object],
        now_ms: Callable[[], int] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._miot_service = miot_service
        self._enqueue_scene_trigger = enqueue_scene_trigger
        self._now_ms = now_ms or _system_now_ms
        self._sleep = sleep or asyncio.sleep
        self._watcher: DeviceStateWatcher | None = None
        self._task: asyncio.Task[None] | None = None
        self._last_poll_result: dict[str, object] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._ensure_watcher()
        self._task = asyncio.create_task(self.run_forever())

    async def stop(self) -> None:
        task = self._task
        if task is None:
            self._running = False
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            self._running = False

    async def run_forever(self) -> None:
        watcher = self._ensure_watcher()
        self._running = True
        try:
            while True:
                self._last_poll_result = await watcher.poll_once()
                sleep_seconds = max(
                    0.0,
                    (watcher.next_poll_after_ms - self._now_ms()) / 1000,
                )
                await self._sleep(sleep_seconds)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

    def status(self) -> dict[str, object]:
        return build_device_state_watcher_status(
            config=self._config,
            running=self._running,
            last_poll_result=self._last_poll_result,
            watcher=self._watcher,
        )

    def _ensure_watcher(self) -> DeviceStateWatcher:
        if self._watcher is None:
            self._watcher = DeviceStateWatcher(
                config=self._config,
                miot_service=self._miot_service,
                enqueue_scene_trigger=self._enqueue_scene_trigger,
                now_ms=self._now_ms,
            )
        return self._watcher


def build_device_state_watcher_status(
    *,
    config: DeviceStateWatcherConfig,
    running: bool,
    last_poll_result: dict[str, object] | None = None,
    watcher: DeviceStateWatcher | None = None,
) -> dict[str, object]:
    status = dict(config.diagnostics())
    status["running"] = running
    status["last_poll"] = _safe_last_poll(last_poll_result)
    status["next_poll_after_ms"] = (
        watcher.next_poll_after_ms if watcher is not None else None
    )
    return status


def _safe_last_poll(result: dict[str, object] | None) -> dict[str, object] | None:
    if result is None:
        return None
    safe_keys = {"action", "triggered", "error", "next_poll_after_ms"}
    return {key: value for key, value in result.items() if key in safe_keys}


def _extract_property_value(response: dict[str, Any], iid: str) -> object | None:
    properties = response.get("properties")
    if not isinstance(properties, list):
        return None
    for item in properties:
        if not isinstance(item, dict):
            continue
        if str(item.get("iid")) == iid:
            return item.get("value")
    return None


def _value_matches(current_value: object, target_value: str | None) -> bool:
    if target_value is None:
        return False
    return _normalize_value(current_value) == _normalize_value(target_value)


def _normalize_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value).strip().lower()


def _system_now_ms() -> int:
    import time

    return int(time.time() * 1000)
