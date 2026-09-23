# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Create to-dos in macOS Reminders.app (syncs to iPhone via iCloud).

Adds a reminder — with an optional due date/time — to Reminders.app. If your
Reminders are on iCloud, it syncs to your iPhone automatically, same trick as
the calendar skill.

macOS only (AppleScript). Low-risk (a to-do, not an outbound message), so it
runs directly without the confirmation gate. Title/notes are passed via
environment variables (injection-safe), never interpolated into the script.

Note: this is separate from the in-app countdown timers/alarms in
`reminders.py` — those are ephemeral session timers; this writes a real,
syncing to-do item.
"""

from __future__ import annotations

import datetime as _dt
import os
import platform
import shutil
import subprocess
from typing import Any

from .base import Skill

# Creates a reminder. If JARVIS_REM_DUE is "1", also sets a due date built from
# the Y/MO/D/H/MI parts. List name is optional (blank = default list).
_CREATE_SCRIPT = r'''
set theName to (system attribute "JARVIS_REM_NAME")
set theNotes to (system attribute "JARVIS_REM_NOTES")
set listName to (system attribute "JARVIS_REM_LIST")
set hasDue to (system attribute "JARVIS_REM_DUE")

tell application "Reminders"
    if listName is "" then
        set theList to default list
    else
        set theList to list listName
    end if
    if hasDue is "1" then
        set dd to current date
        set year of dd to (system attribute "JARVIS_REM_Y") as integer
        set month of dd to (system attribute "JARVIS_REM_MO") as integer
        set day of dd to (system attribute "JARVIS_REM_D") as integer
        set hours of dd to (system attribute "JARVIS_REM_H") as integer
        set minutes of dd to (system attribute "JARVIS_REM_MI") as integer
        set seconds of dd to 0
        make new reminder at end of reminders of theList with properties {name:theName, body:theNotes, due date:dd}
    else
        make new reminder at end of reminders of theList with properties {name:theName, body:theNotes}
    end if
end tell
return "ok"
'''


def _mac_ok() -> bool:
    return platform.system() == "Darwin" and shutil.which("osascript") is not None


def _parse_due(date_str: str, time_str: str) -> _dt.datetime | None:
    date_str = (date_str or "").strip()
    time_str = (time_str or "").strip()
    if not date_str:
        return None
    try:
        d = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None
    t = _dt.time(9, 0)  # default reminder time if only a date is given
    if time_str:
        for fmt in ("%H:%M", "%H.%M"):
            try:
                t = _dt.datetime.strptime(time_str, fmt).time()
                break
            except ValueError:
                continue
        else:
            return None
    return _dt.datetime.combine(d, t)


class CreateReminderSkill(Skill):
    name = "create_reminder"
    description = (
        "Add a to-do to macOS Reminders (syncs to iPhone via iCloud). Give a "
        "'title', and optionally a due 'date' (YYYY-MM-DD), 'time' (HH:MM), "
        "'notes', and a 'list' name."
    )
    parameters: dict[str, Any] = {
        "title": {"type": "string", "description": "What to be reminded of."},
        "date": {"type": "string", "description": "Optional due date YYYY-MM-DD."},
        "time": {"type": "string", "description": "Optional due time HH:MM (24h)."},
        "notes": {"type": "string", "description": "Optional notes."},
        "list": {"type": "string", "description": "Optional Reminders list name."},
    }
    required = ["title"]

    def run(
        self,
        title: str = "",
        date: str = "",
        time: str = "",  # noqa: A002
        notes: str = "",
        list: str = "",  # noqa: A002
        **kwargs: Any,
    ) -> str:
        title = (title or "").strip()
        if not title:
            return "[error] The reminder needs a title."
        if not _mac_ok():
            return "[error] Reminders is macOS-only (via Reminders.app)."

        due = None
        if (date or "").strip():
            due = _parse_due(date, time)
            if due is None:
                return (
                    f"[error] Couldn't read the due date/time "
                    f"(date={date!r}, time={time!r}). Use date 'YYYY-MM-DD'."
                )

        env = dict(os.environ)
        env.update(
            {
                "JARVIS_REM_NAME": title,
                "JARVIS_REM_NOTES": (notes or "").strip(),
                "JARVIS_REM_LIST": (list or "").strip(),
                "JARVIS_REM_DUE": "1" if due else "0",
            }
        )
        if due:
            env.update(
                {
                    "JARVIS_REM_Y": str(due.year),
                    "JARVIS_REM_MO": str(due.month),
                    "JARVIS_REM_D": str(due.day),
                    "JARVIS_REM_H": str(due.hour),
                    "JARVIS_REM_MI": str(due.minute),
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
            return "[error] Reminders took too long to respond."
        except Exception as exc:  # noqa: BLE001
            return f"[error] Couldn't create the reminder: {exc}"
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip()
            if "list" in detail.lower():
                return f"[error] Couldn't find that Reminders list. {detail}"
            return f"[error] Reminders refused: {detail}"

        when = f" (due {due.strftime('%a %d %b %H:%M')})" if due else ""
        return f"Added reminder '{title}'{when}. It'll sync to your devices."
