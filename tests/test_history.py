# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Persistent conversation history store."""

from __future__ import annotations

from jarvis.history import History


def test_add_and_recent():
    h = History()
    h.add("user", "hello")
    h.add("jarvis", "Good day.")
    rows = h.recent()
    assert [r["who"] for r in rows] == ["user", "jarvis"]
    assert rows[0]["text"] == "hello"
    assert "t" in rows[0]  # timestamped


def test_empty_text_ignored():
    h = History()
    h.add("user", "   ")
    assert h.recent() == []


def test_persists_across_instances():
    h1 = History()
    h1.add("user", "remember this turn")
    h2 = History()
    assert any(r["text"] == "remember this turn" for r in h2.recent())


def test_recent_limit():
    h = History()
    for i in range(10):
        h.add("user", f"msg {i}")
    assert len(h.recent(limit=3)) == 3
    assert h.recent(limit=3)[-1]["text"] == "msg 9"  # newest kept, oldest first


def test_clear():
    h = History()
    h.add("user", "x")
    assert h.clear() >= 1
    assert h.recent() == []


def test_corrupt_line_tolerated(tmp_path):
    p = tmp_path / "history.jsonl"
    p.write_text('{"who":"user","text":"ok"}\nNOT JSON\n', encoding="utf-8")
    h = History(path=p)
    rows = h.recent()
    assert len(rows) == 1 and rows[0]["text"] == "ok"
