# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Skills do gestor de disciplinas — controlo por voz/chat, respostas em português.

Alcançam a instância partilhada de Courses via registry.courses (mesmo padrão da
memória), para que o site /cursos e o JARVIS partilhem os mesmos dados.
"""

from __future__ import annotations

from typing import Any

from .base import Skill


def _courses(registry: Any) -> Any:
    """Obtém (ou cria) a loja de disciplinas partilhada no registry."""
    c = getattr(registry, "courses", None)
    if c is None:
        from ..courses import Courses

        c = Courses()
        setattr(registry, "courses", c)
    return c


def _need_disc(registry: Any, name: str) -> tuple[Any, str | None]:
    """Resolve a disciplina por nome/id. Devolve (disciplina, erro_ou_None)."""
    disc = _courses(registry).resolve(name)
    if disc is None:
        return None, (
            f"Não encontrei a disciplina '{name}'. Cria-a primeiro ou verifica o nome."
        )
    return disc, None


class AddDisciplineSkill(Skill):
    name = "add_discipline"
    description = (
        "Criar uma disciplina no gestor de curso. Dá o 'name' e, opcionalmente, "
        "o 'teacher' (nome do professor) e o 'email'."
    )
    parameters: dict[str, Any] = {
        "name": {"type": "string", "description": "Nome da disciplina."},
        "teacher": {"type": "string", "description": "Nome do professor (opcional)."},
        "email": {"type": "string", "description": "Email do professor (opcional)."},
    }
    required = ["name"]

    def run(self, name: str = "", teacher: str = "", email: str = "", **kwargs: Any) -> str:
        disc = _courses(self.registry).add_discipline(name, teacher, email)
        if disc is None:
            return f"[error] Já existe uma disciplina chamada '{name}' (ou o nome está vazio)."
        extra = f", com o professor {disc['teacher']}" if disc["teacher"] else ""
        return f"Disciplina '{disc['name']}' criada{extra}."


class ListDisciplinesSkill(Skill):
    name = "list_disciplines"
    description = "Listar as disciplinas do curso."
    parameters: dict[str, Any] = {}
    required: list[str] = []

    def run(self, **kwargs: Any) -> str:
        discs = _courses(self.registry).list_disciplines()
        if not discs:
            return "Ainda não tens disciplinas registadas."
        linhas = []
        for d in discs:
            prof = f" — {d['teacher']}" if d["teacher"] else ""
            linhas.append(f"• {d['name']}{prof}")
        return "As tuas disciplinas:\n" + "\n".join(linhas)


class AddCourseTestSkill(Skill):
    name = "add_course_test"
    description = (
        "Marcar um teste/exame numa disciplina. Dá 'discipline', 'date' "
        "(AAAA-MM-DD) e, opcionalmente, um 'title'."
    )
    parameters: dict[str, Any] = {
        "discipline": {"type": "string", "description": "Nome da disciplina."},
        "date": {"type": "string", "description": "Data do teste (AAAA-MM-DD)."},
        "title": {"type": "string", "description": "Descrição do teste (opcional)."},
    }
    required = ["discipline", "date"]

    def run(self, discipline: str = "", date: str = "", title: str = "", **kwargs: Any) -> str:
        disc, err = _need_disc(self.registry, discipline)
        if err:
            return f"[error] {err}"
        test = _courses(self.registry).add_test(disc["id"], date, title)
        if test is None:
            return f"[error] Data inválida '{date}'. Usa o formato AAAA-MM-DD."
        desc = f" ({test['title']})" if test["title"] else ""
        return f"Teste marcado em {disc['name']} para {test['date']}{desc}."


class AddCourseTaskSkill(Skill):
    name = "add_course_task"
    description = (
        "Adicionar um trabalho de grupo/entrega a uma disciplina. Dá "
        "'discipline', 'deadline' (AAAA-MM-DD) e, opcionalmente, um 'title'."
    )
    parameters: dict[str, Any] = {
        "discipline": {"type": "string", "description": "Nome da disciplina."},
        "deadline": {"type": "string", "description": "Data de entrega (AAAA-MM-DD)."},
        "title": {"type": "string", "description": "Descrição do trabalho (opcional)."},
    }
    required = ["discipline", "deadline"]

    def run(self, discipline: str = "", deadline: str = "", title: str = "", **kwargs: Any) -> str:
        disc, err = _need_disc(self.registry, discipline)
        if err:
            return f"[error] {err}"
        task = _courses(self.registry).add_task(disc["id"], deadline, title)
        if task is None:
            return f"[error] Data inválida '{deadline}'. Usa o formato AAAA-MM-DD."
        desc = f" ({task['title']})" if task["title"] else ""
        return f"Trabalho de grupo em {disc['name']} para entregar a {task['deadline']}{desc}."


class MarkAbsenceSkill(Skill):
    name = "mark_absence"
    description = (
        "Registar uma falta numa disciplina. Dá 'discipline', 'date' "
        "(AAAA-MM-DD) e, opcionalmente, um 'reason'."
    )
    parameters: dict[str, Any] = {
        "discipline": {"type": "string", "description": "Nome da disciplina."},
        "date": {"type": "string", "description": "Data da falta (AAAA-MM-DD)."},
        "reason": {"type": "string", "description": "Motivo (opcional)."},
    }
    required = ["discipline", "date"]

    def run(self, discipline: str = "", date: str = "", reason: str = "", **kwargs: Any) -> str:
        disc, err = _need_disc(self.registry, discipline)
        if err:
            return f"[error] {err}"
        ab = _courses(self.registry).add_absence(disc["id"], date, reason)
        if ab is None:
            return f"[error] Data inválida '{date}'. Usa o formato AAAA-MM-DD."
        total = len(disc["absences"])
        return f"Falta registada em {disc['name']} ({ab['date']}). Total: {total}."


class AddCourseNoteSkill(Skill):
    name = "add_course_note"
    description = (
        "Guardar um apontamento numa disciplina. Dá 'discipline' e 'text'."
    )
    parameters: dict[str, Any] = {
        "discipline": {"type": "string", "description": "Nome da disciplina."},
        "text": {"type": "string", "description": "O apontamento a guardar."},
    }
    required = ["discipline", "text"]

    def run(self, discipline: str = "", text: str = "", **kwargs: Any) -> str:
        disc, err = _need_disc(self.registry, discipline)
        if err:
            return f"[error] {err}"
        note = _courses(self.registry).add_note(disc["id"], text)
        if note is None:
            return "[error] Não havia texto para guardar."
        return f"Apontamento guardado em {disc['name']}."


class CourseOnDateSkill(Skill):
    name = "course_on_date"
    description = (
        "O que está agendado no curso numa data específica: testes, trabalhos "
        "e faltas. Dá 'date' em AAAA-MM-DD (resolve datas relativas primeiro)."
    )
    parameters: dict[str, Any] = {
        "date": {"type": "string", "description": "Data a consultar (AAAA-MM-DD)."}
    }
    required = ["date"]

    def run(self, date: str = "", **kwargs: Any) -> str:
        from ..courses import _valid_date

        iso = _valid_date(date)
        if iso is None:
            return f"[error] Data inválida '{date}'. Usa o formato AAAA-MM-DD."
        itens = _courses(self.registry).on_date(iso)
        if not itens:
            return f"Não há nada agendado no curso para {iso}."
        linhas = []
        for it in itens:
            desc = f" — {it['title']}" if it["title"] else ""
            feito = " (concluído)" if it.get("done") else ""
            linhas.append(f"• {it['kind']} de {it['discipline']}{desc}{feito}")
        return f"No dia {iso}:\n" + "\n".join(linhas)


class CourseSummarySkill(Skill):
    name = "course_summary"
    description = (
        "Resumo do que está para vir: testes e trabalhos por concluir nos "
        "próximos dias (por omissão 7). Aceita 'days'."
    )
    parameters: dict[str, Any] = {
        "days": {"type": "integer", "description": "Horizonte em dias (por omissão 7)."}
    }
    required: list[str] = []

    def run(self, days: int = 7, **kwargs: Any) -> str:
        try:
            n = max(1, min(60, int(days)))
        except (ValueError, TypeError):
            n = 7
        itens = _courses(self.registry).upcoming(n)
        if not itens:
            return f"Nada marcado para os próximos {n} dias. Estás em dia."
        linhas = []
        for it in itens:
            desc = f" — {it['title']}" if it["title"] else ""
            linhas.append(f"• {it['date']} · {it['kind']} de {it['discipline']}{desc}")
        return f"Para os próximos {n} dias:\n" + "\n".join(linhas)
