# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Skills de materiais de aula: guardar um PPT/PDF numa disciplina e resumir.

Alcançam a loja partilhada via registry.courses e o modelo via registry.llm_client
(mesmo padrão do read_file). Respostas em português.
"""

from __future__ import annotations

from typing import Any

from .base import Skill


def _courses(registry: Any) -> Any:
    c = getattr(registry, "courses", None)
    if c is None:
        from ..courses import Courses

        c = Courses()
        setattr(registry, "courses", c)
    return c


class SaveMaterialSkill(Skill):
    name = "save_material"
    description = (
        "Guardar um material de aula (PowerPoint/PDF/texto) numa disciplina, a "
        "partir do caminho do ficheiro. Dá 'discipline', 'path' e, opcionalmente, "
        "um 'title'."
    )
    parameters: dict[str, Any] = {
        "discipline": {"type": "string", "description": "Nome da disciplina."},
        "path": {"type": "string", "description": "Caminho do ficheiro (PPT/PDF)."},
        "title": {"type": "string", "description": "Título da aula (opcional)."},
    }
    required = ["discipline", "path"]

    def run(self, discipline: str = "", path: str = "", title: str = "", **kwargs: Any) -> str:
        courses = _courses(self.registry)
        disc = courses.resolve(discipline)
        if disc is None:
            return f"[error] Não encontrei a disciplina '{discipline}'."
        from ..attachments import extract_path

        extracted = extract_path(path)
        if extracted.get("kind") != "text":
            return f"[error] {extracted.get('error', 'não consegui ler o ficheiro')}"
        titulo = (title or "").strip() or extracted.get("name", "Aula")
        mat = courses.add_material(disc["id"], titulo, extracted["text"])
        if mat is None:
            return "[error] Não consegui guardar o material."
        return f"Aula '{mat['title']}' guardada em {disc['name']}."


class SummarizeMaterialSkill(Skill):
    name = "summarize_material"
    description = (
        "Resumir a última aula/material guardado de uma disciplina (ou por "
        "título). Dá 'discipline' e, opcionalmente, 'title' para escolher qual."
    )
    parameters: dict[str, Any] = {
        "discipline": {"type": "string", "description": "Nome da disciplina."},
        "title": {"type": "string", "description": "Título da aula a resumir (opcional)."},
    }
    required = ["discipline"]

    def run(self, discipline: str = "", title: str = "", **kwargs: Any) -> str:
        courses = _courses(self.registry)
        disc = courses.resolve(discipline)
        if disc is None:
            return f"[error] Não encontrei a disciplina '{discipline}'."
        mats = disc.get("materials", [])
        if not mats:
            return f"Ainda não há aulas guardadas em {disc['name']}."

        # Escolhe por título (contém) ou a mais recente.
        mat = None
        if title.strip():
            alvo = title.strip().lower()
            for m in mats:
                if alvo in m.get("title", "").lower():
                    mat = m
                    break
            if mat is None:
                return f"Não encontrei uma aula com '{title}' em {disc['name']}."
        else:
            mat = mats[-1]

        if mat.get("summary"):
            return f"Resumo de '{mat['title']}' ({disc['name']}):\n{mat['summary']}"

        # Gera com o modelo (via registry.llm_client, como o read_file).
        client = getattr(self.registry, "llm_client", None)
        if client is None:
            return "[error] Resumir precisa do cérebro online (define JARVIS_API_KEY)."
        model = getattr(self.registry, "llm_model", None) or "gpt-4o-mini"
        instru = (
            f"Faz um resumo claro e organizado da aula '{mat['title']}', em "
            "português de Portugal (pt-PT), com tópicos e conceitos-chave. "
            "Mantém os termos técnicos tal como aparecem. Se houver matemática "
            "(equações, fórmulas, símbolos como Σ, √, ≤, ±, letras gregas, "
            "expoentes), PRESERVA-as de forma legível e fiel, e explica "
            "brevemente o que representam. Não inventes conteúdo."
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user",
                           "content": instru + "\n\n--- Conteúdo ---\n" + mat["text"]}],
            )
            resumo = (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            return f"[error] O modelo não conseguiu resumir: {exc}"
        if not resumo:
            return "Não consegui gerar um resumo."
        courses.set_material_summary(disc["id"], mat["id"], resumo)
        return f"Resumo de '{mat['title']}' ({disc['name']}):\n{resumo}"
