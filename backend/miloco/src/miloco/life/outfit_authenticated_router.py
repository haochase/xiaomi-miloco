# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Authenticated, owner-bound HTTP adapter for Outfit moment projections."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, model_validator

from miloco.life.outfit_moment_runtime import OutfitMomentRuntime
from miloco.schema.common_schema import NormalResponse

_OWNER_SELECTOR_QUERY_KEYS = frozenset(
    {"owner", "owner_person_id", "person_id", "subject", "subject_id"}
)


class ProjectMomentRequest(BaseModel):
    """A projection request names a stored event but never an owner."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    timezone: str = "Asia/Shanghai"


class EditTagRequest(BaseModel):
    """A tag review may change copy, but cannot replace its evidence."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    narrative: str | None = None

    @model_validator(mode="after")
    def _validate_change(self) -> "EditTagRequest":
        if self.label is None and self.narrative is None:
            raise ValueError("tag edit requires label or narrative")
        return self


def build_authenticated_outfit_moment_router(
    runtime: OutfitMomentRuntime,
    *,
    authenticate: Callable[..., object],
) -> APIRouter:
    """Build the safe Outfit API surface for one configured primary person.

    The host owns service authentication. This adapter deliberately exposes no
    owner selector and no private-media endpoint; its runtime context is the
    only source of the primary person and configured persistence locations.
    """
    router = APIRouter(
        prefix="/outfit",
        tags=["Outfit"],
        dependencies=[Depends(authenticate), Depends(_reject_owner_selectors)],
    )

    @router.post("/moments/project", response_model=NormalResponse)
    def project_moment(payload: ProjectMomentRequest) -> NormalResponse:
        try:
            moment = runtime.project_confirmed_wear(
                event_id=payload.event_id,
                timezone=payload.timezone,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return NormalResponse(code=0, message="ok", data=moment.model_dump(mode="json"))

    @router.get("/moments", response_model=NormalResponse)
    def list_moments(
        limit: Literal["10", "30"] = Query(default="10"),
        since_ms: int | None = Query(default=None, ge=0),
    ) -> NormalResponse:
        moments = runtime.moment_service.list_for_owner(
            owner_person_id=runtime.primary_person_id,
            limit=int(limit),
            since_ms=since_ms,
        )
        return NormalResponse(
            code=0,
            message="ok",
            data=[moment.model_dump(mode="json") for moment in moments],
        )

    @router.get("/moments/{moment_id}", response_model=NormalResponse)
    def get_moment(moment_id: str) -> NormalResponse:
        moment = runtime.moment_service.get_for_owner(
            owner_person_id=runtime.primary_person_id,
            moment_id=moment_id,
        )
        if moment is None:
            raise HTTPException(status_code=404, detail="Outfit moment not found")
        return NormalResponse(code=0, message="ok", data=moment.model_dump(mode="json"))

    @router.post("/moments/{moment_id}/tags/refresh", response_model=NormalResponse)
    def refresh_tags(moment_id: str) -> NormalResponse:
        try:
            tags = runtime.moment_service.refresh_tags(
                moment_id,
                owner_person_id=runtime.primary_person_id,
            )
        except ValueError as error:
            raise _tag_error(error) from error
        return NormalResponse(
            code=0,
            message="ok",
            data=[tag.model_dump(mode="json") for tag in tags],
        )

    @router.post(
        "/moments/{moment_id}/tags/{tag_id}/confirm",
        response_model=NormalResponse,
    )
    def confirm_tag(moment_id: str, tag_id: str) -> NormalResponse:
        return _review_tag(
            runtime, moment_id=moment_id, tag_id=tag_id, action="confirm"
        )

    @router.post(
        "/moments/{moment_id}/tags/{tag_id}/reject",
        response_model=NormalResponse,
    )
    def reject_tag(moment_id: str, tag_id: str) -> NormalResponse:
        return _review_tag(runtime, moment_id=moment_id, tag_id=tag_id, action="reject")

    @router.patch(
        "/moments/{moment_id}/tags/{tag_id}",
        response_model=NormalResponse,
    )
    def edit_tag(
        moment_id: str,
        tag_id: str,
        payload: EditTagRequest,
    ) -> NormalResponse:
        try:
            tag = runtime.moment_service.edit_tag(
                tag_id,
                owner_person_id=runtime.primary_person_id,
                label=payload.label,
                narrative=payload.narrative,
            )
        except ValueError as error:
            raise _tag_error(error) from error
        if tag.moment_id != moment_id:
            raise HTTPException(status_code=404, detail="Outfit tag not found")
        return NormalResponse(code=0, message="ok", data=tag.model_dump(mode="json"))

    return router


def _reject_owner_selectors(request: Request) -> None:
    """Keep the configured owner out of client-controlled request selectors."""
    selected_keys = sorted(
        key for key in request.query_params if key in _OWNER_SELECTOR_QUERY_KEYS
    )
    if selected_keys:
        raise HTTPException(
            status_code=400,
            detail="Outfit owner selection is not supported by this endpoint",
        )


def _review_tag(
    runtime: OutfitMomentRuntime,
    *,
    moment_id: str,
    tag_id: str,
    action: Literal["confirm", "reject"],
) -> NormalResponse:
    try:
        tag = (
            runtime.moment_service.confirm_tag(
                tag_id,
                owner_person_id=runtime.primary_person_id,
            )
            if action == "confirm"
            else runtime.moment_service.reject_tag(
                tag_id,
                owner_person_id=runtime.primary_person_id,
            )
        )
    except ValueError as error:
        raise _tag_error(error) from error
    if tag.moment_id != moment_id:
        raise HTTPException(status_code=404, detail="Outfit tag not found")
    return NormalResponse(code=0, message="ok", data=tag.model_dump(mode="json"))


def _tag_error(error: ValueError) -> HTTPException:
    status_code = (
        404
        if str(error) in {"Outfit moment not found", "Outfit tag not found"}
        else 422
    )
    return HTTPException(status_code=status_code, detail=str(error))
