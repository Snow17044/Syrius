// Mode conversation de Syrius : écoute → réponse à voix haute → réécoute, sans toucher l'écran.
// Dire « stop », « merci Syrius » ou « au revoir » pour terminer. Toucher l'orbe pour couper la parole.
"use strict";

(function () {
  const STOP = /^(stop|stoppe|arr[eê]te|arr[eê]te[- ]toi|tais[- ]toi|merci syrius|au revoir|fin de (la )?conversation|c'est (tout|bon) merci)\b/i;
  let on = false;
  let phase = "";
  let silences = 0;
  let pendingConfirm = null; // action à confirmer à la voix (appel, SMS, lien)
  let dismissedIn = undefined;  // discussion où Aurora a été renvoyée : on ne la rappelle pas d'office
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
      .replace(/https?:\/\/\S+/g, "lien").replace(/\s+/g, " ").trim().slice(0, 6000);
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
  function speakAndWait(text, who) {
    const t = clean(text);
    if (!t) return Promise.resolve();
    return new Promise((resolve) => {
      let done = false;
      const finish = () => { if (done) return; done = true; clearTimeout(timer); window.syriusOnSpeakEnd = null; speakAndWait.cancel = null; resolve(); };
      // Estimation de durée si le téléphone ne prévient pas de la fin (ancienne application).
      const timer = setTimeout(finish, 1500 + t.length * 75);
      speakAndWait.cancel = () => { stopSpeaking(); finish(); };
      if (who && typeof window.speakAs === "function") { window.speakAs(t, who, finish); return; }  // chacun sa voix
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

  // ---------------------------------------------------------------- visages animés (Nova, et Aurora si elle est là)
  const F = () => window.SyriusFaces;
  const withAurora = () => { try { return !!state.aurora; } catch (_) { return false; } };
  const currentConv = () => { try { return state.convId || "nouvelle"; } catch (_) { return "nouvelle"; } };
  function buildFaces() {
    const box = $("#voice-faces");
    if (!box || !F()) return;
    box.replaceChildren(F().make("nova", "Nova"));
    if (withAurora()) box.appendChild(F().make("aurora", "Aurora"));
    $("#voice").classList.toggle("has-faces", true);
    $("#voice").classList.toggle("duo", withAurora());
    const b = $("#voice-aurora");
    if (b) b.textContent = withAurora() ? "Laisser Nova seul" : "Inviter Aurora";
  }
  function faces(mode) {
    if (!F()) return;
    F().set("nova", { mode });
    F().set("aurora", { mode });
  }

  // ---------------------------------------------------------------- boucle
  async function loop() {
    while (on) {
      setPhase("listen", "Je t'écoute…");
      faces("listen");
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
        setPhase("speak", "À plus tard !");
        if (F()) F().set("nova", { expr: "content", mode: "talk" });
        await speakAndWait("Ça marche, à plus tard !", "nova");
        close();
        return;
      }
      setPhase("think", withAurora() ? "Ils réfléchissent…" : "Je réfléchis…");
      faces("think");
      $("#voice-reply").textContent = "";
      const replies = window.SyriusChat.askAll ? await window.SyriusChat.askAll(text) : [{ who: "nova", text: await window.SyriusChat.ask(text), expr: "" }];
      if (!on) break;
      if (!replies.length) replies.push({ who: "nova", text: "Désolé, je n'ai pas de réponse.", expr: "inquiet" });
      faces("idle");
      for (const r of replies) {  // chacun parle à son tour, avec sa voix et son expression
        if (!on) break;
        const name = r.who === "aurora" ? "Aurora" : "Nova";
        $("#voice-reply").textContent = (replies.length > 1 ? name + " : " : "") + clean(r.text).slice(0, 400);
        setPhase("speak", name + " répond…");
        if (F()) F().set(r.who, { expr: r.expr || "content", mode: "talk" });
        await speakAndWait(r.text, r.who);
        if (F()) F().set(r.who, { mode: "idle" });
      }
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

  // ---------------------------------------------------------------- en direct, à côté de la voix
  // Les cartes produites par l'IA (appel, action, image, météo…) sont déplacées ici pendant la conversation,
  // puis remises à leur place dans la discussion à la fin (leurs boutons restent actifs).
  const staged = [];
  function stage(node) {
    if (!on || !node) return;
    staged.push({ node, parent: node.parentNode, next: node.nextSibling });
    const box = $("#voice-stage");
    box.appendChild(node);
    $("#voice").classList.add("has-stage");
    requestAnimationFrame(() => node.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" }));
  }
  function unstage() {
    while (staged.length) {
      const { node, parent, next } = staged.shift();
      if (parent && parent.isConnected) parent.insertBefore(node, next && next.parentNode === parent ? next : null);
      else node.remove();
    }
    $("#voice").classList.remove("has-stage");
  }
  // Schéma, maquette 3D ou carte ouverts pendant la conversation : affichés en haut, la voix continue en bas.
  const PANELS = ["#hud", "#holo", "#m3d"];
  function updateSplit() {
    const any = PANELS.some((q) => { const el = $(q); return el && !el.classList.contains("hidden"); });
    document.body.classList.toggle("voice-split", on && any);
  }
  document.addEventListener("DOMContentLoaded", () => {
    const mo = new MutationObserver(updateSplit);
    PANELS.forEach((q) => { const el = $(q); if (el) mo.observe(el, { attributes: true, attributeFilter: ["class"] }); });
  });

  function open() {
    if (!supported()) { alert("La reconnaissance vocale n'est pas disponible sur cet appareil."); return; }
    on = true;
    silences = 0;
    unstage();
    $("#voice").classList.remove("hidden");
    buildFaces();
    // Aurora vient d'office à côté de Nova quand on parle (sauf si on l'a fait partir pendant cette conversation).
    if (dismissedIn !== currentConv() && window.SyriusGroup && !window.SyriusGroup.active) window.SyriusGroup.join().then(buildFaces);
    updateSplit();
    $("#voice-reply").textContent = "";
    keepAwake(true);
    loop();
  }

  function close() {
    on = false;
    if (listenOnce.cancel) listenOnce.cancel();
    if (speakAndWait.cancel) speakAndWait.cancel();
    keepAwake(false);
    unstage();
    $("#voice").classList.add("hidden");
    updateSplit();
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!supported()) return;
    $("#voice-open").classList.remove("hidden");
    $("#voice-open").addEventListener("click", open);
    $("#voice-close").addEventListener("click", close);
    // Toucher un visage = toucher l'orbe (couper la parole, reprendre).
    $("#voice-faces")?.addEventListener("click", () => $("#voice-orb").click());
    // Faire partir Aurora (ou la faire revenir) pendant la conversation vocale.
    $("#voice-aurora")?.addEventListener("click", async () => {
      if (!window.SyriusGroup) return;
      if (withAurora()) { await window.SyriusGroup.leave(); dismissedIn = currentConv(); }
      else { dismissedIn = undefined; await window.SyriusGroup.join(); }
      buildFaces();
    });
    // Toucher l'orbe : couper la parole / reprendre / relancer l'écoute.
    $("#voice-orb").addEventListener("click", () => {
      if (phase === "speak" && speakAndWait.cancel) speakAndWait.cancel();
      else if (phase === "pause") { silences = 0; loop(); }
      else if (phase === "listen" && listenOnce.cancel) listenOnce.cancel();
    });
  });

  function confirm(label, accept, refuse) { pendingConfirm = { label, accept, refuse }; }

  window.SyriusVoice = { open, close, confirm, stage, get active() { return on; } };
})();
