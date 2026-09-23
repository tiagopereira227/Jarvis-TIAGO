# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Shared pytest fixtures and hermetic-environment setup.

Every test runs against a temp store dir and with no API key, so tests never
touch the real ~/.jarvis, never hit the network, and never depend on the
developer's .env. A test that needs an online brain should skip rather than
call out.
"""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Isolate every test: temp store dir, no API keys, no .env leakage."""
    tmp = tempfile.mkdtemp(prefix="jarvis-test-")
    monkeypatch.setenv("JARVIS_STORE_DIR", tmp)
    # Force offline mode regardless of any real key in the environment/.env.
    monkeypatch.delenv("JARVIS_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Neutralise dotenv so a real .env can't override the above during tests.
    import jarvis.config as config

    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    yield


@pytest.fixture
def registry():
    """A fresh default registry (offline; all skills, incl. auto-discovered)."""
    from jarvis.skills import default_registry

    return default_registry()
