# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Launch JARVIS automatically when the machine starts.

Installs a per-user auto-start entry that runs `jarvis --boot` at login — the
full power-up (dashboard + browser + spoken greeting + daemon), so JARVIS is
always there and the proactive morning briefing / event alerts can fire.
Per-platform:

- macOS:   a LaunchAgent plist in ~/Library/LaunchAgents (RunAtLoad).
- Windows: a .cmd shim in the user's Startup folder.
- Linux:   an XDG autostart .desktop entry in ~/.config/autostart.

All of these are *per-user* (no admin/root), reversible with uninstall, and use
the exact Python interpreter currently running (so the venv is preserved).

Honest limits: auto-start runs at *login*, and the daemon only reaches you
while the machine is awake — it can't run while the Mac is off or asleep.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

_LABEL = "com.tiagopereira.jarvis"


def _python_and_cwd() -> tuple[str, str]:
    """The interpreter to launch with and the working dir (project root)."""
    py = sys.executable or "python3"
    # Project root = two levels up from this file (jarvis/autostart.py -> repo).
    root = Path(__file__).resolve().parent.parent
    return py, str(root)


# -- macOS --------------------------------------------------------------------

def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _install_macos() -> str:
    py, cwd = _python_and_cwd()
    log = Path.home() / ".jarvis" / "daemon.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{py}</string>
    <string>-m</string>
    <string>jarvis</string>
    <string>--boot</string>
  </array>
  <key>WorkingDirectory</key><string>{cwd}</string>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""
    path = _macos_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist, encoding="utf-8")
    # Best-effort load so it starts now too (ignore if already loaded).
    import subprocess

    subprocess.run(["launchctl", "unload", str(path)], capture_output=True)  # noqa: S603,S607
    subprocess.run(["launchctl", "load", str(path)], capture_output=True)  # noqa: S603,S607
    return f"Installed LaunchAgent at {path} (runs at login)."


def _uninstall_macos() -> str:
    path = _macos_plist_path()
    if not path.exists():
        return "No LaunchAgent was installed."
    import subprocess

    subprocess.run(["launchctl", "unload", str(path)], capture_output=True)  # noqa: S603,S607
    path.unlink()
    return f"Removed LaunchAgent {path}."


# -- Windows ------------------------------------------------------------------

def _windows_startup_path() -> Path:
    appdata = os.getenv("APPDATA", str(Path.home()))
    return (
        Path(appdata)
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        / "jarvis.cmd"
    )


def _install_windows() -> str:
    py, cwd = _python_and_cwd()
    path = _windows_startup_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # start "" /min runs it minimised without holding a console window open.
    path.write_text(
        f'@echo off\r\ncd /d "{cwd}"\r\nstart "" /min "{py}" -m jarvis --boot\r\n',
        encoding="utf-8",
    )
    return f"Installed startup shim at {path} (runs at login)."


def _uninstall_windows() -> str:
    path = _windows_startup_path()
    if not path.exists():
        return "No startup entry was installed."
    path.unlink()
    return f"Removed startup entry {path}."


# -- Linux --------------------------------------------------------------------

def _linux_desktop_path() -> Path:
    base = os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "jarvis.desktop"


def _install_linux() -> str:
    py, cwd = _python_and_cwd()
    path = _linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=JARVIS\n"
        f"Exec={py} -m jarvis --boot\n"
        f"Path={cwd}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Terminal=false\n",
        encoding="utf-8",
    )
    return f"Installed autostart entry at {path} (runs at login)."


def _uninstall_linux() -> str:
    path = _linux_desktop_path()
    if not path.exists():
        return "No autostart entry was installed."
    path.unlink()
    return f"Removed autostart entry {path}."


# -- Dispatch -----------------------------------------------------------------

def install() -> str:
    system = platform.system()
    if system == "Darwin":
        return _install_macos()
    if system == "Windows":
        return _install_windows()
    if system == "Linux":
        return _install_linux()
    return f"[error] Auto-start isn't supported on {system}."


def uninstall() -> str:
    system = platform.system()
    if system == "Darwin":
        return _uninstall_macos()
    if system == "Windows":
        return _uninstall_windows()
    if system == "Linux":
        return _uninstall_linux()
    return f"[error] Auto-start isn't supported on {system}."
