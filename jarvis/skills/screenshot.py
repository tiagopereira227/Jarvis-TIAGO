# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Screenshot-and-describe skill.

Captures the screen and asks the vision model what's on it. Screen capture is
built for all three platforms:
- macOS:   screencapture (built in)
- Windows: PowerShell + .NET System.Windows.Forms/Drawing (built in)
- Linux:   grim (Wayland), or scrot / import (X11) if present

Needs the LLM client (shared from the brain via the registry) to describe the
image. Without a key it explains that vision needs the online brain. The
captured file is written to a temp path and deleted after encoding.
"""

from __future__ import annotations

import base64
import os
import platform
import shutil
import subprocess
import tempfile
from typing import Any

from .base import Skill


def _capture_to(path: str) -> tuple[bool, str]:
    """Capture the screen to ``path`` (PNG). Return (ok, detail)."""
    system = platform.system()
    try:
        if system == "Darwin":
            # -x = no capture sound. Captures the main display.
            proc = subprocess.run(  # noqa: S603
                ["screencapture", "-x", path], capture_output=True, text=True
            )
            return proc.returncode == 0, (proc.stderr or "").strip()
        if system == "Windows":
            exe = shutil.which("powershell") or shutil.which("powershell.exe")
            if not exe:
                return False, "PowerShell is unavailable."
            # Grab the virtual screen bounds and save a PNG. Path is passed via
            # an environment variable (not string-interpolated into the script)
            # so it can't break out of the PowerShell string.
            script = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                "$b = [System.Windows.Forms.SystemInformation]::VirtualScreen;"
                "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height;"
                "$g = [System.Drawing.Graphics]::FromImage($bmp);"
                "$g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size);"
                "$bmp.Save($env:JARVIS_SHOT, "
                "[System.Drawing.Imaging.ImageFormat]::Png);"
            )
            env = dict(os.environ, JARVIS_SHOT=path)
            proc = subprocess.run(  # noqa: S603
                [exe, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                env=env,
            )
            return proc.returncode == 0 and os.path.exists(path), (
                proc.stderr or ""
            ).strip()
        if system == "Linux":
            for tool, args in (
                ("grim", ["grim", path]),
                ("scrot", ["scrot", path]),
                ("import", ["import", "-window", "root", path]),
            ):
                if shutil.which(tool):
                    proc = subprocess.run(args, capture_output=True, text=True)  # noqa: S603
                    return proc.returncode == 0, (proc.stderr or "").strip()
            return False, "No screenshot tool found (install grim, scrot, or imagemagick)."
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return False, f"Screen capture isn't supported on {system}."


class ScreenshotDescribeSkill(Skill):
    name = "describe_screen"
    description = (
        "Take a screenshot of the current screen and describe what's on it, or "
        "answer a question about it. Needs the online (vision) brain."
    )
    parameters: dict[str, Any] = {
        "question": {
            "type": "string",
            "description": "Optional question about the screen. Default: describe it.",
        }
    }
    required: list[str] = []

    def run(self, question: str = "", **kwargs: Any) -> str:
        client = getattr(self.registry, "llm_client", None)
        if client is None:
            return (
                "[error] Describing the screen needs the online brain (a vision "
                "model). Set JARVIS_API_KEY to enable this."
            )
        model = getattr(self.registry, "llm_model", None) or "gpt-4o-mini"

        # Capture to a temp file, encode, then remove it.
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            ok, detail = _capture_to(path)
            if not ok:
                return f"[error] Couldn't capture the screen: {detail}"
            try:
                with open(path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode("ascii")
            except OSError as exc:
                return f"[error] Couldn't read the screenshot: {exc}"
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

        prompt = question.strip() or "Describe what's on this screen concisely."
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64}"
                                },
                            },
                        ],
                    }
                ],
            )
            return (resp.choices[0].message.content or "").strip() or (
                "I couldn't make out anything useful on the screen."
            )
        except Exception as exc:  # noqa: BLE001
            return f"[error] The vision model couldn't process the screenshot: {exc}"
