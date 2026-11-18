// Page d'installation : montre la bonne marche à suivre selon le téléphone.
(function () {
  const $ = (s) => document.querySelector(s);
  const ua = navigator.userAgent;
  const android = /android/i.test(ua);
  const ios = /iphone|ipad|ipod/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  // Navigateurs intégrés aux applis (où l'installation est impossible)
  const integre = /FBAN|FBAV|FB_IAB|Instagram|Line\/|TikTok|BytedanceWebview|musical_ly|Snapchat|LinkedInApp|Twitter/i.test(ua) || (android && /; wv\)/.test(ua));
  const installee = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  function montrer(id) {
    document.querySelectorAll("main > section").forEach((s) => { s.hidden = s.id !== id; });
  }

  if (installee) montrer("deja");
  else if (integre && android) {
    montrer("integre-android");
    // Lien spécial qui rouvre cette page dans Chrome
    $("#ouvrir-chrome").href = `intent://${location.host}/installer#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=${encodeURIComponent(location.href)};end`;
  } else if (integre && ios) montrer("integre-ios");
  else if (android) montrer("android");
  else if (ios) montrer("ios");
  else {
    montrer("ordinateur");
    $("#adresse").textContent = `${location.host}/installer`;
  }

  // Android / ordinateur : vrai bouton « Installer » quand le navigateur le permet
  let invitation = null;
  addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    invitation = e;
    if (installee || integre) return;
    if (!android) montrer("android");
    $("#installer").hidden = false;
    $("#android-manuel").hidden = true;
  });
  $("#installer").addEventListener("click", async () => {
    if (!invitation) return;
    invitation.prompt();
    const choix = await invitation.userChoice;
    invitation = null;
    if (choix.outcome !== "accepted") { $("#installer").hidden = true; $("#android-manuel").hidden = false; }
  });
  addEventListener("appinstalled", () => montrer("installee"));

  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
})();
