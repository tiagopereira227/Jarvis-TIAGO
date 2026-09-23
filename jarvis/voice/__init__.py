# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Voice layer: text-to-speech (Speaker) and speech-to-text (Listener).

Both are optional and degrade gracefully — the app runs fine in pure text mode
when audio libraries or API keys are unavailable.
"""

from .stt import Listener
from .tts import Speaker
from .wakeword import WakeWord, contains_wake_word, strip_wake_word

__all__ = ["Speaker", "Listener", "WakeWord", "contains_wake_word", "strip_wake_word"]
