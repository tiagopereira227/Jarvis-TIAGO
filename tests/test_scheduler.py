# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Proactive scheduler: briefing fires once/day, event alerts fire once."""

from __future__ import annotations

import datetime as dt

from jarvis.briefing import compose_briefing, greeting_for_now
from jarvis.scheduler import ProactiveScheduler, _parse_hhmm


class _FakeRegistry:
    """Minimal registry stub returning canned skill outputs."""

    def __init__(self, calendar_text=""):
        self._cal = calendar_text

    def dispatch(self, name, args=None):
        if name == "get_calendar":
            return self._cal
        if name == "get_weather":
            return "Weather in Lisbon: clear sky, 20°C."
        if name == "get_news":
            return "1. Something happened."
        return ""


def test_parse_hhmm():
    assert _parse_hhmm("09:30", (0, 0)) == (9, 30)
    assert _parse_hhmm("bad", (9, 30)) == (9, 30)
    assert _parse_hhmm("25:61", (9, 30)) == (9, 30)


def test_greeting_shape():
    assert greeting_for_now().startswith("Good ")


def test_briefing_composes_and_nonempty(registry):
    text = compose_briefing(registry, salutation="sir")
    assert text and "," in text  # greeting + date line always present


def test_briefing_fires_once_per_day():
    spoken = []
    reg = _FakeRegistry()
    s = ProactiveScheduler(reg, speak=spoken.append, briefing_time="09:30",
                           alerts_enabled=False)
    base = dt.datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
    s._maybe_briefing(base - dt.timedelta(minutes=1))   # before target
    assert spoken == []
    s._maybe_briefing(base + dt.timedelta(seconds=30))  # in window
    assert len(spoken) == 1
    s._maybe_briefing(base + dt.timedelta(minutes=2))   # same day again
    assert len(spoken) == 1  # no repeat


def test_event_alert_fires_once():
    alerts = []
    soon = (dt.datetime.now() + dt.timedelta(minutes=5)).strftime("%H:%M")
    reg = _FakeRegistry(calendar_text=f"Today's events:\n{soon} — Standup")
    s = ProactiveScheduler(reg, speak=alerts.append, briefing_enabled=False,
                           alert_lead_minutes=10)
    s._maybe_event_alerts(dt.datetime.now())
    assert len(alerts) == 1 and "Standup" in alerts[0]
    s._maybe_event_alerts(dt.datetime.now())  # dedupe
    assert len(alerts) == 1


def test_event_alert_ignores_far_events():
    alerts = []
    far = (dt.datetime.now() + dt.timedelta(hours=5)).strftime("%H:%M")
    reg = _FakeRegistry(calendar_text=f"Today's events:\n{far} — Later")
    s = ProactiveScheduler(reg, speak=alerts.append, briefing_enabled=False,
                           alert_lead_minutes=10)
    s._maybe_event_alerts(dt.datetime.now())
    assert alerts == []
