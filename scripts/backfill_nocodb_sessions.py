"""One-shot: backfill historical jsonl session records into NocoDB.

Walks ~/.voice-realtime/sessions/*.jsonl, parses each record, and POSTs to
ctt_voice_realtime_sessions. Idempotency: NocoDB has no natural unique key
in our schema, so re-running this WILL create duplicates. Run once after
the table is created, then trust the live writer in CostTracker.persist().

Usage:
    cd ~/OBSIDIAN/PROJETS\\ DEV/voice-realtime
    uv run python scripts/backfill_nocodb_sessions.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make voice_realtime importable when this script is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_realtime.nocodb_writer import insert_session, session_record_from_tracker  # noqa: E402

SESSIONS_DIR = Path.home() / ".voice-realtime" / "sessions"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print records without inserting.")
    args = parser.parse_args()

    if not SESSIONS_DIR.exists():
        print(f"No sessions dir: {SESSIONS_DIR}")
        return 0

    jsonls = sorted(SESSIONS_DIR.glob("*.jsonl"))
    print(f"Found {len(jsonls)} jsonl files")

    ok = fail = empty = 0
    for path in jsonls:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as exc:
            print(f"  SKIP {path.name}: {exc}")
            fail += 1
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"  SKIP malformed line in {path.name}")
                fail += 1
                continue
            nc_record = session_record_from_tracker(
                record,
                project_hint=None,  # historical sessions don't carry this
                vault_note_path=None,
            )
            if args.dry_run:
                print(f"  DRY  {nc_record['Title']} cost=${nc_record['estimated_cost_usd']:.4f}")
                ok += 1
                continue
            if insert_session(nc_record):
                print(f"  OK   {nc_record['Title']}")
                ok += 1
            else:
                print(f"  FAIL {nc_record['Title']}")
                fail += 1
        if not lines:
            empty += 1

    print(f"\nDone: {ok} ok, {fail} failed, {empty} empty files")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
