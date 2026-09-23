# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Create calendar events (macOS Calendar.app, which syncs to iPhone via iCloud).

Adds an event to Calendar.app using AppleScript. If your Mac's Calendar is
signed into iCloud, the event syncs to your iPhone automatically — that's how
"put it in my calendar" reaches your phone, no extra integration needed.

Platform: macOS only (needs Calendar.app + osascript). On other systems the
skill explains it isn't available rather than pretending it worked.

Security: the event title/notes are user- or LLM-supplied free text, so they are
passed to AppleScript via environment variables and read with
`system attribute` inside the script — never string-interpolated into the
AppleScript source. That removes the injection risk from quotes/newlines in a
title like `Movie "night"`.
"""

from __future__ import annotations

import datetime as _dt
import os
import platform
import shutil
import subprocess
from typing import Any

from .base import Skill

# The AppleScript that creates the event. It reads its inputs from environment
# variables (JARVIS_EVT_*) so no user text is embedded in the script text.
_CREATE_SCRIPT = r'''
set theTitle to (system attribute "JARVIS_EVT_TITLE")
set theNotes to (system attribute "JARVIS_EVT_NOTES")
set calName to (system attribute "JARVIS_EVT_CAL")
set y to (system attribute "JARVIS_EVT_Y") as integer
set mo to (system attribute "JARVIS_EVT_MO") as integer
set d to (system attribute "JARVIS_EVT_D") as integer
set h to (system attribute "JARVIS_EVT_H") as integer
set mi to (system attribute "JARVIS_EVT_MI") as integer
set durMin to (system attribute "JARVIS_EVT_DUR") as integer
set allDay to (system attribute "JARVIS_EVT_ALLDAY")

set startDate to current date
set year of startDate to y
set month of startDate to mo
set day of startDate to d
set hours of startDate to h
set minutes of startDate to mi
set seconds of startDate to 0
set endDate to startDate + (durMin * minutes)

tell application "Calendar"
    if calName is not "" then
        set theCal to calendar calName
    else
        -- Prefer a calendar that isn't the on-Mac-only local one, so the event
        -- has a chance of syncing (iCloud/Exchange/Google). Fall back to the
        -- first writable calendar if we can't tell them apart.
        set theCal to missing value
        repeat with c in calendars
            if (writable of c) is true then
                set cn to title of c
                if cn is not "Calendar" and cn does not contain "Reminders" then
                    set theCal to c
                    exit repeat
                end if
            end if
        end repeat
        if theCal is missing value then
            set theCal to first calendar whose writable is true
        end if
    end if
    if allDay is "1" then
        set newEvent to make new event at end of events of theCal with properties {summary:theTitle, start date:startDate, end date:endDate, allday event:true, description:theNotes}
    else
        set newEvent to make new event at end of events of theCal with properties {summary:theTitle, start date:startDate, end date:endDate, description:theNotes}
    end if
    -- Return the calendar name so the skill can tell the user where it landed.
    return title of theCal
end tell
'''


def _parse_when(date_str: str, time_str: str) -> tuple[_dt.datetime, bool] | None:
    """Parse a date (+optional time) into (datetime, is_all_day). None if bad."""
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip()
    try:
        d = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    if not time_str:
        # No time given -> all-day event, anchored at 00:00.
        return _dt.datetime.combine(d, _dt.time(0, 0)), True
    for fmt in ("%H:%M", "%H.%M"):
        try:
            t = _dt.datetime.strptime(time_str, fmt).time()
            return _dt.datetime.combine(d, t), False
        except ValueError:
            continue
    return None


class CreateCalendarEventSkill(Skill):
    name = "create_calendar_event"
    description = (
        "Create a calendar event (macOS Calendar, syncs to iPhone via iCloud). "
        "Give a title, a date as 'YYYY-MM-DD', and optionally a time 'HH:MM' "
        "(24h; omit for an all-day event), a duration in minutes, and notes."
    )
    parameters: dict[str, Any] = {
        "title": {"type": "string", "description": "Event title."},
        "date": {"type": "string", "description": "Date as YYYY-MM-DD."},
        "time": {
            "type": "string",
            "description": "Start time HH:MM (24h). Omit for an all-day event.",
        },
        "duration_minutes": {
            "type": "integer",
            "description": "Length in minutes (default 60). Ignored for all-day.",
        },
        "notes": {"type": "string", "description": "Optional notes/description."},
    }
    required = ["title", "date"]

    def run(
        self,
        title: str = "",
        date: str = "",
        time: str = "",  # noqa: A002
        duration_minutes: int = 60,
        notes: str = "",
        **kwargs: Any,
    ) -> str:
        title = (title or "").strip()
        if not title:
            return "[error] The event needs a title."

        if platform.system() != "Darwin" or not shutil.which("osascript"):
            return (
                "[error] Creating calendar events is macOS-only (via Calendar.app). "
                "On this system, add it manually or use an .ics-based workflow."
            )

        parsed = _parse_when(date, time)
        if parsed is None:
            return (
                f"[error] I couldn't read the date/time. Use date 'YYYY-MM-DD' "
                f"and time 'HH:MM' (got date={date!r}, time={time!r})."
            )
        when, all_day = parsed

        try:
            dur = max(1, int(duration_minutes))
        except (ValueError, TypeError):
            dur = 60

        # Pass everything through the environment so no free text touches the
        # AppleScript source (injection-safe).
        env = dict(os.environ)
        env.update(
            {
                "JARVIS_EVT_TITLE": title,
                "JARVIS_EVT_NOTES": (notes or "").strip(),
                "JARVIS_EVT_CAL": os.getenv("JARVIS_CALENDAR", "").strip(),
                "JARVIS_EVT_Y": str(when.year),
                "JARVIS_EVT_MO": str(when.month),
                "JARVIS_EVT_D": str(when.day),
                "JARVIS_EVT_H": str(when.hour),
                "JARVIS_EVT_MI": str(when.minute),
                "JARVIS_EVT_DUR": str(dur),
                "JARVIS_EVT_ALLDAY": "1" if all_day else "0",
            }
        )
        try:
            proc = subprocess.run(  # noqa: S603
                ["osascript", "-e", _CREATE_SCRIPT],
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return "[error] Calendar took too long to respond."
        except Exception as exc:  # noqa: BLE001
            return f"[error] Couldn't create the event: {exc}"

        if proc.returncode != 0:
            detail = (proc.stderr or "").strip()
            # A wrong calendar name is the most common failure.
            if "calendar" in detail.lower():
                return (
                    f"[error] Couldn't find the target calendar. Set "
                    f"JARVIS_CALENDAR to a calendar name, or leave it blank. {detail}"
                )
            return f"[error] Calendar refused the event: {detail}"

        used_cal = (proc.stdout or "").strip()
        when_str = (
            when.strftime("%A, %d %B")
            if all_day
            else when.strftime("%A, %d %B at %H:%M")
        )
        kind = "all-day event" if all_day else "event"
        base = f"Added {kind} '{title}' on {when_str}"
        if used_cal:
            base += f" to the '{used_cal}' calendar"
        # The default local "Calendar" doesn't sync to iCloud/iPhone. Be honest.
        if used_cal == "Calendar":
            return (
                base + ". Note: that's an on-Mac calendar, so it won't sync to "
                "your iPhone. To sync, enable iCloud Calendar (System Settings → "
                "Apple ID → iCloud → Calendars) and set JARVIS_CALENDAR to your "
                "iCloud calendar name."
            )
        return base + ". It'll sync to your devices."
