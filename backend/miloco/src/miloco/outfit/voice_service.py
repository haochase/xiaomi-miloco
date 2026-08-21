# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Application service for trusted, once-only Outfit voice turns."""

from __future__ import annotations

import asyncio
import time
from typing import Protocol

from miloco.outfit.context import OutfitRecommendationContext
from miloco.outfit.recommendation_service import (
    OutfitRecommendationResponse,
    OutfitRecommendationService,
)
from miloco.outfit.voice_contracts import (
    OutfitVoiceOutcome,
    TrustedSpeechTurn,
    VoiceTurnStatus,
    validate_primary_person_id,
)
from miloco.outfit.voice_delivery import SpeakerTextPort, VoiceDeliveryService
from miloco.outfit.voice_event_repo import (
    VoiceDeliveryState,
    VoiceEventClaimStatus,
    VoiceEventRecord,
    VoiceEventRepository,
)
from miloco.outfit.voice_observability import (
    VoiceAuditDeliveryState,
    VoiceAuditErrorCode,
    VoiceAuditStage,
    VoiceTurnAuditPort,
    build_voice_turn_audit_record,
)

_DELIVERY_UNAVAILABLE_RESPONSE_TEXT = "播报暂不可用，请在面板查看。"


class VoiceContextResolver(Protocol):
    """Host-owned resolver for converting trusted text into structured scene facts."""

    def resolve(self, turn: TrustedSpeechTurn) -> OutfitRecommendationContext: ...


class OutfitVoiceTurnService:
    """Turn trusted speech into at-most-once inventory advice and literal TTS."""

    def __init__(
        self,
        *,
        primary_person_id: str,
        context_resolver: VoiceContextResolver,
        recommendation_service: OutfitRecommendationService,
        event_repository: VoiceEventRepository,
        speaker: SpeakerTextPort,
        speaker_device_id: str,
        delivery_timeout_s: float,
        audit: VoiceTurnAuditPort | None = None,
    ) -> None:
        self._primary_person_id = validate_primary_person_id(primary_person_id)
        if recommendation_service.primary_person_id != self._primary_person_id:
            raise ValueError(
                "recommendation inventory owner must match voice event owner"
            )
        self._context_resolver = context_resolver
        self._recommendation_service = recommendation_service
        self._event_repository = event_repository
        self._delivery_service = VoiceDeliveryService(
            speaker,
            device_id=speaker_device_id,
            timeout_s=delivery_timeout_s,
        )
        self._audit = audit

    async def handle(self, *, turn: TrustedSpeechTurn) -> OutfitVoiceOutcome:
        """Process a fresh host-trusted turn without taking owner from the request."""

        started_ns = time.perf_counter_ns()
        claim = self._event_repository.claim_event(self._primary_person_id, turn)
        if claim.status is VoiceEventClaimStatus.REPLAY:
            if claim.record is None:
                raise ValueError("replayed voice event is missing its outcome")
            outcome = _outcome_from_record(claim.record)
            await self._record_audit(
                turn=turn,
                stage="replay",
                outcome=outcome,
                delivery_state="replayed",
                error_code=None,
                started_ns=started_ns,
            )
            return outcome
        if claim.status is VoiceEventClaimStatus.IN_PROGRESS:
            outcome = OutfitVoiceOutcome(status=VoiceTurnStatus.IGNORED)
            await self._record_audit(
                turn=turn,
                stage="replay",
                outcome=outcome,
                delivery_state=VoiceDeliveryState.NOT_ATTEMPTED,
                error_code="event_in_progress",
                started_ns=started_ns,
            )
            return outcome
        if claim.status is VoiceEventClaimStatus.CONFLICT:
            outcome = OutfitVoiceOutcome(status=VoiceTurnStatus.FAILED)
            await self._record_audit(
                turn=turn,
                stage="recommendation",
                outcome=outcome,
                delivery_state=VoiceDeliveryState.NOT_ATTEMPTED,
                error_code="event_conflict",
                started_ns=started_ns,
            )
            return outcome

        try:
            response = self._recommendation_service.recommend(
                self._context_resolver.resolve(turn)
            )
            outcome_status, response_text = _response_for_voice(response)
        except Exception:
            outcome = self._complete_unavailable_recommendation(turn)
            await self._record_audit(
                turn=turn,
                stage="recommendation",
                outcome=outcome,
                delivery_state=VoiceDeliveryState.NOT_ATTEMPTED,
                error_code="recommendation_failed",
                started_ns=started_ns,
            )
            return outcome

        try:
            delivery = await self._delivery_service.deliver_once(
                text=response_text,
                idempotency_key=turn.idempotency_key,
            )
        except asyncio.CancelledError:
            self._event_repository.complete_event(
                self._primary_person_id,
                turn,
                outcome_status=VoiceTurnStatus.FAILED,
                response_text=_DELIVERY_UNAVAILABLE_RESPONSE_TEXT,
                delivery_state=VoiceDeliveryState.UNKNOWN,
            )
            raise
        if delivery.state is not VoiceDeliveryState.DELIVERED:
            outcome_status = VoiceTurnStatus.FAILED
            response_text = _DELIVERY_UNAVAILABLE_RESPONSE_TEXT

        self._event_repository.complete_event(
            self._primary_person_id,
            turn,
            outcome_status=outcome_status,
            response_text=response_text,
            delivery_state=delivery.state,
        )
        outcome = OutfitVoiceOutcome(status=outcome_status, response_text=response_text)
        await self._record_audit(
            turn=turn,
            stage="completed"
            if delivery.state is VoiceDeliveryState.DELIVERED
            else "delivery",
            outcome=outcome,
            delivery_state=delivery.state,
            error_code=None
            if delivery.state is VoiceDeliveryState.DELIVERED
            else "speaker_delivery_failed",
            started_ns=started_ns,
        )
        return outcome

    async def _record_audit(
        self,
        *,
        turn: TrustedSpeechTurn,
        stage: VoiceAuditStage,
        outcome: OutfitVoiceOutcome,
        delivery_state: VoiceAuditDeliveryState,
        error_code: VoiceAuditErrorCode | None,
        started_ns: int,
    ) -> None:
        if self._audit is None:
            return
        try:
            record = build_voice_turn_audit_record(
                event_id=turn.event_id,
                source_device_id=turn.source_device_id,
                stage=stage,
                status=outcome.status.value,
                delivery_state=(
                    delivery_state.value
                    if isinstance(delivery_state, VoiceDeliveryState)
                    else delivery_state
                ),
                error_code=error_code,
                elapsed_ms=max(
                    0,
                    (time.perf_counter_ns() - started_ns) // 1_000_000,
                ),
                input_tokens=0,
                output_tokens=0,
            )
            await self._audit.record_voice_turn(record)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Observability must not turn a once-only voice result into a retry.
            pass

    def _complete_unavailable_recommendation(
        self,
        turn: TrustedSpeechTurn,
    ) -> OutfitVoiceOutcome:
        """Close a claimed event when advice cannot be formed before TTS."""

        response_text = "穿搭建议暂不可用，请在面板查看。"
        self._event_repository.complete_event(
            self._primary_person_id,
            turn,
            outcome_status=VoiceTurnStatus.FAILED,
            response_text=response_text,
            delivery_state=VoiceDeliveryState.NOT_ATTEMPTED,
        )
        return OutfitVoiceOutcome(
            status=VoiceTurnStatus.FAILED,
            response_text=response_text,
        )

    def delivery_state_for(self, turn: TrustedSpeechTurn) -> VoiceDeliveryState | None:
        """Return the persisted delivery state for the configured primary user only."""

        record = self._event_repository.get_completed_event(
            self._primary_person_id,
            turn,
        )
        return record.delivery_state if record is not None else None


def _response_for_voice(
    response: OutfitRecommendationResponse,
) -> tuple[VoiceTurnStatus, str]:
    if response.status == "needs_context":
        if response.clarification is None:
            raise ValueError("needs_context response is missing clarification")
        return VoiceTurnStatus.NEEDS_CONTEXT, response.clarification.prompt
    if response.status == "insufficient_inventory":
        return (
            VoiceTurnStatus.INSUFFICIENT_INVENTORY,
            "当前衣橱中可组成的完整穿搭不足，请先补充衣物后再试。",
        )
    if response.status == "ready":
        return (
            VoiceTurnStatus.READY,
            "已为你选好第一套库存穿搭，查看更多请打开面板。",
        )
    raise ValueError(f"unsupported Outfit recommendation status: {response.status}")


def _outcome_from_record(record: VoiceEventRecord) -> OutfitVoiceOutcome:
    return OutfitVoiceOutcome(
        status=record.outcome_status,
        response_text=record.response_text,
    )
