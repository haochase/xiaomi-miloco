# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the Xiaomi Miloco License Agreement.

"""Lazy factories for optional plugins shipped with the Miloco host."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from miloco.plugins.registry import PluginFactory

if TYPE_CHECKING:
    from miloco.config.settings import MilocoSettings
    from miloco.plugins.audit import HostAuditEvent
    from miloco.plugins.primary_person import PersonLookup
    from miloco.weather.contracts import WeatherCachePort

_LOGGER = logging.getLogger(__name__)


class _AuditUsageFanoutWriter:
    """Feed persistent audit first, then usage, isolating both sink failures."""

    __slots__ = ("_audit_writer", "_usage_service")

    def __init__(self, *, audit_writer: Any, usage_service: Any) -> None:
        self._audit_writer = audit_writer
        self._usage_service = usage_service

    async def write(self, event: HostAuditEvent) -> None:
        try:
            await self._audit_writer.write(event)
        except Exception:
            _LOGGER.warning("plugin_audit_write_failed")
        try:
            await self._usage_service.consume_audit_event(event)
        except Exception:
            _LOGGER.warning("plugin_usage_feed_failed")


def build_builtin_plugin_factories(
    settings: MilocoSettings,
    person_service: PersonLookup,
    *,
    weather_cache: WeatherCachePort | None = None,
) -> tuple[PluginFactory, ...]:
    """Return explicit built-ins while keeping disabled Outfit entirely lazy."""

    if not settings.features.outfit.enabled:
        return ()

    def build():
        import uuid

        from miloco.outfit.admin_router import create_outfit_admin_usage_router
        from miloco.outfit.capability import OutfitProviderStatus
        from miloco.outfit.filtering import WeatherCapability
        from miloco.outfit.host_weather_adapter import OutfitHostWeatherCacheAdapter
        from miloco.outfit.plugin import (
            OutfitRuntimeExtension,
            create_outfit_plugin_factory,
        )
        from miloco.outfit.recommendation_api import RecommendationSnapshot
        from miloco.outfit.recommendation_router import create_recommendation_router
        from miloco.outfit.recommendation_service import OutfitRecommendationService
        from miloco.outfit.recommendation_snapshot_repo import (
            RecommendationSnapshotRepository,
        )
        from miloco.outfit.storage import OutfitStorage
        from miloco.outfit.visual_observability import VisualHostAuditAdapter
        from miloco.outfit.voice_observability import VoiceHostAuditAdapter
        from miloco.outfit.wardrobe_repo import WardrobeRepository
        from miloco.outfit.wardrobe_router import create_wardrobe_router
        from miloco.outfit.wardrobe_service import WardrobeService
        from miloco.outfit.weather_adapter import CachedWeatherRequirementAdapter
        from miloco.plugins.audit import BestEffortAuditWriter, VersionedHmacDigestor
        from miloco.plugins.audit_repo import AuditRepository
        from miloco.plugins.primary_person import PrimaryPersonResolver
        from miloco.plugins.usage import UsageAggregationService
        from miloco.plugins.usage_repo import UsageRepository
        from miloco.weather.contracts import WeatherLocationQuery

        outfit_settings = settings.features.outfit
        workspace_dir = settings.directories.workspace_dir
        if not workspace_dir.is_absolute():
            raise ValueError("plugin workspace must be absolute")
        outfit_root = workspace_dir / "outfit"
        wardrobe_path = outfit_root / "wardrobe.db"
        audit_path = outfit_root / "audit.db"
        usage_path = outfit_root / "usage.db"
        primary_person_resolver = PrimaryPersonResolver(
            outfit_settings,
            person_service,
        )

        def build_runtime_extension(
            primary_person,
            storage,
            wardrobe_repository,
        ) -> OutfitRuntimeExtension:
            configured_key = outfit_settings.audit_hmac_key
            if configured_key is None:
                raise ValueError("plugin audit key is missing")
            digestor = VersionedHmacDigestor(
                key=configured_key.get_secret_value().encode("utf-8"),
                key_version=outfit_settings.audit_hmac_key_version,
            )
            audit_repository = AuditRepository(audit_path)
            audit_writer = BestEffortAuditWriter(
                repository=audit_repository,
                clock_ms=lambda: time.time_ns() // 1_000_000,
            )
            usage_repository = UsageRepository(usage_path)
            usage_service = UsageAggregationService(
                repository=usage_repository,
                clock=lambda: datetime.now(UTC),
            )
            fanout_writer = _AuditUsageFanoutWriter(
                audit_writer=audit_writer,
                usage_service=usage_service,
            )
            voice_audit = VoiceHostAuditAdapter(
                digestor=digestor,
                writer=fanout_writer,
            )
            visual_audit = VisualHostAuditAdapter(
                digestor=digestor,
                writer=fanout_writer,
            )

            def clock_ms() -> int:
                return time.time_ns() // 1_000_000

            wardrobe_service = WardrobeService(
                wardrobe_repository,
                primary_person_id=primary_person.person_id,
                clock_ms=clock_ms,
            )
            admin_router = create_outfit_admin_usage_router(usage_service=usage_service)
            wardrobe_router = create_wardrobe_router(wardrobe_service=wardrobe_service)
            extension_routers = [admin_router, wardrobe_router]
            extension_resources: list[object] = [
                audit_repository,
                audit_writer,
                usage_repository,
                usage_service,
                fanout_writer,
                digestor,
                voice_audit,
                visual_audit,
                wardrobe_service,
            ]

            if (
                weather_cache is not None
                and settings.weather.enabled
                and settings.weather.city_name is not None
            ):
                query = WeatherLocationQuery(
                    city_name=settings.weather.city_name,
                    country_code=settings.weather.country_code,
                )
                host_weather = OutfitHostWeatherCacheAdapter(
                    cache=weather_cache,
                    query=query,
                )
                weather_requirement = CachedWeatherRequirementAdapter(
                    host_weather,
                    now_ms=clock_ms,
                )
                if weather_requirement.current_resolution().status == "available":
                    snapshot_repository = RecommendationSnapshotRepository(storage)

                    class _NoInferredWeatherCapabilities:
                        def weather_capabilities_for(
                            self,
                            item_id: str,
                        ) -> tuple[WeatherCapability, ...]:
                            del item_id
                            return ()

                    class _OwnerScopedSnapshotWriter:
                        def save(self, snapshot: RecommendationSnapshot) -> None:
                            snapshot_repository.save(
                                owner_person_id=primary_person.person_id,
                                snapshot=snapshot,
                                expires_at_ms=(snapshot.created_at_ms + 86_400_000),
                            )

                    recommendation_service = OutfitRecommendationService(
                        wardrobe_service,
                        weather_port=weather_requirement,
                        capability_port=_NoInferredWeatherCapabilities(),
                    )
                    recommendation_router = create_recommendation_router(
                        recommendation_service=recommendation_service,
                        snapshot_writer=_OwnerScopedSnapshotWriter(),
                        snapshot_id_factory=lambda: f"rec-{uuid.uuid4()}",
                        clock_ms=clock_ms,
                        ranking_version="deterministic-v1",
                    )
                    extension_routers.append(recommendation_router)
                    extension_resources.extend(
                        (
                            host_weather,
                            weather_requirement,
                            snapshot_repository,
                            recommendation_service,
                        )
                    )
            return OutfitRuntimeExtension(
                routers=tuple(extension_routers),
                resources=tuple(extension_resources),
            )

        delegated_factory = create_outfit_plugin_factory(
            settings=outfit_settings,
            primary_person_resolver=primary_person_resolver,
            database_path=wardrobe_path,
            voice_ingress_configured=False,
            camera_allowlisted=False,
            initial_provider_status=OutfitProviderStatus.NOT_CONFIGURED,
            storage_factory=OutfitStorage,
            repository_factory=WardrobeRepository,
            runtime_extension_factory=build_runtime_extension,
        )
        return delegated_factory.build()

    return (PluginFactory(id="outfit_v2", build=build),)
