// Débat d'IA : Nova (pour) contre Aurora (contre). L'utilisateur regarde et intervient seulement s'il le veut.
// Le débat est gardé ici (sur le téléphone) ; le serveur ne fait que donner la réplique suivante.
"use strict";

(function () {
  const IDEAS = ["Faut-il interdire les devoirs à la maison ?", "Mieux vaut vivre en ville ou à la campagne ?",
    "Le télétravail, bonne ou mauvaise idée ?", "Les réseaux sociaux nous rendent-ils plus heureux ?",
    "Faut-il apprendre à coder à l'école ?", "Les voitures électriques sont-elles l'avenir ?"];
  const NAMES = { nova: "Nova · pour", aurora: "Aurora · contre", user: "Toi", verdict: "Verdict" };
  const THINK = /<think>[\s\S]*?(<\/think>|$)/g;
  // L'IA recopie parfois l'étiquette de la transcription (« Toi (Nova) : … ») : on l'enlève.
  const LABEL = /^\s*(?:Toi|Nova|Aurora)\b[^:\n]{0,40}:\s*/;
  const clean = (t) => t.replace(THINK, "").trim().replace(LABEL, "");
  const D = { topic: "", turns: [], target: 6, running: false, paused: false, busy: false, controller: null,
    verdictDone: false, wantVerdict: false };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const aiCount = () => D.turns.filter((t) => t.who !== "user").length;

  function status(text) { $("#debate-status").textContent = text || ""; }

  function bubble(who) {
    const box = node("div", "debate-turn " + who);
    const p = node("p", "debate-text");
    box.append(node("span", "debate-who", NAMES[who]), p);
    $("#debate-log").append(box);
    scrollLog();
    return p;
  }
  function scrollLog() { const l = $("#debate-log"); l.scrollTop = l.scrollHeight; }

  function setButtons() {
    const finished = aiCount() >= D.target;
    const pause = $("#debate-pause");
    pause.classList.toggle("hidden", finished);
    Icons.set(pause, D.paused ? "play" : "pause", D.paused ? "Reprendre" : "Pause");
    $("#debate-more").classList.toggle("hidden", !finished || D.busy);
    $("#debate-verdict").disabled = aiCount() < 2 || D.verdictDone && aiCount() >= D.target;
  }

  // Lit la réponse du serveur (flux d'événements) et l'écrit au fur et à mesure.
  async function turn(speaker) {
    D.busy = true;
    setButtons();
    D.controller = new AbortController();
    const who = speaker || (D.turns.filter((t) => t.who !== "user").slice(-1)[0]?.who === "nova" ? "aurora" : "nova");
    status(who === "verdict" ? "L'arbitre fait le bilan…" : (who === "nova" ? "Nova" : "Aurora") + " réfléchit…");
    let p = null, raw = "", ok = false;
    try {
      const res = await fetch("/api/debate/turn", {
        method: "POST", credentials: "same-origin", signal: D.controller.signal,
        headers: { "Content-Type": "application/json", "X-Syrius": "1" },
        body: JSON.stringify({ topic: D.topic, turns: D.turns, speaker: who }),
      });
      if (res.status === 401) { showLogin(); return false; }
      if (!res.ok) {
        let msg = `Erreur ${res.status}`;
        try { msg = (await res.json()).detail || msg; } catch (_) { /* ignore */ }
        throw new Error(msg);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          if (!chunk.startsWith("data: ")) continue;
          let ev;
          try { ev = JSON.parse(chunk.slice(6)); } catch (_) { continue; }
          if (ev.type === "start") { p = bubble(who); status(""); }
          else if (ev.type === "text") {
            raw += ev.text;
            if (p) { p.textContent = clean(raw); scrollLog(); }
          } else if (ev.type === "done") ok = true;
          else if (ev.type === "error") throw new Error(ev.message || "Erreur.");
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") status("⚠ " + (err.message || "Connexion perdue."));
      if (p && !raw) p.parentElement.remove();
      ok = false;
    } finally {
      D.busy = false;
      D.controller = null;
    }
    const text = clean(raw);
    if (!ok || !text) { setButtons(); return false; }
    if (who !== "verdict") D.turns.push({ who, text });
    else D.verdictDone = true;
    setButtons();
    if ($("#debate-voice").checked) {
      speak(text);
      await wait(Math.min(40000, Math.max(1500, text.length * 65)));  // laisse le temps de l'écouter
    }
    return true;
  }

  async function run() {
    if (D.running) return;
    D.running = true;
    while (!D.paused && aiCount() < D.target && $("#debate").open) {
      if (!(await turn())) { D.paused = true; break; }
      await wait(900);
    }
    D.running = false;
    setButtons();
    await answerUser();  // une intervention arrivée pendant la dernière réplique
    if (D.wantVerdict || (aiCount() >= D.target && !D.verdictDone && !D.paused)) await verdict();
    else if (D.paused && !D.busy) status("En pause. Touche « Reprendre » pour continuer.");
  }

  async function verdict() {
    D.wantVerdict = false;
    status("");
    if (await turn("verdict"))
      status(aiCount() >= D.target ? "Le débat est fini. Tu peux encore intervenir, demander un tour de plus, ou en lancer un nouveau."
        : "Tu peux encore intervenir, ou toucher « Reprendre ».");
  }

  // Ce que tu dis reçoit toujours une réponse, même quand le débat est en pause ou fini.
  async function answerUser() {
    if (D.running || D.busy) return;
    while (D.turns.length && D.turns[D.turns.length - 1].who === "user") {
      if (!(await turn())) break;
    }
  }

  function start(topic) {
    D.topic = topic;
    D.turns = [];
    D.target = 2 * Number($("#debate-rounds").value || 3);
    D.paused = false;
    D.verdictDone = false;
    $("#debate-log").replaceChildren();
    $("#debate-title").textContent = "« " + topic + " »";
    $("#debate-setup").classList.add("hidden");
    $("#debate-live").classList.remove("hidden");
    status("");
    run();
  }

  function stopCurrent() {
    D.paused = true;
    D.wantVerdict = false;
    if (D.controller) D.controller.abort();
  }

  // ---------------------------------------------------------------- interactions
  $("#debate-setup").addEventListener("submit", (e) => {
    e.preventDefault();
    const topic = $("#debate-topic").value.trim();
    if (topic.length >= 3) start(topic);
  });
  const ideas = $("#debate-ideas");
  for (const idea of IDEAS) {
    const b = node("button", "debate-idea", idea);
    b.type = "button";
    b.addEventListener("click", () => { $("#debate-topic").value = idea; $("#debate-topic").focus(); });
    ideas.append(b);
  }

  $("#debate-say").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("#debate-input").value.trim();
    if (!text) return;
    $("#debate-input").value = "";
    D.turns.push({ who: "user", text });
    bubble("user").textContent = text;
    // Débat en cours : l'IA suivante te répondra d'elle-même. En pause ou fini : elle te répond tout de suite.
    await answerUser();
    if (D.paused && !D.running && !D.busy) status("En pause. Touche « Reprendre » pour relancer le débat.");
  });

  $("#debate-pause").addEventListener("click", () => {
    if (D.paused) { D.paused = false; status(""); setButtons(); run(); }
    else { D.paused = true; setButtons(); status(D.busy ? "Pause après cette réplique." : "En pause."); }
  });
  $("#debate-more").addEventListener("click", () => {
    D.target = aiCount() + 2;
    D.paused = false;
    D.verdictDone = false;
    status("");
    run();
  });
  $("#debate-verdict").addEventListener("click", () => {
    D.paused = true;
    if (D.running || D.busy) { D.wantVerdict = true; status("Verdict juste après cette réplique."); return; }
    verdict();
  });
  $("#debate-new").addEventListener("click", () => {
    stopCurrent();
    $("#debate-live").classList.add("hidden");
    $("#debate-setup").classList.remove("hidden");
    $("#debate-topic").focus();
  });
  $("#debate-close").addEventListener("click", () => { stopCurrent(); setButtons(); $("#debate").close(); });
  $("#debate").addEventListener("cancel", () => { stopCurrent(); setButtons(); });

  function open() {
    closeDrawer();
    $("#debate-train").classList.toggle("hidden", state.settings?.account?.owner === false);
    $("#debate").showModal();
    if (!D.topic) $("#debate-topic").focus();
    else { setButtons(); if (D.paused) status("En pause. Touche « Reprendre » pour continuer."); }
  }
  $("#open-debate").addEventListener("click", open);
  window.SyriusDebate = { open };
})();
