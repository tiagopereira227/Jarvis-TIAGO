# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Brain in offline mode: routing, streaming, and the confirmation flow."""

from __future__ import annotations

from jarvis.brain import Brain
from jarvis.config import Config


def _brain(registry):
    b = Brain(Config.load(), registry)
    assert b.online is False  # fixture forces offline
    return b


def test_offline_routes_time(registry):
    b = _brain(registry)
    out = b.respond("what time is it")
    assert "local time" in out.lower()


def test_offline_fallback_message(registry):
    b = _brain(registry)
    out = b.respond("ponder the meaning of life")
    assert "limited" in out.lower() or "no api key" in out.lower()


def test_respond_stream_concatenates_to_respond(registry):
    b = _brain(registry)
    chunks = list(b.respond_stream("what time is it"))
    assert "".join(chunks).strip()
    assert "local time" in "".join(chunks).lower()


def test_power_command_arms_gate_then_cancels(registry):
    b = _brain(registry)
    out = b.respond("shut down the computer")
    assert registry.gate.has_pending
    assert "sure" in out.lower()
    cancel = b.respond("no")
    assert not registry.gate.has_pending
    assert "cancel" in cancel.lower()


def test_power_command_confirm_would_run(registry, monkeypatch):
    # Replace the shutdown skill's command so "yes" doesn't power off the CI box.
    b = _brain(registry)
    b.respond("shut down the computer")
    assert registry.gate.has_pending
    # Swap the pending action for a harmless sentinel to prove yes fires it.
    ran = []
    registry.gate._pending.action = lambda: (ran.append(1), "did-it")[1]
    out = b.respond("yes")
    assert ran == [1] and out == "did-it"
