// Schémas d'idées en 3D (hologramme) : dessinés sur un <canvas>, sans bibliothèque externe.
// Le texte est dessiné avec fillText (jamais inséré comme HTML).
// Gestes : glisser = tourner, pincer / molette = zoomer, toucher une idée = voir son détail.
"use strict";

(function () {
  const COLORS = ["#38d9ff", "#7cf3c8", "#ffd166", "#ff8fab", "#b69cff", "#6fb3ff", "#9ef06c", "#ffa36c"];
  let st = null;   // état du schéma affiché
  let raf = 0;

  // ------------------------------------------------------------------ mise en place 3D
  function v(x, y, z) { return { x, y, z }; }
  function add(a, b) { return v(a.x + b.x, a.y + b.y, a.z + b.z); }
  function sub(a, b) { return v(a.x - b.x, a.y - b.y, a.z - b.z); }
  function mul(a, k) { return v(a.x * k, a.y * k, a.z * k); }
  function len(a) { return Math.hypot(a.x, a.y, a.z) || 1e-6; }
  function norm(a) { return mul(a, 1 / len(a)); }

  function rng(seed) { // pseudo-aléatoire déterministe : même schéma = même forme
    let s = seed >>> 0 || 1;
    return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  }

  function buildGraph(d) {
    const steps = d.style === "etapes";
    const nodes = d.nodes.map((n) => ({ ...n, children: [], depth: 0, pos: v(0, 0, 0), vel: v(0, 0, 0) }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const root = nodes.find((n) => !n.parent) || nodes[0];
    nodes.forEach((n) => { if (n !== root && byId.has(n.parent)) byId.get(n.parent).children.push(n); });
    const order = [root];
    for (let i = 0; i < order.length; i++) {
      order[i].children.forEach((c) => { c.depth = order[i].depth + 1; order.push(c); });
    }
    nodes.forEach((n) => { if (!order.includes(n)) { n.depth = 1; root.children.push(n); order.push(n); } });
    // Couleur : chaque branche principale a sa couleur.
    root.color = "#e9fbff";
    root.children.forEach((c, i) => {
      const paint = (n) => { n.color = COLORS[i % COLORS.length]; n.children.forEach(paint); };
      paint(c);
    });
    const edges = [];
    if (steps) { // processus : chaque étape mène à la suivante
      nodes.slice(1).forEach((n, i) => edges.push({ a: nodes[i], b: n, tree: true }));
    } else {
      nodes.forEach((n) => { if (n !== root && byId.has(n.parent)) edges.push({ a: byId.get(n.parent), b: n, tree: true }); });
    }
    (d.links || []).forEach((l) => {
      if (byId.has(l.from) && byId.has(l.to)) edges.push({ a: byId.get(l.from), b: byId.get(l.to), label: l.label || "" });
    });
    return { nodes, root, edges, order };
  }

  function layout(g, style, seedText) {
    let seed = 7;
    for (const ch of seedText) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
    const rand = rng(seed);
    const n = g.nodes.length;
    if (style === "etapes") { // spirale montante, dans l'ordre donné
      const steps = g.nodes;
      steps.forEach((node, i) => {
        const a = i * 1.15;
        node.pos = v(Math.cos(a) * 150, (i - (steps.length - 1) / 2) * 62, Math.sin(a) * 150);
      });
      return;
    }
    if (style === "arbre") { // niveaux superposés, chaque niveau en cercle
      const levels = [];
      g.order.forEach((node) => { (levels[node.depth] = levels[node.depth] || []).push(node); });
      levels.forEach((lv, d) => {
        lv.forEach((node, i) => {
          const a = (i / lv.length) * Math.PI * 2 + d * 0.6;
          const r = d === 0 ? 0 : 70 + d * 70;
          node.pos = v(Math.cos(a) * r, 150 - d * 115, Math.sin(a) * r);
        });
      });
      return;
    }
    // Carte mentale : départ en étoile autour de l'idée centrale, puis relaxation par ressorts.
    g.root.pos = v(0, 0, 0);
    const golden = Math.PI * (3 - Math.sqrt(5));
    const k = g.root.children.length;
    g.root.children.forEach((c, i) => {
      const y = k === 1 ? 0 : 1 - (i / (k - 1)) * 2;
      const r = Math.sqrt(Math.max(0, 1 - y * y));
      const dir = v(Math.cos(i * golden) * r, y * 0.75, Math.sin(i * golden) * r);
      const place = (node, base, d) => {
        node.pos = add(base, mul(norm(add(dir, v(rand() - 0.5, rand() - 0.5, rand() - 0.5))), 120));
        node.children.forEach((cc) => place(cc, node.pos, d + 1));
      };
      place(c, g.root.pos, 1);
    });
    for (let it = 0; it < 260; it++) {
      const f = g.nodes.map(() => v(0, 0, 0));
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const dvec = sub(g.nodes[i].pos, g.nodes[j].pos);
          const dist = Math.max(len(dvec), 20);
          const push = mul(norm(dvec), 9000 / (dist * dist));
          f[i] = add(f[i], push);
          f[j] = sub(f[j], push);
        }
      }
      g.edges.forEach((e) => {
        const ia = g.nodes.indexOf(e.a), ib = g.nodes.indexOf(e.b);
        const dvec = sub(e.b.pos, e.a.pos);
        const want = e.tree ? (e.a === g.root ? 150 : 105) : 170;
        const pull = mul(norm(dvec), (len(dvec) - want) * (e.tree ? 0.06 : 0.015));
        f[ia] = add(f[ia], pull);
        f[ib] = sub(f[ib], pull);
      });
      g.nodes.forEach((node, i) => {
        if (node === g.root) return;
        node.pos = add(node.pos, mul(f[i], 0.9));
      });
    }
  }

  // ------------------------------------------------------------------ dessin
  function project(p, cam, w, h) {
    const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw), cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
    const x1 = p.x * cy - p.z * sy, z1 = p.x * sy + p.z * cy;
    const y2 = p.y * cp - z1 * sp, z2 = p.y * sp + z1 * cp;
    const dist = 620 / cam.zoom;
    const s = 560 / (dist + z2);
    return { x: w / 2 + x1 * s * (Math.min(w, h) / 420), y: h / 2 - y2 * s * (Math.min(w, h) / 420), s, z: z2 };
  }

  function wrap(ctx, text, maxW) {
    const words = text.split(" ");
    const lines = [];
    let cur = "";
    words.forEach((wd) => {
      const t = cur ? cur + " " + wd : wd;
      if (ctx.measureText(t).width > maxW && cur) { lines.push(cur); cur = wd; } else cur = t;
    });
    if (cur) lines.push(cur);
    return lines.slice(0, 3);
  }

  function draw(t) {
    if (!st) return;
    const { ctx, canvas, g, cam } = st;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (st.spin) cam.yaw += 0.0035;

    // Plateau holographique (anneaux au sol).
    ctx.lineWidth = 1;
    for (let r = 1; r <= 3; r++) {
      ctx.beginPath();
      for (let a = 0; a <= 64; a++) {
        const ang = (a / 64) * Math.PI * 2;
        const p = project(v(Math.cos(ang) * r * 90, -230, Math.sin(ang) * r * 90), cam, w, h);
        if (a) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y);
      }
      ctx.strokeStyle = `rgba(56,217,255,${0.22 - r * 0.05})`;
      ctx.stroke();
    }

    const P = new Map(st.g.nodes.map((n) => [n, project(n.pos, cam, w, h)]));
    const pulse = (Math.sin(t / 500) + 1) / 2;

    // Liens (du plus loin au plus proche).
    const edges = g.edges.slice().sort((a, b) => (P.get(b.a).z + P.get(b.b).z) - (P.get(a.a).z + P.get(a.b).z));
    edges.forEach((e) => {
      const a = P.get(e.a), b = P.get(e.b);
      const depth = Math.max(0.25, Math.min(1, 1.4 - (a.z + b.z) / 900));
      ctx.strokeStyle = e.tree ? e.b.color : "rgba(255,255,255,.7)";
      ctx.globalAlpha = (e.tree ? 0.55 : 0.4) * depth;
      ctx.lineWidth = e.tree ? 2 : 1.2;
      ctx.setLineDash(e.tree ? [] : [5, 5]);
      ctx.shadowColor = ctx.strokeStyle; ctx.shadowBlur = 8;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      if (e.label) {
        ctx.setLineDash([]); ctx.shadowBlur = 0; ctx.globalAlpha = 0.8 * depth;
        ctx.font = "11px system-ui, sans-serif"; ctx.fillStyle = "#cfefff"; ctx.textAlign = "center";
        ctx.fillText(e.label, (a.x + b.x) / 2, (a.y + b.y) / 2 - 4);
      }
    });
    ctx.setLineDash([]); ctx.globalAlpha = 1; ctx.shadowBlur = 0;

    // Idées (sphères lumineuses + texte).
    st.hits = [];
    const nodes = g.nodes.slice().sort((a, b) => P.get(b).z - P.get(a).z);
    nodes.forEach((n) => {
      const p = P.get(n);
      const isRoot = n === g.root, sel = n === st.selected;
      const r = Math.max(4, (isRoot ? 15 : n.depth === 1 ? 10 : 7) * p.s * 1.1) * (sel ? 1.25 + pulse * 0.15 : 1);
      const depth = Math.max(0.35, Math.min(1, 1.3 - p.z / 700));
      ctx.globalAlpha = depth;
      const grad = ctx.createRadialGradient(p.x - r / 3, p.y - r / 3, r / 6, p.x, p.y, r);
      grad.addColorStop(0, "#ffffff"); grad.addColorStop(0.35, n.color); grad.addColorStop(1, "rgba(3,10,20,.2)");
      ctx.shadowColor = n.color; ctx.shadowBlur = isRoot ? 28 : 16;
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;
      if (isRoot || sel) {
        ctx.strokeStyle = n.color; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(p.x, p.y, r + 6 + pulse * 4, 0, Math.PI * 2); ctx.stroke();
      }
      const fs = Math.max(10, Math.min(16, (isRoot ? 15 : 12) * p.s * 1.05));
      ctx.font = `${isRoot ? 700 : 600} ${fs}px system-ui, sans-serif`;
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      const lines = wrap(ctx, n.label, isRoot ? 150 : 120);
      lines.forEach((ln, i) => {
        const y = p.y + r + 5 + i * (fs + 2);
        ctx.lineWidth = 3; ctx.strokeStyle = "rgba(3,10,20,.85)"; ctx.strokeText(ln, p.x, y);
        ctx.fillStyle = isRoot ? "#ffffff" : "#d8f6ff"; ctx.fillText(ln, p.x, y);
      });
      st.hits.push({ n, x: p.x, y: p.y + (lines.length * (fs + 2)) / 2, r: Math.max(r, 18) + 10 });
    });
    ctx.globalAlpha = 1;
    raf = requestAnimationFrame(draw);
  }

  // ------------------------------------------------------------------ gestes
  function select(n) {
    st.selected = n;
    const box = document.getElementById("holo-detail");
    box.replaceChildren();
    if (!n) { box.classList.add("hidden"); return; }
    const t = document.createElement("strong");
    t.textContent = n.label;
    box.append(t);
    if (n.note) {
      const p = document.createElement("span");
      p.textContent = " — " + n.note;
      box.append(p);
    }
    box.classList.remove("hidden");
  }

  function bindGestures(canvas) {
    const pts = new Map();
    let moved = false, pinch0 = 0, zoom0 = 1;
    canvas.addEventListener("pointerdown", (e) => {
      canvas.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      moved = false; st.spin = false;
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        pinch0 = Math.hypot(a.x - b.x, a.y - b.y); zoom0 = st.cam.zoom;
      }
    });
    canvas.addEventListener("pointermove", (e) => {
      const prev = pts.get(e.pointerId);
      if (!prev) return;
      const cur = { x: e.clientX, y: e.clientY };
      pts.set(e.pointerId, cur);
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch0) st.cam.zoom = Math.max(0.5, Math.min(2.6, zoom0 * d / pinch0));
        moved = true;
        return;
      }
      const dx = cur.x - prev.x, dy = cur.y - prev.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      st.cam.yaw += dx * 0.008;
      st.cam.pitch = Math.max(-1.2, Math.min(1.2, st.cam.pitch + dy * 0.006));
    });
    const up = (e) => {
      pts.delete(e.pointerId);
      if (pts.size < 2) pinch0 = 0;
      if (!moved && pts.size === 0) {
        const r = canvas.getBoundingClientRect();
        const x = e.clientX - r.left, y = e.clientY - r.top;
        let best = null, bd = Infinity;
        (st.hits || []).forEach((h) => {
          const d = Math.hypot(h.x - x, h.y - y);
          if (d < h.r && d < bd) { best = h.n; bd = d; }
        });
        select(best);
      }
    };
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      st.spin = false;
      st.cam.zoom = Math.max(0.5, Math.min(2.6, st.cam.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
    }, { passive: false });
  }

  // ------------------------------------------------------------------ ouverture / fermeture
  function close() {
    cancelAnimationFrame(raf);
    raf = 0;
    st = null;
    document.getElementById("holo").classList.add("hidden");
  }

  function show(d) {
    if (!d || !Array.isArray(d.nodes) || d.nodes.length < 2) return;
    const holo = document.getElementById("holo");
    holo.classList.remove("hidden");
    document.getElementById("holo-title").textContent = String(d.title || "").slice(0, 80);
    const canvas = document.getElementById("holo-canvas");
    const g = buildGraph(d);
    layout(g, d.style, String(d.title || ""));
    // Centre le schéma sur l'origine.
    const c = g.nodes.reduce((acc, n) => add(acc, n.pos), v(0, 0, 0));
    const center = mul(c, 1 / g.nodes.length);
    g.nodes.forEach((n) => { n.pos = sub(n.pos, center); });
    const radius = Math.max(...g.nodes.map((n) => len(n.pos)), 120);
    cancelAnimationFrame(raf);
    st = { canvas, ctx: canvas.getContext("2d"), g, selected: null, hits: [], spin: true,
      cam: { yaw: 0.6, pitch: 0.35, zoom: Math.max(0.45, Math.min(1.2, 185 / radius)) } };
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) st.spin = false;
    select(null);
    if (!canvas.dataset.bound) { bindGestures(canvas); canvas.dataset.bound = "1"; }
    raf = requestAnimationFrame(draw);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("holo-close").addEventListener("click", close);
    document.getElementById("holo-spin").addEventListener("click", () => { if (st) st.spin = !st.spin; });
  });

  window.SyriusHolo = { show, close };
})();
