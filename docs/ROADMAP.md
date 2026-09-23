<!-- Copyright (c) 2026 Tiago Pereira. All rights reserved. -->
# JARVIS Roadmap

A record of what's built and what's parked, so ideas aren't lost between sessions.

## Shipped

- **Core assistant** — LLM brain with a witty butler persona, tool/skill calling,
  and an offline keyword-router fallback (works with no API key).
- **Skills (26)** — time, system info, open app, weather, web search, news,
  clipboard, notes, calendar, timers & alarms (persisted), Spotify (local +
  Web API play-by-name), volume/brightness/Do-Not-Disturb, screenshot+describe
  (vision), dev shell (allowlisted, confirmation-gated), power controls
  (shutdown/restart/suspend, confirmation-gated), and memory (remember/recall/
  forget). New skill files under `jarvis/skills/` are auto-discovered.
- **Voice** — speech in (mic → Whisper) with voice-activity detection, speech
  out (macOS `say` / Windows System.Speech / Linux / OpenAI TTS), a "Jarvis"
  wake word, and interruptible (barge-in) speech.
- **Dashboard** — the Iron Man-style HUD (FastAPI + WebSocket): live vitals,
  animated core/radar, activity log, command bar, streaming replies, and
  browser text-to-speech with a voice toggle.
- **Modes** — terminal chat, `--speak`, `--voice`, `--wake`, `--dashboard`,
  and `--daemon` (global hotkey).
- **Cross-session memory** — facts persisted in `~/.jarvis`, injected into the
  system prompt.

## Archived — Wave 5 (parked, not started)

Deferred by choice; pick up when ready.

### Home automation
Control smart lights/plugs/scenes via **Home Assistant** (REST/WebSocket API,
long-lived token) or **HomeKit**. Would land as skills: `set_light`,
`run_scene`, etc. Home Assistant is the more portable target (one API covers
many device brands). Needs the user's hub URL + token in `.env`.

### Proactive morning briefing
A "good morning" that composes existing skills into one spoken summary:
weather + today's calendar + top news headlines. Mostly orchestration over
skills already built; the new part is a scheduler/trigger (a specific time, or
the first interaction of the day) and a briefing template.

## Archived — Wave 6: real phone calls (Twilio) (parked, not started)

Have JARVIS place an **actual phone call** to the user (e.g. for the morning
briefing or an urgent alert) rather than only speaking through the computer.

- Uses **Twilio** Programmable Voice: a paid account, a purchased phone number,
  and account SID / auth token credentials.
- A `call_me` capability places an outbound call and reads text via Twilio's
  TTS (TwiML `<Say>`), or streams our own audio.
- Requires JARVIS to run somewhere always-on (a small server / VPS), since a
  laptop can only call when the app happens to be running.
- Credentials and the destination phone number live in the user's private
  `.env` (gitignored) — never hardcoded in source.
- Per-call cost applies. Consider it only if spoken-through-computer briefings
  aren't enough.

## Archived — Local model (Ollama) support (parked, not started)

Run the brain on a local model via **Ollama** instead of OpenAI: no API cost,
fully offline, private. Ollama exposes an OpenAI-compatible endpoint, so it's
mostly config — set `JARVIS_BASE_URL=http://localhost:11434/v1` and the model
name, plus a dummy API key. Verify tool-calling works on the chosen local model
(smaller models are weaker at it; may need a fallback to the offline router).

## Smaller future ideas

- Wake word via a dedicated on-device model (openWakeWord / Porcupine) instead
  of transcribing every phrase with Whisper.
- Voice-activity detection upgrade to a spectral/ML VAD (webrtcvad / silero).
- Spotify playlist/album control and volume.
- Semantic (vector) memory instead of a flat fact list.
