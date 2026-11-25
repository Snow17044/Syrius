// Page « partenaire » : un ami de Syrius crée son assistant avec le lien d'invitation (/partenaire#jeton).
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const token = decodeURIComponent(location.hash.slice(1));
  history.replaceState(null, "", location.pathname); // le jeton ne reste pas dans la barre d'adresse

  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Vérifie les champs et réessaie.");
    return d;
  }
  function bad(text) {
    if (text) $("#p-bad-text").textContent = text;
    $("#p-bad").classList.remove("hidden");
    $("#p-form").classList.add("hidden");
  }
  const limitText = (n) => `Jusqu'à ${n} messages par jour pour tout le site (et 60 par visiteur).`;

  if (!token) { bad(); return; }
  post("/api/v1/invite/info", { token }).then((info) => {
    $("#p-limit").textContent = limitText(info.limit);
    $("#p-form").classList.remove("hidden");
    $("#p-name").focus();
  }).catch((e) => bad(e.message));

  $("#p-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    $("#p-msg").textContent = "";
    $("#p-go").disabled = true;
    const origins = [$("#p-origin").value, ...$("#p-origins-more").value.split(/[\s,]+/)].map((o) => o.trim()).filter(Boolean);
    try {
      const r = await post("/api/v1/invite/redeem", {
        token, name: $("#p-name").value.trim(), origins, bot_name: $("#p-bot").value.trim() || "Nova",
        instructions: $("#p-instr").value.trim() });
      $("#p-snippet").value = `<script src="${location.origin}/widget.js" data-key="${r.secret}" defer></script>`;
      $("#p-limit2").textContent = "Adresses autorisées : " + r.key.origins.join(", ") + ". " + limitText(r.key.limit);
      $("#p-form").classList.add("hidden");
      $("#p-done").classList.remove("hidden");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      $("#p-msg").textContent = "⚠ " + err.message;
    } finally { $("#p-go").disabled = false; }
  });

  $("#p-copy").addEventListener("click", async () => {
    const ta = $("#p-snippet");
    let ok = false;
    try { await navigator.clipboard.writeText(ta.value); ok = true; } catch (_) {
      ta.select(); try { ok = document.execCommand("copy"); } catch (__) { ok = false; }
    }
    $("#p-copy-msg").textContent = ok ? "✅ Code copié." : "Sélectionne le code et copie-le.";
  });
})();
