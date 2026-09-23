# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Cross-session memory: add/dedupe/forget/clear, persistence, prompt block."""

from __future__ import annotations

from jarvis.memory import Memory


def test_add_and_facts():
    m = Memory()
    assert m.facts() == []
    assert m.add("likes tea") is True
    assert m.facts() == ["likes tea"]


def test_dedupe_case_insensitive():
    m = Memory()
    assert m.add("Likes Tea") is True
    assert m.add("likes tea") is False
    assert len(m.facts()) == 1


def test_empty_fact_rejected():
    m = Memory()
    assert m.add("   ") is False
    assert m.facts() == []


def test_forget_by_substring():
    m = Memory()
    m.add("works at Feedzai")
    m.add("likes tea")
    assert m.forget("feedzai") == 1
    assert m.facts() == ["likes tea"]


def test_clear():
    m = Memory()
    m.add("a")
    m.add("b")
    assert m.clear() == 2
    assert m.facts() == []


def test_persistence_across_instances():
    m1 = Memory()
    m1.add("remembers this")
    m2 = Memory()  # same store dir (temp, from fixture)
    assert "remembers this" in m2.facts()


def test_prompt_block_empty_when_no_facts():
    assert Memory().as_prompt_block() == ""


def test_prompt_block_lists_facts():
    m = Memory()
    m.add("name is Tiago")
    block = m.as_prompt_block()
    assert "name is Tiago" in block
