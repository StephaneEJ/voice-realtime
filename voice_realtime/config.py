"""Configuration loader — reads ~/.claude/voice-realtime.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SECRETS_PATH = Path.home() / ".claude" / "voice-realtime.env"


@dataclass(frozen=True)
class Config:
    openai_api_key: str | None
    gemini_api_key: str | None
    monthly_budget_usd: float

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key)


def load_config(secrets_path: Path = SECRETS_PATH) -> Config:
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"Secrets file not found: {secrets_path}\n"
            f"Create it with:\n"
            f"  OPENAI_API_KEY=sk-...\n"
            f"  GEMINI_API_KEY=AI...\n"
            f"  VOICE_REALTIME_MONTHLY_BUDGET_USD=22"
        )

    load_dotenv(secrets_path, override=False)
    return Config(
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        monthly_budget_usd=float(os.environ.get("VOICE_REALTIME_MONTHLY_BUDGET_USD", "22")),
    )
