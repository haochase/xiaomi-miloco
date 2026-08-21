# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Privacy and failure-isolation contract for host audit events."""

from __future__ import annotations

import logging
import re

import pytest
from miloco.plugins.audit import (
    AUDIT_RETENTION_MS,
    AuditEventRepository,
    BestEffortAuditWriter,
    HostAuditEvent,
    VersionedHmacDigestor,
)
from pydantic import ValidationError


def _event(
    *,
    digestor: VersionedHmacDigestor | None = None,
    created_at_ms: int = 1_700_000_000_000,
) -> HostAuditEvent:
    active_digestor = digestor or VersionedHmacDigestor(
        key=b"k" * 32,
        key_version="audit-v1",
    )
    return HostAuditEvent(
        request_event_digest=active_digestor.digest_event("event-pre-digest"),
        device_digest=active_digestor.digest_device("device-pre-digest"),
        flow="voice",
        stage="completed",
        status="ready",
        error_code=None,
        elapsed_ms=12,
        frame_count=0,
        provider_call_count=0,
        input_tokens=0,
        output_tokens=0,
        video_tokens=0,
        total_tokens=0,
        usage_complete=True,
        created_at_ms=created_at_ms,
    )


def test_versioned_hmac_digest_is_stable_namespaced_and_non_reversible() -> None:
    digestor = VersionedHmacDigestor(key=b"a" * 32, key_version="audit-v1")
    same = VersionedHmacDigestor(key=b"a" * 32, key_version="audit-v1")
    next_key = VersionedHmacDigestor(key=b"b" * 32, key_version="audit-v1")
    next_version = VersionedHmacDigestor(key=b"a" * 32, key_version="audit-v2")

    event_digest = digestor.digest_event("private-value")

    assert event_digest == same.digest_event("private-value")
    assert event_digest != digestor.digest_request("private-value")
    assert event_digest != digestor.digest_device("private-value")
    assert event_digest != next_key.digest_event("private-value")
    assert event_digest != next_version.digest_event("private-value")
    assert event_digest.key_version == "audit-v1"
    assert re.fullmatch(r"[0-9a-f]{64}", event_digest.digest)
    assert "private-value" not in event_digest.model_dump_json()


@pytest.mark.parametrize(
    ("key", "key_version"),
    [
        (b"too-short", "audit-v1"),
        (b"k" * 32, ""),
        (b"k" * 32, "   "),
        (b"k" * 32, "v" * 33),
        (b"k" * 32, "unsafe version"),
    ],
)
def test_digestor_rejects_weak_keys_and_unbounded_versions(
    key: bytes,
    key_version: str,
) -> None:
    with pytest.raises(ValueError):
        VersionedHmacDigestor(key=key, key_version=key_version)


def test_digestor_rejects_blank_pre_digest_input() -> None:
    digestor = VersionedHmacDigestor(key=b"k" * 32, key_version="audit-v1")

    with pytest.raises(ValueError, match="digest input"):
        digestor.digest_event(" ")


def test_host_audit_event_is_frozen_extra_forbid_and_finite() -> None:
    event = _event()

    with pytest.raises(ValidationError):
        event.status = "failed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        HostAuditEvent.model_validate({**event.model_dump(), "owner_id": "private"})
    with pytest.raises(ValidationError):
        HostAuditEvent.model_validate({**event.model_dump(), "stage": "unbounded"})
    with pytest.raises(ValidationError):
        HostAuditEvent.model_validate(
            {**event.model_dump(), "error_code": "exception-detail"}
        )


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "asr_text",
        "media",
        "path",
        "wardrobe_name",
        "owner_id",
        "prompt",
        "model_response",
        "model_name",
        "token",
        "credential",
        "exception_text",
        "raw_event_id",
        "pre_digest",
    ],
)
def test_host_audit_event_rejects_raw_or_sensitive_fields(
    forbidden_field: str,
) -> None:
    event = _event()

    with pytest.raises(ValidationError):
        HostAuditEvent.model_validate(
            {**event.model_dump(), forbidden_field: "private-value"}
        )


def test_host_audit_event_contains_only_the_bounded_contract_fields() -> None:
    assert tuple(HostAuditEvent.model_fields) == (
        "request_event_digest",
        "device_digest",
        "flow",
        "stage",
        "status",
        "error_code",
        "elapsed_ms",
        "frame_count",
        "provider_call_count",
        "input_tokens",
        "output_tokens",
        "video_tokens",
        "total_tokens",
        "usage_complete",
        "created_at_ms",
    )


def test_request_cancelled_is_a_finite_audit_error_code() -> None:
    event = _event()

    cancelled = HostAuditEvent.model_validate(
        {
            **event.model_dump(),
            "stage": "provider",
            "status": "provider_failed",
            "error_code": "request_cancelled",
        }
    )

    assert cancelled.error_code == "request_cancelled"


class _RecordingRepository(AuditEventRepository):
    def __init__(
        self,
        *,
        insert_error: Exception | None = None,
        purge_error: Exception | None = None,
    ) -> None:
        self.insert_error = insert_error
        self.purge_error = purge_error
        self.events: list[HostAuditEvent] = []
        self.cutoffs: list[int] = []

    async def insert(self, event: HostAuditEvent) -> None:
        if self.insert_error is not None:
            raise self.insert_error
        self.events.append(event)

    async def purge_older_than(self, *, cutoff_ms: int) -> int:
        self.cutoffs.append(cutoff_ms)
        if self.purge_error is not None:
            raise self.purge_error
        return 0


@pytest.mark.asyncio
async def test_best_effort_writer_records_then_purges_against_injected_clock() -> None:
    repository = _RecordingRepository()
    writer = BestEffortAuditWriter(
        repository=repository,
        clock_ms=lambda: AUDIT_RETENTION_MS + 123,
    )
    event = _event()

    await writer.write(event)

    assert repository.events == [event]
    assert repository.cutoffs == [123]


@pytest.mark.asyncio
async def test_insert_failure_isolated_with_fixed_warning_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = _RecordingRepository(
        insert_error=RuntimeError("secret event and exception detail")
    )
    writer = BestEffortAuditWriter(repository=repository, clock_ms=lambda: 99)

    with caplog.at_level(logging.WARNING, logger="miloco.plugins.audit"):
        await writer.write(_event())

    assert repository.cutoffs == []
    assert [record.getMessage() for record in caplog.records] == [
        "host_audit_insert_failed"
    ]
    assert "secret" not in caplog.text
    assert "exception detail" not in caplog.text


@pytest.mark.asyncio
async def test_purge_failure_does_not_undo_insert_or_leak_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repository = _RecordingRepository(
        purge_error=RuntimeError("secret purge exception")
    )
    writer = BestEffortAuditWriter(repository=repository, clock_ms=lambda: 99)
    event = _event()

    with caplog.at_level(logging.WARNING, logger="miloco.plugins.audit"):
        await writer.write(event)

    assert repository.events == [event]
    assert [record.getMessage() for record in caplog.records] == [
        "host_audit_purge_failed"
    ]
    assert "secret" not in caplog.text
    assert "exception" not in caplog.text
