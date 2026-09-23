# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Mail / Messages / Reminders skills: registration, validation, gating.

These are macOS-AppleScript skills; tests exercise the pure logic (validation,
confirmation-gating, parsing) without actually driving Mail/Messages/Reminders.
"""

from __future__ import annotations

import datetime as dt

from jarvis.skills.reminders_app import _parse_due
from jarvis.skills.notes_app import _to_html


def test_new_skills_registered(registry):
    for name in ("read_mail", "send_mail", "send_message", "create_reminder",
                 "notes_app"):
        assert registry.has(name), name


def test_notes_app_validates(registry):
    # Bad action and missing title return errors, never raise.
    assert registry.dispatch("notes_app", {"action": "nope", "title": "x"}).startswith("[error]")
    assert registry.dispatch("notes_app", {"action": "create", "title": ""}).startswith("[error]")


def test_notes_html_escaping_prevents_injection():
    # HTML-special chars are escaped; newlines become <br>. No raw tags survive.
    out = _to_html('a & b < c > d\nnext "line"')
    assert "&amp;" in out and "&lt;" in out and "&gt;" in out
    assert "<br>" in out
    assert "<c" not in out  # the literal "< c" must not become a tag


def test_send_mail_validates_address(registry):
    out = registry.dispatch("send_mail", {"to": "not-an-email", "subject": "x", "body": "y"})
    assert out.startswith("[error]")
    assert not registry.gate.has_pending  # bad input never arms the gate


def test_send_mail_arms_gate_for_valid(registry):
    out = registry.dispatch(
        "send_mail", {"to": "friend@example.com", "subject": "Hi", "body": "Yo"}
    )
    # Either it armed the gate (macOS) or reported macOS-only (non-mac CI).
    if out.startswith("[error]"):
        assert "macOS" in out
    else:
        assert registry.gate.has_pending
        registry.gate.resolve("no")  # cancel; never actually sends


def test_send_message_requires_recipient_and_text(registry):
    assert registry.dispatch("send_message", {"to": "", "text": "hi"}).startswith("[error]")
    # Non-empty but on non-mac returns the macOS-only error; on mac it arms gate.
    out = registry.dispatch("send_message", {"to": "+351900000000", "text": "hi"})
    if not out.startswith("[error]"):
        assert registry.gate.has_pending
        registry.gate.resolve("no")


def test_reminder_requires_title(registry):
    assert registry.dispatch("create_reminder", {"title": ""}).startswith("[error]")


def test_reminder_due_parsing():
    assert _parse_due("2026-10-01", "14:30") == dt.datetime(2026, 10, 1, 14, 30)
    # Date-only defaults to 09:00.
    assert _parse_due("2026-10-01", "") == dt.datetime(2026, 10, 1, 9, 0)
    assert _parse_due("bad", "") is None
    assert _parse_due("2026-10-01", "99:99") is None
    assert _parse_due("", "") is None
