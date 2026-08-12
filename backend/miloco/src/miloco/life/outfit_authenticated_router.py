# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Authenticated, owner-bound HTTP adapter for Outfit moment projections."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, model_validator

from miloco.life.outfit_media import (
    MAX_IMAGE_BYTES,
    OutfitMediaAsset,
    OutfitMediaSourceType,
    build_media_asset,
)
from miloco.life.outfit_moment_runtime import OutfitMomentRuntime
from miloco.life.outfit_moments import OutfitMoment
from miloco.life.outfit_recommendations import (
    ConfirmedOutfitWear,
    OutfitRecommendationResult,
    OutfitScenarioInput,
)
from miloco.life.outfit_wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeCategory,
    WardrobeDraftInput,
    WardrobeItemDraft,
)
from miloco.schema.common_schema import NormalResponse

_OWNER_SELECTOR_QUERY_KEYS = frozenset(
    {"owner", "owner_person_id", "person_id", "subject", "subject_id"}
)
_PRIVATE_MEDIA_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}
_MIME_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


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


class ConfirmWardrobeDraftRequest(BaseModel):
    """User confirmation is required before a draft becomes inventory."""

    model_config = ConfigDict(extra="forbid")

    confirmed: bool


class UpdateWardrobeItemRequest(BaseModel):
    """Only item display facts are editable after confirmation."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    category: WardrobeCategory | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UpdateWardrobeItemRequest":
        if self.name is None and self.category is None:
            raise ValueError("at least one wardrobe field must be updated")
        return self


class ConfirmRecommendedWearRequest(BaseModel):
    """A user can confirm only one option from a stored recommendation."""

    model_config = ConfigDict(extra="forbid")

    recommendation_id: str
    option_id: str
    confirmation_id: str
    timezone: str = "Asia/Shanghai"
    confirmed: bool


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
        return NormalResponse(code=0, message="ok", data=_read_model(runtime, moment))

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
            data=[_read_model(runtime, moment) for moment in moments],
        )

    @router.get("/moments/{moment_id}", response_model=NormalResponse)
    def get_moment(moment_id: str) -> NormalResponse:
        moment = runtime.moment_service.get_for_owner(
            owner_person_id=runtime.primary_person_id,
            moment_id=moment_id,
        )
        if moment is None:
            raise HTTPException(status_code=404, detail="Outfit moment not found")
        return NormalResponse(code=0, message="ok", data=_read_model(runtime, moment))

    @router.post(
        "/moments/{moment_id}/media",
        response_model=NormalResponse,
        status_code=201,
    )
    async def upload_media(
        moment_id: str,
        request: Request,
        source_type: OutfitMediaSourceType = Query(default="user_upload"),
        confirmed_for_history: bool = Query(default=False),
    ) -> NormalResponse:
        if (
            runtime.moment_service.get_for_owner(
                owner_person_id=runtime.primary_person_id,
                moment_id=moment_id,
            )
            is None
        ):
            raise HTTPException(status_code=404, detail="Outfit moment not found")
        _reject_oversized_media_request(request)
        try:
            prepared = build_media_asset(
                owner_person_id=runtime.primary_person_id,
                moment_id=moment_id,
                content=await request.body(),
                mime_type=request.headers.get("content-type", "").split(
                    ";", maxsplit=1
                )[0],
                original_filename=request.headers.get("x-original-filename"),
                source_type=source_type,
                confirmed_for_history=confirmed_for_history,
                created_at_ms=int(time.time() * 1_000),
            )
            asset = runtime.media_repo.store(prepared)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return NormalResponse(code=0, message="created", data=_public_asset(asset))

    @router.get("/media/{asset_id}")
    def download_media(
        asset_id: str,
        download: bool = Query(default=False),
    ) -> FileResponse:
        asset = runtime.media_repo.get_for_owner(asset_id, runtime.primary_person_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Outfit media not found")
        path = runtime.media_repo.file_path(asset)
        if path is None:
            raise HTTPException(status_code=404, detail="Outfit media not found")
        return FileResponse(
            path,
            media_type=asset.mime_type,
            filename=_safe_download_name(asset),
            content_disposition_type="attachment" if download else "inline",
            headers=_PRIVATE_MEDIA_HEADERS,
        )

    @router.delete("/media/{asset_id}", response_model=NormalResponse)
    def delete_media(
        asset_id: str,
        confirmed: bool = Query(default=False),
    ) -> NormalResponse:
        try:
            deleted = runtime.media_repo.delete_for_owner(
                asset_id,
                runtime.primary_person_id,
                confirmed=confirmed,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not deleted:
            raise HTTPException(status_code=404, detail="Outfit media not found")
        return NormalResponse(code=0, message="deleted", data={"deleted": True})

    @router.post(
        "/wardrobe/drafts",
        response_model=NormalResponse,
        status_code=201,
    )
    def create_wardrobe_draft(payload: WardrobeDraftInput) -> NormalResponse:
        draft = runtime.wardrobe_service.create_draft(payload)
        return NormalResponse(code=0, message="pending", data=_public_draft(draft))

    @router.post(
        "/wardrobe/drafts/{draft_id}/confirm",
        response_model=NormalResponse,
    )
    def confirm_wardrobe_draft(
        draft_id: str,
        payload: ConfirmWardrobeDraftRequest,
    ) -> NormalResponse:
        try:
            item = runtime.wardrobe_service.confirm_draft(
                draft_id,
                confirmed_by_user=payload.confirmed,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return NormalResponse(code=0, message="ok", data=_public_item(item))

    @router.get("/wardrobe/drafts", response_model=NormalResponse)
    def list_wardrobe_drafts() -> NormalResponse:
        return NormalResponse(
            code=0,
            message="ok",
            data=[
                _public_draft(draft)
                for draft in runtime.wardrobe_service.list_pending_drafts()
            ],
        )

    @router.delete("/wardrobe/drafts/{draft_id}", response_model=NormalResponse)
    def discard_wardrobe_draft(
        draft_id: str,
        confirmed: bool = Query(default=False),
    ) -> NormalResponse:
        try:
            runtime.wardrobe_service.discard_draft(
                draft_id,
                confirmed_by_user=confirmed,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return NormalResponse(code=0, message="deleted", data={"deleted": True})

    @router.get("/wardrobe", response_model=NormalResponse)
    def list_wardrobe() -> NormalResponse:
        return NormalResponse(
            code=0,
            message="ok",
            data=[
                _public_item(item)
                for item in runtime.wardrobe_service.list_confirmed_items()
            ],
        )

    @router.patch("/wardrobe/{item_id}", response_model=NormalResponse)
    def update_wardrobe_item(
        item_id: str,
        payload: UpdateWardrobeItemRequest,
    ) -> NormalResponse:
        try:
            item = runtime.wardrobe_service.update_item(
                item_id,
                name=payload.name,
                category=payload.category,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return NormalResponse(code=0, message="ok", data=_public_item(item))

    @router.delete("/wardrobe/{item_id}", response_model=NormalResponse)
    def delete_wardrobe_item(
        item_id: str,
        confirmed: bool = Query(default=False),
    ) -> NormalResponse:
        try:
            runtime.wardrobe_service.delete_item(
                item_id,
                confirmed_by_user=confirmed,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return NormalResponse(code=0, message="deleted", data={"deleted": True})

    @router.post("/recommendations", response_model=NormalResponse)
    def recommend_outfit(payload: OutfitScenarioInput) -> NormalResponse:
        result = runtime.recommend_outfit(payload)
        return NormalResponse(
            code=0,
            message="ok",
            data=_public_recommendation(result),
        )

    @router.post("/wear-confirmations", response_model=NormalResponse)
    def confirm_recommended_wear(
        payload: ConfirmRecommendedWearRequest,
    ) -> NormalResponse:
        try:
            confirmation = runtime.confirm_recommended_wear(
                recommendation_id=payload.recommendation_id,
                option_id=payload.option_id,
                confirmation_id=payload.confirmation_id,
                timezone=payload.timezone,
                confirmed_by_user=payload.confirmed,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return NormalResponse(
            code=0,
            message="ok",
            data=_public_confirmed_wear(runtime, confirmation),
        )

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


def _read_model(
    runtime: OutfitMomentRuntime, moment: OutfitMoment
) -> dict[str, object]:
    """Attach user-visible review and confirmed-media references to moment facts."""
    serialized = moment.model_dump(mode="json")
    serialized.pop("owner_person_id", None)
    serialized["media_asset_ids"] = runtime.media_repo.list_asset_ids_for_moment(
        moment.owner_person_id,
        moment.moment_id,
    )
    serialized["tags"] = [
        tag.model_dump(mode="json")
        for tag in runtime.moment_service.list_tags(
            moment.moment_id,
            owner_person_id=moment.owner_person_id,
        )
    ]
    return serialized


def _reject_oversized_media_request(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length is None:
        return
    try:
        if int(content_length) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="image exceeds maximum size")
    except ValueError as error:
        raise HTTPException(status_code=422, detail="invalid content length") from error


def _public_asset(asset: OutfitMediaAsset) -> dict[str, object]:
    return asset.model_dump(
        mode="json",
        exclude={
            "owner_person_id",
            "storage_key",
            "thumbnail_storage_key",
            "sha256",
        },
    )


def _safe_download_name(asset: OutfitMediaAsset) -> str:
    date = (
        datetime.fromtimestamp(asset.created_at_ms / 1_000, tz=UTC).date().isoformat()
    )
    return f"outfit-moment-{date}.{_MIME_TO_EXTENSION[asset.mime_type]}"


def _public_draft(draft: WardrobeItemDraft) -> dict[str, object]:
    serialized = draft.model_dump(mode="json")
    serialized.pop("owner_person_id", None)
    return serialized


def _public_item(item: ConfirmedWardrobeItem) -> dict[str, object]:
    serialized = item.model_dump(mode="json")
    serialized.pop("owner_person_id", None)
    return serialized


def _public_recommendation(result: OutfitRecommendationResult) -> dict[str, object]:
    """Serialize context and inventory-only options without a person selector."""
    return result.model_dump(mode="json")


def _public_confirmed_wear(
    runtime: OutfitMomentRuntime,
    confirmation: ConfirmedOutfitWear,
) -> dict[str, object]:
    """Expose the durable IDs and public moment projection after confirmation."""
    return {
        "event_id": confirmation.event_id,
        "moment_id": confirmation.moment_id,
        "recommendation_id": confirmation.recommendation_id,
        "item_ids": list(confirmation.item_ids),
        "moment": _read_model(runtime, confirmation.moment),
    }
