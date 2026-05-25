# swift_aec — Apple AUVoiceProcessingIO mic capture

Standalone Swift binary that opens `AVAudioEngine` with
`setVoiceProcessingEnabled(true)` (= Apple's FaceTime-grade echo
cancellation + noise suppression), downmixes the MBP mic array to mono,
resamples to 16 kHz PCM16 little-endian, and writes the raw bytes to
stdout.

Replaces `pyaec` / SpeexDSP MDF, which silent-failed in real-world
conditions on the MBP Air speaker + mic combo (live test 2026-05-25 —
model auto-triggered on its own voice, AEC residual + non-linear echo
overwhelmed the MDF model).

## Why a separate binary

- Apple's voice processing AU has no Python binding — talking to CoreAudio
  through ctypes would be ~1500 lines and unmaintainable.
- A tiny CLI piped over stdin is the cheapest interop layer that works
  from Python's `MicrophoneStream` (planned) — no PortAudio coupling, no
  Swift-in-the-loop bundling at runtime.
- macOS TCC permission is inherited from the parent process (Terminal or
  the Tauri host), so the binary doesn't need its own bundle yet. When we
  ship the `.app`, the host's `NSMicrophoneUsageDescription` will cover it.

## Build

```bash
./build.sh
```

Output: `build/aec_mic` (~65 KB, statically linked Mach-O ARM64).

## Smoke test

```bash
./build/aec_mic > /tmp/aec.raw 2> /tmp/aec.err &
sleep 5; kill %1
# Should be ~160 KB (5 s × 16 kHz × 2 B) minus ~1 s warmup
wc -c /tmp/aec.raw
# Should show "ready — streaming PCM16 mono @ 16000 Hz"
cat /tmp/aec.err
# Play back to verify the AEC made it through
ffplay -f s16le -ar 16000 -ac 1 /tmp/aec.raw
```

## Known quirks

- ~1 s of zero-amplitude samples at the start while `AVAudioEngine` warms
  up — the Python integration must skip or zero-VU these.
- Logs `mic permission status (initial)` to stderr at startup; if the
  status is not `.authorized` (raw value 3), the OS hasn't granted access
  to the parent process — surface this to the user.
