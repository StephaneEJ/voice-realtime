"""POC AEC stack #2 — speexdsp (PyPI 0.1.1, last release 2018).

Status (2026-05-25, Python 3.14, Apple M-series):
    DOES NOT WORK out of the box. Requires THREE workarounds:

    1. `brew install swig speexdsp` to provide the SWIG compiler and Speex DSP headers.
    2. `pip install speexdsp` with `CFLAGS=-I/opt/homebrew/include LDFLAGS=-L/opt/homebrew/lib`
       — setup.py forgets to look in Homebrew prefix on Apple Silicon.
    3. Patch `site-packages/speexdsp/speexdsp.py` to remove the `import imp` block
       (the `imp` stdlib module was removed in Python 3.12). Replace the
       `swig_import_helper()` function with `from . import _speexdsp`.

    Even with all 3, the SWIG bindings are from SWIG 2.0.11 (2013) and have not
    been regenerated. There is no upstream maintainer.

This POC, after patching, exercises the EchoCanceller API.

Run (after brew install, env-CFLAGS install, AND in-place imp patch):
    python aec_speexdsp.py
"""

from __future__ import annotations

import math
import sys


SAMPLE_RATE = 16000
FRAME_SIZE = 160               # 10ms @ 16kHz
FILTER_LEN = 1600              # 100ms tail


def main() -> int:
    try:
        import speexdsp
    except Exception as exc:
        print(f"FAIL: speexdsp import error → {exc!r}")
        print("If this is `ModuleNotFoundError: No module named 'imp'`, you need")
        print("to patch site-packages/speexdsp/speexdsp.py — see header comment.")
        return 1

    print(f"speexdsp module: {speexdsp.__file__}")
    print(f"attrs: {[a for a in dir(speexdsp) if not a.startswith('_')]}")

    # API discovered: speexdsp.EchoCanceller_create(frame_size, filter_length, sample_rate)
    # returns an EchoCanceller object with a `process(near, far)` method.
    ec = speexdsp.EchoCanceller_create(FRAME_SIZE, FILTER_LEN, SAMPLE_RATE)
    print(f"EchoCanceller created: {ec}")
    print(f"methods: {[m for m in dir(ec) if not m.startswith('_')]}")

    # Build test frames — SWIG wants C arrays. Try bytes first (SWIG typemap usually accepts).
    near = bytes()
    far = bytes()
    for i in range(FRAME_SIZE):
        mic_sample = int(1500 * math.sin(2 * math.pi * 300 * i / SAMPLE_RATE))
        ref_sample = int(8000 * math.sin(2 * math.pi * 1000 * i / SAMPLE_RATE))
        echo_in_mic = mic_sample + int(ref_sample * 0.6)
        # int16 little-endian, 2 bytes per sample
        near += int(echo_in_mic).to_bytes(2, "little", signed=True)
        far += int(ref_sample).to_bytes(2, "little", signed=True)

    try:
        out = ec.process(near, far)
        print(f"OK — process() returned {type(out).__name__} of length {len(out)}")
    except Exception as exc:
        print(f"FAIL: ec.process() raised {exc!r}")
        return 2

    print()
    print("Notes (vs pyaec, same underlying algorithm):")
    print("- Same Speex MDF AEC under the hood — algo quality identical.")
    print("- BUT: stale SWIG bindings, no maintenance since 2018, requires brew + patch.")
    print("- Strongly recommend pyaec instead — same algo, modern packaging, MIT licence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
