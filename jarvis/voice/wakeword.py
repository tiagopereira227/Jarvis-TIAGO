# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Wake-word detection: wait until the user says "Jarvis".

Approach (lazy but dependency-free): reuse the same mic + Whisper we already
have. We capture short VAD-bounded utterances and check whether the transcript
contains the wake word. When it does, the caller can then capture the actual
command.

This is deliberately not a real always-on wake-word engine. It transcribes
every short utterance, which costs a Whisper call per phrase — fine for desktop
use, wasteful at scale. The documented upgrade path is a dedicated on-device
wake-word model (openWakeWord, Porcupine, or Vosk) that runs locally for free
and only wakes Whisper once triggered.

Cross-platform: it relies only on the Listener (sounddevice + Whisper), so it
behaves the same on macOS, Windows, and Linux, and is unavailable (gracefully)
wherever the Listener is.
"""

from __future__ import annotations

import re
from typing import Any

from .stt import Listener

# Accept common mishearings of "jarvis" so a slightly-off transcription still
# triggers (Whisper often renders it "Jarvez", "Travis", "Jarvis," etc.).
_WAKE_PATTERNS = [
    r"\bjarvis\b",
    r"\bjarvez\b",
    r"\bjarvi\b",
    r"\byou there jarvis\b",
    r"\bhey jarvis\b",
    r"\bok jarvis\b",
]
_WAKE_RE = re.compile("|".join(_WAKE_PATTERNS), re.IGNORECASE)


def contains_wake_word(text: str) -> bool:
    """True if the transcript looks like it contains the wake word."""
    return bool(_WAKE_RE.search(text or ""))


def strip_wake_word(text: str) -> str:
    """Remove the wake word from the front of a phrase, if present.

    Lets "Jarvis, what's the weather" be handled in one breath: we detect the
    wake word and treat the remainder as the command.
    """
    if not text:
        return ""
    cleaned = _WAKE_RE.sub("", text, count=1)
    # Trim leftover punctuation/space where the wake word was.
    return cleaned.lstrip(" ,.:;-").strip()


class WakeWord:
    """Listens for the wake word using the shared Listener."""

    def __init__(self, listener: Listener) -> None:
        self._listener = listener

    @property
    def available(self) -> bool:
        return self._listener.available

    def wait_for_wake(self, on_listen: Any = None) -> str:
        """Block until the wake word is heard. Returns any trailing command text.

        Loops: capture a short utterance, transcribe, check for the wake word.
        If the user said "Jarvis, do X", the "do X" part is returned so the
        caller can act on it immediately; otherwise returns "".
        Returns None only if listening is unavailable.
        """
        if not self.available:
            return None  # caller should fall back to manual trigger
        while True:
            heard = self._listener.listen(vad=True)
            if callable(on_listen):
                on_listen(heard)
            if heard and contains_wake_word(heard):
                return strip_wake_word(heard)
            # else keep looping until we hear our name
