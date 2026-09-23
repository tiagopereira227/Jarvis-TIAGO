# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Timer and alarm skills.

Timers count down a duration; alarms fire at a wall-clock time. Both run on
background threads inside the JARVIS process and, when they fire, print a
message and play a short chime.

Persistence: pending timers and alarms are written to a small JSON store and
re-armed when JARVIS starts. Because items are stored by their absolute
``fire_at`` time (not a remaining countdown), a restart recomputes the delay
from the wall clock. On load:
- an alarm whose time has passed fires immediately (you'd want to know);
- a timer whose end has passed is dropped (a finished countdown is stale).

Known ceiling: the store is a single JSON file with no locking across multiple
concurrent JARVIS processes — last writer wins. Fine for one interactive
assistant; a multi-process setup would want a real store.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any

from .base import Skill

_ids = count(1)  # simple monotonic ids for timers/alarms


def default_store_path() -> Path:
    """Where reminders are persisted. Overridable via JARVIS_STORE_DIR."""
    base = os.getenv("JARVIS_STORE_DIR")
    root = Path(base).expanduser() if base else Path.home() / ".jarvis"
    return root / "reminders.json"


def _chime() -> None:
    """Play a short, best-effort notification sound. Never raises."""
    try:
        system = platform.system()
        if system == "Darwin" and shutil.which("afplay"):
            subprocess.run(  # noqa: S603
                ["afplay", "/System/Library/Sounds/Glass.aiff"], check=False
            )
        elif system == "Windows":
            import winsound  # type: ignore

            winsound.MessageBeep()
        else:
            # Terminal bell as a universal fallback.
            print("\a", end="", flush=True)
    except Exception:  # noqa: BLE001
        pass


@dataclass
class _Scheduled:
    id: int
    label: str
    fire_at: _dt.datetime
    timer: threading.Timer = field(repr=False)
    kind: str = "timer"  # "timer" | "alarm"


class _Scheduler:
    """Shared store of pending timers/alarms, keyed by id, persisted to disk."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._items: dict[int, _Scheduled] = {}
        self._lock = threading.RLock()  # reentrant: fire() -> _save() re-locks
        self._store_path = store_path or default_store_path()
        self._loaded = False  # guard so load() runs at most once

    # -- Public API ---------------------------------------------------------

    def schedule(self, kind: str, label: str, delay_seconds: float) -> _Scheduled:
        fire_at = _dt.datetime.now() + _dt.timedelta(seconds=delay_seconds)
        item = self._arm(next(_ids), kind, label, fire_at, delay_seconds)
        self._save()
        return item

    def cancel(self, item_id: int) -> bool:
        with self._lock:
            item = self._items.pop(item_id, None)
            if item is None:
                return False
            item.timer.cancel()
        self._save()
        return True

    def list(self) -> list[_Scheduled]:
        with self._lock:
            return sorted(self._items.values(), key=lambda i: i.fire_at)

    def load(self) -> int:
        """Re-arm persisted reminders. Returns how many were restored/fired.

        Past-due alarms fire right away; past-due timers are dropped as stale.
        Idempotent: only the first call loads; later calls are a no-op returning
        0, so an explicit startup load and the lazy load can't double up.
        """
        with self._lock:
            if self._loaded:
                return 0
            self._loaded = True

        data = self._read_file()
        if not data:
            return 0

        # Keep our id counter ahead of anything we load, so new ids don't clash.
        global _ids
        max_id = max((int(r.get("id", 0)) for r in data), default=0)
        if max_id:
            _ids = count(max_id + 1)

        now = _dt.datetime.now()
        restored = 0
        for rec in data:
            try:
                kind = rec["kind"]
                label = rec.get("label", "")
                fire_at = _dt.datetime.fromisoformat(rec["fire_at"])
                item_id = int(rec["id"])
            except (KeyError, ValueError, TypeError):
                continue  # skip malformed records rather than crash startup

            delay = (fire_at - now).total_seconds()
            if delay <= 0:
                # Timer that already elapsed while we were off = stale, drop it.
                if kind == "timer":
                    continue
                # Alarm in the past = fire immediately so it isn't silently lost.
                delay = 0.0
            self._arm(item_id, kind, label, fire_at, delay)
            restored += 1

        self._save()  # rewrite without the dropped/expired entries
        return restored

    # -- Internals ----------------------------------------------------------

    def _arm(
        self,
        item_id: int,
        kind: str,
        label: str,
        fire_at: _dt.datetime,
        delay_seconds: float,
    ) -> _Scheduled:
        def fire() -> None:
            with self._lock:
                self._items.pop(item_id, None)
            self._save()
            noun = "Alarm" if kind == "alarm" else "Timer"
            suffix = f": {label}" if label else ""
            print(f"\n\U0001f514 {noun} finished{suffix}\n", flush=True)
            _chime()

        t = threading.Timer(max(0.0, delay_seconds), fire)
        t.daemon = True  # don't keep the process alive just for a pending timer
        item = _Scheduled(id=item_id, label=label, fire_at=fire_at, timer=t, kind=kind)
        with self._lock:
            self._items[item_id] = item
        t.start()
        return item

    def _read_file(self) -> list[dict[str, Any]]:
        try:
            with self._store_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError):
            return []  # corrupt/unreadable store: start clean rather than crash
        return data if isinstance(data, list) else []

    def _save(self) -> None:
        """Persist current items atomically. Best-effort; never raises."""
        with self._lock:
            records = [
                {
                    "id": it.id,
                    "kind": it.kind,
                    "label": it.label,
                    "fire_at": it.fire_at.isoformat(),
                }
                for it in self._items.values()
            ]
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._store_path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(records, fh, indent=2)
            os.replace(tmp, self._store_path)  # atomic swap on the same fs
        except OSError:
            pass  # persistence is a convenience; don't break the assistant


# One scheduler shared by all reminder skills in a registry. Created lazily and
# stashed on the registry so timers and alarms see the same set. On first
# creation it loads any persisted reminders and re-arms them; the number
# restored is recorded on the registry as ``reminders_restored`` so the app can
# report it at startup. load() is idempotent, so whichever call happens first
# (this lazy one or an explicit startup load) does the work and the other is a
# no-op.
def _scheduler_for(registry: Any) -> _Scheduler:
    sched = getattr(registry, "_scheduler", None)
    if sched is None:
        store = getattr(registry, "reminder_store_path", None)
        sched = _Scheduler(store_path=store)
        setattr(registry, "_scheduler", sched)
        restored = sched.load()
        setattr(registry, "reminders_restored", restored)
    return sched


def _parse_duration(text: str) -> float | None:
    """Parse '90', '90s', '5m', '1h30m', '2 min' into seconds. None if invalid."""
    import re

    text = text.strip().lower()
    if not text:
        return None
    # Bare number = seconds.
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    # One pass over all "<number><unit>" chunks. Alternatives are ordered
    # longest-first so "min"/"hours" win over the single-letter "m"/"h" and we
    # never match the same text twice (which would double-count "2 min").
    unit_seconds = {
        "hours": 3600, "hour": 3600, "hrs": 3600, "hr": 3600, "h": 3600,
        "mins": 60, "min": 60, "m": 60,
        "secs": 1, "sec": 1, "s": 1,
    }
    pattern = r"(\d+(?:\.\d+)?)\s*(hours|hour|hrs|hr|mins|min|secs|sec|[hms])"
    total = 0.0
    matched = False
    for value, unit in re.findall(pattern, text):
        matched = True
        total += float(value) * unit_seconds[unit]
    return total if matched else None


class TimerSkill(Skill):
    name = "set_timer"
    description = (
        "Set a countdown timer. Give a duration like '90s', '5m', '1h30m', or "
        "a plain number of seconds. Optionally give a label."
    )
    parameters: dict[str, Any] = {
        "duration": {
            "type": "string",
            "description": "Duration, e.g. '10m', '90s', '1h30m', or seconds as a number.",
        },
        "label": {"type": "string", "description": "Optional name for the timer."},
    }
    required = ["duration"]

    def run(self, duration: str = "", label: str = "", **kwargs: Any) -> str:
        seconds = _parse_duration(str(duration))
        if seconds is None or seconds <= 0:
            return f"[error] I couldn't understand the duration {duration!r}."
        item = _scheduler_for(self.registry).schedule("timer", label.strip(), seconds)
        mins, secs = divmod(int(seconds), 60)
        hrs, mins = divmod(mins, 60)
        pretty = ", ".join(
            f"{v} {u}" for v, u in ((hrs, "h"), (mins, "m"), (secs, "s")) if v
        ) or "0s"
        named = f" ('{label.strip()}')" if label.strip() else ""
        return f"Timer #{item.id}{named} set for {pretty}."


class AlarmSkill(Skill):
    name = "set_alarm"
    description = (
        "Set an alarm for a specific clock time today (or tomorrow if that time "
        "has already passed). Time format 'HH:MM' in 24-hour, e.g. '07:30'."
    )
    parameters: dict[str, Any] = {
        "time": {
            "type": "string",
            "description": "Target time as 'HH:MM' (24-hour).",
        },
        "label": {"type": "string", "description": "Optional name for the alarm."},
    }
    required = ["time"]

    def run(self, time: str = "", label: str = "", **kwargs: Any) -> str:  # noqa: A002
        raw = str(time).strip()
        try:
            hh, mm = (int(p) for p in raw.split(":", 1))
            target_t = _dt.time(hour=hh, minute=mm)
        except (ValueError, TypeError):
            return f"[error] I couldn't read the time {raw!r}. Use 'HH:MM'."

        now = _dt.datetime.now()
        target = now.replace(
            hour=target_t.hour, minute=target_t.minute, second=0, microsecond=0
        )
        if target <= now:
            target += _dt.timedelta(days=1)  # already passed today -> tomorrow
        delay = (target - now).total_seconds()

        item = _scheduler_for(self.registry).schedule("alarm", label.strip(), delay)
        named = f" ('{label.strip()}')" if label.strip() else ""
        return (
            f"Alarm #{item.id}{named} set for "
            f"{target.strftime('%H:%M on %A')}."
        )


class ListRemindersSkill(Skill):
    name = "list_reminders"
    description = "List all pending timers and alarms."
    parameters: dict[str, Any] = {}
    required: list[str] = []

    def run(self, **kwargs: Any) -> str:
        items = _scheduler_for(self.registry).list()
        if not items:
            return "You have no pending timers or alarms."
        lines = []
        for it in items:
            when = it.fire_at.strftime("%H:%M:%S")
            label = f" — {it.label}" if it.label else ""
            lines.append(f"#{it.id} [{it.kind}] at {when}{label}")
        return "Pending:\n" + "\n".join(lines)


class CancelReminderSkill(Skill):
    name = "cancel_reminder"
    description = "Cancel a pending timer or alarm by its id number."
    parameters: dict[str, Any] = {
        "id": {"type": "integer", "description": "The id of the timer/alarm to cancel."}
    }
    required = ["id"]

    def run(self, id: int = 0, **kwargs: Any) -> str:  # noqa: A002
        try:
            item_id = int(id)
        except (ValueError, TypeError):
            return f"[error] {id!r} is not a valid id."
        if _scheduler_for(self.registry).cancel(item_id):
            return f"Cancelled #{item_id}."
        return f"I found no pending timer or alarm with id #{item_id}."
