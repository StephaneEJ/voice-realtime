# DESIGN — voice-realtime

**Status :** V0.1 — décisions tranchées 2026-05-21. Phase 1 prête à coder dès création compte OpenAI API.
**Auteurs :** Stéphane + Claude (Opus 4.7)

Liens cliquables vers Obsidian (clic ouvre la note dans Obsidian) :
- Note projet vault : [Voice Realtime Skill](obsidian://open?vault=2ND_CERVEAU&file=1%20PROJETS%2FVoice%20Realtime%20Skill%2FVoice%20Realtime%20Skill)
- Intention phase active : [1 Saut vers la Liberté — Intention](obsidian://open?vault=2ND_CERVEAU&file=2%20CASQUETTES%2FLife%20Phases%2F1%20Saut%20vers%20la%20Libert%C3%A9%2F1%20Intention)
- Infrastructure : [Infrastructure](obsidian://open?vault=2ND_CERVEAU&file=_System%2FInfrastructure)

---

## 1. Goal (rappel)

Skill `/voice-realtime` qui ouvre depuis OpenCode/Claude Code une session de conversation vocale duplex temps réel (WebSocket), avec contexte LLM actif compacté + budgétisé. Multi-provider — frontier reasoning models uniquement.

## 2. Non-goals

- **NE remplace PAS** Jarvis voice (Edge TTS unidirectionnel, gratuit). Coexistence.
- **NE remplace PAS** Superwhisper (STT one-shot post-enregistrement). Coexistence — cf. [Superwhisper Pipeline v3-lite](obsidian://open?vault=2ND_CERVEAU&file=1%20PROJETS%2FSuperwhisper%20Pipeline%20v3-lite%2FSuperwhisper%20Pipeline%20v3-lite).
- Pas de GUI obligatoire. Terminal first.
- Pas de mobile app V1.
- Pas d'orchestration managed (ElevenLabs/Vapi/Retell) — frontier reasoning seulement.

## 3. État du marché (mai 2026) — frontier reasoning realtime voice

| Provider | Modèle | Sorti | Reasoning | Pricing | Statut |
|----------|--------|-------|-----------|---------|--------|
| OpenAI | gpt-realtime-2 | 2026-05-07 | GPT-5-class, niveaux minimal→very high | $32/$64 par 1M tokens audio in/out (~$5/h, ~$0.40 / 5 min) | **GA** |
| Google | gemini-3.1-flash-live | 2026-03-26 | `thinkingLevel` minimal/low/medium/high, audio-natif (pas de pipeline STT/LLM/TTS) | $3/$12 par 1M tokens audio in/out (~$1.40/h, $0.023/min) | **GA** (Vertex + AI Studio) |
| Anthropic | — | — | Claude Opus 4.7 = parité reasoning text mais **pas** de modalité voix realtime API | — | indispo |

**Conclusion :** 2 frontier candidats actifs (OpenAI + Gemini). Anthropic indispo côté voix. ElevenLabs/Vapi = orchestrateurs sans modèle reasoning natif → exclus du périmètre frontier.

## 4. Décisions tranchées 2026-05-21

| # | Décision | Choix | Notes |
|---|----------|-------|-------|
| Langage | Python | SDK officiel `openai-agents` (PyPI) + `openai-node` côté Node aussi mature. Python = cohérence stack vault ([Superwhisper](obsidian://open?vault=2ND_CERVEAU&file=1%20PROJETS%2FSuperwhisper%20Pipeline%20v3-lite%2FSuperwhisper%20Pipeline%20v3-lite), Jarvis, scripts `_System/`). |
| Cas d'usage pilote V1 | **Brainstorming projet actif** | Charger contexte projet, parler 15-30 min, sortir avec décisions + actions, save Obsidian. |
| Auth OpenAI | Créer compte + $10 crédit | ChatGPT Plus = consumer, **pas** d'API access. Compte API séparé sur `platform.openai.com`. |
| Provider V1 | **OpenAI + Gemini live, les deux** | Pas de stub. Comparaison qualité voix réelle sur usage Stéphane. Abstraction provider justifiée. |

## 5. Tensions résiduelles

### 5.1 Scope vs budget (mitigée mais pas éliminée)

Budget $50/mois :
- 100 % OpenAI → 10h/mois
- 100 % Gemini → 35h/mois
- Mix 50/50 → ~16h/mois

Avec 2 providers live + cas d'usage généraliste brainstorming, abstraction provider justifiée par comparaison qualité réelle. **Mais** si après 2 semaines d'usage Stéphane n'utilise qu'un seul provider, on coupe l'autre.

### 5.2 Risque d'abandon 3 mois

Documenté dans [1 Intention](obsidian://open?vault=2ND_CERVEAU&file=2%20CASQUETTES%2FLife%20Phases%2F1%20Saut%20vers%20la%20Libert%C3%A9%2F1%20Intention). Mitigation : gate Phase 2 = 10 sessions réelles + 3 summary lues + budget respecté.

## 6. Architecture

### 6.1 Interface provider

```python
# providers/base.py
from typing import Protocol, AsyncIterator, Literal
from dataclasses import dataclass

@dataclass
class ProviderConfig:
    model: str
    api_key: str
    voice: str | None = None
    thinking_level: Literal["minimal", "low", "medium", "high", "very_high"] | None = None
    context_tokens: int = 3000  # CompactedContext budget

@dataclass
class RealtimeEvent:
    kind: Literal[
        "partial_transcript_user",
        "final_transcript_user",
        "partial_transcript_model",
        "final_transcript_model",
        "audio_chunk_out",
        "tool_call",
        "error",
        "cost_update",
        "session_closed",
    ]
    data: dict
    timestamp_ms: int

class RealtimeVoiceProvider(Protocol):
    async def connect(self, config: ProviderConfig, context: str) -> None: ...
    async def send_audio_chunk(self, pcm16: bytes) -> None: ...
    async def receive_events(self) -> AsyncIterator[RealtimeEvent]: ...
    async def close(self) -> None: ...
```

### 6.2 Pipeline session

```
1. /voice-realtime [--provider openai|gemini] [--project <name>] [--budget medium]
2. context.detect_active()           → ContextPackage (projet, objectif, tâches)
3. summarization.compact(pkg, budget) → CompactedContext (≤3000 tokens V1)
4. provider.connect(model, ctx)
5. audio.start_microphone_stream()
6. while session_active:
     event = await provider.receive_events()
     transcript.render(event)
     cost_tracker.update(event)
     if cost_tracker.over_limit(): provider.close(); break
7. summarization.generate_summary(transcript) via claude -p Sonnet
8. obsidian.save_session_note(summary)
9. memory.reinject(summary)  # MEMORY.md auto Claude Code
```

### 6.3 Modules

| Module | Responsabilité | Notes |
|--------|----------------|-------|
| `providers/openai.py` | OpenAI Realtime client | SDK `openai` `OpenAIRealtimeWebSocket` |
| `providers/gemini.py` | Gemini Live client | SDK `google-genai` Live API |
| `providers/base.py` | Protocol + ProviderConfig + RealtimeEvent | Abstraction commune |
| `context/detector.py` | Détection projet actif | Lit daily note phase active + weekly + env `VR_PROJECT` |
| `summarization/compacter.py` | Builder CompactedContext | Budget low|medium|high |
| `summarization/summary.py` | Summary post-session | Via `claude -p` Sonnet — cf. [feedback_always_claude_cli_not_sdk](obsidian://open?vault=2ND_CERVEAU&file=_System%2FInfrastructure) |
| `websocket/session.py` | Boucle async audio in/out | `sounddevice` pour mic capture |
| `cost-tracking/tracker.py` | Estimation live + kill switch | jsonl local V1 |
| `transcript/renderer.py` | Live terminal + save markdown | `rich` pour TUI |
| `obsidian/save.py` | Save note `1 PROJETS/<X>/Voice Sessions/YYYY-MM-DD HH-MM.md` | Avec backlinks vers projet + tags |
| `commands/voice_realtime.py` | Entry point CLI | `typer` argparse |
| `config/providers.yaml` | Pricing, max_context, voice profile | Cf. `config/providers.example.yaml` |

### 6.4 Config providers (V1)

```yaml
providers:
  openai:
    enabled: true
    model: gpt-realtime-2          # GA 2026-05-07
    api_key: ${OPENAI_API_KEY}
    voice: alloy                    # à arbitrer après test
    thinking_level: low             # défaut OpenAI, équilibre latence/raisonnement
    max_context_tokens: 128000
    pricing:
      mode: token
      input_audio_per_1m_usd: 32.00
      output_audio_per_1m_usd: 64.00
      input_audio_cached_per_1m_usd: 0.40

  gemini:
    enabled: true
    model: gemini-3.1-flash-live    # GA 2026-03-26 Vertex/AI Studio
    api_key: ${GEMINI_API_KEY}
    voice: Aoede                    # à arbitrer après test
    thinking_level: low
    max_context_tokens: 128000
    audio_session_cap_minutes: 15   # limite native Gemini
    pricing:
      mode: token
      input_audio_per_1m_usd: 3.00
      output_audio_per_1m_usd: 12.00

context_budgets:
  low: 3000
  medium: 8000
  high: 20000

limits:
  default_max_duration_minutes: 15
  warning_cost_usd: 1.00
  hard_stop_cost_usd: 3.00
  monthly_budget_usd: 50.00
  monthly_warning_threshold_pct: 80
```

### 6.5 Context detection (V1)

Sources prioritaires :
1. Flag CLI `--project <nom>` → projet explicite
2. Env var `VR_PROJECT` → projet exporté shell
3. **Daily note du jour** (phase active) → intention + 3 priorités + reste à faire
4. **Weekly note active** → priorités + tâches Deep Focus
5. Mémoire auto Claude Code : `~/.claude/projects/.../memory/MEMORY.md` (index)

Hors scope V1 : graphe Obsidian, recherche sémantique vault, conversations Claude Code passées.

### 6.6 Cost tracking V1

- Pre-session : estimation `durée prévue × tarif/min provider` → warn si > $1
- Live : update toutes les 30 s, affichage TUI
- Kill switch hard à $3/session ou 15 min (configurable)
- Persistance : `~/.voice-realtime/sessions.jsonl` (1 ligne par session)
- Compteur mensuel : sum jsonl du mois courant, alerte 80 % budget
- V2 : migration NocoDB `ctt_voice_realtime_sessions` (cohérence infra cf. [Infrastructure](obsidian://open?vault=2ND_CERVEAU&file=_System%2FInfrastructure))

## 7. Phases

### Phase 0 — Design doc (terminée)

- [x] Repo bootstrap [`~/OBSIDIAN/PROJETS DEV/voice-realtime/`](file:///Users/stephanedufresne/OBSIDIAN/PROJETS%20DEV/voice-realtime/)
- [x] README + DESIGN.md V0
- [x] Stub skill `.claude/commands/voice-realtime.md`
- [x] Décisions tranchées : langage, cas d'usage, auth, provider V1
- [x] Modèles frontier vérifiés : OpenAI gpt-realtime-2 + Gemini 3.1 Flash Live
- [x] Mémoire auto Claude Code indexée

### Phase 1 — MVP exécutable (~2-3 semaines effort)

**Pré-requis :** Stéphane crée compte sur `platform.openai.com` + alimente $10 + génère API key. Idem Gemini AI Studio (probablement gratuit pour démarrer).

- [ ] `pyproject.toml` Python 3.12 + uv + ruff + mypy
- [ ] `providers/base.py` Protocol + dataclasses
- [ ] `providers/openai.py` client `OpenAIRealtimeWebSocket` minimal
- [ ] `providers/gemini.py` client Gemini Live minimal
- [ ] `audio/microphone.py` capture PCM16 24kHz mono via sounddevice
- [ ] `audio/playback.py` lecture stream audio out
- [ ] `context/detector.py` lecture daily/weekly + flag projet
- [ ] `summarization/compacter.py` budget low (3000 tokens)
- [ ] `websocket/session.py` boucle async event loop
- [ ] `transcript/renderer.py` TUI live (rich)
- [ ] `cost_tracking/tracker.py` live + kill switch
- [ ] `obsidian/save.py` save markdown summary
- [ ] `summarization/summary.py` via `claude -p` Sonnet
- [ ] `commands/voice_realtime.py` entry point CLI
- [ ] Tests usage réel 2 semaines, 10 sessions minimum

**Gate de fin Phase 1 :** 10 sessions réellement utilisées + budget respecté + 3 notes summary lues post-session + Stéphane confirme valeur ressentie.

### Phase 2 — Si Phase 1 validée

- Provider comparaison auto (run la même question sur les 2, log différence)
- Rolling context window pour sessions > 15 min
- Configurable budget mensuel + Telegram alert via [bot Jarvis](obsidian://open?vault=2ND_CERVEAU&file=_System%2FInfrastructure)
- Latency metrics
- Migration NocoDB sessions table

### Phase 3+ — Reportée

- Multimodal (caméra / screen) via Gemini multimodal Live
- Local model fallback (Whisper local + LLM local)
- Multi-agent concurrent voice
- Telegram / Discord / mobile

## 8. Open questions résiduelles

1. **Compte OpenAI API** — Stéphane crée + alimente $10 cette semaine.
2. **Gemini auth** — réutiliser OAuth `gws` (déjà en place cf. [reference_gws_cli](obsidian://open?vault=2ND_CERVEAU&file=_System%2FInfrastructure)) ou nouvelle API key AI Studio ? AI Studio = simple, gws = nécessite scope Vertex AI ajouté.
3. **Voice profile** — laquelle par provider ? À arbitrer après 1ère session test.
4. **Concurrence Superwhisper** — un `/voice-realtime` actif kill-il Superwhisper ? Probablement oui pour éviter conflits mic.
5. **Build in Public** — repo public GitHub ou privé ?
6. **Skill multi-turn** — voice-realtime invoque-t-elle d'autres skills (`/inversion-check`, `/coach` après détection mot-clé) ? Hors scope V1.

## 9. Risques actualisés

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Abandon 3 mois | Élevée | Élevé | Gate Phase 2 = usage réel mesuré |
| Coût explose | Faible (kill switch hard) | Moyen | Kill switch $3/session + budget mensuel $50 + alerte 80 % |
| Latence audio remote SSH | Faible | Moyen | V1 = Mac local only |
| Qualité voix décevante | Moyenne | Moyen | 2 providers V1 = comparaison réelle |
| Gemini breaking change | Faible (GA depuis 26 mars) | Faible | Provider abstraction = swap rapide |
| OpenAI quota / rate limit | Faible si $10 crédit | Moyen | Surveiller `429` + back-off |

## 10. Actions Stéphane (cette semaine)

1. Aller sur `platform.openai.com`, créer compte (peut partager email avec ChatGPT Plus, billing séparé).
2. Add payment method → top up $10 crédit pay-as-you-go.
3. Settings → API Keys → générer `sk-...`, copier dans `~/.claude/voice-realtime.env` (chmod 600).
4. Gemini : `aistudio.google.com` → générer API key gratuit ou via `gws` OAuth scope Vertex AI.
5. Confirmer langage Python validé, Phase 1 démarre.

## Sources frontier voice (vérif mai 2026)

- OpenAI gpt-realtime-2 release 2026-05-07
- Gemini 3.1 Flash Live release 2026-03-26 (GA Vertex + AI Studio)
- Realtime API guide + SDK officiel `openai-agents` Python + `openai-node` TS
- Gemini Live API Vertex AI

Liens recherche stockés dans `docs/sources-2026-05-21.md` (à créer si besoin de re-vérifier ultérieurement).
