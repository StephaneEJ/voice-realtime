# Phase 3+ — Roadmap & architectural notes

Drafted 2026-05-24 to capture the design space before implementation.
Each section: target, why now, sketch, key risks, "ship gate".

---

## 3.1 — Local model fallback (whisper.cpp + Ollama + Piper)

**Target.** Run voice-realtime offline / $0 cost for low-latency tolerant
sessions (drafting, journaling, alcohol-coach HALT).

**Why now.** User mentioned vocally 23/05 wanting free/connectable voice
models. Budget cap $22/mo = soft, but having a $0 path future-proofs.

**Sketch.** Three subprocesses (see `voice_realtime/providers/local.py` stub):
- `whisper-cli --server :8081` streaming STT (Mac CPU, M-series ~30× realtime
  on `medium.en` model)
- `ollama` HTTP `/api/generate` streaming, model `qwen2.5:3b` or `llama3.2:3b`
  (~5 GB RAM, > 30 tok/s on M-series)
- `piper --output_raw` streaming TTS from stdin, voice `fr_FR-siwis-medium`

**Key risks.**
1. Latency. TTFA target < 1.5 s ; realistic is 1.5-3 s. UX gap vs cloud
   providers (~400-600 ms) is real.
2. Quality. Local 3B reasoning << GPT-5/Gemini for nuanced brainstorm.
   Constrain to drafting / journaling use cases initially.
3. Interruption. Piper doesn't natively support mid-utterance cancel.
   Implement by killing+respawning subprocess on barge-in.

**Ship gate.** 5 real sessions with `--provider local`, transcript saved,
auto-summary acceptable. Compare against `gemini-2.5-flash` matrix on the
9 dimensions (timbre, diction, rhythm, STT FR, latencies, coherence,
relevance, robustness).

---

## 3.2 — Telegram bridge

**Target.** Receive Telegram voice messages → process through the same
pipeline as `talk` → reply with synthesized audio. Mobile-only conversation
on the go.

**Why now.** Stéphane has the Jarvis Telegram bot already running on VPS
(systemd `claude-telegram.service`). Voice messages are already supported
in the bot API.

**Sketch.**
- New service `voice-realtime telegram-listen` (long-running, on Mac or VPS)
- Subscribes to Telegram bot `voice` updates via `python-telegram-bot`
- For each incoming voice message:
  1. Download .ogg file from Telegram
  2. Decode → 16 kHz PCM16 chunks
  3. Send to Gemini Live (or local) provider in a one-shot session
  4. Wait for `final_transcript_user` + `final_transcript_model`
  5. Synthesize model text via Edge TTS (or stream Gemini audio directly)
  6. Send back as voice message to Telegram

**Key risks.**
1. Cold-start latency. Open WebSocket per message = ~700 ms overhead.
   Mitigation: keep one warm session per chat, time-out after 5 min idle.
2. Multi-user concurrency. If Stéphane forwards to a family chat, need
   per-chat locks (reuse the `acquire_lock` pattern with chat_id key).
3. Cost. Each minute of voice = $0.023 (Gemini). Telegram users could
   spam. Budget guard at chat_id level needed.

**Ship gate.** End-to-end voice ping-pong on Stéphane's own chat. Then
expose to bootcamp / family chat behind allowlist.

---

## 3.3 — Multi-agent concurrent sessions

**Target.** Two voice agents in a triangular conversation. E.g.
"Stéphane parle au coach health" + "Stéphane parle à l'investisseur",
two windows, two distinct context loads, neither stomps the other.

**Why now.** Memory `feedback_split_subbugs_before_coding` + the fact
that `acquire_lock` currently refuses any 2nd instance prevents this
today. Multi-agent is the natural next step once Phase 2 is solid.

**Sketch.** Replace the single `~/.voice-realtime/active.lock` with a
named-lock pattern: `~/.voice-realtime/locks/<agent-name>.lock`. Each
agent declares a name via `--agent-name coach-health`. Mic capture stays
mutually exclusive (only one mic instance can read PortAudio at a time)
— either:
- Option A : one mic, multiplexed by user keystroke (Tab to switch agent)
- Option B : two mics (USB headset + AirPods), routed per-agent

**Key risks.**
1. Audio mix on output. Playback might overlap. Need ducking or per-agent
   stereo channels.
2. Mental load. Two agents = cognitive overhead may negate benefits.
   Validate UX before building.

**Ship gate.** N/A — pause until Phase 3.1 + 3.2 land, re-evaluate need.

---

## 3.4 — Multimodal (camera + screen capture)

**Target.** Visual context for the voice session : Stéphane shows code
on screen, voice agent references it ("la fonction ligne 42"). Or shows
a chart, agent comments.

**Why now.** Gemini Live supports image input natively. OpenAI Realtime
gained vision support 2026-Q1. Both providers exposing the right APIs.

**Sketch.**
- New flag `--screen-share` or `--camera`
- Periodic snapshot (every 3-5 s) sent as `inline_data` (Gemini) or
  `conversation.item.create` with image content (OpenAI)
- Snapshot via `screencapture -t jpg -x` (Mac) for screen, or
  `imagesnap` for camera
- Throttle to avoid burning budget (each image = ~$0.001 on Gemini)

**Key risks.**
1. Privacy. Screen contains secrets, passwords, etc. Default OFF, opt-in
   with explicit warning.
2. Token cost. Image input cheaper than audio but still adds up. Cap
   1 image / 5 s minimum interval.
3. Provider parity. Gemini handles streaming images natively, OpenAI
   requires per-turn upload — different code paths.

**Ship gate.** A single session where Stéphane shares his Voice Realtime
README scroll on screen, and the agent quotes a specific section.

---

## 3.5 — Tool calling background

**Target.** During the voice session, the agent can take actions
(open a file, run a search, post a Telegram message) without
interrupting the conversation flow. Detect tool intent from voice,
execute in background, mention result naturally in next turn.

**Why now.** User mentioned vocally 23/05 wanting "modèles voix
connectables avec des actions en arrière-plan". Both Gemini Live and
OpenAI Realtime support function calling at the protocol level.

**Sketch.**
- Define a tool registry in `tools/voice_tools.py` :
  - `read_file(path)` — return file contents to inject as context
  - `search_vault(query)` — grep vault, return top 3 matches
  - `note_action(text)` — append to today's daily note
  - `query_nocodb(table, where)` — read-only reporting
- Register via `tools` param in provider connect()
- On `tool_call` event, dispatch + return result as `function_response`
- Result is injected as silent note (same mechanism as rolling recap),
  agent picks it up at next turn

**Key risks.**
1. False positives. Voice STT misheard ("relire mon fichier" → search
   action). Require explicit confirmation tone before destructive tools.
2. Restricted tool set. NEVER expose `Write` or `Bash` to voice — too
   easy to fat-finger.
3. Latency. Tool execution adds 100-500 ms before next turn. Acceptable
   for non-critical actions.

**Ship gate.** Stéphane asks "qu'est-ce que dit mon Contexte Global
sur le sport ?", agent reads + summarizes. Then asks "ajoute à ma daily
que j'ai couru ce matin", agent confirms + writes.

---

## Implementation order (proposed)

1. **3.1 Local model** — closes the loop on the vocal feedback ("free
   models"). High user-perceived value, contained scope.
2. **3.5 Tool calling** — natural extension of voice agent capability,
   builds on existing context_loader. Highest leverage.
3. **3.2 Telegram bridge** — mobile use case unlocks daily journaling.
   Needs VPS deploy + per-chat budget. Larger DevOps footprint.
4. **3.4 Multimodal** — nice-to-have but niche. Wait until 3.1/3.5 ship.
5. **3.3 Multi-agent** — speculative. Re-evaluate need after 3.1-3.4.

---

## Out of scope (intentional)

- Phone call integration (Twilio etc.). Telegram bridge already covers
  the "remote audio" need.
- Custom voice cloning. Piper voices are good enough; per memory
  `feedback_voice_realtime_raison_etre` the project is bridge to CLI
  context, not voice synthesis polish.
- Continuous always-on mode (wake word). Power + privacy mess, no
  proven need.
