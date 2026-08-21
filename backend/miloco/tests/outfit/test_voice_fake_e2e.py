# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Synthetic composition test for the Outfit authenticated voice path."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.middleware import verify_token
from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.context import OutfitRecommendationContext
from miloco.outfit.ranking import rank_outfit_candidates
from miloco.outfit.recommendation import build_recommendation_result
from miloco.outfit.recommendation_service import OutfitRecommendationResponse
from miloco.outfit.storage import OutfitStorage
from miloco.outfit.voice_event_repo import VoiceEventRepository
from miloco.outfit.voice_router import create_authenticated_voice_router
from miloco.outfit.voice_service import OutfitVoiceTurnService
from miloco.outfit.xiaomi_speaker_adapter import XiaomiSpeakerAdapter


class _FixedContextResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, turn: object) -> OutfitRecommendationContext:
        self.calls += 1
        return OutfitRecommendationContext(
            occasion="client meeting", day_kind="workday"
        )


class _FixedRecommendationService:
    def __init__(self) -> None:
        self.calls = 0
        self.primary_person_id = "configured-primary-person"

    def recommend(
        self,
        context: OutfitRecommendationContext,
    ) -> OutfitRecommendationResponse:
        self.calls += 1
        return OutfitRecommendationResponse(
            status="ready",
            result=build_recommendation_result(
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
            ),
        )


class _RecordingMiotActionPort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    async def call_action(
        self,
        *,
        device_id: str,
        action_name: str,
        params: tuple[str, ...],
    ) -> None:
        self.calls.append((device_id, action_name, params))


def _app(
    tmp_path: Path,
) -> tuple[
    FastAPI,
    _FixedContextResolver,
    _FixedRecommendationService,
    _RecordingMiotActionPort,
]:
    context_resolver = _FixedContextResolver()
    recommendation_service = _FixedRecommendationService()
    action_port = _RecordingMiotActionPort()
    voice_service = OutfitVoiceTurnService(
        primary_person_id="configured-primary-person",
        context_resolver=context_resolver,
        recommendation_service=recommendation_service,
        event_repository=VoiceEventRepository(
            OutfitStorage(tmp_path / "outfit" / "voice-events.db")
        ),
        speaker=XiaomiSpeakerAdapter(action_port, speaker_device_id="speaker-1"),
        speaker_device_id="speaker-1",
        delivery_timeout_s=1.0,
    )
    app = FastAPI()
    app.include_router(
        create_authenticated_voice_router(
            voice_service=voice_service,
            enabled=True,
            source_device_id="authenticated-bridge-1",
            now_ms=lambda: 1_700_000_000_100,
        )
    )
    app.dependency_overrides[verify_token] = _require_test_bearer
    return app, context_resolver, recommendation_service, action_port


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


def test_authenticated_turn_recommends_and_plays_once_then_replays(
    tmp_path: Path,
) -> None:
    app, context_resolver, recommendation_service, action_port = _app(tmp_path)
    body = {
        "event_id": "bridge-event-1",
        "text": "今天客户会议怎么穿",
        "observed_at_ms": 1_700_000_000_000,
        "is_complete": True,
    }

    with TestClient(app) as client:
        first = client.post(
            "/api/outfit/voice/turn",
            json=body,
            headers={"Authorization": "Bearer test-token"},
        )
        replay = client.post(
            "/api/outfit/voice/turn",
            json=body,
            headers={"Authorization": "Bearer test-token"},
        )

    assert first.status_code == 200
    assert replay.json() == first.json()
    assert context_resolver.calls == 1
    assert recommendation_service.calls == 1
    assert action_port.calls == [
        (
            "speaker-1",
            "play-text",
            ("已为你选好第一套库存穿搭，查看更多请打开面板。",),
        )
    ]
