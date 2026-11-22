// Syrius Code — le laboratoire d'essai de Syrius, avec Aurora. Réservé au propriétaire (le serveur le vérifie à chaque requête).
"use strict";

(function () {
  const $ = (s) => document.querySelector(s);
  const Icons = window.SyriusIcons;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (_) { /* */ } },
  };
  const state = { convId: null, streaming: false, convs: [] };

  // ------------------------------------------------------------------ thème : « syrius » (par défaut) ou « nature »
  const THEME_COLORS = { syrius: "#0d0f16", nature: "#eef3e6" };
  function applyTheme(t) {
    const theme = t === "nature" ? "nature" : "syrius";
    document.documentElement.dataset.theme = theme;
    $("#c-theme-color").setAttribute("content", THEME_COLORS[theme]);
    const b = $("#c-theme");
    if (b) {
      Icons.set(b, theme === "nature" ? "palette" : "leaf", "");
      b.setAttribute("aria-label", theme === "nature" ? "Thème Syrius" : "Thème Nature");
      b.title = theme === "nature" ? "Passer au thème Syrius" : "Passer au thème Nature";
    }
    store.set("syrius:code:theme", theme);
  }
  applyTheme(store.get("syrius:code:theme"));
  $("#c-theme").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "nature" ? "syrius" : "nature"));

  // ------------------------------------------------------------------ réseau
  async function api(path, opts = {}) {
    const headers = { "X-Syrius": "1", ...(opts.body ? { "Content-Type": "application/json" } : {}) };
    const res = await fetch(path, { credentials: "same-origin", ...opts, headers });
    if (res.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Non connecté"); }
    if (!res.ok) {
      let msg = `Erreur ${res.status}`;
      try { const j = await res.json(); if (typeof j.detail === "string") msg = j.detail; } catch (_) { /* */ }
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return; } catch (_) { /* repli */ }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.className = "c-offscreen";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } finally { ta.remove(); }
  }
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function btn(label, icon, fn, cls = "ghost") {
    const b = el("button", cls);
    b.type = "button";
    Icons.set(b, icon, label);
    b.addEventListener("click", fn);
    return b;
  }

  // ------------------------------------------------------------------ connexion
  function showLogin(message) {
    $("#c-app").classList.add("hidden");
    $("#c-login").classList.remove("hidden");
    $("#c-login-error").textContent = message || "";
  }
  $("#c-login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#c-login-error").textContent = "";
    try {
      const name = $("#c-login-name").value.trim();
      await api("/api/login", { method: "POST", body: JSON.stringify(name ? { name, password: $("#c-login-password").value } : { password: $("#c-login-password").value }) });
      $("#c-login-password").value = "";
      await start();
    } catch (err) { $("#c-login-error").textContent = err.message; }
  });
  $("#c-logout").addEventListener("click", async () => {
    try { await api("/api/logout", { method: "POST" }); } catch (_) { /* */ }
    store.set("syrius:code:conv", null);
    $("#c-convs").close();
    showLogin();
  });

  async function start() {
    try {
      state.convs = await api("/api/code/conversations");
    } catch (err) {
      if (err.status === 403) { try { await api("/api/logout", { method: "POST" }); } catch (_) { /* */ } showLogin("Ce compte n'est pas le propriétaire : Syrius Code lui est réservé."); }
      else if (err.message !== "Non connecté") showLogin(err.message);
      return;
    }
    $("#c-login").classList.add("hidden");
    $("#c-app").classList.remove("hidden");
    const last = store.get("syrius:code:conv");
    if (last && state.convs.some((c) => c.id === last)) await openConversation(last);
    renderStarters();
  }

  // ------------------------------------------------------------------ navigation
  function go(tab) {
    document.querySelectorAll(".c-tab").forEach((s) => s.classList.toggle("on", s.dataset.tab === tab));
    document.querySelectorAll("#c-nav button").forEach((b) => b.classList.toggle("on", b.dataset.go === tab));
    if (tab === "sites") renderSites();
    if (tab === "tableaux") renderDashboards();
    if (tab === "code") renderCodeTab();
    if (tab === "emails") renderEmailTab();
    if (tab === "code") renderFast();
    if (tab === "aurore") scrollDown(true);
  }
  document.querySelectorAll("#c-nav button").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));

  // ------------------------------------------------------------------ suggestions
  const STARTERS = {
    "#c-starters": [
      ["Scanne mon site", "Scanne mon site monsite.fr et dis-moi les points faibles par ordre de gravité."],
      ["Trie mes emails", "Résume mes emails non lus et dis-moi lesquels sont urgents."],
      ["Écris du code", "Écris en Python une fonction qui "],
      ["Tableau de bord", "Voici mes chiffres. Fais-en un tableau de bord :\n"],
    ],
    "#c-dash-starters": [
      ["Ventes du mois", "Voici mes ventes par semaine : S1 1200, S2 1850, S3 1430, S4 2100. Fais-en un tableau de bord avec l'évolution et le total."],
      ["Dépenses par poste", "Mes dépenses ce mois-ci : loyer 650, courses 320, transport 90, loisirs 140, abonnements 45. Fais un tableau de bord."],
      ["À partir de mes données", "Voici mes données (colle-les ici) :\n"],
    ],
    "#c-mail-starters": [
      ["Résumer & trier", "Résume mes emails non lus et classe-les : urgent, à répondre, à ignorer."],
      ["Préparer une réponse", "Prépare un brouillon de réponse professionnel et poli à mon dernier email."],
      ["Chercher", "Cherche mes emails de la semaine concernant "],
    ],
    "#c-code-starters": [
      ["Relire du code", "Relis ce code, trouve les bugs et les failles de sécurité :\n```\n\n```"],
      ["Expliquer une erreur", "Explique cette erreur et propose la correction :\n```\n\n```"],
      ["Écrire des tests", "Écris des tests pour cette fonction :\n```\n\n```"],
      ["Nouvelle fonctionnalité", "Écris le code complet pour : "],
    ],
  };
  function renderStarters() {
    for (const [sel, items] of Object.entries(STARTERS)) {
      const box = $(sel);
      box.replaceChildren();
      for (const [label, prompt] of items) {
        const b = el("button", "c-chip", label);
        b.type = "button";
        b.addEventListener("click", () => {
          go("aurore");
          const inp = $("#c-input");
          inp.value = prompt;
          autoGrow();
          inp.focus();
          inp.setSelectionRange(inp.value.length, inp.value.length);
        });
        box.appendChild(b);
      }
    }
  }

  // ------------------------------------------------------------------ discussion avec Aurora
  const messages = $("#c-messages");
  function scrollDown(force) {
    const near = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 140;
    if (force || near) messages.scrollTop = messages.scrollHeight;
  }
  function autoGrow() {
    const t = $("#c-input");
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 180) + "px";
  }
  $("#c-input").addEventListener("input", autoGrow);
  $("#c-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); $("#c-form").requestSubmit(); }
  });

  function addBubble(role, text) {
    $("#c-empty").classList.add("hidden");
    const wrap = el("div", `c-msg ${role}`);
    const bubble = el("div", "c-bubble");
    const tools = el("div", "c-tools");
    const body = el("div", "c-body");
    bubble.append(tools, body);
    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    const view = { wrap, bubble, tools, body, text: text || "", role };
    renderText(view);
    return view;
  }
  function renderText(view) {
    if (view.role === "user") { view.body.textContent = view.text; return; }
    window.SyriusMarkdown.render(view.body, view.text);
    view.body.querySelectorAll("pre").forEach((pre) => {
      if (pre.querySelector(".c-copy")) return;
      const b = btn("Copier", "copy", async () => { await copyText(pre.textContent.replace(/Copier\s*$/, "")); b.lastChild.textContent = "Copié"; setTimeout(() => { b.lastChild.textContent = "Copier"; }, 1500); }, "c-copy");
      pre.appendChild(b);
    });
  }
  function setTools(view, labels) {
    view.tools.replaceChildren(...[...new Set(labels)].map((l) => el("span", "c-tool", l)));
  }

  async function openConversation(cid) {
    const conv = await api(`/api/code/conversations/${cid}`);
    state.convId = cid;
    store.set("syrius:code:conv", cid);
    messages.querySelectorAll(".c-msg").forEach((m) => m.remove());
    for (const m of conv.messages) {
      const v = addBubble(m.role, m.text);
      if (m.role === "assistant") {
        if (m.tools && m.tools.length) setTools(v, m.tools);
        (m.diagrams || []).forEach((d) => addCard(v, d));
      }
    }
    $("#c-empty").classList.toggle("hidden", conv.messages.length > 0);
    go("aurore");
    scrollDown(true);
  }
  async function newConversation() {
    const conv = await api("/api/code/conversations", { method: "POST" });
    state.convId = conv.id;
    store.set("syrius:code:conv", conv.id);
    state.convs.unshift(conv);
    messages.querySelectorAll(".c-msg").forEach((m) => m.remove());
    $("#c-empty").classList.remove("hidden");
    return conv;
  }

  // Une carte pour un tableau de bord ou un schéma reçu d'Aurora
  function addCard(view, ev) {
    if (ev.type === "dashboard") {
      const card = renderDashboard(ev);
      const bar = el("div", "c-card-actions");
      const save = btn("Enregistrer", "save", async () => {
        try { await api("/api/code/dashboards", { method: "POST", body: JSON.stringify({ spec: ev }) }); save.lastChild.textContent = "Enregistré"; save.disabled = true; }
        catch (err) { save.lastChild.textContent = "⚠ " + err.message; }
      });
      bar.appendChild(save);
      card.appendChild(bar);
      view.bubble.appendChild(card);
    } else if (ev.type === "diagram") {
      view.bubble.appendChild(renderDiagram(ev));
    } else if (ev.type === "action") {
      view.bubble.appendChild(renderMailDraft(ev));
    } else if (ev.type === "atelier" && /^[0-9a-f]{8}$/.test(ev.id || "")) {
      if (!view.bubble.querySelector(`.c-atelier[data-id="${ev.id}"]`)) view.bubble.appendChild(renderAtelier(ev.id));
    }
  }

  // ------------------------------------------------------------------ atelier d'Aurora : avancement en direct
  const ATELIER_STATES = { pending: ["clock", "En attente de l'atelier"], running: ["refresh", "Aurora travaille"],
    done: ["ok", "Ça marche : tests réussis"], failed: ["alert", "Pas réussi"] };
  function codeBlock(text, label) {
    const pre = el("pre", "c-atelier-pre");
    pre.appendChild(el("code", "", text));
    const b = btn("Copier", "copy", async () => {
      try { await copyText(text); b.lastChild.textContent = "Copié"; } catch (_) { b.lastChild.textContent = "Impossible"; }
      setTimeout(() => { b.lastChild.textContent = "Copier"; }, 1500);
    }, "c-copy");
    b.setAttribute("aria-label", "Copier " + (label || "le code"));
    pre.appendChild(b);
    return pre;
  }
  // ------------------------------------------------------------------ atelier INSTANTANÉ (sites web, dans l'appli)
  // Aurora écrit le site → on l'ouvre dans une boîte fermée (iframe « sandbox », sans accès à Syrius) → le banc d'essai
  // renvoie erreurs et résultats des tests → s'il y a un problème, Aurora corrige. Jusqu'à 4 essais, en quelques secondes.
  const instantRuns = new Set();
  function testInBrowser(url) {
    return new Promise((resolve) => {
      const frame = el("iframe", "c-test-frame");
      frame.setAttribute("sandbox", "allow-scripts allow-forms allow-modals");
      frame.title = "Test du site";
      let done = false;
      const finish = (r) => { if (done) return; done = true; clearTimeout(timer); window.removeEventListener("message", onMsg); frame.remove(); resolve(r); };
      const onMsg = (e) => { if (e.source === frame.contentWindow && e.data && e.data.syriusAtelierTest) finish(e.data); };
      const timer = setTimeout(() => finish({ errors: ["Le site ne s'est pas chargé ou le banc d'essai n'a pas pu tourner (erreur de script bloquante ?)."], results: [] }), 20000);
      window.addEventListener("message", onMsg);
      frame.src = url + "?test=1";
      document.body.appendChild(frame);
    });
  }
  function testReport(r) {
    const lines = [];
    for (const x of r.results || []) lines.push(`${x.ok ? "✔" : "✘"} ${x.nom}${x.ok ? "" : " → " + x.erreur}`);
    for (const e of r.errors || []) lines.push("Erreur : " + e);
    const passed = (r.results || []).filter((x) => x.ok).length;
    lines.push(`Tests : ${passed}/${(r.results || []).length} réussis, ${(r.errors || []).length} erreur(s).`);
    return lines.join("\n");
  }
  async function runInstant(id, update) {
    if (instantRuns.has(id)) return;
    instantRuns.add(id);
    let feedback = "";
    try {
      for (let guard = 0; guard < 16; guard++) {
        let p;
        try { p = await api(`/api/code/atelier/${id}/ask`, { method: "POST", body: JSON.stringify({ feedback }) }); }
        catch (err) { update(); return; }  // essais épuisés, IA indisponible… : la carte affiche la raison
        update();
        if (p.retry || !p.site_url) { feedback = ""; continue; }
        if ((p.todo || []).length) { feedback = ""; continue; }  // gros site : Aurora écrit la suite avant le test
        const r = await testInBrowser(p.site_url);
        const log = testReport(r);
        const ok = !(r.errors || []).length && (r.results || []).length > 0 && (r.results || []).every((x) => x.ok);
        if (ok || (p.attempt || 0) >= 4) {
          await api(`/api/code/atelier/${id}/result`, { method: "POST", body: JSON.stringify({ ok, final: true, log }) });
          update();
          return;
        }
        await api(`/api/code/atelier/${id}/result`, { method: "POST", body: JSON.stringify({ ok: false, final: false, log }) });
        feedback = log;
      }
    } finally { instantRuns.delete(id); update(); }
  }

  function renderAtelier(id) {
    const card = el("div", "c-card c-atelier");
    card.dataset.id = id;
    const head = el("div", "c-atelier-head");
    const badge = el("span", "c-atelier-state");
    head.append(el("strong", "", "Atelier d'Aurora"), badge);
    const summary = el("p", "c-atelier-summary", "Chargement…");
    const details = el("div", "c-atelier-details");
    card.append(head, summary, details);
    let timer = null, shown = "";
    async function refresh() {
      if (!card.isConnected && timer) { clearInterval(timer); return; }
      let p;
      try { p = await api(`/api/code/atelier/${id}`); } catch (err) {
        summary.textContent = err.status === 404 ? "Projet introuvable (trop ancien ?)." : "⚠ " + err.message;
        if (err.status === 404 && timer) clearInterval(timer);
        return;
      }
      if (p.mode === "instant" && (p.status === "pending" || p.status === "running") && !instantRuns.has(id)) {
        runInstant(id, refresh);  // l'atelier instantané tourne ici, dans l'appli
      }
      const [icon, label] = ATELIER_STATES[p.status] || ATELIER_STATES.pending;
      Icons.set(badge, icon, p.status === "running" && p.attempt ? `${label} · essai ${p.attempt}/5` : label);
      badge.className = "c-atelier-state " + p.status;
      summary.textContent = p.summary || (p.status === "pending" ? "Le projet attend qu'un serveur de GitHub le prenne (quelques minutes)." : "");
      const key = JSON.stringify([p.status, p.updated, Object.keys(p.files || {}).length]);
      if (key !== shown) {
        shown = key;
        details.replaceChildren();
        const files = Object.entries(p.files || {});
        if (p.mode === "instant" && p.site_url && p.status === "done") {  // le site, en vrai, dans la discussion
          const live = el("iframe", "c-atelier-live");
          live.setAttribute("sandbox", "allow-scripts allow-forms allow-modals allow-popups");
          live.title = "Aperçu du site";
          live.src = p.site_url;
          details.appendChild(live);
        }
        if (p.has_shot) {  // le site, vu au format téléphone par Aurora
          const img = el("img", "c-atelier-shot");
          img.alt = "Capture du site au format téléphone";
          img.src = `/api/code/atelier/${id}/capture?v=${p.updated}`;
          details.appendChild(img);
        }
        if (p.site_url || p.zip_url) {
          const bar = el("div", "c-atelier-links");
          const link = (href, label, icon, dl) => {
            const a = el("a", "ghost c-atelier-link");
            a.href = href;
            if (dl) a.setAttribute("download", ""); else { a.target = "_blank"; a.rel = "noopener"; }
            Icons.set(a, icon, label);
            return a;
          };
          if (p.site_url) bar.appendChild(link(p.site_url, "Voir le site", "eye"));
          if (p.zip_url) bar.appendChild(link(p.zip_url, "Télécharger (.zip)", "download", true));
          details.appendChild(bar);
        }
        if (p.site_url && p.status === "done" && p.can_publish) {  // publier : toujours sur TON appui, jamais tout seul
          const pub = el("div", "c-atelier-publish");
          if (p.published) {
            const a = el("a", "c-atelier-online", p.published.replace("https://", ""));
            a.href = p.published; a.target = "_blank"; a.rel = "noopener";
            pub.append(el("span", "small muted", "En ligne : "), a);
          }
          const msg = el("p", "small");
          const btn = el("button", p.published ? "ghost" : "primary");
          btn.type = "button";
          Icons.set(btn, "send", p.published ? "Republier la dernière version" : "Publier sur Internet");
          btn.addEventListener("click", async () => {
            if (!p.published && !confirm("Publier ce site sur Internet ? Tout le monde pourra le voir avec son adresse.")) return;
            btn.disabled = true;
            msg.textContent = "Publication sur Vercel…";
            try {
              const r = await api(`/api/code/atelier/${id}/publish`, { method: "POST" });
              msg.textContent = "✅ En ligne : " + r.url;
              shown = "";
              refresh();
            } catch (err) { msg.textContent = "⚠ " + err.message; btn.disabled = false; }
          });
          pub.append(btn, msg);
          details.appendChild(pub);
        }
        if (p.setup || p.test || p.zip_url) {
          const lines = [];
          if (p.zip_url) {  // tout le projet d'un coup dans Termux, au lieu de copier les fichiers un par un
            lines.push("pkg install -y unzip curl " + (p.env === "node" ? "nodejs" : "python"),
              `curl -L -o projet.zip "${location.origin}${p.zip_url}"`, "unzip -o projet.zip -d projet && cd projet");
          }
          if (p.env !== "web" && p.setup) lines.push(p.setup);
          if (p.env === "web") lines.push("cd site && python -m http.server 8080   # puis ouvre http://localhost:8080");
          else if (p.test) lines.push(p.test + "   # lance les tests");
          details.append(el("div", "c-atelier-label", "Dans Termux"), codeBlock(lines.join("\n"), "les commandes"));
        }
        for (const [path, content] of files) {
          const d = el("details", "c-atelier-file");
          d.open = files.length <= 2 && p.status === "done";
          d.append(el("summary", "", path), codeBlock(content, path));
          details.appendChild(d);
        }
        if (p.log) {
          const d = el("details", "c-atelier-file");
          d.append(el("summary", "", p.status === "done" ? "Sortie des tests (réussis)" : "Sortie des tests"), codeBlock(p.log.slice(-4000), "la sortie"));
          details.appendChild(d);
        }
      }
      if ((p.status === "done" || p.status === "failed") && timer) { clearInterval(timer); timer = null; }
    }
    refresh().then(() => { if (!timer && !/(done|failed)/.test(badge.className)) timer = setInterval(refresh, 6000); });
    return card;
  }

  $("#c-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("#c-input").value.trim();
    if (!text || state.streaming) return;
    $("#c-input").value = "";
    autoGrow();
    go("aurore");
    try { if (!state.convId) await newConversation(); } catch (err) { alert(err.message); return; }
    addBubble("user", text);
    const view = addBubble("assistant", "");
    view.wrap.classList.add("typing");
    scrollDown(true);
    state.streaming = true;
    $("#c-send").disabled = true;
    const tools = [];
    let gotError = false;
    try {
      const res = await fetch(`/api/code/conversations/${state.convId}/messages`, {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Syrius": "1" }, body: JSON.stringify({ text }) });
      if (res.status === 401) { showLogin(); throw new Error("Non connecté"); }
      if (!res.ok || !res.body) throw new Error((await res.json().catch(() => ({}))).detail || `Erreur ${res.status}`);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          if (!chunk.startsWith("data: ")) continue;
          let ev;
          try { ev = JSON.parse(chunk.slice(6)); } catch (_) { continue; }
          if (ev.type === "text") { view.text += ev.text; renderText(view); }
          else if (ev.type === "text_replace") { view.text = String(ev.text || ""); renderText(view); }
          else if (ev.type === "tool") { tools.push(ev.label); setTools(view, tools); }
          else if (ev.type === "dashboard" || ev.type === "diagram" || ev.type === "action" || ev.type === "atelier") addCard(view, ev);
          else if (ev.type === "title") { const c = state.convs.find((x) => x.id === state.convId); if (c) c.title = ev.title; }
          else if (ev.type === "error") { gotError = true; view.bubble.appendChild(el("div", "c-error", "⚠ " + ev.message)); }
          scrollDown();
        }
      }
    } catch (err) {
      gotError = true;
      view.bubble.appendChild(el("div", "c-error", "⚠ " + (err.message || "Connexion perdue.")));
    } finally {
      state.streaming = false;
      $("#c-send").disabled = false;
      view.wrap.classList.remove("typing");
      renderText(view);
      if (gotError && !view.text) $("#c-input").value = text;
      scrollDown();
    }
  });

  // Mes discussions
  $("#c-menu").addEventListener("click", async () => {
    try { state.convs = await api("/api/code/conversations"); } catch (_) { /* */ }
    const ul = $("#c-conv-list");
    ul.replaceChildren();
    if (!state.convs.length) ul.appendChild(el("li", "c-card muted", "Aucune discussion pour l'instant."));
    for (const c of state.convs) {
      const li = el("li", "c-card c-row");
      const open = el("button", "c-link", c.title || "Discussion");
      open.type = "button";
      open.addEventListener("click", async () => { $("#c-convs").close(); await openConversation(c.id); });
      li.append(open, btn("", "trash", async () => {
        if (!confirm("Supprimer cette discussion ?")) return;
        await api(`/api/code/conversations/${c.id}`, { method: "DELETE" });
        if (state.convId === c.id) { state.convId = null; store.set("syrius:code:conv", null); messages.querySelectorAll(".c-msg").forEach((m) => m.remove()); $("#c-empty").classList.remove("hidden"); }
        $("#c-menu").click();
      }, "ghost subtle"));
      ul.appendChild(li);
    }
    $("#c-convs").showModal();
  });
  $("#c-convs-close").addEventListener("click", () => $("#c-convs").close());
  $("#c-new").addEventListener("click", async () => { $("#c-convs").close(); await newConversation(); go("aurore"); $("#c-input").focus(); });

  // ------------------------------------------------------------------ emails : brouillon à confirmer, connexion de la boîte
  function renderMailDraft(ev) {
    const card = el("div", "c-dcard");
    card.appendChild(el("h4", "", "Brouillon d'email : en attente de ta confirmation"));
    const f = (k, v) => { const p = el("p", "small"); p.append(el("b", "", k + " "), document.createTextNode(v)); return p; };
    card.append(f("À :", ev.to), f("Sujet :", ev.subject), el("pre", "c-skill-body", ev.body));
    const status = el("p", "small");
    const bar = el("div", "c-actions");
    const done = (msg) => { bar.remove(); status.textContent = msg; };
    const send = btn("Envoyer", "send", async () => {
      send.disabled = true;
      try { await api(`/api/actions/${ev.id}/confirm`, { method: "POST" }); done("✅ Email envoyé."); }
      catch (err) { status.textContent = "⚠ " + err.message; send.disabled = false; }
    }, "primary");
    const cancel = btn("Annuler", "close", async () => { try { await api(`/api/actions/${ev.id}/cancel`, { method: "POST" }); } catch (_) { /* */ } done("Annulé."); });
    bar.append(send, cancel);
    card.append(bar, status);
    return card;
  }
  // ------------------------------------------------------------------ tri automatique des emails
  const MS_ICONS = { urgent: "alert", repondre: "mail", info: "bulb", pub: "news", indesirable: "shield" };
  async function renderMailSort() {
    let d;
    try { d = await api("/api/code/mailsort"); } catch (_) { return; }
    $("#c-ms-on").checked = d.enabled;
    $("#c-ms-status").textContent = d.last_error ? "⚠ " + d.last_error
      : `Dernier tri : ${d.last_run ? ago(d.last_run) : "jamais"}.` + (d.enabled ? "" : " (tri automatique en pause)");
    const box = $("#c-ms-list");
    box.replaceChildren();
    if (!d.items.length) { box.appendChild(el("p", "small muted", "Aucun email trié pour l'instant.")); return; }
    for (const [cat, label] of Object.entries(d.cats)) {
      const items = d.items.filter((i) => i.cat === cat);
      if (!items.length) continue;
      const sec = el("details", "c-ms-cat " + cat);
      sec.open = cat === "urgent" || cat === "repondre";
      const sum = el("summary");
      Icons.set(sum, MS_ICONS[cat], `${label} (${items.length})`);
      sec.appendChild(sum);
      for (const i of items.slice(0, 40)) {
        const row = el("div", "c-ms-item");
        row.append(el("strong", "", i.sujet || "(sans sujet)"), el("span", "small muted", i.de), el("p", "small", i.resume));
        sec.appendChild(row);
      }
      box.appendChild(sec);
    }
  }
  $("#c-ms-on").addEventListener("change", async () => {
    try { await api("/api/code/mailsort", { method: "PUT", body: JSON.stringify({ enabled: $("#c-ms-on").checked }) }); }
    catch (err) { alert(err.message); }
    renderMailSort();
  });
  $("#c-ms-run").addEventListener("click", async () => {
    const b = $("#c-ms-run");
    b.disabled = true;
    $("#c-ms-status").textContent = "Aurora trie tes nouveaux emails…";
    try {
      const r = await api("/api/code/mailsort/run", { method: "POST" });
      if (r.error) $("#c-ms-status").textContent = "⚠ " + r.error;
    } catch (err) { $("#c-ms-status").textContent = "⚠ " + err.message; }
    b.disabled = false;
    renderMailSort();
  });

  // ------------------------------------------------------------------ atelier rapide (Hugging Face)
  const FAST_STAGES = { RUNNING: "✅ Prêt : les projets démarrent en quelques secondes.", BUILDING: "Construction en cours (5 à 10 min la première fois)…",
    RUNNING_BUILDING: "Mise à jour en cours…", SLEEPING: "Endormi : il se réveille tout seul au prochain projet (environ 1 min).",
    PAUSED: "⚠ En pause sur Hugging Face.", RUNTIME_ERROR: "⚠ Erreur au démarrage : réinstalle-le.", BUILD_ERROR: "⚠ Erreur de construction : réinstalle-le." };
  async function renderFast() {
    const el = $("#c-fast-status");
    if (!el) return;
    let s;
    try { s = await api("/api/code/atelier/fast"); } catch (_) { return; }
    const b = $("#c-fast-setup");
    if (!s.hf_token) { el.textContent = "⚠ La clé HF_TOKEN n'est pas dans Vercel."; b.disabled = true; return; }
    Icons.set(b, "bolt", s.configured ? "Réinstaller / mettre à jour" : "Installer l'atelier rapide");
    el.textContent = !s.configured ? "Pas encore installé." : (FAST_STAGES[s.stage] || `État : ${s.stage || "inconnu"}`);
    if (s.stage === "BUILDING" || s.stage === "RUNNING_BUILDING") setTimeout(renderFast, 20000);
  }
  $("#c-start-test")?.addEventListener("click", async () => {
    const b = $("#c-start-test"), out = $("#c-start-status");
    b.disabled = true;
    out.textContent = "Je demande à GitHub de démarrer…";
    try {
      const r = await api("/api/code/atelier/test-start", { method: "POST" });
      out.textContent = r.ok ? "✅ GitHub accepte : les projets démarrent tout de suite (environ 30 s à 1 min)."
        : "⚠ Refusé : " + (r.reason || "raison inconnue") + ".";
    } catch (err) { out.textContent = "⚠ " + err.message; }
    b.disabled = false;
  });
  $("#c-fast-setup")?.addEventListener("click", async () => {
    const b = $("#c-fast-setup");
    b.disabled = true;
    $("#c-fast-status").textContent = "Installation sur Hugging Face…";
    try {
      await api("/api/code/atelier/fast", { method: "POST" });
      $("#c-fast-status").textContent = "Installé : construction en cours (5 à 10 min la première fois)…";
      setTimeout(renderFast, 15000);
    } catch (err) { $("#c-fast-status").textContent = "⚠ " + err.message; }
    b.disabled = false;
  });

  async function renderEmailTab() {
    renderMailSort();
    let s;
    try { s = await api("/api/code/email"); } catch (_) { return; }
    $("#c-mail-status").textContent = s.enabled
      ? "✅ Boîte mail connectée (lecture seule ; chaque envoi demande ta confirmation)."
      : "Non configurée. Connecte ta boîte ci-dessous, ou voir le README (section Emails).";
    $("#c-google-connect").classList.toggle("hidden", !s.google);
    Icons.set($("#c-google-connect"), "mail", s.google_connected ? "Reconnecter Gmail" : "Connecter Gmail");
    $("#c-outlook-connect").classList.toggle("hidden", !s.outlook);
  }
  $("#c-google-connect").addEventListener("click", async () => {
    const msg = $("#c-mail-msg");
    try {
      const { url } = await api("/api/email/google/start", { method: "POST" });
      msg.textContent = "La page de Google s'ouvre : connecte-toi, accepte, puis reviens ici.";
      // Dans l'application Android, ce lien s'ouvre dans le navigateur du téléphone (Google l'exige).
      if (window.SyriusAndroid) location.href = url; else window.open(url, "_blank", "noopener");
    } catch (err) { msg.textContent = "⚠ " + err.message; }
  });
  $("#c-outlook-connect").addEventListener("click", async () => {
    const msg = $("#c-mail-msg");
    try {
      const info = await api("/api/email/outlook/start", { method: "POST" });
      msg.replaceChildren();
      msg.append("Ouvre ");
      const a = el("a", "", info.verification_uri);
      a.href = info.verification_uri; a.target = "_blank"; a.rel = "noopener noreferrer";
      msg.append(a, " et entre le code ", el("b", "", info.user_code), ". J'attends ta validation…");
      const timer = setInterval(async () => {
        try {
          const r = await api("/api/email/outlook/poll", { method: "POST" });
          if (r.status === "ok") { clearInterval(timer); msg.textContent = "✅ Outlook connecté."; renderEmailTab(); }
        } catch (err) { clearInterval(timer); msg.textContent = "⚠ " + err.message; }
      }, Math.max(5, info.interval || 5) * 1000);
    } catch (err) { msg.textContent = "⚠ " + err.message; }
  });

  // ------------------------------------------------------------------ schéma (liste hiérarchique)
  function renderDiagram(d) {
    const card = el("div", "c-dcard");
    card.appendChild(el("h4", "", "Plan : " + d.title));
    const byParent = {};
    for (const n of d.nodes) (byParent[n.parent || ""] = byParent[n.parent || ""] || []).push(n);
    const build = (pid, depth) => {
      const ul = el("ul", "c-tree");
      for (const n of byParent[pid] || []) {
        const li = el("li");
        li.appendChild(el("strong", "", n.label));
        if (n.note) li.appendChild(el("span", "muted small", " — " + n.note));
        if (depth < 6 && byParent[n.id]) li.appendChild(build(n.id, depth + 1));
        ul.appendChild(li);
      }
      return ul;
    };
    card.appendChild(build("", 0));
    return card;
  }

  // ------------------------------------------------------------------ tableaux de bord (dessinés ici, sans bibliothèque)
  const SVGNS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, parent) {
    const e = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, String(v));
    if (parent) parent.appendChild(e);
    return e;
  }
  function fmt(n) {
    const a = Math.abs(n);
    if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(".0", "") + " M";
    if (a >= 1e4) return (n / 1e3).toFixed(0) + " k";
    if (a >= 1e3) return (n / 1e3).toFixed(1).replace(".0", "") + " k";
    return String(Math.round(n * 100) / 100);
  }
  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const f = v / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }
  function drawChart(c) {
    const W = 320, H = 190, L = 38, R = 8, T = 10, B = 26;
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": c.title, class: "c-chart" });
    const n = c.labels.length;
    if (c.type === "pie") {
      const vals = c.series[0].values, total = vals.reduce((a, b) => a + b, 0) || 1;
      let a0 = -Math.PI / 2;
      const cx = 160, cy = 92, r = 78;
      vals.forEach((v, i) => {
        const a1 = a0 + (v / total) * Math.PI * 2;
        if (v / total > 0.9999) svg("circle", { cx, cy, r, class: `c-f${i % 6}` }, s);
        else if (v > 0) {
          const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0), x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
          svg("path", { d: `M${cx},${cy} L${x0},${y0} A${r},${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1},${y1} Z`, class: `c-f${i % 6} c-slice` }, s);
        }
        a0 = a1;
      });
      return s;
    }
    const all = c.series.flatMap((x) => x.values);
    const yMax = niceMax(Math.max(0, ...all)), yMin = Math.min(0, ...all) < 0 ? -niceMax(-Math.min(...all)) : 0;
    const y = (v) => T + (H - T - B) * (1 - (v - yMin) / (yMax - yMin || 1));
    for (let i = 0; i <= 4; i++) {
      const v = yMin + ((yMax - yMin) * i) / 4;
      svg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "c-grid" }, s);
      const t = svg("text", { x: L - 5, y: y(v) + 3, "text-anchor": "end", class: "c-axis" }, s);
      t.textContent = fmt(v);
    }
    const step = (W - L - R) / n;
    const every = Math.ceil(n / 8);
    c.labels.forEach((lb, i) => {
      if (i % every) return;
      const t = svg("text", { x: L + step * (i + 0.5), y: H - 8, "text-anchor": "middle", class: "c-axis" }, s);
      t.textContent = lb.length > 8 ? lb.slice(0, 7) + "…" : lb;
    });
    if (c.type === "bar") {
      const gw = step * 0.78, bw = gw / c.series.length;
      c.series.forEach((se, si) => se.values.forEach((v, i) => {
        const x = L + step * i + (step - gw) / 2 + bw * si, y0 = y(0), y1 = y(v);
        svg("rect", { x, y: Math.min(y0, y1), width: Math.max(1, bw - 1), height: Math.max(1, Math.abs(y0 - y1)), rx: 2, class: `c-f${si % 6}` }, s);
      }));
    } else {
      c.series.forEach((se, si) => {
        const pts = se.values.map((v, i) => [L + step * (i + 0.5), y(v)]);
        svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), class: `c-line c-s${si % 6}`, fill: "none" }, s);
        pts.forEach((p) => svg("circle", { cx: p[0], cy: p[1], r: 2.6, class: `c-f${si % 6}` }, s));
      });
    }
    return s;
  }
  function renderDashboard(d) {
    const root = el("div", "c-dcard");
    root.appendChild(el("h4", "", d.title));
    if (d.kpis.length) {
      const g = el("div", "c-kpis");
      for (const k of d.kpis) {
        const c = el("div", "c-kpi" + (k.trend ? " " + k.trend : ""));
        c.append(el("span", "c-kpi-l", k.label), el("strong", "c-kpi-v", (k.trend === "up" ? "▲ " : k.trend === "down" ? "▼ " : "") + k.value));
        if (k.note) c.appendChild(el("span", "c-kpi-n", k.note));
        g.appendChild(c);
      }
      root.appendChild(g);
    }
    for (const ch of d.charts) {
      const box = el("div", "c-chartbox");
      box.appendChild(el("h5", "", ch.title));
      box.appendChild(drawChart(ch));
      const legend = el("div", "c-legend");
      const items = ch.type === "pie" ? ch.labels.map((l, i) => [l + " (" + fmt(ch.series[0].values[i]) + ")", i]) : ch.series.map((s, i) => [s.name, i]);
      for (const [name, i] of items) { const li = el("span", "c-leg"); li.append(el("i", `c-sw c-b${i % 6}`), document.createTextNode(name)); legend.appendChild(li); }
      box.appendChild(legend);
      root.appendChild(box);
    }
    if (d.table) {
      const wrap = el("div", "c-tablewrap");
      const t = el("table", "c-table");
      const hr = el("tr");
      d.table.columns.forEach((c) => hr.appendChild(el("th", "", c)));
      t.appendChild(el("thead")).appendChild(hr);
      const tb = el("tbody");
      d.table.rows.forEach((r) => { const tr = el("tr"); r.forEach((c) => tr.appendChild(el("td", "", String(c)))); tb.appendChild(tr); });
      t.appendChild(tb);
      wrap.appendChild(t);
      root.appendChild(wrap);
    }
    return root;
  }
  const ago = (at) => { const m = Math.max(0, Math.round((Date.now() / 1000 - at) / 60)); return m < 1 ? "à l'instant" : m < 60 ? `il y a ${m} min` : m < 1440 ? `il y a ${Math.round(m / 60)} h` : `il y a ${Math.round(m / 1440)} j`; };

  async function renderDashboards() {
    let list;
    try { list = await api("/api/code/dashboards"); } catch (_) { return; }
    const ul = $("#c-dashboards");
    ul.replaceChildren();
    if (!list.length) ul.appendChild(el("li", "c-card muted small", "Aucun tableau enregistré. Demande-en un à Aurora, puis touche « Enregistrer »."));
    for (const d of list) {
      const li = el("li", "c-card c-row");
      const open = el("button", "c-link", d.spec.title + " · " + ago(d.at));
      open.type = "button";
      open.addEventListener("click", () => { const v = $("#c-dash-view"); v.replaceChildren(renderDashboard(d.spec)); v.scrollIntoView({ behavior: "smooth", block: "start" }); });
      li.append(open, btn("", "trash", async () => {
        if (!confirm("Supprimer ce tableau de bord ?")) return;
        await api(`/api/code/dashboards/${d.id}`, { method: "DELETE" });
        $("#c-dash-view").replaceChildren();
        renderDashboards();
      }, "ghost subtle"));
      ul.appendChild(li);
    }
  }

  // ------------------------------------------------------------------ sites : gestion et scanner
  const SEV = { haute: "Grave", moyenne: "Moyen", faible: "Léger", info: "Info" };
  async function renderSites() {
    let data;
    try { data = await api("/api/sitescan"); } catch (_) { return; }
    const ul = $("#c-sites");
    ul.replaceChildren();
    if (!data.sites.length) ul.appendChild(el("li", "c-card muted small", "Aucun site pour l'instant. Ajoute-en un ci-dessus."));
    for (const s of data.sites) {
      const li = el("li", "c-card c-site");
      li.appendChild(el("strong", "", s.domain + (s.own ? " (ce serveur)" : "")));
      const hist = (s.history || []).map((h) => h.score);
      li.appendChild(el("span", "muted small", s.last ? `Dernier scan ${ago(s.last.at)} : note ${s.last.score}/100` + (hist.length > 1 ? " · évolution " + hist.join(" → ") : "") : "Pas encore scanné"));
      if (!s.own) {
        li.appendChild(el("span", "small", s.instructions));
        const copy = btn("Copier le code", "copy", async () => { await copyText(s.token); copy.lastChild.textContent = "Copié"; });
        li.appendChild(copy);
      }
      const row = el("div", "c-actions");
      const run = btn("Scanner", "search", () => runScan(s.domain, run), "primary");
      row.appendChild(run);
      if (s.last) row.appendChild(btn("Dernier résultat", "chart", () => showScan(s.domain, s.last)));
      row.appendChild(btn("Demander à Aurora", "sparkle", () => {
        go("aurore");
        $("#c-input").value = `Analyse le dernier scan de ${s.domain} et dis-moi par quoi commencer pour le sécuriser.`;
        autoGrow();
        $("#c-input").focus();
      }));
      if (!s.own) row.appendChild(btn("Retirer", "trash", async () => {
        if (!confirm(`Retirer ${s.domain} de la liste ?`)) return;
        await api(`/api/sitescan/domains/${encodeURIComponent(s.domain)}`, { method: "DELETE" });
        $("#c-scan-result").replaceChildren();
        renderSites();
      }, "ghost subtle"));
      li.appendChild(row);
      ul.appendChild(li);
    }
  }
  async function runScan(domain, button) {
    $("#c-site-msg").textContent = `Scan de ${domain} en cours (environ 20 secondes)…`;
    button.disabled = true;
    try {
      const res = await api("/api/sitescan/run", { method: "POST", body: JSON.stringify({ domain }) });
      $("#c-site-msg").textContent = "";
      showScan(domain, res);
      renderSites();
    } catch (err) {
      $("#c-site-msg").textContent = "⚠ " + err.message;
      button.disabled = false;
    }
  }
  function showScan(domain, res) {
    const box = $("#c-scan-result");
    box.replaceChildren();
    const c = res.counts || {};
    const card = el("div", "c-dcard");
    card.appendChild(el("h4", "", `${domain} : note ${res.score}/100`));
    card.appendChild(el("p", "muted small", `${c.haute || 0} grave(s), ${c.moyenne || 0} moyen(s), ${c.faible || 0} léger(s)` +
      (res.pages ? ` · ${res.pages} page(s) vue(s)` : "") + (res.partial ? " · scan partiel (trop long)" : "")));
    if (!res.findings.length) card.appendChild(el("p", "small", "✅ Rien d'inquiétant trouvé par ce scan passif."));
    const list = el("ul", "c-findings");
    for (const f of res.findings) {
      const li = el("li", "c-finding sev-" + f.sev);
      li.appendChild(el("strong", "", `${SEV[f.sev] || ""} — ${f.title}`));
      li.appendChild(el("span", "small", f.detail + (f.where ? ` (${f.where})` : "")));
      li.appendChild(el("span", "muted small", "Comment corriger : " + f.fix));
      list.appendChild(li);
    }
    card.appendChild(list);
    if (res.findings.length) {
      const share = btn("Copier le rapport", "copy", async () => {
        await copyText(`Scan de sécurité de ${domain} : note ${res.score}/100\n\n` + res.findings.map((f) => `[${SEV[f.sev]}] ${f.title}\n  ${f.detail}\n  Correctif : ${f.fix}`).join("\n\n"));
        share.lastChild.textContent = "Copié";
      });
      card.appendChild(share);
    }
    box.appendChild(card);
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  $("#c-site-add").addEventListener("click", async () => {
    const input = $("#c-site-new");
    if (!input.value.trim()) return;
    try {
      await api("/api/sitescan/domains", { method: "POST", body: JSON.stringify({ domain: input.value.trim() }) });
      input.value = "";
      $("#c-site-msg").textContent = "Site ajouté : place le code de preuve indiqué ci-dessous sur ton site, puis touche « Scanner ».";
      renderSites();
    } catch (err) { $("#c-site-msg").textContent = "⚠ " + err.message; }
  });

  // ------------------------------------------------------------------ code : demandes à l'IA programmeuse + compétences d'Aurora
  const CR_LABEL = { pending: "En attente (vérifiée toutes les 15 min, parfois plus tard)", running: "L'IA programme…", proposed: "Proposition prête", failed: "Échec", refused: "Annulée" };
  function codeMsg(sel, text) { $(sel).textContent = text; }
  async function renderCodeTab() {
    renderChangeRequests();
    renderLessons();
    renderSkills();
  }
  async function renderChangeRequests() {
    let items;
    try { items = await api("/api/selfcode"); } catch (_) { return; }
    const ul = $("#c-cr-list");
    ul.replaceChildren();
    if (!items.length) ul.appendChild(el("li", "c-card muted small", "Aucune demande pour l'instant."));
    for (const it of items) {
      const li = el("li", "c-card c-site");
      li.appendChild(el("strong", "", "« " + it.text + " »"));
      li.appendChild(el("span", "c-tool c-status " + it.status, CR_LABEL[it.status] || it.status));
      if (it.summary) li.appendChild(el("span", "muted small", it.summary));
      if (it.tests) li.appendChild(el("span", "muted small", "Tests : " + it.tests));
      const row = el("div", "c-actions");
      if (it.pr) {
        const a = el("a", "ghost c-linkbtn", "Voir la proposition sur GitHub");
        a.href = it.pr; a.target = "_blank"; a.rel = "noopener";
        row.appendChild(a);
      }
      if (it.status === "proposed" || it.status === "failed") {
        row.appendChild(btn("Pas satisfaite : réessayer", "refresh", async () => {
          const fb = prompt("Qu'est-ce qui ne va pas ? (ta remarque servira aussi pour les prochaines fois)");
          if (!fb) return;
          try { await api(`/api/selfcode/${encodeURIComponent(it.id)}/retry`, { method: "POST", body: JSON.stringify({ text: fb }) }); codeMsg("#c-cr-msg", "✅ Nouvel essai demandé, avec ta remarque."); renderCodeTab(); }
          catch (err) { codeMsg("#c-cr-msg", "⚠ " + err.message); }
        }));
      }
      if (it.status === "pending") {
        row.appendChild(btn("Annuler", "close", async () => {
          try { await api(`/api/selfcode/${encodeURIComponent(it.id)}`, { method: "DELETE" }); renderCodeTab(); } catch (err) { codeMsg("#c-cr-msg", "⚠ " + err.message); }
        }, "ghost subtle"));
      }
      if (row.childNodes.length) li.appendChild(row);
      if (it.pr) li.appendChild(el("span", "muted small", "Pour publier : ouvre la proposition puis « Merge pull request »."));
      ul.appendChild(li);
    }
  }
  async function renderLessons() {
    let s;
    try { s = await api("/api/selfcode/settings"); } catch (_) { return; }
    const ul = $("#c-lessons");
    ul.replaceChildren();
    if (!s.lessons.length) ul.appendChild(el("li", "c-card muted small", "Aucun conseil pour l'instant."));
    for (const l of s.lessons) {
      const li = el("li", "c-card c-row");
      li.appendChild(el("span", "c-link", l.text));
      li.appendChild(btn("", "trash", async () => {
        try { await api(`/api/selfcode/lessons/${encodeURIComponent(l.id)}`, { method: "DELETE" }); renderLessons(); } catch (err) { codeMsg("#c-cr-msg", "⚠ " + err.message); }
      }, "ghost subtle"));
      ul.appendChild(li);
    }
  }
  $("#c-cr-send").addEventListener("click", async () => {
    const text = $("#c-cr-text").value.trim();
    if (text.length < 10) { codeMsg("#c-cr-msg", "⚠ Décris le changement en une phrase ou deux."); return; }
    try {
      const app = $("#c-cr-app").value === "syrius-code" ? "Syrius Code" : "Syrius";
      const res = await api("/api/selfcode", { method: "POST", body: JSON.stringify({ text: `[Application ${app}] ${text}`.slice(0, 1500) }) });
      $("#c-cr-text").value = "";
      codeMsg("#c-cr-msg", res.started ? "✅ Demande envoyée : l'IA programmeuse démarre maintenant."
        : "✅ Demande envoyée. Elle est vérifiée toutes les 15 min (GitHub est parfois en retard, jusqu'à 1 h). Pour démarrer tout de suite, utilise « Lancer maintenant » ci-dessous.");
      renderChangeRequests();
    } catch (err) { codeMsg("#c-cr-msg", "⚠ " + err.message); }
  });
  $("#c-lesson-add").addEventListener("click", async () => {
    const text = $("#c-lesson").value.trim();
    if (text.length < 5) { codeMsg("#c-cr-msg", "⚠ Écris un conseil un peu plus long."); return; }
    try { await api("/api/selfcode/lessons", { method: "POST", body: JSON.stringify({ text }) }); $("#c-lesson").value = ""; renderLessons(); }
    catch (err) { codeMsg("#c-cr-msg", "⚠ " + err.message); }
  });

  async function renderSkills() {
    let list;
    try { list = await api("/api/code/skills"); } catch (_) { return; }
    const ul = $("#c-skills");
    ul.replaceChildren();
    for (const s of list) {
      const li = el("li", "c-card c-site");
      const head = el("div", "c-row");
      head.appendChild(el("strong", "c-link", s.name));
      head.appendChild(el("span", "c-tool", s.builtin ? "intégrée" : "à toi"));
      if (!s.builtin) head.appendChild(btn("", "trash", async () => {
        if (!confirm(`Supprimer la compétence « ${s.name} » ?`)) return;
        try { await api(`/api/code/skills/${encodeURIComponent(s.name)}`, { method: "DELETE" }); renderSkills(); } catch (err) { codeMsg("#c-sk-msg", "⚠ " + err.message); }
      }, "ghost subtle"));
      li.appendChild(head);
      li.appendChild(el("span", "muted small", s.description));
      const view = btn("Voir les consignes", "eye", async () => {
        const box = li.querySelector(".c-skill-body");
        if (box) { box.remove(); return; }
        try { const full = await api(`/api/code/skills/${encodeURIComponent(s.name)}`); li.appendChild(el("pre", "c-skill-body", full.body)); } catch (_) { /* */ }
      }, "ghost subtle");
      li.appendChild(view);
      ul.appendChild(li);
    }
  }
  $("#c-sk-add").addEventListener("click", async () => {
    try {
      await api("/api/code/skills", { method: "POST", body: JSON.stringify({ name: $("#c-sk-name").value, description: $("#c-sk-desc").value, body: $("#c-sk-body").value }) });
      for (const id of ["#c-sk-name", "#c-sk-desc", "#c-sk-body"]) $(id).value = "";
      codeMsg("#c-sk-msg", "✅ Compétence enregistrée : Aurora s'en servira.");
      renderSkills();
    } catch (err) { codeMsg("#c-sk-msg", "⚠ " + err.message); }
  });

  // ------------------------------------------------------------------ démarrage
  start();
})();
