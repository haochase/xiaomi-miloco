# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Application-service contracts for once-only Outfit voice delivery."""

import asyncio
from pathlib import Path

import pytest
from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.context import OutfitClarification, OutfitRecommendationContext
from miloco.outfit.ranking import rank_outfit_candidates
from miloco.outfit.recommendation import build_recommendation_result
from miloco.outfit.recommendation_service import OutfitRecommendationResponse
from miloco.outfit.storage import OutfitStorage
from miloco.outfit.voice_contracts import TrustedSpeechTurn, VoiceTurnStatus
from miloco.outfit.voice_delivery import SpeakerTextPort
from miloco.outfit.voice_event_repo import VoiceDeliveryState, VoiceEventRepository
from miloco.outfit.voice_observability import VoiceTurnAuditPort
from miloco.outfit.voice_service import OutfitVoiceTurnService, VoiceContextResolver


class FixedContextResolver:
    def __init__(self, context: OutfitRecommendationContext) -> None:
        self.context = context
        self.calls = 0

    def resolve(self, turn: TrustedSpeechTurn) -> OutfitRecommendationContext:
        self.calls += 1
        return self.context


class FailingContextResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, turn: TrustedSpeechTurn) -> OutfitRecommendationContext:
        self.calls += 1
        raise RuntimeError("context service unavailable")


class FixedRecommendationService:
    def __init__(
        self,
        response: OutfitRecommendationResponse,
        *,
        primary_person_id: str = "primary-person",
    ) -> None:
        self.response = response
        self.primary_person_id = primary_person_id
        self.calls = 0

    def recommend(
        self,
        context: OutfitRecommendationContext,
    ) -> OutfitRecommendationResponse:
        self.calls += 1
        return self.response


class RecordingSpeaker(SpeakerTextPort):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def play_text(
        self,
        *,
        device_id: str,
        text: str,
        idempotency_key: str,
    ) -> None:
        self.calls.append((device_id, text, idempotency_key))


class UnavailableSpeaker(SpeakerTextPort):
    def __init__(self) -> None:
        self.calls = 0

    async def play_text(
        self,
        *,
        device_id: str,
        text: str,
        idempotency_key: str,
    ) -> None:
        self.calls += 1
        raise RuntimeError("speaker unavailable")


class HangingSpeaker(SpeakerTextPort):
    async def play_text(
        self,
        *,
        device_id: str,
        text: str,
        idempotency_key: str,
    ) -> None:
        await asyncio.Event().wait()


class CancellableSpeaker(SpeakerTextPort):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def play_text(
        self,
        *,
        device_id: str,
        text: str,
        idempotency_key: str,
    ) -> None:
        self.calls.append((device_id, text, idempotency_key))
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


class RecordingVoiceAudit(VoiceTurnAuditPort):
    def __init__(self) -> None:
        self.records = []

    async def record_voice_turn(self, record) -> None:
        self.records.append(record)


class FailingVoiceAudit(VoiceTurnAuditPort):
    async def record_voice_turn(self, record) -> None:
        raise RuntimeError("audit sink unavailable")


def _turn(*, source_device_id: str | None = "speaker-device-1") -> TrustedSpeechTurn:
    return TrustedSpeechTurn(
        event_id="speech-event-1",
        text="今天客户会议怎么穿",
        source_kind="official_perception",
        source_device_id=source_device_id,
        room_id="living-room",
        observed_at_ms=1_700_000_000_000,
        received_at_ms=1_700_000_000_100,
        is_complete=True,
    )


def _ready_response() -> OutfitRecommendationResponse:
    result = build_recommendation_result(
        rank_outfit_candidates(
            [
                OutfitCandidate(
                    item_ids=("navy-top", "gray-bottom", "black-shoes"),
                    pattern="top_bottom_shoes",
                ),
                OutfitCandidate(
                    item_ids=("white-top", "black-bottom", "white-shoes"),
                    pattern="top_bottom_shoes",
                ),
            ]
        )
    )
    return OutfitRecommendationResponse(status="ready", result=result)


def _service(
    tmp_path: Path,
    *,
    speaker: SpeakerTextPort,
    response: OutfitRecommendationResponse | None = None,
    delivery_timeout_s: float = 1.0,
    context_resolver: VoiceContextResolver | None = None,
    audit: VoiceTurnAuditPort | None = None,
    recommendation_primary_person_id: str = "primary-person",
) -> tuple[OutfitVoiceTurnService, FixedRecommendationService, VoiceContextResolver]:
    recommendation_service = FixedRecommendationService(
        response or _ready_response(),
        primary_person_id=recommendation_primary_person_id,
    )
    resolved_context_resolver = context_resolver or FixedContextResolver(
        OutfitRecommendationContext(occasion="client meeting", day_kind="workday")
    )
    service = OutfitVoiceTurnService(
        primary_person_id="primary-person",
        context_resolver=resolved_context_resolver,
        recommendation_service=recommendation_service,
        event_repository=VoiceEventRepository(
            OutfitStorage(tmp_path / "outfit" / "voice-events.db")
        ),
        speaker=speaker,
        speaker_device_id="living-room-speaker",
        delivery_timeout_s=delivery_timeout_s,
        audit=audit,
    )
    return service, recommendation_service, resolved_context_resolver


def test_service_rejects_recommendation_inventory_owner_mismatch(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="recommendation inventory owner"):
        _service(
            tmp_path,
            speaker=RecordingSpeaker(),
            recommendation_primary_person_id="other-person",
        )


@pytest.mark.asyncio
async def test_service_recommends_and_broadcasts_once_then_replays_without_tts(
    tmp_path: Path,
) -> None:
    speaker = RecordingSpeaker()
    service, recommendation_service, context_resolver = _service(
        tmp_path,
        speaker=speaker,
    )
    turn = _turn()

    first = await service.handle(turn=turn)
    replay = await service.handle(turn=turn)

    assert first.status is VoiceTurnStatus.READY
    assert replay == first
    assert recommendation_service.calls == 1
    assert context_resolver.calls == 1
    assert len(speaker.calls) == 1
    device_id, text, idempotency_key = speaker.calls[0]
    assert device_id == "living-room-speaker"
    assert idempotency_key == turn.idempotency_key
    assert "第一套" in text
    assert "查看更多" in text
    assert "primary-person" not in text
    assert "score" not in text


@pytest.mark.asyncio
async def test_service_records_speaker_unavailable_without_replaying_delivery(
    tmp_path: Path,
) -> None:
    speaker = UnavailableSpeaker()
    service, recommendation_service, _ = _service(tmp_path, speaker=speaker)
    turn = _turn()

    first = await service.handle(turn=turn)
    replay = await service.handle(turn=turn)

    assert first.status is VoiceTurnStatus.FAILED
    assert replay == first
    assert recommendation_service.calls == 1
    assert speaker.calls == 1
    assert service.delivery_state_for(turn) is VoiceDeliveryState.FAILED


@pytest.mark.asyncio
async def test_service_records_speaker_timeout_as_unknown_without_retry(
    tmp_path: Path,
) -> None:
    service, recommendation_service, _ = _service(
        tmp_path,
        speaker=HangingSpeaker(),
        delivery_timeout_s=0.01,
    )
    turn = _turn()

    first = await service.handle(turn=turn)
    replay = await service.handle(turn=turn)

    assert first.status is VoiceTurnStatus.FAILED
    assert replay == first
    assert recommendation_service.calls == 1
    assert service.delivery_state_for(turn) is VoiceDeliveryState.UNKNOWN


@pytest.mark.asyncio
async def test_cancellation_before_speaker_attempt_completes_unknown_and_replays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    speaker = RecordingSpeaker()
    service, recommendation_service, _ = _service(tmp_path, speaker=speaker)
    turn = _turn()

    async def cancel_before_speaker_attempt(**_: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(
        service._delivery_service,
        "deliver_once",
        cancel_before_speaker_attempt,
    )

    with pytest.raises(asyncio.CancelledError):
        await service.handle(turn=turn)

    assert service.delivery_state_for(turn) is VoiceDeliveryState.UNKNOWN
    replay = await service.handle(turn=turn)
    assert replay.status is VoiceTurnStatus.FAILED
    assert replay.response_text == "播报暂不可用，请在面板查看。"
    assert recommendation_service.calls == 1
    assert speaker.calls == []


@pytest.mark.asyncio
async def test_cancellation_during_speaker_call_completes_unknown_and_replays(
    tmp_path: Path,
) -> None:
    speaker = CancellableSpeaker()
    service, recommendation_service, _ = _service(tmp_path, speaker=speaker)
    turn = _turn()
    task = asyncio.create_task(service.handle(turn=turn))
    await speaker.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert speaker.cancelled.is_set()
    assert service.delivery_state_for(turn) is VoiceDeliveryState.UNKNOWN
    replay = await service.handle(turn=turn)
    assert replay.status is VoiceTurnStatus.FAILED
    assert replay.response_text == "播报暂不可用，请在面板查看。"
    assert recommendation_service.calls == 1
    assert len(speaker.calls) == 1


@pytest.mark.asyncio
async def test_service_records_context_failure_without_delivery_and_replays_it(
    tmp_path: Path,
) -> None:
    speaker = RecordingSpeaker()
    context_resolver = FailingContextResolver()
    service, recommendation_service, _ = _service(
        tmp_path,
        speaker=speaker,
        context_resolver=context_resolver,
    )
    turn = _turn()

    first = await service.handle(turn=turn)
    replay = await service.handle(turn=turn)

    assert first.status is VoiceTurnStatus.FAILED
    assert replay == first
    assert context_resolver.calls == 1
    assert recommendation_service.calls == 0
    assert speaker.calls == []
    assert first.response_text == "穿搭建议暂不可用，请在面板查看。"
    assert service.delivery_state_for(turn) is VoiceDeliveryState.NOT_ATTEMPTED


@pytest.mark.asyncio
async def test_service_speaks_single_clarification_when_scene_is_missing(
    tmp_path: Path,
) -> None:
    speaker = RecordingSpeaker()
    response = OutfitRecommendationResponse(
        status="needs_context",
        clarification=OutfitClarification(
            field="occasion_or_activity",
            prompt="What occasion or activity should this outfit support?",
        ),
    )
    service, recommendation_service, _ = _service(
        tmp_path,
        speaker=speaker,
        response=response,
    )

    outcome = await service.handle(turn=_turn())

    assert outcome.status is VoiceTurnStatus.NEEDS_CONTEXT
    assert recommendation_service.calls == 1
    assert len(speaker.calls) == 1
    assert (
        speaker.calls[0][1] == "What occasion or activity should this outfit support?"
    )


@pytest.mark.asyncio
async def test_service_records_one_safe_completion_audit_without_raw_voice_data(
    tmp_path: Path,
) -> None:
    speaker = RecordingSpeaker()
    audit = RecordingVoiceAudit()
    service, _, _ = _service(tmp_path, speaker=speaker, audit=audit)

    outcome = await service.handle(turn=_turn())

    assert outcome.status is VoiceTurnStatus.READY
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record.stage == "completed"
    assert record.status == "ready"
    assert record.delivery_state == "delivered"
    payload = record.model_dump_json()
    assert "speech-event-1" not in payload
    assert "speaker-device-1" not in payload
    assert "今天客户会议怎么穿" not in payload
    assert "primary-person" not in payload


@pytest.mark.asyncio
async def test_official_turn_without_source_device_completes_and_is_audited(
    tmp_path: Path,
) -> None:
    speaker = RecordingSpeaker()
    audit = RecordingVoiceAudit()
    service, _, _ = _service(tmp_path, speaker=speaker, audit=audit)

    outcome = await service.handle(turn=_turn(source_device_id=None))

    assert outcome.status is VoiceTurnStatus.READY
    assert len(speaker.calls) == 1
    assert len(audit.records) == 1
    assert len(audit.records[0].source_device_id_digest) == 16


@pytest.mark.asyncio
async def test_service_records_recommendation_failure_stage_without_delivery(
    tmp_path: Path,
) -> None:
    speaker = RecordingSpeaker()
    audit = RecordingVoiceAudit()
    service, recommendation_service, _ = _service(
        tmp_path,
        speaker=speaker,
        context_resolver=FailingContextResolver(),
        audit=audit,
    )

    outcome = await service.handle(turn=_turn())

    assert outcome.status is VoiceTurnStatus.FAILED
    assert recommendation_service.calls == 0
    assert speaker.calls == []
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record.stage == "recommendation"
    assert record.status == "failed"
    assert record.delivery_state == "not_attempted"


@pytest.mark.asyncio
async def test_audit_sink_failure_does_not_change_voice_outcome_or_retry(
    tmp_path: Path,
) -> None:
    speaker = RecordingSpeaker()
    service, recommendation_service, _ = _service(
        tmp_path,
        speaker=speaker,
        audit=FailingVoiceAudit(),
    )

    first = await service.handle(turn=_turn())
    replay = await service.handle(turn=_turn())

    assert first.status is VoiceTurnStatus.READY
    assert replay == first
    assert recommendation_service.calls == 1
    assert len(speaker.calls) == 1


@pytest.mark.asyncio
async def test_service_audits_delivery_failure_without_retry(
    tmp_path: Path,
) -> None:
    audit = RecordingVoiceAudit()
    service, _, _ = _service(
        tmp_path,
        speaker=UnavailableSpeaker(),
        audit=audit,
    )

    outcome = await service.handle(turn=_turn())

    assert outcome.status is VoiceTurnStatus.FAILED
    assert len(audit.records) == 1
    record = audit.records[0]
    assert record.stage == "delivery"
    assert record.status == "failed"
    assert record.delivery_state == "failed"
    assert record.error_code == "speaker_delivery_failed"


@pytest.mark.asyncio
async def test_service_audits_replay_without_repeating_delivery(
    tmp_path: Path,
) -> None:
    speaker = RecordingSpeaker()
    audit = RecordingVoiceAudit()
    service, _, _ = _service(tmp_path, speaker=speaker, audit=audit)
    turn = _turn()

    await service.handle(turn=turn)
    await service.handle(turn=turn)

    assert len(speaker.calls) == 1
    assert [record.stage for record in audit.records] == ["completed", "replay"]
    assert audit.records[-1].delivery_state == "replayed"
