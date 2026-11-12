// Hologramme de Syrius : plan d'action en 3D dessiné sur un <canvas>, sans bibliothèque externe.
// Le texte est dessiné avec fillText ou inséré avec textContent (jamais comme du HTML).
// Gestes : glisser = tourner, pincer / molette = zoomer, toucher une idée = voir son détail.
"use strict";

(function () {
  const COLORS = ["#38d9ff", "#7cf3c8", "#ffd166", "#ff8fab", "#b69cff", "#6fb3ff", "#9ef06c", "#ffa36c"];
  const ICONS = { objectif: "🎯", phase: "◆", etape: "▸", action: "✔", outil: "🛠", budget: "€", delai: "⏱",
    risque: "⚠", idee: "💡", ressource: "📚", personne: "👤" };
  const INTRO_MS = 1400;
  let st = null;
  let raf = 0;

  // ------------------------------------------------------------------ vecteurs
  const v = (x, y, z) => ({ x, y, z });
  const add = (a, b) => v(a.x + b.x, a.y + b.y, a.z + b.z);
  const sub = (a, b) => v(a.x - b.x, a.y - b.y, a.z - b.z);
  const mul = (a, k) => v(a.x * k, a.y * k, a.z * k);
  const len = (a) => Math.hypot(a.x, a.y, a.z) || 1e-6;
  const norm = (a) => mul(a, 1 / len(a));
  const lerp = (a, b, k) => add(a, mul(sub(b, a), k));

  function rng(seed) { // pseudo-aléatoire déterministe : même schéma = même forme
    let s = seed >>> 0 || 1;
    return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  }

  function rgba(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  // ------------------------------------------------------------------ graphe + numérotation
  function buildGraph(d) {
    const steps = d.style === "etapes";
    const nodes = d.nodes.map((n) => ({ ...n, children: [], depth: 0, pos: v(0, 0, 0), num: "" }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const root = nodes.find((n) => !n.parent) || nodes[0];
    nodes.forEach((n) => { if (n !== root && byId.has(n.parent)) byId.get(n.parent).children.push(n); });
    const order = [root];
    for (let i = 0; i < order.length; i++) {
      order[i].children.forEach((c) => { c.depth = order[i].depth + 1; order.push(c); });
    }
    nodes.forEach((n) => { if (!order.includes(n)) { n.depth = 1; root.children.push(n); order.push(n); } });

    root.color = "#e9fbff";
    if (steps) {
      nodes.filter((n) => n !== root).forEach((n, i) => { n.num = String(i + 1); n.color = COLORS[i % COLORS.length]; });
    } else {
      const number = (n, prefix) => n.children.forEach((c, i) => {
        c.num = prefix ? `${prefix}.${i + 1}` : String(i + 1);
        number(c, c.num);
      });
      number(root, "");
      root.children.forEach((c, i) => {
        const paint = (n) => { n.color = COLORS[i % COLORS.length]; n.children.forEach(paint); };
        paint(c);
      });
    }
    const edges = [];
    if (steps) {
      const seq = [root, ...nodes.filter((n) => n !== root)];
      seq.slice(1).forEach((n, i) => edges.push({ a: seq[i], b: n, tree: true }));
    } else {
      nodes.forEach((n) => { if (n !== root && byId.has(n.parent)) edges.push({ a: byId.get(n.parent), b: n, tree: true }); });
    }
    (d.links || []).forEach((l) => {
      if (byId.has(l.from) && byId.has(l.to)) edges.push({ a: byId.get(l.from), b: byId.get(l.to), label: l.label || "" });
    });
    return { nodes, root, edges, order, steps };
  }

  // ------------------------------------------------------------------ disposition 3D
  function layout(g, style, seedText) {
    let seed = 7;
    for (const ch of seedText) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
    const rand = rng(seed);
    if (style === "etapes") { // spirale montante : on suit le chemin du bas vers le haut
      const seq = [g.root, ...g.nodes.filter((n) => n !== g.root)];
      seq.forEach((node, i) => {
        const a = i * 0.95;
        node.pos = v(Math.cos(a) * 200, (i - (seq.length - 1) / 2) * 60, Math.sin(a) * 200);
      });
      return;
    }
    if (style === "arbre") { // étages superposés, chaque étage en cercle
      const levels = [];
      g.order.forEach((node) => { (levels[node.depth] = levels[node.depth] || []).push(node); });
      levels.forEach((lv, d) => {
        lv.forEach((node, i) => {
          const a = (i / lv.length) * Math.PI * 2 + d * 0.5;
          const r = d === 0 ? 0 : 90 + d * 95;
          node.pos = v(Math.cos(a) * r, 170 - d * 140, Math.sin(a) * r);
        });
      });
      return;
    }
    // Plan : les phases tournent autour de l'objectif dans l'ordre (comme une horloge),
    // leurs étapes s'éloignent vers l'extérieur ; puis relaxation pour éviter les chevauchements.
    g.root.pos = v(0, 0, 0);
    const k = g.root.children.length;
    g.root.children.forEach((c, i) => {
      const a = (i / Math.max(k, 1)) * Math.PI * 2 - Math.PI / 2;
      const dir = v(Math.cos(a), (i % 2 ? 0.28 : -0.28), Math.sin(a));
      c.pos = mul(norm(dir), 235);
      const spread = c.children.length;
      c.children.forEach((cc, j) => {
        const off = (j - (spread - 1) / 2) * 0.55;
        const side = v(-dir.z, 0, dir.x);
        cc.pos = add(c.pos, add(mul(norm(dir), 150), add(mul(side, off * 150), v(0, (rand() - 0.5) * 80, 0))));
        const deep = (n, base) => n.children.forEach((x, m) => {
          x.pos = add(base, v((rand() - 0.5) * 120, -60 - m * 40, (rand() - 0.5) * 120));
          deep(x, x.pos);
        });
        deep(cc, cc.pos);
      });
    });
    const n = g.nodes.length;
    for (let it = 0; it < 220; it++) {
      const f = g.nodes.map(() => v(0, 0, 0));
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const dvec = sub(g.nodes[i].pos, g.nodes[j].pos);
          const dist = Math.max(len(dvec), 25);
          const push = mul(norm(dvec), 16000 / (dist * dist));
          f[i] = add(f[i], push);
          f[j] = sub(f[j], push);
        }
      }
      g.edges.forEach((e) => {
        if (!e.tree) return;
        const ia = g.nodes.indexOf(e.a), ib = g.nodes.indexOf(e.b);
        const dvec = sub(e.b.pos, e.a.pos);
        const want = e.a === g.root ? 245 : 150;
        const pull = mul(norm(dvec), (len(dvec) - want) * 0.05);
        f[ia] = add(f[ia], pull);
        f[ib] = sub(f[ib], pull);
      });
      g.nodes.forEach((node, i) => { if (node !== g.root) node.pos = add(node.pos, mul(f[i], 0.8)); });
    }
  }

  // ------------------------------------------------------------------ projection
  function project(p, cam, w, h) {
    const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw), cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
    const x1 = p.x * cy - p.z * sy, z1 = p.x * sy + p.z * cy;
    const y2 = p.y * cp - z1 * sp, z2 = p.y * sp + z1 * cp;
    const dist = 760 / cam.zoom;
    const s = 700 / (dist + z2);
    const k = Math.min(w, h) / 430;
    return { x: w / 2 + x1 * s * k, y: h / 2 - y2 * s * k, s, z: z2 };
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function wrap(ctx, text, maxW, maxLines) {
    const words = text.split(" ");
    const lines = [];
    let cur = "";
    words.forEach((wd) => {
      const t = cur ? cur + " " + wd : wd;
      if (ctx.measureText(t).width > maxW && cur) { lines.push(cur); cur = wd; } else cur = t;
    });
    if (cur) lines.push(cur);
    if (lines.length > maxLines) {
      lines.length = maxLines;
      lines[maxLines - 1] = lines[maxLines - 1].replace(/.{0,2}$/, "…");
    }
    return lines;
  }

  // ------------------------------------------------------------------ dessin
  function drawScene(t) {
    if (!st) return;
    const { ctx, canvas, g, cam } = st;
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (st.spin) cam.yaw += 0.0028;
    const intro = Math.min(1, (t - st.t0) / INTRO_MS);
    const ease = 1 - Math.pow(1 - intro, 3);
    const pulse = (Math.sin(t / 450) + 1) / 2;

    // Étoiles (parallaxe avec la rotation).
    st.stars.forEach((s) => {
      const p = project(s.p, cam, w, h);
      if (p.z < -600) return;
      ctx.fillStyle = `rgba(160,225,255,${s.a * (0.6 + 0.4 * Math.sin(t / 900 + s.ph))})`;
      ctx.fillRect(p.x, p.y, s.r, s.r);
    });

    // Plateau holographique : cercles + rayons.
    const floorY = st.floorY;
    ctx.lineWidth = 1;
    for (let r = 1; r <= 4; r++) {
      ctx.beginPath();
      for (let a = 0; a <= 72; a++) {
        const ang = (a / 72) * Math.PI * 2;
        const p = project(v(Math.cos(ang) * r * 85 * ease, floorY, Math.sin(ang) * r * 85 * ease), cam, w, h);
        if (a) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y);
      }
      ctx.strokeStyle = `rgba(56,217,255,${0.26 - r * 0.05})`;
      ctx.stroke();
    }
    for (let a = 0; a < 12; a++) {
      const ang = (a / 12) * Math.PI * 2 + t / 9000;
      const p1 = project(v(Math.cos(ang) * 40, floorY, Math.sin(ang) * 40), cam, w, h);
      const p2 = project(v(Math.cos(ang) * 340 * ease, floorY, Math.sin(ang) * 340 * ease), cam, w, h);
      ctx.strokeStyle = "rgba(56,217,255,.07)";
      ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
    }

    // Positions animées (les idées « jaillissent » de l'objectif à l'ouverture).
    const pos = new Map(g.nodes.map((n) => {
      const delay = Math.min(0.5, n.depth * 0.18);
      const k = Math.max(0, Math.min(1, (intro - delay) / (1 - delay)));
      const kk = 1 - Math.pow(1 - k, 3);
      return [n, lerp(g.root.pos, n.pos, kk)];
    }));
    const P = new Map(g.nodes.map((n) => [n, project(pos.get(n), cam, w, h)]));

    // Faisceau du projecteur sous l'objectif.
    const rp = P.get(g.root);
    const base = project(v(pos.get(g.root).x, floorY, pos.get(g.root).z), cam, w, h);
    const beam = ctx.createLinearGradient(base.x, base.y, rp.x, rp.y);
    beam.addColorStop(0, "rgba(56,217,255,.35)"); beam.addColorStop(1, "rgba(56,217,255,0)");
    ctx.fillStyle = beam;
    ctx.beginPath(); ctx.moveTo(base.x - 34, base.y); ctx.lineTo(base.x + 34, base.y);
    ctx.lineTo(rp.x + 8, rp.y); ctx.lineTo(rp.x - 8, rp.y); ctx.closePath(); ctx.fill();
    ctx.fillStyle = "rgba(56,217,255,.25)";
    ctx.beginPath(); ctx.ellipse(base.x, base.y, 40 * base.s, 12 * base.s, 0, 0, Math.PI * 2); ctx.fill();

    // Liens courbes + impulsions d'énergie (du parent vers l'enfant).
    const edges = g.edges.slice().sort((a, b) => (P.get(b.a).z + P.get(b.b).z) - (P.get(a.a).z + P.get(a.b).z));
    edges.forEach((e, idx) => {
      const A = pos.get(e.a), B = pos.get(e.b);
      const mid = add(lerp(A, B, 0.5), v(0, 28, 0));
      const a = P.get(e.a), b = P.get(e.b), m = project(mid, cam, w, h);
      const depth = Math.max(0.3, Math.min(1, 1.35 - (a.z + b.z) / 1000));
      const col = e.tree ? e.b.color : "#ffffff";
      const grad = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
      grad.addColorStop(0, rgba(e.tree ? e.a.color : col, 0.15 * depth));
      grad.addColorStop(1, rgba(col, (e.tree ? 0.75 : 0.45) * depth));
      ctx.strokeStyle = grad;
      ctx.lineWidth = e.tree ? 2.2 : 1.2;
      ctx.setLineDash(e.tree ? [] : [6, 6]);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(m.x, m.y, b.x, b.y); ctx.stroke();
      ctx.setLineDash([]);
      if (e.tree && intro >= 1) {
        const u = ((t / 1700) + idx * 0.37) % 1;
        const qx = (1 - u) * (1 - u) * a.x + 2 * (1 - u) * u * m.x + u * u * b.x;
        const qy = (1 - u) * (1 - u) * a.y + 2 * (1 - u) * u * m.y + u * u * b.y;
        const glow = ctx.createRadialGradient(qx, qy, 0, qx, qy, 7);
        glow.addColorStop(0, rgba("#ffffff", 0.95 * depth)); glow.addColorStop(1, rgba(col, 0));
        ctx.fillStyle = glow;
        ctx.beginPath(); ctx.arc(qx, qy, 7, 0, Math.PI * 2); ctx.fill();
      }
      if (e.label) {
        ctx.font = "600 10px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillStyle = rgba("#cfefff", 0.85 * depth);
        ctx.fillText(e.label, m.x, m.y - 6);
      }
    });

    // Idées : orbe + carte lumineuse (numéro, icône, titre).
    st.hits = [];
    const nodes = g.nodes.slice().sort((a, b) => P.get(b).z - P.get(a).z);
    nodes.splice(nodes.indexOf(g.root), 1); nodes.push(g.root); // l'objectif reste lisible
    if (st.selected) { nodes.splice(nodes.indexOf(st.selected), 1); nodes.push(st.selected); } // au premier plan
    nodes.forEach((n) => {
      const p = P.get(n);
      const isRoot = n === g.root, sel = n === st.selected;
      const depth = Math.max(0.4, Math.min(1, 1.3 - p.z / 800));
      const alpha = depth * Math.min(1, intro * 1.6);
      const r = Math.max(3, (isRoot ? 13 : n.depth === 1 ? 8 : 5) * p.s);
      ctx.globalAlpha = alpha;

      // Orbe
      const orb = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 2.6);
      orb.addColorStop(0, "#ffffff"); orb.addColorStop(0.25, n.color); orb.addColorStop(1, rgba(n.color, 0));
      ctx.fillStyle = orb;
      ctx.beginPath(); ctx.arc(p.x, p.y, r * 2.6, 0, Math.PI * 2); ctx.fill();
      if (isRoot) { // anneaux tournants autour de l'objectif
        ctx.strokeStyle = rgba(n.color, 0.7); ctx.lineWidth = 1.5;
        for (let i = 0; i < 2; i++) {
          ctx.beginPath();
          ctx.ellipse(p.x, p.y, r * (3.4 + i * 1.2), r * (1.1 + i * 0.4), t / (1800 + i * 900) * (i ? -1 : 1), 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // Étapes : simple pastille numérotée (le texte complet est dans la liste et au toucher).
      const full = isRoot || sel || (g.steps ? (n.kind === "phase" || g.nodes.length <= 9) : n.depth === 1);
      if (!full) {
        const fsb = Math.round(11 * Math.max(0.8, Math.min(1.1, p.s)));
        ctx.font = `800 ${fsb}px system-ui, sans-serif`;
        const icon = ICONS[n.kind] || "▸";
        const label = n.num || "•";
        const bw = ctx.measureText(label).width + fsb + 18;
        const bh = fsb + 8;
        const bx = p.x - bw / 2, by = p.y + r * 1.4 + 3;
        ctx.shadowColor = n.color; ctx.shadowBlur = 8;
        roundRect(ctx, bx, by, bw, bh, bh / 2);
        ctx.fillStyle = "rgba(4,16,30,.9)"; ctx.fill();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = rgba(n.color, 0.8); ctx.lineWidth = 1; ctx.stroke();
        ctx.textBaseline = "middle"; ctx.textAlign = "left";
        ctx.fillStyle = n.color;
        ctx.font = `${fsb}px system-ui, sans-serif`;
        ctx.fillText(icon, bx + 7, by + bh / 2 + 0.5);
        ctx.font = `800 ${fsb}px system-ui, sans-serif`;
        ctx.fillStyle = "#e2f8ff";
        ctx.fillText(label, bx + 7 + fsb + 3, by + bh / 2 + 0.5);
        st.hits.push({ n, x0: Math.min(bx, p.x - r * 2) - 6, y0: p.y - r * 2 - 6, x1: Math.max(bx + bw, p.x + r * 2) + 6, y1: by + bh + 6 });
        ctx.globalAlpha = 1;
        return;
      }

      // Carte
      const scale = Math.max(0.72, Math.min(1.15, p.s * 1.05));
      const fs = Math.round((isRoot ? 15 : n.depth === 1 ? 13 : 11.5) * scale);
      ctx.font = `${isRoot || n.depth === 1 ? 700 : 600} ${fs}px system-ui, sans-serif`;
      const icon = ICONS[n.kind] || (isRoot ? "🎯" : n.depth === 1 ? "◆" : "▸");
      const head = n.num ? `${n.num}` : "";
      const maxW = (isRoot ? 170 : n.depth === 1 ? 140 : 124) * scale;
      const lines = wrap(ctx, n.label, maxW, 2);
      const textW = Math.max(...lines.map((l) => ctx.measureText(l).width));
      const badgeW = head ? ctx.measureText(head).width + 12 : 0;
      const iconW = fs + 6;
      const padX = 8 * scale, padY = 6 * scale, lh = fs + 3;
      const cw = padX * 2 + iconW + textW + (badgeW ? badgeW + 6 : 0);
      const ch = padY * 2 + lines.length * lh - 3;
      const cx = p.x - cw / 2, cy = isRoot ? p.y - r * 3.6 - ch : p.y + r * 1.6 + 4; // objectif : au-dessus

      ctx.shadowColor = n.color; ctx.shadowBlur = sel ? 22 : isRoot ? 18 : 10;
      roundRect(ctx, cx, cy, cw, ch, 9 * scale);
      ctx.fillStyle = isRoot ? "rgba(10,40,64,.92)" : "rgba(4,16,30,.86)";
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.lineWidth = sel ? 2 : 1;
      ctx.strokeStyle = rgba(n.color, sel ? 1 : 0.55 + 0.25 * pulse * (isRoot ? 1 : 0));
      ctx.stroke();
      // liseré lumineux en haut de la carte
      ctx.fillStyle = rgba(n.color, 0.85);
      ctx.fillRect(cx + 10 * scale, cy, cw - 20 * scale, 1.5);

      let x = cx + padX;
      ctx.textBaseline = "middle"; ctx.textAlign = "left";
      if (badgeW) {
        roundRect(ctx, x, cy + ch / 2 - (fs + 4) / 2, badgeW, fs + 4, (fs + 4) / 2);
        ctx.fillStyle = n.color; ctx.fill();
        ctx.fillStyle = "#03101c";
        ctx.font = `800 ${Math.round(fs * 0.85)}px system-ui, sans-serif`;
        ctx.fillText(head, x + 6, cy + ch / 2 + 0.5);
        x += badgeW + 6;
      }
      ctx.font = `${fs}px system-ui, sans-serif`;
      ctx.fillStyle = n.color;
      ctx.fillText(icon, x, cy + ch / 2 + 0.5);
      x += iconW;
      ctx.font = `${isRoot || n.depth === 1 ? 700 : 600} ${fs}px system-ui, sans-serif`;
      ctx.fillStyle = isRoot ? "#ffffff" : "#e2f8ff";
      lines.forEach((ln, i) => ctx.fillText(ln, x, cy + padY + lh / 2 + i * lh - 1));

      st.hits.push({ n, x0: Math.min(cx, p.x - r * 2), y0: p.y - r * 2, x1: Math.max(cx + cw, p.x + r * 2), y1: cy + ch });
      ctx.globalAlpha = 1;
    });
    raf = requestAnimationFrame(drawScene);
  }

  // ------------------------------------------------------------------ détail + liste du plan
  function select(n, fromList) {
    if (!st) return;
    st.selected = n;
    const box = document.getElementById("holo-detail");
    box.replaceChildren();
    document.querySelectorAll(".holo-step.active").forEach((x) => x.classList.remove("active"));
    if (!n) { box.classList.add("hidden"); return; }
    const t = document.createElement("strong");
    t.textContent = `${n.num ? n.num + " · " : ""}${ICONS[n.kind] ? ICONS[n.kind] + " " : ""}${n.label}`;
    box.append(t);
    if (n.note) {
      const p = document.createElement("span");
      p.textContent = n.note;
      box.append(p);
    }
    box.style.borderColor = n.color;
    box.classList.remove("hidden");
    const li = st.items.get(n);
    if (li) {
      li.classList.add("active");
      if (!fromList) li.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  function buildPlan(g) {
    const list = document.getElementById("holo-plan");
    list.replaceChildren();
    const items = new Map();
    const dfs = [];
    const walk = (n) => n.children.forEach((c) => { dfs.push(c); walk(c); });
    walk(g.root);
    const seq = g.steps ? g.nodes.filter((n) => n !== g.root) : dfs;
    seq.forEach((n) => {
      const li = document.createElement("li");
      li.className = "holo-step" + (n.depth === 1 && !g.steps ? " phase" : "");
      li.style.setProperty("--c", n.color);
      li.style.marginLeft = g.steps ? "0" : `${Math.max(0, n.depth - 1) * 16}px`;
      const num = document.createElement("span");
      num.className = "holo-num";
      num.textContent = n.num;
      const body = document.createElement("div");
      const title = document.createElement("div");
      title.className = "holo-step-title";
      title.textContent = (ICONS[n.kind] ? ICONS[n.kind] + " " : "") + n.label;
      body.append(title);
      if (n.note) {
        const note = document.createElement("div");
        note.className = "holo-step-note";
        note.textContent = n.note;
        body.append(note);
      }
      li.append(num, body);
      li.addEventListener("click", () => {
        st.spin = false;
        select(n, true);
        // Tourne la caméra vers l'idée choisie.
        st.turnTo = Math.atan2(n.pos.x, n.pos.z) + Math.PI;
      });
      items.set(n, li);
      list.appendChild(li);
    });
    return items;
  }

  // ------------------------------------------------------------------ gestes
  function bindGestures(canvas) {
    const pts = new Map();
    let moved = false, pinch0 = 0, zoom0 = 1;
    canvas.addEventListener("pointerdown", (e) => {
      if (!st) return;
      canvas.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      moved = false; st.spin = false; st.turnTo = null;
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        pinch0 = Math.hypot(a.x - b.x, a.y - b.y); zoom0 = st.cam.zoom;
      }
    });
    canvas.addEventListener("pointermove", (e) => {
      const prev = pts.get(e.pointerId);
      if (!prev || !st) return;
      const cur = { x: e.clientX, y: e.clientY };
      pts.set(e.pointerId, cur);
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        if (pinch0) st.cam.zoom = Math.max(0.45, Math.min(2.8, zoom0 * Math.hypot(a.x - b.x, a.y - b.y) / pinch0));
        moved = true;
        return;
      }
      const dx = cur.x - prev.x, dy = cur.y - prev.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      st.cam.yaw += dx * 0.008;
      st.cam.pitch = Math.max(-0.3, Math.min(1.2, st.cam.pitch + dy * 0.006));
    });
    const up = (e) => {
      pts.delete(e.pointerId);
      if (pts.size < 2) pinch0 = 0;
      if (!moved && pts.size === 0 && st) {
        const r = canvas.getBoundingClientRect();
        const x = e.clientX - r.left, y = e.clientY - r.top;
        const hit = (st.hits || []).slice().reverse().find((h) => x >= h.x0 && x <= h.x1 && y >= h.y0 && y <= h.y1);
        select(hit ? hit.n : null);
      }
    };
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", (e) => {
      if (!st) return;
      e.preventDefault();
      st.spin = false;
      st.cam.zoom = Math.max(0.45, Math.min(2.8, st.cam.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
    }, { passive: false });
  }

  function animateTurn() { // rotation douce vers l'idée choisie dans la liste
    if (st && st.turnTo != null) {
      let d = st.turnTo - st.cam.yaw;
      d = Math.atan2(Math.sin(d), Math.cos(d));
      if (Math.abs(d) < 0.01) st.turnTo = null; else st.cam.yaw += d * 0.08;
    }
    if (st) requestAnimationFrame(animateTurn);
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
    document.getElementById("holo").classList.remove("hidden");
    document.getElementById("holo-title").textContent = String(d.title || "").slice(0, 80);
    const canvas = document.getElementById("holo-canvas");
    const g = buildGraph(d);
    layout(g, d.style, String(d.title || ""));
    const c = g.nodes.reduce((acc, n) => add(acc, n.pos), v(0, 0, 0));
    const center = mul(c, 1 / g.nodes.length);
    g.nodes.forEach((n) => { n.pos = sub(n.pos, center); });
    const radius = Math.max(...g.nodes.map((n) => len(n.pos)), 140);
    const rand = rng(42);
    const stars = Array.from({ length: 140 }, () => {
      const u = rand() * 2 - 1, a = rand() * Math.PI * 2, r = Math.sqrt(1 - u * u);
      return { p: mul(v(Math.cos(a) * r, u, Math.sin(a) * r), 900 + rand() * 300), a: 0.25 + rand() * 0.5,
        r: rand() < 0.15 ? 2 : 1, ph: rand() * 6 };
    });
    cancelAnimationFrame(raf);
    st = { canvas, ctx: canvas.getContext("2d"), g, selected: null, hits: [], spin: true, turnTo: null,
      stars, t0: performance.now(), floorY: Math.min(...g.nodes.map((n) => n.pos.y)) - 70,
      cam: { yaw: 0.5, pitch: 0.42, zoom: Math.max(0.32, Math.min(1.15, 205 / radius)) } };
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) { st.spin = false; st.t0 -= INTRO_MS; }
    st.items = buildPlan(g);
    select(null);
    if (!canvas.dataset.bound) { bindGestures(canvas); canvas.dataset.bound = "1"; }
    raf = requestAnimationFrame(drawScene);
    requestAnimationFrame(animateTurn);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("holo-close").addEventListener("click", close);
    document.getElementById("holo-spin").addEventListener("click", () => { if (st) st.spin = !st.spin; });
  });

  window.SyriusHolo = { show, close };
})();
