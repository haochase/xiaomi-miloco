# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Lazy host composition for the built-in optional Outfit contribution."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi import Response
from miloco.config.settings import MilocoSettings, WeatherSettings
from miloco.plugins import builtin as builtin_module
from miloco.plugins.audit import HostAuditEvent, VersionedHmacDigest
from miloco.plugins.builtin import (
    _AuditUsageFanoutWriter,
    build_builtin_plugin_factories,
)
from miloco.plugins.registry import (
    HostPluginRegistry,
    PluginFailureCode,
    PluginLifecycleStage,
)
from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherCondition,
    WeatherLocationQuery,
)


class _PersonService:
    def __init__(self, *, exists: bool = True, fails: bool = False) -> None:
        self._exists = exists
        self._fails = fails

    def exists(self, person_id: str) -> bool:
        del person_id
        if self._fails:
            raise RuntimeError("private-person-detail")
        return self._exists


@dataclass
class _WeatherCache:
    location: ResolvedWeatherLocation | None
    observation: HostWeatherObservation | None
    location_reads: list[WeatherLocationQuery] = field(default_factory=list)
    observation_reads: int = 0

    def read_location(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation | None:
        self.location_reads.append(query)
        return self.location

    def write_location(
        self,
        query: WeatherLocationQuery,
        location: ResolvedWeatherLocation,
    ) -> None:
        del query, location

    def read_observation(self) -> HostWeatherObservation | None:
        self.observation_reads += 1
        return self.observation

    def write_observation(self, observation: HostWeatherObservation) -> None:
        del observation


def _weather_cache(
    *,
    condition: WeatherCondition = "clear",
    valid_until_ms: int = 4_000_000_000_000,
) -> _WeatherCache:
    return _WeatherCache(
        location=ResolvedWeatherLocation(
            city_name="北京市",
            country_code="CN",
            latitude=39.9042,
            longitude=116.4074,
            timezone="Asia/Shanghai",
        ),
        observation=HostWeatherObservation.model_validate(
            {
                "condition": condition,
                "observed_at_ms": 1,
                "valid_until_ms": valid_until_ms,
            }
        ),
    )


def _settings(
    root: Path,
    *,
    key: str | None = "k" * 32,
    primary_person_id: str | None = "chase",
    weather_enabled: bool = False,
) -> MilocoSettings:
    return MilocoSettings(
        directories={"storage": str(root)},
        weather=WeatherSettings(
            enabled=weather_enabled,
            city_name="北京市" if weather_enabled else None,
            country_code="CN",
        ),
        features={
            "outfit": {
                "enabled": True,
                "primary_person_id": primary_person_id,
                "audit_hmac_key": key,
                "audit_hmac_key_version": "audit-v1",
            }
        },
    )


def test_disabled_clean_subprocess_imports_no_outfit_and_creates_no_database_dir(
    tmp_path: Path,
) -> None:
    root = tmp_path / "disabled-home"
    code = """
import json
import sys
from pathlib import Path
from miloco.config.settings import MilocoSettings
from miloco.plugins.builtin import build_builtin_plugin_factories

root = Path(sys.argv[1])
settings = MilocoSettings(
    directories={"storage": str(root)},
    features={"outfit": {"enabled": False}},
)
factories = build_builtin_plugin_factories(settings, object())
print(json.dumps({
    "factory_count": len(factories),
    "outfit_imported": any(
        name == "miloco.outfit" or name.startswith("miloco.outfit.")
        for name in sys.modules
    ),
    "outfit_dir_exists": (root / "outfit").exists(),
}))
"""
    env = os.environ.copy()
    env["MILOCO_HOME"] = str(root)
    completed = subprocess.run(
        [sys.executable, "-c", code, str(root)],
        cwd=Path(__file__).parents[2],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "factory_count": 0,
        "outfit_imported": False,
        "outfit_dir_exists": False,
    }


@pytest.mark.asyncio
async def test_enabled_factory_builds_wardrobe_router_without_recommendation_once(
    tmp_path: Path,
) -> None:
    root = tmp_path / "enabled-home"
    factories = build_builtin_plugin_factories(_settings(root), _PersonService())
    registry = HostPluginRegistry(factories)

    assert len(factories) == 1
    assert factories[0].id == "outfit_v2"
    assert not (root / "outfit").exists()

    await registry.activate()

    outfit_root = root / "outfit"
    assert registry.failures == ()
    assert [route.routes[0].path for route in registry.routers] == [
        "/api/outfit/capability",
        "/api/outfit/admin/usage/today",
        "/api/outfit/wardrobe/drafts",
    ]
    assert not any(
        route.path == "/api/outfit/recommendations"
        for router in registry.routers
        for route in router.routes
    )
    capability = await registry.routers[0].routes[0].endpoint(Response())
    assert capability.last_provider_status.value == "not_configured"
    assert registry.panel_capabilities == ("outfit_v2",)
    assert {path.name for path in outfit_root.iterdir()} == {
        "wardrobe.db",
        "audit.db",
        "usage.db",
    }
    assert all(path.is_absolute() for path in outfit_root.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing_port", "missing_location", "stale"])
async def test_unavailable_weather_keeps_wardrobe_without_recommendation(
    tmp_path: Path,
    case: str,
) -> None:
    if case == "missing_port":
        cache = None
    elif case == "missing_location":
        cache = _WeatherCache(location=None, observation=None)
    else:
        cache = _weather_cache(valid_until_ms=2)
    registry = HostPluginRegistry(
        build_builtin_plugin_factories(
            _settings(tmp_path / case, weather_enabled=True),
            _PersonService(),
            weather_cache=cache,
        )
    )

    await registry.activate()

    paths = [
        getattr(route, "path", "")
        for router in registry.routers
        for route in router.routes
    ]
    assert "/api/outfit/wardrobe/drafts" in paths
    assert "/api/outfit/recommendations" not in paths


@pytest.mark.asyncio
async def test_available_weather_registers_recommendation_once(tmp_path: Path) -> None:
    cache = _weather_cache()
    registry = HostPluginRegistry(
        build_builtin_plugin_factories(
            _settings(tmp_path, weather_enabled=True),
            _PersonService(),
            weather_cache=cache,
        )
    )

    await registry.activate()

    paths = [
        getattr(route, "path", "")
        for router in registry.routers
        for route in router.routes
    ]
    assert paths.count("/api/outfit/recommendations") == 1
    assert cache.location_reads == [
        WeatherLocationQuery(city_name="北京市", country_code="CN")
    ]
    assert cache.observation_reads == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "person_service"),
    (
        (None, _PersonService()),
        ("too-short", _PersonService()),
        ("k" * 32, _PersonService(exists=False)),
        ("k" * 32, _PersonService(fails=True)),
    ),
)
async def test_missing_short_key_and_bad_person_are_fixed_build_failures(
    tmp_path: Path,
    key: str | None,
    person_service: _PersonService,
) -> None:
    registry = HostPluginRegistry(
        build_builtin_plugin_factories(_settings(tmp_path, key=key), person_service)
    )

    await registry.activate()

    assert registry.routers == ()
    assert registry.panel_capabilities == ()
    assert len(registry.failures) == 1
    assert registry.failures[0].stage is PluginLifecycleStage.BUILD
    assert registry.failures[0].code is PluginFailureCode.BUILD_FAILED
    assert key is None or key not in repr(registry.failures)


@pytest.mark.asyncio
async def test_repository_error_is_fixed_build_failure_without_path_or_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import miloco.plugins.audit_repo as audit_repo_module

    private_path = str(tmp_path / "private")
    secret = "z" * 32

    class _FailingAuditRepository:
        def __init__(self, _database_path: Path) -> None:
            raise RuntimeError(f"{private_path}:{secret}")

    monkeypatch.setattr(audit_repo_module, "AuditRepository", _FailingAuditRepository)
    registry = HostPluginRegistry(
        build_builtin_plugin_factories(
            _settings(tmp_path, key=secret),
            _PersonService(),
        )
    )

    await registry.activate()

    assert registry.routers == ()
    assert registry.failures[0].code is PluginFailureCode.BUILD_FAILED
    assert private_path not in repr(registry.failures)
    assert secret not in repr(registry.failures)


@pytest.mark.asyncio
async def test_unusable_workspace_is_a_fixed_build_failure(tmp_path: Path) -> None:
    workspace_file = tmp_path / "workspace-is-a-file"
    workspace_file.write_text("not a directory", encoding="utf-8")
    registry = HostPluginRegistry(
        build_builtin_plugin_factories(
            _settings(workspace_file),
            _PersonService(),
        )
    )

    await registry.activate()

    assert registry.routers == ()
    assert registry.panel_capabilities == ()
    assert registry.failures[0].stage is PluginLifecycleStage.BUILD
    assert registry.failures[0].code is PluginFailureCode.BUILD_FAILED
    assert str(workspace_file) not in repr(registry.failures)


@pytest.mark.asyncio
async def test_audit_usage_fanout_preserves_order_and_isolates_both_failures(
    caplog,
) -> None:
    calls: list[str] = []

    class _FailingAuditWriter:
        async def write(self, _event: HostAuditEvent) -> None:
            calls.append("audit")
            raise RuntimeError("private-audit-detail")

    class _FailingUsageService:
        async def consume_audit_event(self, _event: HostAuditEvent) -> None:
            calls.append("usage")
            raise RuntimeError("private-usage-detail")

    digest = VersionedHmacDigest(key_version="v1", digest="0" * 64)
    event = HostAuditEvent(
        request_event_digest=digest,
        device_digest=digest,
        flow="voice",
        stage="completed",
        status="ready",
        elapsed_ms=0,
        frame_count=0,
        provider_call_count=0,
        input_tokens=0,
        output_tokens=0,
        video_tokens=0,
        total_tokens=0,
        usage_complete=True,
        created_at_ms=0,
    )
    writer = _AuditUsageFanoutWriter(
        audit_writer=_FailingAuditWriter(),
        usage_service=_FailingUsageService(),
    )

    await writer.write(event)

    assert calls == ["audit", "usage"]
    assert "plugin_audit_write_failed" in caplog.text
    assert "plugin_usage_feed_failed" in caplog.text
    assert "private-audit-detail" not in caplog.text
    assert "private-usage-detail" not in caplog.text


def test_builtin_module_has_no_top_level_outfit_import() -> None:
    source = Path(builtin_module.__file__ or "").read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in tree.body if isinstance(node, ast.ImportFrom)}

    assert not any(
        imported == "miloco.outfit" or imported.startswith("miloco.outfit.")
        for imported in top_level_imports
    )
