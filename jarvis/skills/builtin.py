# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""The starter set of skills JARVIS ships with.

Keep these dependency-free and cross-platform where reasonable. macOS-specific
bits (like `open`) degrade gracefully on other systems.
"""

from __future__ import annotations

import datetime as _dt
import json
import platform
import shutil
import subprocess
import urllib.parse
import urllib.request
from typing import Any

from .base import Skill
from .registry import SkillRegistry

# Shared HTTP timeout for network skills, in seconds. Keeps a dead endpoint
# from hanging the whole assistant.
_HTTP_TIMEOUT = 10


def _http_get_json(url: str) -> Any:
    """GET a URL and parse JSON. Raises on network/parse errors (callers catch)."""
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/0.1"})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


class TimeSkill(Skill):
    name = "get_time"
    description = "Get the current local date and time."
    parameters: dict[str, Any] = {}
    required: list[str] = []

    def run(self, **kwargs: Any) -> str:
        now = _dt.datetime.now()
        return now.strftime("It is %A, %d %B %Y, %H:%M:%S local time.")


class SystemInfoSkill(Skill):
    name = "get_system_info"
    description = "Report basic information about the machine JARVIS runs on."
    parameters: dict[str, Any] = {}
    required: list[str] = []

    def run(self, **kwargs: Any) -> str:
        uname = platform.uname()
        return (
            f"System: {uname.system} {uname.release} on {uname.machine}. "
            f"Host: {uname.node}. Python: {platform.python_version()}."
        )


class OpenAppSkill(Skill):
    name = "open_app"
    description = (
        "Open an application or file on the local machine. On macOS this uses "
        "the `open` command (e.g. name='Safari' or name='Calculator')."
    )
    parameters: dict[str, Any] = {
        "name": {
            "type": "string",
            "description": "The application or file name to open.",
        }
    }
    required = ["name"]

    def run(self, name: str = "", **kwargs: Any) -> str:
        name = (name or "").strip()
        if not name:
            return "[error] No application name given."

        system = platform.system()
        # Build the command per-platform. We pass args as a list (no shell),
        # so the user-supplied name can't be used for shell injection.
        if system == "Darwin":
            cmd = ["open", "-a", name]
        elif system == "Windows":
            cmd = ["cmd", "/c", "start", "", name]
        else:  # Linux and friends
            launcher = shutil.which("xdg-open")
            if launcher is None:
                return "[error] No 'xdg-open' available to launch apps on this system."
            cmd = [launcher, name]

        try:
            subprocess.Popen(cmd)  # noqa: S603 - args are a list, not a shell string
        except FileNotFoundError:
            return f"[error] Could not find a launcher to open {name!r}."
        except Exception as exc:  # noqa: BLE001
            return f"[error] Failed to open {name!r}: {exc}"
        return f"Opening {name}."


class WeatherSkill(Skill):
    name = "get_weather"
    description = (
        "Get the current weather for a place by name (city, town, etc.). "
        "Uses the free Open-Meteo service; no API key required."
    )
    parameters: dict[str, Any] = {
        "location": {
            "type": "string",
            "description": "Place name, e.g. 'Lisbon' or 'New York'.",
        }
    }
    required = ["location"]

    # WMO weather codes -> short description (the common subset).
    _CODES = {
        0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
        45: "fog", 48: "depositing rime fog", 51: "light drizzle",
        53: "moderate drizzle", 55: "dense drizzle", 61: "slight rain",
        63: "moderate rain", 65: "heavy rain", 71: "slight snow",
        73: "moderate snow", 75: "heavy snow", 80: "rain showers",
        81: "moderate rain showers", 82: "violent rain showers",
        95: "thunderstorm", 96: "thunderstorm with hail",
    }

    def run(self, location: str = "", **kwargs: Any) -> str:
        location = (location or "").strip()
        if not location:
            return "[error] No location given."

        # 1) Geocode the place name to coordinates.
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": location, "count": 1})
        )
        try:
            geo = _http_get_json(geo_url)
        except Exception as exc:  # noqa: BLE001
            return f"[error] Could not look up '{location}': {exc}"

        results = geo.get("results") or []
        if not results:
            return f"I couldn't find a place called '{location}'."
        place = results[0]
        lat, lon = place["latitude"], place["longitude"]
        label = ", ".join(
            p for p in (place.get("name"), place.get("country")) if p
        )

        # 2) Fetch current weather for those coordinates.
        wx_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
            {"latitude": lat, "longitude": lon, "current_weather": "true"}
        )
        try:
            wx = _http_get_json(wx_url)
        except Exception as exc:  # noqa: BLE001
            return f"[error] Could not fetch weather for {label}: {exc}"

        current = wx.get("current_weather") or {}
        temp = current.get("temperature")
        wind = current.get("windspeed")
        desc = self._CODES.get(current.get("weathercode"), "unknown conditions")
        if temp is None:
            return f"[error] No current weather data for {label}."
        return (
            f"Weather in {label}: {desc}, {temp}°C, wind {wind} km/h."
        )


class WebSearchSkill(Skill):
    name = "web_search"
    description = (
        "Look up a quick factual answer or summary from the web using "
        "DuckDuckGo's Instant Answer API. Best for definitions, facts, and "
        "well-known entities; not a full search-results list."
    )
    parameters: dict[str, Any] = {
        "query": {
            "type": "string",
            "description": "What to look up.",
        }
    }
    required = ["query"]

    def run(self, query: str = "", **kwargs: Any) -> str:
        query = (query or "").strip()
        if not query:
            return "[error] No query given."

        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
            {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        )
        try:
            data = _http_get_json(url)
        except Exception as exc:  # noqa: BLE001
            return f"[error] Search failed: {exc}"

        # Prefer a direct abstract; fall back to the first related topic.
        abstract = (data.get("AbstractText") or "").strip()
        if abstract:
            source = data.get("AbstractURL") or ""
            tail = f" (source: {source})" if source else ""
            return f"{abstract}{tail}"

        answer = (data.get("Answer") or "").strip()
        if answer:
            return answer

        related = data.get("RelatedTopics") or []
        for topic in related:
            text = (topic.get("Text") or "").strip() if isinstance(topic, dict) else ""
            if text:
                return text

        return f"I found nothing conclusive for '{query}'."


def default_registry() -> SkillRegistry:
    """Build a registry pre-loaded with the built-in skills."""
    from .calendar_read import CalendarSkill
    from .news import NewsSkill
    from .notes import AddNoteSkill, ReadClipboardSkill, ReadNotesSkill
    from .power import RestartSkill, ShutdownSkill, SuspendSkill
    from .reminders import (
        AlarmSkill,
        CancelReminderSkill,
        ListRemindersSkill,
        TimerSkill,
    )
    from .screenshot import ScreenshotDescribeSkill
    from .shell import ShellSkill
    from .spotify import SpotifySkill
    from .system_control import BrightnessSkill, DoNotDisturbSkill, VolumeSkill

    registry = SkillRegistry()
    # Core
    registry.register(TimeSkill())
    registry.register(SystemInfoSkill())
    registry.register(OpenAppSkill())
    registry.register(WeatherSkill())
    registry.register(WebSearchSkill())
    # Media
    registry.register(SpotifySkill())
    # Timers & alarms
    registry.register(TimerSkill())
    registry.register(AlarmSkill())
    registry.register(ListRemindersSkill())
    registry.register(CancelReminderSkill())
    # Information
    registry.register(NewsSkill())
    registry.register(CalendarSkill())
    # Clipboard & notes
    registry.register(ReadClipboardSkill())
    registry.register(AddNoteSkill())
    registry.register(ReadNotesSkill())
    # System controls
    registry.register(VolumeSkill())
    registry.register(BrightnessSkill())
    registry.register(DoNotDisturbSkill())
    # Vision
    registry.register(ScreenshotDescribeSkill())
    # Dev shell (read-only runs directly; mutating requires confirmation)
    registry.register(ShellSkill())
    # Power (each requires explicit confirmation before acting)
    registry.register(ShutdownSkill())
    registry.register(RestartSkill())
    registry.register(SuspendSkill())
    # Auto-discover any additional drop-in skills under jarvis/skills/ that
    # aren't registered above. Lets you add a new skill file without editing
    # this function. The explicit registrations above set a sensible order;
    # discovery only fills in what's new.
    registry.autodiscover()
    return registry
