# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contract tests for the authenticated, host-injected Outfit recommendation route."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.context import OutfitClarification, OutfitRecommendationContext
from miloco.outfit.ranking import RankedOutfitOption, RankingScoreComponent
from miloco.outfit.recommendation import OutfitRecommendationResult
from miloco.outfit.recommendation_router import create_recommendation_router
from miloco.outfit.recommendation_service import OutfitRecommendationResponse


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


def _deny_test_bearer(_request: Request) -> bool:
    return False


async def _deny_async_test_bearer(_request: Request) -> bool:
    return False


def _option(*item_ids: str) -> RankedOutfitOption:
    return RankedOutfitOption(
        candidate=OutfitCandidate(item_ids=item_ids, pattern="top_bottom_shoes"),
        score=100,
        score_components=(
            RankingScoreComponent(
                name="inventory_complete",
                value=100,
                explanation="internal explanation",
            ),
        ),
        rationale=("internal ranking rationale",),
    )


def _ready_response() -> OutfitRecommendationResponse:
    return OutfitRecommendationResponse(
        status="ready",
        result=OutfitRecommendationResult(
            status="ready",
            options=(
                _option("item-top", "item-bottom", "item-shoes"),
                _option("item-dress", "item-shoes"),
            ),
            message="internal result message",
        ),
    )


def _insufficient_response() -> OutfitRecommendationResponse:
    return OutfitRecommendationResponse(
        status="insufficient_inventory",
        result=OutfitRecommendationResult(
            status="insufficient_inventory",
            options=(),
            message="internal sparse inventory message",
        ),
    )


def _needs_context_response() -> OutfitRecommendationResponse:
    return OutfitRecommendationResponse(
        status="needs_context",
        clarification=OutfitClarification(
            field="occasion_or_activity",
            prompt="internal prompt",
        ),
    )


@dataclass
class _RecordingRecommendationService:
    response: OutfitRecommendationResponse = field(default_factory=_ready_response)
    error: Exception | None = None
    contexts: list[OutfitRecommendationContext] = field(default_factory=list)

    def recommend(
        self,
        context: OutfitRecommendationContext,
    ) -> OutfitRecommendationResponse:
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        return self.response


def _app(
    service: _RecordingRecommendationService,
    *,
    snapshot_ids: list[str] | None = None,
    authentication_dependency=_require_test_bearer,
) -> FastAPI:
    ids = iter(snapshot_ids or ["rec-router-1"])
    app = FastAPI()
    app.include_router(
        create_recommendation_router(
            recommendation_service=service,
            snapshot_id_factory=lambda: next(ids),
            clock_ms=lambda: 321,
            ranking_version="deterministic-v1",
            authentication_dependency=authentication_dependency,
        )
    )
    return app


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"occasion": "commute", "day_kind": "workday"}
    body.update(overrides)
    return body


def test_recommendation_requires_bearer_and_uses_host_snapshot_values() -> None:
    service = _RecordingRecommendationService()
    app = _app(service)

    with TestClient(app) as client:
        unauthorized = client.post("/api/outfit/recommendations", json=_body())
        response = client.post(
            "/api/outfit/recommendations",
            json=_body(),
            headers=_headers(),
        )

    assert unauthorized.status_code == 401
    assert unauthorized.json() == {"detail": "outfit_unauthorized"}
    assert unauthorized.headers["cache-control"] == "private, no-store"
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "snapshot_id": "rec-router-1",
        "context": {
            "occasion": "commute",
            "activity": None,
            "day_kind": "workday",
        },
        "status": "ready",
        "option_item_ids": [
            ["item-top", "item-bottom", "item-shoes"],
            ["item-dress", "item-shoes"],
        ],
        "ranking_version": "deterministic-v1",
        "created_at_ms": 321,
    }
    assert service.contexts == [
        OutfitRecommendationContext(occasion="commute", day_kind="workday")
    ]
    assert "internal" not in response.text


def test_recommendation_authenticates_before_parsing_malformed_json() -> None:
    service = _RecordingRecommendationService()
    app = _app(service)

    with TestClient(app) as client:
        unauthorized = client.post(
            "/api/outfit/recommendations",
            content="{",
            headers={"Content-Type": "application/json"},
        )
        malformed = client.post(
            "/api/outfit/recommendations",
            content="{",
            headers={**_headers(), "Content-Type": "application/json"},
        )

    assert unauthorized.status_code == 401
    assert unauthorized.json() == {"detail": "outfit_unauthorized"}
    assert unauthorized.headers["cache-control"] == "private, no-store"
    assert malformed.status_code == 422
    assert malformed.json() == {"detail": "invalid_outfit_request"}
    assert malformed.headers["cache-control"] == "private, no-store"
    assert service.contexts == []


def test_recommendation_rejects_owner_provider_and_media_selectors_before_service() -> (
    None
):
    service = _RecordingRecommendationService()
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/recommendations",
            json=_body(
                owner_person_id="spoofed-owner",
                provider_model="private-model",
                media_path="E:/private/photo.jpg",
            ),
            headers=_headers(),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_outfit_request"}
    assert response.headers["cache-control"] == "private, no-store"
    assert "private" not in response.text
    assert service.contexts == []


def test_needs_context_returns_fixed_problem_without_allocating_snapshot() -> None:
    service = _RecordingRecommendationService(response=_needs_context_response())
    snapshot_calls = 0

    def snapshot_id_factory() -> str:
        nonlocal snapshot_calls
        snapshot_calls += 1
        return "rec-unused"

    app = FastAPI()
    app.include_router(
        create_recommendation_router(
            recommendation_service=service,
            snapshot_id_factory=snapshot_id_factory,
            clock_ms=lambda: 321,
            ranking_version="deterministic-v1",
            authentication_dependency=_require_test_bearer,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/recommendations",
            json={},
            headers=_headers(),
        )

    assert response.status_code == 422
    assert response.json() == {"code": "recommendation_needs_context"}
    assert response.headers["cache-control"] == "private, no-store"
    assert snapshot_calls == 0


def test_insufficient_inventory_returns_nonpersistent_empty_snapshot() -> None:
    service = _RecordingRecommendationService(response=_insufficient_response())
    app = _app(service, snapshot_ids=["rec-sparse-1"])

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/recommendations",
            json=_body(activity="walk"),
            headers=_headers(),
        )

    assert response.status_code == 200
    assert response.json()["snapshot_id"] == "rec-sparse-1"
    assert response.json()["status"] == "insufficient_inventory"
    assert response.json()["option_item_ids"] == []


def test_recommendation_failure_is_fixed_and_does_not_reflect_internal_detail() -> None:
    service = _RecordingRecommendationService(
        error=RuntimeError("E:/private/provider-response.json")
    )
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/recommendations",
            json=_body(),
            headers=_headers(),
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "outfit_request_failed"}
    assert response.headers["cache-control"] == "private, no-store"
    assert "private" not in response.text


@pytest.mark.parametrize(
    "authentication_dependency",
    [_deny_test_bearer, _deny_async_test_bearer],
)
def test_recommendation_rejects_false_authentication_adapters_before_service(
    authentication_dependency,
) -> None:
    service = _RecordingRecommendationService()
    app = _app(service, authentication_dependency=authentication_dependency)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/recommendations",
            json=_body(),
            headers=_headers(),
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "outfit_unauthorized"}
    assert response.headers["cache-control"] == "private, no-store"
    assert service.contexts == []
