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

  const SYSTEM_OVERRIDE = { value: "" };

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
      const sys = SYSTEM_OVERRIDE.value || SYSTEM + (window.SyriusVoice && window.SyriusVoice.active
        ? " Ta réponse sera lue à voix haute : 1 à 3 phrases simples, sans liste ni Markdown." : "");
      const r = native().localChat(id, JSON.stringify({ system: sys, messages: msgs }));
      if (r !== "ok") { pending.delete(id); reject(new Error(r || "IA hors ligne indisponible")); }
      chat.current = id;
      chat.vision = false;
    });
  }

  function stop() {
    if (chat.current && available()) {
      if (chat.vision && typeof native().visionStop === "function") native().visionStop();
      else native().localStop(chat.current);
    }
    const p = pending.get(chat.current);
    if (p) { pending.delete(chat.current); p.resolve(p.text); }
  }

  // ---------------------------------------------------------- vision et images hors ligne
  function packs() {
    const n = native();
    if (!n || typeof n.packInfo !== "function") return null;
    try { return JSON.parse(n.packInfo() || "{}"); } catch (_) { return null; }
  }
  function visionReady() { const p = packs(); return !!(p && p.vision && p.vision.installed); }
  function imageReady() { const p = packs(); return !!(p && p.sd15 && p.sd15.installed && p.sd15.engine); }

  const VISION_SYSTEM = "Tu es Syrius. Tu regardes la photo de l'utilisateur et tu réponds à sa question " +
    "en français, en 1 à 4 phrases claires. Décris seulement ce que tu vois vraiment ; si tu n'es pas sûr, dis-le.";

  /** Question sur une photo (data URL JPEG), sans Internet ; onText(texteComplet) à chaque morceau. */
  function askPhoto(question, image, onText) {
    return new Promise((resolve, reject) => {
      const id = "v" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
      pending.set(id, { text: "", onText, resolve, reject });
      const r = native().visionAsk(id, JSON.stringify({ system: VISION_SYSTEM, question: String(question).slice(0, 1500), image }));
      if (r !== "ok") { pending.delete(id); reject(new Error(r || "Vision hors ligne indisponible")); return; }
      chat.current = id;
      chat.vision = true;
    });
  }

  // Demande d'image écrite en français : « dessine… », « crée une image de… »
  const IMAGE_REQUEST = /\bdessine|\b(?:cr[ée]e|g[ée]n[èe]re|fais|fabrique|imagine|invente|peins)\b[^.?!]{0,30}?\b(?:image|dessin|illustration|logo|affiche|fond d'[ée]cran|portrait|tableau|peinture)s?\b/i;
  function wantsImage(text) { return IMAGE_REQUEST.test(String(text || "")); }

  /** Transforme la demande en description anglaise (le générateur comprend surtout l'anglais). */
  async function imagePrompt(text) {
    const subject = String(text).replace(/^.*?\b(?:dessine(?:-moi|-nous)?|image|dessin|illustration|logo|affiche|portrait|tableau|peinture|fond d'[ée]cran)s?\b\s*(?:de|d'|du|des|d’un|d'une|d'un|un|une|avec)?\s*/i, "").trim() || String(text);
    if (!ready()) return subject;
    try {
      let out = "";
      const sys = "You translate image requests into a short English prompt for an image generator. " +
        "Reply with the English prompt only (10 to 40 words: subject, style, colors, lighting), nothing else.";
      const saved = SYSTEM_OVERRIDE.value;
      SYSTEM_OVERRIDE.value = sys;
      try { out = await chat([{ role: "user", text: subject }], () => {}); } finally { SYSTEM_OVERRIDE.value = saved; }
      out = out.replace(/<think>[\s\S]*?<\/think>/g, "").replace(/^["'\s]+|["'\s]+$/g, "").split("\n")[0];
      return out.length >= 3 ? out.slice(0, 380) : subject;
    } catch (_) { return subject; }
  }

  const images = new Map();
  /** Crée une image sur le téléphone ; onProgress(%) ; résout avec une data URL JPEG. */
  function makeImage(prompt, onProgress) {
    return new Promise((resolve, reject) => {
      const id = "i" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
      images.set(id, { onProgress, resolve, reject });
      const r = native().imageGenerate(id, String(prompt).slice(0, 400), 4);
      if (r !== "ok") { images.delete(id); reject(new Error(r || "Création d'image impossible")); }
    });
  }
  function saveImage(dataUrl) {
    try { return native().imageSave(dataUrl) || "ok"; } catch (_) { return "Enregistrement impossible"; }
  }
  function _image(id, percent, dataUrl, error) {
    const p = images.get(id);
    if (!p) return;
    if (error || dataUrl) {
      images.delete(id);
      try { native().imageDone(); } catch (_) { /* */ }
      if (error) p.reject(new Error(error)); else p.resolve(dataUrl);
      return;
    }
    p.onProgress(Number(percent) || 0);
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

  window.SyriusLocal = { available, info, ready, prefs, chat, stop, _chunk, packs, visionReady, imageReady,
    askPhoto, wantsImage, imagePrompt, makeImage, saveImage, _image };
})();
