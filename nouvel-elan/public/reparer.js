// Page de réparation et de diagnostic : efface les vieux caches puis teste le programme et ses photos.
(async function () {
  const liste = document.getElementById("diag");
  function ligne(etat, texte) {
    const li = document.createElement("li");
    li.className = etat; // "ok", "ko" ou "info"
    li.textContent = `${etat === "ok" ? "✅" : etat === "ko" ? "❌" : "ℹ️"} ${texte}`;
    liste.append(li);
    return li;
  }
  const t = Date.now();

  // 1. Téléphone et navigateur
  const ua = navigator.userAgent;
  const appareil = /iphone|ipad|ipod/i.test(ua) ? "iPhone/iPad" : /android/i.test(ua) ? "Android" : "Ordinateur";
  const navigateur = /Instagram/i.test(ua) ? "Instagram" : /FBAN|FBAV|FB_IAB/i.test(ua) ? "Facebook" : /SamsungBrowser/i.test(ua) ? "Samsung Internet"
    : /EdgA?\//.test(ua) ? "Edge" : /Firefox|FxiOS/.test(ua) ? "Firefox" : /CriOS|Chrome/.test(ua) ? "Chrome" : /Safari/.test(ua) ? "Safari" : "autre";
  const installee = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  ligne("info", `${appareil} · ${navigateur}${installee ? " · appli installée" : ""}`);
  const BONNE = "nouvelles-elan.vercel.app";
  if (location.hostname === BONNE || location.hostname === "localhost") ligne("ok", `Bonne adresse : ${location.hostname}`);
  else ligne("ko", `Mauvaise adresse : ${location.hostname} — utilise ${BONNE}`);

  // 2. Nettoyage des vieilles versions
  try {
    let n = 0;
    if ("serviceWorker" in navigator) for (const r of await navigator.serviceWorker.getRegistrations()) { await r.unregister(); n++; }
    let c = [];
    if (window.caches) { c = await caches.keys(); for (const k of c) await caches.delete(k); }
    for (const cle of ["ne-articles", "ne-programme"]) { try { localStorage.removeItem(cle); } catch {} }
    ligne("ok", `Vieilles versions effacées (${n} service, ${c.length} cache${c.length > 1 ? "s" : ""}${c.length ? " : " + c.join(", ") : ""})`);
  } catch (e) { ligne("ko", `Nettoyage impossible : ${e.message}`); }

  // 3. Version de l'appli sur le serveur
  try {
    const code = await (await fetch(`/app.js?_=${t}`, { cache: "no-store" })).text();
    const v = (code.match(/const VERSION = "([^"]+)"/) || [])[1];
    ligne(v ? "ok" : "ko", v ? `Version de l'appli : ${v}` : "Version de l'appli introuvable");
  } catch (e) { ligne("ko", `Serveur injoignable : ${e.message}`); }

  // 4. Programme et photos
  let programme = null;
  try {
    const r = await fetch(`/api/programme?_=${t}`, { cache: "no-store" });
    programme = (await r.json()).programme;
    const avecPhoto = programme.axes.filter((a) => a.photo);
    ligne(programme.axes.length ? "ok" : "ko", `Programme reçu : ${programme.axes.length} thème${programme.axes.length > 1 ? "s" : ""}, ${avecPhoto.length} avec photo`);
  } catch (e) { ligne("ko", `Programme non reçu : ${e.message}`); }

  // Photos stockées sur le serveur (visible pour l'équipe, avec le code déjà enregistré sur ce téléphone)
  let code = ""; try { code = localStorage.getItem("ne-code-editeur") || ""; } catch {}
  if (code) {
    try {
      const r = await fetch(`/api/photo?liste=1&_=${t}`, { cache: "no-store", headers: { "X-Code-Editeur": code } });
      const n = r.ok ? (await r.json()).photos.length : null;
      ligne(n == null ? "info" : "ok", n == null ? "Photos stockées : vérification impossible" : `Photos stockées sur le serveur : ${n} (réutilisables avec « 🖼 Choisir parmi les photos déjà envoyées »)`);
    } catch {}
  }

  if (programme) {
    const zone = document.getElementById("photos");
    const essais = programme.axes.filter((a) => a.photo).map((a, i) => new Promise((fin) => {
      const li = ligne("info", `Photo du thème « ${a.titre.slice(0, 40)} » : chargement…`);
      const img = new Image();
      const delai = setTimeout(() => { li.className = "ko"; li.textContent = `❌ Photo « ${a.titre.slice(0, 40)} » : trop longue à charger`; fin(); }, 15000);
      img.onload = () => { clearTimeout(delai); li.className = "ok"; li.textContent = `✅ Photo « ${a.titre.slice(0, 40)} » : OK (${img.naturalWidth}×${img.naturalHeight})`; zone.append(img); fin(); };
      img.onerror = async () => {
        clearTimeout(delai);
        let statut = "";
        try { statut = ` (réponse du serveur : ${(await fetch(a.photo, { cache: "no-store" })).status})`; } catch (e) { statut = ` (${e.message})`; }
        li.className = "ko"; li.textContent = `❌ Photo « ${a.titre.slice(0, 40)} » : ne se charge pas${statut}`; fin();
      };
      img.alt = "";
      img.src = a.photo;
    }));
    await Promise.all(essais);
  }

  const ouvrir = document.getElementById("ouvrir");
  ouvrir.href = `/?maj=${t}`;
  ouvrir.hidden = false;
})();
