from __future__ import annotations

import base64
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


@pytest.mark.asyncio
async def test_camera_voice_audio_capture_encodes_wav_for_asr(monkeypatch) -> None:
    from miloco.life import camera_voice

    callbacks: dict[str, object] = {}

    class _MiotService:
        async def start_camera_decode_audio_stream(
            self,
            camera_id: str,
            channel: int,
            callback,
        ) -> int:
            callbacks["audio"] = callback
            return 7

        async def stop_camera_decode_audio_stream(
            self,
            camera_id: str,
            channel: int,
            reg_id: int,
        ) -> None:
            return None

    fake_manager = ModuleType("miloco.manager")
    fake_manager.get_manager = lambda: SimpleNamespace(miot_service=_MiotService())
    monkeypatch.setitem(sys.modules, "miloco.manager", fake_manager)

    async def _emit_audio_frame(_seconds: float) -> None:
        audio_callback = callbacks["audio"]
        await audio_callback("cam1", np.zeros(1600, dtype=np.int16), 0, 0)

    monkeypatch.setattr(camera_voice.asyncio, "sleep", _emit_audio_frame)

    encoded, byte_count = await camera_voice._record_camera_audio_base64(
        camera_id="cam1",
        channel=0,
        duration_ms=1000,
    )

    assert encoded is not None
    raw = base64.b64decode(encoded)
    assert raw.startswith(b"RIFF")
    assert raw[8:12] == b"WAVE"
    assert byte_count == len(raw)
