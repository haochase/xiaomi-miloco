# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""FastAPI router seam for life-agent hackathon demo flows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator, model_validator

from miloco.life.camera_voice import (
    CameraVoiceListenPayload,
)
from miloco.life.camera_voice import (
    run_camera_voice_listen as run_camera_voice_listen_service,
)
from miloco.life.notify import LifeNotifyRequest, deliver_life_notification
from miloco.life.scene_trigger import LifeSceneIntent, LifeSceneTriggerPayload
from miloco.life.scene_trigger import (
    run_life_scene_trigger as run_life_scene_trigger_service,
)
from miloco.life.schema import LifeDomain
from miloco.life.service import (
    LIFE_TRIGGER_SOURCES,
    summarize_life_history,
)
from miloco.life.service import (
    run_life_demo as run_life_demo_service,
)
from miloco.life.service import (
    run_life_live_demo as run_life_live_demo_service,
)
from miloco.life.service import (
    run_life_text_trigger as run_life_text_trigger_service,
)
from miloco.life.service import (
    run_life_trigger as run_life_trigger_service,
)
from miloco.life.voice_session import (
    DEFAULT_CAMERA_CHANNEL,
    DEFAULT_CAMERA_DURATION_MS,
)
from miloco.life.voice_session import (
    run_life_voice_command as run_life_voice_command_service,
)
from miloco.middleware import verify_token
from miloco.schema.common_schema import NormalResponse

router = APIRouter(prefix="/life", tags=["Life"])


class LifeDemoRequest(BaseModel):
    mimo_payload: dict[str, Any] | str
    occasion: str = "tomorrow morning interview"
    weather: str | None = "cool and cloudy"
    people_count: int = 3
    time_budget_minutes: int = 30
    persist: bool = False
    db_path: str | None = None


class LifeLiveDemoRequest(BaseModel):
    source_id: str = "live_mimo_demo"
    prompt: str = (
        "Extract visible clothing, shoes, bags, accessories, ingredients, fridge "
        "items, or kitchen items for outfit and cooking recommendations."
    )
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str = "today outing"
    weather: str | None = None
    people_count: int = 1
    time_budget_minutes: int = 30
    persist: bool = False
    db_path: str | None = None

    @model_validator(mode="after")
    def _require_live_input(self) -> "LifeLiveDemoRequest":
        if self.clip_base64 is None and self.mimo_payload is None:
            raise ValueError("clip_base64 or mimo_payload is required")
        return self


class LifeTriggerRequest(BaseModel):
    trigger_source: str
    domain: LifeDomain | None = None
    text: str | None = None
    source_id: str | None = None
    prompt: str | None = (
        "Extract only the assets needed for this explicit life-agent request."
    )
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str = "today outing"
    weather: str | None = None
    people_count: int = 1
    time_budget_minutes: int = 30
    persist: bool = True
    db_path: str | None = None

    @model_validator(mode="after")
    def _validate_on_demand_trigger(self) -> "LifeTriggerRequest":
        if self.trigger_source not in LIFE_TRIGGER_SOURCES:
            raise ValueError(
                "trigger_source must be manual, voice_intent, schedule, or device_state"
            )
        if self.domain is None and not (self.text and self.text.strip()):
            raise ValueError("domain or text is required")
        if self.text is not None:
            self.text = self.text.strip()
        return self


class LifeTextTriggerRequest(BaseModel):
    text: str
    trigger_source: str = "voice_intent"
    source_id: str | None = None
    prompt: str | None = None
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str = "today outing"
    weather: str | None = None
    people_count: int = 1
    time_budget_minutes: int = 30
    persist: bool = True
    db_path: str | None = None

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_text_trigger(self) -> "LifeTextTriggerRequest":
        if self.trigger_source not in LIFE_TRIGGER_SOURCES:
            raise ValueError(
                "trigger_source must be manual, voice_intent, schedule, or device_state"
            )
        return self


class LifeVoiceCommandRequest(BaseModel):
    text: str
    session_id: str | None = None
    speaker_id: str | None = None
    camera_id: str | None = None
    camera_channel: int = DEFAULT_CAMERA_CHANNEL
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS
    trigger_source: str = "voice_intent"
    source_id: str | None = None
    prompt: str | None = None
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str = "today outing"
    weather: str | None = None
    people_count: int = 1
    time_budget_minutes: int = 30
    persist: bool = True
    db_path: str | None = None

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must not be empty")
        return normalized

    @model_validator(mode="after")
    def _validate_voice_command(self) -> "LifeVoiceCommandRequest":
        if self.trigger_source not in LIFE_TRIGGER_SOURCES:
            raise ValueError(
                "trigger_source must be manual, voice_intent, schedule, or device_state"
            )
        return self


class LifeCameraVoiceListenRequest(BaseModel):
    camera_id: str
    speaker_id: str | None = None
    camera_channel: int = DEFAULT_CAMERA_CHANNEL
    listen_duration_ms: int = 3000
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS
    transcript: str | None = None
    session_id: str | None = None
    source_id: str | None = None
    prompt: str | None = None
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str = "today outing"
    weather: str | None = None
    people_count: int = 1
    time_budget_minutes: int = 30
    persist: bool = True
    db_path: str | None = None
    speak: bool = True
    life_mimo_base_url: str | None = None
    life_mimo_vision_model: str | None = None
    life_mimo_asr_model: str | None = None
    fresh_session: bool = False
    force_visual_capture: bool = False

    @field_validator("camera_id")
    @classmethod
    def _validate_camera_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("camera_id must not be empty")
        return normalized

    @field_validator("transcript", "session_id", "source_id", "prompt")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    def to_payload(self) -> CameraVoiceListenPayload:
        return CameraVoiceListenPayload(
            camera_id=self.camera_id,
            speaker_id=self.speaker_id,
            camera_channel=self.camera_channel,
            listen_duration_ms=self.listen_duration_ms,
            camera_duration_ms=self.camera_duration_ms,
            transcript=self.transcript,
            session_id=self.session_id,
            source_id=self.source_id,
            prompt=self.prompt,
            clip_base64=self.clip_base64,
            mimo_payload=self.mimo_payload,
            occasion=self.occasion,
            weather=self.weather,
            people_count=self.people_count,
            time_budget_minutes=self.time_budget_minutes,
            persist=self.persist,
            db_path=self.db_path,
            speak=self.speak,
            life_mimo_base_url=self.life_mimo_base_url,
            life_mimo_vision_model=self.life_mimo_vision_model,
            life_mimo_asr_model=self.life_mimo_asr_model,
            fresh_session=self.fresh_session,
            force_visual_capture=self.force_visual_capture,
        )


class LifeSceneTriggerRequest(BaseModel):
    intent: LifeSceneIntent
    text: str | None = None
    session_id: str | None = None
    speaker_id: str | None = None
    camera_id: str | None = None
    camera_channel: int = DEFAULT_CAMERA_CHANNEL
    camera_duration_ms: int = DEFAULT_CAMERA_DURATION_MS
    trigger_source: str = "voice_intent"
    source_id: str | None = None
    prompt: str | None = None
    clip_base64: str | None = None
    mimo_payload: dict[str, Any] | str | None = None
    occasion: str | None = None
    weather: str | None = None
    people_count: int | None = None
    time_budget_minutes: int | None = None
    persist: bool = True
    db_path: str | None = None
    ack_message: str | None = None
    suppress_speaker: bool = False
    async_mode: bool = False

    @field_validator("text", "ack_message")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_scene_trigger(self) -> "LifeSceneTriggerRequest":
        if self.trigger_source not in LIFE_TRIGGER_SOURCES:
            raise ValueError(
                "trigger_source must be manual, voice_intent, schedule, or device_state"
            )
        return self

    def to_scene_payload(self) -> LifeSceneTriggerPayload:
        return LifeSceneTriggerPayload(
            intent=self.intent,
            text=self.text,
            session_id=self.session_id,
            speaker_id=self.speaker_id,
            camera_id=self.camera_id,
            camera_channel=self.camera_channel,
            camera_duration_ms=self.camera_duration_ms,
            trigger_source=self.trigger_source,  # type: ignore[arg-type]
            source_id=self.source_id,
            prompt=self.prompt,
            clip_base64=self.clip_base64,
            mimo_payload=self.mimo_payload,
            occasion=self.occasion,
            weather=self.weather,
            people_count=self.people_count,
            time_budget_minutes=self.time_budget_minutes,
            persist=self.persist,
            db_path=self.db_path,
            ack_message=self.ack_message,
            suppress_speaker=self.suppress_speaker,
        )


@router.post("/demo", summary="Run life-agent demo", response_model=NormalResponse)
def run_life_demo(payload: LifeDemoRequest) -> NormalResponse:
    return NormalResponse(code=0, message="ok", data=run_life_demo_service(payload))


@router.post(
    "/live-demo",
    summary="Run life-agent demo from live MiMo output",
    response_model=NormalResponse,
)
async def run_life_live_demo(
    payload: LifeLiveDemoRequest, _: None = Depends(verify_token)
) -> NormalResponse:
    return NormalResponse(
        code=0,
        message="ok",
        data=await run_life_live_demo_service(payload),
    )


@router.post(
    "/trigger",
    summary="Run one life-agent recommendation from an explicit trigger",
    response_model=NormalResponse,
)
async def trigger_life_agent(payload: LifeTriggerRequest) -> NormalResponse:
    if payload.text:
        return NormalResponse(
            code=0,
            message="ok",
            data=await run_life_text_trigger_service(payload),
        )
    return NormalResponse(
        code=0,
        message="ok",
        data=await run_life_trigger_service(payload),
    )


@router.post(
    "/text-trigger",
    summary="Classify command text and run a life-agent trigger when matched",
    response_model=NormalResponse,
)
async def trigger_life_agent_from_text(
    payload: LifeTextTriggerRequest,
) -> NormalResponse:
    return NormalResponse(
        code=0,
        message="ok",
        data=await run_life_text_trigger_service(payload),
    )


@router.post(
    "/voice-command",
    summary="Handle one life-agent voice-session turn",
    response_model=NormalResponse,
)
async def trigger_life_agent_voice_session(
    payload: LifeVoiceCommandRequest,
) -> NormalResponse:
    return NormalResponse(
        code=0,
        message="ok",
        data=await run_life_voice_command_service(payload),
    )


@router.post(
    "/camera-voice-listen",
    summary="Run one short camera microphone voice turn for life agents",
    response_model=NormalResponse,
)
async def listen_camera_voice_for_life_agent(
    payload: LifeCameraVoiceListenRequest,
) -> NormalResponse:
    return NormalResponse(
        code=0,
        message="ok",
        data=await run_camera_voice_listen_service(payload.to_payload()),
    )


@router.post(
    "/scene-trigger",
    summary="Handle one XiaoAi/MiHome scene trigger for life agents",
    response_model=NormalResponse,
)
async def trigger_life_agent_scene(
    payload: LifeSceneTriggerRequest,
) -> NormalResponse:
    return NormalResponse(
        code=0,
        message="ok",
        data=await run_life_scene_trigger_service(payload.to_scene_payload()),
    )


@router.post(
    "/notify", summary="Send life-agent notification", response_model=NormalResponse
)
def notify_life_agent(request: LifeNotifyRequest) -> NormalResponse:
    result = deliver_life_notification(request)
    return NormalResponse(code=0, message="ok", data=result.model_dump())


@router.get(
    "/history",
    summary="List persisted life-agent recommendation history",
    response_model=NormalResponse,
)
def list_life_history(
    db_path: str = Query(default="data/life-demo.db"),
    domain: LifeDomain | None = None,
    source_id: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
) -> NormalResponse:
    return NormalResponse(
        code=0,
        message="ok",
        data=summarize_life_history(
            db_path=db_path,
            domain=domain,
            source_id=source_id,
            limit=limit,
        ),
    )
