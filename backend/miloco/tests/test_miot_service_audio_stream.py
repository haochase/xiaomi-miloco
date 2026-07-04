from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from miloco.miot.service import MiotService


def _service_with_proxy_methods() -> MiotService:
    proxy = SimpleNamespace(
        _kv_repo=SimpleNamespace(
            db_connector=SimpleNamespace(
                execute_query=lambda *args, **kwargs: [],
                execute_update=lambda *args, **kwargs: 0,
            ),
        ),
        start_camera_decode_audio_stream=AsyncMock(return_value=42),
        stop_camera_decode_audio_stream=AsyncMock(),
    )
    return MiotService(miot_proxy=proxy)


@pytest.mark.asyncio
async def test_decode_audio_stream_registration_is_proxied() -> None:
    service = _service_with_proxy_methods()
    callback = AsyncMock()

    reg_id = await service.start_camera_decode_audio_stream("cam1", 0, callback)
    await service.stop_camera_decode_audio_stream("cam1", 0, reg_id)

    assert reg_id == 42
    service._miot_proxy.start_camera_decode_audio_stream.assert_awaited_once_with(
        "cam1",
        0,
        callback,
    )
    service._miot_proxy.stop_camera_decode_audio_stream.assert_awaited_once_with(
        "cam1",
        0,
        42,
    )
