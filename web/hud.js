// Panneau holographique de Syrius : carte 3D (bâtiments en relief) + liste des lieux trouvés.
// Carte 3D avec MapLibre si le téléphone sait faire de la 3D (WebGL), sinon carte 2D (Leaflet).
// Aucun texte venant d'Internet n'est inséré comme HTML : tout passe par textContent.
"use strict";

(function () {
  const TILES_2D = "/tiles/{z}/{x}/{y}.png"; // relayées par le serveur Syrius
  const ATTRIBUTION = "© OpenStreetMap";
  let map = null;       // carte 3D (MapLibre) ou 2D (Leaflet)
  let mode = "";        // "3d" ou "2d"
  let layer = null;     // repères 2D
  let markers = [];     // repères 3D
  let spin = 0;         // rotation lente façon hologramme

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

  function webglOk() {
    try {
      const c = document.createElement("canvas");
      return !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch (e) {
      return false;
    }
  }

  // ------------------------------------------------------------------ style holographique 3D
  function style3d() {
    const o = location.origin;
    const name = ["coalesce", ["get", "name:fr"], ["get", "name"]];
    return {
      version: 8,
      glyphs: o + "/map3d/fonts/{fontstack}/{range}.pbf",
      sources: {
        omt: { type: "vector", tiles: [o + "/map3d/t/{z}/{x}/{y}.pbf"], minzoom: 0, maxzoom: 14,
          attribution: "© OpenStreetMap · OpenFreeMap" },
      },
      layers: [
        { id: "fond", type: "background", paint: { "background-color": "#030a14" } },
        { id: "parcs", type: "fill", source: "omt", "source-layer": "park",
          paint: { "fill-color": "#06261f", "fill-opacity": 0.7 } },
        { id: "eau", type: "fill", source: "omt", "source-layer": "water",
          paint: { "fill-color": "#072a45" } },
        { id: "routes", type: "line", source: "omt", "source-layer": "transportation",
          filter: ["match", ["get", "class"], ["path", "track", "rail", "transit", "ferry"], false, true],
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": ["match", ["get", "class"], ["motorway", "trunk", "primary"], "#4fe3ff", "#1d7fa3"],
            "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 10, 0.5, 14, 2, 18, 12],
            "line-opacity": 0.85,
          } },
        { id: "batiments", type: "fill-extrusion", source: "omt", "source-layer": "building", minzoom: 13,
          paint: {
            "fill-extrusion-color": ["interpolate", ["linear"], ["coalesce", ["get", "render_height"], 6],
              0, "#0b3a58", 30, "#1696c2", 100, "#5fe6ff"],
            "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
            "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
            "fill-extrusion-opacity": 0.82,
          } },
        { id: "noms-rues", type: "symbol", source: "omt", "source-layer": "transportation_name", minzoom: 15,
          layout: { "symbol-placement": "line", "text-field": name, "text-font": ["Noto Sans Regular"],
            "text-size": 11 },
          paint: { "text-color": "#8fdcf2", "text-halo-color": "#030a14", "text-halo-width": 1.5 } },
        { id: "villes", type: "symbol", source: "omt", "source-layer": "place",
          layout: { "text-field": name, "text-font": ["Noto Sans Bold"],
            "text-size": ["interpolate", ["linear"], ["zoom"], 8, 11, 14, 14] },
          paint: { "text-color": "#bff4ff", "text-halo-color": "#030a14", "text-halo-width": 2 } },
      ],
    };
  }

  function stopSpin() {
    if (spin) cancelAnimationFrame(spin);
    spin = 0;
  }

  function startSpin() {
    stopSpin();
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let last = performance.now();
    const step = (t) => {
      if (!map || mode !== "3d") return;
      if (!map.isMoving()) map.setBearing(map.getBearing() + ((t - last) / 1000) * 4); // 4°/s
      last = t;
      spin = requestAnimationFrame(step);
    };
    spin = requestAnimationFrame(step);
  }

  function init3d() {
    maplibregl.setWorkerUrl("/static/maplibre-gl-worker.js");
    map = new maplibregl.Map({
      container: "hud-map", style: style3d(), center: [2.35, 48.85], zoom: 15,
      pitch: 60, bearing: -20, maxPitch: 75, attributionControl: { compact: true },
    });
    // Le doigt de l'utilisateur arrête la rotation automatique.
    ["mousedown", "touchstart", "wheel"].forEach((ev) => map.getCanvas().addEventListener(ev, stopSpin,
      { passive: true }));
    map.on("error", () => {}); // une tuile manquante ne doit pas casser la carte
    mode = "3d";
  }

  function init2d() {
    map = L.map("hud-map", { zoomControl: false, attributionControl: true });
    L.tileLayer(TILES_2D, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
    document.getElementById("hud-map").classList.add("flat");
    mode = "2d";
  }

  function pin(n) {
    const e = el("div", "hud-pin hud-pin3d", n); // chiffre uniquement
    return e;
  }

  function place3d(points, places, select) {
    markers.forEach((m) => m.remove());
    markers = [];
    points.forEach((pt) => {
      const m = pt.me
        ? new maplibregl.Marker({ element: el("div", "hud-me hud-me3d") })
        : new maplibregl.Marker({ element: pin(pt.n), anchor: "center" });
      m.setLngLat([pt.lon, pt.lat]).addTo(map);
      if (!pt.me) m.getElement().addEventListener("click", (e) => { e.stopPropagation(); select(pt.i); });
      markers.push(m);
    });
    setTimeout(() => {
      map.resize();
      if (points.length === 1) {
        map.jumpTo({ center: [points[0].lon, points[0].lat], zoom: 16.5, pitch: 60 });
      } else {
        const b = new maplibregl.LngLatBounds();
        points.forEach((pt) => b.extend([pt.lon, pt.lat]));
        const cam = map.cameraForBounds(b, { padding: 50, maxZoom: 17 }) || {};
        map.jumpTo({ center: cam.center || b.getCenter(), zoom: Math.min(cam.zoom || 15, 17), pitch: 0, bearing: 0 });
        map.easeTo({ pitch: 60, bearing: -20, duration: 1200 });
      }
      map.once("idle", startSpin);
    }, 50);
  }

  function place2d(points) {
    if (layer) layer.remove();
    layer = L.layerGroup().addTo(map);
    points.forEach((pt) => {
      if (pt.me) {
        L.marker([pt.lat, pt.lon], {
          icon: L.divIcon({ className: "hud-me", iconSize: [18, 18] }), interactive: false,
        }).addTo(layer);
      } else {
        const m = L.marker([pt.lat, pt.lon], {
          icon: L.divIcon({ className: "hud-pin", html: pt.n, iconSize: [30, 30] }), // chiffre uniquement
          title: pt.name,
        }).addTo(layer);
        m.on("click", () => pt.select());
      }
    });
    setTimeout(() => {
      map.invalidateSize();
      const ll = points.map((pt) => [pt.lat, pt.lon]);
      if (ll.length === 1) map.setView(ll[0], 16);
      else map.fitBounds(ll, { padding: [36, 36], maxZoom: 17 });
    }, 50);
  }

  function focus(p) {
    if (mode === "3d") {
      stopSpin();
      map.flyTo({ center: [p.lon, p.lat], zoom: 17.5, pitch: 65, duration: 1400 });
    } else {
      map.setView([p.lat, p.lon], 17, { animate: true });
    }
  }

  function close() {
    stopSpin();
    document.getElementById("hud").classList.add("hidden");
  }

  function show(ev) {
    const hud = document.getElementById("hud");
    const places = (Array.isArray(ev.places) ? ev.places.slice(0, 8) : [])
      .filter((p) => p && typeof p.lat === "number" && typeof p.lon === "number");
    const has3d = typeof maplibregl !== "undefined" && webglOk();
    if (!places.length || (!has3d && typeof L === "undefined")) return;
    hud.classList.remove("hidden");
    document.getElementById("hud-query").textContent = String(ev.query || "").slice(0, 80);

    if (!map) {
      try {
        if (has3d) init3d(); else init2d();
      } catch (e) {
        map = null;
        if (typeof L === "undefined") return;
        init2d();
      }
    }

    const list = document.getElementById("hud-list");
    list.replaceChildren();
    const items = [];
    const select = (i) => items[i] && items[i].click();
    const points = [];
    if (ev.me && typeof ev.me.lat === "number" && typeof ev.me.lon === "number") {
      points.push({ me: true, lat: ev.me.lat, lon: ev.me.lon });
    }
    places.forEach((p, i) => {
      const n = String(i + 1);
      points.push({ n, i, lat: p.lat, lon: p.lon, name: String(p.name || ""), select: () => select(i) });

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
        focus(p);
        document.querySelectorAll(".hud-item.active").forEach((x) => x.classList.remove("active"));
        item.classList.add("active");
      });
      items.push(item);
      list.appendChild(item);
    });

    if (mode === "3d") place3d(points, places, select); else place2d(points);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("hud-close").addEventListener("click", close);
  });

  window.SyriusHUD = { show, close };
})();
