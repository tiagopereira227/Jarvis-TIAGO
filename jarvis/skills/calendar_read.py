# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Read today's calendar events.

Two sources, tried in order:
1. An .ics file, if JARVIS_ICS_PATH points at one (or a path is passed). This is
   fully cross-platform — macOS, Windows, and Linux — and needs no extra tools.
   Point it at an exported/subscribed calendar file.
2. macOS Calendar.app via AppleScript, as a zero-config fallback on Macs.

On Windows/Linux with no .ics configured, it explains how to enable this rather
than pretending there are no events. The .ics parser is a small, dependency-free
reader of the common VEVENT fields — not a full RFC 5545 implementation (it
handles typical DTSTART/DTEND/SUMMARY lines and all-day dates); that limit is
noted so the upgrade path (a real ics library) is clear.
"""

from __future__ import annotations

import datetime as _dt
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .base import Skill


def _ics_path(explicit: str) -> Path | None:
    raw = explicit.strip() or os.getenv("JARVIS_ICS_PATH", "")
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.exists() else None


def _parse_ics_dt(value: str) -> _dt.datetime | None:
    """Parse the common iCalendar date/date-time forms. None if unrecognized."""
    value = value.strip()
    # Strip a trailing 'Z' (UTC) — we compare on date only, so tz is not critical.
    utc = value.endswith("Z")
    if utc:
        value = value[:-1]
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            return _dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _unfold(text: str) -> list[str]:
    """iCalendar folds long lines with a leading space/tab on continuations."""
    out: list[str] = []
    for line in text.splitlines():
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _today_events_from_ics(path: Path) -> list[tuple[_dt.datetime, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    today = _dt.date.today()
    events: list[tuple[_dt.datetime, str]] = []
    start: _dt.datetime | None = None
    summary = ""
    in_event = False
    for line in _unfold(text):
        if line.startswith("BEGIN:VEVENT"):
            in_event, start, summary = True, None, ""
        elif line.startswith("END:VEVENT"):
            if start and start.date() == today:
                events.append((start, summary or "(no title)"))
            in_event = False
        elif in_event:
            # Keys can carry params, e.g. "DTSTART;VALUE=DATE:20260101".
            key, _, val = line.partition(":")
            key = key.split(";", 1)[0].upper()
            if key == "DTSTART":
                start = _parse_ics_dt(val)
            elif key == "SUMMARY":
                summary = val.strip()
    events.sort(key=lambda e: e[0])
    return events


def _today_events_from_macos() -> tuple[list[str] | None, str | None]:
    """Return (event_lines, error). Uses AppleScript against Calendar.app."""
    if platform.system() != "Darwin" or not shutil.which("osascript"):
        return None, "not macOS"
    # Ask Calendar for events whose start is within today. Kept simple; Calendar
    # scripting can be slow, so this is best-effort.
    script = r'''
    set output to ""
    set today to current date
    set hours of today to 0
    set minutes of today to 0
    set seconds of today to 0
    set tomorrow to today + (1 * days)
    tell application "Calendar"
        repeat with c in calendars
            repeat with e in (every event of c whose start date ≥ today and start date < tomorrow)
                set output to output & (start date of e as string) & " — " & (summary of e) & linefeed
            end repeat
        end repeat
    end tell
    return output
    '''
    try:
        proc = subprocess.run(  # noqa: S603
            ["osascript", "-e", script], capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return None, "Calendar took too long to respond."
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if proc.returncode != 0:
        return None, (proc.stderr or "").strip()
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    return lines, None


class CalendarSkill(Skill):
    name = "get_calendar"
    description = (
        "Read today's calendar events. Uses an .ics file if configured "
        "(JARVIS_ICS_PATH), otherwise macOS Calendar. Optionally pass an .ics path."
    )
    parameters: dict[str, Any] = {
        "ics_path": {
            "type": "string",
            "description": "Optional path to an .ics calendar file to read.",
        }
    }
    required: list[str] = []

    def run(self, ics_path: str = "", **kwargs: Any) -> str:
        # 1) Prefer an .ics file (cross-platform).
        path = _ics_path(ics_path)
        if path is not None:
            events = _today_events_from_ics(path)
            if not events:
                return "Nothing on your calendar today."
            lines = [f"{dt.strftime('%H:%M')} — {title}" for dt, title in events]
            return "Today's events:\n" + "\n".join(lines)

        # 2) macOS Calendar fallback.
        mac_lines, err = _today_events_from_macos()
        if mac_lines is not None:
            if not mac_lines:
                return "Nothing on your calendar today."
            return "Today's events:\n" + "\n".join(mac_lines)

        # 3) Nothing available — explain how to enable it.
        if err == "not macOS":
            return (
                "[error] No calendar source configured. Set JARVIS_ICS_PATH to an "
                ".ics file (exported or subscribed) and I'll read today's events."
            )
        return f"[error] Couldn't read the calendar: {err}"
