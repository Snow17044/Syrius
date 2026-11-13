// Mode conversation de Syrius : écoute → réponse à voix haute → réécoute, sans toucher l'écran.
// Dire « stop », « merci Syrius » ou « au revoir » pour terminer. Toucher l'orbe pour couper la parole.
"use strict";

(function () {
  const STOP = /^(stop|stoppe|arr[eê]te|arr[eê]te[- ]toi|tais[- ]toi|merci syrius|au revoir|fin de (la )?conversation|c'est (tout|bon) merci)\b/i;
  let on = false;
  let phase = "";
  let silences = 0;
  let pendingConfirm = null; // action à confirmer à la voix (appel, SMS, lien)
  const YES = /^(oui|ouais|vas[- ]y|d'accord|ok|okay|appelle|lance|confirme|bien s[uû]r|c'est [çc]a)\b/i;

  const $ = (s) => document.querySelector(s);
  const Native = () => window.SyriusAndroid || null;
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function supported() {
    return !!(Native() || Recognition);
  }

  function setPhase(p, text) {
    phase = p;
    const box = $("#voice");
    box.dataset.phase = p;
    $("#voice-status").textContent = text;
  }

  function clean(text) {
    return String(text || "").replace(/```[\s\S]*?```/g, " ").replace(/\p{Extended_Pictographic}|\uFE0F/gu, "")
      .replace(/[`*#>_\[\]()|]/g, "")
      .replace(/https?:\/\/\S+/g, "lien").replace(/\s+/g, " ").trim().slice(0, 1500);
  }

  // ---------------------------------------------------------------- écoute (une phrase)
  function listenOnce() {
    return new Promise((resolve) => {
      const n = Native();
      if (n) {
        let done = false;
        const finish = (t) => { if (done) return; done = true; listenOnce.cancel = null; restore(); resolve(t); };
        const prevSpeech = window.syriusOnSpeech, prevEnd = window.syriusOnSpeechEnd;
        const restore = () => { window.syriusOnSpeech = prevSpeech; window.syriusOnSpeechEnd = prevEnd; };
        window.syriusOnSpeech = (text, isFinal) => {
          $("#voice-heard").textContent = String(text || "");
          if (isFinal) finish(String(text || ""));
        };
        window.syriusOnSpeechEnd = () => finish("");
        n.startListening();
        listenOnce.cancel = () => {
          try { if (typeof n.cancelListening === "function") n.cancelListening(); else n.stopListening(); } catch (_) { /* */ }
          finish("");
        };
        return;
      }
      const rec = new Recognition();
      rec.lang = "fr-FR";
      rec.interimResults = true;
      let final = "";
      rec.onresult = (e) => {
        let t = "";
        for (const r of e.results) t += r[0].transcript;
        $("#voice-heard").textContent = t;
        if (e.results[e.results.length - 1].isFinal) final = t;
      };
      rec.onend = () => resolve(final);
      rec.onerror = () => { /* onend suit */ };
      rec.start();
      listenOnce.cancel = () => { try { rec.abort(); } catch (_) { /* */ } };
    });
  }

  // ---------------------------------------------------------------- parole (attend la fin)
  function speakAndWait(text) {
    const t = clean(text);
    if (!t) return Promise.resolve();
    return new Promise((resolve) => {
      let done = false;
      const finish = () => { if (done) return; done = true; clearTimeout(timer); window.syriusOnSpeakEnd = null; speakAndWait.cancel = null; resolve(); };
      // Estimation de durée si le téléphone ne prévient pas de la fin (ancienne application).
      const timer = setTimeout(finish, 1500 + t.length * 75);
      speakAndWait.cancel = () => { stopSpeaking(); finish(); };
      const n = Native();
      if (n) {
        window.syriusOnSpeakEnd = finish;
        n.speak(t);
        return;
      }
      if (!("speechSynthesis" in window)) { finish(); return; }
      const u = new SpeechSynthesisUtterance(t);
      u.lang = "fr-FR";
      const v = speechSynthesis.getVoices().find((x) => x.lang && x.lang.startsWith("fr"));
      if (v) u.voice = v;
      u.onend = finish;
      u.onerror = finish;
      speechSynthesis.cancel();
      speechSynthesis.speak(u);
    });
  }

  function stopSpeaking() {
    const n = Native();
    if (n) { try { n.speak(" "); } catch (_) { /* */ } } // remplace la phrase en cours (file vidée)
    else if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  function keepAwake(v) {
    const n = Native();
    if (n && typeof n.keepScreenOn === "function") n.keepScreenOn(!!v);
  }

  // ---------------------------------------------------------------- boucle
  async function loop() {
    while (on) {
      setPhase("listen", "Je vous écoute…");
      $("#voice-heard").textContent = "";
      const text = (await listenOnce()).trim();
      if (!on) break;
      if (!text) {
        silences += 1;
        if (silences >= 3) { setPhase("pause", "En pause — touchez l'orbe pour reprendre."); return; }
        continue;
      }
      silences = 0;
      if (STOP.test(text)) {
        setPhase("speak", "À votre service.");
        await speakAndWait("À votre service.");
        close();
        return;
      }
      setPhase("think", "Je réfléchis…");
      $("#voice-reply").textContent = "";
      const reply = await window.SyriusChat.ask(text);
      if (!on) break;
      $("#voice-reply").textContent = clean(reply).slice(0, 400);
      setPhase("speak", "Je réponds…");
      await speakAndWait(reply || "Désolé, je n'ai pas de réponse.");
      if (on && pendingConfirm) { // ex. « Appeler Maman » : on demande un « oui » explicite
        const c = pendingConfirm;
        pendingConfirm = null;
        setPhase("speak", "Je vérifie…");
        await speakAndWait(`${clean(c.label)}. Je confirme ? Dites oui ou non.`);
        setPhase("listen", "Oui ou non ?");
        const answer = (await listenOnce()).trim();
        if (YES.test(answer)) { c.accept(); await speakAndWait("C'est parti."); }
        else { c.refuse(); await speakAndWait("D'accord, j'annule."); }
      }
    }
  }

  function open() {
    if (!supported()) { alert("La reconnaissance vocale n'est pas disponible sur cet appareil."); return; }
    on = true;
    silences = 0;
    $("#voice").classList.remove("hidden");
    $("#voice-reply").textContent = "";
    keepAwake(true);
    loop();
  }

  function close() {
    on = false;
    if (listenOnce.cancel) listenOnce.cancel();
    if (speakAndWait.cancel) speakAndWait.cancel();
    keepAwake(false);
    $("#voice").classList.add("hidden");
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!supported()) return;
    $("#voice-open").classList.remove("hidden");
    $("#voice-open").addEventListener("click", open);
    $("#voice-close").addEventListener("click", close);
    // Toucher l'orbe : couper la parole / reprendre / relancer l'écoute.
    $("#voice-orb").addEventListener("click", () => {
      if (phase === "speak" && speakAndWait.cancel) speakAndWait.cancel();
      else if (phase === "pause") { silences = 0; loop(); }
      else if (phase === "listen" && listenOnce.cancel) listenOnce.cancel();
    });
  });

  function confirm(label, accept, refuse) { pendingConfirm = { label, accept, refuse }; }

  window.SyriusVoice = { open, close, confirm, get active() { return on; } };
})();
