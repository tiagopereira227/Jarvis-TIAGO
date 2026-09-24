# Copyright (c) 2026 Tiago Pereira. All rights reserved.
"""Extração de conteúdo de anexos para o JARVIS ler.

Suporta três tipos, cada um com o seu caminho:
- imagens (png/jpg/gif/webp) -> data URI base64, para o modelo de visão "ver";
- PDF -> extrai o texto com pypdf (opcional). Um PDF digitalizado (só imagem,
  sem texto) devolve texto vazio — sinalizamos isso para o chamador avisar que
  precisaria de OCR (ainda não suportado);
- texto (txt/md/csv/json/py/...) -> lê diretamente como UTF-8.

Tudo com limites de tamanho para não rebentar a memória, e degrada bem: se o
pypdf não estiver instalado, um PDF devolve um aviso em vez de rebentar.

O resultado é um dicionário simples:
    {"kind": "image", "data_uri": "...", "name": "..."}         # imagem
    {"kind": "text",  "text": "...",     "name": "..."}         # texto/PDF
    {"kind": "error", "error": "...",    "name": "..."}         # falha/limite
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".log", ".py", ".js",
    ".html", ".css", ".xml", ".yaml", ".yml", ".ini", ".rtf",
}

# Limites (bytes). Imagem maior é recusada; texto é truncado.
_MAX_IMAGE_BYTES = 8 * 1024 * 1024   # 8 MB
_MAX_PDF_BYTES = 20 * 1024 * 1024    # 20 MB
_MAX_TEXT_CHARS = 60_000             # texto/PDF/PPT extraído (materiais de aula)


def _image_result(name: str, data: bytes) -> dict[str, Any]:
    if len(data) > _MAX_IMAGE_BYTES:
        return {"kind": "error", "name": name,
                "error": f"Imagem demasiado grande ({len(data) // 1024} KB; máx 8 MB)."}
    mime = mimetypes.guess_type(name)[0] or "image/png"
    b64 = base64.b64encode(data).decode("ascii")
    return {"kind": "image", "name": name, "data_uri": f"data:{mime};base64,{b64}"}


def _pdf_text(name: str, data: bytes) -> dict[str, Any]:
    if len(data) > _MAX_PDF_BYTES:
        return {"kind": "error", "name": name,
                "error": f"PDF demasiado grande ({len(data) // 1024 // 1024} MB; máx 20 MB)."}
    try:
        import io

        from pypdf import PdfReader  # type: ignore
    except Exception:  # noqa: BLE001 - pypdf não instalado
        return {"kind": "error", "name": name,
                "error": "Ler PDF precisa da biblioteca 'pypdf' (pip install pypdf)."}
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
    except Exception as exc:  # noqa: BLE001
        return {"kind": "error", "name": name, "error": f"Não consegui ler o PDF: {exc}"}
    if not text:
        return {"kind": "error", "name": name,
                "error": "Este PDF não tem texto extraível (parece digitalizado). "
                         "OCR de imagens ainda não é suportado."}
    if len(text) > _MAX_TEXT_CHARS:
        text = text[:_MAX_TEXT_CHARS] + "\n… (truncado)"
    return {"kind": "text", "name": name, "text": text}


def _plain_text(name: str, data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8", errors="replace").strip()
    except Exception as exc:  # noqa: BLE001
        return {"kind": "error", "name": name, "error": f"Não consegui ler o texto: {exc}"}
    if not text:
        return {"kind": "error", "name": name, "error": "O ficheiro está vazio."}
    if len(text) > _MAX_TEXT_CHARS:
        text = text[:_MAX_TEXT_CHARS] + "\n… (truncado)"
    return {"kind": "text", "name": name, "text": text}


def _pptx_text(name: str, data: bytes) -> dict[str, Any]:
    """Extrai o texto de todos os slides de um .pptx (precisa de python-pptx)."""
    if len(data) > _MAX_PDF_BYTES:
        return {"kind": "error", "name": name,
                "error": f"Apresentação demasiado grande (máx 20 MB)."}
    try:
        import io

        from pptx import Presentation  # type: ignore
    except Exception:  # noqa: BLE001 - python-pptx não instalado
        return {"kind": "error", "name": name,
                "error": "Ler PowerPoint precisa da biblioteca 'python-pptx' "
                         "(pip install python-pptx)."}
    try:
        prs = Presentation(io.BytesIO(data))
        partes: list[str] = []
        for i, slide in enumerate(prs.slides, 1):
            linhas = []
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False):
                    for p in shape.text_frame.paragraphs:
                        txt = "".join(run.text for run in p.runs).strip()
                        if txt:
                            linhas.append(txt)
            # Notas do orador, se existirem.
            try:
                if slide.has_notes_slide:
                    nt = (slide.notes_slide.notes_text_frame.text or "").strip()
                    if nt:
                        linhas.append(f"[Notas: {nt}]")
            except Exception:  # noqa: BLE001
                pass
            if linhas:
                partes.append(f"— Slide {i} —\n" + "\n".join(linhas))
        text = "\n\n".join(partes).strip()
    except Exception as exc:  # noqa: BLE001
        return {"kind": "error", "name": name, "error": f"Não consegui ler o PowerPoint: {exc}"}
    if not text:
        return {"kind": "error", "name": name,
                "error": "A apresentação não tem texto extraível (só imagens?)."}
    if len(text) > _MAX_TEXT_CHARS:
        text = text[:_MAX_TEXT_CHARS] + "\n… (truncado)"
    return {"kind": "text", "name": name, "text": text}


def extract_bytes(name: str, data: bytes) -> dict[str, Any]:
    """Extrai o conteúdo de um anexo em memória, escolhendo pelo tipo/extensão."""
    ext = Path(name).suffix.lower()
    if ext in _IMAGE_EXTS:
        return _image_result(name, data)
    if ext == ".pdf":
        return _pdf_text(name, data)
    if ext in (".pptx", ".ppt"):
        return _pptx_text(name, data)
    if ext in _TEXT_EXTS or ext == "":
        return _plain_text(name, data)
    # Tipo desconhecido: tenta como texto (muitos ficheiros são texto simples).
    return _plain_text(name, data)


def extract_path(path: str) -> dict[str, Any]:
    """Extrai o conteúdo de um ficheiro no disco, por caminho."""
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        return {"kind": "error", "name": str(p), "error": "Ficheiro não encontrado."}
    try:
        data = p.read_bytes()
    except OSError as exc:
        return {"kind": "error", "name": str(p), "error": f"Não consegui abrir: {exc}"}
    return extract_bytes(p.name, data)
