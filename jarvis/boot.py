# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Full boot sequence: what runs when the machine powers up.

This is the "everything on" entry point (used by auto-start). It:
1. starts the HUD dashboard server in the background,
2. opens it in the default browser,
3. speaks a boot greeting ("Good morning, sir. Systems are starting."), and
4. runs the daemon in the foreground (global hotkey + proactive briefing/alerts).

Each step is best-effort: if the dashboard deps aren't installed, or there's no
display to open a browser, or no TTS, that step is skipped and the rest still
runs. So `--boot` degrades to roughly `--daemon` on a minimal setup.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
import time
import webbrowser

from .briefing import greeting_for_now
from .config import Config


def _open_in_chrome(url: str) -> bool:
    """Open ``url`` in Google Chrome. Returns True on success.

    Chrome is the preferred browser. We try it per-platform, then fall back to
    the OS default via webbrowser if Chrome isn't found. An env override
    (JARVIS_BROWSER) can point at a specific browser command.
    """
    override = os.getenv("JARVIS_BROWSER", "").strip()
    if override:
        try:
            subprocess.Popen([override, url])  # noqa: S603
            return True
        except Exception:  # noqa: BLE001
            pass

    system = platform.system()
    try:
        if system == "Darwin":
            # -a launches a named app; works for "Google Chrome".
            subprocess.Popen(["open", "-a", "Google Chrome", url])  # noqa: S603
            return True
        if system == "Windows":
            if shutil.which("chrome"):
                subprocess.Popen(["chrome", url])  # noqa: S603
                return True
            # Try the registered "chrome" URL handler via start.
            subprocess.Popen(["cmd", "/c", "start", "chrome", url])  # noqa: S603
            return True
        if system == "Linux":
            for exe in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
                if shutil.which(exe):
                    subprocess.Popen([exe, url])  # noqa: S603
                    return True
    except Exception:  # noqa: BLE001
        pass

    # Fallback: whatever the OS considers the default browser.
    try:
        return webbrowser.open(url)
    except Exception:  # noqa: BLE001
        return False


def _start_dashboard(host: str, port: int) -> "object | None":
    """Start the dashboard server on a background thread. Returns the uvicorn
    Server (so it can be stopped), or None if it couldn't start."""
    try:
        import uvicorn

        from .dashboard.server import create_app
    except Exception as exc:  # noqa: BLE001 - deps missing -> skip dashboard
        print(f"[boot] Dashboard not started ({exc}).")
        return None

    try:
        app = create_app()
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
    except Exception as exc:  # noqa: BLE001
        print(f"[boot] Dashboard failed to initialise ({exc}).")
        return None

    threading.Thread(target=server.run, daemon=True).start()
    # Wait briefly for the socket to come up so the browser doesn't race it.
    for _ in range(50):
        if getattr(server, "started", False):
            break
        time.sleep(0.1)
    return server


def run_boot(host: str = "127.0.0.1", port: int = 8000, hotkey: str = "ctrl+alt+j") -> int:
    """The power-up sequence. Returns an exit code."""
    print("JARVIS booting...")

    # 1) Dashboard server + 2) open the browser.
    server = _start_dashboard(host, port)
    url = f"http://{host}:{port}"
    if server is not None:
        print(f"[boot] Dashboard live at {url}")
        _open_in_chrome(url)  # prefers Chrome, falls back to the default browser

    # 3) Spoken boot greeting. Build a Speaker directly so we can greet even
    # before the daemon's own setup. Reuse config for the voice settings.
    config = Config.load()
    greeting = f"{greeting_for_now()}, sir. Systems are starting."
    try:
        from .voice import Speaker

        speaker = Speaker(
            backend=config.tts_backend,
            voice=config.tts_voice,
            say_voice=config.say_voice,
        )
        print(f"[JARVIS] {greeting}")
        speaker.say(greeting)  # blocking so it finishes before the daemon banner
    except Exception:  # noqa: BLE001
        print(f"[JARVIS] {greeting}")

    # 4) Hand off to the daemon (hotkey + proactive briefing/alerts). This
    # blocks until the user quits.
    from .daemon import run_daemon

    try:
        return run_daemon(hotkey=hotkey)
    finally:
        if server is not None:
            server.should_exit = True
