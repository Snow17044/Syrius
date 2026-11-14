"use strict";

const $ = (s) => document.querySelector(s);
const emptyNode = document.getElementById("empty");
const Icons = window.SyriusIcons;

// Messages d'état : « ✅ … », « ⚠ … », « 🔒 … » deviennent une icône dessinée + le texte (jamais d'emoji affiché).
const MARKS = { "✅": ["ok", "ok"], "⚠": ["warn", "alert"], "🔒": ["info", "lock"], "🎙": ["info", "mic"] };
function setMsg(el, text) {
  if (!el) return;
  const t = String(text == null ? "" : text);
  const m = /^(✅|⚠|🔒|🎙)\uFE0F?\s*/u.exec(t);
  el.classList.remove("stat", "ok", "warn", "info");
  if (!m) { el.textContent = t; return; }
  const [kind, icon] = MARKS[m[1]];
  el.classList.add("stat", kind);
  Icons.set(el, icon, t.slice(m[0].length));
}
// Les zones d'état des réglages se mettent à jour toutes seules quand leur texte change.
function watchMsg(el) {
  if (!el) return;
  new MutationObserver(() => {
    const f = el.firstChild;
    if (!f || f.nodeType !== 3) return; // déjà décoré (icône + texte)
    if (/^(✅|⚠|🔒|🎙)/u.test(f.data)) setMsg(el, el.textContent);
    else el.classList.remove("stat", "ok", "warn", "info");
  }).observe(el, { childList: true, characterData: true, subtree: true });
}
document.addEventListener("DOMContentLoaded", () => {
  ["#local-status", "#wake-status", "#wake-learn-msg", "#briefing-msg", "#google-msg", "#outlook-msg",
    "#settings-msg", "#pw-msg", "#family-msg", "#del-msg"].forEach((q) => watchMsg($(q)));
  document.querySelectorAll(".pack-status").forEach(watchMsg);
});

// Icône d'une étape affichée pendant la réponse (« Je cherche sur le web », etc.).
const TOOL_ICONS = [[/web|cherch|recherch|page|article|actu/i, "search"], [/carte|lieu|itin|adresse/i, "map"],
  [/météo|temps qu/i, "partly"], [/mail/i, "mail"], [/souvenir|mémoire|retenu/i, "bulb"], [/schéma/i, "nodes"],
  [/maquette|3d/i, "cube"], [/image|dessin/i, "sparkle"], [/rappel/i, "bell"], [/agenda|rendez/i, "calendar"],
  [/musique/i, "music"], [/appel/i, "phone"], [/sms/i, "message"], [/réveil/i, "alarm"], [/minuteur/i, "timer"],
  [/vision|photo/i, "eye"], [/hors ligne|téléphone/i, "chip"], [/lampe/i, "flashlight"], [/volume/i, "volume"]];
function toolIcon(label) {
  for (const [re, name] of TOOL_ICONS) if (re.test(label)) return name;
  return "sparkle";
}
function stripMark(t) { return String(t || "").replace(/^[^\p{L}\p{N}«"(]+/u, ""); }
function node(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}
// En-tête de carte : pastille d'icône + titre + sous-titre.
function cardHead(icon, title, sub) {
  const head = node("div", "card-head");
  const ic = node("div", "card-icon");
  ic.append(Icons.svg(icon));
  const txt = node("div", "card-text");
  txt.append(node("div", "card-title", title));
  if (sub) txt.append(node("div", "card-sub", sub));
  head.append(ic, txt);
  return head;
}
// Ajoute une carte sous la réponse ; pendant la conversation vocale, elle s'affiche aussi en direct à côté.
function placeCard(view, card) {
  view.bubble.appendChild(card);
  if (window.SyriusVoice && window.SyriusVoice.active && window.SyriusVoice.stage) window.SyriusVoice.stage(card);
  return card;
}
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
  if (!$("#login-name").value) $("#login-name").value = store.get("syrius:loginName") || "";
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
    const name = $("#login-name").value.trim();
    await api("/api/login", { method: "POST", body: JSON.stringify(
      name ? { name, password: $("#login-password").value } : { password: $("#login-password").value }) });
    $("#login-password").value = "";
    store.set("syrius:loginName", name);
    await showApp();
  } catch (err) { $("#login-error").textContent = err.message; }
});

// ------------------------------------------------------------------ famille
function showJoin(on) {
  $("#login-form").classList.toggle("hidden", on);
  $("#join-form").classList.toggle("hidden", !on);
  $("#login-error").textContent = "";
  (on ? $("#join-code") : $("#login-password")).focus();
}
$("#join-open").addEventListener("click", () => showJoin(true));
$("#join-back").addEventListener("click", () => showJoin(false));
$("#join-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    const name = $("#join-name").value.trim();
    await api("/api/family/join", { method: "POST", body: JSON.stringify({
      code: $("#join-code").value.trim(), name, password: $("#join-password").value }) });
    $("#join-password").value = ""; $("#join-code").value = "";
    store.set("syrius:loginName", name);
    $("#login-name").value = name;
    showJoin(false);
    await showApp();
  } catch (err) { $("#login-error").textContent = err.message; }
});

async function renderFamily(account) {
  const box = $("#family-box");
  const owner = !account || account.owner !== false;
  box.classList.toggle("hidden", !owner);
  $("#diag-box").classList.toggle("hidden", !owner);
  const guest = !!(account && account.guest);
  $("#del-title").textContent = owner ? "Effacer mes discussions et ma mémoire" : "Supprimer mon compte";
  $("#del-text").textContent = owner
    ? "Toutes tes discussions et tout ce que Syrius a retenu sur toi seront effacés définitivement."
    : "Ton compte, tes discussions, ta mémoire, tes réglages et tes rappels seront effacés définitivement.";
  $("#del-password").classList.toggle("hidden", guest);
  $("#del-msg").textContent = "";
  if (owner) renderReports();
  $("#s-account").textContent = owner ? "Compte principal (propriétaire de ce Syrius)."
    : account.guest ? `Compte de test — accès jusqu'à ${hourText(account.expires)}, puis tout est effacé.`
    : `Compte de ${account.name} — tes discussions, ta mémoire et tes réglages sont privés.`;
  $("#pw-box")?.classList.toggle("hidden", !!(account && account.guest));
  if (!owner) return;
  $("#family-msg").textContent = "";
  try {
    const f = await api("/api/family");
    $("#family-code").textContent = f.code || "—";
    $("#family-full").classList.toggle("hidden", !f.full);
    $("#family-invite").classList.toggle("hidden", !!f.full);
    $("#family-testbox").classList.toggle("hidden", !!f.full);
    const list = $("#family-list");
    list.textContent = "";
    if (!f.members.length) {
      const li = document.createElement("li");
      li.className = "muted small";
      li.textContent = "Personne n'a encore rejoint ta famille.";
      list.append(li);
    }
    for (const m of f.members) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = m.guest ? `${m.name} · test jusqu'à ${hourText(m.expires)}` : m.name;
      const del = document.createElement("button");
      del.type = "button"; del.className = "ghost subtle";
      del.textContent = "Retirer";
      del.addEventListener("click", async () => {
        if (!confirm(`Retirer le compte de ${m.name} ? Ses discussions ne seront plus accessibles.`)) return;
        try { await api(`/api/family/${encodeURIComponent(m.id)}`, { method: "DELETE" }); await renderFamily(account); }
        catch (err) { $("#family-msg").textContent = "⚠ " + err.message; }
      });
      li.append(name, del);
      list.append(li);
    }
  } catch (err) { $("#family-msg").textContent = "⚠ " + err.message; }
}

async function renderReports() {
  const list = $("#report-list");
  try {
    const items = await api("/api/reports");
    list.textContent = "";
    $("#report-clear").classList.toggle("hidden", !items.length);
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "muted small"; li.textContent = "Aucun signalement.";
      list.append(li);
    }
    for (const r of items) {
      const li = document.createElement("li");
      li.className = "diag";
      const t = document.createElement("strong");
      t.textContent = `${r.who} · ${new Date(r.at * 1000).toLocaleString("fr-FR")}` + (r.reason ? ` — ${r.reason}` : "");
      const d = document.createElement("span");
      d.className = "small muted"; d.textContent = r.text.slice(0, 300);
      li.append(t, d);
      list.append(li);
    }
  } catch (_) { /* hors ligne */ }
}
$("#report-clear").addEventListener("click", async () => {
  if (!confirm("Effacer tous les signalements ?")) return;
  try { await api("/api/reports", { method: "DELETE" }); renderReports(); } catch (_) { /* ignore */ }
});

$("#del-run").addEventListener("click", async () => {
  const owner = !state.settings?.account || state.settings.account.owner !== false;
  if (!confirm(owner ? "Effacer toutes tes discussions et ta mémoire ? C'est définitif."
    : "Supprimer ton compte et toutes tes données ? C'est définitif.")) return;
  try {
    const r = await api("/api/account/delete", { method: "POST",
      body: JSON.stringify({ password: $("#del-password").value }) });
    $("#del-password").value = "";
    if (r.deleted === "account") {
      store.set("syrius:loginName", "");
      $("#settings").close();
      showLogin();
      $("#login-error").textContent = "Ton compte a été supprimé.";
    } else {
      $("#del-msg").textContent = "✅ Discussions et mémoire effacées.";
      await loadConversations();
      newConversationView();
    }
  } catch (err) { $("#del-msg").textContent = "⚠ " + err.message; }
});

$("#diag-run").addEventListener("click", async () => {
  const btn = $("#diag-run"), list = $("#diag-list");
  btn.disabled = true;
  list.textContent = "";
  const wait = document.createElement("li");
  wait.className = "muted small"; wait.textContent = "Test en cours…";
  list.append(wait);
  try {
    const r = await api("/api/diagnostic", { method: "POST" });
    list.textContent = "";
    for (const c of r.checks) {
      const li = document.createElement("li");
      li.className = "diag " + (c.ok ? "ok" : "ko");
      const t = document.createElement("strong");
      t.textContent = (c.ok ? "✅ " : "❌ ") + c.name;
      const d = document.createElement("span");
      d.className = "small muted";
      d.textContent = `${c.detail} (${c.s} s)`;
      li.append(t, d);
      list.append(li);
    }
  } catch (err) { wait.textContent = "⚠ " + err.message; }
  finally { btn.disabled = false; }
});

function hourText(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("fr-FR", { weekday: "long", hour: "2-digit", minute: "2-digit" });
}

async function shareText(text, done) {
  try {
    if (navigator.share) await navigator.share({ title: "Syrius", text });
    else { await navigator.clipboard.writeText(text); $("#family-msg").textContent = done; }
  } catch (_) { /* partage annulé */ }
}

$("#family-test").addEventListener("click", async () => {
  try {
    const r = await api("/api/family/test-link", { method: "POST" });
    const url = `${location.origin}/essai/${encodeURIComponent(r.link)}`;
    await shareText(`Essaie mon assistant Syrius pendant ${r.hours} h (aucun compte à créer) : ${url}`,
      "Lien de test copié (valable 24 h).");
    const s = await api("/api/settings");
    await renderFamily(s.account);
  } catch (err) { $("#family-msg").textContent = "⚠ " + err.message; }
});

$("#family-renew").addEventListener("click", async () => {
  if (!confirm("Créer un nouveau code ? L'ancien ne fonctionnera plus (les comptes déjà créés restent).")) return;
  try {
    $("#family-code").textContent = (await api("/api/family/code", { method: "POST" })).code;
    $("#family-msg").textContent = "Nouveau code créé.";
  } catch (err) { $("#family-msg").textContent = "⚠ " + err.message; }
});
$("#family-share").addEventListener("click", async () => {
  const code = $("#family-code").textContent;
  const url = `${location.origin}/rejoindre/${encodeURIComponent(code)}`;
  await shareText(`Rejoins mon assistant Syrius : ouvre ce lien et crée ton compte ${url} (code : ${code})`,
    "Invitation copiée.");
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
    Icons.set(open, c.pinned ? "pin" : "message", c.title);
    open.addEventListener("click", () => { openConversation(c.id); closeDrawer(); });
    const more = document.createElement("button");
    more.className = "conv-more";
    more.setAttribute("aria-label", "Options");
    more.append(Icons.svg("more"));
    more.addEventListener("click", () => openConvMenu(c));
    li.append(open, more);
    ul.appendChild(li);
  }
}

function openConvMenu(c) {
  state.menuConv = c;
  $("#conv-menu-title").textContent = c.title;
  Icons.set($("#cm-pin"), "pin", c.pinned ? "Désépingler" : "Épingler");
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
  if (role === "assistant") addReportButton(view);
  return view;
}

// Signaler une réponse ou une image de l'IA (règle Google Play sur l'IA générative)
function addReportButton(view) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "msg-report";
  btn.title = "Signaler cette réponse";
  Icons.set(btn, "alert", "Signaler");
  btn.addEventListener("click", async () => {
    if (state.offline) return;
    const reason = prompt("Signaler cette réponse : qu'est-ce qui ne va pas ? (facultatif)");
    if (reason === null) return;
    const imgs = [...view.wrap.querySelectorAll(".gen-image")].map((i) => "[image : " + (i.alt || "") + "]");
    try {
      await api("/api/report", { method: "POST", body: JSON.stringify({
        text: ([view.text || ""].concat(imgs).join("\n") || "(vide)").slice(0, 4000), reason: reason.slice(0, 300) }) });
      Icons.set(btn, "check", "Signalé, merci");
      btn.disabled = true;
    } catch (err) { Icons.set(btn, "alert", "⚠ " + err.message); }
  });
  view.wrap.append(btn);
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
    Icons.set(d, toolIcon(l), stripMark(l));
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

// ------------------------------------------------------------------ photo (vision)
// La photo est réduite ici (1024 px max, JPEG) avant l'envoi : rapide, légère, et jamais enregistrée.
function shrinkImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, 1024 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Image illisible")); };
    img.src = url;
  });
}
function setPhoto(dataUrl) {
  state.photo = dataUrl || null;
  $("#photo-preview").classList.toggle("hidden", !state.photo);
  if (state.photo) $("#photo-thumb").src = state.photo;
}
$("#photo-btn").addEventListener("click", () => $("#photo-input").click());
$("#photo-input").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = "";
  if (!f) return;
  if (!/^image\//.test(f.type)) { alert("Choisis une image."); return; }
  try { setPhoto(await shrinkImage(f)); $("#input").focus(); } catch (err) { alert(err.message); }
});
$("#photo-remove").addEventListener("click", () => setPhoto(null));

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
  Icons.set($("#local-download"), i.installed ? "refresh" : "download", i.installed ? "Changer de modèle" : "Télécharger");
  $("#local-delete").classList.toggle("hidden", !i.installed && !busy);
  Icons.set($("#local-delete"), busy ? "close" : "trash", busy ? "Annuler" : "Supprimer");
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
  const packsBusy = refreshPacks();
  clearTimeout(localTimer);
  if ((busy || packsBusy) && $("#settings").open) localTimer = setTimeout(refreshLocalBox, 1500);
}

// Vision et images hors ligne : un bloc par modèle (téléchargement vérifié par empreinte).
function refreshPacks() {
  const p = L() && L().packs();
  $("#packs").classList.toggle("hidden", !p);
  if (!p) return false;
  let anyBusy = false;
  document.querySelectorAll("#packs .pack").forEach((el) => {
    const i = p[el.dataset.pack] || {};
    const busy = !!(i.downloading || i.verifying);
    anyBusy = anyBusy || busy;
    el.querySelector(".pack-dl").classList.toggle("hidden", busy || !!i.installed);
    const del = el.querySelector(".pack-del");
    del.classList.toggle("hidden", !i.installed && !busy);
    Icons.set(del, busy ? "close" : "trash", busy ? "Annuler" : "Supprimer");
    const prog = el.querySelector(".local-progress");
    prog.classList.toggle("hidden", !i.downloading);
    if (i.downloading) {
      prog.querySelector("progress").value = i.progress || 0;
      prog.querySelector("span").textContent = `${i.progress || 0} %`;
    }
    const noEngine = el.dataset.pack === "sd15" && i.engine === false;
    el.querySelector(".pack-status").textContent = i.error ? "⚠ " + i.error
      : noEngine ? "⚠ Moteur d'images absent de cette version de l'application."
      : i.verifying ? "🔒 Vérification des empreintes des fichiers…"
      : i.downloading ? "Téléchargement en cours (tu peux fermer cet écran, il continue)…"
      : i.installed ? "✅ Installée et prête." : "Pas encore installée.";
  });
  return anyBusy;
}
document.querySelectorAll("#packs .pack").forEach((el) => {
  const id = el.dataset.pack;
  el.querySelector(".pack-dl").addEventListener("click", () => {
    const name = el.querySelector("h5").textContent.trim();
    if (!confirm(`Télécharger ${name} ? Utilise de préférence le Wi-Fi.`)) return;
    const r = window.SyriusAndroid.packDownload(id);
    if (r !== "ok") alert(r);
    setTimeout(refreshLocalBox, 500);
  });
  el.querySelector(".pack-del").addEventListener("click", () => {
    const i = ((L() && L().packs()) || {})[id] || {};
    if (i.downloading) window.SyriusAndroid.packCancel(id);
    else if (confirm("Supprimer ce modèle de ce téléphone ?")) window.SyriusAndroid.packDelete(id);
    setTimeout(refreshLocalBox, 300);
  });
});

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
  setTools(view, [note || "IA hors ligne (sur ton téléphone)"]);
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

// Sans réseau, la photo est analysée par la vision du téléphone (si elle est installée).
function offlineVisionWanted() {
  const l = L();
  return !!(l && l.visionReady() && (l.prefs.force || state.offline || !navigator.onLine));
}

async function sendLocal(text) {
  $("#input").value = "";
  autoGrow();
  addMessage("user", text);
  const view = addMessage("assistant", "");
  scrollDown(true);
  const l = L();
  if (l && l.wantsImage(text) && l.imageReady()) {
    setTools(view, ["Image créée sur ton téléphone (hors ligne)"]);
    setStreaming(true);
    let prompt;
    try { prompt = await l.imagePrompt(text); } finally { setStreaming(false); }
    view.text = "Je dessine ça sur ton téléphone, sans Internet. Patience : 1 à 3 minutes.";
    state.lastReply = view.text;
    renderText(view, "assistant");
    imageCard(view, { prompt, caption: text.slice(0, 80) });
    return;
  }
  await answerLocally(view);
}

async function sendLocalPhoto(text, photo) {
  $("#input").value = "";
  autoGrow();
  const userView = addMessage("user", text);
  const im = document.createElement("img");
  im.className = "msg-photo"; im.src = photo; im.alt = "Photo envoyée";
  userView.bubble.prepend(im);
  setPhoto(null);
  const view = addMessage("assistant", "");
  scrollDown(true);
  setTools(view, ["Vision hors ligne (sur ton téléphone) — 30 s à 1 min"]);
  setStreaming(true);
  state.localRunning = true;
  let pending = false;
  try {
    await L().askPhoto(text, photo, (full) => {
      view.text = full;
      if (pending) return;
      pending = true;
      requestAnimationFrame(() => { pending = false; renderText(view, "assistant"); scrollDown(); });
    });
  } catch (err) {
    showError(view, err.message || "Vision hors ligne indisponible.");
  } finally {
    state.localRunning = false;
    setStreaming(false);
    renderText(view, "assistant");
    state.lastReply = view.text;
    if (view.text && state.settings.voice_reply && !window.SyriusVoice?.active) speak(view.text);
  }
}

// Image : créée en ligne (quelques secondes) ; sans réseau ou si le service est saturé, le téléphone
// prend le relais avec son générateur hors ligne (quelques minutes).
async function onlineImage(prompt) {
  const res = await fetch("/api/image", {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Syrius": "1" },
    body: JSON.stringify({ prompt: String(prompt).slice(0, 600) }),
  });
  if (res.status === 401) { showLogin(); throw new Error("Connexion expirée."); }
  if (!res.ok) {
    let msg = `Erreur ${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch (_) { /* ignore */ }
    throw new Error(msg);
  }
  const url = URL.createObjectURL(await res.blob());
  try {  // converti en JPEG : même format que les images du téléphone (enregistrement dans la galerie)
    const img = await new Promise((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = ko; i.src = url; });
    const c = document.createElement("canvas");
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    c.getContext("2d").drawImage(img, 0, 0);
    return c.toDataURL("image/jpeg", 0.92);
  } catch (_) {
    throw new Error("Image illisible.");
  } finally {
    URL.revokeObjectURL(url);
  }
}

function imageCard(view, params) {
  const card = node("div", "action-card image-card tone-rose");
  card.append(cardHead("sparkle", params.caption || "Image", "Création d'image"));
  const bar = document.createElement("progress");
  bar.max = 100;
  const status = node("p", "small");
  card.append(bar, status);
  placeCard(view, card);
  scrollDown();
  const l = L();
  const phoneOk = !!(l && typeof l.makeImage === "function" && l.imageReady());
  const started = Date.now();
  const online = navigator.onLine && !state.offline && !(l && l.prefs.force);

  const phone = () => {
    bar.value = 0;
    status.textContent = "Création sur ton téléphone, sans Internet (1 à 3 min)…";
    return l.makeImage(params.prompt, (pct) => {
      bar.value = pct;
      const mins = Math.round((Date.now() - started) / 60000);
      status.textContent = `Création sur ton téléphone… ${pct} %` + (mins ? ` (${mins} min)` : "");
    });
  };
  let where = "en ligne";
  const run = async () => {
    if (online) {
      bar.removeAttribute("value");  // barre animée : quelques secondes
      status.textContent = "Création de l'image en ligne (quelques secondes)…";
      try { return await onlineImage(params.prompt); } catch (err) {
        if (!phoneOk) throw err;
        status.textContent = "Service en ligne indisponible → ton téléphone prend le relais…";
      }
    } else if (!phoneOk) {
      throw new Error(Native
        ? "Sans Internet, il faut « Images hors ligne » : Réglages → IA hors ligne."
        : "Pas de connexion Internet.");
    }
    where = "sur ton téléphone";
    return phone();
  };
  run().then((dataUrl) => {
    bar.remove();
    const secs = Math.round((Date.now() - started) / 1000);
    status.textContent = `Image créée ${where} en ${secs < 90 ? Math.max(1, secs) + " s" : Math.round(secs / 60) + " min"}.`;
    const img = document.createElement("img");
    img.className = "gen-image"; img.src = dataUrl; img.alt = params.caption || "Image créée par Syrius";
    const row = document.createElement("div");
    row.className = "action-buttons";
    if (Native && l && typeof l.saveImage === "function" && typeof Native.imageSave === "function") {
      const save = document.createElement("button");
      save.className = "primary"; Icons.set(save, "save", "Enregistrer dans la galerie");
      save.addEventListener("click", () => {
        const r = l.saveImage(dataUrl);
        save.disabled = r === "ok";
        if (r === "ok") Icons.set(save, "check", "Enregistrée (Images › Syrius)");
        else Icons.set(save, "alert", r);
      });
      row.append(save);
    } else {
      const a = document.createElement("a");
      a.className = "primary btn-link"; Icons.set(a, "download", "Télécharger l'image");
      a.href = dataUrl; a.download = "Syrius.jpg";
      row.append(a);
    }
    card.insertBefore(img, status);
    card.append(row);
    scrollDown();
  }).catch((err) => {
    bar.remove();
    setMsg(status, "⚠ " + (err.message || "Création de l'image impossible."));
  });
}

async function sendMessage(text) {
  text = (text || "").trim();
  const photo = state.photo;
  if (photo && !text) text = "Que vois-tu sur cette photo ?";
  if (!text || state.streaming) return;
  if (localWanted() || (photo && offlineVisionWanted())) {
    if (photo) {
      if (!L() || !L().visionReady()) {
        alert("Sans Internet, la photo a besoin de la « Vision hors ligne » : Réglages → IA hors ligne → Télécharger.");
        return;
      }
      return sendLocalPhoto(text, photo);
    }
    return sendLocal(text);
  }
  if (!state.convId) {
    const conv = await api("/api/conversations", { method: "POST" });
    state.convId = conv.id;
    store.set("syrius:lastConv", conv.id);
    $("#messages").replaceChildren();
    loadConversations();
  }
  $("#input").value = "";
  autoGrow();
  const userView = addMessage("user", text);
  if (photo) { // vignette de la photo dans la bulle (affichée seulement, pas enregistrée)
    const im = document.createElement("img");
    im.className = "msg-photo"; im.src = photo; im.alt = "Photo envoyée";
    userView.bubble.prepend(im);
    setPhoto(null);
  }
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
        voice: !!window.SyriusVoice?.active, image: photo || undefined }),
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
        else if (ev.type === "action") { placeCard(view, actionCard(ev)); scrollDown(); }
        else if (ev.type === "device") { handleDevice(view, ev); scrollDown(); }
        else if (ev.type === "map") { addMapCard(view, ev); if (window.SyriusHUD) window.SyriusHUD.show(ev); }
        else if (ev.type === "diagram") { addDiagramCard(view, ev); if (window.SyriusHolo) window.SyriusHolo.show(ev); }
        else if (ev.type === "weather") { addWeatherCard(view, ev); scrollDown(); }
        else if (ev.type === "model") {
          addDiagramCard(view, ev);
          if (window.SyriusModel) window.SyriusModel.show(ev);
          realModel(view, ev);
        }
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
      await answerLocally(view, "IA en ligne indisponible → réponse hors ligne (sur ton téléphone)");
      return;
    }
    if (gotError && !view.text) $("#input").value = text; // on rend le message pour réessayer
    state.lastReply = view.text;
    if (!gotError && view.text && state.settings.voice_reply && !window.SyriusVoice?.active) speak(view.text);
    loadConversations();
  }
}

function showError(view, msg) {
  const p = node("p", "msg-error");
  Icons.set(p, "alert", msg);
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
  const card = node("button", "action-card open-card tone-sky");
  card.type = "button";
  const n = Array.isArray(ev.places) ? ev.places.length : 0;
  card.append(cardHead("map", `${n} lieu${n > 1 ? "x" : ""} sur la carte`, String(ev.query || "Toucher pour ouvrir").slice(0, 80)));
  card.firstChild.append(Icons.svg("right", "go"));
  card.addEventListener("click", () => window.SyriusHUD && window.SyriusHUD.show(ev));
  placeCard(view, card);
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
  head.append(Icons.set(el("div", "wx-place"), "place", String(w.place || "Météo")));
  const main = el("div", "wx-main");
  const big = el("div", "wx-icon");
  big.append(Icons.svg(wxIcon(n.icon)));
  main.append(big, el("div", "wx-temp", deg(n.temp)));
  const info = el("div", "wx-info");
  info.append(el("div", "wx-label", n.label || ""),
    el("div", "wx-meta", `Ressenti ${deg(n.feels)} · Vent ${n.wind ?? "–"} km/h · Humidité ${n.humidity ?? "–"} %`));
  main.append(info);
  const hours = el("div", "wx-hours");
  (w.hours || []).forEach((h) => {
    const c = el("div", "wx-hour");
    const hi = el("span", "wx-hicon");
    hi.append(Icons.svg(wxIcon(h.icon)));
    const rain = el("small", "", " ");
    if (typeof h.rain === "number" && h.rain >= 20) Icons.set(rain, "drop", `${Math.round(h.rain)}%`);
    c.append(el("span", "", h.h), hi, el("b", "", deg(h.temp)), rain);
    hours.append(c);
  });
  const days = el("div", "wx-days");
  (w.days || []).forEach((d) => {
    const r = el("div", "wx-day");
    const di = el("span", "wx-dicon");
    di.append(Icons.svg(wxIcon(d.icon)));
    r.append(el("span", "wx-dname", d.day), di,
      el("span", "wx-drain", typeof d.rain === "number" && d.rain >= 20 ? `${Math.round(d.rain)} %` : ""),
      el("span", "wx-dtemp", `${deg(d.min)} / ${deg(d.max)}`));
    days.append(r);
  });
  card.append(head, main, hours, days, el("div", "wx-src", "Open-Meteo"));
  placeCard(view, card);
}

// Symboles météo du serveur → icônes dessinées.
const WX = [["⛈", "storm"], ["🌩", "storm"], ["🌨", "snow"], ["❄", "snow"], ["🌧", "rain"], ["🌦", "rain"],
  ["🌫", "fog"], ["🌤", "partly"], ["⛅", "partly"], ["🌥", "cloud"], ["☁", "cloud"], ["🌙", "moon"], ["☀", "sun"]];
function wxIcon(sym) {
  const s = String(sym || "");
  for (const [k, name] of WX) if (s.includes(k)) return name;
  return "thermo";
}

function addDiagramCard(view, ev) {
  const isModel = ev.type === "model";
  const card = node("button", "action-card open-card " + (isModel ? "tone-sky" : "tone-mint"));
  card.type = "button";
  card.append(cardHead(isModel ? "cube" : "nodes", String(ev.title || (isModel ? "Maquette 3D" : "Schéma")).slice(0, 70),
    isModel ? "Maquette 3D · toucher pour ouvrir" : "Schéma · toucher pour ouvrir"));
  card.firstChild.append(Icons.svg("right", "go"));
  card.addEventListener("click", () => {
    if (isModel) {
      if (ev._glb && window.SyriusModel) window.SyriusModel.showGlb(ev._glb.slice(0), ev._info).catch(() => window.SyriusModel.show(ev));
      else if (window.SyriusModel) window.SyriusModel.show(ev);
    } else if (window.SyriusHolo) window.SyriusHolo.show(ev);
  });
  placeCard(view, card);
}

// ------------------------------------------------------------------ vraie maquette 3D (fichier GLB texturé)
// 1) bibliothèque Poly Pizza (modèles d'artistes, instantané) ; 2) sinon création sur mesure (TRELLIS.2, 1 à 2 min).
// La version simplifiée reste affichée en attendant, puis est remplacée automatiquement.
async function fetchGlb(url, body) {
  const res = await fetch(url, {
    method: body ? "POST" : "GET", credentials: "same-origin",
    headers: { "X-Syrius": "1", ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) { showLogin(); throw new Error("Connexion expirée."); }
  if (!res.ok) {
    let msg = `Erreur ${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch (_) { /* ignore */ }
    throw new Error(msg);
  }
  return res;
}

function realModel(view, ev) {
  if (!ev || !(ev.search_en || ev.prompt_en) || !window.SyriusModel || !window.SyriusModel.showGlb) return;
  const card = node("div", "action-card image-card tone-sky");
  const head = cardHead("cube", "Maquette réaliste", "Recherche d'un vrai modèle 3D…");
  const sub = head.querySelector(".card-sub");
  const bar = document.createElement("progress");
  const status = node("p", "small");
  card.append(head, bar, status);
  placeCard(view, card);
  const started = Date.now();
  const display = (buf, credit) => {
    ev._glb = buf;
    ev._info = { title: ev.title, description: ev.description, facts: [...(ev.facts || []), ...(credit ? [credit] : [])] };
    const panelOpen = !document.getElementById("m3d").classList.contains("hidden");
    const open = () => window.SyriusModel.showGlb(buf.slice(0), ev._info);
    bar.remove();
    sub.textContent = credit || "Maquette texturée créée sur mesure";
    setMsg(status, `✅ Prête en ${Math.max(1, Math.round((Date.now() - started) / 1000))} s.`);
    const row = node("div", "action-buttons");
    const btn = node("button", "primary");
    Icons.set(btn, "cube", "Voir la maquette réaliste");
    btn.addEventListener("click", () => open().catch((e) => setMsg(status, "⚠ " + e.message)));
    row.append(btn);
    card.append(row);
    if (panelOpen) open().catch((e) => setMsg(status, "⚠ " + e.message));
    scrollDown();
  };
  (async () => {
    let libErr = "";
    if (ev.search_en) {
      try {
        const r = await (await fetchGlb("/api/model3d/search", { query: ev.search_en })).json();
        const best = (r.results || [])[0];
        if (best) {
          sub.textContent = `Modèle trouvé : ${best.title}`;
          const buf = await (await fetchGlb("/api/model3d/poly?path=" + encodeURIComponent(best.path))).arrayBuffer();
          const credit = `Modèle « ${best.title} »${best.creator ? " par " + best.creator : ""}${best.licence ? " · " + best.licence : ""} (Poly Pizza)`;
          display(buf, credit);
          return;
        }
        libErr = "aucun modèle correspondant dans la bibliothèque";
      } catch (e) { libErr = e.message; }
    }
    if (!ev.prompt_en) throw new Error(libErr || "pas de description pour la création");
    sub.textContent = "Création sur mesure en cours (1 à 2 min)…";
    status.textContent = "L'IA dessine l'objet puis le transforme en maquette 3D texturée.";
    const buf = await (await fetchGlb("/api/model3d/generate", { prompt: ev.prompt_en, key: (ev.search_en || ev.prompt_en || "").slice(0, 80) })).arrayBuffer();
    display(buf, "");
  })().catch((e) => {
    bar.remove();
    sub.textContent = "Version simplifiée affichée";
    setMsg(status, "⚠ " + (e.message || "Maquette réaliste indisponible."));
  });
}

// ------------------------------------------------------------------ actions sur le téléphone
// Chaque action : [icône, titre, détail, teinte]. Le texte passe toujours par textContent.
const pad2 = (n) => String(n).padStart(2, "0");
const MUSIC = { pause: ["pause", "Pause"], resume: ["play", "Reprise"], next: ["next", "Titre suivant"], previous: ["prev", "Titre précédent"] };
const DEVICE = {
  phone_alarm: (p) => ["alarm", `Réveil à ${pad2(p.hour)}h${pad2(p.minute)}`, p.label && p.label !== "Syrius" ? p.label : "Réveil du téléphone", "amber"],
  phone_timer: (p) => ["timer", `Minuteur de ${Math.round(p.seconds / 60) || 1} min`, p.label || "Minuteur", "amber"],
  phone_call: (p) => ["phone", `Appeler ${p.contact}`, "Appel", "mint"],
  phone_sms: (p) => ["message", `SMS à ${p.contact}`, `« ${p.message} »`, "sky"],
  phone_open_app: (p) => ["apps", `Ouvrir ${p.app}`, "Application", ""],
  phone_map: (p) => ["place", p.navigate ? "Itinéraire" : "Carte", p.query, "sky"],
  phone_open_url: (p) => ["link", "Ouvrir le lien", p.url, ""],
  phone_flashlight: (p) => ["flashlight", `Lampe ${p.on ? "allumée" : "éteinte"}`, "Lampe torche", "amber"],
  phone_volume: (p) => ["volume", `Volume à ${p.level} %`, "Son des médias", ""],
  phone_settings: (p) => ["settings", "Réglages du téléphone", String(p.page || "").replace("_", " "), ""],
  phone_reminder: (p) => ["bell", p.text, `Rappel ${p.label}` +
    (p.repeat === "daily" ? " · tous les jours" : p.repeat === "weekly" ? " · chaque semaine" : ""), "rose"],
  phone_reminder_cancel: () => ["trash", "Rappel annulé", "", ""],
  phone_music: (p) => p.action === "play"
    ? ["music", p.query, p.app && p.app !== "auto" ? p.app.replace("_", " ") : "Musique", "rose"]
    : [...(MUSIC[p.action] || ["music", "Musique"]), "Musique", "rose"],
  phone_image: (p) => ["sparkle", p.caption || "Image", "Image", "rose"],
  phone_calendar: (p) => ["calendar", p.title, `${p.label}${p.location ? " · " + p.location : ""}`, "sky"],
};
function deviceInfo(ev) {
  const f = DEVICE[ev.action];
  return f ? f(ev.params || {}) : ["bolt", ev.action, "", ""];
}
const DEVICE_TEXT = new Proxy({}, { get: (_, k) => (DEVICE[k] ? (p) => DEVICE[k](p)[1] : undefined) });

// Actions qui demandent une version récente de l'application Android.
const NEEDS_FEATURE = { phone_reminder: "reminders", phone_reminder_cancel: "reminders", phone_calendar: "calendar",
  phone_music: "music", phone_image: "imagegen" };
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
  if (ev.action === "phone_image") { imageCard(view, ev.params || {}); return; }
  if (ev.action === "phone_call") { callCard(view, ev); return; }
  const [icon, titleText, sub, tone] = deviceInfo(ev);
  const card = node("div", "action-card" + (tone ? " tone-" + tone : ""));
  card.append(cardHead(icon, titleText, sub));
  const title = { textContent: titleText };
  const status = node("p", "small");
  const finish = (res) => setMsg(status, res === "ok" ? "✅ Envoyé au téléphone." : "⚠ " + res);
  if (ev.confirm) {
    if (ev.after_untrusted) {
      const warn = document.createElement("p");
      warn.className = "small msg-error";
      warn.textContent = "Syrius vient de lire un email ou une page web : vérifie bien que c'est toi qui as demandé cette action.";
      card.append(warn);
    }
    const row = node("div", "action-buttons");
    const ok = node("button", "primary");
    Icons.set(ok, "check", "Confirmer");
    const no = node("button", "ghost", "Annuler");
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
  placeCard(view, card);
}

// Appel : carte dédiée (avatar, nom, boutons ronds). L'appel ne part qu'après « Appeler » ou un « oui » à la voix.
function callCard(view, ev) {
  const p = ev.params || {};
  const who = String(p.contact || "Contact");
  const card = node("div", "action-card call-card");
  const avatar = node("div", "call-avatar");
  const initials = who.replace(/[^\p{L}\s]/gu, " ").trim().split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  if (initials) avatar.textContent = initials; else avatar.append(Icons.svg("phone"));
  const sub = node("div", "call-sub");
  Icons.set(sub, "lock", "Appel vocal · confirmation requise");
  const status = node("div", "call-status");
  const actions = node("div", "call-actions");
  const btn = (cls, icon, label) => {
    const b = node("button", "call-btn " + cls);
    b.type = "button";
    const r = node("span", "round");
    r.append(Icons.svg(icon));
    b.append(r, node("span", "", label));
    return b;
  };
  const decline = btn("decline", "hangup", "Annuler");
  const accept = btn("accept", "phone", "Appeler");
  actions.append(decline, accept);
  card.append(avatar, node("div", "call-name", who), sub, actions, status);
  let decided = false;
  const go = () => {
    if (decided) return; decided = true; actions.remove();
    const res = runDevice(ev);
    if (res === "ok") {
      card.classList.add("ringing");
      Icons.set(sub, "phone", "Appel en cours…");
      setTimeout(() => card.classList.remove("ringing"), 8000);
    } else setMsg(status, "⚠ " + res);
  };
  const stop = () => { if (decided) return; decided = true; actions.remove(); setMsg(status, "Appel annulé."); };
  accept.addEventListener("click", go);
  decline.addEventListener("click", stop);
  if (window.SyriusVoice?.active) window.SyriusVoice.confirm(`Appeler ${who}`, go, stop);
  placeCard(view, card);
}

function actionCard(ev) {
  const node = $("#tpl-action").content.firstElementChild.cloneNode(true);
  node.querySelector(".a-to").textContent = ev.to;
  node.querySelector(".a-subject").textContent = ev.subject;
  node.querySelector(".a-body").textContent = ev.body;
  const status = node.querySelector(".a-status");
  const buttons = node.querySelectorAll(".action-buttons button");
  const finish = (msg) => { buttons.forEach((b) => b.remove()); setMsg(status, msg); };
  node.querySelector(".a-send").addEventListener("click", async () => {
    buttons.forEach((b) => { b.disabled = true; });
    try { await api(`/api/actions/${ev.id}/confirm`, { method: "POST" }); finish("✅ Email envoyé."); }
    catch (err) { setMsg(status, "⚠ " + err.message); buttons.forEach((b) => { b.disabled = false; }); }
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
  const tag = document.querySelector(".hero-tag span:last-child");
  if (tag) tag.textContent = "Syrius · " + (off ? "hors ligne" : "en ligne");
  document.querySelector(".hero-tag .live-dot")?.classList.toggle("off", off);
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
  $("#wake-overlay").classList.add("hidden");  // plus nécessaire : la musique s'ouvre via une notification
  void canOpen;
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
    if (w.status && w.status !== "listening") $("#wake-status").textContent = "⚠ " + (w.status === "stopped" ? "L'écoute est arrêtée (le téléphone l'a peut-être coupée : touche « Ne pas couper Syrius »)." : w.status);
    const learned = (w.learned || []).join(" · ");
    $("#wake-learn-msg").textContent = w.learning
      ? `🎙 Dis « Hey Syrius » … (${w.learnCount || 0}/3), une phrase à la fois, puis attends 2 secondes.`
      : learned ? `✅ Appris : ${learned}` : "";
    Icons.set($("#wake-learn"), w.learning ? "close" : "learn", w.learning ? "Arrêter l'apprentissage" : "Apprendre ma façon de dire « Hey Syrius »");
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
  await renderFamily(s.account);
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
    del.append(Icons.svg("trash"));
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
  // Liens reçus : invitation famille (?rejoindre=CODE) ou essai de 24 h (?test=...)
  const params = new URLSearchParams(location.search);
  const m = location.pathname.match(/^\/(rejoindre|essai)\/([A-Za-z0-9_-]{4,80})\/?$/);
  const joinCode = m && m[1] === "rejoindre" ? m[2] : params.get("rejoindre");
  const testLink = m && m[1] === "essai" ? m[2] : params.get("test");
  if (joinCode || testLink || location.pathname !== "/") history.replaceState(null, "", "/");
  if (testLink) {
    try {
      await api("/api/family/test", { method: "POST", body: JSON.stringify({ link: testLink.slice(0, 80) }) });
    } catch (err) {
      showLogin();
      $("#login-error").textContent = err.message;
      return;
    }
  }
  try {
    const s = await (await fetch("/api/session", { credentials: "same-origin" })).json();
    if (joinCode && !s.authenticated) {
      showLogin();
      showJoin(true);
      $("#join-code").value = joinCode.slice(0, 20);
      $("#join-name").focus();
      return;
    }
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
      $("#conv-title").textContent = "Syrius hors ligne";
      return;
    }
    showLogin();
    $("#login-error").textContent = "Serveur injoignable.";
  }
})();
