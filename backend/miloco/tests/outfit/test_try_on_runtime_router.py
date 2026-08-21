# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contract tests for the disabled-by-default visual trigger ingress."""

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.middleware import verify_token
from miloco.outfit.visual_service import VisualReviewOutcome, VisualReviewStatus


class _RecordingVisualTriggerHandler:
    def __init__(self) -> None:
        self.triggers: list[tuple[str, str, str]] = []

    async def handle_trigger(
        self,
        *,
        trigger_id: str,
        recommendation_id: str,
        device_id: str,
    ) -> VisualReviewOutcome:
        self.triggers.append((trigger_id, recommendation_id, device_id))
        return VisualReviewOutcome(status=VisualReviewStatus.COMPLETED)


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


def _app(
    handler: _RecordingVisualTriggerHandler,
    *,
    enabled: bool = True,
    allowlist: frozenset[str] = frozenset({"camera-1"}),
) -> FastAPI:
    from miloco.outfit.try_on_runtime_router import create_visual_trigger_router

    app = FastAPI()
    app.include_router(
        create_visual_trigger_router(
            visual_handler=handler,
            enabled=enabled,
            device_allowlist=allowlist,
        )
    )
    app.dependency_overrides[verify_token] = _require_test_bearer
    return app


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "trigger_id": "trigger-1",
        "recommendation_id": "recommendation-1",
        "device_id": "camera-1",
    }
    body.update(overrides)
    return body


def test_visual_trigger_is_absent_by_default() -> None:
    handler = _RecordingVisualTriggerHandler()
    app = _app(handler, enabled=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/try-on/review",
            json=_body(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    assert handler.triggers == []


def test_visual_trigger_requires_bearer_and_allowlisted_camera() -> None:
    handler = _RecordingVisualTriggerHandler()
    app = _app(handler)

    with TestClient(app) as client:
        assert client.post("/api/outfit/try-on/review", json=_body()).status_code == 401
        assert (
            client.post(
                "/api/outfit/try-on/review",
                json=_body(device_id="camera-unknown"),
                headers={"Authorization": "Bearer test-token"},
            ).status_code
            == 403
        )
        response = client.post(
            "/api/outfit/try-on/review",
            json=_body(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "completed", "error_code": None}
    assert handler.triggers == [("trigger-1", "recommendation-1", "camera-1")]


def test_visual_trigger_rejects_owner_media_and_candidate_selectors() -> None:
    handler = _RecordingVisualTriggerHandler()
    app = _app(handler)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/try-on/review",
            json=_body(
                owner_person_id="spoofed-owner",
                media_path="C:/private/photo.jpg",
                candidate_item_ids=["not-in-snapshot"],
            ),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 422
    assert handler.triggers == []


def test_empty_camera_allowlist_keeps_visual_trigger_absent() -> None:
    handler = _RecordingVisualTriggerHandler()
    app = _app(handler, allowlist=frozenset())

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/try-on/review",
            json=_body(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 404
    assert handler.triggers == []


def test_disabled_visual_router_does_not_change_existing_health_response() -> None:
    handler = _RecordingVisualTriggerHandler()
    app = _app(handler, enabled=False)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert handler.triggers == []


def test_visual_trigger_normalizes_identifiers_before_dispatch() -> None:
    handler = _RecordingVisualTriggerHandler()
    app = _app(handler)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/try-on/review",
            json=_body(
                trigger_id=" trigger-1 ",
                recommendation_id=" recommendation-1 ",
                device_id=" camera-1 ",
            ),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert handler.triggers == [("trigger-1", "recommendation-1", "camera-1")]


@pytest.mark.parametrize(
    "field_name",
    ["trigger_id", "recommendation_id", "device_id"],
)
def test_visual_trigger_rejects_blank_normalized_identifiers(field_name: str) -> None:
    handler = _RecordingVisualTriggerHandler()
    app = _app(handler)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/try-on/review",
            json=_body(**{field_name: "   "}),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 422
    assert handler.triggers == []
