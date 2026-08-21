# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contract tests for the disabled-by-default authenticated Outfit voice ingress."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.middleware import verify_token
from miloco.outfit.voice_contracts import (
    OutfitVoiceOutcome,
    TrustedSpeechTurn,
    VoiceTurnStatus,
)
from miloco.outfit.voice_router import create_authenticated_voice_router


class _RecordingVoiceService:
    def __init__(self) -> None:
        self.turns: list[TrustedSpeechTurn] = []

    async def handle(self, *, turn: TrustedSpeechTurn) -> OutfitVoiceOutcome:
        self.turns.append(turn)
        return OutfitVoiceOutcome(
            status=VoiceTurnStatus.READY,
            response_text="已为你选好第一套库存穿搭，查看更多请打开面板。",
        )


def _app(
    service: _RecordingVoiceService,
    *,
    enabled: bool = True,
    source_device_id: str | None = "bridge-device-1",
) -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(
        create_authenticated_voice_router(
            voice_service=service,
            enabled=enabled,
            source_device_id=source_device_id,
            now_ms=lambda: 1_700_000_000_100,
        )
    )
    app.dependency_overrides[verify_token] = _require_test_bearer
    return app


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "event_id": "bridge-event-1",
        "text": "今天客户会议怎么穿",
        "observed_at_ms": 1_700_000_000_000,
        "room_id": "living-room",
        "is_complete": True,
    }
    body.update(overrides)
    return body


def test_voice_ingress_is_absent_by_default_and_does_not_affect_health() -> None:
    service = _RecordingVoiceService()
    app = _app(service, enabled=False)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"ok": True}
        response = client.post(
            "/api/outfit/voice/turn",
            json=_body(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    assert service.turns == []


def test_voice_ingress_requires_bearer_and_binds_configured_bridge_device() -> None:
    service = _RecordingVoiceService()
    app = _app(service)

    with TestClient(app) as client:
        assert client.post("/api/outfit/voice/turn", json=_body()).status_code == 401
        assert (
            client.post(
                "/api/outfit/voice/turn",
                json=_body(source_device_id="caller-selected-device"),
                headers={"Authorization": "Bearer test-token"},
            ).status_code
            == 422
        )
        response = client.post(
            "/api/outfit/voice/turn",
            json=_body(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "message": "已为你选好第一套库存穿搭，查看更多请打开面板。",
    }
    assert len(service.turns) == 1
    assert service.turns[0].source_kind == "authenticated_asr_bridge"
    assert service.turns[0].source_device_id == "bridge-device-1"
    assert service.turns[0].received_at_ms == 1_700_000_000_100


def test_voice_ingress_rejects_owner_and_source_kind_selectors_from_request() -> None:
    service = _RecordingVoiceService()
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/voice/turn",
            json=_body(
                owner_person_id="spoofed-owner", source_kind="official_perception"
            ),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 422
    assert service.turns == []


def test_voice_ingress_requires_complete_literal_true() -> None:
    service = _RecordingVoiceService()
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/voice/turn",
            json=_body(is_complete=False),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 422
    assert service.turns == []


@pytest.mark.parametrize("source_device_id", [None, "   "])
def test_missing_configured_bridge_device_keeps_voice_ingress_absent(
    source_device_id: str | None,
) -> None:
    service = _RecordingVoiceService()
    app = _app(service, source_device_id=source_device_id)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/voice/turn",
            json=_body(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    assert service.turns == []
