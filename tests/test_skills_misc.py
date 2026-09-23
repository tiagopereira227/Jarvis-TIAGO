# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Assorted skill logic: news XXE guard, shell allowlist, calendar parsing."""

from __future__ import annotations

import datetime as dt

import pytest

from jarvis.skills import news
from jarvis.skills.calendar_write import _parse_when
from jarvis.skills.system_control import _clamp_pct


def test_news_rejects_doctype_xxe():
    xxe = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY x "y">]><rss></rss>'
    with pytest.raises(ValueError):
        news._extract_titles(xxe, 5)


def test_news_parses_clean_rss():
    rss = b"<rss><channel><item><title>Hello</title></item></channel></rss>"
    assert news._extract_titles(rss, 5) == ["Hello"]


def test_news_parses_atom():
    atom = (
        b'<feed xmlns="http://www.w3.org/2005/Atom">'
        b"<entry><title>Atom Item</title></entry></feed>"
    )
    assert news._extract_titles(atom, 5) == ["Atom Item"]


def test_clamp_pct():
    assert _clamp_pct(150) == 100
    assert _clamp_pct(-5) == 0
    assert _clamp_pct(42) == 42
    assert _clamp_pct("nope") is None


def test_calendar_parse_when_timed():
    w, all_day = _parse_when("2026-10-01", "14:30")
    assert w == dt.datetime(2026, 10, 1, 14, 30)
    assert all_day is False


def test_calendar_parse_when_allday():
    w, all_day = _parse_when("2026-10-01", "")
    assert all_day is True
    assert w.date() == dt.date(2026, 10, 1)


def test_calendar_parse_when_bad():
    assert _parse_when("nope", "14:30") is None
    assert _parse_when("2026-10-01", "99:99") is None


def test_shell_allowlist_blocks_unknown(registry):
    out = registry.dispatch("run_command", {"command": "curl http://evil"})
    assert out.startswith("[error]") and "allowlist" in out


def test_shell_readonly_runs(registry):
    out = registry.dispatch("run_command", {"command": "echo hello-tests"})
    assert "hello-tests" in out and not registry.gate.has_pending


def test_shell_mutating_requires_confirmation(registry):
    out = registry.dispatch("run_command", {"command": "rm somefile"})
    assert registry.gate.has_pending and "sure" in out.lower()
    registry.gate.resolve("no")  # cancel; nothing deleted
