# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Entry point: a text (and optionally voice) chat loop with JARVIS.

Run with:
    python3 -m jarvis                 # text in, text out
    python3 -m jarvis --speak         # text in, JARVIS speaks replies
    python3 -m jarvis --voice         # speak to JARVIS and hear replies
    python3 -m jarvis --wake          # hands-free: say "Jarvis" then your command
    python3 -m jarvis --dashboard     # HUD dashboard in the browser

Quit with: 'exit', 'quit', or Ctrl-D / Ctrl-C.
"""

from __future__ import annotations

import argparse
import sys

from .brain import Brain
from .config import Config
from .skills import default_registry
from .voice import Listener, Speaker, WakeWord

BANNER = r"""
      _   _    ____     __     __ ___   ____
     | | / \  |  _ \    \ \   / /|_ _| / ___|
  _  | |/ _ \ | |_) |    \ \ / /  | |  \___ \
 | |_| / ___ \|  _ <      \ V /   | |   ___) |
  \___/_/   \_\_| \_\      \_/   |___| |____/
"""

QUIT_WORDS = {"exit", "quit", "bye", "goodbye"}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jarvis", description="Your JARVIS assistant.")
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch the HUD dashboard in a browser instead of the terminal chat.",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Dashboard host (default 127.0.0.1)."
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Dashboard port (default 8000)."
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Listen for spoken input via the microphone (needs sounddevice + API key).",
    )
    parser.add_argument(
        "--wake",
        action="store_true",
        help='Hands-free: wait for the wake word "Jarvis" before each command '
        "(implies --voice).",
    )
    parser.add_argument(
        "--boot",
        action="store_true",
        help="Full power-up: start dashboard, open browser, greet aloud, then "
        "run the daemon. This is what auto-start launches.",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in the background; summon JARVIS with a global hotkey.",
    )
    parser.add_argument(
        "--hotkey",
        default="ctrl+alt+j",
        help="Global hotkey for --daemon (default: ctrl+alt+j).",
    )
    parser.add_argument(
        "--install-autostart",
        action="store_true",
        help="Launch JARVIS (--daemon) automatically when your computer starts.",
    )
    parser.add_argument(
        "--uninstall-autostart",
        action="store_true",
        help="Remove the auto-start entry.",
    )
    speak = parser.add_mutually_exclusive_group()
    speak.add_argument(
        "--speak",
        dest="speak",
        action="store_true",
        help="Speak replies aloud.",
    )
    speak.add_argument(
        "--no-speak",
        dest="speak",
        action="store_false",
        help="Do not speak replies (text only).",
    )
    # Default: speak aloud only when --voice is on. Resolved after parsing.
    parser.set_defaults(speak=None)
    return parser.parse_args(argv)


def _get_input(
    listener: Listener | None,
    waker: "WakeWord | None" = None,
    speaker: "Speaker | None" = None,
) -> str | None:
    """Return the next user utterance, or None to quit (EOF/interrupt)."""
    # Hands-free wake-word mode: wait for "Jarvis", then take the command.
    if waker is not None and waker.available:
        print('(listening for "Jarvis"...)')
        trailing = waker.wait_for_wake()
        # Barge-in: the user spoke, so cut off any speech still playing.
        if speaker is not None:
            speaker.stop()
        if trailing:  # user said "Jarvis, <command>" in one breath
            print(f"you> {trailing}")
            return trailing
        # Woken with just the name — now capture the actual command.
        print("... yes? ...")
        heard = listener.listen() if listener else ""
        if heard:
            print(f"you> {heard}")
            return heard
        return ""  # heard nothing after wake; loop again

    if listener is not None and listener.available:
        try:
            input("(press Enter, then speak) ")
        except (EOFError, KeyboardInterrupt):
            return None
        print("... listening ...")
        heard = listener.listen()
        if heard:
            print(f"you> {heard}")
            return heard
        print("(heard nothing — type instead, or Enter to retry)")
    # Text input (either voice off, unavailable, or a failed capture).
    try:
        return input("you> ").strip()
    except (EOFError, KeyboardInterrupt):
        return None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # Dashboard mode: hand off to the HUD web server (its own Brain/registry).
    if args.dashboard:
        from .dashboard.server import serve

        print(f"JARVIS HUD starting at http://{args.host}:{args.port}")
        print("Open that URL in your browser. Ctrl-C to stop.")
        serve(host=args.host, port=args.port)
        return 0

    if args.install_autostart:
        from . import autostart

        print(autostart.install())
        return 0

    if args.uninstall_autostart:
        from . import autostart

        print(autostart.uninstall())
        return 0

    if args.boot:
        from .boot import run_boot

        return run_boot(host=args.host, port=args.port, hotkey=args.hotkey)

    if args.daemon:
        from .daemon import run_daemon

        return run_daemon(hotkey=args.hotkey)

    config = Config.load()
    registry = default_registry()
    brain = Brain(config, registry)

    # Re-arm any timers/alarms persisted from a previous session. Touching the
    # scheduler here loads the store (past-due alarms fire, stale timers drop)
    # before we take input, and records how many were restored.
    from .skills.reminders import _scheduler_for

    _scheduler_for(registry)
    restored = getattr(registry, "reminders_restored", 0)

    # --wake implies voice input.
    voice_on = args.voice or args.wake

    # Speak by default when voice mode is on; otherwise stay silent unless asked.
    speak = args.speak if args.speak is not None else voice_on
    speaker = (
        Speaker(
            backend=config.tts_backend,
            client=brain.client,
            voice=config.tts_voice,
            say_voice=config.say_voice,
        )
        if speak
        else None
    )
    listener = Listener(client=brain.client) if voice_on else None
    waker = WakeWord(listener) if (args.wake and listener) else None

    print(BANNER)
    mode = "online" if brain.online else "limited (no API key)"
    print(f"JARVIS {mode}. Skills: {', '.join(registry.names())}.")
    if restored:
        noun = "reminder" if restored == 1 else "reminders"
        print(f"Restored {restored} {noun} from a previous session.")
    if speaker is not None:
        print(f"Voice output: {'on (' + speaker.backend + ')' if speaker.enabled else 'unavailable'}.")
    if voice_on:
        if listener is not None and listener.available:
            print("Voice input: on." + (' Wake word: "Jarvis".' if waker else ""))
        else:
            reason = listener.why_unavailable() if listener else "disabled"
            print(f"Voice input: unavailable ({reason}). Falling back to typing.")
    print("Type 'exit' to disconnect.\n")

    greeting = "Good day. How may I be of service?"
    print(f"JARVIS: {greeting}\n")
    if speaker is not None:
        speaker.say(greeting)

    while True:
        user_input = _get_input(listener, waker, speaker)
        if user_input is None:
            farewell = "Very good. Powering down."
            print(f"\nJARVIS: {farewell}")
            if speaker is not None:
                speaker.say(farewell)
            return 0

        if not user_input:
            continue
        if user_input.lower() in QUIT_WORDS:
            farewell = "Very good. Powering down."
            print(f"JARVIS: {farewell}")
            if speaker is not None:
                speaker.say(farewell)
            return 0

        try:
            # Stream the reply so it appears as it's generated. We still collect
            # the full text to hand to TTS once complete.
            print("JARVIS: ", end="", flush=True)
            parts: list[str] = []
            for chunk in brain.respond_stream(user_input):
                print(chunk, end="", flush=True)
                parts.append(chunk)
            print("\n")
            reply = "".join(parts)
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            print(f"\nJARVIS: I'm afraid something went wrong: {exc}\n")
            continue

        if speaker is not None and reply.strip():
            # Speak in the background so, in wake mode, the next "Jarvis" can
            # barge in and cut it off via speaker.stop() in _get_input.
            speaker.say_async(reply)


if __name__ == "__main__":
    sys.exit(main())
