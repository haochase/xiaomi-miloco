# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Owner-bound HTTP contracts for configured Outfit moment persistence."""

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from miloco.life.outfit_authenticated_router import (
    build_authenticated_outfit_moment_router,
)
from miloco.life.outfit_feedback_events import OutfitFeedbackEvent
from miloco.life.outfit_installation import OutfitRuntimeContext
from miloco.life.outfit_moment_runtime import build_outfit_moment_runtime


def _require_test_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test token")


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    workspace_dir = tmp_path / "miloco-home"
    workspace_dir.mkdir()
    runtime = build_outfit_moment_runtime(
        OutfitRuntimeContext(
            primary_person_id="primary-person",
            workspace_dir=workspace_dir,
            storage_dir=workspace_dir / "outfit",
        ),
        clock_ms=lambda: 2_000,
    )
    runtime.feedback_event_repo.append(
        OutfitFeedbackEvent(
            event_id="wear-1",
            owner_person_id="primary-person",
            event_type="wear_confirmed",
            recommendation_id="recommendation-1",
            item_ids=("top-1", "bottom-1", "shoes-1"),
            occurred_at_ms=1_000,
            confirmed_by_user=True,
        )
    )
    app = FastAPI()
    app.include_router(
        build_authenticated_outfit_moment_router(
            runtime,
            authenticate=_require_test_token,
        ),
        prefix="/api",
    )
    return TestClient(app), "Bearer test-token"


def test_router_requires_the_injected_service_authentication(tmp_path: Path) -> None:
    client, token = _client(tmp_path)

    missing = client.get("/api/outfit/moments")
    invalid = client.get(
        "/api/outfit/moments",
        headers={"Authorization": "Bearer wrong-token"},
    )
    authenticated = client.get(
        "/api/outfit/moments",
        headers={"Authorization": token},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert authenticated.status_code == 200
    assert authenticated.json()["data"] == []


def test_router_binds_moment_requests_to_the_configured_primary_owner(
    tmp_path: Path,
) -> None:
    client, token = _client(tmp_path)
    headers = {"Authorization": token}

    rejected_query = client.post(
        "/api/outfit/moments/project",
        params={"owner_person_id": "another-person"},
        json={"event_id": "wear-1", "timezone": "Asia/Shanghai"},
        headers=headers,
    )
    rejected_body = client.post(
        "/api/outfit/moments/project",
        json={
            "event_id": "wear-1",
            "timezone": "Asia/Shanghai",
            "owner_person_id": "another-person",
        },
        headers=headers,
    )
    projected = client.post(
        "/api/outfit/moments/project",
        json={"event_id": "wear-1", "timezone": "Asia/Shanghai"},
        headers=headers,
    )
    moment_id = projected.json()["data"]["moment_id"]
    listed = client.get("/api/outfit/moments", headers=headers)
    detail = client.get(f"/api/outfit/moments/{moment_id}", headers=headers)

    assert rejected_query.status_code == 400
    assert rejected_body.status_code == 422
    assert projected.status_code == 200
    assert projected.json()["data"]["owner_person_id"] == "primary-person"
    assert listed.status_code == 200
    assert [moment["moment_id"] for moment in listed.json()["data"]] == [moment_id]
    assert detail.status_code == 200
    assert detail.json()["data"]["owner_person_id"] == "primary-person"
