/* Syrius — bulle de discussion pour le site d'un ami.
 *
 * À coller juste avant </body> :
 *   <script src="https://TON-SYRIUS/widget.js" data-key="sk_syr_…" defer></script>
 * Options (facultatives) : data-color="#7c8cff"  data-position="left"  data-theme="light"
 *                          data-welcome="Bonjour ! Une question sur nos horaires ?"
 * Tout est isolé (Shadow DOM) : le widget ne touche pas au style du site, et le site ne touche pas au widget.
 */
(function () {
  "use strict";
  const me = document.currentScript;
  if (!me || window.__syriusWidget) return;
  window.__syriusWidget = true;
  const KEY = me.dataset.key || "";
  const BASE = new URL(me.src).origin;
  const COLOR = /^#[0-9a-f]{3,8}$/i.test(me.dataset.color || "") ? me.dataset.color : "#a9b5ff";
  const LEFT = me.dataset.position === "left";
  const LIGHT = me.dataset.theme === "light";
  const STORE = "syrius-widget:" + KEY.slice(-8);
  let name = "Nova";
  let history = [];
  try { history = JSON.parse(sessionStorage.getItem(STORE) || "[]"); } catch (_) { history = []; }
  if (!Array.isArray(history)) history = [];
  const save = () => { try { sessionStorage.setItem(STORE, JSON.stringify(history.slice(-20))); } catch (_) { /* privé */ } };

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;z-index:2147483000;bottom:0;" + (LEFT ? "left:0" : "right:0");
  const root = host.attachShadow({ mode: "open" });
  const bg = LIGHT ? "#ffffff" : "#11131c", surf = LIGHT ? "#f2f3f7" : "#1c202d", text = LIGHT ? "#1a1c24" : "#eceef6";
  const muted = LIGHT ? "#6b7080" : "#959ab0", line = LIGHT ? "rgba(0,0,0,.09)" : "rgba(255,255,255,.08)";
  const style = document.createElement("style");
  style.textContent = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
    .fab { position: fixed; bottom: 20px; ${LEFT ? "left" : "right"}: 20px; width: 60px; height: 60px; border-radius: 50%;
      border: 0; cursor: pointer; background: radial-gradient(circle at 34% 30%, #fff 0 6%, ${COLOR} 55%, #6a5acd 100%);
      box-shadow: 0 10px 30px rgba(0,0,0,.3), 0 0 0 4px rgba(255,255,255,.06); transition: transform .2s; }
    .fab:hover { transform: scale(1.06); } .fab:focus-visible { outline: 3px solid ${COLOR}; outline-offset: 3px; }
    .panel { position: fixed; bottom: 92px; ${LEFT ? "left" : "right"}: 20px; width: 370px; max-width: calc(100vw - 32px);
      height: 560px; max-height: calc(100vh - 120px); display: flex; flex-direction: column; background: ${bg}; color: ${text};
      border: 1px solid ${line}; border-radius: 22px; box-shadow: 0 24px 60px rgba(0,0,0,.35); overflow: hidden;
      transform-origin: bottom ${LEFT ? "left" : "right"}; transition: transform .2s, opacity .2s; }
    .panel[hidden] { display: flex; opacity: 0; transform: scale(.9); pointer-events: none; visibility: hidden; }
    @media (max-width: 480px) { .panel { left: 8px; right: 8px; width: auto; max-width: none; bottom: 88px; height: calc(100vh - 110px); } }
    header { display: flex; align-items: center; gap: 10px; padding: 14px 16px; border-bottom: 1px solid ${line}; }
    .orb { width: 30px; height: 30px; border-radius: 50%; flex: none;
      background: radial-gradient(circle at 34% 30%, #fff 0 6%, ${COLOR} 55%, #6a5acd 100%); }
    header b { font-size: 15px; display: block; } header small { color: ${muted}; font-size: 12px; }
    .x { margin-left: auto; background: none; border: 0; color: ${muted}; font-size: 22px; cursor: pointer; width: 36px; height: 36px; border-radius: 10px; }
    .x:hover { background: ${surf}; }
    .msgs { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
    .m { max-width: 85%; padding: 10px 13px; border-radius: 16px; font-size: 14.5px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
    .m.assistant { background: ${surf}; align-self: flex-start; border-bottom-left-radius: 6px; }
    .m.user { background: ${COLOR}; color: #12142b; align-self: flex-end; border-bottom-right-radius: 6px; }
    .m.err { background: transparent; color: #ff8fa3; font-size: 13px; padding: 2px 4px; }
    .dots::after { content: "…"; animation: d 1s steps(3) infinite; } @keyframes d { 0% { content: "."; } 50% { content: ".."; } }
    form { display: flex; gap: 8px; padding: 12px; border-top: 1px solid ${line}; }
    textarea { flex: 1; resize: none; border: 1px solid ${line}; background: ${surf}; color: ${text}; border-radius: 14px;
      padding: 10px 12px; font-size: 15px; max-height: 120px; outline: none; }
    textarea:focus { border-color: ${COLOR}; }
    .send { width: 44px; height: 44px; border-radius: 50%; border: 0; cursor: pointer; background: ${COLOR}; color: #12142b; font-size: 18px; flex: none; }
    .send:disabled { opacity: .5; cursor: default; }
    .by { text-align: center; font-size: 11px; color: ${muted}; padding: 0 0 8px; }
  `;
  const fab = document.createElement("button");
  fab.className = "fab"; fab.type = "button"; fab.setAttribute("aria-label", "Ouvrir la discussion");
  const panel = document.createElement("section");
  panel.className = "panel"; panel.hidden = true; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Discussion");
  panel.innerHTML = `<header><span class="orb"></span><div><b class="nm">Nova</b><small>Assistant IA · en ligne</small></div>
    <button type="button" class="x" aria-label="Fermer">×</button></header>
    <div class="msgs" aria-live="polite"></div>
    <form><textarea rows="1" maxlength="2000" placeholder="Écris ton message…" aria-label="Message"></textarea>
    <button class="send" type="submit" aria-label="Envoyer">↑</button></form><div class="by">Propulsé par Syrius</div>`;
  root.append(style, fab, panel);
  const msgs = panel.querySelector(".msgs"), input = panel.querySelector("textarea"), send = panel.querySelector(".send");

  function bubble(role, content) {
    const d = document.createElement("div");
    d.className = "m " + role;
    d.textContent = content; // jamais de HTML venant de l'IA
    msgs.append(d);
    msgs.scrollTop = msgs.scrollHeight;
    return d;
  }
  function render() {
    msgs.textContent = "";
    bubble("assistant", me.dataset.welcome || `Bonjour, je suis ${name}. Comment puis-je t'aider ?`);
    for (const m of history) bubble(m.role, m.content);
  }
  function headers() { return { "Content-Type": "application/json", Authorization: "Bearer " + KEY }; }

  fetch(BASE + "/api/v1/info", { headers: headers() }).then((r) => r.json()).then((d) => {
    if (d && d.name) { name = d.name; panel.querySelector(".nm").textContent = name; render(); }
  }).catch(() => {});

  fab.addEventListener("click", () => { panel.hidden = !panel.hidden; if (!panel.hidden) input.focus(); });
  panel.querySelector(".x").addEventListener("click", () => { panel.hidden = true; fab.focus(); });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 120) + "px"; });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); panel.querySelector("form").requestSubmit(); } });
  panel.querySelector("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || send.disabled) return;
    input.value = ""; input.style.height = "auto";
    history.push({ role: "user", content: text }); save();
    bubble("user", text);
    const wait = bubble("assistant", ""); wait.classList.add("dots");
    send.disabled = true;
    try {
      const r = await fetch(BASE + "/api/v1/chat", { method: "POST", headers: headers(), body: JSON.stringify({ messages: history.slice(-20) }) });
      const d = await r.json().catch(() => ({}));
      wait.remove();
      if (!r.ok) { history.pop(); save(); bubble("err", d.error || "Erreur, réessaie."); input.value = text; return; }
      history.push({ role: "assistant", content: d.reply }); save();
      bubble("assistant", d.reply);
    } catch (_) {
      wait.remove(); history.pop(); save(); input.value = text;
      bubble("err", "Pas de connexion. Réessaie.");
    } finally { send.disabled = false; input.focus(); }
  });
  render();
  (document.body || document.documentElement).append(host);
})();
