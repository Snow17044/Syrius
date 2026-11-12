// Service worker : démarre l'app instantanément (interface en cache).
// Les données (/api) ne sont JAMAIS mises en cache : elles restent sur ton serveur.
"use strict";
const VERSION = "syrius-v6";
const SHELL = ["/", "/static/style.css", "/static/app.js", "/static/markdown.js",
  "/static/manifest.webmanifest", "/icons/icon.svg", "/icons/icon-192.png",
  "/static/leaflet.js", "/static/leaflet.css", "/static/hud.js",
  "/static/maplibre-gl.js", "/static/maplibre-gl-worker.js", "/static/maplibre-gl.css"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/tiles/") || url.pathname.startsWith("/map3d/")) return;
  // Réseau d'abord (pour avoir la dernière version), cache si hors ligne.
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok && SHELL.includes(url.pathname)) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
