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

    # Token estimates — proxy values derived from elapsed time, NOT real
    # provider usage_metadata. Both providers stream tokens but neither
    # exposes a clean realtime counter today; we approximate at ~50 tok/s
    # per direction (audio tokenization is roughly ~3000 tokens per minute
    # for mid-quality speech). Replace with provider-reported counts when
    # OpenAI Realtime `response.done` usage / Gemini usage_metadata wiring
    # lands (separate sprint).
    _TOKENS_PER_SECOND = 50.0
    # Conservative model context window proxy — used by UI as denominator.
    # Gemini Live: 1M tokens. OpenAI Realtime-2: 128k tokens.
    _CONTEXT_WINDOW_BY_PROVIDER = {"gemini": 1_000_000, "openai": 128_000}

    @property
    def estimated_tokens_in(self) -> int:
        return int(self.elapsed_seconds * self._TOKENS_PER_SECOND)

    @property
    def estimated_tokens_out(self) -> int:
        return int(self.elapsed_seconds * self._TOKENS_PER_SECOND)

    @property
    def estimated_tokens_total(self) -> int:
        return self.estimated_tokens_in + self.estimated_tokens_out

    @property
    def context_window_tokens(self) -> int:
        return self._CONTEXT_WINDOW_BY_PROVIDER.get(self.provider, 128_000)

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

    def persist(
        self,
        transcript: str = "",
        reason: str = "ended",
        project_hint: str | None = None,
        vault_note_path: str | None = None,
    ) -> Path:
        """Write the session record to local jsonl + best-effort to NocoDB.

        jsonl stays the source of truth (always writes, no external deps).
        NocoDB is opt-in via ~/.nocodb.env: success makes the row show up in
        the dashboard-perso /voice tab; failure is logged and swallowed.
        """
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

        # Best-effort NocoDB mirror — never crashes the caller.
        try:
            from .nocodb_writer import insert_session, session_record_from_tracker
            nc_record = session_record_from_tracker(
                record, project_hint=project_hint, vault_note_path=vault_note_path,
            )
            insert_session(nc_record)
        except Exception:
            pass

        return path


def _iter_session_records():
    """Yield (path, parsed record dict) for every jsonl line on disk.

    Errors (unreadable file, bad JSON line) are skipped silently — one bad
    record shouldn't hide the rest.
    """
    for path in SESSIONS_DIR.glob("*.jsonl"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield path, json.loads(line)
            except json.JSONDecodeError:
                continue


def _record_ended_dt(record: dict) -> datetime | None:
    """Best-effort parse of `ended_iso` (preferred) or `started_iso`."""
    for key in ("ended_iso", "started_iso"):
        raw = record.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            continue
    return None


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


def daily_total_usd(day: datetime | None = None) -> float:
    """Sum estimated_cost_usd for sessions that ended on `day` (default today UTC)."""
    if day is None:
        day = datetime.now(timezone.utc)
    target_date = day.date()
    total = 0.0
    for _path, record in _iter_session_records():
        ended = _record_ended_dt(record)
        if ended is None:
            continue
        if ended.date() == target_date:
            total += float(record.get("estimated_cost_usd", 0.0))
    return total


def weekly_total_usd(days: int = 7, now: datetime | None = None) -> float:
    """Sum estimated_cost_usd for sessions ended in the trailing `days` window.

    `days=7` = trailing 7 days, NOT the ISO calendar week — matches what the
    Stéphane usually wants ("how much did I spend in the last week").
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - days * 86400
    total = 0.0
    for _path, record in _iter_session_records():
        ended = _record_ended_dt(record)
        if ended is None:
            continue
        if ended.timestamp() >= cutoff:
            total += float(record.get("estimated_cost_usd", 0.0))
    return total


def historical_series(days: int = 30, now: datetime | None = None) -> list[tuple[str, float]]:
    """Return `[(YYYY-MM-DD, total_usd)]` for each of the trailing `days` days,
    oldest first. Days with no sessions are present with total=0.0 so the UI
    can draw a continuous sparkline.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    from datetime import timedelta
    buckets: dict[str, float] = {}
    # Seed bucket for every day in window so empty days show as 0.0
    for offset in range(days):
        d = (now - timedelta(days=offset)).date().isoformat()
        buckets[d] = 0.0
    # Aggregate matching records
    cutoff = now.timestamp() - days * 86400
    for _path, record in _iter_session_records():
        ended = _record_ended_dt(record)
        if ended is None:
            continue
        if ended.timestamp() < cutoff:
            continue
        key = ended.date().isoformat()
        if key in buckets:
            buckets[key] += float(record.get("estimated_cost_usd", 0.0))
    return sorted(buckets.items())
