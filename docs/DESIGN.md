# DESIGN — voice-realtime

**Status :** V0 — draft. À challenger.
**Date :** 2026-05-21
**Auteur :** Stéphane + Claude (Opus 4.7)

---

## 1. Goal (rappel)

Permettre depuis une session OpenCode/Claude Code de basculer vers une conversation vocale duplex temps réel (WebSocket), tout en préservant et compactant intelligemment le contexte LLM actif. Multi-provider (OpenAI Realtime, Gemini Live, futur local).

## 2. Non-goals

- **NE remplace PAS** Jarvis voice (Edge TTS unidirectionnel). Coexistence.
- **NE remplace PAS** Superwhisper (STT one-shot post-enregistrement). Coexistence.
- Pas de GUI obligatoire. Terminal first.
- Pas de mobile app V1.

## 3. Tensions identifiées

### 3.1 Scope vs budget

Choix utilisateur : multi-usage généraliste + budget <$50/mois + 2 providers V1.

Conflit : multi-usage exige abstraction propre. $50/mois = ~4h/mois = ~8 min/jour. À ce volume, l'abstraction multi-provider ne s'amortit jamais (utilisation < courbe d'apprentissage).

**Résolution proposée :**

- Abstraction provider présente dès l'architecture (interface, pas magie).
- V1 ne wire qu'**OpenAI Realtime** (plus mature, doc solide).
- Gemini = **stub d'interface** vérifiant que l'abstraction tient. Wire live en V1.1 seulement si usage réel justifie.
- Si après 2 semaines d'usage Phase 1 le compteur dit "1h/mois", on coupe Gemini définitivement et on simplifie.

**À challenger :** est-ce que Stéphane veut payer la "taxe abstraction" maintenant pour bénéfice peut-être jamais atteint ?

### 3.2 Cas d'usage généraliste = piège

Multi-usage en pratique = code qui ne sert spécifiquement à rien. Le MVP doit avoir **un** cas d'usage pilote testable, sinon on construit pour rien.

**Résolution proposée :** Phase 1 trancher 1 cas d'usage pilote parmi :
- Brainstorming projet actif (charger contexte projet, sortir décisions/actions)
- Mom Test debrief vocal (parler post-interview, extraire insights)
- Coach addicto HALT (4 questions + plan physio avant cognitif)

**À challenger :** lequel ?

### 3.3 Langage

Python (cohérent avec Jarvis voice actuel, edge-tts, Superwhisper, scripts vault) vs TypeScript/Node (audio realtime côté Node SDK OpenAI plus mature, exemples officiels TS).

**Résolution proposée :** **Python** par défaut (cohérence stack), avec validation que le SDK OpenAI Python supporte bien le streaming audio realtime (à vérifier).

**À challenger :** vérification SDK Python audio streaming = blocker potentiel. Si galère, fallback Node.

## 4. Architecture

### 4.1 Interface provider

```python
# providers/base.py
class RealtimeVoiceProvider(Protocol):
    async def connect(self, config: ProviderConfig) -> None: ...
    async def send_audio_chunk(self, chunk: bytes) -> None: ...
    async def receive_events(self) -> AsyncIterator[RealtimeEvent]: ...
    async def close(self) -> None: ...

@dataclass
class RealtimeEvent:
    kind: Literal["partial_transcript", "final_transcript", "audio_chunk", "error", "cost_update"]
    data: dict
    timestamp_ms: int
```

### 4.2 Pipeline session

```
1. /voice-realtime invoked
2. context.detect_active()          → ContextPackage (projet, objectif, tâches)
3. summarization.compact(pkg, budget) → CompactedContext (≤3000 tokens V1)
4. provider.connect(model, ctx)
5. audio.start_microphone_stream()
6. while session_active:
     event = await provider.receive_events()
     transcript.render(event)
     cost_tracker.update(event)
     if cost_tracker.over_limit(): provider.close(); break
7. summarization.generate_summary(transcript)
8. obsidian.save_session_note(summary)
9. memory.reinject(summary)
```

### 4.3 Modules

| Module | Responsabilité | Phase |
|--------|----------------|-------|
| `providers/openai.py` | OpenAI Realtime client | 1 |
| `providers/gemini.py` | Stub interface V1, live V1.1 | 1 (stub) / 2 (live) |
| `context/detector.py` | Détection projet actif (lecture daily/weekly note, env var, glob `_System/active-context.md`) | 1 |
| `summarization/compacter.py` | Builder du CompactedContext | 1 |
| `summarization/summary.py` | Génération summary post-session via `claude -p` | 1 |
| `websocket/session.py` | Boucle async, audio streaming | 1 |
| `cost-tracking/tracker.py` | Estimation live + kill switch | 1 |
| `transcript/renderer.py` | Live terminal + save markdown | 1 |
| `obsidian/save.py` | Écriture note `1 PROJETS/<X>/Voice Sessions/YYYY-MM-DD HH-MM.md` | 1 |
| `commands/voice_realtime.py` | Entry point CLI | 1 |
| `config/providers.yaml` | Pricing, max_context, voice profile | 1 |

### 4.4 Config providers

```yaml
# config/providers.yaml
providers:
  openai:
    enabled: true
    model: gpt-realtime  # à confirmer nom exact 2026
    max_context_tokens: 32000
    pricing:
      mode: token
      input_audio_per_1m: 40.00  # USD, à vérifier doc OpenAI
      output_audio_per_1m: 80.00

  gemini:
    enabled: false  # stub V1, live V1.1
    model: gemini-live-2.5  # à confirmer
    max_context_tokens: 64000
    pricing:
      mode: minute
      per_minute: 0.10  # à vérifier doc Google

context_budgets:
  low: 3000
  medium: 8000
  high: 20000

limits:
  default_max_duration_minutes: 15
  warning_cost_usd: 1.00
  hard_stop_cost_usd: 3.00
  monthly_budget_usd: 50.00
```

### 4.5 Context detection (V1)

Sources prioritaires :
1. **Daily note du jour** (phase active) → intention + 3 priorités + reste à faire
2. **Weekly note active** → priorités + tâches Deep Focus
3. **Projet actif** : env var `VR_PROJECT` ou flag `--project <nom>`, sinon dernier projet modifié dans `1 PROJETS/`
4. **Mémoire auto Claude** : `~/.claude/projects/.../memory/MEMORY.md` (index)

Hors scope V1 : graphe Obsidian, recherche sémantique vault, conversations Claude Code passées.

### 4.6 Cost tracking V1

- Estimation **avant** session : durée prévue × tarif/min provider → warn si > $1
- Live update toutes les 30 s
- Kill switch hard à $3/session ou 15 min (configurable)
- Persistance : `~/.voice-realtime/sessions.jsonl` (1 ligne par session) — pas NocoDB V1 (perf + simplicité)
- Compteur mensuel : sum jsonl du mois courant, alerte 80 % budget

## 5. Phases

### Phase 0 — Design doc (actuelle)

- [x] Repo bootstrap
- [x] README + DESIGN.md V0
- [x] Stub skill `.claude/commands/voice-realtime.md`
- [ ] Validation Stéphane : tensions, choix langage, cas d'usage pilote

### Phase 1 — MVP exécutable (~2-3 semaines effort)

- [ ] Choix langage final (Python ou TS) après vérif SDK
- [ ] Choix cas d'usage pilote
- [ ] Provider abstraction + OpenAI Realtime live
- [ ] Context compacter V0 (budget low : 3000 tokens, 1 source = daily/weekly note)
- [ ] WebSocket session + audio in/out
- [ ] Transcript live terminal + save markdown
- [ ] Cost tracking + kill switch
- [ ] Stub Gemini provider (interface only)
- [ ] Tests usage réel 2 semaines, 10 sessions minimum

**Gate de fin Phase 1 :** 10 sessions réellement utilisées + budget respecté + au moins 3 notes summary générées et lues post-session.

### Phase 2 — Si Phase 1 validée

- Gemini Live wire
- Summary auto enrichi + extraction décisions/actions structurées
- Rolling context window pour sessions > 15 min
- Configurable budget mensuel + Telegram alert
- Latency metrics

### Phase 3+ — Reportée

- Multimodal (caméra/screen)
- Local model fallback
- Multi-agent concurrent voice
- Telegram/Discord/mobile

## 6. Open questions

1. **Langage final** — Python (cohérence) ou TS (audio realtime maturity) ?
2. **Cas d'usage pilote Phase 1** — brainstorming projet / Mom Test debrief / coach addicto HALT ?
3. **Auth OpenAI** — compte API à créer (pas encore de clé Anthropic-style configurée pour OpenAI), budget à approvisionner.
4. **Auth Gemini** — réutiliser OAuth `gws` existant ou nouvelle clé API ?
5. **Microphone capture** — `sounddevice` Python ou pipeline OS-natif ? Réutilisation Superwhisper exclue (cf. note projet).
6. **Persistance budget** — jsonl local (V1) puis NocoDB `ctt_voice_realtime_sessions` (V2) ?
7. **Summary post-session** — via `claude -p` (cohérence règle vault) ou via le modèle realtime lui-même ?
8. **Concurrence Superwhisper** — un `/voice-realtime` actif kill-il Superwhisper ? Ou les deux coexistent ?

## 7. Risques

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Abandon 3 mois (pattern documenté Intention) | Élevée | Élevé | Phase 1 minimale, gate de validation usage réel |
| Coût explose si usage > prévu | Moyenne | Moyen | Kill switch hard $3/session, budget mensuel $50 |
| SDK Python OpenAI Realtime immature | Moyenne | Élevé | Vérif blocking Phase 1, fallback TS si besoin |
| Latence audio inacceptable en SSH/remote | Faible | Moyen | V1 = Mac local only, remote = Phase 2+ |
| Confusion avec Jarvis voice / Superwhisper | Moyenne | Faible | Doc claire, README, note projet, naming explicite |

## 8. Décisions à acter

- [ ] Langage : Python | TS
- [ ] Cas d'usage pilote Phase 1
- [ ] Mode auth OpenAI (compte perso à créer + carte associée)
- [ ] Soft launch (juste pour soi) ou Build in Public dès V1 ?
- [ ] Repo public GitHub ou privé ?
