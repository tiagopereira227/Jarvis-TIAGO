# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Gestor de disciplinas — armazenamento persistente do curso.

Guarda as disciplinas e, para cada uma, os apontamentos, testes, trabalhos de
grupo e faltas. Persistido em JSON no diretório do JARVIS (~/.jarvis/courses.json
por omissão), tal como a memória e o histórico. Escrita atómica e tolerante a
falhas — nunca rebenta a aplicação.

Modelo (cada disciplina é independente, para ter o seu próprio separador na
página /cursos):

    {
      "disciplines": {
        "<id>": {
          "id": "<id>",
          "name": "Matemática",
          "teacher": "Prof. Silva",
          "email": "silva@escola.pt",
          "notes":   [{"id","t","text"}],
          "tests":   [{"id","date","title","done"}],
          "tasks":   [{"id","deadline","title","done"}],
          "absences":[{"id","date","reason"}]
        }
      }
    }
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any


def _store_path() -> Path:
    base = os.getenv("JARVIS_STORE_DIR")
    root = Path(base).expanduser() if base else Path.home() / ".jarvis"
    return root / "courses.json"


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _valid_date(s: str) -> str | None:
    """Return an ISO date string if ``s`` is a valid YYYY-MM-DD, else None."""
    s = (s or "").strip()
    try:
        return _dt.datetime.strptime(s, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


class Courses:
    """Loja persistente de disciplinas e respetivos dados."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _store_path()
        self._data: dict[str, Any] = self._load()

    # -- persistência -------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {"disciplines": {}}
        except (OSError, json.JSONDecodeError):
            return {"disciplines": {}}
        if not isinstance(data, dict) or "disciplines" not in data:
            return {"disciplines": {}}
        # Migração leve: garante que disciplinas antigas têm os campos novos,
        # para a página e as skills nunca rebentarem por uma chave em falta.
        for d in data["disciplines"].values():
            for key in ("notes", "tests", "tasks", "absences", "schedule", "grades"):
                d.setdefault(key, [])
        return data

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)  # troca atómica
        except OSError:
            pass  # persistência é conveniência; nunca rebenta

    # -- disciplinas --------------------------------------------------------

    def _find_by_name(self, name: str) -> dict[str, Any] | None:
        name = (name or "").strip().lower()
        for d in self._data["disciplines"].values():
            if d["name"].strip().lower() == name:
                return d
        return None

    def list_disciplines(self) -> list[dict[str, Any]]:
        return sorted(
            self._data["disciplines"].values(), key=lambda d: d["name"].lower()
        )

    def get_discipline(self, disc_id: str) -> dict[str, Any] | None:
        return self._data["disciplines"].get(disc_id)

    def resolve(self, name_or_id: str) -> dict[str, Any] | None:
        """Encontra uma disciplina por id exato ou por nome (sem distinção de
        maiúsculas). Devolve None se não existir."""
        raw = (name_or_id or "").strip()
        if raw in self._data["disciplines"]:
            return self._data["disciplines"][raw]
        return self._find_by_name(raw)

    def add_discipline(
        self, name: str, teacher: str = "", email: str = ""
    ) -> dict[str, Any] | None:
        """Cria uma disciplina. Devolve-a, ou None se o nome estiver vazio ou já
        existir (para evitar duplicados)."""
        name = (name or "").strip()
        if not name or self._find_by_name(name):
            return None
        disc = {
            "id": _new_id(),
            "name": name,
            "teacher": (teacher or "").strip(),
            "email": (email or "").strip(),
            "notes": [],
            "tests": [],
            "tasks": [],
            "absences": [],
            "schedule": [],  # aulas: {id, weekday, start, end, room}
            "grades": [],  # classificações avulsas: {id, label, value}
        }
        self._data["disciplines"][disc["id"]] = disc
        self._save()
        return disc

    def update_discipline(
        self, disc_id: str, teacher: str | None = None, email: str | None = None
    ) -> bool:
        d = self.get_discipline(disc_id)
        if d is None:
            return False
        if teacher is not None:
            d["teacher"] = teacher.strip()
        if email is not None:
            d["email"] = email.strip()
        self._save()
        return True

    def remove_discipline(self, disc_id: str) -> bool:
        if disc_id in self._data["disciplines"]:
            del self._data["disciplines"][disc_id]
            self._save()
            return True
        return False

    # -- entradas (apontamentos / testes / trabalhos / faltas) --------------

    def add_note(self, disc_id: str, text: str) -> dict[str, Any] | None:
        d = self.get_discipline(disc_id)
        text = (text or "").strip()
        if d is None or not text:
            return None
        note = {
            "id": _new_id(),
            "t": _dt.datetime.now().isoformat(timespec="minutes"),
            "text": text,
        }
        d["notes"].append(note)
        self._save()
        return note

    def add_test(self, disc_id: str, date: str, title: str = "") -> dict[str, Any] | None:
        d = self.get_discipline(disc_id)
        iso = _valid_date(date)
        if d is None or iso is None:
            return None
        test = {"id": _new_id(), "date": iso, "title": (title or "").strip(),
                "done": False, "grade": ""}
        d["tests"].append(test)
        d["tests"].sort(key=lambda x: x["date"])
        self._save()
        return test

    def add_task(self, disc_id: str, deadline: str, title: str = "") -> dict[str, Any] | None:
        d = self.get_discipline(disc_id)
        iso = _valid_date(deadline)
        if d is None or iso is None:
            return None
        task = {"id": _new_id(), "deadline": iso, "title": (title or "").strip(),
                "done": False, "grade": ""}
        d["tasks"].append(task)
        d["tasks"].sort(key=lambda x: x["deadline"])
        self._save()
        return task

    def add_absence(self, disc_id: str, date: str, reason: str = "") -> dict[str, Any] | None:
        d = self.get_discipline(disc_id)
        iso = _valid_date(date)
        if d is None or iso is None:
            return None
        ab = {"id": _new_id(), "date": iso, "reason": (reason or "").strip()}
        d["absences"].append(ab)
        d["absences"].sort(key=lambda x: x["date"])
        self._save()
        return ab

    def toggle_done(self, disc_id: str, kind: str, entry_id: str) -> bool:
        """Marca/desmarca um teste ou trabalho como concluído. kind: tests|tasks."""
        d = self.get_discipline(disc_id)
        if d is None or kind not in ("tests", "tasks"):
            return False
        for e in d[kind]:
            if e["id"] == entry_id:
                e["done"] = not e.get("done", False)
                self._save()
                return True
        return False

    def remove_entry(self, disc_id: str, kind: str, entry_id: str) -> bool:
        """Remove uma entrada. kind: notes|tests|tasks|absences|schedule|grades."""
        d = self.get_discipline(disc_id)
        valid = ("notes", "tests", "tasks", "absences", "schedule", "grades")
        if d is None or kind not in valid:
            return False
        before = len(d[kind])
        d[kind] = [e for e in d[kind] if e["id"] != entry_id]
        if len(d[kind]) != before:
            self._save()
            return True
        return False

    # -- horário ------------------------------------------------------------

    def add_class(
        self, disc_id: str, weekday: str, start: str = "", end: str = "", room: str = ""
    ) -> dict[str, Any] | None:
        """Adiciona uma aula ao horário. weekday é livre ('Segunda', '2ª', ...);
        start/end são horas 'HH:MM' (opcionais); room é a sala (opcional)."""
        d = self.get_discipline(disc_id)
        weekday = (weekday or "").strip()
        if d is None or not weekday:
            return None
        aula = {
            "id": _new_id(),
            "weekday": weekday,
            "start": (start or "").strip(),
            "end": (end or "").strip(),
            "room": (room or "").strip(),
        }
        d["schedule"].append(aula)
        # Ordena por dia (ordem canónica PT) e depois por hora de início.
        order = {
            "segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3,
            "sexta": 4, "sábado": 5, "sabado": 5, "domingo": 6,
        }
        d["schedule"].sort(
            key=lambda a: (order.get(a["weekday"].strip().lower(), 9), a.get("start", ""))
        )
        self._save()
        return aula

    # -- classificações -----------------------------------------------------

    def add_grade(self, disc_id: str, label: str, value: str) -> dict[str, Any] | None:
        """Adiciona uma classificação avulsa (ex.: 'Teste 1' -> '15')."""
        d = self.get_discipline(disc_id)
        label = (label or "").strip()
        value = (value or "").strip()
        if d is None or not label or not value:
            return None
        g = {"id": _new_id(), "label": label, "value": value}
        d["grades"].append(g)
        self._save()
        return g

    def set_grade(self, disc_id: str, kind: str, entry_id: str, grade: str) -> bool:
        """Define a nota de um teste ou trabalho existente. kind: tests|tasks."""
        d = self.get_discipline(disc_id)
        if d is None or kind not in ("tests", "tasks"):
            return False
        for e in d[kind]:
            if e["id"] == entry_id:
                e["grade"] = (grade or "").strip()
                self._save()
                return True
        return False

    # -- resumos ------------------------------------------------------------

    def upcoming(self, days: int = 7) -> list[dict[str, Any]]:
        """Testes e trabalhos por concluir dentro dos próximos ``days`` dias.

        Devolve uma lista ordenada por data com o nome da disciplina anexado,
        para o resumo falado e para o briefing da manhã.
        """
        today = _dt.date.today()
        horizon = today + _dt.timedelta(days=days)
        out: list[dict[str, Any]] = []
        for d in self._data["disciplines"].values():
            for t in d["tests"]:
                if t.get("done"):
                    continue
                dt_ = _valid_date(t["date"])
                if dt_ and today.isoformat() <= dt_ <= horizon.isoformat():
                    out.append({"kind": "teste", "discipline": d["name"],
                                "date": t["date"], "title": t["title"]})
            for t in d["tasks"]:
                if t.get("done"):
                    continue
                dt_ = _valid_date(t["deadline"])
                if dt_ and today.isoformat() <= dt_ <= horizon.isoformat():
                    out.append({"kind": "trabalho", "discipline": d["name"],
                                "date": t["deadline"], "title": t["title"]})
        out.sort(key=lambda x: x["date"])
        return out
