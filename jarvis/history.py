# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Persistent conversation history for the dashboard.

Appends each turn (who + text + timestamp) to a JSON-Lines file under the
JARVIS dir, so past conversations survive restarts and can be shown in the HUD.
JSON-Lines (one object per line) makes appends cheap and reads simple, and a
cap keeps the file bounded.

Best-effort: a write failure is swallowed (history is a convenience, never
allowed to break a reply). Reads tolerate malformed lines.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

# Keep at most this many turns on disk; older ones are trimmed on write.
_MAX_TURNS = 500


def _path() -> Path:
    base = os.getenv("JARVIS_STORE_DIR")
    root = Path(base).expanduser() if base else Path.home() / ".jarvis"
    return root / "history.jsonl"


class History:
    """Append-only conversation log with a bounded size."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _path()

    def add(self, who: str, text: str) -> None:
        """Record a turn. ``who`` is 'user' or 'jarvis'. Never raises."""
        text = (text or "").strip()
        if not text:
            return
        rec = {
            "t": _dt.datetime.now().isoformat(timespec="seconds"),
            "who": who,
            "text": text,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except OSError:
            return
        self._trim()

    def recent(self, limit: int = 50) -> list[dict]:
        """Return the most recent turns (oldest first), up to ``limit``."""
        rows = self._read_all()
        return rows[-max(0, limit):]

    def clear(self) -> int:
        rows = self._read_all()
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass
        return len(rows)

    # -- internals ----------------------------------------------------------

    def _read_all(self) -> list[dict]:
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                out = []
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # skip a corrupt line rather than fail
                    if isinstance(obj, dict) and "text" in obj:
                        out.append(obj)
                return out
        except FileNotFoundError:
            return []
        except OSError:
            return []

    def _trim(self) -> None:
        rows = self._read_all()
        if len(rows) <= _MAX_TURNS:
            return
        keep = rows[-_MAX_TURNS:]
        try:
            tmp = self._path.with_suffix(".jsonl.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                for r in keep:
                    fh.write(json.dumps(r) + "\n")
            os.replace(tmp, self._path)
        except OSError:
            pass
