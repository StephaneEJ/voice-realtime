"""Smoke test — imports + instantiation without launching audio session."""
from __future__ import annotations

from voice_realtime.cli import app
from voice_realtime.audio import MicrophoneStream, AudioPlayer
from voice_realtime.context_loader import build_context, find_active_phase
from voice_realtime.cost_tracker import CostTracker, monthly_total_usd
from voice_realtime.session_saver import save_session_note
from voice_realtime.providers.openai_realtime import OpenAIRealtimeProvider
from voice_realtime.providers.gemini import GeminiProvider


def main() -> None:
    print("All imports OK")
    print("---")
    phase = find_active_phase()
    print(f"Active phase: {phase}")
    ctx = build_context(project_hint="Voice Realtime")
    print(f"Context length: {len(ctx)} chars")
    print("First 300 chars:")
    print(ctx[:300])
    print("---")
    monthly = monthly_total_usd()
    print(f"Monthly cost so far: ${monthly:.4f}")
    print("---")
    print("Instantiate providers (no network):")
    OpenAIRealtimeProvider()
    GeminiProvider()
    print("OK")


if __name__ == "__main__":
    main()
