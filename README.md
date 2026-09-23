# JARVIS

A small, witty, butler-styled AI assistant in the spirit of Tony Stark's JARVIS.
Text chat, a cloud LLM brain, and an expandable skill system.

## Features

- **Conversational brain** — talks to any OpenAI-compatible chat model.
- **Skills** — things it can actually do:
  - Tell the time, report system info, open apps
  - Fetch the weather, run a quick web lookup
  - Control Spotify (play/pause/next/previous/open); play any track by name
    when the optional Spotify Web API is configured
  - Set countdown timers and clock alarms (list & cancel them); they persist
    across restarts and re-arm automatically
  - Read the latest news headlines (RSS/Atom, any feed)
  - Read the clipboard; take and read back notes
  - Check today's calendar, and **create events** (macOS Calendar, syncs to
    iPhone via iCloud)
  - Read unread email and send email (macOS Mail); send iMessages (Messages);
    create to-dos in Reminders (syncs to iPhone) — sends ask for confirmation
  - Adjust volume, brightness, and Do Not Disturb
  - Take a screenshot and describe it (vision model)
  - Run allowlisted dev commands (git, pytest, npm, ...) — read-only runs
    directly, anything that changes state asks first
  - Shut down, restart, or suspend the machine — **with confirmation**
- **Voice** — optional speech in (microphone → Whisper) and speech out (OS
  built-in voice or OpenAI TTS). Works on macOS, Windows, and Linux.
- **Safety** — destructive power actions never fire on a single command; they
  ask first and only proceed on an explicit "yes".
- **Personality** — a dry, unflappable butler tone.
- **Offline fallback** — with no API key it still runs the skills via a simple
  keyword router.

## Setup

```bash
# 1. (Recommended) create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your key
cp .env.example .env
# then edit .env and set JARVIS_API_KEY
```

## Run

```bash
python3 -m jarvis                 # text in, text out
python3 -m jarvis --speak         # text in, JARVIS speaks replies
python3 -m jarvis --voice         # speak to JARVIS and hear replies
python3 -m jarvis --voice --no-speak   # speak to it, read replies
python3 -m jarvis --wake          # hands-free: say "Jarvis" then your command
python3 -m jarvis --daemon        # background; summon with a global hotkey
python3 -m jarvis --dashboard     # launch the HUD dashboard in a browser
```

Replies stream in as they're generated (terminal and dashboard), and JARVIS's
speech is interruptible — start talking (wake mode) or send a new command
(dashboard) and it stops mid-sentence.

### Power-up & proactive briefing

- `python3 -m jarvis --boot` is the full "systems on" sequence: it starts the
  dashboard, opens it in Google Chrome, speaks a greeting ("Good morning, sir.
  Systems are starting."), and then runs the daemon (hotkey + proactive
  features). Set `JARVIS_BROWSER` to override the browser.
- **Auto-start on login:** `python3 -m jarvis --install-autostart` registers a
  per-user startup entry (macOS LaunchAgent / Windows Startup / Linux autostart)
  that runs `--boot` when you log in. Remove it with `--uninstall-autostart`.
- **Morning briefing:** while running, JARVIS speaks a weather + calendar + news
  summary at `JARVIS_BRIEFING_TIME` (default 09:30). Set `JARVIS_HOME_LOCATION`
  for the weather line.
- **Event alerts:** a spoken heads-up `JARVIS_ALERT_LEAD_MINUTES` (default 10)
  before calendar events. Needs a calendar source configured.
- Honest limit: these only fire while JARVIS is running and the machine is
  awake — auto-start launches it at login, but it can't run while the Mac is
  off or asleep.

### Hands-free & always-on

- `--wake` waits for the wake word "Jarvis" before each command. Say
  "Jarvis, what's the weather" in one breath, or just "Jarvis" then speak.
- `--daemon` runs quietly and listens for a global hotkey (default
  `Ctrl+Alt+J`, set with `--hotkey`). Press it from any app to talk to JARVIS.
  Needs `pip install pynput`; without it, press Enter in the daemon's terminal
  to trigger. On macOS, grant your terminal Accessibility permission for the
  global hotkey to work.

### Dashboard (the HUD)

`--dashboard` starts a local web server with an Iron Man-style HUD: live system
vitals (CPU/memory/storage), a clock, an animated core + radar, and an activity
log. Type in the command bar and JARVIS answers through the same brain and
skills as the terminal — and **reads its replies aloud** via your browser's
speech synthesis (toggle with the VOICE button, no extra setup). Open the
printed URL (default http://127.0.0.1:8000).

Needs the dashboard extras: `pip install 'fastapi' 'uvicorn[standard]' psutil`.
Without `psutil` it still runs, showing disk usage only.

The HUD also has a **click-to-talk mic** (browser speech recognition, feeds the
command bar), **persisted conversation history** (past turns replay on load),
and **live weather + news tiles** (set `JARVIS_HOME_LOCATION` for weather).

## Tests

```bash
pip install pytest
python3 -m pytest        # hermetic: no network, no API, temp store
```

Type `exit` (or Ctrl-D) to quit.

Without an API key, JARVIS runs in limited mode via a keyword router. Try:
"what time is it", "system info", "open Safari", "weather in Lisbon",
"play", "pause", "timer 5m", "alarm 07:30", "list timers", or "shut down".

### Power controls & confirmation

Asking JARVIS to shut down, restart, or suspend never happens immediately. It
replies with a confirmation question and waits. Your next message decides it:
say "yes" (or "confirm", "do it") to proceed; anything else cancels. This is
enforced in code, not just the prompt — there is no path that powers off
without that explicit confirmation.

## Adding a skill

1. Subclass `Skill` in `jarvis/skills/` — set `name`, `description`,
   `parameters` (a JSON-schema dict), and implement `run`.
2. Register it in `jarvis/skills/builtin.py` inside `default_registry()`.

That's it. The LLM sees the new tool automatically and can call it.

## Project layout

```
jarvis/
  __main__.py        # chat loop entry point (python3 -m jarvis)
  config.py          # environment / .env config
  persona.py         # the JARVIS system prompt
  brain.py           # LLM loop + tool calling, with an offline fallback
  voice/
    tts.py           # text-to-speech (macOS say / Windows / Linux / OpenAI)
    stt.py           # speech-to-text (mic capture + Whisper)
  skills/
    base.py          # Skill base class
    registry.py      # SkillRegistry: collects skills, dispatches calls
    confirm.py       # arm-then-confirm gate for dangerous actions
    builtin.py       # core skills + default_registry()
    spotify.py       # Spotify control (local app + Web API)
    spotify_web.py   # optional Spotify Web API backend (play by name)
    reminders.py     # timers & alarms (persisted, re-armed on startup)
    power.py         # shutdown / restart / suspend (confirmation-gated)
    news.py          # RSS/Atom headlines
    notes.py         # clipboard read + notes
    system_control.py# volume / brightness / do-not-disturb
    screenshot.py    # capture screen + describe (vision)
    shell.py         # allowlisted dev commands (confirmation-gated writes)
    calendar_read.py # today's events (macOS Calendar / .ics)
```

### Spotify Web API (optional)

By default JARVIS controls the local Spotify desktop app. To play *any* track by
name on your active device (from any platform), set up the Web API:

1. Create an app at the [Spotify developer dashboard](https://developer.spotify.com/dashboard).
2. Add a redirect URI (default `http://localhost:8888/callback`) to the app.
3. Put `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, and (if changed)
   `SPOTIFY_REDIRECT_URI` in your `.env`, and `pip install spotipy`.

The first "play <song>" opens a browser once to authorize; the token is cached
under the store dir. If it's not configured, JARVIS falls back to local control.

### Persistence

Timers and alarms are saved to `~/.jarvis/reminders.json` (override with
`JARVIS_STORE_DIR`) and re-armed on startup. A past-due alarm fires as soon as
JARVIS starts; a countdown timer that already elapsed while it was off is
dropped as stale.

## Roadmap ideas

- Voice activity detection (stop recording on silence) instead of fixed windows
- Spotify playlist/album control and volume
- Conversation memory across sessions
```

## License

Copyright (c) 2026 Tiago Pereira. All rights reserved.

This project is proprietary. See [LICENSE](LICENSE) for the full terms. No use,
copying, modification, or distribution is permitted without the prior written
permission of the copyright holder.
