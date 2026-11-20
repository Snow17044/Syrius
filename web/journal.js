// Réveil Jarvis et journal intime du soir. Utilise les outils de app.js ($, api, node, sendMessage…).
"use strict";

(function () {
  const JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
  const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
    "novembre", "décembre"];
  const JOURNAL_PROMPT = "On fait mon journal du soir ?";

  function dayLabel(day, today) {
    const [y, m, d] = day.split("-").map(Number);
    const date = new Date(y, m - 1, d);
    const label = `${JOURS[date.getDay()]} ${d} ${MOIS[m - 1]}` + (y !== new Date().getFullYear() ? ` ${y}` : "");
    return day === today ? "Aujourd'hui · " + label : label.charAt(0).toUpperCase() + label.slice(1);
  }

  async function renameCurrent(title) {
    if (!state.convId) return;
    try {
      await api(`/api/conversations/${state.convId}`, { method: "PATCH", body: JSON.stringify({ title }) });
      $("#conv-title").textContent = title;
      loadConversations();
    } catch (_) { /* le titre automatique reste */ }
  }

  function todayTitle(prefix) {
    const n = new Date();
    return `${prefix} du ${n.getDate()} ${MOIS[n.getMonth()]}`;
  }

  // ---------------------------------------------------------------- réveil Jarvis
  async function wakeUp() {
    closeDrawer();
    await window.syriusBriefing();
    renameCurrent(todayTitle("Réveil"));
  }

  // ---------------------------------------------------------------- journal du soir
  async function startJournal() {
    if ($("#app").classList.contains("hidden")) { pendingJournal = true; return; }  // après connexion
    if ($("#journal").open) $("#journal").close();
    closeDrawer();
    newConversationView();
    await sendMessage(JOURNAL_PROMPT);
    renameCurrent(todayTitle("Journal"));
  }
  let pendingJournal = false;
  window.syriusJournal = startJournal;  // appelé par la notification du soir (application Android)

  async function renderJournal() {
    const list = $("#journal-list");
    list.replaceChildren(node("li", "muted small", "Chargement…"));
    let data;
    try { data = await api("/api/journal"); } catch (err) {
      list.replaceChildren(node("li", "muted small", "⚠ " + err.message));
      return;
    }
    list.replaceChildren();
    if (!data.entries.length) {
      list.append(node("li", "muted small", "Aucune page pour l'instant. Ce soir, touche « Raconter ma journée »."));
      return;
    }
    for (const e of data.entries) {
      const li = node("li", "journal-entry");
      const head = node("div", "journal-head");
      head.append(node("strong", "", dayLabel(e.day, data.today)));
      if (e.mood) head.append(node("span", "journal-mood", e.mood));
      const del = node("button", "icon-btn journal-del");
      del.type = "button";
      del.setAttribute("aria-label", "Effacer cette page");
      del.append(Icons.svg("trash"));
      del.addEventListener("click", async () => {
        if (!confirm("Effacer définitivement cette page du journal ?")) return;
        try { await api(`/api/journal/${e.day}`, { method: "DELETE" }); li.remove(); } catch (err) { alert(err.message); }
      });
      head.append(del);
      li.append(head, node("p", "journal-text", e.text));
      list.append(li);
    }
  }

  // Notification du soir (application Android récente seulement).
  function refreshEvening() {
    const ok = !!(Native && typeof Native.getJournal === "function" && appFeatures().includes("journal"));
    $("#journal-evening").classList.toggle("hidden", !ok);
    if (!ok) return;
    let j = { on: false, hour: 21, minute: 30 };
    try { j = JSON.parse(Native.getJournal()); } catch (_) { /* défaut */ }
    $("#journal-on").checked = !!j.on;
    $("#journal-time").value = `${String(j.hour ?? 21).padStart(2, "0")}:${String(j.minute ?? 30).padStart(2, "0")}`;
  }
  function saveEvening() {
    const [h, m] = ($("#journal-time").value || "21:30").split(":").map(Number);
    const r = Native.setJournal($("#journal-on").checked, h || 0, m || 0);
    setMsg($("#journal-msg"), r === "ok"
      ? ($("#journal-on").checked ? `✅ Chaque soir à ${$("#journal-time").value}.` : "Notification du soir désactivée.")
      : "⚠ " + r);
  }

  $("#open-journal").addEventListener("click", () => {
    closeDrawer();
    $("#journal-msg").textContent = "";
    refreshEvening();
    renderJournal();
    $("#journal").showModal();
  });
  $("#journal-start").addEventListener("click", startJournal);
  $("#journal-on").addEventListener("change", saveEvening);
  $("#journal-time").addEventListener("change", saveEvening);
  $("#open-wakeup").addEventListener("click", wakeUp);
  document.querySelectorAll(".chip[data-action]").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.action === "wakeup") wakeUp();
    else if (b.dataset.action === "journal") startJournal();
    else if (b.dataset.action === "debate" && window.SyriusDebate) window.SyriusDebate.open();
  }));

  // Ouverture depuis la notification avant la connexion : on attend que l'application soit affichée.
  const appScreen = $("#app");
  new MutationObserver(() => {
    if (pendingJournal && !appScreen.classList.contains("hidden")) { pendingJournal = false; setTimeout(startJournal, 800); }
  }).observe(appScreen, { attributes: true, attributeFilter: ["class"] });
})();
