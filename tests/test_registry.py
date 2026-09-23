# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Skill registry: registration, dispatch safety, tool schemas, auto-discovery."""

from __future__ import annotations

import pytest

from jarvis.skills.base import Skill
from jarvis.skills.registry import SkillRegistry


class _Echo(Skill):
    name = "echo_test"
    description = "echo"
    parameters = {"text": {"type": "string", "description": "t"}}
    required = ["text"]

    def run(self, text: str = "", **k):
        return f"echo:{text}"


def test_register_and_dispatch():
    r = SkillRegistry()
    r.register(_Echo())
    assert r.has("echo_test")
    assert r.dispatch("echo_test", {"text": "hi"}) == "echo:hi"


def test_duplicate_registration_rejected():
    r = SkillRegistry()
    r.register(_Echo())
    with pytest.raises(ValueError):
        r.register(_Echo())


def test_dispatch_unknown_skill_returns_error_not_raise():
    r = SkillRegistry()
    out = r.dispatch("nope")
    assert out.startswith("[error]") and "Unknown skill" in out


def test_dispatch_bad_json_arguments():
    r = SkillRegistry()
    r.register(_Echo())
    out = r.dispatch("echo_test", "{not json")
    assert out.startswith("[error]")


def test_dispatch_unexpected_kwarg_returns_error():
    # A skill whose run() does NOT accept **kwargs must not raise on a stray
    # argument — the registry turns the TypeError into an error string.
    class Strict(Skill):
        name = "strict"
        description = "s"
        parameters: dict = {}
        required: list = []

        def run(self):  # no **kwargs on purpose
            return "ok"

    r = SkillRegistry()
    r.register(Strict())
    out = r.dispatch("strict", {"unexpected": "x"})
    assert out.startswith("[error]")


def test_skill_exception_is_contained():
    class Boom(Skill):
        name = "boom"
        description = "b"
        parameters: dict = {}
        required: list = []

        def run(self, **k):
            raise RuntimeError("nope")

    r = SkillRegistry()
    r.register(Boom())
    out = r.dispatch("boom")
    assert out.startswith("[error]") and "boom" in out


def test_tool_schemas_wellformed(registry):
    schemas = registry.tool_schemas()
    names = {s["function"]["name"] for s in schemas}
    assert names == set(registry.names())
    assert all(s["type"] == "function" for s in schemas)
    for s in schemas:
        fn = s["function"]
        assert isinstance(fn["parameters"]["properties"], dict)


def test_default_registry_has_expected_skills(registry):
    # A representative sample rather than an exact count, so adding a skill
    # doesn't require editing this test — but core ones must always be present.
    for name in (
        "get_time", "get_weather", "spotify_control", "set_timer",
        "shutdown_computer", "remember", "create_calendar_event",
    ):
        assert registry.has(name), name


def test_bind_gives_skill_the_registry():
    r = SkillRegistry()
    s = _Echo()
    r.register(s)
    assert s.registry is r
