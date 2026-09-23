# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Mail skills: read unread messages and send email via macOS Mail.app.

macOS only (AppleScript against Mail.app); on other systems the skills explain
they're unavailable rather than pretending. Reading is safe and runs directly.
Sending is an outbound action with real consequences, so it goes through the
confirmation gate — JARVIS drafts it, shows you, and only sends on an explicit
"yes".

Security: recipient / subject / body are user- or LLM-supplied free text and
are passed to AppleScript via environment variables (read with `system
attribute`), never string-interpolated into the script — so quotes, newlines,
or AppleScript syntax in a body can't break out or inject.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any

from .base import Skill

_READ_SCRIPT = r'''
set maxN to (system attribute "JARVIS_MAIL_N") as integer
set out to ""
set n to 0
tell application "Mail"
    repeat with acct in accounts
        repeat with mbox in mailboxes of acct
            try
                set msgs to (messages of mbox whose read status is false)
                repeat with m in msgs
                    if n ≥ maxN then exit repeat
                    set out to out & "• " & (sender of m) & " — " & (subject of m) & linefeed
                    set n to n + 1
                end repeat
            end try
            if n ≥ maxN then exit repeat
        end repeat
        if n ≥ maxN then exit repeat
    end repeat
end tell
if out is "" then return "NONE"
return out
'''

_SEND_SCRIPT = r'''
set theTo to (system attribute "JARVIS_MAIL_TO")
set theSubj to (system attribute "JARVIS_MAIL_SUBJ")
set theBody to (system attribute "JARVIS_MAIL_BODY")
tell application "Mail"
    set newMsg to make new outgoing message with properties {subject:theSubj, content:theBody, visible:false}
    tell newMsg
        make new to recipient at end of to recipients with properties {address:theTo}
    end tell
    send newMsg
end tell
return "sent"
'''


def _mac_ok() -> bool:
    return platform.system() == "Darwin" and shutil.which("osascript") is not None


def _run(script: str, env_extra: dict[str, str], timeout: int = 30) -> tuple[bool, str]:
    env = dict(os.environ, **env_extra)
    try:
        proc = subprocess.run(  # noqa: S603
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, "Mail took too long to respond."
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if proc.returncode != 0:
        return False, (proc.stderr or "").strip()
    return True, (proc.stdout or "").strip()


class ReadMailSkill(Skill):
    name = "read_mail"
    description = "Read unread email (sender + subject) from macOS Mail."
    parameters: dict[str, Any] = {
        "count": {"type": "integer", "description": "Max messages to list (default 5)."}
    }
    required: list[str] = []

    def run(self, count: int = 5, **kwargs: Any) -> str:
        if not _mac_ok():
            return "[error] Reading mail is macOS-only (via Mail.app)."
        try:
            n = max(1, min(25, int(count)))
        except (ValueError, TypeError):
            n = 5
        ok, out = _run(_READ_SCRIPT, {"JARVIS_MAIL_N": str(n)})
        if not ok:
            return f"[error] Couldn't read mail: {out}"
        if out == "NONE":
            return "You have no unread mail."
        return "Unread mail:\n" + out


class SendMailSkill(Skill):
    name = "send_mail"
    description = (
        "Send an email via macOS Mail. Asks for confirmation before sending. "
        "Give 'to', 'subject', and 'body'."
    )
    parameters: dict[str, Any] = {
        "to": {"type": "string", "description": "Recipient email address."},
        "subject": {"type": "string", "description": "Email subject."},
        "body": {"type": "string", "description": "Email body text."},
    }
    required = ["to", "subject", "body"]

    def run(self, to: str = "", subject: str = "", body: str = "", **kwargs: Any) -> str:
        if not _mac_ok():
            return "[error] Sending mail is macOS-only (via Mail.app)."
        to = (to or "").strip()
        if "@" not in to:
            return f"[error] '{to}' doesn't look like an email address."
        subject = (subject or "").strip()
        body = (body or "").strip()
        if self.registry is None:
            return "[error] Confirmation is unavailable, so I won't send that."

        def action() -> str:
            ok, out = _run(
                _SEND_SCRIPT,
                {
                    "JARVIS_MAIL_TO": to,
                    "JARVIS_MAIL_SUBJ": subject,
                    "JARVIS_MAIL_BODY": body,
                },
            )
            return f"Email sent to {to}." if ok else f"[error] Couldn't send: {out}"

        preview = subject or "(no subject)"
        return self.registry.gate.arm(f"send an email to {to} — \"{preview}\"", action)
