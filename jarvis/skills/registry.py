# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Central registry that collects skills and dispatches calls to them."""

from __future__ import annotations

import json
from typing import Any

from .base import Skill
from .confirm import ConfirmationGate


class SkillRegistry:
    """Holds the available skills and routes tool calls to the right one."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        # Shared arm-then-confirm gate for dangerous actions (see confirm.py).
        self.gate = ConfirmationGate()

    def register(self, skill: Skill) -> None:
        if not skill.name:
            raise ValueError(f"Skill {skill!r} has no name")
        if skill.name in self._skills:
            raise ValueError(f"Duplicate skill name: {skill.name}")
        self._skills[skill.name] = skill
        skill.bind(self)  # give the skill access to shared services

    def has(self, name: str) -> bool:
        return name in self._skills

    def __len__(self) -> int:
        return len(self._skills)

    def names(self) -> list[str]:
        return sorted(self._skills)

    def autodiscover(self, package: str = "jarvis.skills") -> list[str]:
        """Import every module in ``package`` and register new Skill subclasses.

        Lets you drop a new skill file into jarvis/skills/ and have it picked up
        automatically — no need to edit default_registry(). A class is
        registered only if it is a concrete Skill subclass with a non-empty
        ``name`` that isn't already registered. Abstract bases (empty name,
        leading-underscore classes) and duplicates are skipped, so calling this
        after the hand-built defaults simply fills in anything new.

        Returns the list of skill names newly added. Import errors in one module
        are swallowed so a single bad file can't break the whole assistant.
        """
        import importlib
        import inspect
        import pkgutil

        added: list[str] = []
        try:
            pkg = importlib.import_module(package)
        except ImportError:
            return added

        for mod_info in pkgutil.iter_modules(pkg.__path__):
            name = mod_info.name
            if name.startswith("_"):
                continue  # private/helper modules
            try:
                module = importlib.import_module(f"{package}.{name}")
            except Exception:  # noqa: BLE001 - one bad module shouldn't break all
                continue
            for _, obj in inspect.getmembers(module, inspect.isclass):
                # Concrete Skill subclass defined in this module, with a name.
                if (
                    issubclass(obj, Skill)
                    and obj is not Skill
                    and obj.__module__ == module.__name__
                    and not obj.__name__.startswith("_")
                    and not inspect.isabstract(obj)
                    and getattr(obj, "name", "")
                    and not self.has(obj.name)
                ):
                    try:
                        self.register(obj())
                        added.append(obj.name)
                    except Exception:  # noqa: BLE001 - skip anything that won't instantiate
                        continue
        return added

    def tool_schemas(self) -> list[dict[str, Any]]:
        """All skills as OpenAI tool schemas, for handing to the LLM."""
        return [skill.tool_schema() for skill in self._skills.values()]

    def dispatch(self, name: str, arguments: dict[str, Any] | str | None = None) -> str:
        """Run the named skill. ``arguments`` may be a dict or JSON string.

        Returns a result string. Never raises for a bad call: it returns an
        error string instead, so a misbehaving LLM tool call can't crash the
        assistant.
        """
        skill = self._skills.get(name)
        if skill is None:
            return f"[error] Unknown skill: {name}"

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return f"[error] Could not parse arguments for {name}: {arguments!r}"
        if arguments is None:
            arguments = {}

        try:
            return skill.run(**arguments)
        except TypeError as exc:
            return f"[error] Bad arguments for {name}: {exc}"
        except Exception as exc:  # noqa: BLE001 - skills must never crash the loop
            return f"[error] {name} failed: {exc}"
