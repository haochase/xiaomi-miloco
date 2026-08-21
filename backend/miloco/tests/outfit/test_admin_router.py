# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Authenticated read-only Outfit usage API contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from miloco.middleware import verify_token
from miloco.outfit.admin_router import create_outfit_admin_usage_router
from miloco.plugins.usage import USAGE_TIMEZONE, UsageSnapshot


def _require_test_bearer(request: Request) -> None:
    if request.headers.get("Authorization") != "Bearer test-token":
        raise HTTPException(status_code=401, detail="invalid test bearer")


@dataclass
class _ReadOnlyUsageService:
    snapshot: UsageSnapshot
    reads: int = 0
    inserts: int = 0
    purges: int = 0
    providers: int = 0
    devices: int = 0

    async def get_today(self) -> UsageSnapshot:
        self.reads += 1
        return self.snapshot


def _app(snapshot: UsageSnapshot) -> tuple[FastAPI, _ReadOnlyUsageService]:
    service = _ReadOnlyUsageService(snapshot=snapshot)
    app = FastAPI()
    app.include_router(create_outfit_admin_usage_router(usage_service=service))
    app.dependency_overrides[verify_token] = _require_test_bearer
    return app, service


def test_today_requires_header_bearer_and_returns_exact_private_response() -> None:
    app, service = _app(
        UsageSnapshot(
            date=date(2026, 4, 2),
            timezone=USAGE_TIMEZONE,
            call_count=2,
            input_tokens=13,
            output_tokens=5,
            estimated_total_tokens=21,
            complete=True,
        )
    )

    with TestClient(app) as client:
        assert client.get("/api/outfit/admin/usage/today").status_code == 401
        assert (
            client.get("/api/outfit/admin/usage/today?token=test-token").status_code
            == 401
        )
        response = client.get(
            "/api/outfit/admin/usage/today",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "date": "2026-04-02",
        "timezone": "Asia/Shanghai",
        "call_count": 2,
        "input_tokens": 13,
        "output_tokens": 5,
        "estimated_total_tokens": 21,
        "complete": True,
    }
    assert set(response.json()) == {
        "date",
        "timezone",
        "call_count",
        "input_tokens",
        "output_tokens",
        "estimated_total_tokens",
        "complete",
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert service.reads == 1


@pytest.mark.parametrize(
    "snapshot",
    [
        UsageSnapshot(
            date=date(2026, 4, 2),
            timezone=USAGE_TIMEZONE,
            call_count=2,
            input_tokens=None,
            output_tokens=None,
            estimated_total_tokens=None,
            complete=False,
        ),
        UsageSnapshot(
            date=date(2026, 4, 2),
            timezone=USAGE_TIMEZONE,
            call_count=0,
            input_tokens=0,
            output_tokens=0,
            estimated_total_tokens=0,
            complete=True,
        ),
    ],
)
def test_today_preserves_incomplete_nulls_and_empty_day_zeros(
    snapshot: UsageSnapshot,
) -> None:
    app, _ = _app(snapshot)

    with TestClient(app) as client:
        response = client.get(
            "/api/outfit/admin/usage/today",
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json()["input_tokens"] == snapshot.input_tokens
    assert response.json()["output_tokens"] == snapshot.output_tokens
    assert response.json()["estimated_total_tokens"] == snapshot.estimated_total_tokens
    assert response.json()["complete"] is snapshot.complete


def test_today_has_no_selectors_and_only_reads_service() -> None:
    snapshot = UsageSnapshot(
        date=date(2026, 4, 2),
        timezone=USAGE_TIMEZONE,
        call_count=0,
        input_tokens=0,
        output_tokens=0,
        estimated_total_tokens=0,
        complete=True,
    )
    app, service = _app(snapshot)
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(app) as client:
        baseline = client.get("/api/outfit/admin/usage/today", headers=headers)
        query_selected = client.get(
            "/api/outfit/admin/usage/today?owner=private&device=camera-1",
            headers=headers,
        )
        body_selected = client.request(
            "GET",
            "/api/outfit/admin/usage/today",
            headers=headers,
            json={"model": "private-model", "database_path": "C:/private.db"},
        )

    assert baseline.json() == query_selected.json() == body_selected.json()
    assert service.reads == 3
    assert service.inserts == 0
    assert service.purges == 0
    assert service.providers == 0
    assert service.devices == 0
    operation = app.openapi()["paths"]["/api/outfit/admin/usage/today"]["get"]
    assert "requestBody" not in operation
    assert operation.get("parameters", []) == []
