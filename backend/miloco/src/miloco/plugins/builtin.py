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
) -> tuple[PluginFactory, ...]:
    """Return explicit built-ins while keeping disabled Outfit entirely lazy."""

    if not settings.features.outfit.enabled:
        return ()

    def build():
        from miloco.outfit.admin_router import create_outfit_admin_usage_router
        from miloco.outfit.capability import OutfitProviderStatus
        from miloco.outfit.plugin import (
            OutfitRuntimeExtension,
            create_outfit_plugin_factory,
        )
        from miloco.outfit.storage import OutfitStorage
        from miloco.outfit.visual_observability import VisualHostAuditAdapter
        from miloco.outfit.voice_observability import VoiceHostAuditAdapter
        from miloco.outfit.wardrobe_repo import WardrobeRepository
        from miloco.plugins.audit import BestEffortAuditWriter, VersionedHmacDigestor
        from miloco.plugins.audit_repo import AuditRepository
        from miloco.plugins.primary_person import PrimaryPersonResolver
        from miloco.plugins.usage import UsageAggregationService
        from miloco.plugins.usage_repo import UsageRepository

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
            _primary_person,
            _storage,
            _wardrobe_repository,
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
            admin_router = create_outfit_admin_usage_router(usage_service=usage_service)
            return OutfitRuntimeExtension(
                routers=(admin_router,),
                resources=(
                    audit_repository,
                    audit_writer,
                    usage_repository,
                    usage_service,
                    fanout_writer,
                    digestor,
                    voice_audit,
                    visual_audit,
                ),
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
