# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Low-sensitivity notification adaptation for confirmed Outfit moments.

This module deliberately knows nothing about MiOT, OpenClaw, or a live push
service. A host adapter may implement the narrow port after its authentication,
primary-person, and delivery guarantees have been reviewed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlparse

from miloco.life.outfit_moments import OutfitMoment, OutfitMomentTag

_SAFE_SUMMARY = "A confirmed outfit moment is ready to review."
_APPROVED_TAG_STATUSES = frozenset({"confirmed", "edited"})


@dataclass(frozen=True)
class OutfitMomentNotification:
    """A transport-neutral, low-sensitivity notification payload."""

    summary: str
    deep_link_path: str
    panel_url: str | None
    idempotency_key: str


class OutfitMomentNotificationPort(Protocol):
    """Host-owned delivery boundary for optional Outfit notifications."""

    async def send_outfit_moment_notification(
        self, message: OutfitMomentNotification
    ) -> None:
        """Deliver a notification or raise an adapter-specific failure."""


class OutfitMomentNotificationDispatcher:
    """Suppress successful duplicate deliveries within one host process.

    A future host adapter must provide durable idempotency before this is wired
    to a real notification channel. Failed sends deliberately remain retryable.
    """

    def __init__(self, port: OutfitMomentNotificationPort):
        self._port = port
        self._delivered_keys: set[str] = set()

    async def dispatch(self, message: OutfitMomentNotification) -> bool:
        """Return whether this process attempted a new successful delivery."""
        if message.idempotency_key in self._delivered_keys:
            return False
        await self._port.send_outfit_moment_notification(message)
        self._delivered_keys.add(message.idempotency_key)
        return True


def build_outfit_moment_notification(
    moment: OutfitMoment,
    tag: OutfitMomentTag,
    *,
    panel_base_url: str | None = None,
) -> OutfitMomentNotification:
    """Build a generic summary and a configured, safe panel deep link."""
    if tag.moment_id != moment.moment_id:
        raise ValueError("tag must belong to the Outfit moment")
    if tag.review_status not in _APPROVED_TAG_STATUSES:
        raise ValueError("only an approved tag may trigger a notification")

    deep_link_path = f"/#/agents/outfit/moments/{quote(moment.moment_id, safe='')}"
    panel_url = _resolve_panel_url(panel_base_url, deep_link_path)
    idempotency_key = _idempotency_key(moment.moment_id, tag.tag_id, tag.review_status)
    return OutfitMomentNotification(
        summary=_SAFE_SUMMARY,
        deep_link_path=deep_link_path,
        panel_url=panel_url,
        idempotency_key=idempotency_key,
    )


def _resolve_panel_url(panel_base_url: str | None, deep_link_path: str) -> str | None:
    if panel_base_url is None:
        return None
    parsed = urlparse(panel_base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("panel base URL must be an origin without credentials or path")
    return f"{parsed.scheme}://{parsed.netloc}{deep_link_path}"


def _idempotency_key(moment_id: str, tag_id: str, review_status: str) -> str:
    raw = f"outfit-moment-v1\0{moment_id}\0{tag_id}\0{review_status}".encode()
    return f"outfit-moment-v1:{hashlib.sha256(raw).hexdigest()}"
