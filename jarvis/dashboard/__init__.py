# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""JARVIS dashboard: the Iron Man-style HUD web face.

A thin FastAPI + WebSocket server that reuses the existing Brain and
SkillRegistry. The browser shows live system vitals, an activity log, and a
command bar that drives the same assistant as the terminal.
"""
