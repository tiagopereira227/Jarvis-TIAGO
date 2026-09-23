# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""A tiny arm-then-confirm gate for dangerous actions.

Some skills (shutting the machine down, restarting it) must never fire on a
single call — an over-eager LLM or a misheard voice command shouldn't be able
to power off your computer. So those skills don't act directly: they *arm* a
pending action here and return a question. The action only runs when
``confirm`` is later called with an affirmative answer.

This is enforced in code, not merely requested in the prompt: the destructive
command lives inside the pending action's callable and there is no other path
to it, so the confirmation step cannot be skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class _Pending:
    description: str  # human-readable, e.g. "shut down the computer"
    action: Callable[[], str]  # runs the real thing, returns a result string


# Words we accept as a clear "yes". Anything else cancels — for a destructive
# action, "only proceed on an explicit yes" is the safe default.
_AFFIRMATIVE = {
    "yes", "y", "yeah", "yep", "yup", "confirm", "confirmed", "do it",
    "go ahead", "affirmative", "proceed", "sure", "ok", "okay",
}


class ConfirmationGate:
    """Holds at most one pending action awaiting confirmation."""

    def __init__(self) -> None:
        self._pending: _Pending | None = None

    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    def pending_description(self) -> str | None:
        return self._pending.description if self._pending else None

    def arm(self, description: str, action: Callable[[], str]) -> str:
        """Stage an action and return the confirmation prompt."""
        self._pending = _Pending(description=description, action=action)
        return (
            f"Are you sure you want to {description}? "
            "This will not happen until you confirm. Say 'yes' to proceed, "
            "or anything else to cancel."
        )

    @staticmethod
    def is_affirmative(answer: str) -> bool:
        return answer.strip().lower().rstrip(".!") in _AFFIRMATIVE

    def resolve(self, answer: str) -> str:
        """Confirm or cancel the pending action based on ``answer``."""
        if self._pending is None:
            return "There's nothing awaiting confirmation."
        pending = self._pending
        self._pending = None  # clear first, so a failing action can't re-fire
        if self.is_affirmative(answer):
            return pending.action()
        return f"Cancelled: I will not {pending.description}."

    def cancel(self) -> str:
        if self._pending is None:
            return "There's nothing to cancel."
        desc = self._pending.description
        self._pending = None
        return f"Cancelled: I will not {desc}."
