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

    if (activeId === "__new__") { renderNewDiscipline(); return; }
    const disc = state.disciplines.find((d) => d.id === activeId);
    if (!disc) { contentEl.innerHTML = "<p class='empty'>Sem disciplinas. Cria uma.</p>"; return; }
    renderDiscipline(disc);
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
