"""External media pause/resume + Jarvis TTS guard during voice-realtime sessions.

When a `voice-realtime talk` session starts :
- Deezer (Electron, no AppleScript API) is paused by sending SIGSTOP to its
  processes — hard freeze, audio stops within milliseconds. SIGCONT on exit.
- Spotify and Music (native AppleScript support) are paused via osascript,
  resumed at the end IF they were playing when we started.
- A lock file `~/.voice-realtime/active.lock` is created. Any TTS script that
  honors this lock (e.g. `speak-selection.sh`) will queue its message in
  `~/.voice-realtime/jarvis-queue.txt` instead of speaking. We drain that
  queue at session end.
"""

from __future__ import annotations

import os
import signal as signal_module
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

VR_DIR = Path.home() / ".voice-realtime"
LOCK_PATH = VR_DIR / "active.lock"
QUEUE_PATH = VR_DIR / "jarvis-queue.txt"
SPEAK_SELECTION = Path.home() / ".local" / "bin" / "speak-selection.sh"


@dataclass
class MediaState:
    deezer_pids: list[int] = field(default_factory=list)
    spotify_was_playing: bool = False
    music_was_playing: bool = False


def _pgrep(name: str, exact: bool = True) -> list[int]:
    try:
        flag = "-x" if exact else "-f"
        result = subprocess.run(["pgrep", flag, name], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return [int(p) for p in result.stdout.split() if p]
    except (OSError, subprocess.SubprocessError):
        pass
    return []


def _applescript(script: str, timeout: float = 2.0) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def pause_external_media() -> MediaState:
    state = MediaState()
    # Match all Deezer-related processes (main + 5 helpers: GPU, Network,
    # Renderer, AudioService, crashpad). The AudioService child runs the
    # actual audio rendering — freezing only the main PID lets sound continue
    # until the OS audio buffer drains.
    state.deezer_pids = _pgrep("Deezer", exact=False)
    for pid in state.deezer_pids:
        try:
            os.kill(pid, signal_module.SIGSTOP)
        except (ProcessLookupError, PermissionError):
            pass
    s = _applescript('tell application "Spotify" to if it is running then return (player state as string)')
    if s == "playing":
        state.spotify_was_playing = True
        _applescript('tell application "Spotify" to pause')
    m = _applescript('tell application "Music" to if it is running then return (player state as string)')
    if m == "playing":
        state.music_was_playing = True
        _applescript('tell application "Music" to pause')
    return state


def resume_external_media(state: MediaState) -> None:
    for pid in state.deezer_pids:
        try:
            os.kill(pid, signal_module.SIGCONT)
        except (ProcessLookupError, PermissionError):
            pass
    if state.spotify_was_playing:
        _applescript('tell application "Spotify" to play')
    if state.music_was_playing:
        _applescript('tell application "Music" to play')


def acquire_lock() -> None:
    VR_DIR.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(f"{os.getpid()} {time.time():.0f}\n", encoding="utf-8")
    # Stop any currently-speaking Jarvis TTS so it doesn't clash with the session.
    for pattern in ("edge-tts.*jarvis", "afplay.*jarvis_", "afplay.*speak-selection", "mpv.*speak-selection"):
        try:
            subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=2)
        except (OSError, subprocess.SubprocessError):
            pass


def release_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def drain_jarvis_queue() -> int:
    """Speak any messages queued during the session via speak-selection.sh.

    Returns the count of queued messages drained.
    """
    if not QUEUE_PATH.exists():
        return 0
    try:
        raw = QUEUE_PATH.read_text(encoding="utf-8")
    except OSError:
        return 0
    QUEUE_PATH.unlink(missing_ok=True)
    # Each line in the queue file is one queued message.
    messages = [ln for ln in raw.splitlines() if ln.strip()]
    if not messages or not SPEAK_SELECTION.exists():
        return 0
    for text in messages:
        try:
            subprocess.Popen(
                [str(SPEAK_SELECTION)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).communicate(input=text.encode("utf-8"), timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
    return len(messages)
