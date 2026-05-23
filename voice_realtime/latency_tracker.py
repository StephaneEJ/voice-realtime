"""Latency tracker for voice-realtime sessions.

Two metrics that matter for perceived UX :
- TTFA (time-to-first-audio) : ms from user's last mic chunk sent to first model
  audio chunk received. Captures round-trip + first-token generation time.
- TTFI (time-to-flush-on-interrupt) : ms from `model_interrupted` server event
  to local player buffer flush completion. If high, model continues talking
  after user breaks in — pain point flagged in session 2026-05-23 15:17.

All access from the single asyncio event loop ; GIL is enough, no lock.
"""

from __future__ import annotations

import time
from collections import deque


class LatencyTracker:
    def __init__(self, window: int = 5) -> None:
        self._ttfa_ms: deque[float] = deque(maxlen=window)
        self._ttfi_ms: deque[float] = deque(maxlen=window)
        self._last_user_audio_at: float | None = None
        self._first_audio_received_this_turn: bool = False
        self._interrupt_started_at: float | None = None

    def on_user_audio_sent(self) -> None:
        self._last_user_audio_at = time.monotonic()

    def on_model_audio_received(self) -> None:
        if self._first_audio_received_this_turn:
            return
        if self._last_user_audio_at is not None:
            ttfa = (time.monotonic() - self._last_user_audio_at) * 1000.0
            self._ttfa_ms.append(ttfa)
        self._first_audio_received_this_turn = True

    def on_turn_complete(self) -> None:
        self._first_audio_received_this_turn = False

    def on_interrupt_signal(self) -> None:
        self._interrupt_started_at = time.monotonic()
        self._first_audio_received_this_turn = False

    def on_flush_complete(self) -> None:
        if self._interrupt_started_at is not None:
            ttfi = (time.monotonic() - self._interrupt_started_at) * 1000.0
            self._ttfi_ms.append(ttfi)
            self._interrupt_started_at = None

    @property
    def last_ttfa_ms(self) -> float | None:
        return self._ttfa_ms[-1] if self._ttfa_ms else None

    @property
    def avg_ttfa_ms(self) -> float | None:
        return (sum(self._ttfa_ms) / len(self._ttfa_ms)) if self._ttfa_ms else None

    @property
    def last_ttfi_ms(self) -> float | None:
        return self._ttfi_ms[-1] if self._ttfi_ms else None

    @property
    def avg_ttfi_ms(self) -> float | None:
        return (sum(self._ttfi_ms) / len(self._ttfi_ms)) if self._ttfi_ms else None
