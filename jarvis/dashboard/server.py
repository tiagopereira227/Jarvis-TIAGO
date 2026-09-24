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
        from fastapi import (
            FastAPI,
            File,
            Form,
            Request,
            UploadFile,
            WebSocket,
            WebSocketDisconnect,
        )
        from fastapi.responses import HTMLResponse, JSONResponse
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
    cursos_html = (_STATIC / "cursos.html").read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return index_html

    # -- Anexos (imagem / PDF / texto) -------------------------------------

    _MAX_UPLOAD = 20 * 1024 * 1024  # 20 MB de guarda no upload

    @app.post("/api/anexo")
    async def api_attachment(file: UploadFile = File(...), prompt: str = Form("")) -> Any:
        data = await file.read()
        if len(data) > _MAX_UPLOAD:
            return JSONResponse(
                {"error": "Ficheiro demasiado grande (máx 20 MB)."}, status_code=400
            )
        from ..attachments import extract_bytes

        extracted = extract_bytes(file.filename or "anexo", data)
        # Corre o brain (bloqueante) fora do event loop.
        reply = await asyncio.to_thread(
            brain.respond_to_attachment, extracted, prompt
        )
        # Regista no histórico da conversa para reaparecer ao recarregar.
        try:
            history.add("user", f"[anexo: {file.filename}] {prompt}".strip())
            history.add("jarvis", reply)
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse({"name": file.filename, "reply": reply})

    # -- Horário: grelha semanal + importar de anexo -----------------------

    @app.get("/api/horario")
    async def api_horario() -> Any:
        # Todas as aulas de todas as disciplinas, para a grelha semanal.
        return JSONResponse({"classes": registry.courses.all_classes()})

    @app.post("/api/horario/extrair")
    async def api_horario_extrair(file: UploadFile = File(...)) -> Any:
        # Lê o anexo do horário e devolve uma PROPOSTA de aulas (não grava).
        data = await file.read()
        if len(data) > _MAX_UPLOAD:
            return JSONResponse({"error": "Ficheiro demasiado grande (máx 20 MB)."},
                                status_code=400)
        from ..attachments import extract_bytes

        extracted = extract_bytes(file.filename or "horario", data)
        result = await asyncio.to_thread(brain.extract_schedule, extracted)
        if "error" in result:
            return JSONResponse({"error": result["error"]}, status_code=400)
        return JSONResponse(result)  # {"classes": [...]}

    @app.post("/api/horario/aplicar")
    async def api_horario_aplicar(req: Request) -> Any:
        # Grava a proposta confirmada: para cada aula, encontra (ou cria) a
        # disciplina e adiciona a aula ao horário.
        body = await req.json()
        classes = body.get("classes") or []
        courses = registry.courses
        gravadas = 0
        for c in classes:
            disc_name = (c.get("discipline") or "").strip()
            weekday = (c.get("weekday") or "").strip()
            if not disc_name or not weekday:
                continue
            disc = courses.resolve(disc_name) or courses.add_discipline(disc_name)
            if disc is None:
                continue
            if courses.add_class(
                disc["id"], weekday, c.get("start", ""), c.get("end", ""), c.get("room", "")
            ):
                gravadas += 1
        return JSONResponse({"ok": True, "gravadas": gravadas})

    # -- Materiais de aula (PPT/PDF) por disciplina ------------------------

    @app.post("/api/cursos/{disc_id}/material")
    async def api_add_material(disc_id: str, file: UploadFile = File(...),
                               title: str = Form("")) -> Any:
        # Anexa um PPT/PDF: extrai o texto e guarda como material na disciplina.
        if registry.courses.get_discipline(disc_id) is None:
            return JSONResponse({"error": "Disciplina não encontrada."}, status_code=404)
        data = await file.read()
        if len(data) > _MAX_UPLOAD:
            return JSONResponse({"error": "Ficheiro demasiado grande (máx 20 MB)."},
                                status_code=400)
        from ..attachments import extract_bytes

        extracted = extract_bytes(file.filename or "aula", data)
        if extracted.get("kind") != "text":
            return JSONResponse(
                {"error": extracted.get("error", "Não consegui extrair texto do ficheiro.")},
                status_code=400,
            )
        titulo = (title or "").strip() or (file.filename or "Aula")
        mat = registry.courses.add_material(disc_id, titulo, extracted["text"])
        if mat is None:
            return JSONResponse({"error": "Não consegui guardar o material."},
                                status_code=400)
        # Não devolve o texto completo (pode ser grande) — só os metadados.
        return JSONResponse({"id": mat["id"], "title": mat["title"],
                             "date": mat["date"], "summary": mat["summary"],
                             "chars": len(mat["text"])})

    @app.post("/api/cursos/{disc_id}/material/{mat_id}/resumir")
    async def api_resumir_material(disc_id: str, mat_id: str) -> Any:
        mat = registry.courses.get_material(disc_id, mat_id)
        if mat is None:
            return JSONResponse({"error": "Material não encontrado."}, status_code=404)
        # Se já tem resumo, devolve-o (poupa uma chamada ao modelo).
        if mat.get("summary"):
            return JSONResponse({"summary": mat["summary"], "cached": True})
        resumo = await asyncio.to_thread(
            brain.summarize_text, mat["text"], mat["title"]
        )
        if resumo.startswith("[error]"):
            return JSONResponse({"error": resumo}, status_code=400)
        registry.courses.set_material_summary(disc_id, mat_id, resumo)
        return JSONResponse({"summary": resumo, "cached": False})

    @app.post("/api/cursos/{disc_id}/material/{mat_id}/resumir-forcar")
    async def api_resumir_forcar(disc_id: str, mat_id: str) -> Any:
        # Regenera o resumo mesmo que já exista.
        mat = registry.courses.get_material(disc_id, mat_id)
        if mat is None:
            return JSONResponse({"error": "Material não encontrado."}, status_code=404)
        resumo = await asyncio.to_thread(
            brain.summarize_text, mat["text"], mat["title"]
        )
        if resumo.startswith("[error]"):
            return JSONResponse({"error": resumo}, status_code=400)
        registry.courses.set_material_summary(disc_id, mat_id, resumo)
        return JSONResponse({"summary": resumo, "cached": False})

    # -- Gestor de disciplinas (/cursos) -----------------------------------

    courses = registry.courses  # shared store (set up by Brain)

    @app.get("/cursos", response_class=HTMLResponse)
    async def cursos_page() -> str:
        return cursos_html

    @app.get("/api/cursos")
    async def api_list() -> Any:
        # Estado completo, mas com os materiais "aligeirados": enviamos só os
        # metadados + resumo (não o texto completo dos slides, que pode ser
        # enorme). O texto fica no servidor para gerar o resumo.
        import copy

        discs = copy.deepcopy(courses.list_disciplines())
        for d in discs:
            for m in d.get("materials", []):
                m["chars"] = len(m.get("text", ""))
                m.pop("text", None)
        return JSONResponse({"disciplines": discs})

    @app.post("/api/cursos")
    async def api_add_discipline(req: Request) -> Any:
        body = await req.json()
        disc = courses.add_discipline(
            body.get("name", ""), body.get("teacher", ""), body.get("email", "")
        )
        if disc is None:
            return JSONResponse(
                {"error": "Nome vazio ou disciplina já existente."}, status_code=400
            )
        return JSONResponse(disc)

    @app.post("/api/cursos/{disc_id}/update")
    async def api_update(disc_id: str, req: Request) -> Any:
        body = await req.json()
        ok = courses.update_discipline(
            disc_id, teacher=body.get("teacher"), email=body.get("email")
        )
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    @app.post("/api/cursos/{disc_id}/delete")
    async def api_delete_discipline(disc_id: str) -> Any:
        ok = courses.remove_discipline(disc_id)
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    # Rotas específicas (horário / classificações) — antes da rota genérica
    # {kind}, senão "schedule"/"grades" seriam apanhados por api_add_entry.
    @app.post("/api/cursos/{disc_id}/schedule")
    async def api_add_class(disc_id: str, req: Request) -> Any:
        body = await req.json()
        aula = courses.add_class(
            disc_id,
            body.get("weekday", ""),
            body.get("start", ""),
            body.get("end", ""),
            body.get("room", ""),
        )
        if aula is None:
            return JSONResponse(
                {"error": "Disciplina não encontrada ou dia em falta."}, status_code=400
            )
        return JSONResponse(aula)

    @app.post("/api/cursos/{disc_id}/grades")
    async def api_add_grade(disc_id: str, req: Request) -> Any:
        body = await req.json()
        g = courses.add_grade(disc_id, body.get("label", ""), body.get("value", ""))
        if g is None:
            return JSONResponse(
                {"error": "Disciplina não encontrada, ou falta o nome/valor."},
                status_code=400,
            )
        return JSONResponse(g)

    @app.post("/api/cursos/{disc_id}/{kind}/{entry_id}/grade")
    async def api_set_grade(disc_id: str, kind: str, entry_id: str, req: Request) -> Any:
        body = await req.json()
        ok = courses.set_grade(disc_id, kind, entry_id, body.get("grade", ""))
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    @app.post("/api/cursos/{disc_id}/{kind}")
    async def api_add_entry(disc_id: str, kind: str, req: Request) -> Any:
        # 'delete'/'update' are handled by their own routes above; guard anyway.
        if kind not in ("notes", "tests", "tasks", "absences"):
            return JSONResponse({"error": "tipo inválido"}, status_code=400)
        body = await req.json()
        if kind == "notes":
            entry = courses.add_note(disc_id, body.get("text", ""))
        elif kind == "tests":
            entry = courses.add_test(disc_id, body.get("date", ""), body.get("title", ""))
        elif kind == "tasks":
            entry = courses.add_task(disc_id, body.get("deadline", ""), body.get("title", ""))
        elif kind == "absences":
            entry = courses.add_absence(disc_id, body.get("date", ""), body.get("reason", ""))
        else:
            return JSONResponse({"error": "tipo inválido"}, status_code=400)
        if entry is None:
            return JSONResponse(
                {"error": "Disciplina não encontrada ou dados inválidos (data AAAA-MM-DD)."},
                status_code=400,
            )
        return JSONResponse(entry)

    @app.post("/api/cursos/{disc_id}/{kind}/{entry_id}/toggle")
    async def api_toggle(disc_id: str, kind: str, entry_id: str) -> Any:
        ok = courses.toggle_done(disc_id, kind, entry_id)
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    @app.post("/api/cursos/{disc_id}/{kind}/{entry_id}/delete")
    async def api_delete_entry(disc_id: str, kind: str, entry_id: str) -> Any:
        ok = courses.remove_entry(disc_id, kind, entry_id)
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    if _STATIC.exists():
        # StaticFiles com no-cache: assim o browser apanha sempre a versão mais
        # recente do hud.js/cursos.js/css depois de atualizarmos algo, sem ser
        # preciso um "hard refresh" (Cmd+Shift+R).
        class _NoCacheStatic(StaticFiles):
            def is_not_modified(self, *args: Any, **kwargs: Any) -> bool:
                return False  # nunca responde 304; serve sempre o ficheiro

            async def get_response(self, path: str, scope: Any) -> Any:
                resp = await super().get_response(path, scope)
                resp.headers["Cache-Control"] = "no-store, max-age=0"
                return resp

        app.mount("/static", _NoCacheStatic(directory=str(_STATIC)), name="static")

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
