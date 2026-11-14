// Icônes de Syrius : un seul jeu dessiné sur mesure (traits fins arrondis, grille 24 × 24), à la place des emojis.
// <i data-icon="micro"></i> dans le HTML est remplacé par le dessin ; SyriusIcons.svg("micro") en JavaScript ;
// SyriusIcons.draw(ctx, …) pour les dessins sur <canvas> (schémas). Contenu fixe : aucune donnée extérieure.
"use strict";

(function () {
  const NS = "http://www.w3.org/2000/svg";
  const P = {
    menu: '<path d="M4 7h16M4 12h16M4 17h10"/>',
    close: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    chart: '<path d="M4 19h16"/><path d="M5 15l4-5 4 3 6-7"/><circle cx="9" cy="10" r="1"/><circle cx="13" cy="13" r="1"/>',
    compose: '<path d="M4.5 19.5h4L19 9a2.1 2.1 0 0 0-3-3L5.5 16.5z"/><path d="M14 8l3 3"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    settings: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    logout: '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4"/><path d="M10 8l-4 4 4 4M6 12h10"/>',
    send: '<path d="M12 19V5.5M6.5 11L12 5.5 17.5 11"/>',
    stop: '<rect x="7" y="7" width="10" height="10" rx="2.6"/>',
    mic: '<rect x="9" y="3.5" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5v3"/>',
    wave: '<path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/>',
    camera: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.5-2h6l1.5 2h2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.5"/>',
    image: '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M4 17l5-5 4 4 2.5-2.5L20 18"/>',
    sparkle: '<path d="M11 3.5l1.7 4.8 4.8 1.7-4.8 1.7L11 16.5l-1.7-4.8L4.5 10l4.8-1.7z"/><path d="M18 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
    pin: '<path d="M9 4h6l-1 5 3 3v2H7v-2l3-3z"/><path d="M12 14v6"/>',
    trash: '<path d="M5 7h14M10 4h4M7 7l1 12.5h8L17 7"/><path d="M10.5 11v5M13.5 11v5"/>',
    download: '<path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/>',
    refresh: '<path d="M19 12a7 7 0 1 1-2.05-4.95M19 4v4.5h-4.5"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    ok: '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.3l2.8 2.8 5.4-5.5"/>',
    alert: '<path d="M10.3 4.9L3.4 17a2 2 0 0 0 1.7 3h13.8a2 2 0 0 0 1.7-3L13.7 4.9a2 2 0 0 0-3.4 0z"/><path d="M12 10v4M12 17v.01"/>',
    lock: '<rect x="5" y="10.5" width="14" height="9.5" rx="2.5"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
    shield: '<path d="M12 3.5l7 2.8v5.2c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6.3z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
    map: '<path d="M9 5L4 7v12l5-2 6 2 5-2V5l-5 2z"/><path d="M9 5v12M15 7v12"/>',
    place: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.4"/>',
    cube: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
    nodes: '<circle cx="12" cy="5.5" r="2.5"/><circle cx="5.5" cy="18" r="2.5"/><circle cx="18.5" cy="18" r="2.5"/><path d="M11 7.8l-4.4 8M13 7.8l4.4 8M8 18h8"/>',
    layers: '<path d="M12 4l8.5 4.5L12 13 3.5 8.5z"/><path d="M3.5 12.5L12 17l8.5-4.5M3.5 16.5L12 21l8.5-4.5"/>',
    palette: '<path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.2 0 1.8-.9 1.4-2l-.3-.8c-.4-1.1.4-2.2 1.6-2.2H17a3.5 3.5 0 0 0 3.5-3.5c0-4.7-3.8-8.5-8.5-8.5z"/><circle cx="8" cy="11" r="1"/><circle cx="11" cy="7.5" r="1"/><circle cx="15.5" cy="8.5" r="1"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    moon: '<path d="M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10z"/>',
    cloud: '<path d="M7.5 18.5H17a4 4 0 0 0 .4-8A5.5 5.5 0 0 0 6.9 9.4a4.6 4.6 0 0 0 .6 9.1z"/>',
    partly: '<path d="M8 3.8V5M3.3 8.5h1.2M4.6 5.1l.9.9M11.4 5.1l-.9.9"/><path d="M5.6 11.3A3.2 3.2 0 1 1 10.9 8"/><path d="M9.5 19.5h8a3.5 3.5 0 0 0 .3-7 4.8 4.8 0 0 0-9.2-.5 4 4 0 0 0 .9 7.5z"/>',
    rain: '<path d="M7.5 14.5H17a3.6 3.6 0 0 0 .3-7.2A5 5 0 0 0 7.4 6.5a4 4 0 0 0 .1 8z"/><path d="M8.5 17.5l-1 2.5M12.5 17.5l-1 2.5M16.5 17.5l-1 2.5"/>',
    snow: '<path d="M7.5 14.5H17a3.6 3.6 0 0 0 .3-7.2A5 5 0 0 0 7.4 6.5a4 4 0 0 0 .1 8z"/><path d="M8 18.2v.01M12 19.6v.01M16 18.2v.01M10 21.3v.01M14 21.3v.01"/>',
    storm: '<path d="M7.5 14.5H17a3.6 3.6 0 0 0 .3-7.2A5 5 0 0 0 7.4 6.5a4 4 0 0 0 .1 8z"/><path d="M12.8 15.5l-2.3 3.4h3L11.2 22"/>',
    fog: '<path d="M4 9h16M6 13h12M4 17h16"/>',
    drop: '<path d="M12 3.5s6 6.4 6 10.5a6 6 0 0 1-12 0c0-4.1 6-10.5 6-10.5z"/>',
    thermo: '<path d="M10 13.5V5a2 2 0 0 1 4 0v8.5a4 4 0 1 1-4 0z"/><path d="M12 9v6.5"/>',
    wind: '<path d="M3 9h11a3 3 0 1 0-3-3M3 15h15a3 3 0 1 1-3 3"/>',
    alarm: '<circle cx="12" cy="13" r="7"/><path d="M12 9.5V13l2.5 2M4.5 5.5l3-2.5M19.5 5.5l-3-2.5"/>',
    timer: '<circle cx="12" cy="13.5" r="7"/><path d="M12 13.5l3-3M10 3h4"/>',
    phone: '<path d="M6.6 4h2.6l1.5 4-2 1.3a10.5 10.5 0 0 0 6 6l1.3-2 4 1.5v2.6A2 2 0 0 1 18 19.5C10.9 19.5 4.5 13.1 4.5 6A2 2 0 0 1 6.6 4z"/>',
    message: '<path d="M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v8.5a1.5 1.5 0 0 1-1.5 1.5h-9l-4.5 3.5V17H5a1.5 1.5 0 0 1-1.5-1.5V7A1.5 1.5 0 0 1 5 5.5z"/>',
    apps: '<rect x="4" y="4" width="6.5" height="6.5" rx="2"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="2"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="2"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="2"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    flashlight: '<path d="M8 3.5h8v3l-2 3.5v10.5h-4V10L8 6.5z"/><path d="M12 13.5v2"/>',
    volume: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
    calendar: '<rect x="4" y="5.5" width="16" height="14.5" rx="3"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
    music: '<path d="M9 17.5V6l10-2v11.5"/><circle cx="6.5" cy="17.5" r="2.5"/><circle cx="16.5" cy="15.5" r="2.5"/>',
    play: '<path d="M8 5.5v13l10.5-6.5z"/>',
    pause: '<path d="M8.5 5.5v13M15.5 5.5v13"/>',
    next: '<path d="M6 6v12l9-6zM18 6v12"/>',
    prev: '<path d="M18 6v12l-9-6zM6 6v12"/>',
    bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    offline: '<path d="M4 4l16 16"/><path d="M8.5 16a5 5 0 0 1 7 0M5 12.5a10 10 0 0 1 4-2.4M19 12.5a10 10 0 0 0-3.2-2.1M2 9a14 14 0 0 1 4.5-2.9M22 9a14 14 0 0 0-11-3.8M12 19.5v.01"/>',
    wifi: '<path d="M2 9a14.5 14.5 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 19.5v.01"/>',
    chip: '<rect x="6.5" y="6.5" width="11" height="11" rx="2.5"/><path d="M10 10h4v4h-4zM9 3.5v3M15 3.5v3M9 17.5v3M15 17.5v3M3.5 9h3M3.5 15h3M17.5 9h3M17.5 15h3"/>',
    bolt: '<path d="M13 3L5.5 13.5H11L10 21l7.5-10.5H12z"/>',
    mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2.5"/><path d="M4 7l8 6 8-6"/>',
    user: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
    tool: '<path d="M14.7 6.3a4 4 0 0 0 5 5l-9.3 9.3a2.1 2.1 0 0 1-3-3z"/><path d="M14.7 6.3l2-2 3 3-2 2"/>',
    euro: '<path d="M17.5 6.5a6.5 6.5 0 1 0 0 11M5 10.5h8M5 13.5h8"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    bulb: '<path d="M9 17.5h6M10 20.5h4M8.5 14.5a6 6 0 1 1 7 0c-.8.6-1 1.4-1 3h-5c0-1.6-.2-2.4-1-3z"/>',
    book: '<path d="M5 5.5A2 2 0 0 1 7 3.5h12V18H7a2 2 0 0 0-2 2z"/><path d="M5 20a2 2 0 0 0 2 1.5h12"/>',
    flag: '<path d="M5.5 21V4M5.5 4.5h11l-2 4 2 4h-11"/>',
    diamond: '<path d="M12 3.5l8.5 8.5-8.5 8.5L3.5 12z"/>',
    dot: '<circle cx="12" cy="12" r="3"/>',
    right: '<path d="M9.5 6l6 6-6 6"/>',
    left: '<path d="M14.5 6l-6 6 6 6"/>',
    down: '<path d="M6 9.5l6 6 6-6"/>',
    more: '<circle cx="5.5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="18.5" cy="12" r="1.4"/>',
    headset: '<path d="M4.5 14v-2a7.5 7.5 0 0 1 15 0v2"/><rect x="3.5" y="13.5" width="4" height="6" rx="1.8"/><rect x="16.5" y="13.5" width="4" height="6" rx="1.8"/>',
    news: '<rect x="4" y="4.5" width="13" height="15" rx="2"/><path d="M17 8.5h2.5V18a1.5 1.5 0 0 1-3 0M7.5 8.5h6M7.5 12h6M7.5 15.5h4"/>',
    learn: '<path d="M2.5 9.5L12 5l9.5 4.5L12 14z"/><path d="M6.5 11.5v4c2.5 2 8.5 2 11 0v-4M21.5 9.5v5"/>',
    battery: '<rect x="3" y="7.5" width="16" height="9" rx="2.5"/><path d="M21 10.5v3M6.5 10.5v3M9.5 10.5v3"/>',
    ear: '<path d="M7 9a5 5 0 0 1 10 0c0 3-3 3.5-3 6.5a2.5 2.5 0 0 1-5 0"/><path d="M10 9.5a2 2 0 0 1 4 0"/>',
    save: '<path d="M5 4.5h11l3.5 3.5v10A1.5 1.5 0 0 1 18 19.5H6A1.5 1.5 0 0 1 4.5 18V6A1.5 1.5 0 0 1 5 4.5z"/><path d="M8 4.5v4h7v-4M8 19.5v-6h8v6"/>',
    hangup: '<path d="M3.5 13.5c4.7-4 12.3-4 17 0l-1.6 2.6-3.6-1.1v-2.4a12 12 0 0 0-6.6 0V15l-3.6 1.1z"/>',
    orbit: '<circle cx="12" cy="12" r="2.6"/><ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(-28 12 12)"/>',
  };
  const FILL = new Set(["play", "stop", "more", "next", "prev"]);

  function svg(name, cls) {
    const s = document.createElementNS(NS, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("class", "ic" + (FILL.has(name) ? " ic-fill" : "") + (cls ? " " + cls : ""));
    s.innerHTML = P[name] || P.diamond; // dessins fixes ci-dessus uniquement
    return s;
  }

  /** Icône + texte dans un élément (le texte passe par textContent). */
  function set(el, name, text) {
    const span = document.createElement("span");
    span.textContent = text == null ? "" : String(text);
    el.replaceChildren(svg(name), span);
    return el;
  }

  function hydrate(root) {
    (root || document).querySelectorAll("[data-icon]").forEach((el) => {
      if (el.querySelector(":scope > svg.ic")) return;
      el.prepend(svg(el.dataset.icon));
    });
  }

  // Dessin sur canvas : on relit les formes du jeu d'icônes (path, circle, rect, ellipse).
  const cache = new Map();
  function shapes(name) {
    if (cache.has(name)) return cache.get(name);
    const s = svg(name);
    const list = [];
    for (const c of s.children) {
      const a = (k) => parseFloat(c.getAttribute(k) || "0");
      const p = new Path2D();
      if (c.tagName === "path") { list.push(new Path2D(c.getAttribute("d"))); continue; }
      if (c.tagName === "circle") p.arc(a("cx"), a("cy"), a("r"), 0, Math.PI * 2);
      else if (c.tagName === "rect") {
        const x = a("x"), y = a("y"), w = a("width"), h = a("height"), r = Math.min(a("rx"), w / 2, h / 2);
        p.moveTo(x + r, y); p.arcTo(x + w, y, x + w, y + h, r); p.arcTo(x + w, y + h, x, y + h, r);
        p.arcTo(x, y + h, x, y, r); p.arcTo(x, y, x + w, y, r); p.closePath();
      } else if (c.tagName === "ellipse") {
        const m = /rotate\(([-\d.]+)/.exec(c.getAttribute("transform") || "");
        p.ellipse(a("cx"), a("cy"), a("rx"), a("ry"), m ? (parseFloat(m[1]) * Math.PI) / 180 : 0, 0, Math.PI * 2);
      }
      list.push(p);
    }
    cache.set(name, { list, fill: FILL.has(name) });
    return cache.get(name);
  }
  function draw(ctx, name, cx, cy, size, color, width) {
    const sh = shapes(P[name] ? name : "diamond");
    const k = size / 24;
    ctx.save();
    ctx.translate(cx - size / 2, cy - size / 2);
    ctx.scale(k, k);
    ctx.lineWidth = (width || 1.8) / k * k; // épaisseur dans la grille 24
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.strokeStyle = color; ctx.fillStyle = color;
    sh.list.forEach((p) => { if (sh.fill) ctx.fill(p); else ctx.stroke(p); });
    ctx.restore();
  }

  window.SyriusIcons = { svg, set, hydrate, draw, has: (n) => n in P };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => hydrate(document));
  else hydrate(document);
})();
