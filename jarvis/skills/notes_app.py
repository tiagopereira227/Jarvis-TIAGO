# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Write to the macOS Notes.app (syncs to iPhone via iCloud).

Unlike the plain-text notes in notes.py (a local ~/.jarvis/notes.txt), this
writes real notes into Notes.app. If your Notes are on iCloud, they sync to your
iPhone automatically — same trick as the calendar/reminders skills.

Two actions:
- create a new note (title + body), and
- append a line to an existing note found by title — so "I write, JARVIS writes
  back into the same note" works: repeated appends land in one running note.

macOS only (AppleScript). Low-risk (a note, not an outbound message), so it runs
directly without the confirmation gate. Title/body are passed via environment
variables (read with `system attribute`), never string-interpolated into the
script, so their contents can't break out or inject.

Note on formatting: Notes.app stores note bodies as HTML. We convert newlines
to <br> and escape &/</> so plain text renders correctly and can't inject HTML.
"""

from __future__ import annotations

import html
import os
import platform
import shutil
import subprocess
from typing import Any

from .base import Skill

# Create a new note. Body arrives as pre-built HTML in JARVIS_NOTE_BODY.
# Inputs come in through environment variables, but we read them via
# `do shell script "printf %s ..."` rather than `system attribute`. That matters
# for encoding: `system attribute` decodes env vars with the legacy Mac Roman
# codec, which mangles UTF-8 accents (ç -> √ß). `do shell script` returns UTF-8
# text correctly, so Portuguese and other non-ASCII text lands intact.
_CREATE_SCRIPT = r'''
set theTitle to (do shell script "printf %s \"$JARVIS_NOTE_TITLE\"")
set theBodyHTML to (do shell script "printf %s \"$JARVIS_NOTE_BODY\"")
set folderName to (do shell script "printf %s \"$JARVIS_NOTE_FOLDER\"")
tell application "Notes"
    if folderName is "" then
        make new note with properties {name:theTitle, body:theBodyHTML}
    else
        tell folder folderName
            make new note with properties {name:theTitle, body:theBodyHTML}
        end tell
    end if
end tell
return "ok"
'''

# Append a line to the first note whose name matches the title. If none exists,
# report "notfound" so the skill can fall back to creating one.
_APPEND_SCRIPT = r'''
set theTitle to (do shell script "printf %s \"$JARVIS_NOTE_TITLE\"")
set theLineHTML to (do shell script "printf %s \"$JARVIS_NOTE_BODY\"")
tell application "Notes"
    set matches to (notes whose name is theTitle)
    if (count of matches) is 0 then
        return "notfound"
    end if
    set theNote to item 1 of matches
    set body of theNote to (body of theNote) & "<br>" & theLineHTML
end tell
return "ok"
'''


def _mac_ok() -> bool:
    return platform.system() == "Darwin" and shutil.which("osascript") is not None


def _to_html(text: str) -> str:
    """Escape text for a Notes HTML body and turn newlines into <br>."""
    return html.escape(text or "").replace("\n", "<br>")


def _run(script: str, env_extra: dict[str, str]) -> tuple[bool, str]:
    env = dict(os.environ, **env_extra)
    try:
        proc = subprocess.run(  # noqa: S603
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "Notes took too long to respond."
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or "").strip()
    return True, (proc.stdout or "").strip()


class NotesAppSkill(Skill):
    name = "notes_app"
    description = (
        "Write to the macOS Notes app (syncs to iPhone via iCloud). action "
        "'create' makes a new note (needs 'title', optional 'body'); action "
        "'append' adds a line to an existing note by 'title' (creates it if "
        "missing). Optional 'folder' for the Notes folder."
    )
    parameters: dict[str, Any] = {
        "action": {
            "type": "string",
            "enum": ["create", "append"],
            "description": "Create a new note or append to an existing one.",
        },
        "title": {"type": "string", "description": "Note title (used to find it for append)."},
        "body": {"type": "string", "description": "Text to write (the note body, or the line to append)."},
        "folder": {"type": "string", "description": "Optional Notes folder name."},
    }
    required = ["action", "title"]

    def run(
        self,
        action: str = "",
        title: str = "",
        body: str = "",
        folder: str = "",
        **kwargs: Any,
    ) -> str:
        action = (action or "").strip().lower()
        title = (title or "").strip()
        if action not in ("create", "append"):
            return "[error] action must be 'create' or 'append'."
        if not title:
            return "[error] The note needs a title."
        if not _mac_ok():
            return "[error] Notes is macOS-only (via Notes.app)."

        if action == "create":
            ok, out = _run(
                _CREATE_SCRIPT,
                {
                    "JARVIS_NOTE_TITLE": title,
                    "JARVIS_NOTE_BODY": _to_html(body),
                    "JARVIS_NOTE_FOLDER": (folder or "").strip(),
                },
            )
            if not ok:
                if "folder" in out.lower():
                    return f"[error] Couldn't find that Notes folder. {out}"
                return f"[error] Couldn't create the note: {out}"
            return f"Created note '{title}' in Notes. It'll sync to your devices."

        # append
        if not body.strip():
            return "[error] There's nothing to append."
        ok, out = _run(
            _APPEND_SCRIPT,
            {"JARVIS_NOTE_TITLE": title, "JARVIS_NOTE_BODY": _to_html(body)},
        )
        if ok and out == "notfound":
            # No such note yet — create it with this line as the first body.
            ok2, out2 = _run(
                _CREATE_SCRIPT,
                {
                    "JARVIS_NOTE_TITLE": title,
                    "JARVIS_NOTE_BODY": _to_html(body),
                    "JARVIS_NOTE_FOLDER": (folder or "").strip(),
                },
            )
            if not ok2:
                return f"[error] Couldn't create the note: {out2}"
            return f"Started note '{title}' in Notes with your line. It'll sync."
        if not ok:
            return f"[error] Couldn't append to the note: {out}"
        return f"Added your line to note '{title}'."
