// Visages animés de Nova et d'Aurora (style pixel) pour le mode conversation.
// Chaque visage cligne des yeux, bouge la bouche quand il parle, regarde en l'air quand il réfléchit
// et change d'expression selon ce que l'IA ressent (« [rieur] », « [sceptique] »… au début de sa réponse).
// Dessin en SVG construit élément par élément avec le DOM, grille de 20 × 20 pixels.
"use strict";

(function () {
  const NS = "http://www.w3.org/2000/svg";
  const N = 20, C = 9.5;
  const EXPRESSIONS = ["neutre", "content", "rieur", "pensif", "surpris", "sceptique", "inquiet", "fier"];
  // Repère les expressions au début d'une réponse : « [rieur] Ha ! … »
  const TAG = new RegExp("^\\s*\\[(" + EXPRESSIONS.join("|") + ")\\]\\s*", "i");

  const ring = [];
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const d = Math.hypot(x - C, y - C);
    if (d >= 8.2 && d < 9.3) ring.push([x, y]);
  }
  const rect = (x0, y0, w, h) => { const o = []; for (let y = y0; y < y0 + h; y++) for (let x = x0; x < x0 + w; x++) o.push([x, y]); return o; };
  const pts = (list) => list.map(([x, y]) => [x, y]);

  // Yeux : ouverts, fermés (clignement), en l'air (réflexion), grands (surprise), plissés (rire)
  const EYES = {
    open: [...rect(6, 6, 2, 4), ...rect(12, 6, 2, 4)],
    closed: [...rect(6, 8, 2, 1), ...rect(12, 8, 2, 1)],
    up: [...rect(6, 5, 2, 3), ...rect(12, 5, 2, 3)],
    big: [...rect(5, 5, 3, 5), ...rect(12, 5, 3, 5)],
    happy: pts([[5, 8], [6, 7], [7, 7], [8, 8], [11, 8], [12, 7], [13, 7], [14, 8]]),
    wink: [...rect(6, 6, 2, 4), ...pts([[11, 8], [12, 8], [13, 8], [14, 8]])],
    skeptic: [...rect(6, 6, 2, 4), ...rect(12, 8, 2, 2), ...pts([[11, 5], [12, 4], [13, 4], [14, 5]])],
    worried: [...rect(6, 7, 2, 3), ...rect(12, 7, 2, 3), ...pts([[5, 5], [6, 5], [7, 6], [12, 6], [13, 5], [14, 5]])],
  };
  // Bouches
  const MOUTH = {
    smile: pts([[5, 12], [6, 13], [7, 14], [8, 14], [9, 14], [10, 14], [11, 14], [12, 14], [13, 13], [14, 12]]),
    grin: [...pts([[4, 11], [5, 12], [6, 13], [7, 14], [12, 14], [13, 13], [14, 12], [15, 11]]), ...rect(5, 11, 10, 1),
      ...rect(8, 15, 4, 1), ...pts([[6, 12], [13, 12], [7, 13], [12, 13]])],
    flat: rect(7, 14, 6, 1),
    small: rect(8, 14, 4, 1),
    side: pts([[9, 14], [10, 14], [11, 14], [12, 13], [13, 13]]),
    o: [...rect(8, 12, 4, 1), ...rect(8, 15, 4, 1), ...pts([[7, 13], [7, 14], [12, 13], [12, 14]])],
    frown: pts([[6, 15], [7, 14], [8, 13], [9, 13], [10, 13], [11, 13], [12, 14], [13, 15]]),
    proud: pts([[6, 13], [7, 14], [8, 14], [9, 14], [10, 14], [11, 14], [12, 13], [13, 12], [14, 11]]),
    talk: [...rect(8, 12, 4, 1), ...rect(8, 15, 4, 1), ...pts([[7, 13], [7, 14], [12, 13], [12, 14]])],
    talk2: [...rect(7, 13, 6, 1), ...rect(8, 14, 4, 1)],
  };
  const LOOK = {
    neutre: ["open", "flat"], content: ["open", "smile"], rieur: ["happy", "grin"], pensif: ["up", "side"],
    surpris: ["big", "o"], sceptique: ["skeptic", "side"], inquiet: ["worried", "frown"], fier: ["wink", "proud"],
  };

  const faces = {};

  function make(who, name) {
    const wrap = document.createElement("div");
    wrap.className = "face face-" + who;
    wrap.dataset.who = who;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `-1 -1 ${N + 2} ${N + 2}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Visage de " + name);
    const bg = document.createElementNS(NS, "rect");
    bg.setAttribute("x", "-1"); bg.setAttribute("y", "-1"); bg.setAttribute("width", N + 2); bg.setAttribute("height", N + 2);
    bg.setAttribute("rx", "4"); bg.setAttribute("class", "face-bg");
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", "face-px");
    svg.append(bg, g);
    const label = document.createElement("div");
    label.className = "face-name";
    label.textContent = name;
    wrap.append(svg, label);
    const f = { who, wrap, g, expr: "content", mode: "idle", blink: false, mouthAlt: false, timer: null };
    faces[who] = f;
    draw(f);
    schedule(f);
    return wrap;
  }

  function draw(f) {
    let [eyes, mouth] = LOOK[f.expr] || LOOK.content;
    if (f.mode === "think") { eyes = "up"; mouth = "side"; }
    if (f.mode === "listen" && f.expr === "neutre") mouth = "small";
    if (f.mode === "talk") mouth = f.mouthAlt ? "talk" : "talk2";
    if (f.blink && eyes !== "happy") eyes = "closed";
    const cells = [...ring, ...EYES[eyes], ...MOUTH[mouth]];
    const seen = new Set();
    const frag = document.createDocumentFragment();
    for (const [x, y] of cells) {
      const k = x * 100 + y;
      if (seen.has(k)) continue;
      seen.add(k);
      const r = document.createElementNS(NS, "rect");
      r.setAttribute("x", x + 0.08); r.setAttribute("y", y + 0.08);
      r.setAttribute("width", "0.84"); r.setAttribute("height", "0.84");
      frag.appendChild(r);
    }
    f.g.replaceChildren(frag);
    f.wrap.dataset.mode = f.mode;
  }

  // Petite vie : clignement de temps en temps, bouche qui bouge en parlant.
  function schedule(f) {
    clearTimeout(f.timer);
    const step = () => {
      if (!f.wrap.isConnected) { f.timer = setTimeout(step, 1500); return; }
      if (f.mode === "talk") { f.mouthAlt = !f.mouthAlt; draw(f); f.timer = setTimeout(step, 140 + Math.random() * 90); return; }
      f.blink = true; draw(f);
      setTimeout(() => { f.blink = false; draw(f); }, 130);
      f.timer = setTimeout(step, 2200 + Math.random() * 2600);
    };
    f.timer = setTimeout(step, 1200 + Math.random() * 1500);
  }

  function set(who, { expr, mode } = {}) {
    const f = faces[who];
    if (!f) return;
    if (expr && LOOK[expr]) f.expr = expr;
    if (mode) { f.mode = mode; schedule(f); }
    draw(f);
  }

  // « [rieur] Ha ! » → { expr: "rieur", text: "Ha !" }
  function split(text) {
    const m = TAG.exec(String(text || ""));
    return m ? { expr: m[1].toLowerCase(), text: String(text).slice(m[0].length) } : { expr: "", text: String(text || "") };
  }

  window.SyriusFaces = { make, set, split, EXPRESSIONS };
})();
