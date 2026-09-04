# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Authenticated, host-injected HTTP route for Outfit recommendation snapshots."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Protocol

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from miloco.middleware import verify_token
from miloco.outfit.context import OutfitRecommendationContext
from miloco.outfit.recommendation_api import (
    CreateRecommendationRequest,
    RecommendationApiProblem,
    RecommendationSnapshot,
    snapshot_from_result,
)
from miloco.outfit.recommendation_service import OutfitRecommendationResponse

_NO_STORE_HEADER = {"Cache-Control": "private, no-store"}
_INTERNAL_ERROR_DETAIL = "outfit_request_failed"
_BEARER_PREFIX = "Bearer "


class RecommendationHandler(Protocol):
    """Owner-fixed deterministic recommendation service consumed by HTTP."""

    def recommend(
        self,
        context: OutfitRecommendationContext,
    ) -> OutfitRecommendationResponse: ...


class RecommendationSnapshotWriter(Protocol):
    """Persist one bounded snapshot using host-fixed owner and expiry policy."""

    def save(self, snapshot: RecommendationSnapshot) -> None: ...


def create_recommendation_router(
    *,
    recommendation_service: RecommendationHandler,
    snapshot_writer: RecommendationSnapshotWriter,
    snapshot_id_factory: Callable[[], str],
    clock_ms: Callable[[], int],
    ranking_version: str,
    authentication_dependency: Callable[..., object] = verify_token,
) -> APIRouter:
    """Create a route without owner, provider, media, or device request selectors."""

    router = APIRouter()

    async def authenticate(request: Request) -> bool:
        """Fail closed without forwarding host authentication implementation details."""

        authorization = request.headers.get("Authorization")
        if not isinstance(authorization, str) or not authorization.startswith(
            _BEARER_PREFIX
        ):
            return False
        if not authorization[len(_BEARER_PREFIX) :].strip():
            return False
        try:
            result = authentication_dependency(request)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            return False
        return result is None or result is True

    @router.post(
        "/api/outfit/recommendations",
        response_model=RecommendationSnapshot,
        responses={422: {"model": RecommendationApiProblem}},
    )
    async def create_recommendation(
        request: Request,
        response: Response,
        authenticated: bool = Depends(authenticate),
    ) -> RecommendationSnapshot | JSONResponse:
        if not authenticated:
            return _unauthorized_response()
        try:
            request_body = CreateRecommendationRequest.model_validate(
                await request.json()
            )
        except (ValidationError, ValueError):
            return _invalid_request_response()

        try:
            recommendation = recommendation_service.recommend(request_body.to_context())
        except Exception:
            return _internal_error_response()

        if recommendation.status == "needs_context":
            return _problem_response()

        try:
            if recommendation.result is None:
                return _internal_error_response()
            snapshot = snapshot_from_result(
                snapshot_id=snapshot_id_factory(),
                context=request_body.to_context(),
                result=recommendation.result,
                created_at_ms=clock_ms(),
                ranking_version=ranking_version,
            )
            snapshot_writer.save(snapshot)
        except Exception:
            return _internal_error_response()

        response.headers.update(_NO_STORE_HEADER)
        return snapshot

    return router


def _problem_response() -> JSONResponse:
    """Return one fixed clarification outcome without internal prompt text."""

    return JSONResponse(
        status_code=422,
        content=RecommendationApiProblem(
            code="recommendation_needs_context"
        ).model_dump(mode="json"),
        headers=_NO_STORE_HEADER,
    )


def _internal_error_response() -> JSONResponse:
    """Return one opaque server error for unexpected service failures."""

    return JSONResponse(
        status_code=500,
        content={"detail": _INTERNAL_ERROR_DETAIL},
        headers=_NO_STORE_HEADER,
    )


def _unauthorized_response() -> JSONResponse:
    """Return a private fixed authentication failure for Outfit routes."""

    return JSONResponse(
        status_code=401,
        content={"detail": "outfit_unauthorized"},
        headers=_NO_STORE_HEADER,
    )


def _invalid_request_response() -> JSONResponse:
    """Reject malformed or selector-bearing bodies without reflecting input."""

    return JSONResponse(
        status_code=422,
        content={"detail": "invalid_outfit_request"},
        headers=_NO_STORE_HEADER,
    )
