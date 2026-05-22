"""Cost tracker — live cost estimate + hard kill switch + jsonl persistence."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path.home() / ".voice-realtime" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# 2026-05-22 pricing (USD per hour, approx, conversational mix in/out audio).
# Per-model rates take priority — fall back to per-provider default if model unknown.
# OpenAI gpt-realtime-2  : $32/$64 per 1M in/out audio tokens ≈ $5/h
# OpenAI gpt-realtime-mini : $8/$16 per 1M ≈ $1.25/h (4× cheaper than gpt-realtime-2)
# Gemini 2.5-flash-native-audio : $3/$12 per 1M ≈ $1.40/h (latest + preview-12-2025 same)
DEFAULT_HOURLY_RATE_USD_BY_MODEL = {
    "gpt-realtime-2": 5.0,
    "gpt-realtime": 5.0,           # latest alias
    "gpt-realtime-mini": 1.25,
    "gpt-realtime-1.5": 4.0,       # legacy
    "gemini-2.5-flash-native-audio-latest": 1.40,
    "gemini-2.5-flash-native-audio-preview-12-2025": 1.40,
    "gemini-3.1-flash-live-preview": 1.40,
}
DEFAULT_HOURLY_RATE_USD_BY_PROVIDER = {
    "openai": 5.0,
    "gemini": 1.40,
}


@dataclass
class CostTracker:
    provider: str
    model: str
    hourly_rate_usd: float = field(default=0.0)
    started_at: float = field(default_factory=time.monotonic)
    started_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    warning_cost_usd: float = 1.00
    hard_stop_cost_usd: float = 3.00
    max_duration_seconds: float = 900.0  # 15 min default
    _warned: bool = False

    def __post_init__(self) -> None:
        if self.hourly_rate_usd <= 0:
            # Model-specific rate wins ; fall back to provider default ; last resort $5/h.
            self.hourly_rate_usd = (
                DEFAULT_HOURLY_RATE_USD_BY_MODEL.get(self.model)
                or DEFAULT_HOURLY_RATE_USD_BY_PROVIDER.get(self.provider, 5.0)
            )

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def estimated_cost_usd(self) -> float:
        return (self.elapsed_seconds / 3600.0) * self.hourly_rate_usd

    def should_warn(self) -> bool:
        if self._warned:
            return False
        if self.estimated_cost_usd >= self.warning_cost_usd:
            self._warned = True
            return True
        return False

    def should_kill(self) -> tuple[bool, str]:
        if self.estimated_cost_usd >= self.hard_stop_cost_usd:
            return True, f"hard cost cap ${self.hard_stop_cost_usd:.2f} reached"
        if self.elapsed_seconds >= self.max_duration_seconds:
            return True, f"max duration {self.max_duration_seconds:.0f}s reached"
        return False, ""

    def persist(self, transcript: str = "", reason: str = "ended") -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = SESSIONS_DIR / f"{ts}_{self.provider}.jsonl"
        record = {
            "started_iso": self.started_iso,
            "ended_iso": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "provider": self.provider,
            "model": self.model,
            "hourly_rate_usd": self.hourly_rate_usd,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "end_reason": reason,
            "transcript_chars": len(transcript),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path


def monthly_total_usd() -> float:
    """Sum estimated_cost_usd from all session jsonl files this month."""
    now = datetime.now(timezone.utc)
    prefix = now.strftime("%Y%m")
    total = 0.0
    for path in SESSIONS_DIR.glob("*.jsonl"):
        if not path.name.startswith(prefix):
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                total += float(record.get("estimated_cost_usd", 0.0))
        except (OSError, json.JSONDecodeError):
            continue
    return total
