"""LocalProvider Phase 3.1 stub — verify NotImplementedError surfaces clearly.

Future implementer can replace these tests with real behavior tests.
For now, the goal is to lock in the API surface so Phase 2 code that
depends on the Protocol stays type-safe.
"""

from __future__ import annotations

import pytest

from voice_realtime.providers.base import ProviderConfig
from voice_realtime.providers.local import LocalProvider, LocalProviderDeps


async def test_local_provider_instantiates() -> None:
    p = LocalProvider()
    assert p.name == "local"


async def test_local_provider_connect_raises_not_implemented() -> None:
    p = LocalProvider()
    cfg = ProviderConfig(model="qwen2.5:3b", api_key="dummy")
    with pytest.raises(NotImplementedError):
        await p.connect(cfg, "system prompt")


async def test_local_provider_send_text_raises() -> None:
    p = LocalProvider()
    with pytest.raises(NotImplementedError):
        await p.send_text("hi")


async def test_local_provider_send_audio_chunk_raises() -> None:
    p = LocalProvider()
    with pytest.raises(NotImplementedError):
        await p.send_audio_chunk(b"\x00\x00")


async def test_local_provider_close_marks_closed() -> None:
    p = LocalProvider()
    await p.close()
    assert p._closed is True


def test_local_provider_deps_default_lookups() -> None:
    deps = LocalProviderDeps()
    assert deps.whisper_cli == "whisper-cli"
    assert deps.ollama_model == "qwen2.5:3b"
    assert deps.piper_voice.startswith("fr_FR")
