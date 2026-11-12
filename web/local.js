// IA hors ligne de Syrius : petit modèle open source qui tourne SUR le téléphone (application Android).
// Utilisée quand il n'y a pas de réseau, quand toutes les IA en ligne sont épuisées, ou sur demande.
"use strict";

(function () {
  const native = () => window.SyriusAndroid;
  const pending = new Map();
  const SYSTEM = "Tu es Syrius, l'assistant personnel de l'utilisateur, dans l'esprit de J.A.R.V.I.S. : " +
    "loyal, efficace, avec une pointe d'humour. Tu réponds toujours en français, de façon courte et claire. " +
    "Tu fonctionnes en mode hors ligne sur le téléphone : tu n'as accès ni à Internet, ni aux emails, ni aux " +
    "cartes, ni aux actions du téléphone. Si on te demande l'une de ces choses, dis-le simplement. " +
    "Si tu ne sais pas, dis-le : n'invente jamais.";

  function available() {
    const n = native();
    return !!(n && typeof n.localInfo === "function");
  }

  function info() {
    if (!available()) return null;
    try { return JSON.parse(native().localInfo() || "{}"); } catch (_) { return null; }
  }

  function ready() {
    const i = info();
    return !!(i && i.installed && !i.verifying);
  }

  const prefs = {
    get fallback() { try { return localStorage.getItem("syrius:local:fallback") !== "0"; } catch (_) { return true; } },
    set fallback(v) { try { localStorage.setItem("syrius:local:fallback", v ? "1" : "0"); } catch (_) { /* */ } },
    get force() { try { return localStorage.getItem("syrius:local:force") === "1"; } catch (_) { return false; } },
    set force(v) { try { localStorage.setItem("syrius:local:force", v ? "1" : "0"); } catch (_) { /* */ } },
  };

  /** Envoie la conversation au modèle local ; onText(texteComplet) à chaque morceau. */
  function chat(messages, onText) {
    return new Promise((resolve, reject) => {
      const id = "r" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
      const msgs = messages.filter((m) => m && m.text).slice(-12)
        .map((m) => ({ role: m.role === "assistant" ? "assistant" : "user", text: String(m.text).slice(0, 2000) }));
      pending.set(id, { text: "", onText, resolve, reject });
      const r = native().localChat(id, JSON.stringify({ system: SYSTEM, messages: msgs }));
      if (r !== "ok") { pending.delete(id); reject(new Error(r || "IA hors ligne indisponible")); }
      chat.current = id;
    });
  }

  function stop() {
    if (chat.current && available()) native().localStop(chat.current);
    const p = pending.get(chat.current);
    if (p) { pending.delete(chat.current); p.resolve(p.text); }
  }

  // Appelé par l'application Android (texte toujours échappé côté Java).
  function _chunk(id, text, done, error) {
    const p = pending.get(id);
    if (!p) return;
    if (error) { pending.delete(id); p.reject(new Error(error)); return; }
    p.text += String(text || "");
    p.onText(p.text);
    if (done) { pending.delete(id); p.resolve(p.text); }
  }

  window.SyriusLocal = { available, info, ready, prefs, chat, stop, _chunk };
})();
