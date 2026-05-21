# voice-realtime

Skill `/voice-realtime` pour OpenCode / Claude Code — conversation vocale duplex temps réel (WebSocket) avec préservation de contexte LLM compactée et budgétée.

**Status :** Phase 0 — design doc. Pas exécutable.

## Pourquoi ce projet

Le mode TTS actuel (Edge TTS via Jarvis) est unidirectionnel : Claude écrit, l'utilisateur écoute. Realtime ouvre un mode duplex : parler et être interrompu, latence ~400-600 ms, conversation naturelle.

Cas d'usage envisagés (à arbitrer en design doc) :
- Brainstorming projet actif (charger contexte projet, parler 15-30 min, sortir avec décisions + actions)
- Préparation / debrief interviews Mom Test
- Coaching vocal (santé, alcool, journaling émotionnel)

## Architecture cible

```
voice-realtime/
├── providers/          # OpenAI Realtime, Gemini Live, future local
├── context/            # détection contexte actif (vault, OpenCode)
├── summarization/      # compactage + budgétage avant envoi
├── websocket/          # session realtime (connexion, audio, events)
├── cost-tracking/      # estimation + kill switch budget
├── transcript/         # live terminal + sauvegarde markdown
├── obsidian/           # post-session : summary, décisions, actions
├── commands/           # commandes CLI / skill OpenCode
├── config/             # providers, budgets, limites
└── docs/               # DESIGN.md, ADRs
```

## Décisions de cadrage (2026-05-21)

| Question | Décision | Notes |
|----------|----------|-------|
| Cas d'usage V1 | Multi-usage généraliste | Mitigé par MVP 1 cas d'usage pilote en Phase 1 |
| Budget mensuel | <$50/mois (5h max) | Kill switch agressif obligatoire dès MVP |
| Provider V1 | OpenAI + Gemini | OpenAI live, Gemini en stub abstraction |
| Structure | PROJETS DEV + skill stub vault | Pattern établi |

## Phases

- **Phase 0** — Design doc figé (`docs/DESIGN.md`). En cours.
- **Phase 1** — MVP : 1 provider live (OpenAI), 1 cas d'usage pilote, transcript markdown, kill switch budget.
- **Phase 2** — Gemini live, summary auto Obsidian, rolling context.
- **Phase 3+** — Multimodal, local model, multi-agent, Telegram/Discord.

## Liens

- Note projet vault : `2ND_CERVEAU/1 PROJETS/Voice Realtime Skill/Voice Realtime Skill.md`
- Skill stub : `2ND_CERVEAU/.claude/commands/voice-realtime.md`
- Spec source : fournie par Stéphane 2026-05-21 (16 chapitres)

## Licence

Privé. Usage perso.
