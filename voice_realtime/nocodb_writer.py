"""NocoDB writer for voice-realtime session records.

Posts each session to `ctt_voice_realtime_sessions` so the dashboard-perso
voice tab can read live cost + minutes. Failures never crash the parent
process — voice-realtime treats NocoDB as an opt-in side-channel.

Env vars required (read from ~/.nocodb.env if not set in env):
    NOCODB_URL, NOCODB_API_TOKEN, NOCODB_VOICE_REALTIME_TABLE_ID

Memory feedback_nocodb_mcp_update_broken says MCP UPDATE is broken; we only
INSERT here, which works fine through both the MCP wrapper and curl/urllib.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("voice_realtime.nocodb")

NOCODB_ENV_PATH = Path.home() / ".nocodb.env"


def _load_env() -> dict[str, str]:
    """Read ~/.nocodb.env into a dict (skips comments + blanks)."""
    if not NOCODB_ENV_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for line in NOCODB_ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _config() -> tuple[str, str, str] | None:
    """Return (url, token, table_id) or None if any piece is missing."""
    env = {**_load_env(), **os.environ}  # process env wins
    url = env.get("NOCODB_URL")
    token = env.get("NOCODB_API_TOKEN")
    table = env.get("NOCODB_VOICE_REALTIME_TABLE_ID")
    if not (url and token and table):
        return None
    return url, token, table


def insert_session(record: dict[str, Any]) -> bool:
    """POST one row to ctt_voice_realtime_sessions.

    Caller passes a dict matching the table schema:
        Title, started_iso, ended_iso, elapsed_seconds, provider, model,
        hourly_rate_usd, estimated_cost_usd, end_reason, transcript_chars,
        vault_note_path, project_hint.

    Returns True on success, False on any error (never raises).
    """
    cfg = _config()
    if cfg is None:
        logger.debug("nocodb_writer: config missing, skipping insert")
        return False
    url, token, table_id = cfg
    endpoint = f"{url.rstrip('/')}/api/v2/tables/{table_id}/records"
    body = json.dumps(record).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "xc-token": token,
            "Content-Type": "application/json",
            "User-Agent": "voice-realtime/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if 200 <= resp.status < 300:
                return True
            logger.warning("nocodb_writer: unexpected status %d", resp.status)
            return False
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode("utf-8", errors="ignore")[:200]
        except Exception:
            pass
        logger.warning("nocodb_writer: HTTPError %d %s — %s", exc.code, exc.reason, body_text)
        return False
    except urllib.error.URLError as exc:
        logger.warning("nocodb_writer: URLError %r", exc)
        return False
    except Exception as exc:
        logger.warning("nocodb_writer: unexpected error %r", exc)
        return False


def session_record_from_tracker(
    tracker_payload: dict[str, Any],
    *,
    project_hint: str | None = None,
    vault_note_path: str | None = None,
) -> dict[str, Any]:
    """Adapt the dict CostTracker.persist() builds into the NocoDB schema.

    Adds two operational fields not stored in the jsonl (project + vault path)
    so the dashboard can group sessions by project later.
    """
    started = tracker_payload.get("started_iso", "")
    provider = tracker_payload.get("provider", "?")
    title = f"{started[:16]} — {provider}"  # human-readable, ~"2026-05-24T01:23 — gemini"
    return {
        "Title": title,
        "started_iso": started,
        "ended_iso": tracker_payload.get("ended_iso", ""),
        "elapsed_seconds": tracker_payload.get("elapsed_seconds", 0),
        "provider": provider,
        "model": tracker_payload.get("model", ""),
        "hourly_rate_usd": tracker_payload.get("hourly_rate_usd", 0),
        "estimated_cost_usd": tracker_payload.get("estimated_cost_usd", 0),
        "end_reason": tracker_payload.get("end_reason", ""),
        "transcript_chars": tracker_payload.get("transcript_chars", 0),
        "vault_note_path": vault_note_path or "",
        "project_hint": project_hint or "",
    }
