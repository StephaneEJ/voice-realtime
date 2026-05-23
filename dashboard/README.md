# Dashboard integration

Plug-and-play module for `/home/steph/dashboard-perso/api/` (VPS).

## Files

- `voice_endpoint.py` — FastAPI router exposing two endpoints:
  - `GET /api/voice/summary?days=30` — cost, minutes, per-provider, current-month budget %
  - `GET /api/voice/sessions?days=7&limit=50` — recent session rows
- `voice_fragment.html` — drop-in tab markup with KPI tiles, provider breakdown, recent sessions table

## Deploy steps (on VPS)

```bash
scp dashboard/voice_endpoint.py mon-serveur:/home/steph/dashboard-perso/api/
scp dashboard/voice_fragment.html mon-serveur:/home/steph/dashboard-perso/src/frontend/voice.html
# Then on VPS, edit main.py:
#   from .voice_endpoint import router as voice_router
#   app.include_router(voice_router)
# And register the tab in the nav (see /weight, /food for the pattern).
# Restart per memory feedback_dashboard_perso_restart:
#   setsid bash start.sh
```

## Env vars expected

Already present in `/home/steph/dashboard-perso/.env` (need to add the new ID):

```
NOCODB_URL=...
NOCODB_API_TOKEN=...
NOCODB_VOICE_REALTIME_TABLE_ID=m0zk60kh2eakrjc
```

## Read-only

The endpoints only `SELECT` from `ctt_voice_realtime_sessions`. No write
path runs from the dashboard — writes happen exclusively in
`voice_realtime.cost_tracker.persist()` on the user's Mac.
