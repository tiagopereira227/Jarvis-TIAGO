# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Cross-session memory: facts JARVIS remembers about you between runs.

A small JSON store under the JARVIS dir (~/.jarvis/memory.json by default).
Facts are short strings ("prefers metric units", "works at Feedzai"). On
startup they're injected into the system prompt so JARVIS actually uses what it
knows, and the `remember` skill lets you add to them mid-conversation.

Known ceiling: this is a flat list of facts with a cap, not a semantic memory.
It won't summarize long histories or retrieve by relevance — every fact is
always in the prompt. That's fine for a handful of personal facts; a vector
store is the upgrade path if it ever needs to scale.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Cap so the injected prompt can't grow without bound.
_MAX_FACTS = 50


def _store_path() -> Path:
    base = os.getenv("JARVIS_STORE_DIR")
    root = Path(base).expanduser() if base else Path.home() / ".jarvis"
    return root / "memory.json"


class Memory:
    """A flat, persistent list of short facts about the user."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _store_path()
        self._facts: list[str] = self._load()

    def _load(self) -> list[str]:
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError):
            return []  # corrupt store -> start clean rather than crash
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
        return []

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self._facts, fh, indent=2)
            os.replace(tmp, self._path)  # atomic
        except OSError:
            pass  # memory is a convenience; never break on a write failure

    def facts(self) -> list[str]:
        return list(self._facts)

    def add(self, fact: str) -> bool:
        """Add a fact. Returns False if empty or a duplicate."""
        fact = (fact or "").strip()
        if not fact:
            return False
        # Case-insensitive dedupe.
        if any(fact.lower() == f.lower() for f in self._facts):
            return False
        self._facts.append(fact)
        # Keep only the most recent _MAX_FACTS.
        if len(self._facts) > _MAX_FACTS:
            self._facts = self._facts[-_MAX_FACTS:]
        self._save()
        return True

    def forget(self, needle: str) -> int:
        """Remove facts containing ``needle`` (case-insensitive). Returns count."""
        needle = (needle or "").strip().lower()
        if not needle:
            return 0
        before = len(self._facts)
        self._facts = [f for f in self._facts if needle not in f.lower()]
        removed = before - len(self._facts)
        if removed:
            self._save()
        return removed

    def clear(self) -> int:
        n = len(self._facts)
        self._facts = []
        self._save()
        return n

    def as_prompt_block(self) -> str:
        """Render facts for injection into the system prompt, or '' if none."""
        if not self._facts:
            return ""
        lines = "\n".join(f"- {f}" for f in self._facts)
        return (
            "\nThings you know about the user (from memory; use them naturally "
            "when relevant, don't recite them):\n" + lines + "\n"
        )
