"""FastAPI endpoint module ready to drop into /home/steph/dashboard-perso/api/.

Reads from NocoDB `ctt_voice_realtime_sessions` and returns aggregates the
voice tab can render. Designed to be additive — doesn't touch any existing
dashboard module. To integrate:

    # In main.py:
    from .voice_endpoint import router as voice_router
    app.include_router(voice_router)

Env vars expected (already present on VPS dashboard config):
    NOCODB_URL, NOCODB_API_TOKEN, NOCODB_VOICE_REALTIME_TABLE_ID

Endpoints:
    GET /api/voice/summary?days=30      → {total_cost, total_minutes, by_provider, monthly_budget_pct}
    GET /api/voice/sessions?days=7&limit=50 → list of recent sessions
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
import json
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from fastapi import APIRouter, HTTPException, Query  # type: ignore
except ImportError:  # pragma: no cover — only loaded inside the dashboard env
    APIRouter = None  # type: ignore

MONTHLY_BUDGET_USD = 22.0  # mirrors voice_realtime.config default


def _nocodb_config() -> tuple[str, str, str]:
    url = os.environ.get("NOCODB_URL")
    token = os.environ.get("NOCODB_API_TOKEN")
    table = os.environ.get("NOCODB_VOICE_REALTIME_TABLE_ID")
    if not (url and token and table):
        raise RuntimeError("NocoDB env vars missing")
    return url.rstrip("/"), token, table


def _fetch_records(days: int, limit: int = 500) -> list[dict[str, Any]]:
    """Pull session records from NocoDB then filter client-side.

    NocoDB v2 DateTime range filters are unreliable (memory reference
    `feedback_alcohol_logging`: filter DateTime range cassé → fetch all +
    filter Python). We sort server-side by -started_iso and grab `limit`
    rows, then drop anything older than the cutoff.
    """
    url, token, table = _nocodb_config()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    params = {
        "limit": str(limit),
        "sort": "-started_iso",
    }
    endpoint = f"{url}/api/v2/tables/{table}/records?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        endpoint,
        headers={
            "xc-token": token,
            "User-Agent": "dashboard-voice/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=5.0) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    raw_rows = payload.get("list", []) if isinstance(payload, dict) else []
    return [r for r in raw_rows if (r.get("started_iso") or "") >= cutoff]


def summary(days: int = 30) -> dict[str, Any]:
    """Aggregate cost + minutes + provider breakdown over the window."""
    rows = _fetch_records(days=days)
    total_cost = sum(float(r.get("estimated_cost_usd", 0) or 0) for r in rows)
    total_seconds = sum(float(r.get("elapsed_seconds", 0) or 0) for r in rows)

    by_provider: dict[str, dict[str, float]] = {}
    for r in rows:
        prov = r.get("provider") or "?"
        b = by_provider.setdefault(prov, {"sessions": 0, "cost": 0.0, "minutes": 0.0})
        b["sessions"] += 1
        b["cost"] += float(r.get("estimated_cost_usd", 0) or 0)
        b["minutes"] += float(r.get("elapsed_seconds", 0) or 0) / 60.0

    # Current calendar month spend (separately from the rolling window)
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    monthly_rows = [
        r for r in rows
        if r.get("started_iso", "") >= month_start.isoformat()
    ]
    monthly_cost = sum(float(r.get("estimated_cost_usd", 0) or 0) for r in monthly_rows)

    return {
        "window_days": days,
        "total_sessions": len(rows),
        "total_cost_usd": round(total_cost, 4),
        "total_minutes": round(total_seconds / 60.0, 1),
        "by_provider": {
            p: {
                "sessions": int(d["sessions"]),
                "cost_usd": round(d["cost"], 4),
                "minutes": round(d["minutes"], 1),
            }
            for p, d in by_provider.items()
        },
        "current_month_cost_usd": round(monthly_cost, 4),
        "current_month_budget_usd": MONTHLY_BUDGET_USD,
        "current_month_pct": round(100.0 * monthly_cost / MONTHLY_BUDGET_USD, 1)
        if MONTHLY_BUDGET_USD > 0 else 0.0,
    }


def sessions_list(days: int = 7, limit: int = 50) -> list[dict[str, Any]]:
    """Return raw sessions for table display in the dashboard."""
    rows = _fetch_records(days=days, limit=limit)
    return [
        {
            "started_iso": r.get("started_iso"),
            "ended_iso": r.get("ended_iso"),
            "provider": r.get("provider"),
            "model": r.get("model"),
            "elapsed_seconds": r.get("elapsed_seconds"),
            "estimated_cost_usd": r.get("estimated_cost_usd"),
            "end_reason": r.get("end_reason"),
            "project_hint": r.get("project_hint"),
            "vault_note_path": r.get("vault_note_path"),
        }
        for r in rows
    ]


# ─── FastAPI router (only imported inside the dashboard env) ──────────


if APIRouter is not None:
    router = APIRouter(prefix="/api/voice", tags=["voice-realtime"])

    @router.get("/summary")  # type: ignore[misc]
    def get_summary(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
        try:
            return summary(days=days)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    @router.get("/sessions")  # type: ignore[misc]
    def get_sessions(
        days: int = Query(7, ge=1, le=365),
        limit: int = Query(50, ge=1, le=500),
    ) -> list[dict[str, Any]]:
        try:
            return sessions_list(days=days, limit=limit)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))


__all__ = ["summary", "sessions_list"]
if APIRouter is not None:
    __all__.append("router")
