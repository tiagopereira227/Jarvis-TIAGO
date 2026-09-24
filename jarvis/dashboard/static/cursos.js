// Copyright (c) 2026 Tiago Pereira. All rights reserved.
// Gestor de disciplinas: um separador por disciplina.
(function () {
  "use strict";

  const tabsEl = document.getElementById("tabs");
  const contentEl = document.getElementById("content");
  const toastEl = document.getElementById("toast");
  let state = { disciplines: [] };
  let activeId = null;

  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    setTimeout(() => toastEl.classList.remove("show"), 2200);
  }

  async function api(method, url, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const r = await fetch(url, opts);
    let data = {};
    try { data = await r.json(); } catch (e) {}
    if (!r.ok) throw new Error(data.error || ("Erro " + r.status));
    return data;
  }

  async function load(keepActive) {
    state = await api("GET", "/api/cursos");
    if (!keepActive || !state.disciplines.some((d) => d.id === activeId)) {
      activeId = state.disciplines.length ? state.disciplines[0].id : "__new__";
    }
    render();
  }

  // Escape helper so discipline/entry text can't inject HTML.
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function render() {
    // Tabs: one per discipline + an "add" tab.
    tabsEl.innerHTML = "";
    // Aba especial "Horário" (grelha semanal de todas as disciplinas).
    const horTab = document.createElement("button");
    horTab.className = "tab" + (activeId === "__horario__" ? " active" : "");
    horTab.textContent = "🗓 Horário";
    horTab.onclick = () => { activeId = "__horario__"; render(); };
    tabsEl.appendChild(horTab);

    state.disciplines.forEach((d) => {
      const t = document.createElement("button");
      t.className = "tab" + (d.id === activeId ? " active" : "");
      t.textContent = d.name;
      t.onclick = () => { activeId = d.id; render(); };
      tabsEl.appendChild(t);
    });
    const addTab = document.createElement("button");
    addTab.className = "tab add" + (activeId === "__new__" ? " active" : "");
    addTab.textContent = "+ Nova disciplina";
    addTab.onclick = () => { activeId = "__new__"; render(); };
    tabsEl.appendChild(addTab);

    if (activeId === "__horario__") { renderHorario(); return; }
    if (activeId === "__new__") { renderNewDiscipline(); return; }
    const disc = state.disciplines.find((d) => d.id === activeId);
    if (!disc) { contentEl.innerHTML = "<p class='empty'>Sem disciplinas. Cria uma.</p>"; return; }
    renderDiscipline(disc);
  }

  const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];
  function normDia(w) {
    const s = (w || "").trim().toLowerCase();
    if (s.startsWith("seg")) return "Segunda";
    if (s.startsWith("ter")) return "Terça";
    if (s.startsWith("qua")) return "Quarta";
    if (s.startsWith("qui")) return "Quinta";
    if (s.startsWith("sex")) return "Sexta";
    if (s.startsWith("sáb") || s.startsWith("sab")) return "Sábado";
    return w || "";
  }

  async function renderHorario() {
    contentEl.innerHTML = `<div class="panel"><h2>Horário semanal</h2>
      <p class="empty">A carregar...</p></div>`;
    let classes = [];
    try { classes = (await api("GET", "/api/horario")).classes || []; }
    catch (e) { classes = []; }

    // Agrupa por dia.
    const porDia = {};
    DIAS.forEach((d) => (porDia[d] = []));
    classes.forEach((c) => {
      const dia = normDia(c.weekday);
      if (!porDia[dia]) porDia[dia] = [];
      porDia[dia].push(c);
    });

    let grelha = `<div class="panel"><h2>Horário semanal</h2>`;
    if (!classes.length) {
      grelha += `<p class="empty">Sem aulas ainda. Importa o teu horário em baixo ou adiciona aulas em cada disciplina.</p>`;
    } else {
      grelha += `<div class="hgrid">`;
      DIAS.forEach((dia) => {
        const aulas = (porDia[dia] || []).slice().sort((a, b) => (a.start || "").localeCompare(b.start || ""));
        grelha += `<div class="hday"><div class="hday-title">${dia}</div><div class="hday-body">`;
        if (!aulas.length) {
          grelha += `<div class="hday-empty">sem aulas</div>`;
        } else {
          aulas.forEach((c) => {
            const hora = [c.start, c.end].filter(Boolean).join(" – ");
            const sala = c.room ? `<span class="room">🚪 ${esc(c.room)}</span>` : "";
            grelha += `<div class="haula">
              <span class="when">${esc(hora || "—")}</span>
              <span class="name">${esc(c.discipline)}</span>
              ${sala}
            </div>`;
          });
        }
        grelha += `</div></div>`;
      });
      grelha += `</div>`;
    }
    grelha += `</div>`;

    // Painel de importação.
    grelha += `
      <div class="panel">
        <h2>Importar horário de imagem/PDF</h2>
        <p class="empty">Anexa uma foto ou PDF do teu horário. O JARVIS lê e
        propõe as aulas; tu confirmas antes de gravar.</p>
        <form class="add-row" id="impForm">
          <input type="file" id="horFile" accept=".png,.jpg,.jpeg,.gif,.webp,.pdf" required />
          <button class="btn" type="submit">Ler horário</button>
        </form>
        <div id="propostaWrap"></div>
      </div>`;

    contentEl.innerHTML = grelha;
    document.getElementById("impForm").onsubmit = importarHorario;
  }

  async function importarHorario(e) {
    e.preventDefault();
    const input = document.getElementById("horFile");
    const wrap = document.getElementById("propostaWrap");
    const f = input.files && input.files[0];
    if (!f) return;
    wrap.innerHTML = `<p class="empty">A ler o horário... (pode demorar uns segundos)</p>`;
    const fd = new FormData();
    fd.append("file", f);
    let data;
    try {
      const r = await fetch("/api/horario/extrair", { method: "POST", body: fd });
      data = await r.json();
      if (!r.ok) throw new Error(data.error || "Erro");
    } catch (err) {
      wrap.innerHTML = `<p class="empty">Não consegui ler: ${esc(err.message)}</p>`;
      return;
    }
    renderProposta(data.classes || [], wrap);
  }

  function renderProposta(classes, wrap) {
    if (!classes.length) { wrap.innerHTML = `<p class="empty">Nenhuma aula detetada.</p>`; return; }
    // Tabela editável: cada linha é uma aula proposta.
    let html = `<h2 style="margin-top:14px">Proposta (${classes.length} aulas) — revê e corrige</h2>
      <div id="propRows">`;
    classes.forEach((c, i) => {
      html += `<div class="add-row proprow" data-i="${i}" style="margin-bottom:6px">
        <input name="discipline" value="${esc(c.discipline)}" placeholder="Disciplina" class="grow" />
        <input name="weekday" value="${esc(c.weekday)}" placeholder="Dia" style="max-width:100px" />
        <input name="start" value="${esc(c.start)}" placeholder="Início" type="time" />
        <input name="end" value="${esc(c.end)}" placeholder="Fim" type="time" />
        <input name="room" value="${esc(c.room)}" placeholder="Sala" style="max-width:90px" />
        <button class="btn del" type="button" data-rm="${i}">✕</button>
      </div>`;
    });
    html += `</div>
      <button class="btn" id="confirmImp" style="margin-top:8px">Confirmar e gravar</button>`;
    wrap.innerHTML = html;

    wrap.querySelectorAll("[data-rm]").forEach((b) => {
      b.onclick = () => { b.closest(".proprow").remove(); };
    });
    document.getElementById("confirmImp").onclick = async () => {
      const rows = [...wrap.querySelectorAll(".proprow")].map((row) => {
        const g = (n) => row.querySelector(`[name=${n}]`).value.trim();
        return { discipline: g("discipline"), weekday: g("weekday"),
                 start: g("start"), end: g("end"), room: g("room") };
      }).filter((r) => r.discipline && r.weekday);
      if (!rows.length) { toast("Nada para gravar."); return; }
      try {
        const res = await api("POST", "/api/horario/aplicar", { classes: rows });
        toast(`Gravadas ${res.gravadas} aulas.`);
        await load();            // recarrega disciplinas (podem ter sido criadas)
        activeId = "__horario__"; render();
      } catch (err) { toast(err.message); }
    };
  }

  function renderNewDiscipline() {
    contentEl.innerHTML = `
      <div class="panel">
        <h2>Nova disciplina</h2>
        <form class="add-row" id="newDiscForm">
          <input class="grow" name="name" placeholder="Nome da disciplina" required />
          <input name="teacher" placeholder="Professor (opcional)" />
          <input name="email" placeholder="Email (opcional)" />
          <button class="btn" type="submit">Criar</button>
        </form>
      </div>`;
    document.getElementById("newDiscForm").onsubmit = async (e) => {
      e.preventDefault();
      const f = e.target;
      try {
        const disc = await api("POST", "/api/cursos", {
          name: f.name.value.trim(),
          teacher: f.teacher.value.trim(),
          email: f.email.value.trim(),
        });
        toast("Disciplina criada.");
        await load();
        activeId = disc.id; render();
      } catch (err) { toast(err.message); }
    };
  }

  function listSection(disc, kind, title, opts) {
    // opts: { render(entry)->{when,txt}, form: [fields], toggle: bool }
    const items = disc[kind] || [];
    let html = `<div class="panel"><h2>${title} ${items.length ? '<span class="count">('+items.length+')</span>' : ''}</h2><ul>`;
    if (!items.length) html += `<li class="empty">Nada registado.</li>`;
    items.forEach((e) => {
      const r = opts.render(e);
      const doneCls = e.done ? " done" : "";
      html += `<li class="${doneCls}">`;
      if (r.when) html += `<span class="when">${esc(r.when)}</span>`;
      html += `<span class="txt">${esc(r.txt)}</span>`;
      if (opts.grade) {
        const g = e.grade ? esc(e.grade) : "—";
        html += `<span class="grade" data-grade="${kind}:${e.id}" title="Definir nota">${g}</span>`;
      }
      if (opts.toggle) html += `<button class="btn" data-toggle="${kind}:${e.id}">${e.done ? "↺" : "✓"}</button>`;
      html += `<button class="btn del" data-del="${kind}:${e.id}">✕</button>`;
      html += `</li>`;
    });
    html += `</ul>${opts.formHtml}</div>`;
    return html;
  }

  function renderDiscipline(disc) {
    const teacher = disc.teacher || "—";
    const email = disc.email ? `<a href="mailto:${esc(disc.email)}">${esc(disc.email)}</a>` : "—";
    contentEl.innerHTML = `
      <div class="panel">
        <div class="disc-head">
          <span class="name">${esc(disc.name)}</span>
          <span class="meta">Prof.: ${esc(teacher)} · ${email}</span>
        </div>
        <form class="add-row" id="metaForm" style="margin-top:10px">
          <input name="teacher" placeholder="Professor" value="${esc(disc.teacher)}" />
          <input name="email" placeholder="Email" value="${esc(disc.email)}" />
          <button class="btn" type="submit">Guardar</button>
          <button class="btn del" type="button" id="delDisc">Apagar disciplina</button>
        </form>
      </div>
      <div class="panel">
        <h2>Horário</h2>
        <ul>
          ${(disc.schedule || []).length ? "" : '<li class="empty">Sem aulas registadas.</li>'}
          ${(disc.schedule || []).map((a) => {
            const hora = [a.start, a.end].filter(Boolean).join("–");
            const sala = a.room ? ` · ${esc(a.room)}` : "";
            const quando = [esc(a.weekday), esc(hora)].filter(Boolean).join(" ");
            return `<li><span class="txt">${quando}${sala}</span>
              <button class="btn del" data-del="schedule:${a.id}">✕</button></li>`;
          }).join("")}
        </ul>
        <form class="add-row" data-add="schedule">
          <input name="weekday" placeholder="Dia (ex.: Segunda)" required style="min-width:120px" />
          <input type="time" name="start" title="Início" />
          <input type="time" name="end" title="Fim" />
          <input name="room" placeholder="Sala (opcional)" />
          <button class="btn" type="submit">+ Aula</button>
        </form>
      </div>
      <div class="panel">
        <h2>Classificações</h2>
        <ul>
          ${(disc.grades || []).length ? "" : '<li class="empty">Sem classificações.</li>'}
          ${(disc.grades || []).map((g) =>
            `<li><span class="txt">${esc(g.label)}</span>
              <span class="grade-static">${esc(g.value)}</span>
              <button class="btn del" data-del="grades:${g.id}">✕</button></li>`
          ).join("")}
        </ul>
        <form class="add-row" data-addgrade="1">
          <input class="grow" name="label" placeholder="Nome (ex.: Teste 1, Ficha)" required />
          <input name="value" placeholder="Nota" required style="max-width:90px" />
          <button class="btn" type="submit">+ Nota</button>
        </form>
      </div>
      <div class="grid">
        ${listSection(disc, "tests", "Testes", {
          toggle: true, grade: true,
          render: (e) => ({ when: e.date, txt: e.title || "Teste" }),
          formHtml: `<form class="add-row" data-add="tests">
            <input type="date" name="date" required />
            <input class="grow" name="title" placeholder="Descrição (opcional)" />
            <button class="btn" type="submit">+ Teste</button></form>`,
        })}
        ${listSection(disc, "tasks", "Trabalhos de grupo", {
          toggle: true, grade: true,
          render: (e) => ({ when: e.deadline, txt: e.title || "Trabalho" }),
          formHtml: `<form class="add-row" data-add="tasks">
            <input type="date" name="deadline" required />
            <input class="grow" name="title" placeholder="Descrição (opcional)" />
            <button class="btn" type="submit">+ Trabalho</button></form>`,
        })}
        ${listSection(disc, "absences", "Faltas", {
          toggle: false,
          render: (e) => ({ when: e.date, txt: e.reason || "Falta" }),
          formHtml: `<form class="add-row" data-add="absences">
            <input type="date" name="date" required />
            <input class="grow" name="reason" placeholder="Motivo (opcional)" />
            <button class="btn" type="submit">+ Falta</button></form>`,
        })}
        ${listSection(disc, "notes", "Apontamentos", {
          toggle: false,
          render: (e) => ({ when: (e.t || "").slice(0, 10), txt: e.text }),
          formHtml: `<form class="add-row" data-add="notes">
            <input class="grow" name="text" placeholder="Escrever apontamento..." required />
            <button class="btn" type="submit">+ Nota</button></form>`,
        })}
      </div>
      <div class="panel">
        <h2>Materiais / Aulas (PowerPoint, PDF)</h2>
        <ul id="matList">
          ${(disc.materials || []).length ? "" : '<li class="empty">Sem materiais. Anexa um PPT ou PDF de uma aula.</li>'}
          ${(disc.materials || []).map((m) => `
            <li class="matrow" data-mat="${m.id}">
              <div style="flex:1">
                <span class="when">${esc(m.date)}</span>
                <span class="txt">${esc(m.title)}</span>
                <span class="room">(${m.chars || 0} caract.)</span>
                <div class="matsummary">${m.summary ? esc(m.summary) : ""}</div>
              </div>
              <button class="btn" data-resumir="${m.id}">${m.summary ? "Ver resumo" : "Resumir"}</button>
              <button class="btn del" data-del="materials:${m.id}">✕</button>
            </li>`).join("")}
        </ul>
        <form class="add-row" id="matForm">
          <input type="file" id="matFile" accept=".pptx,.ppt,.pdf,.txt,.md" required />
          <input name="title" placeholder="Título da aula (opcional)" class="grow" />
          <button class="btn" type="submit">+ Guardar aula</button>
        </form>
      </div>`;

    // Save teacher/email.
    document.getElementById("metaForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api("POST", `/api/cursos/${disc.id}/update`, {
          teacher: e.target.teacher.value.trim(),
          email: e.target.email.value.trim(),
        });
        toast("Guardado."); await load(true);
      } catch (err) { toast(err.message); }
    };
    // Delete discipline.
    document.getElementById("delDisc").onclick = async () => {
      if (!confirm(`Apagar a disciplina "${disc.name}" e todos os seus dados?`)) return;
      try { await api("POST", `/api/cursos/${disc.id}/delete`); toast("Disciplina apagada."); await load(); }
      catch (err) { toast(err.message); }
    };
    // Anexar material (PPT/PDF) -> guarda o texto na disciplina.
    const matForm = document.getElementById("matForm");
    if (matForm) matForm.onsubmit = async (e) => {
      e.preventDefault();
      const fileEl = document.getElementById("matFile");
      const f = fileEl.files && fileEl.files[0];
      if (!f) return;
      const fd = new FormData();
      fd.append("file", f);
      fd.append("title", matForm.title.value.trim());
      toast("A guardar a aula...");
      try {
        const r = await fetch(`/api/cursos/${disc.id}/material`, { method: "POST", body: fd });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || "Erro");
        toast("Aula guardada.");
        await load(true);
      } catch (err) { toast(err.message); }
    };
    // Resumir um material (gera e guarda; se já tiver resumo, mostra-o).
    contentEl.querySelectorAll("[data-resumir]").forEach((b) => {
      b.onclick = async () => {
        const mid = b.getAttribute("data-resumir");
        const row = b.closest(".matrow");
        const box = row && row.querySelector(".matsummary");
        if (box && box.textContent.trim()) { // já mostrado
          box.classList.toggle("open");
          return;
        }
        b.disabled = true; b.textContent = "A resumir...";
        try {
          const res = await api("POST", `/api/cursos/${disc.id}/material/${mid}/resumir`);
          if (box) { box.textContent = res.summary; box.classList.add("open"); }
          b.textContent = "Ver resumo"; b.disabled = false;
          toast(res.cached ? "Resumo (já guardado)." : "Resumo gerado e guardado.");
        } catch (err) { b.disabled = false; b.textContent = "Resumir"; toast(err.message); }
      };
    });
    // Add-entry forms.
    contentEl.querySelectorAll("form[data-add]").forEach((form) => {
      form.onsubmit = async (e) => {
        e.preventDefault();
        const kind = form.getAttribute("data-add");
        const body = {};
        form.querySelectorAll("input").forEach((i) => { if (i.name) body[i.name] = i.value.trim(); });
        try { await api("POST", `/api/cursos/${disc.id}/${kind}`, body); toast("Adicionado."); await load(true); }
        catch (err) { toast(err.message); }
      };
    });
    // Toggle done / delete entries.
    contentEl.querySelectorAll("[data-toggle]").forEach((b) => {
      b.onclick = async () => {
        const [kind, id] = b.getAttribute("data-toggle").split(":");
        try { await api("POST", `/api/cursos/${disc.id}/${kind}/${id}/toggle`); await load(true); }
        catch (err) { toast(err.message); }
      };
    });
    contentEl.querySelectorAll("[data-del]").forEach((b) => {
      b.onclick = async () => {
        const [kind, id] = b.getAttribute("data-del").split(":");
        try { await api("POST", `/api/cursos/${disc.id}/${kind}/${id}/delete`); await load(true); }
        catch (err) { toast(err.message); }
      };
    });
    // Add a standalone grade (classificação).
    const gForm = contentEl.querySelector("form[data-addgrade]");
    if (gForm) gForm.onsubmit = async (e) => {
      e.preventDefault();
      const body = { label: gForm.label.value.trim(), value: gForm.value.value.trim() };
      try { await api("POST", `/api/cursos/${disc.id}/grades`, body); toast("Nota adicionada."); await load(true); }
      catch (err) { toast(err.message); }
    };
    // Set a grade on a test/task (click the grade badge -> prompt).
    contentEl.querySelectorAll("[data-grade]").forEach((el) => {
      el.onclick = async () => {
        const [kind, id] = el.getAttribute("data-grade").split(":");
        const current = el.textContent === "—" ? "" : el.textContent;
        const val = prompt("Nota:", current);
        if (val === null) return; // cancelou
        try { await api("POST", `/api/cursos/${disc.id}/${kind}/${id}/grade`, { grade: val.trim() }); await load(true); }
        catch (err) { toast(err.message); }
      };
    });
  }

  load().catch((e) => { contentEl.innerHTML = `<p class='empty'>Erro a carregar: ${e.message}</p>`; });
})();
