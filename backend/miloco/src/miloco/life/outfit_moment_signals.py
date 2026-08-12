# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Pure, deterministic evidence signals and safe candidate tag templates."""

from __future__ import annotations

import hashlib
import json

from miloco.life.outfit_moments import (
    OutfitMoment,
    OutfitMomentSignal,
    OutfitMomentTag,
)

RULE_VERSION = "outfit-moment-signal-v1"
RARE_COLOR_RETURN_WINDOW_MS = 30 * 24 * 60 * 60 * 1000


def derive_moment_signals(
    current: OutfitMoment, *, history: list[OutfitMoment]
) -> list[OutfitMomentSignal]:
    """Derive only reproducible signals from confirmed moment facts."""
    moments = _normalized_history(current, history)
    signals: list[OutfitMomentSignal] = []

    same_combination = [
        moment
        for moment in moments
        if moment.occurred_at_ms <= current.occurred_at_ms
        and tuple(sorted(moment.item_ids)) == tuple(sorted(current.item_ids))
    ]
    if len(same_combination) >= 3:
        evidence = tuple(
            moment.confirmed_wear_event_id for moment in same_combination[-3:]
        )
        value = {"confirmed_count": len(same_combination)}
        signals.append(
            _signal(
                current,
                signal_type="repeat_favorite",
                value_json=value,
                evidence_event_ids=evidence,
            )
        )

    for color in sorted(set(current.color_labels)):
        prior = [
            moment
            for moment in moments
            if moment.moment_id != current.moment_id
            and moment.occurred_at_ms < current.occurred_at_ms
            and color in moment.color_labels
        ]
        if not prior:
            continue
        previous = prior[-1]
        elapsed_ms = current.occurred_at_ms - previous.occurred_at_ms
        if elapsed_ms < RARE_COLOR_RETURN_WINDOW_MS:
            continue
        elapsed_days = elapsed_ms // (24 * 60 * 60 * 1000)
        signals.append(
            _signal(
                current,
                signal_type="rare_color_return",
                value_json={
                    "color": color,
                    "days_since_last_confirmed": elapsed_days,
                },
                evidence_event_ids=(
                    previous.confirmed_wear_event_id,
                    current.confirmed_wear_event_id,
                ),
            )
        )

    return sorted(signals, key=lambda signal: (signal.signal_type, signal.signal_id))


def build_candidate_tags(signals: list[OutfitMomentSignal]) -> list[OutfitMomentTag]:
    """Translate allowed signals into auditable, non-sensitive candidate copy."""
    return [_tag_from_signal(signal) for signal in signals]


def _normalized_history(
    current: OutfitMoment, history: list[OutfitMoment]
) -> list[OutfitMoment]:
    moments = {moment.moment_id: moment for moment in history}
    moments[current.moment_id] = current
    if any(
        moment.owner_person_id != current.owner_person_id for moment in moments.values()
    ):
        raise ValueError("moment history must be owner scoped")
    return sorted(
        moments.values(), key=lambda moment: (moment.occurred_at_ms, moment.moment_id)
    )


def _signal(
    current: OutfitMoment,
    *,
    signal_type: str,
    value_json: dict[str, int | str],
    evidence_event_ids: tuple[str, ...],
) -> OutfitMomentSignal:
    payload = json.dumps(
        value_json, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(
        "\x00".join(
            (
                current.owner_person_id,
                current.moment_id,
                signal_type,
                payload,
                *evidence_event_ids,
                RULE_VERSION,
            )
        ).encode("utf-8")
    ).hexdigest()[:20]
    return OutfitMomentSignal(
        signal_id=f"signal-{digest}",
        moment_id=current.moment_id,
        signal_type=signal_type,  # type: ignore[arg-type]
        value_json=value_json,
        evidence_event_ids=evidence_event_ids,
        rule_version=RULE_VERSION,
    )


def _tag_from_signal(signal: OutfitMomentSignal) -> OutfitMomentTag:
    if signal.signal_type == "repeat_favorite":
        confirmed_count = signal.value_json["confirmed_count"]
        label = "常穿组合"
        narrative = f"已确认记录显示，这套组合已出现 {confirmed_count} 次。"
    else:
        days = signal.value_json["days_since_last_confirmed"]
        label = "久违的颜色"
        narrative = f"已确认记录显示，这个颜色距离上次出现已有 {days} 天。"
    digest = hashlib.sha256(
        f"{signal.moment_id}\x00{signal.signal_id}\x00{RULE_VERSION}".encode("utf-8")
    ).hexdigest()[:20]
    return OutfitMomentTag(
        tag_id=f"tag-{digest}",
        moment_id=signal.moment_id,
        tag_type=signal.signal_type,
        label=label,
        narrative=narrative,
        evidence_signal_ids=(signal.signal_id,),
        source="rule",
        confidence=1.0,
        review_status="pending",
        dedupe_key=f"{signal.signal_type}:{signal.signal_id}:{RULE_VERSION}",
        generator_version=RULE_VERSION,
    )
