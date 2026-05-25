"""Acoustic Echo Cancellation — wraps pyaec (SpeexDSP MDF) for hands-free voice.

The EchoCanceller holds a ring buffer of recently-played reference audio (the
model's voice as fed to the speaker) and, for each mic frame, pulls the
time-aligned reference and runs Speex MDF to subtract the echo path.

Speex MDF constraints:
    - Fixed 10ms frames at the chosen sample rate.
    - Native rates: 8/16/32 kHz. We standardise on 16 kHz internally — model
      output is usually 24 kHz, so the player resamples its reference before
      pushing into the canceller. The mic is also expected at 16 kHz (caller
      forces ``mic_rate=16000`` when ``aec`` is active).

Threading:
    - ``push_reference`` is called from the PortAudio output callback thread.
    - ``process`` is called from the PortAudio input callback thread.
    - Both serialise on ``self._lock`` over the ref ring buffer. The Aec
      instance itself is single-instance per stream and must not be shared
      across callbacks without that lock — which we enforce here.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover — import only for type hints
    from pyaec import Aec  # type: ignore[import-not-found]


INTERNAL_RATE = 16000          # Speex MDF sweet spot
FRAME_MS = 10                  # MDF requires fixed 10ms frames
FRAME_SAMPLES = INTERNAL_RATE * FRAME_MS // 1000   # 160
FRAME_BYTES = FRAME_SAMPLES * 2                    # int16 mono


def _resample_linear_to_16k(pcm16: bytes, src_rate: int) -> bytes:
    """Cheap linear resampler to 16 kHz. Sufficient for AEC reference path.

    For higher quality (mic-side audio actually sent to STT) callers should
    use ``scipy.signal.resample_poly`` instead, but for the speaker reference
    fed into Speex MDF, linear is fine — Speex is robust to small spectral
    distortions on the reference.
    """
    if src_rate == INTERNAL_RATE or not pcm16:
        return pcm16
    arr = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32)
    n_in = arr.shape[0]
    n_out = max(1, int(round(n_in * INTERNAL_RATE / src_rate)))
    if n_out == n_in:
        return arr.astype(np.int16).tobytes()
    xp = np.linspace(0.0, 1.0, n_in, endpoint=False, dtype=np.float64)
    fp = arr.astype(np.float64)
    x = np.linspace(0.0, 1.0, n_out, endpoint=False, dtype=np.float64)
    out = np.interp(x, xp, fp)
    return out.astype(np.int16).tobytes()


class EchoCanceller:
    """Online AEC with a ring-buffered reference path.

    Lifecycle:
        ec = EchoCanceller(delay_ms=60)
        # in playback callback (after writing speaker samples):
        ec.push_reference(outdata_bytes, src_rate=24000)
        # in mic callback (before enqueueing for the model):
        clean = ec.process(mic_bytes, src_rate=16000)
    """

    def __init__(
        self,
        delay_ms: int = 60,
        tail_ms: int = 100,
        enable_preprocess: bool = True,
    ) -> None:
        # Import here so the module can be imported without pyaec installed
        # (tests can mock the engine).
        from pyaec import Aec  # type: ignore[import-not-found]

        filter_samples = INTERNAL_RATE * tail_ms // 1000
        self._aec: "Aec" = Aec(
            FRAME_SAMPLES,
            filter_samples,
            INTERNAL_RATE,
            enable_preprocess=enable_preprocess,
        )

        self._lock = threading.Lock()
        # Pre-pad the ref ring with ``delay_ms`` of silence so the first mic
        # frames pull silence — which is correct, since the speaker hasn't
        # had time to produce echo yet.
        delay_samples = INTERNAL_RATE * delay_ms // 1000
        self._ref_buffer = bytearray(delay_samples * 2)
        # Cap the buffer at 8× delay so an offline phase (mic muted) doesn't
        # accumulate ref forever.
        self._max_ref_bytes = max(delay_samples * 2 * 8, FRAME_BYTES * 32)
        self.delay_ms = delay_ms
        self.tail_ms = tail_ms

    def push_reference(self, ref_pcm16: bytes, src_rate: int = INTERNAL_RATE) -> None:
        if not ref_pcm16:
            return
        resampled = _resample_linear_to_16k(ref_pcm16, src_rate)
        with self._lock:
            self._ref_buffer.extend(resampled)
            overflow = len(self._ref_buffer) - self._max_ref_bytes
            if overflow > 0:
                del self._ref_buffer[:overflow]

    def process(self, mic_pcm16: bytes, src_rate: int = INTERNAL_RATE) -> bytes:
        """Cancel echo on a mic chunk. Returns the same number of samples
        (post-resample to 16 kHz). Caller can resample back if needed."""
        if not mic_pcm16:
            return mic_pcm16
        mic_16k = _resample_linear_to_16k(mic_pcm16, src_rate)
        out = bytearray()
        offset = 0
        while offset + FRAME_BYTES <= len(mic_16k):
            mic_frame = mic_16k[offset:offset + FRAME_BYTES]
            offset += FRAME_BYTES
            with self._lock:
                if len(self._ref_buffer) >= FRAME_BYTES:
                    ref_frame = bytes(self._ref_buffer[:FRAME_BYTES])
                    del self._ref_buffer[:FRAME_BYTES]
                else:
                    # Underrun: no recent ref → assume no echo on this frame.
                    ref_frame = b"\x00" * FRAME_BYTES
            mic_list = np.frombuffer(mic_frame, dtype=np.int16).tolist()
            ref_list = np.frombuffer(ref_frame, dtype=np.int16).tolist()
            cancelled = self._aec.cancel_echo(mic_list, ref_list)
            out.extend(np.asarray(cancelled, dtype=np.int16).tobytes())
        # Pass through any sub-frame leftover unchanged. With sensible
        # ``chunk_ms`` (multiples of 10 ms) this branch never fires.
        if offset < len(mic_16k):
            out.extend(mic_16k[offset:])
        return bytes(out)

    def reset(self) -> None:
        """Drop the pending reference buffer. Call on a barge-in/flush so the
        next mic frames are processed against silence rather than stale
        post-interrupt audio."""
        with self._lock:
            self._ref_buffer.clear()
            # Re-pad the silence cushion so the first post-reset frame still
            # sees an aligned-but-empty echo path.
            delay_samples = INTERNAL_RATE * self.delay_ms // 1000
            self._ref_buffer.extend(b"\x00" * (delay_samples * 2))
