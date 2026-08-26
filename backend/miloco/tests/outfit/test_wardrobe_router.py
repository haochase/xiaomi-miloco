# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contract tests for the authenticated, host-injected Outfit wardrobe routes."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.outfit.wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeItemDraft,
    WardrobeSourceEvidence,
)
from miloco.outfit.wardrobe_repo import DuplicateWardrobeSourceError
from miloco.outfit.wardrobe_router import create_wardrobe_router


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


def _deny_test_bearer(_request: Request) -> bool:
    return False


async def _deny_async_test_bearer(_request: Request) -> bool:
    return False


def _draft() -> WardrobeItemDraft:
    return WardrobeItemDraft(
        draft_id="draft-1",
        owner_person_id="configured-owner",
        name="Navy shirt",
        category="top",
        source_evidence=(
            WardrobeSourceEvidence(source_type="manual", reference="closet shelf"),
        ),
        created_at_ms=100,
    )


def _item() -> ConfirmedWardrobeItem:
    return ConfirmedWardrobeItem(
        item_id="item-draft-1",
        owner_person_id="configured-owner",
        name="Navy shirt",
        category="top",
        source_evidence=(
            WardrobeSourceEvidence(source_type="photo", reference="private-token"),
        ),
        confirmed_at_ms=200,
        confirmed_by_user=True,
    )


@dataclass
class _RecordingWardrobeService:
    draft: WardrobeItemDraft = field(default_factory=_draft)
    item: ConfirmedWardrobeItem = field(default_factory=_item)
    create_error: Exception | None = None
    confirm_error: Exception | None = None
    calls: list[tuple[str, object]] = field(default_factory=list)

    def create_draft(
        self,
        *,
        name: str,
        category: str,
        source_evidence: tuple[WardrobeSourceEvidence, ...],
    ) -> WardrobeItemDraft:
        self.calls.append(("create", (name, category, source_evidence)))
        if self.create_error is not None:
            raise self.create_error
        return self.draft

    def confirm_draft(
        self,
        draft_id: str,
        *,
        confirmed_by_user: bool,
    ) -> ConfirmedWardrobeItem:
        self.calls.append(("confirm", (draft_id, confirmed_by_user)))
        if self.confirm_error is not None:
            raise self.confirm_error
        return self.item

    def list_pending_drafts(self) -> tuple[WardrobeItemDraft, ...]:
        self.calls.append(("list_pending", None))
        return (self.draft,)

    def list_confirmed_available_items(self) -> tuple[ConfirmedWardrobeItem, ...]:
        self.calls.append(("list_available", None))
        return (self.item,)


def _app(
    service: _RecordingWardrobeService,
    *,
    authentication_dependency=_require_test_bearer,
) -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_wardrobe_router(
            wardrobe_service=service,
            authentication_dependency=authentication_dependency,
        )
    )
    return app


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def _draft_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "Navy shirt",
        "category": "top",
        "source_evidence": [{"source_type": "manual", "reference": "closet shelf"}],
    }
    body.update(overrides)
    return body


def test_wardrobe_routes_require_header_bearer_and_return_private_responses() -> None:
    service = _RecordingWardrobeService()
    app = _app(service)

    with TestClient(app) as client:
        unauthorized = client.post("/api/outfit/wardrobe/drafts", json=_draft_body())
        created = client.post(
            "/api/outfit/wardrobe/drafts",
            json=_draft_body(),
            headers=_headers(),
        )
        pending = client.get("/api/outfit/wardrobe/drafts", headers=_headers())
        available = client.get(
            "/api/outfit/wardrobe/items/available",
            headers=_headers(),
        )
        confirmed = client.post(
            "/api/outfit/wardrobe/drafts/draft-1/confirm",
            json={"confirmed_by_user": True},
            headers=_headers(),
        )

    assert unauthorized.status_code == 401
    assert unauthorized.json() == {"detail": "outfit_unauthorized"}
    assert unauthorized.headers["cache-control"] == "private, no-store"
    assert created.status_code == 201
    assert created.json() == {
        "draft_id": "draft-1",
        "name": "Navy shirt",
        "category": "top",
        "source_types": ["manual"],
        "status": "pending",
    }
    assert pending.json()[0]["draft_id"] == "draft-1"
    assert available.json()[0]["item_id"] == "item-draft-1"
    assert confirmed.json()["availability"] == "available"
    assert all(
        response.headers["cache-control"] == "private, no-store"
        for response in (created, pending, available, confirmed)
    )
    assert [call[0] for call in service.calls] == [
        "create",
        "list_pending",
        "list_available",
        "confirm",
    ]


def test_wardrobe_authenticates_before_parsing_malformed_json() -> None:
    service = _RecordingWardrobeService()
    app = _app(service)

    with TestClient(app) as client:
        unauthorized = client.post(
            "/api/outfit/wardrobe/drafts",
            content="{",
            headers={"Content-Type": "application/json"},
        )
        malformed = client.post(
            "/api/outfit/wardrobe/drafts",
            content="{",
            headers={**_headers(), "Content-Type": "application/json"},
        )

    assert unauthorized.status_code == 401
    assert unauthorized.json() == {"detail": "outfit_unauthorized"}
    assert unauthorized.headers["cache-control"] == "private, no-store"
    assert malformed.status_code == 422
    assert malformed.json() == {"detail": "invalid_outfit_request"}
    assert malformed.headers["cache-control"] == "private, no-store"
    assert service.calls == []


def test_wardrobe_create_rejects_owner_path_and_media_selectors_before_service() -> (
    None
):
    service = _RecordingWardrobeService()
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/wardrobe/drafts",
            json=_draft_body(
                owner_person_id="spoofed-owner",
                source_path="E:/private/closet.jpg",
                raw_media="data:image/jpeg;base64,unsafe",
            ),
            headers=_headers(),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_outfit_request"}
    assert response.headers["cache-control"] == "private, no-store"
    assert "private" not in response.text
    assert service.calls == []


@pytest.mark.parametrize(
    ("create_error", "confirm_error", "path", "body", "status", "expected"),
    [
        (
            DuplicateWardrobeSourceError("E:/private/duplicate.jpg"),
            None,
            "/api/outfit/wardrobe/drafts",
            _draft_body(),
            409,
            {"code": "wardrobe_duplicate_external_source"},
        ),
        (
            None,
            ValueError("wardrobe draft not found"),
            "/api/outfit/wardrobe/drafts/draft-missing/confirm",
            {"confirmed_by_user": True},
            404,
            {"code": "wardrobe_draft_not_found"},
        ),
        (
            None,
            ValueError("wardrobe draft is no longer pending"),
            "/api/outfit/wardrobe/drafts/draft-stale/confirm",
            {"confirmed_by_user": True},
            409,
            {"code": "wardrobe_draft_confirmation_required"},
        ),
        (
            RuntimeError("E:/private/outfit.db"),
            None,
            "/api/outfit/wardrobe/drafts",
            _draft_body(),
            500,
            {"detail": "outfit_request_failed"},
        ),
    ],
)
def test_wardrobe_failures_are_fixed_and_do_not_reflect_service_details(
    create_error: Exception | None,
    confirm_error: Exception | None,
    path: str,
    body: dict[str, object],
    status: int,
    expected: dict[str, str],
) -> None:
    service = _RecordingWardrobeService(
        create_error=create_error,
        confirm_error=confirm_error,
    )
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(path, json=body, headers=_headers())

    assert response.status_code == status
    assert response.json() == expected
    assert response.headers["cache-control"] == "private, no-store"
    assert "private" not in response.text


def test_wardrobe_confirmation_requires_literal_true_before_service() -> None:
    service = _RecordingWardrobeService()
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/wardrobe/drafts/draft-1/confirm",
            json={"confirmed_by_user": False},
            headers=_headers(),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_outfit_request"}
    assert response.headers["cache-control"] == "private, no-store"
    assert service.calls == []


def test_wardrobe_confirmation_rejects_non_draft_path_identifier_before_service() -> (
    None
):
    service = _RecordingWardrobeService()
    app = _app(service)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/wardrobe/drafts/E%3Aprivate/confirm",
            json={"confirmed_by_user": True},
            headers=_headers(),
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_outfit_request"}
    assert response.headers["cache-control"] == "private, no-store"
    assert service.calls == []


@pytest.mark.parametrize(
    "authentication_dependency",
    [_deny_test_bearer, _deny_async_test_bearer],
)
def test_wardrobe_rejects_false_authentication_adapters_before_service(
    authentication_dependency,
) -> None:
    service = _RecordingWardrobeService()
    app = _app(service, authentication_dependency=authentication_dependency)

    with TestClient(app) as client:
        response = client.post(
            "/api/outfit/wardrobe/drafts",
            json=_draft_body(),
            headers=_headers(),
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "outfit_unauthorized"}
    assert response.headers["cache-control"] == "private, no-store"
    assert service.calls == []
