# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Safety policy helpers for life-agent recommendations and notifications."""

from __future__ import annotations

from miloco.life.schema import _reject_absolute_safety_claim_text


def reject_absolute_kitchen_safety_claims(text: str) -> None:
    """Reject absolute kitchen safety claims in user-facing output."""
    _reject_absolute_safety_claim_text(text)
