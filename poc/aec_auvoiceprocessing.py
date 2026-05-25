"""POC AEC stack #3 — macOS AUVoiceProcessing IO (Apple built-in AEC+NS+AGC).

Status (2026-05-25): NO standalone POC possible from Python without writing
~150 LoC of CoreAudio bridge code (Objective-C / pyobjc) that drives a full
AudioUnit graph. AUVoiceProcessing is NOT a "filter you call frame-by-frame":
it OWNS the input + output devices and routes them through a private DSP graph
that pulls reference internally from the OutputUnit. There is no public API to
feed a "reference" buffer manually.

WHY NO POC:
    AUVoiceProcessing (subType kAudioUnitSubType_VoiceProcessingIO under
    AudioUnit kAudioUnitType_Output) is exposed via CoreAudio AudioUnit. The
    canonical use is:
        - Create an AUVoiceProcessingIO unit
        - Enable input AND output on the same unit
        - Set kAUVoiceIOProperty_BypassVoiceProcessing = 0
        - Set kAUVoiceIOProperty_VoiceProcessingEnableAGC = 1
        - Set kAUVoiceIOProperty_VoiceProcessingEnableDuckOthers as desired
        - Render callback returns AEC'd mic audio; OutputCallback feeds speaker.
    The AEC runs INSIDE the unit; you cannot inject a "reference" because the
    reference IS the audio you sent to the same unit's OutputScope.

PYTHON PATH:
    pyobjc-framework-CoreAudio gives ctypes access to AudioUnit APIs but the
    full integration (graph setup, render callbacks crossing the C/Python
    boundary at <10ms latency) is fragile and competes with sounddevice for
    device ownership. In practice, projects that need this on Python either:
        (a) call out to a small Swift/ObjC helper binary that owns CoreAudio,
            and pipe AEC'd PCM16 over stdout / domain socket (clean, ~250 LoC
            Swift, ships as bundled binary), OR
        (b) use AVAudioEngine via PyObjC and set
            inputNode.setVoiceProcessingEnabled(true) — iOS API, also on macOS
            13+. This still requires PyObjC + an event loop.

PROS vs Speex AEC (pyaec):
    + State of the art (Apple's own implementation, same as FaceTime/Siri).
    + Free CPU (runs on dedicated DSP block on M-series).
    + Handles double-talk, NLP, AGC, NS, comfort noise — all in one.
    + No reference-alignment headache: Apple does it internally.

CONS:
    - Replaces sounddevice for BOTH input and output (it OWNS the devices).
        ⇒ Major refactor of microphone.py + playback.py.
    - macOS only. Loses Linux/Windows portability.
    - Requires PyObjC bridge OR a bundled Swift binary.
    - ~150-250 LoC of plumbing before first echo-cancelled sample.

If quality is the dealbreaker (live test shows pyaec residual echo), this is
the upgrade path. Otherwise, pyaec is 30 min of integration and works on every
OS.

Run: this script just prints the diagnostic above and exits 0.
"""

from __future__ import annotations


def main() -> int:
    print(__doc__)
    print("(no executable POC — read header)")

    # Best-effort: confirm pyobjc-framework-CoreAudio could even be imported,
    # so the reader knows what to `pip install` if they want to take this path.
    try:
        import objc  # noqa: F401  — only here to detect pyobjc presence
        try:
            from CoreAudio import AudioComponentDescription  # type: ignore
            print("pyobjc + CoreAudio import OK — bridge path is reachable.")
        except Exception as exc:
            print(f"pyobjc installed but CoreAudio not yet imported: {exc!r}")
    except ModuleNotFoundError:
        print("pyobjc not installed — `pip install pyobjc-framework-CoreAudio`")
        print("if you want to explore this path. Not required if you go with pyaec.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
