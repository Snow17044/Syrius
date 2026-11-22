// Banc d'essai de l'atelier instantané : chargé AU DÉBUT du site d'Aurora (dans sa boîte fermée), il note toutes les
// erreurs (console, scripts, fichiers introuvables), lance ses tests (window.__tests) puis envoie le bilan à Syrius Code.
"use strict";
(function () {
  const errors = [];
  const add = (m) => { if (errors.length < 30) errors.push(String(m).slice(0, 300)); };
  window.addEventListener("error", (e) => {
    const t = e.target;
    if (t && t !== window && (t.src || t.href)) add("Ressource introuvable : " + (t.src || t.href).split("/site/").pop());
    else add((e.message || "Erreur") + (e.lineno ? ` (ligne ${e.lineno})` : ""));
  }, true);
  window.addEventListener("unhandledrejection", (e) => add("Promesse rejetée : " + (e.reason && e.reason.message || e.reason)));
  const ce = console.error.bind(console);
  console.error = (...a) => { add("console.error : " + a.join(" ")); ce(...a); };

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const q = (s) => { const el = document.querySelector(s); if (!el) throw new Error("élément introuvable : " + s); return el; };
  const t = {
    q, wait,
    click: (s) => q(s).click(),
    type: (s, txt) => { const el = q(s); el.focus(); el.value = txt; el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); },
    text: (s) => (q(s).textContent || "").trim(),
    assert: (ok, msg) => { if (!ok) throw new Error(msg || "vérification ratée"); },
  };

  // ---------------------------------------------------------------- contrôle du design (règles simples et sûres)
  function rgb(c) {
    const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/.exec(c || "");
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  }
  function lum([r, g, b]) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }
  function background(el) {  // couleur de fond réelle (le premier parent opaque) ; null si image ou dégradé
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== "none") return null;
      const c = rgb(cs.backgroundColor);
      if (c && c[3] > 0.9) return c;
    }
    return [255, 255, 255, 1];
  }
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none" && +cs.opacity > 0.1; };
  function designChecks() {
    const out = [];
    if (!document.querySelector('meta[name="viewport"]')) out.push("balise <meta name=\"viewport\"> manquante (le site sera minuscule sur téléphone).");
    const body = getComputedStyle(document.body);
    if (/times/i.test(body.fontFamily) || body.fontFamily.trim() === "serif") out.push("police par défaut du navigateur (Times) : choisis une police moderne.");
    if (parseFloat(body.fontSize) < 15) out.push(`texte de base trop petit (${parseFloat(body.fontSize)} px, il faut 16 px ou plus).`);
    if (!document.querySelector("h1")) out.push("pas de titre principal <h1>.");
    const small = [...document.querySelectorAll("button, input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea, [role=button]")]
      .filter((el) => visible(el) && el.getBoundingClientRect().height < 36);
    if (small.length) out.push(`${small.length} élément(s) cliquable(s) trop petit(s) pour un doigt (moins de 40 px de haut).`);
    let bad = 0, sample = "";
    const texts = [...document.querySelectorAll("p, span, a, li, h1, h2, h3, h4, label, button, td, small, strong, em")].slice(0, 300);
    for (const el of texts) {
      if (!visible(el) || ![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
      const cs = getComputedStyle(el), fg = rgb(cs.color), bg = background(el);
      if (!fg || !bg || fg[3] < 0.5) continue;
      const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
      const ratio = (a + 0.05) / (b + 0.05), big = parseFloat(cs.fontSize) >= 24 || (parseFloat(cs.fontSize) >= 18.6 && +cs.fontWeight >= 700);
      if (ratio < (big ? 3 : 4.5)) { bad++; if (!sample) sample = ` (ex. « ${el.textContent.trim().slice(0, 30)} » : ${ratio.toFixed(1)}:1)`; }
    }
    if (bad) out.push(`${bad} texte(s) peu lisible(s), contraste trop faible${sample} : il faut au moins 4.5:1.`);
    const noAlt = [...document.querySelectorAll("img")].filter((i) => !i.hasAttribute("alt")).length;
    if (noAlt) out.push(`${noAlt} image(s) sans texte alternatif (alt).`);
    return out;
  }

  async function run() {
    await wait(600);  // laisse le site démarrer
    const results = [];
    const tests = Array.isArray(window.__tests) ? window.__tests.slice(0, 12) : null;
    if (!tests) results.push({ nom: "tests.js", ok: false, erreur: "aucun test trouvé (window.__tests absent)" });
    for (const x of tests || []) {
      try {
        await Promise.race([Promise.resolve(x.test(t)), wait(5000).then(() => { throw new Error("trop long (5 s)"); })]);
        results.push({ nom: String(x.nom || "test"), ok: true });
      } catch (err) {
        results.push({ nom: String(x.nom || "test"), ok: false, erreur: String(err && err.message || err).slice(0, 300) });
      }
    }
    const w = document.documentElement.scrollWidth, vw = window.innerWidth;
    if (w > vw + 4) errors.push(`La page déborde de l'écran (${w} px de large pour ${vw} px) : pas adaptée au téléphone.`);
    for (const d of designChecks()) errors.push("Design : " + d);
    parent.postMessage({ syriusAtelierTest: true, errors, results, titre: document.title.slice(0, 120) }, "*");
  }
  if (document.readyState === "complete") run(); else window.addEventListener("load", run);
})();
