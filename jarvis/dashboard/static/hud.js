// Copyright (c) 2026 Tiago Pereira. All rights reserved.
// JARVIS HUD front-end: WebSocket client + canvas core/radar + waveform.
(function () {
  "use strict";

  // ---- element handles ----
  const $ = (id) => document.getElementById(id);
  const els = {
    statusdot: $("statusdot"), statustext: $("statustext"), modeltext: $("modeltext"),
    clock: $("clock"),
    cpuBig: $("cpuBig"), cpuTxt: $("cpuTxt"), uptime: $("uptime"),
    cpuPct: $("cpuPct"), cpuBar: $("cpuBar"),
    memPct: $("memPct"), memBar: $("memBar"),
    diskPct: $("diskPct"), diskBar: $("diskBar"),
    osName: $("osName"), sensors: $("sensors"),
    skillCount: $("skillCount"), brainState: $("brainState"),
    coreState: $("coreState"), vitStatus: $("vitStatus"),
    log: $("log"), cmd: $("cmd"), cmdform: $("cmdform"),
    voicebtn: $("voicebtn"), voiceicon: $("voiceicon"),
    weatherTile: $("weatherTile"), newsTile: $("newsTile"),
  };

  // ---- Text-to-speech (browser Web Speech API) ----
  // JARVIS reads its replies aloud. Runs entirely client-side: no server audio,
  // no extra deps. Degrades silently if the browser lacks speechSynthesis.
  const tts = {
    on: true,
    supported: "speechSynthesis" in window,
    voice: null,
  };
  function pickVoice() {
    if (!tts.supported) return;
    const voices = window.speechSynthesis.getVoices();
    if (!voices.length) return;
    // Prefer an English, ideally British ("JARVIS") male-ish voice if present.
    tts.voice =
      voices.find((v) => /en-GB/i.test(v.lang) && /male|daniel|arthur/i.test(v.name)) ||
      voices.find((v) => /en-GB/i.test(v.lang)) ||
      voices.find((v) => /^en/i.test(v.lang)) ||
      voices[0];
  }
  if (tts.supported) {
    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;
  }
  function speak(text) {
    if (!tts.on || !tts.supported || !text) return;
    try {
      window.speechSynthesis.cancel(); // don't stack utterances
      const u = new SpeechSynthesisUtterance(text);
      if (tts.voice) u.voice = tts.voice;
      u.rate = 1.02; u.pitch = 0.9; // calm, slightly low — butler-ish
      window.speechSynthesis.speak(u);
    } catch (e) { /* speech is a nicety; never break on it */ }
  }
  function updateVoiceBtn() {
    els.voicebtn.classList.toggle("off", !tts.on);
    els.voiceicon.innerHTML = tts.on ? "&#128266;" : "&#128263;"; // speaker / muted
  }
  els.voicebtn.addEventListener("click", () => {
    tts.on = !tts.on;
    if (!tts.on && tts.supported) window.speechSynthesis.cancel();
    updateVoiceBtn();
    logLine("sys", tts.on ? "Voice output enabled." : "Voice output muted.");
  });
  if (!tts.supported) {
    els.voicebtn.classList.add("off");
    els.voicebtn.title = "Speech synthesis not supported in this browser";
  }

  // ---- activity log ----
  function stamp() {
    const d = new Date();
    return d.toTimeString().slice(0, 8);
  }
  function logLine(who, text) {
    const div = document.createElement("div");
    const cls = who === "you" ? "u" : who === "sys" ? "t" : "j";
    const label = who === "you" ? "USER" : who === "sys" ? "SYS " : "JVIS";
    div.innerHTML = `<span class="t">${stamp()}</span> ` +
      `<span class="${cls}">[${label}]</span> ` +
      `<span class="${who === "you" ? "u" : "j"}"></span>`;
    div.lastElementChild.textContent = text; // textContent = no HTML injection
    els.log.appendChild(div);
    els.log.scrollTop = els.log.scrollHeight;
    // Keep the log from growing without bound.
    while (els.log.childElementCount > 200) els.log.removeChild(els.log.firstChild);
  }

  // Streaming reply: keep a handle to the current JARVIS line and append to it
  // as deltas arrive, so the reply "types out" in the log.
  let streamEl = null;
  function streamDelta(text) {
    if (!streamEl) {
      const div = document.createElement("div");
      div.innerHTML = `<span class="t">${stamp()}</span> ` +
        `<span class="j">[JVIS]</span> <span class="j"></span>`;
      streamEl = div.lastElementChild;
      els.log.appendChild(div);
    }
    streamEl.textContent += text; // textContent = no HTML injection
    els.log.scrollTop = els.log.scrollHeight;
  }
  function streamEnd() { streamEl = null; }

  function fmtUptime(s) {
    if (s == null) return "--";
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return `${h}h ${m}m ${sec}s`;
  }

  function setBar(barEl, pctEl, value) {
    if (value == null) {
      pctEl.textContent = "n/a";
      barEl.style.width = "0%";
      return;
    }
    pctEl.textContent = value + "%";
    barEl.style.width = Math.max(0, Math.min(100, value)) + "%";
  }

  // ---- WebSocket ----
  let ws = null;
  let activity = 0; // 0..1 drives the core/wave energy; decays over time.

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      els.statusdot.classList.remove("off");
      els.statustext.textContent = "OPTIMAL";
      logLine("sys", "Connection established.");
    };
    ws.onclose = () => {
      els.statusdot.classList.add("off");
      els.statustext.textContent = "OFFLINE";
      els.brainState.textContent = "DISCONNECTED";
      logLine("sys", "Connection lost. Reconnecting in 3s...");
      setTimeout(connect, 3000);
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      switch (msg.type) {
        case "hello":
          els.skillCount.textContent = (msg.skills || []).length;
          els.brainState.textContent = msg.online ? "ONLINE" : "LIMITED";
          els.brainState.style.color = msg.online ? "var(--ok)" : "var(--warn)";
          els.modeltext.textContent = msg.online && msg.model ? msg.model : "OFFLINE MODE";
          logLine("sys", `JARVIS ${msg.online ? "online" : "in limited mode"}. ` +
            `${(msg.skills || []).length} skills ready.`);
          break;
        case "stats":
          els.clock.textContent = msg.time || "--:--:--";
          els.cpuBig.textContent = msg.cpu == null ? "--" : msg.cpu;
          els.cpuTxt.textContent = msg.cpu == null ? "n/a" : msg.cpu + "%";
          els.uptime.textContent = fmtUptime(msg.uptime_seconds);
          els.osName.textContent = msg.system || "--";
          els.sensors.textContent = msg.has_psutil ? "NOMINAL" : "LIMITED";
          setBar(els.cpuBar, els.cpuPct, msg.cpu);
          setBar(els.memBar, els.memPct, msg.memory);
          setBar(els.diskBar, els.diskPct, msg.disk);
          break;
        case "user":
          logLine("you", msg.text);
          activity = 1;
          break;
        case "tiles":
          // textContent = no HTML injection from feed/skill content.
          if (els.weatherTile) els.weatherTile.textContent = msg.weather || "—";
          if (els.newsTile) els.newsTile.textContent = msg.news || "—";
          break;
        case "history":
          // Replay persisted past turns so the log reflects prior sessions.
          (msg.turns || []).forEach((turn) => {
            logLine(turn.who === "user" ? "you" : "jarvis", turn.text);
          });
          logLine("sys", "— end of earlier conversation —");
          break;
        case "reply_delta":
          streamDelta(msg.text);
          els.coreState.textContent = "ACTIVE";
          activity = Math.max(activity, 0.85);
          break;
        case "reply_done":
          streamEnd();
          speak(msg.text); // speak the complete reply once, when done
          break;
        case "reply": // legacy single-shot (kept for compatibility)
          logLine("jarvis", msg.text);
          els.coreState.textContent = "ACTIVE";
          activity = Math.max(activity, 0.85);
          speak(msg.text);
          break;
      }
    };
  }

  function send(text) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "command", text }));
    } else {
      logLine("sys", "Not connected — command dropped.");
    }
  }

  els.cmdform.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = els.cmd.value.trim();
    if (!text) return;
    // Barge-in: cut off any reply still being spoken when a new command is sent.
    if (tts.supported) window.speechSynthesis.cancel();
    send(text);
    els.cmd.value = "";
  });

  // ---- Anexos (imagem / PDF / texto) ----
  (function setupAttach() {
    const btn = document.getElementById("attachbtn");
    const input = document.getElementById("fileinput");
    if (!btn || !input) return;
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", async () => {
      const f = input.files && input.files[0];
      if (!f) return;
      const prompt = els.cmd.value.trim(); // texto na barra vira a pergunta
      els.cmd.value = "";
      logLine("you", `📎 ${f.name}${prompt ? " — " + prompt : ""}`);
      logLine("sys", "A ler o anexo...");
      const fd = new FormData();
      fd.append("file", f);
      fd.append("prompt", prompt);
      try {
        const r = await fetch("/api/anexo", { method: "POST", body: fd });
        const data = await r.json();
        if (data.reply) {
          logLine("jarvis", data.reply);
          speak(data.reply);
        } else {
          logLine("sys", data.error || "Não consegui ler o anexo.");
        }
      } catch (err) {
        logLine("sys", "Erro a enviar o anexo.");
      }
      input.value = ""; // permite reenviar o mesmo ficheiro
    });
  })();

  // ---- Click-to-talk (browser Web Speech API speech recognition) ----
  // Transcribes a spoken phrase into the command bar and submits it. Uses the
  // browser's SpeechRecognition (Chrome/Edge/Safari). Hidden if unsupported.
  (function setupMic() {
    const micbtn = document.getElementById("micbtn");
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR || !micbtn) {
      if (micbtn) micbtn.classList.add("hidden");
      return;
    }
    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    let listening = false;

    micbtn.addEventListener("click", () => {
      if (listening) { rec.stop(); return; }
      // Barge-in: stop JARVIS talking so it doesn't hear itself.
      if (tts.supported) window.speechSynthesis.cancel();
      try { rec.start(); } catch (e) { /* already starting */ }
    });
    rec.onstart = () => {
      listening = true;
      micbtn.classList.add("listening");
      els.cmd.placeholder = "LISTENING...";
    };
    rec.onend = () => {
      listening = false;
      micbtn.classList.remove("listening");
      els.cmd.placeholder = "AWAITING COMMAND...";
    };
    rec.onerror = () => { logLine("sys", "Voice input error."); };
    rec.onresult = (ev) => {
      const said = (ev.results[0] && ev.results[0][0] && ev.results[0][0].transcript || "").trim();
      if (said) {
        logLine("you", said);
        send(said);
      }
    };
  })();

  // ---- Core + radar animation ----
  const core = $("core");
  const cx = core.getContext("2d");
  const CW = core.width, CH = core.height, C = CW / 2;
  let t = 0;

  function drawCore() {
    t += 0.016;
    activity *= 0.985; // decay toward idle
    const energy = 0.35 + activity * 0.65;
    cx.clearRect(0, 0, CW, CH);

    // Rotating radar sweep.
    const sweep = (t * 0.6) % (Math.PI * 2);
    const grad = cx.createConicGradient
      ? cx.createConicGradient(sweep, C, C)
      : null;
    if (grad) {
      grad.addColorStop(0, "rgba(70,214,228,0.28)");
      grad.addColorStop(0.08, "rgba(70,214,228,0.0)");
      grad.addColorStop(1, "rgba(70,214,228,0.0)");
      cx.fillStyle = grad;
      cx.beginPath(); cx.arc(C, C, 200, 0, Math.PI * 2); cx.fill();
    }

    // Concentric rings.
    cx.strokeStyle = "rgba(70,214,228,0.18)";
    cx.lineWidth = 1;
    for (const r of [70, 120, 170, 200]) {
      cx.beginPath(); cx.arc(C, C, r, 0, Math.PI * 2); cx.stroke();
    }
    // Cross hairs.
    cx.beginPath();
    cx.moveTo(C - 200, C); cx.lineTo(C + 200, C);
    cx.moveTo(C, C - 200); cx.lineTo(C, C + 200);
    cx.stroke();

    // Sweep line.
    cx.save();
    cx.translate(C, C); cx.rotate(sweep);
    cx.strokeStyle = "rgba(70,214,228,0.7)";
    cx.lineWidth = 2;
    cx.beginPath(); cx.moveTo(0, 0); cx.lineTo(200, 0); cx.stroke();
    cx.restore();

    // Two counter-rotating dashed rings.
    for (let k = 0; k < 2; k++) {
      cx.save();
      cx.translate(C, C);
      cx.rotate((k ? -t : t) * 0.5);
      cx.strokeStyle = "rgba(70,214,228,0.5)";
      cx.setLineDash([6, 14]);
      cx.lineWidth = 2;
      cx.beginPath(); cx.arc(0, 0, 95 + k * 18, 0, Math.PI * 2); cx.stroke();
      cx.setLineDash([]);
      cx.restore();
    }

    // Pulsing core orb.
    const pulse = 40 + Math.sin(t * 3) * 4 * energy;
    const glow = cx.createRadialGradient(C, C, 4, C, C, pulse + 30);
    glow.addColorStop(0, `rgba(120,240,250,${0.55 * energy})`);
    glow.addColorStop(0.5, `rgba(70,214,228,${0.25 * energy})`);
    glow.addColorStop(1, "rgba(70,214,228,0)");
    cx.fillStyle = glow;
    cx.beginPath(); cx.arc(C, C, pulse + 30, 0, Math.PI * 2); cx.fill();
    cx.fillStyle = `rgba(150,245,255,${0.85 * energy})`;
    cx.beginPath(); cx.arc(C, C, 10 + energy * 4, 0, Math.PI * 2); cx.fill();

    requestAnimationFrame(drawCore);
  }
  requestAnimationFrame(drawCore);

  // ---- Waveform (idle shimmer, spikes on activity) ----
  const wave = $("wave");
  const wx = wave.getContext("2d");
  const WW = wave.width, WH = wave.height;
  function drawWave() {
    wx.clearRect(0, 0, WW, WH);
    wx.strokeStyle = "rgba(70,214,228,0.8)";
    wx.lineWidth = 2;
    wx.beginPath();
    const bars = 40;
    for (let i = 0; i < bars; i++) {
      const x = (i / (bars - 1)) * WW;
      const base = Math.sin(t * 4 + i * 0.5) * (2 + activity * 9);
      const h = Math.abs(base) + 1;
      wx.moveTo(x, WH / 2 - h);
      wx.lineTo(x, WH / 2 + h);
    }
    wx.stroke();
    requestAnimationFrame(drawWave);
  }
  requestAnimationFrame(drawWave);

  // Live clock between server ticks so it never looks frozen.
  setInterval(() => {
    if (els.statustext.textContent === "OFFLINE") return;
    els.clock.textContent = new Date().toTimeString().slice(0, 8);
  }, 1000);

  connect();
})();
