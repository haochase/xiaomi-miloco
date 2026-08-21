# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""主使用者解析器的精确、低敏感度行为契约。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from miloco.config.settings import OutfitSettings
from miloco.plugins.primary_person import (
    PrimaryPersonErrorCode,
    PrimaryPersonResolutionError,
    PrimaryPersonResolver,
)


class RecordingPersonService:
    """记录解析器向人员服务发出的精确 ID 查询。"""

    def __init__(self, known_ids: set[str]) -> None:
        self._known_ids = known_ids
        self.calls: list[str] = []

    def exists(self, person_id: str) -> bool:
        self.calls.append(person_id)
        return person_id in self._known_ids


class FailingPersonService:
    """模拟可能包含敏感上下文的人员服务失败。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def exists(self, person_id: str) -> bool:
        self.calls.append(person_id)
        raise RuntimeError(
            "lookup failed for synthetic-person-id at E:\\synthetic\\people.json"
        )


def test_resolver_returns_immutable_ref_after_exact_chase_validation() -> None:
    service = RecordingPersonService({"chase"})
    resolver = PrimaryPersonResolver(
        OutfitSettings(enabled=True, primary_person_id="chase"), service
    )

    ref = resolver.resolve()

    assert ref.person_id == "chase"
    assert service.calls == ["chase"]
    with pytest.raises(FrozenInstanceError):
        ref.person_id = "someone-else"  # type: ignore[misc]


def test_resolver_rejects_disabled_outfit_without_person_lookup() -> None:
    service = RecordingPersonService({"chase"})
    resolver = PrimaryPersonResolver(OutfitSettings(), service)

    with pytest.raises(PrimaryPersonResolutionError) as error:
        resolver.resolve()

    assert error.value.code is PrimaryPersonErrorCode.DISABLED
    assert str(error.value) == PrimaryPersonErrorCode.DISABLED.value
    assert service.calls == []


def test_resolver_rejects_missing_primary_person_id_without_person_lookup() -> None:
    service = RecordingPersonService({"chase"})
    resolver = PrimaryPersonResolver(OutfitSettings(enabled=True), service)

    with pytest.raises(PrimaryPersonResolutionError) as error:
        resolver.resolve()

    assert error.value.code is PrimaryPersonErrorCode.MISSING_PRIMARY_PERSON_ID
    assert str(error.value) == PrimaryPersonErrorCode.MISSING_PRIMARY_PERSON_ID.value
    assert service.calls == []


def test_resolver_rejects_unknown_id_without_leaking_or_looking_it_up() -> None:
    raw_person_id = "private-person-id"
    service = RecordingPersonService({"chase", raw_person_id})
    resolver = PrimaryPersonResolver(
        OutfitSettings(enabled=True, primary_person_id=raw_person_id), service
    )

    with pytest.raises(PrimaryPersonResolutionError) as error:
        resolver.resolve()

    assert error.value.code is PrimaryPersonErrorCode.UNKNOWN_PRIMARY_PERSON
    assert str(error.value) == PrimaryPersonErrorCode.UNKNOWN_PRIMARY_PERSON.value
    assert raw_person_id not in str(error.value)
    assert service.calls == []


def test_resolver_rejects_unregistered_chase_with_fixed_error_code() -> None:
    service = RecordingPersonService(set())
    resolver = PrimaryPersonResolver(
        OutfitSettings(enabled=True, primary_person_id="chase"), service
    )

    with pytest.raises(PrimaryPersonResolutionError) as error:
        resolver.resolve()

    assert error.value.code is PrimaryPersonErrorCode.UNKNOWN_PRIMARY_PERSON
    assert str(error.value) == PrimaryPersonErrorCode.UNKNOWN_PRIMARY_PERSON.value
    assert service.calls == ["chase"]


def test_resolver_maps_person_lookup_failure_to_a_fixed_low_sensitivity_code() -> None:
    service = FailingPersonService()
    resolver = PrimaryPersonResolver(
        OutfitSettings(enabled=True, primary_person_id="chase"), service
    )

    with pytest.raises(PrimaryPersonResolutionError) as error:
        resolver.resolve()

    assert error.value.code is PrimaryPersonErrorCode.LOOKUP_FAILED
    assert str(error.value) == PrimaryPersonErrorCode.LOOKUP_FAILED.value
    assert "synthetic-person-id" not in str(error.value)
    assert "E:\\synthetic\\people.json" not in str(error.value)
    assert service.calls == ["chase"]
