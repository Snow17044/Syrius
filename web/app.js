"use strict";

const $ = (s) => document.querySelector(s);
const emptyNode = document.getElementById("empty");
const state = {
  convId: null,
  conversations: [],
  settings: {},
  streaming: false,
  location: null,
  controller: null,
  menuConv: null,
};

// ------------------------------------------------------------------ API
async function api(path, opts = {}) {
  const headers = { "X-Syrius": "1", ...(opts.body ? { "Content-Type": "application/json" } : {}) };
  const res = await fetch(path, { credentials: "same-origin", ...opts, headers });
  if (res.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Non connecté"); }
  if (!res.ok) {
    let msg = `Erreur ${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch (_) { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

const store = {
  get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (_) { /* ignore */ } },
};

// ------------------------------------------------------------------ écrans
function showLogin() {
  $("#app").classList.add("hidden");
  $("#login").classList.remove("hidden");
  $("#login-password").focus();
}

async function showApp() {
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  await loadSettings();
  refreshLocation();
  await loadConversations();
  const last = store.get("syrius:lastConv");
  if (last && state.conversations.some((c) => c.id === last)) await openConversation(last);
  else newConversationView();
  if (briefingWaiting) { briefingWaiting = false; window.syriusBriefing(); }
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ password: $("#login-password").value }) });
    $("#login-password").value = "";
    await showApp();
  } catch (err) { $("#login-error").textContent = err.message; }
});

$("#setup-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    const password = $("#setup-password").value;
    await api("/api/setup", { method: "POST", body: JSON.stringify({ code: $("#setup-code").value, password }) });
    await api("/api/login", { method: "POST", body: JSON.stringify({ password }) });
    $("#setup-code").value = ""; $("#setup-password").value = "";
    $("#setup-form").classList.add("hidden");
    $("#login-form").classList.remove("hidden");
    await showApp();
  } catch (err) { $("#login-error").textContent = err.message; }
});

$("#logout").addEventListener("click", async () => {
  try { await api("/api/logout", { method: "POST" }); } catch (_) { /* ignore */ }
  store.set("syrius:lastConv", null);
  showLogin();
});

// ------------------------------------------------------------------ tiroir
function openDrawer() { $("#drawer").classList.add("open"); $("#backdrop").classList.remove("hidden"); }
function closeDrawer() { $("#drawer").classList.remove("open"); $("#backdrop").classList.add("hidden"); }
$("#open-drawer").addEventListener("click", openDrawer);
$("#close-drawer").addEventListener("click", closeDrawer);
$("#backdrop").addEventListener("click", closeDrawer);

let searchTimer;
$("#search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadConversations, 250);
});

async function loadConversations() {
  const q = $("#search").value.trim();
  state.conversations = await api("/api/conversations" + (q ? "?q=" + encodeURIComponent(q) : ""));
  renderConversations();
}

function renderConversations() {
  const ul = $("#conv-list");
  ul.replaceChildren();
  for (const c of state.conversations) {
    const li = document.createElement("li");
    if (c.id === state.convId) li.classList.add("active");
    const open = document.createElement("button");
    open.className = "conv-open";
    open.textContent = (c.pinned ? "📌 " : "") + c.title;
    open.addEventListener("click", () => { openConversation(c.id); closeDrawer(); });
    const more = document.createElement("button");
    more.className = "conv-more";
    more.setAttribute("aria-label", "Options");
    more.textContent = "⋯";
    more.addEventListener("click", () => openConvMenu(c));
    li.append(open, more);
    ul.appendChild(li);
  }
}

function openConvMenu(c) {
  state.menuConv = c;
  $("#conv-menu-title").textContent = c.title;
  $("#cm-pin").textContent = c.pinned ? "📌 Désépingler" : "📌 Épingler";
  $("#conv-menu").showModal();
}
$("#cm-close").addEventListener("click", () => $("#conv-menu").close());
$("#cm-rename").addEventListener("click", async () => {
  const c = state.menuConv;
  $("#conv-menu").close();
  const title = prompt("Nouveau nom :", c.title);
  if (title && title.trim()) {
    await api(`/api/conversations/${c.id}`, { method: "PATCH", body: JSON.stringify({ title: title.trim() }) });
    if (c.id === state.convId) $("#conv-title").textContent = title.trim();
    loadConversations();
  }
});
$("#cm-pin").addEventListener("click", async () => {
  const c = state.menuConv;
  $("#conv-menu").close();
  await api(`/api/conversations/${c.id}`, { method: "PATCH", body: JSON.stringify({ pinned: !c.pinned }) });
  loadConversations();
});
$("#cm-delete").addEventListener("click", async () => {
  const c = state.menuConv;
  $("#conv-menu").close();
  if (!confirm(`Supprimer « ${c.title} » ?`)) return;
  await api(`/api/conversations/${c.id}`, { method: "DELETE" });
  if (c.id === state.convId) newConversationView();
  loadConversations();
});

// ------------------------------------------------------------------ discussions
function greeting() {
  const h = new Date().getHours();
  const name = state.settings.user_name ? `, ${state.settings.user_name}` : "";
  if (h < 5) return `Encore debout${name}\u00a0? Je suis là.`;
  if (h < 12) return `Bonjour${name}. À votre service.`;
  if (h < 18) return `Bon après-midi${name}. Que puis-je faire\u00a0?`;
  return `Bonsoir${name}. Je vous écoute.`;
}

function newConversationView() {
  state.convId = null;
  store.set("syrius:lastConv", null);
  $("#conv-title").textContent = "Syrius";
  $("#messages").replaceChildren(emptyNode);
  emptyNode.classList.remove("hidden");
  $("#greeting").textContent = greeting();
  renderConversations();
  $("#input").focus();
}

$("#new-chat").addEventListener("click", newConversationView);
$("#new-chat-drawer").addEventListener("click", () => { newConversationView(); closeDrawer(); });
document.querySelectorAll(".chip").forEach((b) =>
  b.addEventListener("click", () => sendMessage(b.dataset.prompt)));

async function openConversation(id) {
  if (state.streaming) return;
  const conv = await api(`/api/conversations/${id}`);
  state.convId = id;
  store.set("syrius:lastConv", id);
  $("#conv-title").textContent = conv.title;
  const box = $("#messages");
  box.replaceChildren();
  for (const m of conv.messages) {
    const view = addMessage(m.role, m.text);
    if (m.tools && m.tools.length) setTools(view, [...new Set(m.tools)]);
    (m.diagrams || []).forEach((d) => addDiagramCard(view, d));
  }
  if (!conv.messages.length) newConversationView();
  renderConversations();
  scrollDown(true);
}

function addMessage(role, text) {
  $("#empty")?.classList.add("hidden");
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const tools = document.createElement("div");
  const body = document.createElement("div");
  bubble.append(tools, body);
  wrap.appendChild(bubble);
  $("#messages").appendChild(wrap);
  const view = { wrap, bubble, tools, body, text: text || "", role };
  renderText(view, role);
  state.views = (state.views || []).filter((v) => v.wrap.isConnected);
  state.views.push(view);
  return view;
}

function renderText(view, role) {
  if (role === "user") view.body.textContent = view.text;
  else window.SyriusMarkdown.render(view.body, view.text);
}

function setTools(view, labels) {
  view.tools.replaceChildren();
  for (const l of labels) {
    const d = document.createElement("div");
    d.className = "tool-line";
    d.textContent = l;
    view.tools.appendChild(d);
  }
}

function scrollDown(force) {
  const box = $("#messages");
  if (force || box.scrollHeight - box.scrollTop - box.clientHeight < 160) box.scrollTop = box.scrollHeight;
}

// ------------------------------------------------------------------ envoi + réponse en direct
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); sendMessage($("#input").value); });
$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && window.matchMedia("(min-width: 900px)").matches) {
    e.preventDefault(); sendMessage($("#input").value);
  }
});
$("#input").addEventListener("input", autoGrow);
function autoGrow() { const t = $("#input"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 160) + "px"; }
$("#stop").addEventListener("click", () => {
  state.controller?.abort();
  if (state.localRunning && window.SyriusLocal) window.SyriusLocal.stop();
});

function setStreaming(on) {
  state.streaming = on;
  $("#send").classList.toggle("hidden", on);
  $("#stop").classList.toggle("hidden", !on);
  document.querySelectorAll(".orb.small").forEach((o) => o.classList.toggle("thinking", on));
}

// ------------------------------------------------------------------ IA hors ligne (sur le téléphone)
let localTimer = null;
function refreshLocalBox() {
  const l = L();
  const box = $("#local-box");
  const inApp = !!window.SyriusAndroid;
  const old = inApp && !(l && l.available()); // application installée trop ancienne
  box.classList.toggle("hidden", !inApp);
  $("#local-update").classList.toggle("hidden", !old);
  $("#local-ui").classList.toggle("hidden", old);
  if (!inApp || old) return;
  const i = l.info() || {};
  const sel = $("#local-model");
  if (!sel.options.length) {
    (i.models || []).forEach((m) => sel.appendChild(new Option(m.label, m.id)));
  }
  if (i.installed) sel.value = i.installed;
  const busy = !!(i.downloading || i.verifying);
  $("#local-download").classList.toggle("hidden", busy);
  $("#local-download").textContent = i.installed ? "🔁 Changer de modèle" : "⬇ Télécharger";
  $("#local-delete").classList.toggle("hidden", !i.installed && !busy);
  $("#local-delete").textContent = busy ? "✕ Annuler" : "🗑 Supprimer";
  $("#local-progress").classList.toggle("hidden", !i.downloading);
  if (i.downloading) {
    $("#local-progress progress").value = i.progress || 0;
    $("#local-progress span").textContent = `${i.progress || 0} %`;
  }
  $("#local-status").textContent = i.error ? "⚠ " + i.error
    : i.verifying ? "🔒 Vérification de l'empreinte du fichier…"
    : i.downloading ? "Téléchargement en cours (tu peux fermer cet écran, il continue)…"
    : i.installed ? "✅ Installée et prête." : "Pas encore installée.";
  $("#local-fallback").checked = l.prefs.fallback;
  $("#local-force").checked = l.prefs.force;
  clearTimeout(localTimer);
  if (busy && $("#settings").open) localTimer = setTimeout(refreshLocalBox, 1500);
}

$("#local-download").addEventListener("click", () => {
  const l = L();
  const id = $("#local-model").value;
  const m = ((l.info() || {}).models || []).find((x) => x.id === id);
  const go = confirm(`Télécharger ${m ? m.label : "le modèle"} ? Utilise de préférence le Wi-Fi.`);
  if (!go) return;
  const r = window.SyriusAndroid.localDownload(id);
  if (r !== "ok") alert(r);
  setTimeout(refreshLocalBox, 500);
});
$("#local-delete").addEventListener("click", () => {
  const i = L().info() || {};
  if (i.downloading) window.SyriusAndroid.localCancel();
  else if (confirm("Supprimer l'IA hors ligne de ce téléphone ?")) window.SyriusAndroid.localDelete();
  setTimeout(refreshLocalBox, 300);
});
$("#local-fallback").addEventListener("change", (e) => { L().prefs.fallback = e.target.checked; });
$("#local-force").addEventListener("change", (e) => { L().prefs.force = e.target.checked; });
const L = () => window.SyriusLocal;
function localWanted() {
  const l = L();
  return !!(l && l.ready() && (l.prefs.force || state.offline || !navigator.onLine));
}

async function answerLocally(view, note) {
  const l = L();
  const history = (state.views || []).filter((v) => v.wrap.isConnected && v !== view)
    .map((v) => ({ role: v.role, text: v.text }));
  setTools(view, [note || "📴 IA hors ligne (sur ton téléphone)"]);
  setStreaming(true);
  state.localRunning = true;
  let pending = false;
  try {
    await l.chat(history, (full) => {
      view.text = full;
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; renderText(view, "assistant"); scrollDown(); });
    });
  } catch (err) {
    showError(view, err.message || "IA hors ligne indisponible.");
  } finally {
    state.localRunning = false;
    setStreaming(false);
    renderText(view, "assistant");
    state.lastReply = view.text;
    if (view.text && state.settings.voice_reply && !window.SyriusVoice?.active) speak(view.text);
  }
}

async function sendLocal(text) {
  $("#input").value = "";
  autoGrow();
  addMessage("user", text);
  const view = addMessage("assistant", "");
  scrollDown(true);
  await answerLocally(view);
}

async function sendMessage(text) {
  text = (text || "").trim();
  if (!text || state.streaming) return;
  if (localWanted()) return sendLocal(text);
  if (!state.convId) {
    const conv = await api("/api/conversations", { method: "POST" });
    state.convId = conv.id;
    store.set("syrius:lastConv", conv.id);
    $("#messages").replaceChildren();
    loadConversations();
  }
  $("#input").value = "";
  autoGrow();
  addMessage("user", text);
  const view = addMessage("assistant", "");
  const typing = document.createElement("div");
  typing.className = "typing";
  typing.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
  view.body.appendChild(typing);
  scrollDown(true);

  setStreaming(true);
  state.controller = new AbortController();
  const tools = [];
  let pending = false, gotError = false;
  const repaint = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; renderText(view, "assistant"); scrollDown(); });
  };

  try {
    const res = await fetch(`/api/conversations/${state.convId}/messages`, {
      method: "POST", credentials: "same-origin", signal: state.controller.signal,
      headers: { "Content-Type": "application/json", "X-Syrius": "1" },
      body: JSON.stringify({ text, location: state.settings.location === false ? null : state.location,
        voice: !!window.SyriusVoice?.active }),
    });
    if (res.status === 401) { showLogin(); return; }
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
        if (ev.type === "text") { view.text += ev.text; repaint(); }
        else if (ev.type === "text_replace") { view.text = String(ev.text || ""); repaint(); }
        else if (ev.type === "tool") { tools.push(ev.label); setTools(view, [...new Set(tools)]); scrollDown(); }
        else if (ev.type === "action") { view.bubble.appendChild(actionCard(ev)); scrollDown(); }
        else if (ev.type === "device") { handleDevice(view, ev); scrollDown(); }
        else if (ev.type === "map") { addMapCard(view, ev); if (window.SyriusHUD) window.SyriusHUD.show(ev); }
        else if (ev.type === "diagram") { addDiagramCard(view, ev); if (window.SyriusHolo) window.SyriusHolo.show(ev); }
        else if (ev.type === "weather") { addWeatherCard(view, ev); scrollDown(); }
        else if (ev.type === "model") { addDiagramCard(view, ev); if (window.SyriusModel) window.SyriusModel.show(ev); }
        else if (ev.type === "memory") { tools.push("Souvenir enregistré : " + ev.content); setTools(view, [...new Set(tools)]); }
        else if (ev.type === "title") { $("#conv-title").textContent = ev.title; loadConversations(); }
        else if (ev.type === "error") { gotError = true; showError(view, ev.message); }
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") { gotError = true; showError(view, err.message || "Connexion perdue."); }
  } finally {
    setStreaming(false);
    renderText(view, "assistant");
    const l = L();
    if (gotError && !view.text && l && l.ready() && l.prefs.fallback) {
      // Toutes les IA en ligne sont épuisées ou injoignables : le téléphone prend le relais.
      view.bubble.querySelectorAll(".msg-error").forEach((e) => e.remove());
      await answerLocally(view, "📴 IA en ligne indisponible → réponse hors ligne (sur ton téléphone)");
      return;
    }
    if (gotError && !view.text) $("#input").value = text; // on rend le message pour réessayer
    state.lastReply = view.text;
    if (!gotError && view.text && state.settings.voice_reply && !window.SyriusVoice?.active) speak(view.text);
    loadConversations();
  }
}

function showError(view, msg) {
  const p = document.createElement("p");
  p.className = "msg-error";
  p.textContent = "⚠ " + msg;
  view.bubble.appendChild(p);
}

// ------------------------------------------------------------------ position et carte
// Position approximative, demandée seulement si le réglage est activé. Jamais enregistrée sur le serveur.
function refreshLocation() {
  if (state.settings.location === false || !("geolocation" in navigator)) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => { state.location = { lat: pos.coords.latitude, lon: pos.coords.longitude }; },
    () => { state.location = null; },
    { enableHighAccuracy: false, maximumAge: 300000, timeout: 15000 },
  );
}

function addMapCard(view, ev) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "action-card map-card";
  const n = Array.isArray(ev.places) ? ev.places.length : 0;
  card.textContent = `🗺 ${n} lieu${n > 1 ? "x" : ""} sur la carte — ouvrir`;
  card.addEventListener("click", () => window.SyriusHUD && window.SyriusHUD.show(ev));
  view.bubble.appendChild(card);
}

// Carte météo (tout le texte passe par textContent).
function addWeatherCard(view, w) {
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  };
  const deg = (v) => (typeof v === "number" ? `${Math.round(v)}°` : "–");
  const n = w.now || {};
  const card = el("div", "wx-card");
  const head = el("div", "wx-head");
  head.append(el("div", "wx-place", "◈ MÉTÉO · " + String(w.place || "").toUpperCase()));
  const main = el("div", "wx-main");
  main.append(el("div", "wx-icon", n.icon || "🌡"), el("div", "wx-temp", deg(n.temp)));
  const info = el("div", "wx-info");
  info.append(el("div", "wx-label", n.label || ""),
    el("div", "wx-meta", `Ressenti ${deg(n.feels)} · Vent ${n.wind ?? "–"} km/h · Humidité ${n.humidity ?? "–"} %`));
  main.append(info);
  const hours = el("div", "wx-hours");
  (w.hours || []).forEach((h) => {
    const c = el("div", "wx-hour");
    c.append(el("span", "", h.h), el("span", "wx-hicon", h.icon), el("b", "", deg(h.temp)),
      el("small", "", typeof h.rain === "number" && h.rain >= 20 ? `💧${Math.round(h.rain)}%` : " "));
    hours.append(c);
  });
  const days = el("div", "wx-days");
  (w.days || []).forEach((d) => {
    const r = el("div", "wx-day");
    r.append(el("span", "wx-dname", d.day), el("span", "wx-dicon", d.icon),
      el("span", "wx-drain", typeof d.rain === "number" && d.rain >= 20 ? `💧${Math.round(d.rain)}%` : ""),
      el("span", "wx-dtemp", `${deg(d.min)} / ${deg(d.max)}`));
    days.append(r);
  });
  card.append(head, main, hours, days, el("div", "wx-src", "Open-Meteo"));
  view.bubble.appendChild(card);
}

function addDiagramCard(view, ev) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "action-card map-card";
  const isModel = ev.type === "model";
  card.textContent = `${isModel ? "🧊 Maquette 3D" : "🧠 Schéma 3D"} : ${String(ev.title || "").slice(0, 60)} — ouvrir`;
  card.addEventListener("click", () => {
    if (isModel) { if (window.SyriusModel) window.SyriusModel.show(ev); }
    else if (window.SyriusHolo) window.SyriusHolo.show(ev);
  });
  view.bubble.appendChild(card);
}

// ------------------------------------------------------------------ actions sur le téléphone
const DEVICE_TEXT = {
  phone_alarm: (p) => `⏰ Réveil à ${String(p.hour).padStart(2, "0")}h${String(p.minute).padStart(2, "0")}`,
  phone_timer: (p) => `⏱ Minuteur de ${Math.round(p.seconds / 60) || 1} min`,
  phone_call: (p) => `📞 Appeler ${p.contact}`,
  phone_sms: (p) => `💬 SMS à ${p.contact} : « ${p.message} »`,
  phone_open_app: (p) => `📱 Ouvrir ${p.app}`,
  phone_map: (p) => `🗺 ${p.navigate ? "Itinéraire vers" : "Carte :"} ${p.query}`,
  phone_open_url: (p) => `🔗 Ouvrir ${p.url}`,
  phone_flashlight: (p) => `🔦 Lampe ${p.on ? "allumée" : "éteinte"}`,
  phone_volume: (p) => `🔊 Volume à ${p.level} %`,
  phone_settings: (p) => `⚙ Réglages : ${p.page.replace("_", " ")}`,
  phone_reminder: (p) => `⏰ Rappel ${p.label} : « ${p.text} »` +
    (p.repeat === "daily" ? " (tous les jours)" : p.repeat === "weekly" ? " (chaque semaine)" : ""),
  phone_reminder_cancel: () => "🗑 Rappel annulé",
  phone_music: (p) => p.action === "play" ? `🎵 ${p.query}${p.app && p.app !== "auto" ? " · " + p.app.replace("_", " ") : ""}`
    : { pause: "⏸ Pause", resume: "▶ Reprise", next: "⏭ Titre suivant", previous: "⏮ Titre précédent" }[p.action],
  phone_calendar: (p) => `📅 ${p.title} — ${p.label}${p.location ? " · " + p.location : ""}`,
};

// Actions qui demandent une version récente de l'application Android.
const NEEDS_FEATURE = { phone_reminder: "reminders", phone_reminder_cancel: "reminders", phone_calendar: "calendar",
  phone_music: "music" };
function appFeatures() {
  try { return Native && typeof Native.features === "function" ? JSON.parse(Native.features()) : []; } catch (_) { return []; }
}

function runDevice(ev) {
  if (!Native) return "Tu es sur le site (navigateur), pas dans l'application Android Syrius : ouvre l'application téléchargée.";
  if (typeof Native.device !== "function" || (NEEDS_FEATURE[ev.action] && !appFeatures().includes(NEEDS_FEATURE[ev.action]))) {
    return "Ton application Syrius est une ancienne version : Réglages → IA hors ligne → « Télécharger la nouvelle version ».";
  }
  try { return Native.device(JSON.stringify({ action: ev.action, params: ev.params })) || "ok"; }
  catch (_) { return "Action impossible sur ce téléphone."; }
}

function handleDevice(view, ev) {
  const card = document.createElement("div");
  card.className = "action-card";
  const title = document.createElement("div");
  title.className = "action-title";
  title.textContent = (DEVICE_TEXT[ev.action] || (() => ev.action))(ev.params || {});
  const status = document.createElement("p");
  status.className = "small";
  card.append(title);
  const finish = (res) => { status.textContent = res === "ok" ? "✅ Envoyé au téléphone." : "⚠ " + res; };
  if (ev.confirm) {
    if (ev.after_untrusted) {
      const warn = document.createElement("p");
      warn.className = "small msg-error";
      warn.textContent = "Syrius vient de lire un email ou une page web : vérifie bien que c'est toi qui as demandé cette action.";
      card.append(warn);
    }
    const row = document.createElement("div");
    row.className = "action-buttons";
    const ok = document.createElement("button");
    ok.className = "primary"; ok.textContent = "Confirmer";
    const no = document.createElement("button");
    no.className = "ghost"; no.textContent = "Annuler";
    let decided = false;
    const accept = () => { if (decided) return; decided = true; row.remove(); finish(runDevice(ev)); };
    const refuse = () => { if (decided) return; decided = true; row.remove(); status.textContent = "Annulé."; };
    ok.addEventListener("click", accept);
    no.addEventListener("click", refuse);
    row.append(ok, no);
    card.append(row);
    // Mode conversation : la confirmation se fait aussi à la voix (« oui » / « non »).
    if (window.SyriusVoice?.active) window.SyriusVoice.confirm(title.textContent, accept, refuse);
  } else {
    finish(runDevice(ev));
  }
  card.append(status);
  view.bubble.appendChild(card);
}

function actionCard(ev) {
  const node = $("#tpl-action").content.firstElementChild.cloneNode(true);
  node.querySelector(".a-to").textContent = ev.to;
  node.querySelector(".a-subject").textContent = ev.subject;
  node.querySelector(".a-body").textContent = ev.body;
  const status = node.querySelector(".a-status");
  const buttons = node.querySelectorAll(".action-buttons button");
  const finish = (msg) => { buttons.forEach((b) => b.remove()); status.textContent = msg; };
  node.querySelector(".a-send").addEventListener("click", async () => {
    buttons.forEach((b) => { b.disabled = true; });
    try { await api(`/api/actions/${ev.id}/confirm`, { method: "POST" }); finish("✅ Email envoyé."); }
    catch (err) { status.textContent = "⚠ " + err.message; buttons.forEach((b) => { b.disabled = false; }); }
  });
  node.querySelector(".a-cancel").addEventListener("click", async () => {
    try { await api(`/api/actions/${ev.id}/cancel`, { method: "POST" }); } catch (_) { /* ignore */ }
    finish("Annulé.");
  });
  return node;
}

// ------------------------------------------------------------------ état du réseau (en-tête)
function updateNetStatus() {
  const off = state.offline || !navigator.onLine;
  const local = L() && L().prefs && L().available() && L().prefs.force;
  const el = $("#net-status");
  el.textContent = off ? "hors ligne" : local ? "IA du téléphone" : "en ligne";
  el.classList.toggle("off", off);
  const tag = document.querySelector(".hero-tag");
  if (tag) tag.textContent = "◈ SYRIUS · " + (off ? "HORS LIGNE" : "EN LIGNE");
}
window.addEventListener("online", updateNetStatus);
window.addEventListener("offline", updateNetStatus);
setTimeout(updateNetStatus, 500);

// ------------------------------------------------------------------ briefing du matin
const BRIEFING_PROMPT = "Fais-moi mon briefing du matin : la météo près de moi, mes rappels prévus aujourd'hui " +
  "(list_reminders) et 3 actualités importantes du jour, le tout en quelques phrases claires.";
let briefingWaiting = false;
window.syriusBriefing = async () => {
  if ($("#app").classList.contains("hidden")) { briefingWaiting = true; return; } // après connexion
  newConversationView();
  const reply = await window.SyriusChat.ask(BRIEFING_PROMPT);
  if (reply && !state.settings.voice_reply) speak(reply);
};

// ------------------------------------------------------------------ « Hey Syrius »
let wakeTimer = null;
function refreshWakeBox() {
  const ok = Native && appFeatures().includes("wake");
  $("#wake-box").classList.toggle("hidden", !ok);
  if (!ok) return;
  let w = {};
  try { w = JSON.parse(Native.wakeInfo()); } catch (_) { /* */ }
  const busy = !!(w.downloading || w.installing);
  $("#wake-download").classList.toggle("hidden", !!w.ready || busy);
  $("#wake-progress").classList.toggle("hidden", !w.downloading);
  if (w.downloading) {
    $("#wake-progress progress").value = w.progress || 0;
    $("#wake-progress span").textContent = `${w.progress || 0} %`;
  }
  $("#wake-on").disabled = !w.ready;
  const canOpen = typeof Native.canOpenApps === "function" && Native.canOpenApps();
  $("#wake-overlay").textContent = canOpen ? "✅ Musique app fermée autorisée" : "🎵 Lancer la musique app fermée (autoriser)";
  $("#wake-on").checked = !!w.enabled;
  $("#wake-status").textContent = w.error ? "⚠ " + w.error
    : w.installing ? "🔒 Vérification et installation…"
    : w.downloading ? "Téléchargement…"
    : !w.ready ? "Installe d'abord la reconnaissance vocale."
    : w.enabled ? "✅ Syrius écoute « Hey Syrius »." : "Prêt. Active l'écoute ci-dessus.";
  // Diagnostic en direct : ce que l'écoute entend (rien n'est envoyé, tout reste sur le téléphone).
  const live = !!(w.ready && w.enabled);
  $("#wake-live").classList.toggle("hidden", !live);
  if (live) {
    const ago = typeof w.heardAgo === "number" && w.heardAgo >= 0 ? ` (il y a ${w.heardAgo} s)` : "";
    $("#wake-heard").textContent = w.heard ? `« ${w.heard} »${ago}` : "rien pour l'instant — parle près du téléphone";
    if (w.status && w.status !== "listening") $("#wake-status").textContent = "⚠ " + (w.status === "stopped" ? "L'écoute est arrêtée (le téléphone l'a peut-être coupée : touche 🔋)." : w.status);
    const learned = (w.learned || []).join(" · ");
    $("#wake-learn-msg").textContent = w.learning
      ? `🎙 Dis « Hey Syrius » … (${w.learnCount || 0}/3), une phrase à la fois, puis attends 2 secondes.`
      : learned ? `✅ Appris : ${learned}` : "";
    $("#wake-learn").textContent = w.learning ? "✕ Arrêter l'apprentissage" : "🎓 Apprendre ma façon de dire « Hey Syrius »";
  }
  clearTimeout(wakeTimer);
  if ((busy || live) && $("#settings").open) wakeTimer = setTimeout(refreshWakeBox, busy ? 1500 : 1000);
}
$("#wake-learn").addEventListener("click", () => {
  let w = {};
  try { w = JSON.parse(Native.wakeInfo()); } catch (_) { /* */ }
  Native.wakeLearn(!w.learning);
  setTimeout(refreshWakeBox, 200);
});
$("#wake-download").addEventListener("click", () => {
  const r = Native.wakeDownload();
  if (r !== "ok") alert(r);
  setTimeout(refreshWakeBox, 500);
});
$("#wake-on").addEventListener("change", (e) => {
  const r = Native.wakeEnable(e.target.checked);
  if (r !== "ok") { $("#wake-status").textContent = "⚠ " + r; e.target.checked = false; return; }
  setTimeout(refreshWakeBox, 300);
});
$("#wake-battery").addEventListener("click", () => Native.batterySettings());
$("#wake-overlay").addEventListener("click", () => Native.overlaySettings());

function refreshBriefingBox() {
  const ok = Native && appFeatures().includes("briefing");
  $("#briefing-box").classList.toggle("hidden", !ok);
  if (!ok) return;
  let b = { on: false, hour: 7, minute: 30 };
  try { b = JSON.parse(Native.getBriefing()); } catch (_) { /* défaut */ }
  $("#briefing-on").checked = !!b.on;
  $("#briefing-time").value = `${String(b.hour).padStart(2, "0")}:${String(b.minute).padStart(2, "0")}`;
}
function saveBriefing() {
  const [h, m] = ($("#briefing-time").value || "07:30").split(":").map(Number);
  const r = Native.setBriefing($("#briefing-on").checked, h || 0, m || 0);
  $("#briefing-msg").textContent = r === "ok"
    ? ($("#briefing-on").checked ? `✅ Chaque jour à ${$("#briefing-time").value}.` : "Briefing désactivé.") : "⚠ " + r;
}
$("#briefing-on").addEventListener("change", saveBriefing);
$("#briefing-time").addEventListener("change", saveBriefing);

// Pour le mode conversation : envoie une phrase et renvoie la réponse complète.
window.SyriusChat = {
  async ask(text) {
    state.lastReply = "";
    await sendMessage(text);
    return state.lastReply || "";
  },
};

// ------------------------------------------------------------------ voix
// Dans l'application Android, la voix passe par le téléphone (pont "SyriusAndroid").
const Native = window.SyriusAndroid || null;

function speak(text) {
  const clean = text.replace(/[`*#>_\[\]()]/g, "").replace(/https?:\/\/\S+/g, "lien").slice(0, 1500);
  if (Native) { Native.speak(clean); return; }
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(clean);
  u.lang = "fr-FR";
  const voice = speechSynthesis.getVoices().find((v) => v.lang && v.lang.startsWith("fr"));
  if (voice) u.voice = voice;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (Native) {
  const mic = $("#mic");
  mic.classList.remove("hidden");
  let base = "";
  // Appelé par l'application Android avec le texte reconnu.
  window.syriusOnSpeech = (text, isFinal) => {
    $("#input").value = (base ? base + " " : "") + String(text || "");
    autoGrow();
    if (isFinal) { mic.classList.remove("listening"); if (text) sendMessage($("#input").value); }
  };
  window.syriusOnSpeechEnd = () => mic.classList.remove("listening");
  mic.addEventListener("click", () => {
    if (mic.classList.contains("listening")) { Native.stopListening(); return; }
    base = $("#input").value;
    mic.classList.add("listening");
    Native.startListening();
  });
} else if (Recognition) {
  const mic = $("#mic");
  mic.classList.remove("hidden");
  let rec = null;
  mic.addEventListener("click", () => {
    if (rec) { rec.stop(); return; }
    rec = new Recognition();
    rec.lang = "fr-FR";
    rec.interimResults = true;
    const base = $("#input").value;
    rec.onresult = (e) => {
      let t = "";
      for (const r of e.results) t += r[0].transcript;
      $("#input").value = (base ? base + " " : "") + t;
      autoGrow();
      if (e.results[e.results.length - 1].isFinal) { rec.stop(); sendMessage($("#input").value); }
    };
    rec.onend = () => { mic.classList.remove("listening"); rec = null; };
    mic.classList.add("listening");
    rec.start();
  });
}

// ------------------------------------------------------------------ réglages
async function loadSettings() {
  state.settings = await api("/api/settings");
  state.offline = false;
}

$("#open-settings").addEventListener("click", async () => {
  await loadSettings();
  const s = state.settings;
  $("#s-name").value = s.user_name || "";
  $("#s-custom").value = s.custom_instructions || "";
  $("#s-effort").value = s.effort === "low" ? "low" : "high";
  $("#s-web").checked = s.internet !== false;
  $("#s-web").disabled = false;
  $("#s-web-note").textContent = "Internet passe par un pare-feu : pages publiques uniquement, contenu jamais pris pour un ordre.";
  $("#s-voice").checked = !!s.voice_reply;
  $("#s-location").checked = s.location !== false;
  await renderBrains(s);
  $("#outlook-box").classList.toggle("hidden", !s.outlook);
  $("#google-box").classList.toggle("hidden", !s.google);
  $("#google-connect").textContent = s.google_connected ? "Reconnecter Gmail" : "Connecter Gmail";
  $("#google-msg").textContent = s.google_connected ? "✅ Gmail est connecté." : "";
  $("#outlook-msg").textContent = "";
  $("#s-email").textContent = s.email_enabled
    ? "✅ Boîte mail connectée (lecture seule ; chaque envoi demande ta confirmation)."
    : "Non configurés. Voir le guide d'installation (README, section Emails).";
  $("#settings-msg").textContent = "";
  await renderMemories();
  closeDrawer();
  refreshLocalBox();
  refreshBriefingBox();
  refreshWakeBox();
  $("#settings").showModal();
});

async function renderBrains(s) {
  const sel = $("#s-brain");
  sel.replaceChildren();
  let brains = [];
  try { brains = await api("/api/brains"); } catch (_) { /* ignore */ }
  const auto = document.createElement("option");
  auto.value = "";
  auto.textContent = "Automatique" + (brains[0] ? ` (${brains[0].label} d'abord)` : "");
  sel.appendChild(auto);
  for (const b of brains) {
    const o = document.createElement("option");
    o.value = b.name;
    o.textContent = `${b.label} — ${b.model}`;
    sel.appendChild(o);
  }
  sel.value = brains.some((b) => b.name === s.brain) ? s.brain : "";
}

async function renderMemories() {
  const list = await api("/api/memories");
  const ul = $("#memory-list");
  ul.replaceChildren();
  if (!list.length) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = "Rien pour l'instant.";
    ul.appendChild(li);
  }
  for (const m of list) {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = m.content;
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "🗑";
    del.setAttribute("aria-label", "Supprimer ce souvenir");
    del.addEventListener("click", async () => { await api(`/api/memories/${m.id}`, { method: "DELETE" }); renderMemories(); });
    li.append(span, del);
    ul.appendChild(li);
  }
}

$("#google-connect").addEventListener("click", async () => {
  const msg = $("#google-msg");
  try {
    const { url } = await api("/api/email/google/start", { method: "POST" });
    msg.textContent = "La page de Google s'ouvre : connecte-toi, accepte, puis reviens ici et rouvre les réglages.";
    // Dans l'application Android, ce lien s'ouvre dans le navigateur du téléphone (Google l'exige).
    if (Native) location.href = url; else window.open(url, "_blank", "noopener");
  } catch (err) { msg.textContent = "⚠ " + err.message; }
});

$("#outlook-connect").addEventListener("click", async () => {
  const msg = $("#outlook-msg");
  try {
    const info = await api("/api/email/outlook/start", { method: "POST" });
    msg.replaceChildren();
    msg.append("Ouvre ");
    const a = document.createElement("a");
    a.href = info.verification_uri; a.target = "_blank"; a.rel = "noopener noreferrer";
    a.textContent = info.verification_uri;
    const b = document.createElement("b");
    b.textContent = info.user_code;
    msg.append(a, " et entre le code ", b, ". J'attends ta validation…");
    const timer = setInterval(async () => {
      try {
        const r = await api("/api/email/outlook/poll", { method: "POST" });
        if (r.status === "ok") { clearInterval(timer); msg.textContent = "✅ Outlook connecté."; }
      } catch (err) { clearInterval(timer); msg.textContent = "⚠ " + err.message; }
    }, Math.max(5, info.interval || 5) * 1000);
  } catch (err) { msg.textContent = "⚠ " + err.message; }
});

$("#settings-save").addEventListener("click", async () => {
  try {
    state.settings = {
      ...state.settings,
      ...(await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({
          user_name: $("#s-name").value.trim(),
          custom_instructions: $("#s-custom").value,
          effort: $("#s-effort").value,
          brain: $("#s-brain").value,
          internet: $("#s-web").checked,
          location: $("#s-location").checked,
          voice_reply: $("#s-voice").checked,
        }),
      })),
    };
    $("#settings-msg").textContent = "✅ Enregistré.";
    if (!state.convId) $("#greeting").textContent = greeting();
  } catch (err) { $("#settings-msg").textContent = "⚠ " + err.message; }
});

$("#pw-save").addEventListener("click", async () => {
  try {
    const r = await api("/api/password", { method: "POST",
      body: JSON.stringify({ current: $("#pw-current").value, new: $("#pw-new").value }) });
    $("#pw-msg").textContent = r.detail;
    setTimeout(() => { $("#settings").close(); showLogin(); }, 1200);
  } catch (err) { $("#pw-msg").textContent = "⚠ " + err.message; }
});

// ------------------------------------------------------------------ démarrage
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* hors ligne ou non supporté */ });
}

(async () => {
  try {
    const s = await (await fetch("/api/session", { credentials: "same-origin" })).json();
    if (s.authenticated) await showApp();
    else {
      showLogin();
      if (s.setup_available) {
        $("#login-form").classList.add("hidden");
        $("#setup-form").classList.remove("hidden");
      } else if (!s.password_set) {
        $("#login-error").textContent =
          "Aucun mot de passe défini : ajoute SYRIUS_SETUP_CODE dans Vercel (voir README).";
      }
    }
  } catch (_) {
    const l = L();
    if (l && l.ready()) { // pas de réseau : Syrius démarre en mode hors ligne
      state.offline = true;
      $("#login").classList.add("hidden");
      $("#app").classList.remove("hidden");
      newConversationView();
      $("#conv-title").textContent = "📴 Syrius hors ligne";
      return;
    }
    showLogin();
    $("#login-error").textContent = "Serveur injoignable.";
  }
})();
