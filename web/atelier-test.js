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
    parent.postMessage({ syriusAtelierTest: true, errors, results, titre: document.title.slice(0, 120) }, "*");
  }
  if (document.readyState === "complete") run(); else window.addEventListener("load", run);
})();
