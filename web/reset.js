// Réinitialisation du mot de passe du propriétaire (code de secours défini dans Vercel).
"use strict";
(function () {
  const $ = (s) => document.querySelector(s);
  async function state() {
    try {
      const r = await fetch("/api/reset/state", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.available) { $("#r-form").classList.add("hidden"); $("#r-off").classList.remove("hidden"); }
    } catch (_) { $("#r-msg").textContent = "⚠ Serveur injoignable."; }
  }
  $("#r-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("#r-msg");
    msg.textContent = "";
    if ($("#r-password").value !== $("#r-password2").value) { msg.textContent = "⚠ Les deux mots de passe sont différents."; return; }
    $("#r-go").disabled = true;
    try {
      const res = await fetch("/api/reset", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Syrius": "1" },
        body: JSON.stringify({ code: $("#r-code").value, password: $("#r-password").value }) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : `Erreur ${res.status}`);
      $("#r-form").reset();
      msg.textContent = "✅ Mot de passe changé. Tu peux te reconnecter. Pense à supprimer la variable SYRIUS_RESET_CODE dans Vercel (puis Redeploy) : la réinitialisation sera de nouveau désactivée.";
    } catch (err) {
      msg.textContent = "⚠ " + err.message;
    } finally { $("#r-go").disabled = false; }
  });
  state();
})();
