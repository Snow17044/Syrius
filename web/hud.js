// Panneau holographique de Syrius : carte + liste des lieux trouvés.
// Aucun texte venant d'Internet n'est inséré comme HTML : tout passe par textContent.
"use strict";

(function () {
  // Cartes OpenStreetMap relayées par le serveur Syrius (aucune clé, rien envoyé à un tiers).
  // Assombries en CSS pour l'effet holographique.
  const TILES = "/tiles/{z}/{x}/{y}.png";
  const ATTRIBUTION = "© OpenStreetMap";
  let map = null;
  let layer = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function fmtDistance(m) {
    if (typeof m !== "number") return "";
    return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1).replace(".", ",")} km`;
  }

  function navigate(p) {
    const dest = `${p.lat},${p.lon}`;
    const native = window.SyriusAndroid;
    if (native && typeof native.device === "function") {
      native.device(JSON.stringify({ action: "phone_map", params: { query: dest, navigate: true } }));
    } else {
      window.open("https://www.google.com/maps/dir/?api=1&destination=" + encodeURIComponent(dest),
        "_blank", "noopener");
    }
  }

  function close() {
    document.getElementById("hud").classList.add("hidden");
  }

  function show(ev) {
    const hud = document.getElementById("hud");
    const places = Array.isArray(ev.places) ? ev.places.slice(0, 8) : [];
    if (!places.length || typeof L === "undefined") return;
    hud.classList.remove("hidden");
    document.getElementById("hud-query").textContent = String(ev.query || "").slice(0, 80);

    if (!map) {
      map = L.map("hud-map", { zoomControl: false, attributionControl: true });
      L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
    }
    if (layer) layer.remove();
    layer = L.layerGroup().addTo(map);

    const points = [];
    if (ev.me && typeof ev.me.lat === "number") {
      L.marker([ev.me.lat, ev.me.lon], {
        icon: L.divIcon({ className: "hud-me", iconSize: [18, 18] }), interactive: false,
      }).addTo(layer);
      points.push([ev.me.lat, ev.me.lon]);
    }

    const list = document.getElementById("hud-list");
    list.replaceChildren();
    places.forEach((p, i) => {
      if (typeof p.lat !== "number" || typeof p.lon !== "number") return;
      const n = String(i + 1);
      const marker = L.marker([p.lat, p.lon], {
        icon: L.divIcon({ className: "hud-pin", html: n, iconSize: [30, 30] }), // chiffre uniquement
        title: String(p.name || ""),
      }).addTo(layer);
      points.push([p.lat, p.lon]);

      const item = el("li", "hud-item");
      const badge = el("span", "hud-num", n);
      const info = el("div", "hud-info");
      info.append(el("div", "hud-name", String(p.name || "Lieu")));
      const meta = [fmtDistance(p.distance_m), String(p.address || "")].filter(Boolean).join(" · ");
      info.append(el("div", "hud-meta", meta));
      const go = el("button", "hud-go", "Y aller");
      go.type = "button";
      go.addEventListener("click", (e) => { e.stopPropagation(); navigate(p); });
      item.append(badge, info, go);
      item.addEventListener("click", () => {
        map.setView([p.lat, p.lon], 17, { animate: true });
        document.querySelectorAll(".hud-item.active").forEach((x) => x.classList.remove("active"));
        item.classList.add("active");
      });
      marker.on("click", () => item.click());
      list.appendChild(item);
    });

    setTimeout(() => {
      map.invalidateSize();
      if (points.length === 1) map.setView(points[0], 16);
      else map.fitBounds(points, { padding: [36, 36], maxZoom: 17 });
    }, 50);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("hud-close").addEventListener("click", close);
  });

  window.SyriusHUD = { show, close };
})();
