"use strict";

const $ = (s) => document.querySelector(s);
const emptyNode = document.getElementById("empty");
const state = {
  convId: null,
  conversations: [],
  settings: {},
  streaming: false,
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
  await loadConversations();
  const last = store.get("syrius:lastConv");
  if (last && state.conversations.some((c) => c.id === last)) await openConversation(last);
  else newConversationView();
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
  const view = { wrap, bubble, tools, body, text: text || "" };
  renderText(view, role);
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
$("#stop").addEventListener("click", () => state.controller?.abort());

function setStreaming(on) {
  state.streaming = on;
  $("#send").classList.toggle("hidden", on);
  $("#stop").classList.toggle("hidden", !on);
  document.querySelectorAll(".orb.small").forEach((o) => o.classList.toggle("thinking", on));
}

async function sendMessage(text) {
  text = (text || "").trim();
  if (!text || state.streaming) return;
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
      body: JSON.stringify({ text }),
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
        else if (ev.type === "tool") { tools.push(ev.label); setTools(view, [...new Set(tools)]); scrollDown(); }
        else if (ev.type === "action") { view.bubble.appendChild(actionCard(ev)); scrollDown(); }
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
    if (gotError && !view.text) $("#input").value = text; // on rend le message pour réessayer
    if (!gotError && view.text && state.settings.voice_reply) speak(view.text);
    loadConversations();
  }
}

function showError(view, msg) {
  const p = document.createElement("p");
  p.className = "msg-error";
  p.textContent = "⚠ " + msg;
  view.bubble.appendChild(p);
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

// ------------------------------------------------------------------ voix
function speak(text) {
  if (!("speechSynthesis" in window)) return;
  const clean = text.replace(/[`*#>_\[\]()]/g, "").replace(/https?:\/\/\S+/g, "lien").slice(0, 1500);
  const u = new SpeechSynthesisUtterance(clean);
  u.lang = "fr-FR";
  const voice = speechSynthesis.getVoices().find((v) => v.lang && v.lang.startsWith("fr"));
  if (voice) u.voice = voice;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (Recognition) {
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
}

$("#open-settings").addEventListener("click", async () => {
  await loadSettings();
  const s = state.settings;
  $("#s-name").value = s.user_name || "";
  $("#s-custom").value = s.custom_instructions || "";
  $("#s-effort").value = s.effort === "low" ? "low" : "high";
  $("#s-web").checked = !!s.web_search && s.web_search_available;
  $("#s-web").disabled = !s.web_search_available;
  $("#s-web-note").textContent = s.web_search_available ? ""
    : "Pour l'activer : clé gratuite Ollama dans le fichier .env (voir README).";
  $("#s-voice").checked = !!s.voice_reply;
  await renderModels(s);
  $("#s-email").textContent = s.email_enabled
    ? "✅ Boîte mail connectée (lecture seule ; chaque envoi demande ta confirmation)."
    : "Non configurés. Voir le guide d'installation (README, section Emails).";
  $("#settings-msg").textContent = "";
  await renderMemories();
  closeDrawer();
  $("#settings").showModal();
});

async function renderModels(s) {
  const sel = $("#s-model-choice");
  sel.replaceChildren();
  let installed = [];
  try { installed = (await api("/api/models")).installed; } catch (_) { /* ignore */ }
  const def = document.createElement("option");
  def.value = "";
  def.textContent = `Par défaut (${s.default_model})`;
  sel.appendChild(def);
  for (const name of installed) {
    const o = document.createElement("option");
    o.value = name;
    o.textContent = name;
    sel.appendChild(o);
  }
  sel.value = installed.includes(s.model) ? s.model : "";
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
          model: $("#s-model-choice").value,
          web_search: $("#s-web").checked,
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
      if (!s.password_set) $("#login-error").textContent =
        "Aucun mot de passe défini. Sur le serveur, lance : python -m server.manage set-password";
    }
  } catch (_) {
    showLogin();
    $("#login-error").textContent = "Serveur injoignable.";
  }
})();
