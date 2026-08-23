# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Synthetic host isolation contracts for the optional Outfit contribution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from miloco.config.settings import MilocoSettings
from miloco.outfit.camera_adapter import CameraFrameCaptureAdapter
from miloco.outfit.composition import OutfitCandidate
from miloco.outfit.ranking import rank_outfit_candidates
from miloco.outfit.try_on import snapshot_recommended_outfit
from miloco.outfit.vision_provider import ConstrainedVisionProviderAdapter
from miloco.outfit.visual_budget import VisualSessionBudgetGuard
from miloco.outfit.visual_ports import CapturedFrame, VisionProviderObservation
from miloco.outfit.visual_service import (
    OutfitVisualReviewService,
    VisualReviewOutcome,
    VisualReviewRequest,
    VisualReviewStatus,
)
from miloco.outfit.xiaomi_speaker_adapter import XiaomiSpeakerAdapter
from miloco.plugins.builtin import build_builtin_plugin_factories
from miloco.plugins.host_composition import HostPluginRuntime
from miloco.plugins.registry import PluginFailureCode, PluginLifecycleStage


class _PersonService:
    def __init__(self, *, exists: bool = True) -> None:
        self._exists = exists
        self.calls: list[str] = []

    def exists(self, person_id: str) -> bool:
        self.calls.append(person_id)
        return self._exists


@dataclass
class _SideEffectTripwire:
    capture: int = 0
    provider: int = 0
    play_text: int = 0


def _install_real_get_side_effect_tripwires(
    monkeypatch: pytest.MonkeyPatch,
) -> _SideEffectTripwire:
    """Fail if the read-only GET routes reach real production side-effect ports."""

    tripwire = _SideEffectTripwire()

    async def _reject_capture(*_args: object, **_kwargs: object) -> CapturedFrame:
        tripwire.capture += 1
        raise AssertionError("read-only GET reached camera capture")

    async def _reject_provider(
        *_args: object,
        **_kwargs: object,
    ) -> VisionProviderObservation:
        tripwire.provider += 1
        raise AssertionError("read-only GET reached vision provider")

    async def _reject_speaker(*_args: object, **_kwargs: object) -> None:
        tripwire.play_text += 1
        raise AssertionError("read-only GET reached speaker playback")

    monkeypatch.setattr(
        CameraFrameCaptureAdapter,
        "capture_frame",
        _reject_capture,
    )
    monkeypatch.setattr(
        ConstrainedVisionProviderAdapter,
        "observe",
        _reject_provider,
    )
    monkeypatch.setattr(XiaomiSpeakerAdapter, "play_text", _reject_speaker)
    return tripwire


class _SyntheticCapture:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def capture_frame(self, *, device_id: str, request_id: str) -> CapturedFrame:
        self.calls.append((device_id, request_id))
        return CapturedFrame(
            request_id=request_id,
            device_id=device_id,
            media_token="synthetic-temporary-frame",
        )


class _SyntheticProvider:
    def __init__(self, *, fails: bool) -> None:
        self._fails = fails
        self.calls = 0

    async def observe(
        self,
        *,
        frame: CapturedFrame,
        candidate_items: tuple[object, ...],
        max_tokens: int,
    ) -> VisionProviderObservation:
        del frame, max_tokens
        self.calls += 1
        if self._fails:
            raise RuntimeError("private synthetic provider failure")
        return VisionProviderObservation(
            observed_item_ids=(candidate_items[0].item_id,),
            confidence=0.95,
            usage={
                "input_tokens": 3,
                "output_tokens": 2,
                "video_tokens": 1,
            },
        )


class _SyntheticTemporaryMedia:
    def __init__(self, *, fails: bool) -> None:
        self._fails = fails
        self.delete_attempts: list[str] = []
        self.deleted_tokens: list[str] = []

    async def delete_frame(self, *, frame: CapturedFrame) -> None:
        self.delete_attempts.append(frame.media_token)
        if self._fails:
            raise RuntimeError("private temporary media failure")
        self.deleted_tokens.append(frame.media_token)


class _FailingVisualAudit:
    def __init__(self) -> None:
        self.calls = 0

    async def record_visual_review(self, _record: object) -> None:
        self.calls += 1
        raise RuntimeError("private audit sink failure")


def _settings(root: Path, *, enabled: bool = True) -> MilocoSettings:
    return MilocoSettings(
        directories={"storage": str(root)},
        features={
            "outfit": {
                "enabled": enabled,
                "primary_person_id": "chase",
                "audit_hmac_key": "k" * 32,
                "audit_hmac_key_version": "audit-v1",
            }
        },
    )


@dataclass
class _SyntheticHostState:
    visual_attempts: int = 0
    visual_statuses: list[str] = field(default_factory=list)
    visual_snapshot_before: dict[str, object] | None = None
    visual_snapshot_after: dict[str, object] | None = None


def _synthetic_host(
    *,
    visual_service: OutfitVisualReviewService | None = None,
) -> tuple[FastAPI, _SyntheticHostState]:
    app = FastAPI()
    state = _SyntheticHostState()

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "core": {
                "status": "core-ok",
                "marker": "synthetic-core-health",
            },
            "visual_attempts": state.visual_attempts,
            "visual_statuses": state.visual_statuses.copy(),
        }

    if visual_service is not None:

        @app.post(
            "/synthetic/outfit/visual-review",
            response_model=VisualReviewOutcome,
        )
        async def review_visual(request: VisualReviewRequest) -> VisualReviewOutcome:
            state.visual_attempts += 1
            state.visual_snapshot_before = request.snapshot.model_dump()
            try:
                outcome = await visual_service.evaluate(request=request)
            finally:
                state.visual_snapshot_after = request.snapshot.model_dump()
            state.visual_statuses.append(outcome.status.value)
            return outcome

    @app.get("/{full_path:path}", name="spa_handler")
    async def spa_handler(full_path: str) -> dict[str, str]:
        return {"path": full_path}

    return app, state


async def _assert_core_routes_are_unchanged(app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://synthetic-host",
    ) as client:
        health = await client.get("/health")
        spa = await client.get("/client-side/path")

    assert health.status_code == 200
    assert health.json() == {
        "core": {
            "status": "core-ok",
            "marker": "synthetic-core-health",
        },
        "visual_attempts": 0,
        "visual_statuses": [],
    }
    assert spa.status_code == 200
    assert spa.json() == {"path": "client-side/path"}
    paths = _route_paths(app)
    assert "/health" in paths
    assert "/{full_path:path}" in paths
    assert not any(path.startswith("/api/outfit") for path in paths)


def _route_paths(app: FastAPI) -> tuple[str, ...]:
    return tuple(getattr(route, "path", "") for route in app.router.routes)


def _outfit_file_tree(outfit_root: Path) -> tuple[str, ...]:
    assert outfit_root.is_dir()
    return tuple(
        sorted(
            path.relative_to(outfit_root).as_posix()
            for path in outfit_root.rglob("*")
            if path.is_file()
        )
    )


def _is_known_testclient_lifecycle_task(task: asyncio.Task[object]) -> bool:
    return task.get_name().startswith("anyio.from_thread.BlockingPortal")


def _pending_tasks() -> frozenset[asyncio.Task[object]]:
    current_task = asyncio.current_task()
    return frozenset(
        task
        for task in asyncio.all_tasks()
        if task is not current_task
        and not task.done()
        and not _is_known_testclient_lifecycle_task(task)
    )


def _snapshot():
    option = rank_outfit_candidates(
        [
            OutfitCandidate(
                item_ids=("navy-top", "gray-bottom", "white-shoes"),
                pattern="top_bottom_shoes",
            )
        ]
    )[0]
    return snapshot_recommended_outfit(
        recommendation_id="synthetic-recommendation",
        owner_person_id="primary-person",
        option=option,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "person_exists", "expected_failure"),
    (
        ("disabled", True, False),
        ("invalid_person", False, True),
        ("storage_build_failure", True, True),
    ),
)
async def test_builtin_host_preserves_core_routes_when_outfit_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    person_exists: bool,
    expected_failure: bool,
) -> None:
    if case == "storage_build_failure":
        import miloco.outfit.storage as storage_module

        class _FailingStorage:
            def __init__(self, _database_path: Path) -> None:
                raise RuntimeError("private storage build failure")

        monkeypatch.setattr(storage_module, "OutfitStorage", _FailingStorage)

    app, _state = _synthetic_host()
    runtime = HostPluginRuntime(
        build_builtin_plugin_factories(
            _settings(tmp_path / case, enabled=case != "disabled"),
            _PersonService(exists=person_exists),
        )
    )

    try:
        await runtime.start(app)

        await _assert_core_routes_are_unchanged(app)
        assert runtime.registry.routers == ()
        assert runtime.registry.panel_capabilities == ()
        if expected_failure:
            assert len(runtime.registry.failures) == 1
            failure = runtime.registry.failures[0]
            assert failure.stage is PluginLifecycleStage.BUILD
            assert failure.code is PluginFailureCode.BUILD_FAILED
            assert "private" not in repr(failure)
        else:
            assert runtime.registry.failures == ()
    finally:
        await runtime.stop(app)


@pytest.mark.asyncio
async def test_builtin_capability_and_usage_gets_are_authenticated_and_side_effect_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import miloco.middleware.auth_middleware as auth_middleware

    tripwire = _install_real_get_side_effect_tripwires(monkeypatch)
    app, state = _synthetic_host()
    runtime = HostPluginRuntime(
        build_builtin_plugin_factories(_settings(tmp_path / "host"), _PersonService())
    )
    monkeypatch.setattr(
        auth_middleware,
        "get_settings",
        lambda: SimpleNamespace(server=SimpleNamespace(token="test-token")),
    )

    try:
        await runtime.start(app)

        assert runtime.registry.panel_capabilities == ("outfit_v2",)
        assert [router.routes[0].path for router in runtime.registry.routers] == [
            "/api/outfit/capability",
            "/api/outfit/admin/usage/today",
        ]
        outfit_root = tmp_path / "host" / "outfit"
        file_tree_before = _outfit_file_tree(outfit_root)
        pending_tasks_before = _pending_tasks()
        route_paths_before = _route_paths(app)
        headers = {"Authorization": "Bearer test-token"}

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://synthetic-host",
        ) as client:
            health_before = await client.get("/health")
            capability_first = await client.get(
                "/api/outfit/capability",
                headers=headers,
            )
            capability_second = await client.get(
                "/api/outfit/capability",
                headers=headers,
            )
            usage_first = await client.get(
                "/api/outfit/admin/usage/today",
                headers=headers,
            )
            usage_second = await client.get(
                "/api/outfit/admin/usage/today",
                headers=headers,
            )
            health_after = await client.get("/health")

        await asyncio.sleep(0)

        assert health_before.status_code == health_after.status_code == 200
        assert health_after.json() == health_before.json()
        assert health_after.json()["visual_attempts"] == state.visual_attempts == 0
        assert capability_first.status_code == capability_second.status_code == 200
        assert usage_first.status_code == usage_second.status_code == 200
        assert capability_first.json() == capability_second.json()
        assert usage_first.json() == usage_second.json()
        assert capability_first.headers["cache-control"] == "private, no-store"
        assert usage_first.headers["cache-control"] == "private, no-store"
        assert tripwire == _SideEffectTripwire()
        assert _outfit_file_tree(outfit_root) == file_tree_before
        assert _route_paths(app) == route_paths_before
        assert _pending_tasks() - pending_tasks_before == frozenset()
    finally:
        await runtime.stop(app)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "failure_case",
        "provider_fails",
        "audit_fails",
        "cleanup_fails",
        "expected_status",
        "expected_error_code",
    ),
    (
        (
            "provider",
            True,
            False,
            False,
            VisualReviewStatus.PROVIDER_FAILED,
            "provider_failed",
        ),
        (
            "audit",
            False,
            True,
            False,
            VisualReviewStatus.COMPLETED,
            None,
        ),
        (
            "cleanup",
            False,
            False,
            True,
            VisualReviewStatus.CLEANUP_FAILED,
            "temporary_media_cleanup_failed",
        ),
    ),
)
async def test_synthetic_visual_failure_isolation_is_not_h6_production_proof(
    failure_case: str,
    provider_fails: bool,
    audit_fails: bool,
    cleanup_fails: bool,
    expected_status: VisualReviewStatus,
    expected_error_code: str | None,
) -> None:
    # This is synthetic service proof only, not H6 production visual composition proof.
    snapshot = _snapshot()
    capture = _SyntheticCapture()
    provider = _SyntheticProvider(fails=provider_fails)
    media_store = _SyntheticTemporaryMedia(fails=cleanup_fails)
    audit = _FailingVisualAudit() if audit_fails else None
    service = OutfitVisualReviewService(
        capture=capture,
        provider=provider,
        temporary_media_store=media_store,
        audit=audit,
        enabled=True,
        provider_timeout_s=1.0,
        budget_guard=VisualSessionBudgetGuard(
            ttl_ms=1_000,
            max_concurrent_requests=1,
            max_model_calls=1,
            max_total_tokens=10,
            max_consecutive_provider_errors=1,
        ),
        now_ms=lambda: 1_100,
    )
    app, state = _synthetic_host(visual_service=service)
    route_paths_before = _route_paths(app)
    request = VisualReviewRequest(
        request_id=f"synthetic-{failure_case}-request",
        device_id="synthetic-camera",
        snapshot=snapshot,
        explicit_trigger=True,
        session_id=f"synthetic-{failure_case}-session",
        session_started_at_ms=1_000,
        max_tokens=10,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://synthetic-host",
    ) as client:
        health_before = await client.get("/health")
        review = await client.post(
            "/synthetic/outfit/visual-review",
            json=request.model_dump(mode="json"),
        )
        health_after = await client.get("/health")
        spa_after = await client.get("/client-side/path")

    assert health_before.status_code == health_after.status_code == 200
    assert (
        health_before.json()["core"]
        == health_after.json()["core"]
        == {
            "status": "core-ok",
            "marker": "synthetic-core-health",
        }
    )
    assert health_before.json()["visual_attempts"] == 0
    assert health_after.json()["visual_attempts"] == state.visual_attempts == 1
    assert health_after.json()["visual_statuses"] == [expected_status.value]
    assert spa_after.status_code == 200
    assert spa_after.json() == {"path": "client-side/path"}
    assert _route_paths(app) == route_paths_before
    assert review.status_code == 200
    assert review.json()["status"] == expected_status.value
    assert review.json()["error_code"] == expected_error_code
    assert set(review.json()) == {
        "status",
        "comparison",
        "correction",
        "error_code",
    }
    assert state.visual_snapshot_before is not None
    assert state.visual_snapshot_after == state.visual_snapshot_before
    assert capture.calls == [("synthetic-camera", f"synthetic-{failure_case}-request")]
    assert provider.calls == 1
    assert media_store.delete_attempts == ["synthetic-temporary-frame"]
    assert media_store.deleted_tokens == (
        [] if cleanup_fails else ["synthetic-temporary-frame"]
    )
    assert (audit.calls if audit is not None else 0) == int(audit_fails)
