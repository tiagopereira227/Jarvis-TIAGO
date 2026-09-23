# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""The arm-then-confirm gate is safety-critical: a dangerous action must never
run without an explicit yes. These tests lock that behaviour in."""

from __future__ import annotations

from jarvis.skills.confirm import ConfirmationGate


def test_arm_does_not_run_action():
    ran = []
    g = ConfirmationGate()
    msg = g.arm("shut down the computer", lambda: ran.append(1) or "done")
    assert g.has_pending
    assert "shut down the computer" in msg
    assert ran == []  # merely arming must not execute


def test_yes_runs_action_once():
    ran = []
    g = ConfirmationGate()
    g.arm("do it", lambda: (ran.append(1), "RESULT")[1])
    out = g.resolve("yes")
    assert out == "RESULT"
    assert ran == [1]
    assert not g.has_pending  # cleared after firing


def test_non_yes_cancels_without_running():
    ran = []
    g = ConfirmationGate()
    g.arm("delete stuff", lambda: ran.append(1))
    out = g.resolve("no")
    assert ran == []
    assert "Cancelled" in out
    assert not g.has_pending


def test_ambiguous_answer_cancels():
    # Safety default: anything that isn't clearly affirmative cancels.
    g = ConfirmationGate()
    g.arm("x", lambda: "ran")
    assert "Cancelled" in g.resolve("maybe later")
    assert not g.has_pending


def test_affirmative_variants():
    for word in ("yes", "y", "yeah", "confirm", "do it", "ok", "sure"):
        assert ConfirmationGate.is_affirmative(word), word
    for word in ("no", "nope", "cancel", "later", ""):
        assert not ConfirmationGate.is_affirmative(word), word


def test_resolve_with_nothing_pending():
    g = ConfirmationGate()
    assert not g.has_pending
    # Should be harmless, not raise.
    out = g.resolve("yes")
    assert "nothing" in out.lower()


def test_action_failure_clears_pending():
    # Even if the action raises, the gate must not stay armed (no re-fire loop).
    def boom():
        raise RuntimeError("kaboom")

    g = ConfirmationGate()
    g.arm("risky", boom)
    try:
        g.resolve("yes")
    except RuntimeError:
        pass
    assert not g.has_pending
