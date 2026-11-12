// Hologramme de Syrius : plan d'action en carrousel 3D, dessiné sur un <canvas> (aucune bibliothèque).
// L'objectif brille en haut ; chaque phase est un panneau lumineux qui tourne autour.
// Un seul panneau est face à l'utilisateur : tout reste lisible, même avec beaucoup d'étapes.
// Le texte est dessiné avec fillText ou inséré avec textContent (jamais comme du HTML).
"use strict";

(function () {
  const COLORS = ["#38d9ff", "#7cf3c8", "#ffd166", "#ff8fab", "#b69cff", "#6fb3ff", "#9ef06c", "#ffa36c"];
  const ICONS = { objectif: "🎯", phase: "◆", etape: "▸", action: "✔", outil: "🛠", budget: "€", delai: "⏱",
    risque: "⚠", idee: "💡", ressource: "📚", personne: "👤" };
  const FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
  const INTRO_MS = 1100;
  let st = null;
  let raf = 0;

  function rgba(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  function rng(seed) {
    let s = seed >>> 0 || 1;
    return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  }

  // ------------------------------------------------------------------ structure : objectif → panneaux
  function buildPlan(d) {
    const nodes = d.nodes.map((n) => ({ ...n, children: [] }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const root = nodes.find((n) => !n.parent) || nodes[0];
    nodes.forEach((n) => {
      if (n === root) return;
      (byId.has(n.parent) ? byId.get(n.parent) : root).children.push(n);
    });
    let panels;
    if (d.style === "etapes") { // chaque idée = un panneau, dans l'ordre donné
      panels = nodes.filter((n) => n !== root).map((n, i) => ({ node: n, num: String(i + 1), items: [] }));
    } else {
      panels = root.children.map((n, i) => {
        const items = [];
        const walk = (x, prefix, depth) => x.children.forEach((c, j) => {
          const num = `${prefix}.${j + 1}`;
          items.push({ node: c, num, depth });
          walk(c, num, depth + 1);
        });
        walk(n, String(i + 1), 0);
        return { node: n, num: String(i + 1), items };
      });
    }
    panels.forEach((p, i) => { p.color = COLORS[i % COLORS.length]; });
    return { root, panels };
  }

  // ------------------------------------------------------------------ texte
  function wrap(ctx, text, maxW, maxLines) {
    const words = String(text).split(" ");
    const lines = [];
    let cur = "";
    for (const wd of words) {
      const t = cur ? cur + " " + wd : wd;
      if (ctx.measureText(t).width > maxW && cur) { lines.push(cur); cur = wd; } else cur = t;
    }
    if (cur) lines.push(cur);
    if (lines.length > maxLines) {
      lines.length = maxLines;
      let last = lines[maxLines - 1];
      while (last.length > 1 && ctx.measureText(last + "…").width > maxW) last = last.slice(0, -1);
      lines[maxLines - 1] = last.trimEnd() + "…";
    }
    return lines;
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

  // Mise en page d'un panneau (calculée une fois par taille d'écran), en coordonnées locales.
  function layoutPanel(ctx, p, W, maxH) {
    const pad = 16;
    const inner = W - pad * 2;
    const rows = [];
    let y = pad;
    ctx.font = `800 13px ${FONT}`;
    const badgeW = p.num ? ctx.measureText(p.num).width + 18 : 0;
    ctx.font = `700 17px ${FONT}`;
    const titleLines = wrap(ctx, p.node.label, inner - badgeW - 30, 2);
    rows.push({ t: "head", y, titleLines, badgeW });
    y += titleLines.length * 21 + 8;
    if (p.node.note) {
      ctx.font = `13px ${FONT}`;
      const noteLines = wrap(ctx, p.node.note, inner, p.items.length ? 2 : 6);
      rows.push({ t: "note", y, lines: noteLines });
      y += noteLines.length * 17 + 6;
    }
    if (p.items.length) {
      rows.push({ t: "sep", y: y + 4 });
      y += 14;
    }
    let shown = 0;
    for (const it of p.items) {
      const indent = it.depth * 14;
      ctx.font = `800 11px ${FONT}`;
      const numW = ctx.measureText(it.num).width + 14;
      ctx.font = `600 14px ${FONT}`;
      const tl = wrap(ctx, (ICONS[it.node.kind] ? ICONS[it.node.kind] + " " : "") + it.node.label,
        inner - indent - numW - 8, 2);
      ctx.font = `12px ${FONT}`;
      const nl = it.node.note ? wrap(ctx, it.node.note, inner - indent - numW - 8, 2) : [];
      const h = tl.length * 18 + nl.length * 15 + 10;
      if (y + h > maxH - pad - 18) break;
      rows.push({ t: "item", y, it, indent, numW, tl, nl });
      y += h;
      shown += 1;
    }
    if (shown < p.items.length) {
      rows.push({ t: "more", y, n: p.items.length - shown });
      y += 18;
    }
    return { rows, H: Math.min(maxH, y + pad) };
  }

  function drawPanel(ctx, p, L, W, color, focus) {
    const H = L.H;
    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, "rgba(14,44,72,.95)");
    bg.addColorStop(1, "rgba(4,14,28,.95)");
    ctx.shadowColor = color; ctx.shadowBlur = focus ? 26 : 8;
    roundRect(ctx, 0, 0, W, H, 16);
    ctx.fillStyle = bg; ctx.fill();
    ctx.shadowBlur = 0;
    ctx.lineWidth = focus ? 1.6 : 1;
    ctx.strokeStyle = rgba(color, focus ? 0.95 : 0.5);
    ctx.stroke();
    const top = ctx.createLinearGradient(0, 0, W, 0);
    top.addColorStop(0, rgba(color, 0)); top.addColorStop(0.5, rgba(color, 1)); top.addColorStop(1, rgba(color, 0));
    ctx.fillStyle = top; ctx.fillRect(18, 0, W - 36, 2);
    ctx.strokeStyle = color; ctx.lineWidth = 2;
    [[8, 22, 8, 8, 22, 8], [W - 22, 8, W - 8, 8, W - 8, 22], [8, H - 22, 8, H - 8, 22, H - 8],
      [W - 22, H - 8, W - 8, H - 8, W - 8, H - 22]].forEach((c) => {
      ctx.beginPath(); ctx.moveTo(c[0], c[1]); ctx.lineTo(c[2], c[3]); ctx.lineTo(c[4], c[5]); ctx.stroke();
    });

    const pad = 16;
    ctx.textBaseline = "top"; ctx.textAlign = "left";
    L.rows.forEach((r) => {
      if (r.t === "head") {
        let x = pad;
        if (p.num) {
          roundRect(ctx, x, r.y + 1, r.badgeW, 21, 10.5);
          ctx.fillStyle = color; ctx.fill();
          ctx.fillStyle = "#03101c"; ctx.font = `800 13px ${FONT}`;
          ctx.fillText(p.num, x + 9, r.y + 5);
          x += r.badgeW + 8;
        }
        ctx.fillStyle = color; ctx.font = `15px ${FONT}`;
        ctx.fillText(ICONS[p.node.kind] || "◆", x, r.y + 3);
        x += 22;
        ctx.fillStyle = "#ffffff"; ctx.font = `700 17px ${FONT}`;
        r.titleLines.forEach((ln, i) => ctx.fillText(ln, x, r.y + 2 + i * 21));
      } else if (r.t === "note") {
        ctx.fillStyle = "#a9c9da"; ctx.font = `13px ${FONT}`;
        r.lines.forEach((ln, i) => ctx.fillText(ln, pad, r.y + i * 17));
      } else if (r.t === "sep") {
        const g = ctx.createLinearGradient(pad, 0, W - pad, 0);
        g.addColorStop(0, rgba(color, 0.6)); g.addColorStop(1, rgba(color, 0));
        ctx.fillStyle = g; ctx.fillRect(pad, r.y, W - pad * 2, 1);
      } else if (r.t === "item") {
        const x0 = pad + r.indent;
        roundRect(ctx, x0, r.y + 1, r.numW, 17, 8.5);
        ctx.fillStyle = rgba(color, 0.18); ctx.fill();
        ctx.strokeStyle = rgba(color, 0.7); ctx.lineWidth = 1; ctx.stroke();
        ctx.fillStyle = color; ctx.font = `800 11px ${FONT}`;
        ctx.fillText(r.it.num, x0 + 7, r.y + 4);
        const tx = x0 + r.numW + 8;
        ctx.fillStyle = "#e6f8ff"; ctx.font = `600 14px ${FONT}`;
        r.tl.forEach((ln, i) => ctx.fillText(ln, tx, r.y + i * 18));
        ctx.fillStyle = "#8fb3c6"; ctx.font = `12px ${FONT}`;
        r.nl.forEach((ln, i) => ctx.fillText(ln, tx, r.y + r.tl.length * 18 + 1 + i * 15));
      } else if (r.t === "more") {
        ctx.fillStyle = rgba(color, 0.9); ctx.font = `600 12px ${FONT}`;
        ctx.fillText(`+ ${r.n} autre${r.n > 1 ? "s" : ""} étape${r.n > 1 ? "s" : ""} · voir la liste`, pad, r.y);
      }
    });
  }

  // ------------------------------------------------------------------ scène
  function frame(t) {
    if (!st) return;
    const { ctx, canvas, plan } = st;
    const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      st.layouts = null;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const intro = Math.min(1, (t - st.t0) / INTRO_MS);
    const ease = 1 - Math.pow(1 - intro, 3);
    const n = plan.panels.length;

    if (!st.dragging) { // retour doux vers le panneau visé
      const d = st.target - st.angle;
      st.angle = Math.abs(d) < 0.001 ? st.target : st.angle + d * 0.14;
    }

    const PW = Math.min(300, w * 0.74);
    const coreY = Math.max(36, h * 0.1);
    const panelTop = coreY + 50;
    const maxH = h - panelTop - 24;
    if (!st.layouts) st.layouts = plan.panels.map((p) => layoutPanel(ctx, p, PW, maxH));

    // Étoiles (défilent avec la rotation)
    st.stars.forEach((s) => {
      const x = ((s.x - st.angle * 60) % w + w) % w;
      ctx.fillStyle = `rgba(160,225,255,${s.a * (0.6 + 0.4 * Math.sin(t / 900 + s.ph))})`;
      ctx.fillRect(x, s.y * h, s.r, s.r);
    });

    // Plateau holographique
    const floorY = h - 12;
    for (let i = 3; i >= 1; i--) {
      ctx.strokeStyle = `rgba(56,217,255,${0.08 * i})`;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.ellipse(w / 2, floorY, w * 0.15 * i * ease, 6 * i * ease, 0, 0, Math.PI * 2); ctx.stroke();
    }

    // Panneaux sur un anneau 3D
    const R = PW * 1.05;
    const step = n > 1 ? Math.min((Math.PI * 2) / n, 0.78) : 0; // écart entre panneaux voisins
    const items = plan.panels.map((p, i) => {
      let d = n > 1 ? i - st.angle : 0;
      d = ((d % n) + n) % n;
      if (d > n / 2) d -= n; // distance la plus courte sur l'anneau
      const a = d * step;
      const x = Math.sin(a) * R, z = Math.cos(a) * R;
      const s = 900 / (900 + (R - z) * 1.25);
      return { p, i, a, d, x, z, s, L: st.layouts[i] };
    }).filter((it) => Math.abs(it.d) < 2.3).sort((A, B) => A.z - B.z);

    // Faisceaux de l'objectif vers les panneaux
    items.forEach((it) => {
      const front = Math.cos(it.a);
      if (front < -0.2) return;
      const px = w / 2 + it.x * it.s * ease, py = panelTop + 2;
      const g = ctx.createLinearGradient(w / 2, coreY, px, py);
      g.addColorStop(0, "rgba(255,255,255,.5)"); g.addColorStop(1, rgba(it.p.color, 0.08 + 0.4 * Math.max(0, front)));
      ctx.strokeStyle = g; ctx.lineWidth = 1 + Math.max(0, front) * 1.5;
      ctx.beginPath(); ctx.moveTo(w / 2, coreY); ctx.lineTo(px, py); ctx.stroke();
      if (front > 0.9 && intro >= 1) {
        const u = (t / 1300) % 1;
        const qx = w / 2 + (px - w / 2) * u, qy = coreY + (py - coreY) * u;
        const gl = ctx.createRadialGradient(qx, qy, 0, qx, qy, 6);
        gl.addColorStop(0, "#fff"); gl.addColorStop(1, rgba(it.p.color, 0));
        ctx.fillStyle = gl; ctx.beginPath(); ctx.arc(qx, qy, 6, 0, Math.PI * 2); ctx.fill();
      }
    });

    st.hits = [];
    items.forEach((it) => {
      const front = Math.cos(it.a);
      if (front < -0.2) return; // panneaux de dos : invisibles
      const sx = Math.max(0.1, Math.abs(front)); // le panneau pivote sur lui-même
      const sc = it.s * (0.75 + 0.25 * ease);
      const cx = w / 2 + it.x * it.s * ease;
      const bob = Math.sin(t / 1400 + it.i) * 3;
      const alpha = Math.pow(Math.max(0, front), 4) * Math.min(1, intro * 1.5); // voisins en retrait
      ctx.save();
      ctx.globalAlpha = Math.max(0.05, alpha);
      ctx.translate(cx, panelTop + bob);
      ctx.scale(sc * sx, sc);
      ctx.translate(-PW / 2, 0);
      drawPanel(ctx, it.p, it.L, PW, it.p.color, front > 0.95);
      ctx.restore();
      st.hits.push({ i: it.i, x0: cx - (PW / 2) * sc * sx, x1: cx + (PW / 2) * sc * sx, front });
    });

    // Objectif : noyau lumineux + anneaux + titre
    const pulse = (Math.sin(t / 500) + 1) / 2;
    const core = ctx.createRadialGradient(w / 2, coreY, 0, w / 2, coreY, 26);
    core.addColorStop(0, "#ffffff"); core.addColorStop(0.3, "#9ff0ff"); core.addColorStop(1, "rgba(56,217,255,0)");
    ctx.fillStyle = core; ctx.beginPath(); ctx.arc(w / 2, coreY, 26, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "rgba(120,235,255,.75)"; ctx.lineWidth = 1.3;
    for (let i = 0; i < 2; i++) {
      ctx.beginPath();
      ctx.ellipse(w / 2, coreY, 30 + i * 9 + pulse * 2, 9 + i * 3, (t / (1600 + i * 700)) * (i ? -1 : 1), 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.font = `700 14px ${FONT}`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const title = wrap(ctx, ICONS.objectif + " " + plan.root.label, w - 110, 1)[0];
    const tw = ctx.measureText(title).width + 24;
    ctx.shadowColor = "#38d9ff"; ctx.shadowBlur = 14;
    roundRect(ctx, w / 2 - tw / 2, coreY + 19, tw, 26, 13);
    ctx.fillStyle = "rgba(8,34,56,.95)"; ctx.fill();
    ctx.shadowBlur = 0; ctx.strokeStyle = "rgba(120,235,255,.8)"; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = "#ffffff"; ctx.fillText(title, w / 2, coreY + 32.5);

    raf = requestAnimationFrame(frame);
  }

  // ------------------------------------------------------------------ navigation
  function index(v) {
    const n = st.plan.panels.length;
    return ((Math.round(v) % n) + n) % n;
  }

  function go(to) {
    if (!st) return;
    st.target = Math.round(to);
    const idx = index(st.target);
    const p = st.plan.panels[idx];
    [...document.getElementById("holo-dots").children].forEach((d, i) => d.classList.toggle("on", i === idx));
    document.getElementById("holo-count").textContent =
      `${st.plan.panels.length > 1 ? `${idx + 1} / ${st.plan.panels.length} · ` : ""}${p ? p.node.label : ""}`;
    document.querySelectorAll(".holo-step.active").forEach((x) => x.classList.remove("active"));
    const li = st.listItems[idx];
    if (li) li.classList.add("active");
  }

  function goIndex(i) { // chemin le plus court vers le panneau i
    const n = st.plan.panels.length;
    let d = i - index(st.target);
    if (d > n / 2) d -= n;
    if (d < -n / 2) d += n;
    go(st.target + d);
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function buildList(plan) {
    const list = document.getElementById("holo-plan");
    list.replaceChildren();
    const out = plan.panels.map((p, i) => {
      const group = el("li", "holo-step phase");
      group.style.setProperty("--c", p.color);
      const head = el("div", "holo-step-row");
      const body = el("div");
      body.append(el("div", "holo-step-title", p.node.label));
      if (p.node.note) body.append(el("div", "holo-step-note", p.node.note));
      head.append(el("span", "holo-num", p.num || "•"), body);
      group.append(head);
      if (p.items.length) {
        const ul = el("ul", "holo-sub");
        p.items.forEach((it) => {
          const li = el("li");
          li.style.paddingLeft = `${it.depth * 14}px`;
          const b = el("div");
          b.append(el("div", "holo-sub-title", (ICONS[it.node.kind] ? ICONS[it.node.kind] + " " : "") + it.node.label));
          if (it.node.note) b.append(el("div", "holo-step-note", it.node.note));
          li.append(el("span", "holo-subnum", it.num), b);
          ul.append(li);
        });
        group.append(ul);
      }
      group.addEventListener("click", () => {
        goIndex(i);
        document.getElementById("holo-canvas").scrollIntoView({ block: "nearest", behavior: "smooth" });
      });
      list.append(group);
      return group;
    });
    document.getElementById("holo-dots").replaceChildren(...plan.panels.map((p, i) => {
      const d = el("button", "holo-dot");
      d.type = "button";
      d.setAttribute("aria-label", `Phase ${i + 1}`);
      d.style.setProperty("--c", p.color);
      d.addEventListener("click", () => goIndex(i));
      return d;
    }));
    return out;
  }

  function bindGestures(canvas) {
    let startX = 0, startAngle = 0, moved = false, id = null;
    canvas.addEventListener("pointerdown", (e) => {
      if (!st) return;
      id = e.pointerId;
      canvas.setPointerCapture(id);
      startX = e.clientX; startAngle = st.angle; moved = false; st.dragging = true;
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!st || e.pointerId !== id) return;
      const dx = e.clientX - startX;
      if (Math.abs(dx) > 6) moved = true;
      if (moved) st.angle = startAngle - dx / (canvas.clientWidth * 0.6);
    });
    const up = (e) => {
      if (!st || e.pointerId !== id) return;
      id = null; st.dragging = false;
      const dx = e.clientX - startX;
      if (moved) {
        let to = Math.round(st.angle);
        if (to === Math.round(startAngle) && Math.abs(dx) > 30) to += dx < 0 ? 1 : -1;
        go(to);
        return;
      }
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left;
      const side = st.hits.filter((hh) => hh.front < 0.95 && x >= hh.x0 && x <= hh.x1)
        .sort((a, b) => b.front - a.front)[0];
      if (side) goIndex(side.i);
      else if (x < r.width * 0.15) go(st.target - 1);
      else if (x > r.width * 0.85) go(st.target + 1);
    };
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
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
    const plan = buildPlan(d);
    if (!plan.panels.length) return;
    document.getElementById("holo").classList.remove("hidden");
    document.getElementById("holo-title").textContent = String(d.title || "").slice(0, 80);
    const canvas = document.getElementById("holo-canvas");
    const rand = rng(42);
    cancelAnimationFrame(raf);
    st = { canvas, ctx: canvas.getContext("2d"), plan, angle: -0.5, target: 0, dragging: false, hits: [],
      layouts: null, t0: performance.now(),
      stars: Array.from({ length: 90 }, () => ({ x: rand() * 2000, y: rand(), a: 0.2 + rand() * 0.5,
        r: rand() < 0.15 ? 2 : 1, ph: rand() * 6 })) };
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) { st.t0 -= INTRO_MS; st.angle = 0; }
    const multi = plan.panels.length > 1;
    document.getElementById("holo-nav").classList.toggle("hidden", !multi);
    st.listItems = buildList(plan);
    go(0);
    if (!canvas.dataset.bound) { bindGestures(canvas); canvas.dataset.bound = "1"; }
    raf = requestAnimationFrame(frame);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("holo-close").addEventListener("click", close);
    document.getElementById("holo-prev").addEventListener("click", () => st && go(st.target - 1));
    document.getElementById("holo-next").addEventListener("click", () => st && go(st.target + 1));
  });

  window.SyriusHolo = { show, close };
})();
