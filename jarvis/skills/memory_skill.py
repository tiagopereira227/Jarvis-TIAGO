# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Skills for the cross-session memory: remember, recall, forget.

These reach the shared Memory instance via the registry (registry.memory), so
the facts they change are the same ones injected into the system prompt.
"""

from __future__ import annotations

from typing import Any

from .base import Skill


def _memory(registry: Any) -> Any:
    """Get (or lazily create) the shared Memory on the registry."""
    mem = getattr(registry, "memory", None)
    if mem is None:
        from ..memory import Memory

        mem = Memory()
        setattr(registry, "memory", mem)
    return mem


class RememberSkill(Skill):
    name = "remember"
    description = (
        "Store a fact about the user for future sessions (e.g. a preference, "
        "name, or detail). Use when the user says to remember something."
    )
    parameters: dict[str, Any] = {
        "fact": {"type": "string", "description": "The fact to remember."}
    }
    required = ["fact"]

    def run(self, fact: str = "", **kwargs: Any) -> str:
        if _memory(self.registry).add(fact):
            return "I'll remember that."
        return "I already had that noted, or there was nothing to remember."


class RecallSkill(Skill):
    name = "recall"
    description = "List what JARVIS remembers about the user."
    parameters: dict[str, Any] = {}
    required: list[str] = []

    def run(self, **kwargs: Any) -> str:
        facts = _memory(self.registry).facts()
        if not facts:
            return "I don't have anything remembered yet."
        return "Here's what I know:\n" + "\n".join(f"- {f}" for f in facts)


class ForgetSkill(Skill):
    name = "forget"
    description = (
        "Forget remembered facts. Pass 'topic' to forget facts mentioning it, "
        "or 'all' set to true to clear everything."
    )
    parameters: dict[str, Any] = {
        "topic": {"type": "string", "description": "Text to match facts to forget."},
        "all": {"type": "boolean", "description": "Forget everything if true."},
    }
    required: list[str] = []

    def run(self, topic: str = "", all: bool = False, **kwargs: Any) -> str:  # noqa: A002
        mem = _memory(self.registry)
        if all:
            n = mem.clear()
            return f"Forgotten everything ({n} fact{'s' if n != 1 else ''})."
        n = mem.forget(topic)
        if n:
            return f"Forgotten {n} fact{'s' if n != 1 else ''} about '{topic}'."
        return f"I had nothing remembered about '{topic}'."
