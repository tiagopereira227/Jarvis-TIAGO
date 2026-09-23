# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Configuration loaded from the environment (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional; env vars still work without it.
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False


DEFAULT_MODEL = "gpt-4o-mini"


@dataclass
class Config:
    api_key: str | None
    model: str
    base_url: str | None
    # Voice settings
    tts_backend: str  # "auto" | "say" | "openai"
    tts_voice: str  # OpenAI voice name (used when tts_backend == "openai")
    say_voice: str | None  # macOS `say` voice name, or None for the default
    # Proactive scheduler settings
    briefing_enabled: bool
    briefing_time: str  # "HH:MM", default 09:30
    alerts_enabled: bool
    alert_lead_minutes: int

    @property
    def has_llm(self) -> bool:
        """True when we have enough to talk to an LLM."""
        return bool(self.api_key)

    @staticmethod
    def _bool(name: str, default: bool) -> bool:
        val = os.getenv(name)
        if val is None:
            return default
        return val.strip().lower() in ("1", "true", "yes", "on")

    @classmethod
    def load(cls) -> "Config":
        load_dotenv()  # reads .env in the working dir if present
        api_key = os.getenv("JARVIS_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = os.getenv("JARVIS_MODEL", DEFAULT_MODEL)
        base_url = os.getenv("JARVIS_BASE_URL") or None
        tts_backend = (os.getenv("JARVIS_TTS_BACKEND") or "auto").lower()
        tts_voice = os.getenv("JARVIS_TTS_VOICE", "onyx")
        say_voice = os.getenv("JARVIS_SAY_VOICE") or None
        try:
            lead = int(os.getenv("JARVIS_ALERT_LEAD_MINUTES", "10"))
        except ValueError:
            lead = 10
        return cls(
            api_key=api_key or None,
            model=model,
            base_url=base_url,
            tts_backend=tts_backend,
            tts_voice=tts_voice,
            say_voice=say_voice,
            briefing_enabled=cls._bool("JARVIS_BRIEFING_ENABLED", True),
            briefing_time=os.getenv("JARVIS_BRIEFING_TIME", "09:30"),
            alerts_enabled=cls._bool("JARVIS_ALERTS_ENABLED", True),
            alert_lead_minutes=lead,
        )
