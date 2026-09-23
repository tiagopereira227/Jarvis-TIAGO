# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Messages skill: send an iMessage/SMS via macOS Messages.app.

macOS only (AppleScript against Messages.app). Sending is an outbound action, so
it goes through the confirmation gate — JARVIS shows the draft and only sends on
an explicit "yes".

Security: the recipient and message text are passed via environment variables
(read with `system attribute`), never string-interpolated into the AppleScript,
so their contents can't break out or inject.

Note on delivery: Messages sends via iMessage when the recipient is on iMessage,
otherwise it can fall back to SMS only if your Mac has Text Message Forwarding
set up with your iPhone. Without that, non-iMessage numbers may not send.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any

from .base import Skill

# Send to a buddy on the iMessage service. Uses the first iMessage account.
_SEND_SCRIPT = r'''
set theTarget to (system attribute "JARVIS_MSG_TO")
set theText to (system attribute "JARVIS_MSG_BODY")
tell application "Messages"
    set svc to 1st account whose service type = iMessage
    set theBuddy to participant theTarget of svc
    send theText to theBuddy
end tell
return "sent"
'''


def _mac_ok() -> bool:
    return platform.system() == "Darwin" and shutil.which("osascript") is not None


class SendMessageSkill(Skill):
    name = "send_message"
    description = (
        "Send an iMessage/SMS via macOS Messages. Asks for confirmation before "
        "sending. Give 'to' (phone number or Apple ID email) and 'text'."
    )
    parameters: dict[str, Any] = {
        "to": {
            "type": "string",
            "description": "Recipient phone number (e.g. +351912345678) or Apple ID.",
        },
        "text": {"type": "string", "description": "The message to send."},
    }
    required = ["to", "text"]

    def run(self, to: str = "", text: str = "", **kwargs: Any) -> str:
        if not _mac_ok():
            return "[error] Sending messages is macOS-only (via Messages.app)."
        to = (to or "").strip()
        text = (text or "").strip()
        if not to:
            return "[error] No recipient given."
        if not text:
            return "[error] There's no message to send."
        if self.registry is None:
            return "[error] Confirmation is unavailable, so I won't send that."

        def action() -> str:
            env = dict(os.environ, JARVIS_MSG_TO=to, JARVIS_MSG_BODY=text)
            try:
                proc = subprocess.run(  # noqa: S603
                    ["osascript", "-e", _SEND_SCRIPT],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                return "[error] Messages took too long to respond."
            except Exception as exc:  # noqa: BLE001
                return f"[error] Couldn't send: {exc}"
            if proc.returncode != 0:
                detail = (proc.stderr or "").strip()
                return (
                    f"[error] Messages refused to send: {detail} "
                    "(the recipient may not be on iMessage, or Messages isn't "
                    "signed in)."
                )
            return f"Message sent to {to}."

        preview = text if len(text) <= 40 else text[:40] + "…"
        return self.registry.gate.arm(f'send "{preview}" to {to}', action)
