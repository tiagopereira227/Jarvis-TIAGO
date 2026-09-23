# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Text-to-speech: give JARVIS a voice.

Backends, picked automatically per platform:
- "openai": natural-sounding, needs an API key + internet. Opt-in.
- "local":  the OS's built-in speech — macOS `say`, or Windows PowerShell
            System.Speech. Zero dependencies, offline.

If none is available (e.g. Linux with no client and no `spd-say`/`espeak`),
speaking becomes a silent no-op so the app never breaks.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
import threading
from typing import Any


class Speaker:
    def __init__(
        self,
        backend: str = "auto",
        client: Any | None = None,
        voice: str = "onyx",
        say_voice: str | None = None,
    ) -> None:
        self._client = client
        self._voice = voice
        self._say_voice = say_voice
        self._backend = self._resolve_backend(backend, client)
        # Barge-in support: track the current playback process and speaking
        # thread so a caller can stop() speech the instant the user talks.
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self._lock = threading.Lock()

    # -- Local (offline) speech availability, per platform ------------------

    @staticmethod
    def _local_kind() -> str | None:
        """Which local speech engine this OS offers, or None."""
        system = platform.system()
        if system == "Darwin" and shutil.which("say"):
            return "macos"
        if system == "Windows":
            # PowerShell ships with System.Speech; powershell.exe is always present.
            if shutil.which("powershell") or shutil.which("powershell.exe"):
                return "windows"
        if system == "Linux":
            if shutil.which("spd-say"):
                return "linux-spd"
            if shutil.which("espeak"):
                return "linux-espeak"
        return None

    def _has_local(self) -> bool:
        return self._local_kind() is not None

    def _resolve_backend(self, backend: str, client: Any | None) -> str:
        if backend == "openai":
            return "openai" if client is not None else self._fallback()
        if backend in ("say", "local"):  # "say" kept for backward compat
            return "local" if self._has_local() else "none"
        # auto: prefer local (offline, instant). OpenAI TTS is opt-in.
        return self._fallback()

    def _fallback(self) -> str:
        return "local" if self._has_local() else "none"

    @property
    def backend(self) -> str:
        """Public backend label, including the local engine when relevant."""
        if self._backend == "local":
            return f"local:{self._local_kind()}"
        return self._backend

    @property
    def enabled(self) -> bool:
        return self._backend != "none"

    # -- Process tracking (for barge-in) -----------------------------------

    def _spawn(self, cmd: list[str], input_text: str | None = None, **kwargs: Any) -> None:
        """Start a speech/playback process we can later stop(), and wait on it.

        If ``input_text`` is given, it's written to the process's stdin (used by
        the Windows PowerShell path, which reads the phrase from stdin).
        """
        if input_text is not None:
            kwargs.setdefault("stdin", subprocess.PIPE)
            kwargs.setdefault("text", True)
        with self._lock:
            if self._stopped.is_set():
                return
            self._proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
            proc = self._proc
        try:
            proc.communicate(input=input_text)  # feeds stdin (if any) and waits
        except Exception:  # noqa: BLE001
            pass
        with self._lock:
            if self._proc is proc:
                self._proc = None

    def stop(self) -> None:
        """Immediately stop any in-progress speech (barge-in)."""
        self._stopped.set()
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass

    def is_speaking(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def wait(self) -> None:
        t = self._thread
        if t is not None:
            t.join()

    def say_async(self, text: str) -> None:
        """Speak in the background so the caller can keep listening / stop()."""
        text = (text or "").strip()
        if not text or self._backend == "none":
            return
        self.wait()  # let any previous utterance finish/stop first
        self._stopped.clear()
        self._thread = threading.Thread(target=self.say, args=(text,), daemon=True)
        self._thread.start()

    def say(self, text: str) -> None:
        """Speak the text (blocking). Never raises; failure degrades to silence."""
        text = (text or "").strip()
        if not text or self._backend == "none":
            return
        try:
            if self._backend == "openai":
                self._say_openai(text)
            else:
                self._say_local(text)
        except Exception:  # noqa: BLE001 - speech is a nicety, not critical
            # Fall back to local speech once if OpenAI TTS fails mid-session.
            if self._backend == "openai" and self._has_local():
                try:
                    self._say_local(text)
                except Exception:  # noqa: BLE001
                    pass

    # -- Local speech engines ----------------------------------------------

    def _say_local(self, text: str) -> None:
        kind = self._local_kind()
        if kind == "macos":
            self._say_macos(text)
        elif kind == "windows":
            self._say_windows(text)
        elif kind == "linux-spd":
            self._spawn(["spd-say", "--wait", text])
        elif kind == "linux-espeak":
            self._spawn(["espeak", text])

    def _say_macos(self, text: str) -> None:
        cmd = ["say"]
        if self._say_voice:
            cmd += ["-v", self._say_voice]
        cmd.append(text)
        # List args (no shell): user/LLM text can't be a shell injection vector.
        self._spawn(cmd)

    def _say_windows(self, text: str) -> None:
        # Drive System.Speech from PowerShell. We pass the text via stdin (not
        # interpolated into the script) so it can't break out of the string or
        # inject PowerShell — the script reads it verbatim from the pipe.
        voice_line = (
            f"$s.SelectVoice('{self._say_voice}');" if self._say_voice else ""
        )
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"{voice_line}"
            "$t = [Console]::In.ReadToEnd();"
            "$s.Speak($t);"
        )
        exe = shutil.which("powershell") or shutil.which("powershell.exe") or "powershell"
        self._spawn(
            [exe, "-NoProfile", "-NonInteractive", "-Command", script],
            input_text=text,
        )

    # -- OpenAI TTS ---------------------------------------------------------

    def _say_openai(self, text: str) -> None:
        # Stream speech to a temp file, then play it with the OS player.
        with self._client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=self._voice,
            input=text,
        ) as response:
            with tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False
            ) as tmp:
                path = tmp.name
                for chunk in response.iter_bytes():
                    tmp.write(chunk)
        try:
            self._play(path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _play(self, path: str) -> None:
        # Route playback through _spawn so stop() can cut it off mid-audio.
        system = platform.system()
        if system == "Darwin" and shutil.which("afplay"):
            self._spawn(["afplay", path])
            return
        if system == "Windows":
            if shutil.which("ffplay"):
                self._spawn(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
                )
            else:
                # Best effort: hand off to the default player (not stoppable).
                os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
            return
        if shutil.which("ffplay"):
            self._spawn(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
            )
        # else: no player available; silently skip.
