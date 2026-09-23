# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Clipboard and notes skills.

- Clipboard reading is platform-specific and built for all three: macOS
  (pbpaste), Windows (PowerShell Get-Clipboard), and Linux (wl-paste / xclip /
  xsel). If none is available it degrades to a clear message.
- Notes are appended to a plain text file under the JARVIS store dir
  (~/.jarvis/notes.txt by default), which is fully cross-platform via pathlib.
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


def _store_dir() -> Path:
    base = os.getenv("JARVIS_STORE_DIR")
    return Path(base).expanduser() if base else Path.home() / ".jarvis"


def _notes_path() -> Path:
    return _store_dir() / "notes.txt"


def _read_clipboard() -> tuple[str | None, str | None]:
    """Return (text, error). Exactly one is non-None."""
    system = platform.system()
    try:
        if system == "Darwin":
            if not shutil.which("pbpaste"):
                return None, "pbpaste is unavailable."
            proc = subprocess.run(  # noqa: S603
                ["pbpaste"], capture_output=True, text=True
            )
            return proc.stdout, None
        if system == "Windows":
            exe = shutil.which("powershell") or shutil.which("powershell.exe")
            if not exe:
                return None, "PowerShell is unavailable."
            proc = subprocess.run(  # noqa: S603
                [exe, "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
            )
            # PowerShell adds a trailing newline; strip a single one.
            return proc.stdout.rstrip("\r\n"), None
        if system == "Linux":
            for tool, args in (
                ("wl-paste", ["wl-paste", "--no-newline"]),
                ("xclip", ["xclip", "-selection", "clipboard", "-o"]),
                ("xsel", ["xsel", "--clipboard", "--output"]),
            ):
                if shutil.which(tool):
                    proc = subprocess.run(args, capture_output=True, text=True)  # noqa: S603
                    return proc.stdout, None
            return None, "No clipboard tool found (install wl-clipboard, xclip, or xsel)."
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    return None, f"Clipboard reading isn't supported on {system}."


class ReadClipboardSkill(Skill):
    name = "read_clipboard"
    description = "Read and return the current contents of the system clipboard."
    parameters: dict[str, Any] = {}
    required: list[str] = []

    def run(self, **kwargs: Any) -> str:
        text, error = _read_clipboard()
        if error is not None:
            return f"[error] {error}"
        text = (text or "").strip()
        if not text:
            return "The clipboard is empty."
        # Keep the reply reasonable; note truncation rather than dumping a novel.
        if len(text) > 2000:
            return f"Clipboard (first 2000 of {len(text)} chars):\n{text[:2000]}"
        return f"Clipboard contents:\n{text}"


class AddNoteSkill(Skill):
    name = "add_note"
    description = "Save a note. It's appended with a timestamp to your notes file."
    parameters: dict[str, Any] = {
        "text": {"type": "string", "description": "The note to save."}
    }
    required = ["text"]

    def run(self, text: str = "", **kwargs: Any) -> str:
        text = (text or "").strip()
        if not text:
            return "[error] There's no note text to save."
        stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            path = _notes_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(f"[{stamp}] {text}\n")
        except OSError as exc:
            return f"[error] Couldn't save the note: {exc}"
        return "Noted."


class ReadNotesSkill(Skill):
    name = "read_notes"
    description = "Read back saved notes (most recent last). Optionally limit the count."
    parameters: dict[str, Any] = {
        "count": {
            "type": "integer",
            "description": "How many of the most recent notes to show. Default all.",
        }
    }
    required: list[str] = []

    def run(self, count: int | None = None, **kwargs: Any) -> str:
        path = _notes_path()
        try:
            lines = [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except FileNotFoundError:
            return "You have no saved notes yet."
        except OSError as exc:
            return f"[error] Couldn't read notes: {exc}"
        if not lines:
            return "You have no saved notes yet."
        if count is not None:
            try:
                n = max(1, int(count))
                lines = lines[-n:]
            except (ValueError, TypeError):
                pass
        return "Your notes:\n" + "\n".join(lines)
