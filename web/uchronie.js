// Uchronie : jeu de stratégie historique. La carte est dessinée ici ; le monde est simulé par le maître du jeu (IA)
// côté serveur. La partie est gardée sur le téléphone et sauvegardée dans l'espace privé du joueur après chaque tour.
"use strict";

(function () {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const node = (tag, cls, text) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  };
  const LOCAL = "uchronie_cache_v1";
  const ERAS = [["−50", -50], ["1492", 1492], ["1789", 1789], ["1914", 1914], ["1936", 1936], ["1962", 1962], ["2025", 2025]];
  const LABEL_MIN_AREA = { 1: 500, 2: 150, 3: 35, 4: 8, 5: 1, 6: 0 };

  const G = {
    world: null,        // territoires de la carte
    state: null,        // partie en cours (vérifiée par le serveur)
    talks: {},          // diplomatie du tour : code de nation -> [{who, text}]
    shapes: {},         // code de territoire -> polygone Leaflet
    labels: null,
    map: null,
    selected: null,     // territoire touché
    choosing: false,
    busy: false,
    standalone: false,  // site à part : pas de compte, parties gardées dans le navigateur
  };

  // ------------------------------------------------------------------ réseau
  async function api(path, opts = {}) {
    const res = await fetch(path, {
      method: opts.method || "GET", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Syrius": "1" },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (res.status === 401) { needLogin(); throw new Error("Non connecté"); }
    if (!res.ok) {
      let msg = `Erreur ${res.status}`;
      try { const d = await res.json(); msg = typeof d.detail === "string" ? d.detail : msg; } catch (_) { /* */ }
      throw new Error(msg);
    }
    return res;
  }

  // Flux d'événements du serveur (comme le débat d'IA).
  async function stream(path, body, onEvent) {
    const res = await api(path, { method: "POST", body });
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
        if (ev.type === "error") throw new Error(ev.message || "Erreur.");
        if (ev.type === "quota") { showQuota(ev.left); continue; }
        onEvent(ev);
      }
    }
  }

  function showQuota(left) {
    const q = $("#u-quota");
    q.classList.toggle("hidden", left == null);
    q.textContent = `Demandes à l'IA restantes aujourd'hui : ${left}`;
    if (left === 5 || left === 1) toast(`Attention : plus que ${left} demande(s) à l'IA aujourd'hui.`);
  }

  function needLogin() {
    toast("Connecte-toi d'abord à Syrius. Retour à l'accueil…");
    setTimeout(() => { location.href = "/"; }, 2200);
  }

  let toastTimer = null;
  function toast(text) {
    const t = $("#u-toast");
    t.textContent = text;
    t.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add("hidden"), 5000);
  }

  function wait(text, sub) {
    $("#u-wait").classList.toggle("hidden", text == null);
    if (text != null) { $("#u-wait-text").textContent = text; $("#u-wait-sub").textContent = sub || ""; }
  }

  // ------------------------------------------------------------------ sauvegarde
  function cacheLocal() {
    try { localStorage.setItem(LOCAL, JSON.stringify({ state: G.state, talks: G.talks })); } catch (_) { /* plein */ }
  }

  async function saveRemote() {
    cacheLocal();
    if (G.standalone) return;
    try { await api("/api/uchronie/save", { method: "PUT", body: { state: G.state } }); }
    catch (err) { if (err.message !== "Non connecté") toast("Sauvegarde en ligne impossible (gardée sur ce téléphone)."); }
  }

  // ------------------------------------------------------------------ la carte
  function ringArea(r) {
    let a = 0;
    for (let i = 0; i < r.length - 1; i++) a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
    return Math.abs(a / 2);
  }

  function buildMap() {
    const map = L.map("u-map", {
      preferCanvas: true, zoomControl: false, attributionControl: false, worldCopyJump: false,
      minZoom: 1, maxZoom: 6, zoomSnap: 0.5, maxBounds: [[-75, -200], [85, 200]], maxBoundsViscosity: 0.8,
    });
    map.fitBounds([[-50, -150], [75, 160]]);
    for (const t of G.world) {
      t.area = t.p.reduce((s, poly) => s + ringArea(poly[0]), 0);
      const latlngs = t.p.map((poly) => poly.map((ring) => ring.map(([x, y]) => [y, x])));
      const shape = L.polygon(latlngs, { weight: 0.6, color: "#0b1424", fillColor: "#3a4256", fillOpacity: 0.9 });
      shape.on("click", (e) => { L.DomEvent.stopPropagation(e); selectTerritory(t.id); });
      shape.addTo(map);
      G.shapes[t.id] = shape;
    }
    map.on("click", () => closeCard());
    map.on("zoomend", drawLabels);
    G.labels = L.layerGroup().addTo(map);
    G.map = map;
  }

  const terr = (id) => G.world.find((t) => t.id === id);
  const nation = (id) => G.state.nations[id] || { name: id, color: "#888888", leader: "", regime: "", desc: "" };

  function holdings() {
    const out = {};
    for (const [tid, nid] of Object.entries(G.state.owners)) (out[nid] = out[nid] || []).push(tid);
    return out;
  }

  function paint() {
    if (!G.state) return;
    for (const t of G.world) {
      const owner = G.state.owners[t.id];
      const mine = G.state.player && owner === G.state.player;
      G.shapes[t.id].setStyle({
        fillColor: nation(owner).color, fillOpacity: t.id === G.selected ? 1 : 0.86,
        color: mine ? "#e3b964" : (t.id === G.selected ? "#ffffff" : "#0b1424"),
        weight: mine ? 1.6 : (t.id === G.selected ? 2 : 0.6),
      });
    }
    drawLabels();
  }

  function drawLabels() {
    if (!G.state || !G.labels) return;
    G.labels.clearLayers();
    const min = LABEL_MIN_AREA[Math.max(1, Math.min(6, Math.round(G.map.getZoom())))];
    const placed = [];  // rectangles déjà occupés (pixels) : deux noms ne se chevauchent jamais
    const items = Object.entries(holdings()).map(([nid, tids]) => {
      const parts = tids.map(terr);
      return { nid, parts, area: parts.reduce((s, t) => s + t.area, 0) };
    }).filter((it) => it.area >= min).sort((a, b) => b.area - a.area);
    for (const { nid, parts, area } of items) {
      // Le nom va sur le pays d'origine (la France en France, pas sur Madagascar), sinon sur la plus grande terre.
      const core = parts.find((t) => t.id === nid) || parts.reduce((a, b) => (b.area > a.area ? b : a));
      const big = area > 600;
      const pt = G.map.latLngToLayerPoint([core.c[1], core.c[0]]);
      const w = nation(nid).name.length * (big ? 9 : 6.5) / 2 + 4, h = big ? 10 : 8;
      const box = [pt.x - w, pt.y - h, pt.x + w, pt.y + h];
      if (placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
      placed.push(box);
      const icon = L.divIcon({ className: "u-label" + (big ? " big" : ""), html: "", iconSize: null });
      const m = L.marker([core.c[1], core.c[0]], { icon, interactive: false, keyboard: false });
      m.addTo(G.labels);
      const el = m.getElement();
      if (el) el.textContent = nation(nid).name;  // texte de l'IA : jamais en HTML
    }
  }

  function flash(tids) {
    for (const id of tids) G.shapes[id]?.setStyle({ color: "#ffffff", weight: 3 });
    setTimeout(paint, 3500);
  }

  // ------------------------------------------------------------------ fiche d'un territoire
  function selectTerritory(tid) {
    if (!G.state) return;
    G.selected = tid;
    paint();
    const nid = G.state.owners[tid];
    const n = nation(nid);
    const count = holdings()[nid]?.length || 0;
    $("#u-card-terr").textContent = terr(tid).n;
    $("#u-card-dot").style.background = n.color;
    $("#u-card-name").textContent = n.name;
    $("#u-card-leader").textContent = [n.leader, n.regime].filter(Boolean).join(" · ");
    $("#u-card-desc").textContent = n.desc || "";
    $("#u-card-size").textContent = count > 1 ? `${count} territoires sur la carte` : "";
    $("#u-pick").classList.toggle("hidden", !G.choosing);
    $("#u-talk-to").classList.toggle("hidden", G.choosing || !G.state.player || nid === G.state.player);
    $("#u-card").classList.remove("hidden");
    $("#u-card").dataset.nation = nid;
  }

  function closeCard() {
    $("#u-card").classList.add("hidden");
    G.selected = null;
    paint();
  }

  // ------------------------------------------------------------------ écrans
  function showSetup() {
    $("#u-setup").classList.remove("hidden");
    $("#u-setup-cancel").classList.toggle("hidden", !(G.state && G.state.player));
    $("#u-panel").classList.add("hidden");
    $("#u-choose").classList.add("hidden");
  }

  function startChoosing() {
    G.choosing = true;
    $("#u-setup").classList.add("hidden");
    $("#u-panel").classList.add("hidden");
    $("#u-me").classList.add("hidden");
    $("#u-date").textContent = G.state.date;
    const list = $("#u-choose-list");
    list.replaceChildren(new Option("— Choisir dans la liste —", ""));
    const h = holdings();
    Object.keys(h).sort((a, b) => nation(a).name.localeCompare(nation(b).name, "fr"))
      .forEach((nid) => list.append(new Option(nation(nid).name + (h[nid].length > 1 ? ` (${h[nid].length})` : ""), nid)));
    $("#u-choose").classList.remove("hidden");
    paint();
  }

  function pickNation(nid) {
    G.state.player = nid;
    G.choosing = false;
    G.talks = {};
    $("#u-choose").classList.add("hidden");
    closeCard();
    saveRemote();
    showGame();
    $("#u-helpbox").classList.remove("hidden");
  }

  function showGame() {
    G.choosing = false;
    $("#u-setup").classList.add("hidden");
    $("#u-choose").classList.add("hidden");
    $("#u-panel").classList.remove("hidden");
    const me = nation(G.state.player);
    $("#u-date").textContent = G.state.date;
    $("#u-me").classList.remove("hidden");
    $("#u-me-dot").style.background = me.color;
    $("#u-me-name").textContent = `${me.name} · tour ${G.state.turn}`;
    renderLog();
    renderWorld();
    renderTalkList();
    renderTalksNote();
    paint();
    const mine = holdings()[G.state.player];
    if (!mine) toast("Ta nation n'a plus aucun territoire… Tu peux continuer en exil ou commencer une nouvelle partie.");
  }

  function renderLog() {
    const ol = $("#u-log");
    ol.replaceChildren();
    for (const e of G.state.log.slice().reverse()) {
      const li = node("li", e.mine ? "mine" : "");
      li.append(node("small", "", e.date), node("b", "", e.title), node("p", "", e.text));
      ol.append(li);
    }
    if (!G.state.log.length) ol.append(node("li", "", "Aucun événement pour l'instant : à toi de jouer."));
  }

  function renderWorld() {
    $("#u-summary").textContent = G.state.summary || "";
    const ol = $("#u-powers");
    ol.replaceChildren();
    Object.entries(holdings()).sort((a, b) => b[1].length - a[1].length).slice(0, 15).forEach(([nid, tids]) => {
      const li = node("li");
      const dot = node("i", "u-dot");
      dot.style.background = nation(nid).color;
      li.append(dot, document.createTextNode(nation(nid).name), node("span", "u-muted", `${tids.length}`));
      ol.append(li);
    });
  }

  // ------------------------------------------------------------------ diplomatie
  function renderTalkList() {
    const sel = $("#u-talk-nation");
    const keep = sel.value;
    sel.replaceChildren();
    const h = holdings();
    Object.keys(G.state.nations).filter((nid) => nid !== G.state.player && h[nid])
      .sort((a, b) => (h[b].length - h[a].length) || nation(a).name.localeCompare(nation(b).name, "fr"))
      .forEach((nid) => sel.append(new Option(nation(nid).name, nid)));
    if (keep && G.state.nations[keep]) sel.value = keep;
    renderTalk();
  }

  function renderTalk() {
    const nid = $("#u-talk-nation").value;
    const box = $("#u-talk-log");
    box.replaceChildren();
    for (const m of G.talks[nid] || []) box.append(bubble(m.who, nid, m.text));
    if (!(G.talks[nid] || []).length)
      box.append(node("p", "u-small u-muted", `Écris à ${nation(nid).leader || "ce gouvernement"} : alliance, commerce, menace, traité…`));
    box.scrollTop = box.scrollHeight;
  }

  function bubble(who, nid, text) {
    const d = node("div", "u-msg " + who);
    d.append(node("b", "", who === "me" ? "Ton émissaire" : (nation(nid).leader || nation(nid).name)));
    d.append(document.createTextNode(text));
    return d;
  }

  function renderTalksNote() {
    const n = Object.keys(G.talks).filter((k) => G.talks[k].length).length;
    const note = $("#u-talks-note");
    note.classList.toggle("hidden", !n);
    note.textContent = `${n} échange(s) diplomatique(s) seront pris en compte à la fin du tour.`;
  }

  async function sendTalk(text) {
    const nid = $("#u-talk-nation").value;
    if (!nid || !text || G.busy) return;
    G.busy = true;
    const msgs = (G.talks[nid] = G.talks[nid] || []);
    msgs.push({ who: "me", text });
    renderTalk();
    const box = $("#u-talk-log");
    const answer = bubble("them", nid, "…");
    box.append(answer);
    box.scrollTop = box.scrollHeight;
    let raw = "";
    try {
      await stream("/api/uchronie/talk", { state: G.state, nation: nid, messages: msgs.slice(-12) }, (ev) => {
        if (ev.type === "text") {
          raw += ev.text;
          answer.lastChild.textContent = raw.replace(/<think>[\s\S]*?(<\/think>|$)/g, "").trim();
          box.scrollTop = box.scrollHeight;
        }
      });
      const clean = raw.replace(/<think>[\s\S]*?(<\/think>|$)/g, "").trim();
      if (clean) msgs.push({ who: "them", text: clean.slice(0, 800) });
      else msgs.pop();
    } catch (err) {
      msgs.pop();
      if (err.message !== "Non connecté") toast(err.message || "Connexion perdue.");
    } finally {
      G.busy = false;
      renderTalk();
      renderTalksNote();
      cacheLocal();
    }
  }

  function diplomacySummary() {
    return Object.entries(G.talks).filter(([, m]) => m.length).slice(0, 6).map(([nid, msgs]) => ({
      nation: nid,
      text: msgs.slice(-4).map((m) => (m.who === "me" ? "Émissaire du joueur : " : "Réponse : ") + m.text).join(" / ").slice(-900),
    }));
  }

  // ------------------------------------------------------------------ partie
  async function createWorld(year, scenario) {
    G.busy = true;
    wait("Le maître du jeu prépare le monde…", "Cela prend en général 20 à 60 secondes.");
    let state = null;
    try {
      await stream("/api/uchronie/start", { year, scenario }, (ev) => {
        if (ev.type === "progress") $("#u-wait-sub").textContent = `Il écrit l'Histoire… (${ev.chars} caractères)`;
        if (ev.type === "state") state = ev.state;
      });
      if (!state) throw new Error("Le maître du jeu n'a pas répondu. Réessaie.");
      G.state = state;
      G.talks = {};
      saveRemote();
      startChoosing();
    } catch (err) {
      if (err.message !== "Non connecté") toast(err.message || "Connexion perdue.");
    } finally {
      G.busy = false;
      wait(null);
    }
  }

  async function endTurn() {
    if (G.busy) return;
    G.busy = true;
    $("#u-end").disabled = true;
    wait("Le monde réagit à tes décisions…", "Les autres nations jouent leur tour.");
    let result = null;
    try {
      await stream("/api/uchronie/turn", {
        state: G.state, actions: $("#u-actions").value.trim(), span: $("#u-span").value, diplomacy: diplomacySummary(),
      }, (ev) => {
        if (ev.type === "progress") $("#u-wait-sub").textContent = `Le maître du jeu écrit… (${ev.chars} caractères)`;
        if (ev.type === "state") result = ev;
      });
      if (!result) throw new Error("Le maître du jeu n'a pas répondu. Tes décisions sont gardées : réessaie.");
      const before = G.state.owners;
      G.state = result.state;
      G.talks = {};
      $("#u-actions").value = "";
      const advice = $("#u-advice");
      advice.textContent = result.advice || "";
      advice.classList.toggle("hidden", !result.advice);
      showGame();
      flash(Object.keys(before).filter((t) => before[t] !== G.state.owners[t]));
      showNews(result.events);
      saveRemote();
    } catch (err) {
      if (err.message !== "Non connecté") toast(err.message || "Connexion perdue.");
    } finally {
      G.busy = false;
      $("#u-end").disabled = false;
      wait(null);
    }
  }

  function showNews(events) {
    $("#u-news-date").textContent = G.state.date;
    const list = $("#u-news-list");
    list.replaceChildren();
    for (const e of events.slice().sort((a, b) => b.mine - a.mine)) {
      const a = node("article", "u-article" + (e.mine ? " mine" : ""));
      a.append(node("h3", "", e.title), node("p", "", e.text));
      list.append(a);
    }
    $("#u-news").classList.remove("hidden");
  }

  // ------------------------------------------------------------------ démarrage
  function bind() {
    const eras = $("#u-eras");
    for (const [label, year] of ERAS) {
      const b = node("button", "", label);
      b.type = "button";
      b.addEventListener("click", () => { $("#u-year").value = year; });
      eras.append(b);
    }
    $("#u-setup-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const year = parseInt($("#u-year").value, 10);
      if (!Number.isFinite(year) || year < -500 || year > 2100) { toast("Choisis une année entre −500 et 2100."); return; }
      $("#u-setup").classList.add("hidden");
      createWorld(year, $("#u-scenario").value.trim());
    });
    $("#u-setup-cancel").addEventListener("click", () => { $("#u-setup").classList.add("hidden"); showGame(); });
    $("#u-choose-list").addEventListener("change", (e) => {
      const nid = e.target.value;
      if (!nid) return;
      const tid = holdings()[nid][0];
      selectTerritory(holdings()[nid].includes(nid) ? nid : tid);
      const t = terr(G.selected);
      G.map.flyTo([t.c[1], t.c[0]], Math.max(G.map.getZoom(), 3));
    });
    $("#u-pick").addEventListener("click", () => pickNation($("#u-card").dataset.nation));
    $("#u-card-close").addEventListener("click", closeCard);
    $("#u-talk-to").addEventListener("click", () => {
      const nid = $("#u-card").dataset.nation;
      closeCard();
      openTab("talk");
      $("#u-talk-nation").value = nid;
      renderTalk();
      $("#u-panel").classList.remove("mini");
      $("#u-talk-input").focus();
    });
    $$(".u-tab").forEach((b) => b.addEventListener("click", () => openTab(b.dataset.tab)));
    $("#u-grip").addEventListener("click", () => {
      const p = $("#u-panel");
      if (p.classList.contains("mini")) p.classList.remove("mini");
      else if (p.classList.contains("tall")) { p.classList.remove("tall"); p.classList.add("mini"); }
      else p.classList.add("tall");
    });
    $("#u-orders").addEventListener("submit", (e) => { e.preventDefault(); endTurn(); });
    $("#u-talk-nation").addEventListener("change", renderTalk);
    $("#u-talk-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const input = $("#u-talk-input");
      const text = input.value.trim();
      input.value = "";
      sendTalk(text);
    });
    $("#u-news-ok").addEventListener("click", () => $("#u-news").classList.add("hidden"));
    $("#u-help-ok").addEventListener("click", () => $("#u-helpbox").classList.add("hidden"));
    $("#u-menu").addEventListener("click", (e) => { e.stopPropagation(); $("#u-menu-box").classList.toggle("hidden"); });
    document.addEventListener("click", () => $("#u-menu-box").classList.add("hidden"));
    $("#u-help").addEventListener("click", () => $("#u-helpbox").classList.remove("hidden"));
    $("#u-export").addEventListener("click", exportGame);
    $("#u-import").addEventListener("click", () => $("#u-import-file").click());
    $("#u-setup-import").addEventListener("click", () => $("#u-import-file").click());
    $("#u-import-file").addEventListener("change", (e) => { if (e.target.files[0]) importGame(e.target.files[0]); e.target.value = ""; });
    $("#u-new").addEventListener("click", () => {
      if (G.state && G.state.player && !confirm("Commencer une nouvelle partie ? La partie en cours sera remplacée à la création du nouveau monde.")) return;
      showSetup();
    });
  }

  function exportGame() {
    if (!G.state) { toast("Aucune partie à exporter."); return; }
    const blob = new Blob([JSON.stringify({ uchronie: 1, state: G.state }, null, 1)], { type: "application/json" });
    const a = node("a");
    a.href = URL.createObjectURL(blob);
    a.download = `uchronie-${(nation(G.state.player).name || "monde").replace(/[^\p{L}\p{N}]+/gu, "-")}-tour-${G.state.turn}.json`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }

  async function importGame(file) {
    try {
      if (file.size > 400000) throw new Error("Fichier trop gros.");
      const data = JSON.parse(await file.text());
      const st = data && data.state;
      if (!st || typeof st !== "object" || !st.nations || !st.owners) throw new Error("Ce fichier n'est pas une partie d'Uchronie.");
      G.state = st;  // le serveur revérifie tout l'état au prochain tour
      G.talks = {};
      await saveRemote();
      if (!G.state.player) startChoosing(); else showGame();
      toast("Partie importée.");
    } catch (err) { toast(err.message || "Fichier illisible."); }
  }

  function openTab(name) {
    $$(".u-tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
    $$(".u-pane").forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== name));
    const panel = $("#u-panel");
    panel.classList.toggle("mini", false);
    if (name === "talk" || name === "log") panel.classList.toggle("tall", true);
  }

  async function init() {
    bind();
    try {
      const res = await fetch("/static/uchronie-monde.json", { credentials: "same-origin" });
      G.world = (await res.json()).territories;
      buildMap();
    } catch (_) {
      toast("Impossible de charger la carte.");
      return;
    }
    try {
      const cfg = await (await fetch("/api/uchronie/config", { credentials: "same-origin" })).json();
      G.standalone = !!cfg.standalone;
      if (G.standalone) {
        const back = $("#u-back");
        back.replaceWith(node("span", "u-spacer"));
        showQuota(cfg.left);
        $("#u-save-note").textContent = "Ta partie est gardée dans ce navigateur. Menu ⋯ → « Exporter » pour la garder en fichier.";
      }
    } catch (_) { /* Syrius : la route n'existe pas */ }
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(LOCAL) || "null"); } catch (_) { /* */ }
    let remote = null;
    if (!G.standalone) {
      try { remote = (await (await api("/api/uchronie/save")).json()).state; }
      catch (err) { if (err.message === "Non connecté") return; }
    }
    // La copie du téléphone l'emporte si elle est plus avancée (sauvegarde en ligne ratée).
    const local = saved && saved.state;
    G.state = local && (!remote || local.turn > remote.turn) ? local : remote;
    G.talks = (local && G.state === local && saved.talks) || {};
    if (!G.state) showSetup();
    else if (!G.state.player) startChoosing();
    else showGame();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
