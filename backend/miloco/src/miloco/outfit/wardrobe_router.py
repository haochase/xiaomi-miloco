# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Authenticated, host-injected HTTP routes for Outfit wardrobe facts."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import Protocol

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from miloco.middleware import verify_token
from miloco.outfit.wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeItemDraft,
    WardrobeSourceEvidence,
)
from miloco.outfit.wardrobe_api import (
    ConfirmedWardrobeItemResponse,
    ConfirmWardrobeDraftRequest,
    CreateWardrobeDraftRequest,
    WardrobeApiProblem,
    WardrobeApiProblemCode,
    WardrobeDraftResponse,
)
from miloco.outfit.wardrobe_repo import DuplicateWardrobeSourceError

_NO_STORE_HEADER = {"Cache-Control": "private, no-store"}
_INTERNAL_ERROR_DETAIL = "outfit_request_failed"
_DRAFT_ID_PATTERN = re.compile(r"^draft-[a-z0-9]{1,64}$")
_BEARER_PREFIX = "Bearer "


class WardrobeHandler(Protocol):
    """Owner-fixed service surface consumed by the HTTP boundary."""

    def create_draft(
        self,
        *,
        name: str,
        category: str,
        source_evidence: tuple[WardrobeSourceEvidence, ...],
    ) -> WardrobeItemDraft: ...

    def confirm_draft(
        self,
        draft_id: str,
        *,
        confirmed_by_user: bool,
    ) -> ConfirmedWardrobeItem: ...

    def list_pending_drafts(self) -> tuple[WardrobeItemDraft, ...]: ...

    def list_confirmed_available_items(self) -> tuple[ConfirmedWardrobeItem, ...]: ...


def create_wardrobe_router(
    *,
    wardrobe_service: WardrobeHandler,
    authentication_dependency: Callable[..., object] = verify_token,
) -> APIRouter:
    """Create routes without accepting an owner, storage, or media selector."""

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
        "/api/outfit/wardrobe/drafts",
        response_model=WardrobeDraftResponse,
        status_code=201,
    )
    async def create_draft(
        request: Request,
        response: Response,
        authenticated: bool = Depends(authenticate),
    ) -> WardrobeDraftResponse | JSONResponse:
        if not authenticated:
            return _unauthorized_response()
        try:
            request_body = CreateWardrobeDraftRequest.model_validate(
                await request.json()
            )
        except (ValidationError, ValueError):
            return _invalid_request_response()

        try:
            draft = wardrobe_service.create_draft(
                name=request_body.name,
                category=request_body.category,
                source_evidence=request_body.source_evidence,
            )
        except DuplicateWardrobeSourceError:
            return _problem_response(
                status_code=409,
                code="wardrobe_duplicate_external_source",
            )
        except Exception:
            return _internal_error_response()

        try:
            mapped_draft = WardrobeDraftResponse.from_domain(draft)
        except Exception:
            return _internal_error_response()

        response.headers.update(_NO_STORE_HEADER)
        return mapped_draft

    @router.get(
        "/api/outfit/wardrobe/drafts",
        response_model=tuple[WardrobeDraftResponse, ...],
    )
    async def list_pending_drafts(
        response: Response,
        authenticated: bool = Depends(authenticate),
    ) -> tuple[WardrobeDraftResponse, ...] | JSONResponse:
        if not authenticated:
            return _unauthorized_response()
        try:
            drafts = tuple(
                WardrobeDraftResponse.from_domain(draft)
                for draft in wardrobe_service.list_pending_drafts()
            )
        except Exception:
            return _internal_error_response()

        response.headers.update(_NO_STORE_HEADER)
        return drafts

    @router.get(
        "/api/outfit/wardrobe/items/available",
        response_model=tuple[ConfirmedWardrobeItemResponse, ...],
    )
    async def list_confirmed_available_items(
        response: Response,
        authenticated: bool = Depends(authenticate),
    ) -> tuple[ConfirmedWardrobeItemResponse, ...] | JSONResponse:
        if not authenticated:
            return _unauthorized_response()
        try:
            items = tuple(
                ConfirmedWardrobeItemResponse.from_domain(item)
                for item in wardrobe_service.list_confirmed_available_items()
            )
        except Exception:
            return _internal_error_response()

        response.headers.update(_NO_STORE_HEADER)
        return items

    @router.post(
        "/api/outfit/wardrobe/drafts/{draft_id}/confirm",
        response_model=ConfirmedWardrobeItemResponse,
    )
    async def confirm_draft(
        draft_id: str,
        request: Request,
        response: Response,
        authenticated: bool = Depends(authenticate),
    ) -> ConfirmedWardrobeItemResponse | JSONResponse:
        if not authenticated:
            return _unauthorized_response()
        if not _DRAFT_ID_PATTERN.fullmatch(draft_id):
            return _invalid_request_response()
        try:
            request_body = ConfirmWardrobeDraftRequest.model_validate(
                await request.json()
            )
        except (ValidationError, ValueError):
            return _invalid_request_response()

        try:
            item = wardrobe_service.confirm_draft(
                draft_id,
                confirmed_by_user=request_body.confirmed_by_user,
            )
        except DuplicateWardrobeSourceError:
            return _problem_response(
                status_code=409,
                code="wardrobe_duplicate_external_source",
            )
        except ValueError as exc:
            if str(exc) == "wardrobe draft not found":
                return _problem_response(
                    status_code=404,
                    code="wardrobe_draft_not_found",
                )
            return _problem_response(
                status_code=409,
                code="wardrobe_draft_confirmation_required",
            )
        except Exception:
            return _internal_error_response()

        try:
            mapped_item = ConfirmedWardrobeItemResponse.from_domain(item)
        except Exception:
            return _internal_error_response()

        response.headers.update(_NO_STORE_HEADER)
        return mapped_item

    return router


def _problem_response(
    *,
    status_code: int,
    code: WardrobeApiProblemCode,
) -> JSONResponse:
    """Return a fixed business failure without reflecting internal details."""

    return JSONResponse(
        status_code=status_code,
        content=WardrobeApiProblem(code=code).model_dump(mode="json"),
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
