# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Optional Spotify Web API backend: search a track by name and play it.

This is the upgrade over local app control — it can play *any* track by name on
your active Spotify device. It needs a Spotify developer app (client id/secret)
and a one-time OAuth login, plus the `spotipy` package. All optional: if any of
that is missing, ``available`` is False and the caller falls back to local
control.

Config (env or .env):
- SPOTIFY_CLIENT_ID
- SPOTIFY_CLIENT_SECRET
- SPOTIFY_REDIRECT_URI   (default http://127.0.0.1:8888/callback; must match the
                          redirect URI registered in your Spotify app. Spotify
                          rejects "localhost" as insecure — use 127.0.0.1.)

Token cache is stored under the JARVIS store dir so the OAuth login persists.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# spotipy is optional. Import guarded so the module loads without it.
try:
    import spotipy  # type: ignore
    from spotipy.oauth2 import SpotifyOAuth  # type: ignore
except Exception:  # noqa: BLE001
    spotipy = None  # type: ignore
    SpotifyOAuth = None  # type: ignore

# Scopes: read playback/devices, control playback, and read the user's profile
# (needed for the market/country so search returns region-appropriate tracks).
_SCOPE = (
    "user-read-playback-state user-modify-playback-state user-read-private"
)


def _store_dir() -> Path:
    base = os.getenv("JARVIS_STORE_DIR")
    return Path(base).expanduser() if base else Path.home() / ".jarvis"


class SpotifyWeb:
    """Thin wrapper over spotipy for search-and-play. Lazy-authenticates."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self._client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        # Spotify now rejects "localhost" as insecure but accepts the loopback
        # IP 127.0.0.1 over http. Default to that so the dashboard's redirect
        # URI is accepted without fuss.
        self._redirect = os.getenv(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        )

    @property
    def configured(self) -> bool:
        """True if the package is installed and credentials are present."""
        return (
            spotipy is not None
            and bool(self._client_id)
            and bool(self._client_secret)
        )

    def _connect(self) -> Any | None:
        if self._client is not None:
            return self._client
        if not self.configured:
            return None
        try:
            cache_dir = _store_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            auth = SpotifyOAuth(
                client_id=self._client_id,
                client_secret=self._client_secret,
                redirect_uri=self._redirect,
                scope=_SCOPE,
                cache_path=str(cache_dir / "spotify_token.json"),
                open_browser=True,
            )
            self._client = spotipy.Spotify(auth_manager=auth)
        except Exception:  # noqa: BLE001
            self._client = None
        return self._client

    def _pick_device_id(self, sp: Any) -> str | None:
        """Return a device id to play on, or None if truly none exist.

        A freshly opened Spotify app that has never played this session reports
        as a device but not the *active* one, so start_playback fails with "no
        active device". We look at the device list and pick one (preferring the
        active one, then a Computer, then whatever's there) so we can transfer
        playback to it explicitly.
        """
        try:
            devices = (sp.devices() or {}).get("devices") or []
        except Exception:  # noqa: BLE001
            return None
        if not devices:
            return None
        for d in devices:  # already-active device wins
            if d.get("is_active"):
                return d.get("id")
        for d in devices:  # then a desktop/computer
            if d.get("type", "").lower() == "computer":
                return d.get("id")
        return devices[0].get("id")  # otherwise the first available

    def _wake_macos_app(self) -> None:
        """Best-effort: nudge the local Spotify app so it registers a device."""
        import platform
        import shutil
        import subprocess

        if platform.system() != "Darwin" or not shutil.which("osascript"):
            return
        try:
            # Launch (if needed) and issue a play/pause so Spotify announces
            # itself as a device to the Web API.
            subprocess.run(  # noqa: S603
                ["osascript", "-e", 'tell application "Spotify" to activate'],
                capture_output=True,
            )
            subprocess.run(  # noqa: S603
                ["osascript", "-e", 'tell application "Spotify" to playpause'],
                capture_output=True,
            )
        except Exception:  # noqa: BLE001
            pass

    def _market(self, sp: Any) -> str | None:
        """The user's country, used to scope search to available tracks."""
        try:
            return (sp.me() or {}).get("country") or None
        except Exception:  # noqa: BLE001
            return None

    # Words that mark a non-original version. If the user didn't ask for one of
    # these, we push such results down so the original is preferred.
    _VARIANT_WORDS = (
        "remix", "live", "acoustic", "instrumental", "edit", "version",
        "remaster", "remastered", "cover", "karaoke", "sped up", "slowed",
        "radio edit", "extended", "demo", "mix", "reprise",
    )

    def _best_track(self, sp: Any, query: str) -> Any | None:
        """Search and choose the best match, preferring the original studio cut.

        Fetches several candidates (not just the top hit) and, unless the user's
        query itself asks for a variant (e.g. "live", "remix"), demotes tracks
        whose title contains variant words. Ties break toward higher Spotify
        popularity. Falls back to the raw top hit if scoring finds nothing.
        """
        q = query.lower()
        wants_variant = any(w in q for w in self._VARIANT_WORDS)
        market = self._market(sp)
        try:
            results = sp.search(q=query, type="track", limit=10, market=market)
        except Exception:  # noqa: BLE001
            results = sp.search(q=query, type="track", limit=10)
        items = (results.get("tracks") or {}).get("items") or []
        if not items:
            return None
        if wants_variant:
            return items[0]  # user asked for a specific version; trust ranking

        def score(track: Any) -> tuple[int, int]:
            title = (track.get("name") or "").lower()
            is_variant = any(w in title for w in self._VARIANT_WORDS)
            # Prefer originals (0 before 1), then higher popularity.
            return (1 if is_variant else 0, -int(track.get("popularity") or 0))

        return sorted(items, key=score)[0]

    def play_query(self, query: str) -> str | None:
        """Search for ``query`` and start playback. Returns a result string,
        or None to signal the caller should fall back to local control."""
        sp = self._connect()
        if sp is None:
            return None
        try:
            track = self._best_track(sp, query)
            if track is None:
                return f"I found no track matching '{query}' on Spotify."
            uri = track["uri"]
            name = track["name"]
            artist = ", ".join(a["name"] for a in track.get("artists", []))
            label = f"{name} by {artist}" if artist else name

            def try_play(device_id: str | None) -> bool:
                sp.start_playback(device_id=device_id, uris=[uri])
                return True

            # 1) Try the currently active device.
            try:
                try_play(None)
                return f"Playing {label} on Spotify."
            except Exception as exc:  # noqa: BLE001
                if "no active device" not in str(exc).lower() and "404" not in str(exc):
                    return None  # unknown failure -> fall back to local control

            # 2) No active device. Find one from the device list and target it.
            device_id = self._pick_device_id(sp)
            if device_id is None:
                # 3) Nudge the local macOS app to register itself, then retry.
                self._wake_macos_app()
                import time

                time.sleep(1.5)
                device_id = self._pick_device_id(sp)

            if device_id is None:
                return (
                    f"Found '{label}', but no Spotify device is available to "
                    "play on. Open Spotify and play anything once, then retry."
                )
            try:
                sp.transfer_playback(device_id=device_id, force_play=False)
                try_play(device_id)
                return f"Playing {label} on Spotify."
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if "premium" in msg or "403" in msg:
                    return (
                        f"Found '{label}', but Spotify only allows API playback "
                        "on Premium accounts. I've queued it — open Spotify to play."
                    )
                return None  # fall back to local control
        except Exception:  # noqa: BLE001
            return None  # any failure -> fall back to local control
