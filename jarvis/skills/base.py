# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Skill base class and shared types.

A "skill" is something JARVIS can actually *do* (as opposed to just talk about):
tell the time, report system info, open an app, and so on. Each skill exposes
an OpenAI-style tool schema so the LLM can decide when to call it, and a plain
``run`` method so skills also work in offline mode.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Skill(ABC):
    """One capability JARVIS can invoke.

    Subclasses set ``name``, ``description`` and ``parameters`` (a JSON-schema
    dict of arguments) and implement ``run``.
    """

    name: str = ""
    description: str = ""
    # JSON-schema "properties" dict. Empty means the skill takes no arguments.
    parameters: dict[str, Any] = {}
    required: list[str] = []

    # Set by the registry when the skill is registered, so skills can reach
    # shared services (e.g. the confirmation gate). Optional for most skills.
    registry: Any = None

    def bind(self, registry: Any) -> None:
        """Called by the registry on registration. Override if you need it."""
        self.registry = registry

    @abstractmethod
    def run(self, **kwargs: Any) -> str:
        """Execute the skill and return a short, human-readable result string."""
        raise NotImplementedError

    def tool_schema(self) -> dict[str, Any]:
        """Return the OpenAI tool/function schema describing this skill."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required,
                },
            },
        }
