# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Live system vitals for the dashboard.

Uses psutil when available (accurate, cross-platform). Without it, degrades to
best-effort stdlib values so the dashboard still shows *something* rather than
breaking. Everything here is read-only and safe to poll frequently.
"""

from __future__ import annotations

import platform
import shutil
import time
from typing import Any

try:
    import psutil  # type: ignore
except Exception:  # noqa: BLE001
    psutil = None  # type: ignore

_BOOT = time.time()


def _fallback_stats() -> dict[str, Any]:
    """Rough numbers without psutil. Disk is real; CPU/mem are placeholders."""
    total = used = 0
    try:
        usage = shutil.disk_usage("/")
        total, used = usage.total, usage.used
    except OSError:
        pass
    disk_pct = round(used / total * 100) if total else 0
    return {
        "cpu": None,  # can't measure reliably without psutil
        "memory": None,
        "disk": disk_pct,
        "has_psutil": False,
    }


def snapshot() -> dict[str, Any]:
    """Return current CPU %, memory %, disk %, and a couple of extras."""
    if psutil is None:
        data = _fallback_stats()
    else:
        vm = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage("/").percent
        except Exception:  # noqa: BLE001
            disk = 0
        data = {
            # interval=None -> non-blocking, compares since the last call.
            "cpu": round(psutil.cpu_percent(interval=None)),
            "memory": round(vm.percent),
            "disk": round(disk),
            "has_psutil": True,
        }
    data["uptime_seconds"] = int(time.time() - _BOOT)
    data["system"] = f"{platform.system()} {platform.release()}"
    return data
