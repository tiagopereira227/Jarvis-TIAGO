<!-- Copyright (c) 2026 Tiago Pereira. All rights reserved. -->
# Como abrir o JARVIS / Gestor de Disciplinas — passo a passo

Guia para quem **nunca programou**. Segue as linhas pela ordem. Não precisas de
perceber o que cada coisa faz — é só seguir.

> ✅ **Para o curso (disciplinas, horário, testes, notas) não pagas nada e não
> precisas de conta nenhuma.** É tudo gratuito e fica no teu computador.

Escolhe o teu sistema:
- [🪟 Windows](#-windows)
- [🍎 Mac](#-mac)

---

## 🪟 Windows

### Passo 1 — Instalar o Python
1. Vai a **https://www.python.org/downloads/**
2. Clica no botão amarelo grande **"Download Python 3.x"**.
3. Abre o ficheiro que descarregou (fica na pasta *Transferências*).
4. **MUITO IMPORTANTE:** na primeira janela, marca a caixinha em baixo que diz
   **"Add python.exe to PATH"**. Só depois clica em **"Install Now"**.
5. Espera acabar e clica **"Close"**.

### Passo 2 — Descarregar o programa
1. Vai a **https://github.com/tiagopereira227/Jarvis-TIAGO**
2. Clica no botão verde **"< > Code"**.
3. No menu, clica em **"Download ZIP"**.
4. Vai à pasta *Transferências*, clica com o botão direito no ficheiro
   `Jarvis-TIAGO-main.zip` e escolhe **"Extrair tudo…"** → **"Extrair"**.
5. Fica com uma pasta chamada `Jarvis-TIAGO-main`.

### Passo 3 — Abrir a janela de comandos na pasta certa
1. Entra na pasta `Jarvis-TIAGO-main` (dá duplo clique).
2. Clica na **barra de endereço** lá em cima (onde está o caminho da pasta),
   escreve `powershell` e carrega **Enter**.
3. Abre-se uma janela azul/preta. É aqui que vais escrever os comandos.

### Passo 4 — Preparar (só na primeira vez)
Escreve isto e carrega **Enter** (podes copiar e colar):
```
py -m venv .venv
```
Depois:
```
.venv\Scripts\Activate.ps1
```
> Se aparecer um erro vermelho sobre "execution policy", escreve isto, Enter, e
> tenta o comando de cima outra vez:
> ```
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

Agora instala o necessário (Enter):
```
pip install fastapi "uvicorn[standard]" psutil
```
Espera até parar de escrever (uns segundos).

### Passo 5 — Ligar
```
python -m jarvis --dashboard
```
Vai aparecer uma linha com `http://127.0.0.1:8000`. **Deixa esta janela aberta.**

### Passo 6 — Usar
Abre o **Google Chrome** e escreve na barra de cima:
```
http://127.0.0.1:8000/cursos
```
Pronto! Já podes criar disciplinas, horário, testes e notas. 🎉

**Para desligar:** volta à janela azul e carrega `Ctrl + C`.
**Das próximas vezes:** só precisas dos Passos 3, 5 e 6 (o 4 é só a primeira vez).

---

## 🍎 Mac

### Passo 1 — Instalar o Python
1. Vai a **https://www.python.org/downloads/**
2. Clica no botão grande **"Download Python 3.x"**.
3. Abre o ficheiro `.pkg` descarregado e clica **"Continuar" → "Instalar"**
   (mete a tua palavra-passe do Mac se pedir).

### Passo 2 — Descarregar o programa
1. Vai a **https://github.com/tiagopereira227/Jarvis-TIAGO**
2. Clica no botão verde **"< > Code"** → **"Download ZIP"**.
3. Vai a *Transferências* e dá duplo clique no ZIP para o abrir.
4. Fica com uma pasta `Jarvis-TIAGO-main`. Arrasta-a para o **Ambiente de
   trabalho** (Desktop), para ser fácil de encontrar.

### Passo 3 — Abrir o Terminal na pasta
1. Abre a app **Terminal** (carrega `Cmd + Espaço`, escreve `Terminal`, Enter).
2. Escreve `cd ` (com um espaço no fim) — **não carregues Enter ainda**.
3. Arrasta a pasta `Jarvis-TIAGO-main` para dentro do Terminal (o caminho
   aparece sozinho). Agora sim, carrega **Enter**.

### Passo 4 — Preparar (só na primeira vez)
Um de cada vez, Enter a seguir a cada linha:
```
python3 -m venv .venv
```
```
source .venv/bin/activate
```
```
pip install fastapi "uvicorn[standard]" psutil
```

### Passo 5 — Ligar
```
python3 -m jarvis --dashboard
```
Aparece `http://127.0.0.1:8000`. **Deixa o Terminal aberto.**

### Passo 6 — Usar
Abre o **Google Chrome** e escreve na barra de cima:
```
http://127.0.0.1:8000/cursos
```
Pronto! 🎉

**Para desligar:** no Terminal, carrega `Ctrl + C`.
**Das próximas vezes:** só os Passos 3, 5 e 6.

---

## Perguntas rápidas

**Preciso de pagar alguma coisa?**
Não. Para o gestor de disciplinas é tudo gratuito.

**Os meus dados vão para a internet?**
Não. Ficam só no teu computador, numa pasta escondida `.jarvis` na tua conta.

**O meu amigo vê as minhas disciplinas?**
Não. Cada pessoa tem as suas, no próprio PC. Não é partilhado.

**Deu um erro "python não é reconhecido" (Windows).**
Não marcaste o **"Add python.exe to PATH"** no Passo 1. Desinstala o Python,
instala outra vez e marca essa caixa.

**Quero que o JARVIS também converse (falar/responder).**
Isso é opcional e **pago** (precisa de uma chave da OpenAI). Só se quiseres:
copia o ficheiro `.env.example` para `.env` e mete a tua chave em
`JARVIS_API_KEY`. Cada pessoa usa a sua própria chave.
