# voice-realtime

Skill `/voice-realtime` pour OpenCode / Claude Code — conversation vocale duplex temps réel (WebSocket) avec préservation de contexte LLM compactée et budgétée.

**Status :** Phase 2 finalisée à 95 % (2026-05-24). Reste : tests vocaux de validation (P1 retest, P6 matrice 9 dim).

## Pourquoi ce projet

Le mode TTS actuel (Edge TTS via Jarvis) est unidirectionnel : Claude écrit, l'utilisateur écoute. Realtime ouvre un mode duplex : parler et être interrompu, latence ~400-600 ms, conversation naturelle.

Cas d'usage en prod :
- Brainstorming projet actif (charger contexte projet, parler 15-30 min, sortir avec décisions + actions auto-extraites par `summarize-voice`)
- Reprendre une conversation Claude Code / OpenCode CLI en mode vocal sans changer de fenêtre (`--cli-context`)
- Coaching vocal (santé, alcool, journaling émotionnel)

## Quick start

```bash
# Vue d'ensemble des stats
voice-realtime stats --days 30

# Conversation Gemini (défaut) + contexte projet vault + contexte CLI actif
voice-realtime talk \
  --provider gemini \
  --project "Voice Realtime" \
  --cli-context \
  --max-minutes 15 \
  --clean-terminal

# Mot-clé "killchat" prononcé seul termine la session ;
# barge-in client (parler par-dessus) coupe l'audio du modèle.
```

## Architecture livrée

```
voice_realtime/
├── providers/           # base.py (Protocol) + openai_realtime.py + gemini.py
├── audio/               # microphone.py + playback.py (sounddevice PCM16)
├── cli.py               # status / hello / talk / preview-voices / summarize / stats
├── config.py            # ~/.voice-realtime/secrets.env loader + budget
├── context_loader.py    # phase active + daily + note projet (prioritized sections)
├── cli_context.py       # transcript Claude Code (.jsonl) OU OpenCode (SQLite) actif
├── rolling_recap.py     # compactage périodique via claude -p Sonnet → silent inject
├── cost_tracker.py      # estim cost + kill switch + jsonl + NocoDB mirror
├── session_saver.py     # markdown vault: _System/voice-sessions/YYYY-MM-DD ... .md
├── summarizer.py        # post-session JSON strict → append note projet
├── telegram_alert.py    # alerte mensuelle 80 % budget
├── system_audio.py      # SIGSTOP Deezer/Spotify/Music + lock anti-multi-instance
├── nocodb_writer.py     # mirror ctt_voice_realtime_sessions (best-effort)
└── latency_tracker.py   # TTFA / TTFI metrics
tests/                   # 48 unit tests, < 2s, no network
dashboard/               # drop-in FastAPI router + HTML fragment pour dashboard-perso
scripts/                 # backfill_nocodb_sessions.py (one-shot)
docs/DESIGN.md           # décisions architecturales
```

## Modèles supportés

| Provider | Modèle défaut | Pricing approx | Voix défaut |
|----------|---------------|----------------|-------------|
| Gemini   | `gemini-2.5-flash-native-audio-latest` | ~$1.40/h | Charon |
| OpenAI   | `gpt-realtime-2` (backup : `gpt-realtime-mini` 4× moins cher) | $5/h | (selon clé) |

## Flags `talk`

| Flag | Effet |
|------|-------|
| `--provider gemini\|openai` | Choix provider (défaut gemini) |
| `--project "Nom"` | Injecte contexte note projet vault |
| `--cli-context / -k` | Injecte conversation CLI active (Claude Code .jsonl OR OpenCode SQLite, auto-detect) |
| `--rolling-recap` / `--no-rolling-recap` | Compactage périodique pendant session (défaut on) |
| `--recap-interval 420` | Trigger recap min seconds (défaut 7 min) |
| `--recap-user-chars 2500` | Trigger recap char count (défaut ≈ 3-4 min de parole) |
| `--mic-rate 24000` | Override mic rate (A/B test STT FR sur Gemini) |
| `--max-minutes 15` | Kill switch durée (défaut 15) |
| `--cost-cap 3.00` | Kill switch cost USD (défaut $3) |
| `--summarize / --no-summarize` | Auto-summarize post-session (défaut on) |
| `--clean-terminal / -c` | Terminal affiche que les transcripts |
| `--voice <name>` | Override voix (Gemini : Aoede/Charon/Fenrir/Kore/Puck) |

## Vocabulaire vocal

- **« killchat »** (mot isolé) → termine la session + farewell vocal
- Parler par-dessus l'IA → barge-in client (flush audio modèle en local, < 100 ms)

## Phases — état au 2026-05-24

- **Phase 0** ✅ Design doc figé
- **Phase 1** ✅ MVP exécutable Python + 2 providers + audio duplex + context + cost + vault save (16 commits, 21-22/05)
- **Phase 2** ✅ 95 % : --cli-context multi-source, rolling context window, summarize-voice, Telegram budget, NocoDB integration, barge-in hysteresis. Reste : tests vocaux user (matrice 9 dim 3+ modèles, retest live).
- **Phase 3+** ⏳ Local model fallback (whisper.cpp + Ollama + Piper), Telegram/Discord, multimodal (caméra/écran), tool calling background.

## Liens

- Note projet vault : `2ND_CERVEAU/1 PROJETS/Voice Realtime Skill/Voice Realtime Skill.md`
- Skill stub : `2ND_CERVEAU/.claude/commands/voice-realtime.md`
- Spec source : fournie par Stéphane 2026-05-21 (16 chapitres)

## Licence

Privé. Usage perso.
