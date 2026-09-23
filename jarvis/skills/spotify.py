# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Spotify control.

Two layers, best-first:
1. Web API (spotify_web.py) — optional. When Spotify developer credentials are
   configured, "play <name>" searches and plays *any* track on your active
   device, on every platform. Falls through to local control if unset or if a
   call fails (e.g. no active device).
2. Local app control — zero-setup, drives the installed desktop app:
   - macOS: full control via AppleScript (play/pause/next/previous); a named
     play with no Web API opens a Spotify search URI.
   - Windows / Linux: transport via media keys / playerctl, plus "open" to
     launch the app or a spotify: URI.

So play-by-name works everywhere once the Web API is set up; without it, you
still get transport control and search-open locally.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import urllib.parse
from typing import Any

from .base import Skill
from .spotify_web import SpotifyWeb

_ACTIONS = {"play", "pause", "playpause", "next", "previous", "open"}


def _osascript(script: str) -> str:
    """Run AppleScript; return "" on success or an [error] string."""
    try:
        proc = subprocess.run(  # noqa: S603
            ["osascript", "-e", script], capture_output=True, text=True
        )
    except FileNotFoundError:
        return "[error] osascript not available."
    if proc.returncode != 0:
        return f"[error] Spotify control failed: {(proc.stderr or '').strip()}"
    return ""


class SpotifySkill(Skill):
    name = "spotify_control"
    description = (
        "Control Spotify. actions: 'play', 'pause', 'next', 'previous', or "
        "'open'. Pass 'query' with 'play' to search for and play a song, "
        "artist, or playlist by name."
    )
    parameters: dict[str, Any] = {
        "action": {
            "type": "string",
            "enum": ["play", "pause", "playpause", "next", "previous", "open"],
            "description": "What to do. Use 'play' with a query to start something.",
        },
        "query": {
            "type": "string",
            "description": "Optional song/artist/playlist name to search for and play.",
        },
    }
    required = ["action"]

    # Lazily-created Web API backend (shared across calls on this skill).
    _web: SpotifyWeb | None = None

    def _web_backend(self) -> SpotifyWeb:
        if self._web is None:
            self._web = SpotifyWeb()
        return self._web

    def run(self, action: str = "", query: str = "", **kwargs: Any) -> str:
        action = (action or "").strip().lower()
        query = (query or "").strip()
        if action not in _ACTIONS:
            return f"[error] Unknown action {action!r}. Use one of: {', '.join(sorted(_ACTIONS))}."

        # Playing by name: prefer the Web API (plays any track on any platform)
        # when it's configured. If it isn't set up or the call fails, fall
        # through to the local app control below.
        if query and action in ("play", "open"):
            web = self._web_backend()
            if web.configured:
                result = web.play_query(query)
                if result is not None:
                    return result
                # result is None -> Web API couldn't handle it; fall back.

        system = platform.system()
        if system == "Darwin":
            return self._run_macos(action, query)
        if system == "Windows":
            return self._run_windows(action, query)
        return self._run_linux(action, query)

    # -- macOS: AppleScript -------------------------------------------------

    def _run_macos(self, action: str, query: str) -> str:
        if query and action in ("play", "open"):
            # Try to resolve the query to a track URI and play it. If the
            # search yields nothing, fall back to opening a search in the app.
            uri = self._macos_first_track_uri(query)
            if uri:
                err = _osascript(f'tell application "Spotify" to play track "{uri}"')
                return err or f"Playing '{query}' on Spotify."
            # Fallback: open the app on a search results view.
            search_uri = "spotify:search:" + urllib.parse.quote(query)
            subprocess.run(["open", search_uri], check=False)  # noqa: S603
            return f"I couldn't auto-play '{query}', so I opened a search for it."

        scripts = {
            "play": 'tell application "Spotify" to play',
            "pause": 'tell application "Spotify" to pause',
            "playpause": 'tell application "Spotify" to playpause',
            "next": 'tell application "Spotify" to next track',
            "previous": 'tell application "Spotify" to previous track',
            "open": 'tell application "Spotify" to activate',
        }
        err = _osascript(scripts[action])
        if err:
            return err
        if action == "open":
            return "Spotify is open."
        return {
            "play": "Playing.",
            "pause": "Paused.",
            "playpause": "Toggled playback.",
            "next": "Skipped to the next track.",
            "previous": "Back to the previous track.",
        }[action]

    def _macos_first_track_uri(self, query: str) -> str | None:
        """Best-effort: ask the Spotify app to search and return a track URI.

        The Spotify AppleScript dictionary doesn't expose search directly, so
        this returns None; the caller then falls back to opening a search URI.
        Kept as a seam for a future Web API-backed lookup.
        """
        return None

    # -- Windows: media keys + URI ------------------------------------------

    def _run_windows(self, action: str, query: str) -> str:
        if action == "open" or (query and action == "play"):
            target = (
                "spotify:search:" + urllib.parse.quote(query)
                if query
                else "spotify:"
            )
            try:
                import os

                os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
            except Exception as exc:  # noqa: BLE001
                return f"[error] Could not open Spotify: {exc}"
            if query:
                return (
                    f"I opened a Spotify search for '{query}'. Auto-play by name "
                    "needs the Spotify Web API, which isn't set up."
                )
            return "Spotify is open."
        return self._media_key_windows(action)

    def _media_key_windows(self, action: str) -> str:
        # Virtual-key codes for media transport keys.
        vk = {
            "playpause": 0xB3,
            "play": 0xB3,  # no distinct "play"; toggle is closest
            "pause": 0xB3,
            "next": 0xB0,
            "previous": 0xB1,
        }.get(action)
        if vk is None:
            return f"[error] '{action}' isn't supported on Windows."
        try:
            import ctypes

            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)  # key down
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # key up
        except Exception as exc:  # noqa: BLE001
            return f"[error] Could not send media key: {exc}"
        return "Sent the media command to Spotify."

    # -- Linux: playerctl / URI --------------------------------------------

    def _run_linux(self, action: str, query: str) -> str:
        if action == "open" or (query and action == "play"):
            target = (
                "spotify:search:" + urllib.parse.quote(query) if query else "spotify"
            )
            launcher = shutil.which("xdg-open")
            if launcher is None:
                return "[error] No 'xdg-open' to launch Spotify."
            subprocess.run([launcher, target], check=False)  # noqa: S603
            if query:
                return f"Opened a Spotify search for '{query}'."
            return "Spotify is open."

        if shutil.which("playerctl") is None:
            return (
                "[error] Transport control on Linux needs 'playerctl' "
                "(install it, e.g. 'sudo apt install playerctl')."
            )
        cmd_arg = {
            "play": "play",
            "pause": "pause",
            "playpause": "play-pause",
            "next": "next",
            "previous": "previous",
        }[action]
        subprocess.run(  # noqa: S603
            ["playerctl", "--player=spotify", cmd_arg], check=False
        )
        return f"Sent '{action}' to Spotify."
