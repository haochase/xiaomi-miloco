# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Owner-bound HTTP contracts for configured Outfit moment persistence."""

from io import BytesIO
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
from PIL import Image


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


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(40, 80, 120)).save(output, format="JPEG")
    return output.getvalue()


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
    assert "owner_person_id" not in projected.json()["data"]
    assert listed.status_code == 200
    assert [moment["moment_id"] for moment in listed.json()["data"]] == [moment_id]
    assert "owner_person_id" not in listed.json()["data"][0]
    assert detail.status_code == 200
    assert "owner_person_id" not in detail.json()["data"]


def test_router_exposes_confirmed_media_only_through_authenticated_private_routes(
    tmp_path: Path,
) -> None:
    client, token = _client(tmp_path)
    headers = {"Authorization": token}
    projected = client.post(
        "/api/outfit/moments/project",
        json={"event_id": "wear-1", "timezone": "Asia/Shanghai"},
        headers=headers,
    )
    moment_id = projected.json()["data"]["moment_id"]

    unconfirmed = client.post(
        f"/api/outfit/moments/{moment_id}/media",
        content=_jpeg_bytes(),
        headers={**headers, "content-type": "image/jpeg"},
    )
    confirmed = client.post(
        f"/api/outfit/moments/{moment_id}/media",
        params={"confirmed_for_history": "true"},
        content=_jpeg_bytes(),
        headers={
            **headers,
            "content-type": "image/jpeg",
            "x-original-filename": "../../private-photo.jpg",
        },
    )
    asset_id = confirmed.json()["data"]["asset_id"]
    detail = client.get(f"/api/outfit/moments/{moment_id}", headers=headers)
    unauthorized = client.get(f"/api/outfit/media/{asset_id}")
    foreign_selector = client.get(
        f"/api/outfit/media/{asset_id}",
        params={"owner_person_id": "other-person"},
        headers=headers,
    )
    downloaded = client.get(
        f"/api/outfit/media/{asset_id}",
        params={"download": "true"},
        headers=headers,
    )

    assert unconfirmed.status_code == 201
    assert confirmed.status_code == 201
    assert "owner_person_id" not in confirmed.json()["data"]
    assert "storage_key" not in confirmed.json()["data"]
    assert "thumbnail_storage_key" not in confirmed.json()["data"]
    assert "sha256" not in confirmed.json()["data"]
    assert detail.json()["data"]["media_asset_ids"] == [asset_id]
    assert detail.json()["data"]["tags"] == []
    assert unauthorized.status_code == 401
    assert foreign_selector.status_code == 400
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["content-disposition"].startswith("attachment;")


def test_router_requires_explicit_confirmation_to_delete_private_media(
    tmp_path: Path,
) -> None:
    client, token = _client(tmp_path)
    headers = {"Authorization": token}
    projected = client.post(
        "/api/outfit/moments/project",
        json={"event_id": "wear-1", "timezone": "Asia/Shanghai"},
        headers=headers,
    )
    moment_id = projected.json()["data"]["moment_id"]
    uploaded = client.post(
        f"/api/outfit/moments/{moment_id}/media",
        params={"confirmed_for_history": "true"},
        content=_jpeg_bytes(),
        headers={**headers, "content-type": "image/jpeg"},
    )
    asset_id = uploaded.json()["data"]["asset_id"]
    missing_confirmation = client.delete(
        f"/api/outfit/media/{asset_id}",
        headers={"Authorization": token},
    )
    deleted = client.delete(
        f"/api/outfit/media/{asset_id}",
        params={"confirmed": "true"},
        headers={"Authorization": token},
    )
    absent = client.get(
        f"/api/outfit/media/{asset_id}",
        headers={"Authorization": token},
    )

    assert missing_confirmation.status_code == 422
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {"deleted": True}
    assert absent.status_code == 404


def test_router_keeps_wardrobe_drafts_pending_until_the_primary_user_confirms(
    tmp_path: Path,
) -> None:
    client, token = _client(tmp_path)
    headers = {"Authorization": token}

    draft = client.post(
        "/api/outfit/wardrobe/drafts",
        json={
            "name": "navy cotton shirt",
            "category": "top",
            "source_type": "manual",
            "source_reference": "navy shirt from closet",
        },
        headers=headers,
    )
    before_confirmation = client.get("/api/outfit/wardrobe", headers=headers)
    draft_id = draft.json()["data"]["draft_id"]
    confirmed = client.post(
        f"/api/outfit/wardrobe/drafts/{draft_id}/confirm",
        json={"confirmed": True},
        headers=headers,
    )
    after_confirmation = client.get("/api/outfit/wardrobe", headers=headers)

    assert draft.status_code == 201
    assert draft.json()["data"]["status"] == "pending"
    assert "owner_person_id" not in draft.json()["data"]
    assert before_confirmation.json()["data"] == []
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["name"] == "navy cotton shirt"
    assert (
        after_confirmation.json()["data"][0]["item_id"]
        == confirmed.json()["data"]["item_id"]
    )


def test_router_rejects_wardrobe_owner_selectors(tmp_path: Path) -> None:
    client, token = _client(tmp_path)

    response = client.get(
        "/api/outfit/wardrobe",
        params={"owner_person_id": "other-person"},
        headers={"Authorization": token},
    )

    assert response.status_code == 400


def test_router_requires_confirmation_for_pending_draft_and_inventory_deletion(
    tmp_path: Path,
) -> None:
    client, token = _client(tmp_path)
    headers = {"Authorization": token}
    draft = client.post(
        "/api/outfit/wardrobe/drafts",
        json={
            "name": "navy cotton shirt",
            "category": "top",
            "source_type": "manual",
            "source_reference": "navy shirt from closet",
        },
        headers=headers,
    )
    draft_id = draft.json()["data"]["draft_id"]

    pending = client.get("/api/outfit/wardrobe/drafts", headers=headers)
    missing_discard_confirmation = client.delete(
        f"/api/outfit/wardrobe/drafts/{draft_id}",
        headers=headers,
    )
    discarded = client.delete(
        f"/api/outfit/wardrobe/drafts/{draft_id}",
        params={"confirmed": "true"},
        headers=headers,
    )

    assert pending.status_code == 200
    assert pending.json()["data"][0]["draft_id"] == draft_id
    assert missing_discard_confirmation.status_code == 422
    assert discarded.json()["data"] == {"deleted": True}


def test_router_allows_primary_user_to_correct_or_explicitly_delete_inventory(
    tmp_path: Path,
) -> None:
    client, token = _client(tmp_path)
    headers = {"Authorization": token}
    draft = client.post(
        "/api/outfit/wardrobe/drafts",
        json={
            "name": "navy cotton shirt",
            "category": "top",
            "source_type": "manual",
            "source_reference": "navy shirt from closet",
        },
        headers=headers,
    )
    item = client.post(
        f"/api/outfit/wardrobe/drafts/{draft.json()['data']['draft_id']}/confirm",
        json={"confirmed": True},
        headers=headers,
    )
    item_id = item.json()["data"]["item_id"]

    updated = client.patch(
        f"/api/outfit/wardrobe/{item_id}",
        json={"name": "navy linen shirt", "category": "outerwear"},
        headers=headers,
    )
    missing_delete_confirmation = client.delete(
        f"/api/outfit/wardrobe/{item_id}",
        headers=headers,
    )
    deleted = client.delete(
        f"/api/outfit/wardrobe/{item_id}",
        params={"confirmed": "true"},
        headers=headers,
    )

    assert updated.json()["data"]["name"] == "navy linen shirt"
    assert updated.json()["data"]["source_reference"] == "navy shirt from closet"
    assert missing_delete_confirmation.status_code == 422
    assert deleted.json()["data"] == {"deleted": True}


def test_router_returns_inventory_only_recommendations_and_projects_confirmed_wear(
    tmp_path: Path,
) -> None:
    client, token = _client(tmp_path)
    headers = {"Authorization": token}

    def confirm_item(name: str, category: str) -> None:
        draft = client.post(
            "/api/outfit/wardrobe/drafts",
            json={
                "name": name,
                "category": category,
                "source_type": "manual",
                "source_reference": f"closet:{name}",
            },
            headers=headers,
        )
        client.post(
            f"/api/outfit/wardrobe/drafts/{draft.json()['data']['draft_id']}/confirm",
            json={"confirmed": True},
            headers=headers,
        )

    confirm_item("navy cotton shirt", "top")
    confirm_item("white linen shirt", "top")
    confirm_item("charcoal trousers", "bottom")
    confirm_item("black loafers", "shoes")

    missing_context = client.post(
        "/api/outfit/recommendations",
        json={},
        headers=headers,
    )
    recommendation = client.post(
        "/api/outfit/recommendations",
        json={"occasion": "team meeting"},
        headers=headers,
    )
    result = recommendation.json()["data"]
    confirmation = client.post(
        "/api/outfit/wear-confirmations",
        json={
            "recommendation_id": result["recommendation_id"],
            "option_id": result["options"][0]["option_id"],
            "confirmation_id": "team-meeting-20260812",
            "timezone": "Asia/Shanghai",
            "confirmed": True,
        },
        headers=headers,
    )
    replayed = client.post(
        "/api/outfit/wear-confirmations",
        json={
            "recommendation_id": result["recommendation_id"],
            "option_id": result["options"][0]["option_id"],
            "confirmation_id": "team-meeting-20260812",
            "timezone": "Asia/Shanghai",
            "confirmed": True,
        },
        headers=headers,
    )

    assert missing_context.status_code == 200
    assert missing_context.json()["data"] == {
        "status": "needs_context",
        "recommendation_id": None,
        "options": [],
        "missing_context": ["occasion_or_activity"],
        "inventory_hints": [],
    }
    assert recommendation.status_code == 200
    assert result["status"] == "ready"
    assert len(result["options"]) == 2
    assert "owner_person_id" not in result
    assert confirmation.status_code == 200
    assert replayed.json()["data"] == confirmation.json()["data"]
    assert "owner_person_id" not in confirmation.json()["data"]["moment"]


def test_router_requires_explicit_wear_confirmation_and_rejects_owner_selector(
    tmp_path: Path,
) -> None:
    client, token = _client(tmp_path)

    owner_query = client.post(
        "/api/outfit/recommendations",
        params={"owner_person_id": "other-person"},
        json={"occasion": "team meeting"},
        headers={"Authorization": token},
    )
    unconfirmed = client.post(
        "/api/outfit/wear-confirmations",
        json={
            "recommendation_id": "recommendation-1",
            "option_id": "option-1",
            "confirmation_id": "not-confirmed",
            "confirmed": False,
        },
        headers={"Authorization": token},
    )

    assert owner_query.status_code == 400
    assert unconfirmed.status_code == 422
