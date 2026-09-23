<!-- Copyright (c) 2026 Tiago Pereira. All rights reserved. -->
# Instalação — abrir o JARVIS noutro computador

Guia rápido para pôr o **gestor de disciplinas** (e, opcionalmente, o assistente
JARVIS) a correr noutro PC. Funciona em **Windows, macOS e Linux**.

> **Para o curso não precisas de nada pago.** A página de disciplinas
> (`/cursos`) — horário, testes, trabalhos, faltas, notas — funciona sem chave
> de API e sem custos. Só as respostas conversacionais do JARVIS é que precisam
> de uma chave (secção opcional no fim).

## O que precisas
- **Python 3.11 ou mais recente** — https://www.python.org/downloads/
  (no Windows, durante a instalação marca **"Add Python to PATH"**).

## Passos

### 1. Obter o código
Com `git`:
```bash
git clone https://github.com/tiagopereira227/Jarvis-TIAGO.git
cd Jarvis-TIAGO
```
Sem `git`: no GitHub, **Code → Download ZIP**, extrai e abre a pasta.

### 2. Criar o ambiente e instalar

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" psutil
```

**Windows (PowerShell):**
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]" psutil
```

### 3. Arrancar o site
```bash
python -m jarvis --dashboard
```
Depois abre no browser: **http://127.0.0.1:8000/cursos**

Já podes criar disciplinas, meter horário, testes, trabalhos de grupo, faltas e
classificações. Cada disciplina tem o seu separador.

## Onde ficam os dados
Tudo é guardado **no teu computador**, em `~/.jarvis/` (uma pasta na tua conta
de utilizador). Não há servidor partilhado: cada pessoa que corre isto tem as
suas próprias disciplinas e notas. Nada é enviado para a internet.

## Assistente conversacional (opcional, pago)
Só isto precisa de uma chave de API (com custo por utilização):
1. Copia `.env.example` para `.env`.
2. Em `JARVIS_API_KEY`, põe a **tua própria** chave da OpenAI
   (https://platform.openai.com/api-keys). Cada pessoa usa a sua chave.
3. Volta a arrancar. No terminal: `python -m jarvis` (chat) ou continua com
   `--dashboard`.

## Notas
- **Windows/Linux:** o gestor de disciplinas funciona na mesma. As skills que
  usam apps da Apple (Notes, Calendário, Mail, Mensagens) são só de macOS —
  nesses sistemas ficam indisponíveis, sem partir o resto.
- **Testes:** `pip install pytest` e depois `python -m pytest`.
