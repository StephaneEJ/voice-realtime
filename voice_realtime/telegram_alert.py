"""Telegram notifier — best-effort budget alerts via the Jarvis bot.

Reads `~/.claude/jarvis.conf` for `JARVIS_TELEGRAM_TOKEN` + `JARVIS_TELEGRAM_CHAT_ID`.
Sends HTML messages (per memory feedback_telegram_parse_mode_html — Markdown V1
breaks on unescaped `_` in paths or model names).
"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("voice_realtime.telegram")

JARVIS_CONF = Path.home() / ".claude" / "jarvis.conf"
LAST_ALERT_PATH = Path.home() / ".voice-realtime" / "budget-alert-last.txt"


def _load_jarvis_conf() -> dict[str, str]:
    conf: dict[str, str] = {}
    if not JARVIS_CONF.exists():
        return conf
    try:
        for raw in JARVIS_CONF.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return conf


def send_telegram_html(text: str, timeout: float = 5.0) -> bool:
    """Send an HTML-formatted message to the Jarvis Telegram chat. True on success."""
    conf = _load_jarvis_conf()
    token = conf.get("JARVIS_TELEGRAM_TOKEN", "").strip()
    chat_id = conf.get("JARVIS_TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.debug("Telegram skipped — missing token or chat_id")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:
        logger.warning("Telegram send failed: %r", exc)
        return False


def maybe_alert_budget(monthly_used: float, monthly_cap: float, threshold_pct: float = 80.0) -> bool:
    """If usage crosses threshold and we haven't alerted this month, ping Telegram.

    Returns True if an alert was actually sent this call.
    """
    if monthly_cap <= 0 or monthly_used < monthly_cap * (threshold_pct / 100.0):
        return False

    current_month = datetime.now().strftime("%Y-%m")
    if LAST_ALERT_PATH.exists():
        try:
            last_month = LAST_ALERT_PATH.read_text(encoding="utf-8").strip()
            if last_month == current_month:
                return False  # already alerted this month
        except OSError:
            pass

    pct = 100.0 * monthly_used / monthly_cap
    msg = (
        f"⚠ <b>voice-realtime budget alert</b>\n"
        f"Consommé : <b>${monthly_used:.2f}</b> / ${monthly_cap:.2f} "
        f"(<b>{pct:.0f}%</b>)\n"
        f"Seuil : {threshold_pct:.0f}%  |  Mois : {current_month}"
    )
    if send_telegram_html(msg):
        LAST_ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_ALERT_PATH.write_text(current_month, encoding="utf-8")
        logger.info("Telegram budget alert sent at %.0f%%", pct)
        return True
    return False
