# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Skill read_file — ler um ficheiro do disco (imagem/PDF/texto) e responder.

Usa o extrator de anexos (attachments.extract_path) e o modelo LLM partilhado
no registry (registry.llm_client / llm_model), tal como o describe_screen.
Precisa do cérebro online. Respostas em português.
"""

from __future__ import annotations

from typing import Any

from .base import Skill


class ReadFileSkill(Skill):
    name = "read_file"
    description = (
        "Ler um ficheiro do computador (imagem, PDF com texto, ou ficheiro de "
        "texto) e resumir/explicar ou responder a uma pergunta sobre ele. Dá "
        "'path' (caminho do ficheiro) e, opcionalmente, 'question'."
    )
    parameters: dict[str, Any] = {
        "path": {"type": "string", "description": "Caminho do ficheiro a ler."},
        "question": {
            "type": "string",
            "description": "Pergunta sobre o ficheiro (opcional).",
        },
    }
    required = ["path"]

    def run(self, path: str = "", question: str = "", **kwargs: Any) -> str:
        path = (path or "").strip()
        if not path:
            return "[error] Falta o caminho do ficheiro."

        client = getattr(self.registry, "llm_client", None)
        if client is None:
            return (
                "[error] Ler ficheiros precisa do cérebro online (modelo). "
                "Define JARVIS_API_KEY para ativar."
            )
        model = getattr(self.registry, "llm_model", None) or "gpt-4o-mini"

        from ..attachments import extract_path

        extracted = extract_path(path)
        if extracted.get("kind") == "error":
            return f"[error] {extracted.get('error', 'não consegui ler o ficheiro')}"

        name = extracted.get("name", path)
        ask = (question or "").strip() or (
            "Resume e explica o conteúdo deste ficheiro de forma clara, em português."
        )

        try:
            if extracted["kind"] == "image":
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": ask},
                            {"type": "image_url",
                             "image_url": {"url": extracted["data_uri"]}},
                        ],
                    }
                ]
            else:  # texto (inclui PDF já extraído)
                content = f"{ask}\n\n--- Conteúdo de '{name}' ---\n{extracted['text']}"
                messages = [{"role": "user", "content": content}]

            resp = client.chat.completions.create(model=model, messages=messages)
            return (resp.choices[0].message.content or "").strip() or (
                "Não consegui tirar nada de útil do ficheiro."
            )
        except Exception as exc:  # noqa: BLE001
            return f"[error] O modelo não conseguiu processar o ficheiro: {exc}"
