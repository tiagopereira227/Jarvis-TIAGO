# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""System control skills: volume, brightness, do-not-disturb.

Each is built for macOS, Windows, and Linux. Where an OS has no reliable,
dependency-free way to do something (brightness on desktops, DND toggles), the
skill returns a clear message instead of pretending it worked.

All shell-outs pass arguments as lists (never a shell string), and numeric
inputs are validated and clamped before use, so nothing user-supplied reaches a
command interpreter unchecked.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

from .base import Skill


def _run(cmd: list[str]) -> tuple[bool, str]:
    """Run a command (list args, no shell). Return (ok, detail)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    except FileNotFoundError:
        return False, f"{cmd[0]} not found"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "").strip()
    return True, (proc.stdout or "").strip()


def _clamp_pct(value: Any) -> int | None:
    try:
        n = int(round(float(value)))
    except (ValueError, TypeError):
        return None
    return max(0, min(100, n))


class VolumeSkill(Skill):
    name = "set_volume"
    description = (
        "Set the system output volume to a percentage (0-100), or mute/unmute. "
        "Pass 'level' (0-100) or 'mute' = true/false."
    )
    parameters: dict[str, Any] = {
        "level": {"type": "integer", "description": "Target volume 0-100."},
        "mute": {"type": "boolean", "description": "Mute (true) or unmute (false)."},
    }
    required: list[str] = []

    def run(self, level: Any = None, mute: Any = None, **kwargs: Any) -> str:
        system = platform.system()
        if mute is not None:
            return self._set_mute(system, bool(mute))
        pct = _clamp_pct(level)
        if pct is None:
            return "[error] Give a volume level between 0 and 100, or mute true/false."
        return self._set_level(system, pct)

    def _set_level(self, system: str, pct: int) -> str:
        if system == "Darwin":
            ok, detail = _run(
                ["osascript", "-e", f"set volume output volume {pct}"]
            )
        elif system == "Windows":
            # Drive the master volume via a tiny PowerShell WScript.Shell trick
            # is unreliable; use nircmd if present, else explain.
            if shutil.which("nircmd"):
                # nircmd takes 0-65535.
                ok, detail = _run(
                    ["nircmd", "setsysvolume", str(int(pct / 100 * 65535))]
                )
            else:
                return (
                    "[error] Setting an exact volume on Windows needs 'nircmd' on "
                    "PATH. I can still mute/unmute via the media key."
                )
        elif system == "Linux":
            if shutil.which("pactl"):
                ok, detail = _run(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"]
                )
            elif shutil.which("amixer"):
                ok, detail = _run(["amixer", "set", "Master", f"{pct}%"])
            else:
                return "[error] No 'pactl' or 'amixer' found to set volume."
        else:
            return f"[error] Volume control isn't supported on {system}."
        return f"Volume set to {pct}%." if ok else f"[error] {detail}"

    def _set_mute(self, system: str, mute: bool) -> str:
        if system == "Darwin":
            val = "true" if mute else "false"
            ok, detail = _run(["osascript", "-e", f"set volume output muted {val}"])
        elif system == "Windows":
            # VK_VOLUME_MUTE toggles; we can't force a state without extra tools,
            # so send the toggle key and report it as a toggle.
            try:
                import ctypes

                ctypes.windll.user32.keybd_event(0xAD, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0xAD, 0, 2, 0)
            except Exception as exc:  # noqa: BLE001
                return f"[error] Could not send mute key: {exc}"
            return "Toggled mute."
        elif system == "Linux":
            if shutil.which("pactl"):
                ok, detail = _run(
                    ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if mute else "0"]
                )
            elif shutil.which("amixer"):
                ok, detail = _run(
                    ["amixer", "set", "Master", "mute" if mute else "unmute"]
                )
            else:
                return "[error] No 'pactl' or 'amixer' found to mute."
        else:
            return f"[error] Mute isn't supported on {system}."
        return ("Muted." if mute else "Unmuted.") if ok else f"[error] {detail}"


class BrightnessSkill(Skill):
    name = "set_brightness"
    description = "Set the display brightness to a percentage (0-100)."
    parameters: dict[str, Any] = {
        "level": {"type": "integer", "description": "Target brightness 0-100."}
    }
    required = ["level"]

    def run(self, level: Any = None, **kwargs: Any) -> str:
        pct = _clamp_pct(level)
        if pct is None:
            return "[error] Give a brightness level between 0 and 100."
        system = platform.system()

        if system == "Darwin":
            # macOS has no built-in CLI for brightness; needs the 'brightness'
            # tool (brew install brightness). Value is 0.0-1.0.
            if shutil.which("brightness"):
                ok, detail = _run(["brightness", f"{pct / 100:.2f}"])
                return f"Brightness set to {pct}%." if ok else f"[error] {detail}"
            return (
                "[error] Setting brightness on macOS needs the 'brightness' tool "
                "(brew install brightness)."
            )
        if system == "Windows":
            # WMI can set laptop panel brightness. This works on internal
            # displays; external monitors generally don't support it.
            exe = shutil.which("powershell") or shutil.which("powershell.exe")
            if not exe:
                return "[error] PowerShell is unavailable."
            script = (
                "(Get-WmiObject -Namespace root/WMI "
                "-Class WmiMonitorBrightnessMethods)."
                f"WmiSetBrightness(1,{pct})"
            )
            ok, detail = _run(
                [exe, "-NoProfile", "-NonInteractive", "-Command", script]
            )
            if ok:
                return f"Brightness set to {pct}% (internal display)."
            return (
                "[error] Couldn't set brightness. This works on laptop panels; "
                f"external monitors usually don't support it. {detail}"
            )
        if system == "Linux":
            if shutil.which("brightnessctl"):
                ok, detail = _run(["brightnessctl", "set", f"{pct}%"])
                return f"Brightness set to {pct}%." if ok else f"[error] {detail}"
            return "[error] Setting brightness on Linux needs 'brightnessctl'."
        return f"[error] Brightness control isn't supported on {system}."


class DoNotDisturbSkill(Skill):
    name = "do_not_disturb"
    description = (
        "Turn Do Not Disturb / Focus on or off. Pass 'enable' = true/false. "
        "Support varies by OS."
    )
    parameters: dict[str, Any] = {
        "enable": {"type": "boolean", "description": "Turn DND on (true) or off (false)."}
    }
    required = ["enable"]

    def run(self, enable: Any = None, **kwargs: Any) -> str:
        if enable is None:
            return "[error] Say whether to enable or disable Do Not Disturb."
        on = bool(enable)
        system = platform.system()

        if system == "Darwin":
            # Recent macOS gates Focus behind Shortcuts. If the user has a
            # shortcut named accordingly we use it; otherwise we explain, since
            # there's no stable public CLI toggle across versions.
            name = "Turn On Do Not Disturb" if on else "Turn Off Do Not Disturb"
            if shutil.which("shortcuts"):
                ok, detail = _run(["shortcuts", "run", name])
                if ok:
                    return f"Do Not Disturb {'on' if on else 'off'}."
                return (
                    f"[error] I tried the '{name}' shortcut but it failed. Create "
                    "a Shortcut with that exact name to enable this. " + detail
                )
            return (
                "[error] macOS Focus has no stable CLI. Create Shortcuts named "
                "'Turn On/Off Do Not Disturb' and I can trigger them."
            )
        if system == "Windows":
            # Windows Focus Assist has no supported CLI toggle without third-
            # party tools. Be honest rather than fake it.
            return (
                "[error] Windows Focus Assist has no built-in command-line "
                "toggle. This one isn't available on Windows without extra tools."
            )
        if system == "Linux":
            # GNOME exposes DND via gsettings.
            if shutil.which("gsettings"):
                ok, detail = _run(
                    [
                        "gsettings",
                        "set",
                        "org.gnome.desktop.notifications",
                        "show-banners",
                        "false" if on else "true",
                    ]
                )
                if ok:
                    return f"Do Not Disturb {'on' if on else 'off'}."
                return f"[error] {detail}"
            return "[error] DND toggle on Linux needs GNOME 'gsettings'."
        return f"[error] Do Not Disturb isn't supported on {system}."
