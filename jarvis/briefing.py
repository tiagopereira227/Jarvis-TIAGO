# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Compose a proactive spoken briefing from existing skills.

The morning briefing stitches together weather + today's calendar + top news
into one short, natural summary that JARVIS can speak. It reuses the skills we
already have (get_weather, get_calendar, get_news) via the registry, so there's
no duplicated logic — this is pure orchestration.

Everything degrades gracefully: any part that errors or is unconfigured (e.g.
no calendar source, no home location for weather) is simply left out rather
than breaking the whole briefing.
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Any


def _clean(result: str) -> str | None:
    """Return a skill result if it's usable, else None (drops [error]/empty)."""
    if not result:
        return None
    text = result.strip()
    if not text or text.startswith("[error]"):
        return None
    return text


def greeting_for_now() -> str:
    """A time-appropriate greeting."""
    hour = _dt.datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def compose_briefing(registry: Any, *, salutation: str = "sir") -> str:
    """Build the spoken briefing string from the available skills.

    Weather uses JARVIS_HOME_LOCATION (skipped if unset). Calendar and news are
    best-effort. The result always at least greets and gives the date, so the
    briefing is never empty.
    """
    now = _dt.datetime.now()
    parts: list[str] = [
        f"{greeting_for_now()}, {salutation}. "
        f"It's {now.strftime('%A, %d %B')}, {now.strftime('%H:%M')}."
    ]

    # Weather (needs a configured home location).
    location = os.getenv("JARVIS_HOME_LOCATION", "").strip()
    if location:
        wx = _clean(registry.dispatch("get_weather", {"location": location}))
        if wx:
            parts.append(wx)

    # Today's calendar.
    cal = _clean(registry.dispatch("get_calendar"))
    if cal:
        if "nothing on your calendar" in cal.lower():
            parts.append("You have nothing on your calendar today.")
        else:
            parts.append(cal)

    # Upcoming course tests / group tasks (next 7 days). Spoken in Portuguese,
    # since the course manager is Portuguese. Pulled straight from the shared
    # course store on the registry.
    courses = getattr(registry, "courses", None)
    if courses is not None:
        try:
            itens = courses.upcoming(7)
        except Exception:  # noqa: BLE001
            itens = []
        if itens:
            linhas = [
                f"{it['kind']} de {it['discipline']} a {it['date']}"
                + (f" ({it['title']})" if it.get("title") else "")
                for it in itens
            ]
            parts.append("Para esta semana: " + "; ".join(linhas) + ".")

    # Top news headlines (keep it short for speech).
    news = _clean(registry.dispatch("get_news", {"count": 3}))
    if news:
        parts.append(news)

    return "\n".join(parts)
