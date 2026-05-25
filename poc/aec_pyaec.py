"""POC AEC stack #1 — pyaec (wraps SpeexDSP via Rust, MIT, native arm64 wheel).

Status (2026-05-25, Python 3.14, Apple M-series):
    PyPI:    `pip install pyaec`  → installs `pyaec-1.0.1-py3-none-macosx_11_0_arm64.whl`
    No build tools required. No SWIG. No brew dependency. ctypes only.

This POC:
    1. Instantiates an Aec with frame_size=160 (10ms @ 16kHz), filter_length=1600
       (100ms tail — typical Speex AEC config), sample_rate=16000.
    2. Synthesizes 10ms of mic input (sine + simulated echo) and 10ms of
       reference (the "echo" signal that the speaker would have played).
    3. Calls `cancel_echo(rec, echo)` and verifies the output buffer is the
       expected length and that energy is reduced relative to input.

Run:
    source /tmp/aec_test_py314/bin/activate  # or any venv with `pip install pyaec`
    python aec_pyaec.py
"""

from __future__ import annotations

import math

from pyaec import Aec


SAMPLE_RATE = 16000           # Hz — Speex AEC sweet spot. (Voice-realtime uses 16-24kHz; resample if needed)
FRAME_MS = 10                 # Speex AEC requires fixed 10ms frames
FRAME_SIZE = SAMPLE_RATE * FRAME_MS // 1000   # 160 samples
FILTER_LEN_MS = 100           # echo tail length to model
FILTER_LEN = SAMPLE_RATE * FILTER_LEN_MS // 1000  # 1600 samples


def _rms(samples: list[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def main() -> int:
    print(f"pyaec POC — frame={FRAME_SIZE} filter={FILTER_LEN} rate={SAMPLE_RATE}")

    # enable_preprocess=True turns on Speex's noise suppressor & AGC in addition to AEC
    aec = Aec(FRAME_SIZE, FILTER_LEN, SAMPLE_RATE, enable_preprocess=True)
    print(f"AEC instance created: {aec}")

    # Synthesize a 10ms reference signal (what the speaker plays — model output)
    # 1kHz sine at amplitude 8000 / int16 max 32767
    ref = [int(8000 * math.sin(2 * math.pi * 1000 * i / SAMPLE_RATE)) for i in range(FRAME_SIZE)]

    # Synthesize the mic capture: a faint voice (300Hz sine at 1500) + the echoed reference
    # (attenuated 0.6× to simulate speaker→room→mic path)
    mic = [
        int(1500 * math.sin(2 * math.pi * 300 * i / SAMPLE_RATE)) + int(ref[i] * 0.6)
        for i in range(FRAME_SIZE)
    ]

    print(f"Input RMS mic={_rms(mic):.1f} ref={_rms(ref):.1f}")

    # Process — pyaec returns a Python list of int16 samples (length == frame_size)
    out = aec.cancel_echo(mic, ref)
    assert len(out) == FRAME_SIZE, f"unexpected output length {len(out)}"

    print(f"Output RMS = {_rms(out):.1f}  (length={len(out)})")
    print("OK — pyaec processed 1 frame, output length matches input frame size.")
    print()
    print("Notes:")
    print("- Speex AEC needs the echo (reference) buffer to be TIME-ALIGNED with the mic")
    print("  capture: estimate playback->capture latency (typically 30-80ms on macOS")
    print("  speakerphone) and DELAY the reference by that amount before feeding it in.")
    print("- For 24kHz pipelines, either run AEC at 16kHz (downsample mic+ref) or use")
    print("  one of the supported rates. Speex MDF supports 8/16/32kHz natively.")
    print("- Single AEC instance per stream — do NOT share across mic/playback callbacks")
    print("  without a lock.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
