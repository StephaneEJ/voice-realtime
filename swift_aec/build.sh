#!/usr/bin/env bash
# Build the Swift mic capture binary that pipes voiceProcessing'd PCM16
# from CoreAudio to stdout. Invoked by:
#   - manual dev (`./build.sh` from this directory)
#   - the voice-realtime build pipeline before distribution (planned)
#
# Output: build/aec_mic (single statically-linked Mach-O binary, ~65 KB).
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p build
swiftc -O -o build/aec_mic Sources/aec_mic.swift
echo "built: $(pwd)/build/aec_mic ($(wc -c < build/aec_mic) bytes)"
