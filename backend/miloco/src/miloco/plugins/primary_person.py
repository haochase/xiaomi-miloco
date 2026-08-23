# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Outfit 主使用者的显式、低敏感度解析。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from miloco.config.settings import OutfitSettings


class PersonLookup(Protocol):
    """解析器需要的最小人员服务能力。"""

    def exists(self, person_id: str) -> bool:
        """返回固定 person ID 是否已注册。"""


class PrimaryPersonErrorCode(str, Enum):
    """主使用者解析可安全暴露的固定错误码。"""

    DISABLED = "outfit_primary_person_disabled"
    MISSING_PRIMARY_PERSON_ID = "outfit_primary_person_id_missing"
    UNKNOWN_PRIMARY_PERSON = "outfit_primary_person_unknown"
    LOOKUP_FAILED = "outfit_primary_person_lookup_failed"


class PrimaryPersonResolutionError(RuntimeError):
    """只携带固定错误码，避免在错误文本中暴露人员标识。"""

    def __init__(self, code: PrimaryPersonErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class PrimaryPersonRef:
    """可选插件消费的不可变主使用者引用。"""

    person_id: str


class PrimaryPersonResolver:
    """仅解析配置的稳定主使用者 ID，不提供任何身份回退。"""

    def __init__(self, outfit: OutfitSettings, person_service: PersonLookup) -> None:
        self._outfit = outfit
        self._person_service = person_service

    def resolve(self) -> PrimaryPersonRef:
        if not self._outfit.enabled:
            raise PrimaryPersonResolutionError(PrimaryPersonErrorCode.DISABLED)
        person_id = self._outfit.primary_person_id
        if person_id is None:
            raise PrimaryPersonResolutionError(
                PrimaryPersonErrorCode.MISSING_PRIMARY_PERSON_ID
            )
        try:
            person_exists = self._person_service.exists(person_id)
        except Exception:
            raise PrimaryPersonResolutionError(
                PrimaryPersonErrorCode.LOOKUP_FAILED
            ) from None
        if not person_exists:
            raise PrimaryPersonResolutionError(
                PrimaryPersonErrorCode.UNKNOWN_PRIMARY_PERSON
            )
        return PrimaryPersonRef(person_id=person_id)
