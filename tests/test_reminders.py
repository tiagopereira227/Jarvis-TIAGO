# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Duration parsing for timers — the bit that had a real double-counting bug."""

from __future__ import annotations

from jarvis.skills.reminders import _parse_duration


def test_bare_seconds():
    assert _parse_duration("90") == 90


def test_units():
    assert _parse_duration("5m") == 300
    assert _parse_duration("1h30m") == 5400
    assert _parse_duration("2h") == 7200


def test_spelled_out_not_double_counted():
    # Regression: "2 min" once counted as 240 (m + min). Must be 120.
    assert _parse_duration("2 min") == 120
    assert _parse_duration("30 sec") == 30
    assert _parse_duration("1 hour") == 3600


def test_invalid():
    assert _parse_duration("banana") is None
    assert _parse_duration("") is None
