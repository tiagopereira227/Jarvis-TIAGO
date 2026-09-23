# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Proactive scheduler: JARVIS reaches out on its own.

Runs a background thread that:
- fires a spoken **morning briefing** once per day at a configured time
  (default 09:30), and
- checks the calendar periodically and gives a **pre-event alert** a few
  minutes before something starts.

It speaks through a callback (the daemon passes Speaker.say_async), so the
scheduler itself knows nothing about audio. Everything is opt-in and best-effort
— a failed briefing or calendar read is logged-and-skipped, never fatal.

Known ceiling: this only fires while JARVIS is actually running (see the daemon
and the auto-start LaunchAgent). It can't wake a sleeping/off machine.
"""

from __future__ import annotations

import datetime as _dt
import re
import threading
from typing import Any, Callable

from .briefing import compose_briefing

# How often the loop wakes to check the clock / calendar, in seconds. Small
# enough to hit the briefing minute and event lead time without busy-spinning.
_TICK = 20.0


def _parse_hhmm(spec: str, default: tuple[int, int]) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", spec or "")
    if not m:
        return default
    hh, mm = int(m.group(1)), int(m.group(2))
    if 0 <= hh < 24 and 0 <= mm < 60:
        return hh, mm
    return default


class ProactiveScheduler:
    """Fires the morning briefing and pre-event alerts on a background thread."""

    def __init__(
        self,
        registry: Any,
        speak: Callable[[str], None],
        *,
        briefing_time: str = "09:30",
        briefing_enabled: bool = True,
        alerts_enabled: bool = True,
        alert_lead_minutes: int = 10,
        salutation: str = "sir",
    ) -> None:
        self._registry = registry
        self._speak = speak
        self._bh, self._bm = _parse_hhmm(briefing_time, (9, 30))
        self._briefing_enabled = briefing_enabled
        self._alerts_enabled = alerts_enabled
        self._lead = max(1, int(alert_lead_minutes))
        self._salutation = salutation

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Guard rails against repeat-firing within the same tick window.
        self._last_briefing_date: _dt.date | None = None
        self._alerted: set[str] = set()  # event keys we've already announced

    # -- Lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def summary(self) -> str:
        bits = []
        if self._briefing_enabled:
            bits.append(f"briefing at {self._bh:02d}:{self._bm:02d}")
        if self._alerts_enabled:
            bits.append(f"event alerts {self._lead} min ahead")
        return ", ".join(bits) if bits else "proactive features off"

    # -- Main loop ----------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = _dt.datetime.now()
            try:
                if self._briefing_enabled:
                    self._maybe_briefing(now)
                if self._alerts_enabled:
                    self._maybe_event_alerts(now)
            except Exception:  # noqa: BLE001 - proactive features must not crash
                pass
            self._stop.wait(_TICK)

    def _maybe_briefing(self, now: _dt.datetime) -> None:
        # Fire once when we first observe a time at/just after the target today.
        if self._last_briefing_date == now.date():
            return
        target = now.replace(hour=self._bh, minute=self._bm, second=0, microsecond=0)
        # Fire if we're within the tick window after the target (so a slightly
        # late tick still catches it), but not before it.
        if target <= now < target + _dt.timedelta(minutes=5):
            self._last_briefing_date = now.date()
            text = compose_briefing(self._registry, salutation=self._salutation)
            if text:
                self._speak(text)

    def _maybe_event_alerts(self, now: _dt.datetime) -> None:
        """Announce events starting within the lead window (once each)."""
        events = self._todays_timed_events()
        for start, title in events:
            if start < now:
                continue
            minutes_away = (start - now).total_seconds() / 60.0
            if 0 <= minutes_away <= self._lead:
                key = f"{start.isoformat()}|{title}"
                if key in self._alerted:
                    continue
                self._alerted.add(key)
                mins = max(1, round(minutes_away))
                self._speak(
                    f"{self._salutation.capitalize()}, a reminder: "
                    f"'{title}' begins in about {mins} minute"
                    f"{'s' if mins != 1 else ''}."
                )

    def _todays_timed_events(self) -> list[tuple[_dt.datetime, str]]:
        """Parse the calendar skill's output back into (start_dt, title) pairs.

        The calendar skill returns lines like "09:30 — Standup". We only need
        today's timed events for near-term alerts, so we pair each HH:MM with
        today's date. Lines without a time are skipped.
        """
        raw = self._registry.dispatch("get_calendar")
        if not raw or raw.strip().startswith("[error]"):
            return []
        today = _dt.date.today()
        out: list[tuple[_dt.datetime, str]] = []
        for line in raw.splitlines():
            m = re.match(r"\s*(\d{1,2}):(\d{2})\s*[—-]\s*(.+)", line)
            if not m:
                continue
            hh, mm, title = int(m.group(1)), int(m.group(2)), m.group(3).strip()
            if 0 <= hh < 24 and 0 <= mm < 60:
                out.append((_dt.datetime.combine(today, _dt.time(hh, mm)), title))
        return out
