# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Power-control skills: shut down, restart, suspend the machine.

Every one of these is destructive, so none of them acts on the first call.
They *arm* the confirmation gate (see confirm.py) and return a question; the
real command runs only after an explicit "yes". The command lives inside the
armed callable, so there is no code path that powers off without confirmation.

Commands are chosen per-platform. Where an OS needs elevated rights (e.g. Linux
`systemctl`/`shutdown`), the command may fail without privileges; we surface
that as an error string rather than pretending it worked.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

from .base import Skill


def _run(cmd: list[str]) -> str:
    """Run a power command (list args, no shell) and report the outcome."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    except FileNotFoundError:
        return f"[error] Command not found: {cmd[0]}"
    except Exception as exc:  # noqa: BLE001
        return f"[error] Failed to run {cmd[0]}: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return f"[error] {cmd[0]} exited {proc.returncode}: {detail}"
    return ""  # empty == success; caller adds the friendly message


class _PowerSkill(Skill):
    """Shared base: resolve a per-OS command, then arm the gate with it."""

    # Human phrase used in the confirmation prompt, e.g. "shut down the computer".
    phrase: str = ""
    # Message spoken once the action has actually been dispatched.
    done_message: str = ""

    def _command(self) -> list[str] | None:
        """Return the OS command, or None if unsupported on this platform."""
        raise NotImplementedError

    def run(self, **kwargs: Any) -> str:
        cmd = self._command()
        if cmd is None:
            return f"[error] I don't know how to {self.phrase} on this system."
        if self.registry is None:  # not bound; can't confirm safely -> refuse
            return "[error] Confirmation is unavailable, so I won't proceed."

        def action() -> str:
            err = _run(cmd)
            return err if err else self.done_message

        return self.registry.gate.arm(self.phrase, action)


class ShutdownSkill(_PowerSkill):
    name = "shutdown_computer"
    description = (
        "Shut down (power off) this computer. Asks for confirmation first and "
        "only powers off after the user explicitly confirms."
    )
    parameters: dict[str, Any] = {}
    required: list[str] = []
    phrase = "shut down the computer"
    done_message = "Shutting down. Goodbye, sir."

    def _command(self) -> list[str] | None:
        system = platform.system()
        if system == "Darwin":
            # osascript avoids needing sudo for a normal user shutdown.
            return ["osascript", "-e", 'tell app "System Events" to shut down']
        if system == "Windows":
            return ["shutdown", "/s", "/t", "0"]
        if system == "Linux":
            if shutil.which("systemctl"):
                return ["systemctl", "poweroff"]
            return ["shutdown", "-h", "now"]
        return None


class RestartSkill(_PowerSkill):
    name = "restart_computer"
    description = (
        "Restart (reboot) this computer. Asks for confirmation first and only "
        "reboots after the user explicitly confirms."
    )
    parameters: dict[str, Any] = {}
    required: list[str] = []
    phrase = "restart the computer"
    done_message = "Restarting now."

    def _command(self) -> list[str] | None:
        system = platform.system()
        if system == "Darwin":
            return ["osascript", "-e", 'tell app "System Events" to restart']
        if system == "Windows":
            return ["shutdown", "/r", "/t", "0"]
        if system == "Linux":
            if shutil.which("systemctl"):
                return ["systemctl", "reboot"]
            return ["shutdown", "-r", "now"]
        return None


class SuspendSkill(_PowerSkill):
    name = "suspend_computer"
    description = (
        "Suspend / sleep this computer. Asks for confirmation first and only "
        "sleeps after the user explicitly confirms."
    )
    parameters: dict[str, Any] = {}
    required: list[str] = []
    phrase = "put the computer to sleep"
    done_message = "Going to sleep."

    def _command(self) -> list[str] | None:
        system = platform.system()
        if system == "Darwin":
            return ["pmset", "sleepnow"]
        if system == "Windows":
            # SetSuspendState: sleep (not hibernate), don't force-close apps.
            return [
                "rundll32.exe",
                "powrprof.dll,SetSuspendState",
                "0",
                "1",
                "0",
            ]
        if system == "Linux":
            if shutil.which("systemctl"):
                return ["systemctl", "suspend"]
            return None
        return None
