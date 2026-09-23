# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""FastAPI + WebSocket server backing the JARVIS HUD.

Reuses the existing Brain and SkillRegistry — the dashboard is just another
front end onto the same assistant, exactly like the terminal loop. The browser
connects over a WebSocket and receives:
- periodic "stats" frames (CPU/memory/disk, clock, uptime), and
- "reply"/"log" frames in response to commands it sends.

The Brain call is synchronous, so we run it in a thread to avoid blocking the
event loop (and other clients) while the LLM thinks.

Note: we intentionally do NOT use `from __future__ import annotations` here.
FastAPI resolves the WebSocket handler's parameter by its type annotation, and
with stringized (PEP 563) annotations plus a function-local `WebSocket` import,
it can't resolve the name and mis-treats the parameter as a query field. Real
annotations avoid that.
"""

import asyncio
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from ..brain import Brain
from ..config import Config
from ..skills import default_registry
from . import stats

_STATIC = Path(__file__).parent / "static"
# How often to push a vitals/clock frame, in seconds.
_TICK = 2.0
# How often to refresh the weather/news tiles, in seconds (networked; slower).
_TILE_TICK = 600.0


def create_app() -> Any:
    """Build the FastAPI app. Imports FastAPI lazily with a helpful error."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:  # pragma: no cover - exercised only without deps
        raise SystemExit(
            "The dashboard needs FastAPI and uvicorn. Install them with:\n"
            "  pip install 'fastapi' 'uvicorn[standard]'\n"
            f"(import error: {exc})"
        )

    config = Config.load()
    registry = default_registry()
    brain = Brain(config, registry)

    # Re-arm persisted reminders, same as the terminal entry point.
    from ..skills.reminders import _scheduler_for

    _scheduler_for(registry)

    from ..history import History

    history = History()

    app = FastAPI(title="JARVIS HUD")
    app.state.brain = brain
    app.state.registry = registry
    app.state.history = history

    index_html = (_STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return index_html

    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        # Greet + say online/offline and the skill roster.
        await sock.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "online": brain.online,
                    "model": config.model if brain.online else None,
                    "skills": registry.names(),
                }
            )
        )
        # Replay recent conversation history so the log isn't empty on load.
        try:
            past = history.recent(limit=40)
        except Exception:  # noqa: BLE001
            past = []
        if past:
            await sock.send_text(json.dumps({"type": "history", "turns": past}))

        async def pump_stats() -> None:
            """Push a vitals+clock frame every _TICK seconds."""
            try:
                while True:
                    frame = {
                        "type": "stats",
                        "time": _dt.datetime.now().strftime("%H:%M:%S"),
                        "date": _dt.datetime.now().strftime("%a %d %b %Y"),
                        **stats.snapshot(),
                    }
                    await sock.send_text(json.dumps(frame))
                    await asyncio.sleep(_TICK)
            except (WebSocketDisconnect, RuntimeError):
                return

        async def pump_tiles() -> None:
            """Fetch weather + news off-thread and push a tiles frame, refreshed
            every _TILE_TICK. Both skills are blocking + networked, so they run
            in a thread; a failed fetch just yields an empty tile."""
            import os

            location = os.getenv("JARVIS_HOME_LOCATION", "").strip()
            try:
                while True:
                    weather = ""
                    if location:
                        weather = await asyncio.to_thread(
                            registry.dispatch, "get_weather", {"location": location}
                        )
                        if weather.startswith("[error]"):
                            weather = ""
                    news = await asyncio.to_thread(
                        registry.dispatch, "get_news", {"count": 4}
                    )
                    if news.startswith("[error]"):
                        news = ""
                    await sock.send_text(
                        json.dumps({"type": "tiles", "weather": weather, "news": news})
                    )
                    await asyncio.sleep(_TILE_TICK)
            except (WebSocketDisconnect, RuntimeError):
                return

        pusher = asyncio.create_task(pump_stats())
        tiler = asyncio.create_task(pump_tiles())
        try:
            while True:
                raw = await sock.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") != "command":
                    continue
                text = (msg.get("text") or "").strip()
                if not text:
                    continue

                # Echo the user's command back as a log line immediately.
                await sock.send_text(
                    json.dumps({"type": "user", "text": text})
                )
                history.add("user", text)
                # Stream the reply. The brain generator is blocking, so we run
                # it in a thread and hand each chunk back to the event loop via
                # a queue, forwarding "reply_delta" frames and a final
                # "reply_done" that carries the complete text (for TTS).
                loop = asyncio.get_running_loop()
                queue: asyncio.Queue = asyncio.Queue()
                _DONE = object()

                def drain() -> None:
                    try:
                        for chunk in brain.respond_stream(text):
                            loop.call_soon_threadsafe(queue.put_nowait, chunk)
                    except Exception as exc:  # noqa: BLE001
                        loop.call_soon_threadsafe(
                            queue.put_nowait, f"[error] {exc}"
                        )
                    finally:
                        loop.call_soon_threadsafe(queue.put_nowait, _DONE)

                collected: list[str] = []
                worker = asyncio.create_task(asyncio.to_thread(drain))
                while True:
                    item = await queue.get()
                    if item is _DONE:
                        break
                    collected.append(item)
                    await sock.send_text(
                        json.dumps({"type": "reply_delta", "text": item})
                    )
                await worker
                reply_text = "".join(collected)
                await sock.send_text(
                    json.dumps({"type": "reply_done", "text": reply_text})
                )
                history.add("jarvis", reply_text)
        except WebSocketDisconnect:
            pass
        finally:
            pusher.cancel()
            tiler.cancel()

    return app


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the dashboard with uvicorn."""
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "The dashboard needs uvicorn. Install it with:\n"
            "  pip install 'uvicorn[standard]'"
        )
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    serve()
