"""Unit tests for the AEC wrapper.

The Speex MDF engine is mocked — these tests only validate framing, ring
buffer alignment, resampling, and integration plumbing. Echo-cancellation
quality is validated live by ``voice-realtime talk --aec`` on hardware.
"""

from __future__ import annotations

import math
import sys
from types import ModuleType, SimpleNamespace
from typing import List

import numpy as np
import pytest


class _FakeAec:
    """Stand-in for pyaec.Aec — returns mic minus 0.5×ref, integer rounded.

    The signature mirrors the real engine: ``cancel_echo(mic_list, ref_list)``
    returns ``list[int]`` of the same length as the inputs.
    """

    def __init__(self, frame_size: int, filter_len: int, sample_rate: int, enable_preprocess: bool = True) -> None:
        self.frame_size = frame_size
        self.filter_len = filter_len
        self.sample_rate = sample_rate
        self.enable_preprocess = enable_preprocess
        self.calls: list[tuple[list[int], list[int]]] = []

    def cancel_echo(self, mic: List[int], ref: List[int]) -> List[int]:
        assert len(mic) == self.frame_size
        assert len(ref) == self.frame_size
        self.calls.append((mic, ref))
        return [int(m - 0.5 * r) for m, r in zip(mic, ref)]


@pytest.fixture(autouse=True)
def _inject_fake_pyaec(monkeypatch):
    fake_module = ModuleType("pyaec")
    fake_module.Aec = _FakeAec  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyaec", fake_module)
    # Force a fresh import of voice_realtime.audio.aec so the fake module is
    # picked up at import time inside the EchoCanceller constructor.
    monkeypatch.delitem(sys.modules, "voice_realtime.audio.aec", raising=False)
    yield


def _sine_pcm16(freq_hz: float, rate: int, ms: int, amp: int = 8000) -> bytes:
    n = rate * ms // 1000
    samples = np.array(
        [int(amp * math.sin(2 * math.pi * freq_hz * i / rate)) for i in range(n)],
        dtype=np.int16,
    )
    return samples.tobytes()


def _rms(pcm16: bytes) -> float:
    arr = np.frombuffer(pcm16, dtype=np.int16).astype(np.float64)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)))


def test_process_returns_same_length_at_16k():
    from voice_realtime.audio.aec import EchoCanceller

    ec = EchoCanceller(delay_ms=0, tail_ms=100)
    mic = _sine_pcm16(300, 16000, 20)  # 20 ms = 2 frames
    out = ec.process(mic, src_rate=16000)
    assert len(out) == len(mic)


def test_process_returns_resampled_length_from_24k():
    from voice_realtime.audio.aec import EchoCanceller

    ec = EchoCanceller(delay_ms=0, tail_ms=100)
    # 60 ms at 24 kHz = 1440 samples → resamples to 960 samples @ 16 kHz =
    # 6 × 10 ms frames, no leftover.
    mic = _sine_pcm16(300, 24000, 60)
    out = ec.process(mic, src_rate=24000)
    assert len(out) == 960 * 2  # 6 frames × 320 bytes


def test_reference_alignment_pulls_pushed_audio():
    """After push_reference, the next process() consumes those bytes."""
    from voice_realtime.audio.aec import EchoCanceller, FRAME_BYTES

    ec = EchoCanceller(delay_ms=0, tail_ms=100)  # no pre-pad to keep alignment simple
    ref = _sine_pcm16(1000, 16000, 10)  # 1 frame of strong sine
    ec.push_reference(ref, src_rate=16000)
    mic = b"\x00" * FRAME_BYTES  # silent mic
    _ = ec.process(mic, src_rate=16000)
    # The fake engine recorded the ref it received — should match what we pushed.
    aec_instance = ec._aec  # type: ignore[attr-defined]
    assert len(aec_instance.calls) == 1
    _, ref_received = aec_instance.calls[0]
    ref_expected = np.frombuffer(ref, dtype=np.int16).tolist()
    assert ref_received == ref_expected


def test_pre_pad_delays_reference_consumption():
    """With delay_ms=60 the first 60 ms of mic should see silence as ref."""
    from voice_realtime.audio.aec import EchoCanceller

    ec = EchoCanceller(delay_ms=60, tail_ms=100)
    ref = _sine_pcm16(1000, 16000, 10)
    ec.push_reference(ref, src_rate=16000)
    # First mic frame consumes pre-padded silence, not our pushed ref.
    mic = b"\x00" * (16000 * 10 // 1000 * 2)
    _ = ec.process(mic, src_rate=16000)
    aec_instance = ec._aec  # type: ignore[attr-defined]
    assert len(aec_instance.calls) == 1
    _, ref_received = aec_instance.calls[0]
    assert all(s == 0 for s in ref_received), "first frame should pull silence under 60ms delay"


def test_rms_attenuation_with_fake_engine():
    """Fake engine returns mic - 0.5×ref → mic of (sine + 0.6×ref) drops in RMS."""
    from voice_realtime.audio.aec import EchoCanceller

    ec = EchoCanceller(delay_ms=0, tail_ms=100)
    ref = _sine_pcm16(1000, 16000, 10, amp=8000)
    ref_arr = np.frombuffer(ref, dtype=np.int16).astype(np.int32)
    voice = np.array(
        [int(1500 * math.sin(2 * math.pi * 300 * i / 16000)) for i in range(ref_arr.size)],
        dtype=np.int32,
    )
    mic_arr = (voice + (ref_arr * 0.6).astype(np.int32)).astype(np.int16)
    mic = mic_arr.tobytes()
    rms_in = _rms(mic)
    ec.push_reference(ref, src_rate=16000)
    out = ec.process(mic, src_rate=16000)
    rms_out = _rms(out)
    # Fake engine subtracts 0.5 × ref; mic contained 0.6 × ref → residual is
    # voice + 0.1 × ref, so RMS should drop meaningfully (>20%).
    assert rms_out < rms_in * 0.80, f"expected attenuation, got rms_in={rms_in:.0f} rms_out={rms_out:.0f}"


def test_reset_clears_buffer_and_repads():
    from voice_realtime.audio.aec import EchoCanceller

    ec = EchoCanceller(delay_ms=20, tail_ms=100)
    ref = _sine_pcm16(1000, 16000, 30)  # 30 ms of ref
    ec.push_reference(ref, src_rate=16000)
    ec.reset()
    # After reset the buffer should hold ONLY the silence pre-pad (20 ms).
    expected_pad_bytes = 16000 * 20 // 1000 * 2
    assert len(ec._ref_buffer) == expected_pad_bytes  # type: ignore[attr-defined]
    assert all(b == 0 for b in ec._ref_buffer)  # type: ignore[attr-defined]


def test_microphone_stream_runs_aec_on_callback():
    """Smoke test: MicrophoneStream forwards bytes through aec.process."""
    from voice_realtime.audio.aec import EchoCanceller
    from voice_realtime.audio.microphone import MicrophoneStream

    ec = EchoCanceller(delay_ms=0, tail_ms=100)
    mic = MicrophoneStream(rate=16000, chunk_ms=10, aec=ec)
    mic._loop = SimpleNamespace(
        call_soon_threadsafe=lambda fn, payload: mic._safe_put(payload),
    )  # type: ignore[assignment]
    indata = np.full(160, 1000, dtype=np.int16).reshape(160, 1)
    mic._sd_callback(indata, 160, None, None)
    # One chunk should be in the queue, of length matching 10 ms @ 16 kHz int16.
    assert mic._queue.qsize() == 1
    chunk = mic._queue.get_nowait()
    assert len(chunk) == 160 * 2


def test_player_pushes_reference_into_aec():
    """Smoke test: AudioPlayer._sd_callback feeds the ref ring buffer."""
    from voice_realtime.audio.aec import EchoCanceller, FRAME_BYTES
    from voice_realtime.audio.playback import AudioPlayer

    ec = EchoCanceller(delay_ms=0, tail_ms=100)
    player = AudioPlayer(rate=24000, aec=ec)
    pcm = _sine_pcm16(1000, 24000, 20)  # 20 ms @ 24 kHz
    # Pre-load buffer then trigger the callback.
    player._buffer.extend(pcm)  # type: ignore[attr-defined]
    frames = 24000 * 20 // 1000  # 480
    outdata = np.zeros((frames, 1), dtype=np.int16)
    player._sd_callback(outdata, frames, None, None)
    # The 20 ms of 24 kHz audio resamples to ~320 samples @ 16 kHz = 640 bytes
    # of ref, which is 2 full frames.
    assert len(ec._ref_buffer) == FRAME_BYTES * 2  # type: ignore[attr-defined]
