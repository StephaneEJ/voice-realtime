# Batterie de tests — voice-realtime Phase 3 V2 (2026-05-24)

Tests à exécuter en une session après les 7 commits de la journée :
`P0.1` VAD slider · `P0.2` killchat FR · `3.A` persona system · `3.D` persona new ·
`3.E` cost metrics · `3.G` synthesis inline · `3.H` rolling-terminal context.

Ordre conseillé : A (automatique, 2 min) → B (vocaux, 15-20 min) → C (vérifs post, 5 min).

Budget mois actuel : ~$4.5 / $22 (20%). La batterie B coûtera ~$1 cumulé.

---

## A — Tests automatiques (sans audio)

### A1. Pytest full suite

```bash
cd ~/OBSIDIAN/PROJETS\ DEV/voice-realtime
uv run pytest -q
```

**Attendu** : `138 passed, 1 warning` en <2s. Aucun fail.

### A2. CLI help — sous-commandes persona

```bash
uv run voice-realtime --help
uv run voice-realtime persona --help
uv run voice-realtime persona new --help
uv run voice-realtime talk --help | grep -E "vad|persona|rolling-terminal"
```

**Attendu** :
- Sous-commande `persona` visible dans le help racine
- `persona` a 3 commandes : `list`, `show`, `new`
- `persona new` accepte tous les flags (--name, --description, --voice, --vad, --creativity, --greeting-mode, --greeting-text, --skills, --notes, --overwrite, --dry-run)
- `talk` expose les flags `--vad`, `--persona`, `--rolling-terminal`, `--terminal-interval`

### A3. Status — cost breakdown + sparkline 30j

```bash
uv run voice-realtime status
```

**Attendu** :
- Panel avec Today / Last 7 days / This month
- Pourcentage du budget mensuel
- Sparkline 30 jours (chars `▁▂▃▄▅▆▇█`)
- Date range affichée

### A4. Persona list — table 3 personas

```bash
uv run voice-realtime persona list
```

**Attendu** : Table Rich avec `jarvis`, `hormozi`, `coach-halt` :
- Jarvis : voice=Charon, vad=balanced, provider=gemini, skills=`—`
- Hormozi : voice=Charon, vad=balanced, provider=gemini, skills=`5+1`
- Coach HALT : voice=Charon, vad=patient, provider=gemini, skills=`1+0`

### A5. Persona show — Hormozi (knowledge block lourd)

```bash
uv run voice-realtime persona show hormozi
```

**Attendu** :
- Panel "Persona" avec name/slug/voice/model/provider/vad/greeting/skills/notes/source
- Panel "System prompt" avec le markdown body
- Panel "Knowledge block" : ~16 000 chars (cap), preview 1500 chars
- Pas de Warnings (toutes les skills + notes Hormozi sont résolues)

### A6. Persona show — Jarvis (vide, pas de filter)

```bash
uv run voice-realtime persona show jarvis
```

**Attendu** : Panel Persona + System prompt. Pas de Knowledge block (filter vide).

### A7. Persona new — dry-run sans appel claude

```bash
# Doit ÉCHOUER avec slug invalide
uv run voice-realtime persona new "Bad Slug" --dry-run
# → red error sur slug

# Doit échouer si existe déjà
uv run voice-realtime persona new jarvis --dry-run
# → red "Persona already exists"
```

---

## B — Tests vocaux (audio, casque obligatoire)

> **Pré-requis** : AirPods Pro ou casque branché. Mute Deezer/Spotify si lancés (la pause auto les attrapera). Pas de bruit ambient excessif (ou utiliser `--vad very-patient`).

### B1. VAD slider — `very-patient` vs `balanced`

```bash
# Test 1 — balanced (défaut, ancien comportement)
uv run voice-realtime talk --vad balanced --max-minutes 2 --cost-cap 0.20 -c
```

Dis quelques phrases en marquant des courtes pauses (0.5s). Vois si le modèle te coupe trop vite ou pas. **Note la sensation**.

```bash
# Test 2 — very-patient (anti-bruit ambient)
uv run voice-realtime talk --vad very-patient --max-minutes 2 --cost-cap 0.20 -c
```

Refais la même chose. Tape sur ton clavier exprès, racle ta gorge. **Le modèle doit moins se laisser interrompre**.

**Vérif logs** : `grep "silence_duration_ms" ~/.voice-realtime/logs/$(ls -t ~/.voice-realtime/logs | head -1)` → tu vois `silence_duration_ms=700` (balanced) puis `silence_duration_ms=2000` (very-patient).

### B2. Killchat FR — "termine la session"

```bash
uv run voice-realtime talk --max-minutes 5 --cost-cap 0.30 -c
```

1. Dis "salut" puis quelques phrases banales (~1 min).
2. Dis **"termine la session"** seul, comme une phrase isolée.
3. **Attendu** : le modèle dit farewell ("Fin voice realtime") puis close propre. La session se ferme sans Ctrl+C.

**Vérif** :
```bash
grep "killchat\|end_reason" ~/.voice-realtime/logs/$(ls -t ~/.voice-realtime/logs | head -1)
```
Tu dois voir `end_reason=user_voice_killchat`.

Retry avec les autres mot-clés si tu veux : `fin jarvis`, `stop session`. Tous doivent fermer la session.

### B3. Persona Jarvis — greeting fixe + posture ISTP

```bash
uv run voice-realtime talk --persona jarvis --max-minutes 2 --cost-cap 0.20 -c
```

**Attendu** :
- Premier audio : "Salut Stéphane, je suis connecté, je t'écoute."
- RIEN d'autre tant que tu n'as pas parlé.
- Pose une question banale. Modèle = direct, pas flatteur, court (2-3 phrases max).

### B4. Persona Hormozi — coach offres + skills vault chargés

```bash
uv run voice-realtime talk --persona hormozi --max-minutes 3 --cost-cap 0.30 -c --project "Libert"
```

**Attendu** :
- Greeting : "Salut Stéphane. Sur quelle offre on bosse aujourd'hui ?"
- Pose une vague question business : "j'hésite à vendre mon coaching à 500 ou 1500 euros".
- Modèle = challenge direct, ramène à value equation, demande Dream Outcome / CAC / LTV.
- Doit citer ses propres concepts ($100M Offers, Grand Slam, Bonus Stack...).

**Vérif knowledge block utilisé** :
```bash
grep "hormozi-offer\|Connaissances actives" ~/.voice-realtime/logs/$(ls -t ~/.voice-realtime/logs | head -1)
```

### B5. Persona Coach HALT — questions HALT + ton calme

```bash
uv run voice-realtime talk --persona coach-halt --max-minutes 2 --cost-cap 0.20 -c
```

**Attendu** :
- Greeting : "Là, maintenant. Qu'est-ce qui se passe ?"
- Dis "j'ai envie de boire un verre".
- Modèle pose HALT dans l'ordre : Hungry → Angry → Lonely → Tired. UNE question à la fois.
- Phrases ultra-courtes. Pas de leçon, pas de moralisation.

### B6. Rolling-terminal context — absorption delta

```bash
# Active rolling-terminal + claude-context, intervalle court pour tester
uv run voice-realtime talk --persona jarvis --claude-context --rolling-terminal --terminal-interval 60 --max-minutes 4 --cost-cap 0.40 -c
```

Pendant la session vocale (sur une autre fenêtre / un autre tab Claude Code) :
1. Tape une question ou un message complet dans Claude Code, attends sa réponse.
2. Continue à parler avec le persona vocal — discutez d'un autre sujet.
3. Au bout d'environ 60-90 secondes : pose au persona vocal une question liée à CE que tu viens d'écrire dans Claude Code (ex: "tu as vu ce qu'on vient de discuter dans le terminal ?").

**Attendu** : le persona vocal sait ce que tu viens d'écrire dans Claude Code (sans que tu aies eu à le répéter vocalement).

**Vérif logs** :
```bash
grep "rolling-terminal" ~/.voice-realtime/logs/$(ls -t ~/.voice-realtime/logs | head -1)
```
Tu dois voir au moins 1 ligne `rolling-terminal injection #N (delta X chars, offset=Y)`.

---

## C — Vérifications post-session (manual review)

### C1. Note voice-session — synthèse inline

```bash
ls -t "/Users/stephanedufresne/OBSIDIAN/2ND_CERVEAU/_System/voice-sessions/" | head -5
```

Ouvre la note la plus récente (de B3/B4/B5). **Vérif** :
- En bas, la section "## Notes post-session — Synthèse auto" **remplace** le placeholder "à compléter manuellement".
- Sections : Sujet / Décisions / Actions / Insights / Questions ouvertes — toutes remplies (ou marquées `_(aucune)_`).

### C2. Note projet — synthèse appendée

Si tu as utilisé `--project "Libert"` (B4), ouvre `1 PROJETS/Liberté Accélérée - Core Product/Liberté Accélérée - Core Product.md`. **Vérif** :
- En bas (avant le `---` final ou EOF) une section "## Voice session YYYY-MM-DD HH:MM — synthèse (gemini)".
- Wikilink vers la note voice-session : `**Transcript brut :** [[2026-05-24 HH-MM — gemini]]`.

### C3. Stats — nouvelles sessions visibles

```bash
uv run voice-realtime status
```

**Vérif** :
- `Today` a augmenté d'environ ~$0.5-1.0 (selon le nombre de sessions B exécutées).
- Le dernier caractère de la sparkline est plus haut qu'avant.

### C4. Vérif dashboard NocoDB (si actif)

Sessions B doivent apparaître dans la table `ctt_voice_realtime_sessions` (44 backfillées + nouvelles). Dépend de `~/.nocodb.env`.

---

## Tableau de scoring rapide

| Test | OK / Bug | Notes |
|---|---|---|
| A1 pytest | ☐ / ☐ | |
| A2 CLI help | ☐ / ☐ | |
| A3 status sparkline | ☐ / ☐ | |
| A4 persona list | ☐ / ☐ | |
| A5 persona show hormozi | ☐ / ☐ | |
| A6 persona show jarvis | ☐ / ☐ | |
| A7 persona new dry-run | ☐ / ☐ | |
| B1 VAD balanced vs very-patient | ☐ / ☐ | |
| B2 killchat "termine la session" | ☐ / ☐ | |
| B3 persona jarvis | ☐ / ☐ | |
| B4 persona hormozi + skills | ☐ / ☐ | |
| B5 persona coach-halt | ☐ / ☐ | |
| B6 rolling-terminal absorption | ☐ / ☐ | |
| C1 synthèse inline transcript | ☐ / ☐ | |
| C2 synthèse projet | ☐ / ☐ | |
| C3 stats nouvelles sessions | ☐ / ☐ | |
| C4 NocoDB | ☐ / ☐ | |

---

## Si quelque chose plante

- `pgrep -af voice-realtime` → check zombies, `kill -KILL <pid>` si besoin
- `rm ~/.voice-realtime/active.lock` si une session précédente s'est mal fermée
- Log de la dernière session : `tail -100 ~/.voice-realtime/logs/$(ls -t ~/.voice-realtime/logs | head -1)`

---

## Prochaine étape — non livrée ce sprint

**3.F UX macOS native** — bloqué design. Brief Claude Design copy-paste dans `~/.claude/plans/14-il-faut-qu-on-temporal-hearth.md` (section "Brief Claude Design"). À ouvrir https://claude.ai/design avec le brief pour obtenir mockups menubar + popup + split-screen + sidebar avatar/VU.
