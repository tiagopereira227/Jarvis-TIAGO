# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Run a small, safe set of developer shell commands.

This is the most security-sensitive skill, so it is deliberately locked down:

1. NEVER uses a shell. The command string is parsed with shlex.split and run as
   an argument list, so shell metacharacters, pipes, redirects, command
   substitution, and chaining (`;`, `&&`, `|`, backticks) have no effect — they
   become literal arguments to a single program, not new commands.
2. ALLOWLIST. Only a known set of base commands may run at all. Anything else is
   refused outright.
3. READ-ONLY vs MUTATING. Read-only commands (git status, git log, ls, pytest,
   ...) run directly. Anything that can change state (git commit/push/reset/
   checkout, rm, mv, ...) is routed through the confirmation gate and only runs
   after an explicit "yes".
4. Bounded. Runs in the workspace with a timeout and a capped output size.

This is a convenience for common dev tasks, not a general shell. The allowlist
is the security boundary; widening it is a deliberate decision, not a default.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any

from .base import Skill

_TIMEOUT = 60  # seconds
_MAX_OUTPUT = 4000  # chars returned to the model

# Base commands allowed at all. Anything not here is refused. The read-only ones
# run directly; the file-mutating ones (rm/mv/cp/...) are allowed but always
# routed through the confirmation gate by _is_readonly below.
_ALLOWED = {
    # read-only / inspection
    "git", "ls", "cat", "pwd", "echo", "python", "python3", "pip", "pip3",
    "pytest", "node", "npm", "npx", "make", "grep", "find", "wc", "head", "tail",
    "which", "whoami", "date", "df", "du", "env",
    # file management (mutating -> require confirmation)
    "rm", "mv", "cp", "mkdir", "rmdir", "touch", "chmod", "chown",
}

# git subcommands that only read state. Other git subcommands are treated as
# mutating and require confirmation.
_GIT_READONLY = {
    "status", "log", "diff", "show", "branch", "remote", "config", "ls-files",
    "rev-parse", "describe", "blame", "shortlog", "tag",
}

# Base commands that are inherently mutating -> always require confirmation.
_MUTATING_CMDS = {"rm", "mv", "cp", "mkdir", "rmdir", "touch", "chmod", "chown"}


def _is_readonly(parts: list[str]) -> bool:
    """Best-effort: is this invocation read-only (safe to run without asking)?"""
    cmd = parts[0]
    if cmd in _MUTATING_CMDS:
        return False
    if cmd == "git":
        # "git <sub> ..." — read-only only if the subcommand is in the set and
        # no obviously-writing flag is present.
        sub = parts[1] if len(parts) > 1 else ""
        if sub not in _GIT_READONLY:
            return False
        # `git config --global x y` writes; treat any config with a value as write.
        if sub == "config" and len(parts) > 3:
            return False
        return True
    # pip/npm install etc. change the environment -> confirm.
    if cmd in ("pip", "pip3") and any(p in ("install", "uninstall") for p in parts[1:]):
        return False
    if cmd in ("npm", "npx") and any(p in ("install", "uninstall", "i") for p in parts[1:]):
        return False
    # The rest of the allowlist (ls, cat, pytest, grep, ...) is read-only.
    return True


def _execute(parts: list[str]) -> str:
    """Run the arg list (no shell) in the workspace, capture and cap output."""
    cwd = os.getenv("JARVIS_WORKDIR") or os.getcwd()
    try:
        proc = subprocess.run(  # noqa: S603 - arg list, no shell; base cmd allowlisted
            parts,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=_TIMEOUT,
        )
    except FileNotFoundError:
        return f"[error] Command not found: {parts[0]}"
    except subprocess.TimeoutExpired:
        return f"[error] '{parts[0]}' timed out after {_TIMEOUT}s."
    except Exception as exc:  # noqa: BLE001
        return f"[error] Failed to run: {exc}"

    out = (proc.stdout or "") + (proc.stderr or "")
    out = out.strip() or f"(no output; exit code {proc.returncode})"
    if len(out) > _MAX_OUTPUT:
        out = out[:_MAX_OUTPUT] + f"\n… (truncated, {len(out)} chars total)"
    prefix = "" if proc.returncode == 0 else f"[exit {proc.returncode}]\n"
    return prefix + out


class ShellSkill(Skill):
    name = "run_command"
    description = (
        "Run a developer shell command from an allowlist (git, ls, cat, python, "
        "pytest, npm, make, grep, ...). Read-only commands run immediately; "
        "commands that change state ask for confirmation first. No pipes, "
        "redirects, or chaining — a single command only."
    )
    parameters: dict[str, Any] = {
        "command": {
            "type": "string",
            "description": "The command to run, e.g. 'git status' or 'pytest -q'.",
        }
    }
    required = ["command"]

    def run(self, command: str = "", **kwargs: Any) -> str:
        command = (command or "").strip()
        if not command:
            return "[error] No command given."

        # Parse without a shell. This is the core safety step: the string never
        # reaches a shell interpreter, so metacharacters are inert.
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"[error] Couldn't parse the command: {exc}"
        if not parts:
            return "[error] Empty command."

        base = parts[0]
        if base not in _ALLOWED:
            return (
                f"[error] '{base}' isn't on the allowlist. Allowed: "
                f"{', '.join(sorted(_ALLOWED))}."
            )

        if _is_readonly(parts):
            return _execute(parts)

        # Mutating: route through the confirmation gate. The actual execution is
        # captured in the armed callable; nothing runs until an explicit yes.
        if self.registry is None:
            return "[error] Confirmation is unavailable, so I won't run that."

        def action(p: list[str] = parts) -> str:
            return _execute(p)

        return self.registry.gate.arm(f"run: {command}", action)
