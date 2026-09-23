# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Skill system: base class, registry, and the built-in skills."""

from .base import Skill
from .builtin import default_registry
from .registry import SkillRegistry

__all__ = ["Skill", "SkillRegistry", "default_registry"]
