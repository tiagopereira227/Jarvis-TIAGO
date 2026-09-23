# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Background daemon: an always-running JARVIS summoned by a global hotkey.

Runs quietly in the background. Press the hotkey (default Ctrl+Alt+J) anywhere
and JARVIS listens for a spoken command, answers, and speaks the reply — then
goes back to waiting. It's the "always there" mode, closest to the films.

The global hotkey uses `pynput`, which is optional:
- With it, the hotkey works system-wide (from any app).
- Without it, we fall back to a terminal prompt: press Enter in this window to
  trigger a command. So the daemon is useful even before you install pynput.

macOS note: capturing a global hotkey needs Accessibility permission
(System Settings → Privacy & Security → Accessibility) for the terminal/app
running this. Without it, pynput silently won't receive keys — we detect the
likely case and tell the user to use the Enter fallback or grant permission.

Voice input still needs sounddevice + an API key (the Listener); without those
the daemon takes typed commands instead.
"""

from __future__ import annotations

import sys
import threading
from typing import Any

from .brain import Brain
from .config import Config
from .skills import default_registry
from .voice import Listener, Speaker


def _parse_hotkey(spec: str) -> str:
    """Normalise a hotkey spec into pynput's <mod>+<mod>+<key> format."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    out = []
    for p in parts:
        if p in ("ctrl", "control"):
            out.append("<ctrl>")
        elif p in ("alt", "option", "opt"):
            out.append("<alt>")
        elif p in ("cmd", "command", "super", "win"):
            out.append("<cmd>")
        elif p in ("shift",):
            out.append("<shift>")
        else:
            out.append(p)  # a literal key like "j"
    return "+".join(out)


class Daemon:
    """Always-running assistant triggered by a hotkey (or Enter fallback)."""

    def __init__(self, hotkey: str = "ctrl+alt+j") -> None:
        self.config = Config.load()
        self.registry = default_registry()
        self.brain = Brain(self.config, self.registry)
        # Re-arm persisted reminders like the other entry points.
        from .skills.reminders import _scheduler_for

        _scheduler_for(self.registry)

        self.speaker = Speaker(
            backend=self.config.tts_backend,
            client=self.brain.client,
            voice=self.config.tts_voice,
            say_voice=self.config.say_voice,
        )
        self.listener = Listener(client=self.brain.client)
        self._hotkey = hotkey
        self._busy = threading.Lock()
        self._stop = threading.Event()

        # Proactive scheduler: speaks the morning briefing + event alerts while
        # the daemon runs. Speaks via the same Speaker (async, so barge-in and
        # normal commands still work).
        from .scheduler import ProactiveScheduler

        self.scheduler = ProactiveScheduler(
            self.registry,
            speak=self._speak_proactive,
            briefing_time=self.config.briefing_time,
            briefing_enabled=self.config.briefing_enabled,
            alerts_enabled=self.config.alerts_enabled,
            alert_lead_minutes=self.config.alert_lead_minutes,
        )

    def _speak_proactive(self, text: str) -> None:
        """Speak a proactive message: print it and say it aloud."""
        print(f"\n[JARVIS] {text}\n", flush=True)
        self.speaker.say_async(text)

    # -- One interaction ----------------------------------------------------

    def _handle(self) -> None:
        """Capture one command and respond. Guarded so overlapping triggers
        don't stack up."""
        if not self._busy.acquire(blocking=False):
            return  # already handling a command; ignore the extra trigger
        try:
            # Barge-in: stop anything currently being spoken.
            self.speaker.stop()
            if self.listener.available:
                print("\n[JARVIS] Listening...", flush=True)
                text = self.listener.listen()
            else:
                try:
                    text = input("\n[JARVIS] Command> ").strip()
                except (EOFError, KeyboardInterrupt):
                    return
            if not text:
                print("[JARVIS] (nothing heard)", flush=True)
                return
            print(f"[you] {text}", flush=True)
            print("[JARVIS] ", end="", flush=True)
            parts: list[str] = []
            for chunk in self.brain.respond_stream(text):
                print(chunk, end="", flush=True)
                parts.append(chunk)
            print("", flush=True)
            reply = "".join(parts)
            if reply.strip():
                self.speaker.say_async(reply)
        finally:
            self._busy.release()

    # -- Run loops ----------------------------------------------------------

    def run(self) -> int:
        """Start the daemon. Uses a global hotkey if pynput is available,
        otherwise an Enter-to-trigger loop."""
        try:
            from pynput import keyboard  # type: ignore
        except Exception:  # noqa: BLE001
            keyboard = None

        mode = "online" if self.brain.online else "limited (no API key)"
        voice = "voice" if self.listener.available else "text"
        print(f"JARVIS daemon running [{mode}, {voice} input].")

        # Kick off proactive briefing/alerts alongside the hotkey listener.
        self.scheduler.start()
        print(f"Proactive: {self.scheduler.summary()}.")

        if keyboard is None:
            print(
                "Global hotkey needs 'pynput' (pip install pynput). Falling back:"
                " press Enter here to talk to JARVIS. Ctrl-C to quit.\n"
            )
            return self._run_enter_loop()

        hk = _parse_hotkey(self._hotkey)
        print(f'Press {self._hotkey.upper()} anywhere to summon JARVIS. Ctrl-C to quit.')
        print(
            "(macOS: if the hotkey does nothing, grant Accessibility permission "
            "to your terminal, or use Ctrl-C then run without a hotkey.)\n"
        )

        def on_activate() -> None:
            # Run the handler on its own thread so the hotkey listener stays
            # responsive (and a long reply doesn't block the next trigger).
            threading.Thread(target=self._handle, daemon=True).start()

        try:
            with keyboard.GlobalHotKeys({hk: on_activate}) as _:
                while not self._stop.is_set():
                    self._stop.wait(0.5)
        except KeyboardInterrupt:
            pass
        self.scheduler.stop()
        print("\nJARVIS daemon stopped.")
        return 0

    def _run_enter_loop(self) -> int:
        try:
            while not self._stop.is_set():
                try:
                    input()  # wait for Enter
                except EOFError:
                    break
                self._handle()
        except KeyboardInterrupt:
            pass
        self.scheduler.stop()
        print("\nJARVIS daemon stopped.")
        return 0


def run_daemon(hotkey: str = "ctrl+alt+j") -> int:
    return Daemon(hotkey=hotkey).run()
