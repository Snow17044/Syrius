// Studio 3D de Syrius : maquettes holographiques (monuments, objets, véhicules…) avec Three.js.
// L'IA décrit l'objet en formes simples ; on les assemble, on centre, on éclaire, on anime.
// Aucun texte n'est inséré comme HTML (textContent uniquement).
"use strict";

(function () {
  const HOLO = 0x38d9ff;
  let st = null;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function webglOk() {
    try {
      const c = document.createElement("canvas");
      return !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch (e) {
      return false;
    }
  }

  // ------------------------------------------------------------------ formes
  function vec3(v, d) { // tolérant : nombre seul, liste incomplète ou absente
    if (typeof v === "number") return [v, v, v];
    const a = Array.isArray(v) ? v : [];
    return [0, 1, 2].map((i) => (typeof a[i] === "number" && isFinite(a[i]) ? a[i] : d));
  }

  function geometry(p) {
    const [a, b, c] = vec3(p.size, 1).map((x) => Math.max(0.001, Math.abs(x)));
    switch (p.shape) {
      case "box": return new THREE.BoxGeometry(a, b, c);
      case "cylinder": return new THREE.CylinderGeometry(a, c, b, 28);
      case "cone": return new THREE.ConeGeometry(a, b, 28);
      case "sphere": return new THREE.SphereGeometry(a, 28, 18);
      case "torus": return new THREE.TorusGeometry(a, Math.min(b, a), 14, 40);
      case "capsule": return new THREE.CapsuleGeometry(a, b, 8, 16);
      case "pyramid": {
        const g = new THREE.ConeGeometry(Math.SQRT1_2, 1, 4, 1);
        g.rotateY(Math.PI / 4);
        g.scale(a, b, c);
        return g;
      }
      default: return new THREE.BoxGeometry(a, b, c);
    }
  }

  function buildModel(ev) {
    const group = new THREE.Group();
    const parts = [];
    ev.parts.forEach((p) => {
      const geo = geometry(p);
      const color = new THREE.Color(/^#[0-9a-f]{6}$/i.test(p.color || "") ? p.color : "#38d9ff");
      const mat = new THREE.MeshStandardMaterial({
        color, emissive: color, emissiveIntensity: 0.16, metalness: 0.35, roughness: 0.45,
        transparent: true, opacity: 0.9,
      });
      const mesh = new THREE.Mesh(geo, mat);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 28),
        new THREE.LineBasicMaterial({ color: color.clone().lerp(new THREE.Color(0xffffff), 0.45),
          transparent: true, opacity: 0.45 }));
      mesh.add(edges);
      const pos = vec3(p.pos, 0), rot = vec3(p.rot, 0);
      mesh.position.set(pos[0], pos[1], pos[2]);
      mesh.rotation.set(THREE.MathUtils.degToRad(rot[0]), THREE.MathUtils.degToRad(rot[1]),
        THREE.MathUtils.degToRad(rot[2]));
      group.add(mesh);
      parts.push({ mesh, edges, color });
    });
    // Centre la maquette, pose-la au sol et ramène-la à une taille standard.
    const box = new THREE.Box3().setFromObject(group);
    const size = box.getSize(new THREE.Vector3());
    const k = 10 / Math.max(size.x, size.y, size.z, 0.001);
    const center = box.getCenter(new THREE.Vector3());
    group.children.forEach((m) => {
      m.position.sub(new THREE.Vector3(center.x, box.min.y, center.z));
    });
    const holder = new THREE.Group();
    holder.add(group);
    holder.scale.setScalar(k);
    return { holder, group, parts, height: size.y * k, radius: Math.max(size.x, size.z) * k / 2 };
  }

  // ------------------------------------------------------------------ décor holographique
  function buildStage(scene) {
    const stage = new THREE.Group();
    const cyan = new THREE.LineBasicMaterial({ color: HOLO, transparent: true, opacity: 0.35 });
    const grid = new THREE.PolarGridHelper(8, 16, 6, 64, HOLO, HOLO);
    grid.material.transparent = true; grid.material.opacity = 0.18;
    stage.add(grid);
    for (let i = 1; i <= 3; i++) {
      const ring = new THREE.Mesh(new THREE.RingGeometry(7.6 + i * 0.35, 7.68 + i * 0.35, 96),
        new THREE.MeshBasicMaterial({ color: HOLO, transparent: true, opacity: 0.5 / i, side: THREE.DoubleSide }));
      ring.rotation.x = -Math.PI / 2;
      stage.add(ring);
    }
    // disque lumineux du projecteur
    const disc = new THREE.Mesh(new THREE.CircleGeometry(6.5, 64),
      new THREE.MeshBasicMaterial({ color: HOLO, transparent: true, opacity: 0.07, side: THREE.DoubleSide }));
    disc.rotation.x = -Math.PI / 2; disc.position.y = 0.01;
    stage.add(disc);
    // étoiles
    const pts = [];
    for (let i = 0; i < 500; i++) {
      const u = Math.random() * 2 - 1, a = Math.random() * Math.PI * 2, r = 60 + Math.random() * 40;
      const s = Math.sqrt(1 - u * u);
      pts.push(Math.cos(a) * s * r, u * r, Math.sin(a) * s * r);
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    stage.add(new THREE.Points(sg, new THREE.PointsMaterial({ color: 0x9fe8ff, size: 0.35, transparent: true,
      opacity: 0.7, sizeAttenuation: true })));
    // anneau de balayage (scanner)
    const scan = new THREE.Mesh(new THREE.RingGeometry(0.1, 7.2, 64),
      new THREE.MeshBasicMaterial({ color: HOLO, transparent: true, opacity: 0.06, side: THREE.DoubleSide,
        depthWrite: false }));
    scan.rotation.x = -Math.PI / 2;
    const scanEdge = new THREE.LineLoop(new THREE.CircleGeometry(7.2, 96), cyan);
    scanEdge.rotation.x = -Math.PI / 2;
    stage.add(scan, scanEdge);
    scene.add(stage);
    return { stage, scan, scanEdge };
  }

  // ------------------------------------------------------------------ apparence
  function applyMode() {
    if (!st) return;
    const holo = st.mode === "holo";
    st.model.parts.forEach(({ mesh, edges, color }) => {
      mesh.material.color.set(holo ? HOLO : color);
      mesh.material.emissive.set(holo ? HOLO : color);
      mesh.material.emissiveIntensity = holo ? 0.7 : 0.16;
      mesh.material.opacity = holo ? 0.38 : 0.92;
      mesh.material.depthWrite = !holo;
      edges.material.color.set(holo ? 0xbff4ff : color.clone().lerp(new THREE.Color(0xffffff), 0.45));
      edges.material.opacity = holo ? 0.9 : 0.4;
    });
    document.getElementById("m3d-mode").textContent = holo ? "🎨" : "💠";
    document.getElementById("m3d-mode").setAttribute("aria-label", holo ? "Couleurs réelles" : "Mode hologramme");
  }

  // ------------------------------------------------------------------ caméra (orbite au doigt)
  function bindControls(canvas) {
    const pts = new Map();
    let pinch0 = 0, dist0 = 0, lastTap = 0;
    canvas.addEventListener("pointerdown", (e) => {
      if (!st) return;
      canvas.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      st.auto = false;
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        pinch0 = Math.hypot(a.x - b.x, a.y - b.y); dist0 = st.cam.dist;
      }
      const now = performance.now();
      if (now - lastTap < 300) { st.cam.theta = 0.7; st.cam.phi = 1.15; st.cam.dist = st.cam.home; st.auto = true; }
      lastTap = now;
    });
    canvas.addEventListener("pointermove", (e) => {
      const prev = pts.get(e.pointerId);
      if (!prev || !st) return;
      const cur = { x: e.clientX, y: e.clientY };
      pts.set(e.pointerId, cur);
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        if (pinch0) st.cam.dist = Math.max(6, Math.min(60, dist0 * pinch0 / Math.hypot(a.x - b.x, a.y - b.y)));
        return;
      }
      st.cam.theta -= (cur.x - prev.x) * 0.008;
      st.cam.phi = Math.max(0.25, Math.min(1.55, st.cam.phi - (cur.y - prev.y) * 0.006));
    });
    const up = (e) => { pts.delete(e.pointerId); if (pts.size < 2) pinch0 = 0; };
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", (e) => {
      if (!st) return;
      e.preventDefault();
      st.auto = false;
      st.cam.dist = Math.max(6, Math.min(60, st.cam.dist * (e.deltaY < 0 ? 0.9 : 1.1)));
    }, { passive: false });
  }

  // ------------------------------------------------------------------ boucle d'animation
  function loop(t) {
    if (!st) return;
    try {
      const { renderer, scene, camera, canvas, cam, model, stage } = st;
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (w > 10 && h > 10 && (st.w !== w || st.h !== h)) {
        renderer.setSize(w, h, false);
        camera.aspect = w / h; camera.updateProjectionMatrix();
        st.w = w; st.h = h;
      }
      const intro = Math.min(1, (t - st.t0) / 1400);
      const ease = 1 - Math.pow(1 - intro, 3);
      model.holder.scale.y = model.k * Math.max(0.001, ease); // la maquette « se construit » depuis le sol
      if (st.auto) cam.theta += 0.0035;
      const target = new THREE.Vector3(0, model.height * 0.45, 0);
      camera.position.set(
        target.x + cam.dist * Math.sin(cam.phi) * Math.sin(cam.theta),
        target.y + cam.dist * Math.cos(cam.phi),
        target.z + cam.dist * Math.sin(cam.phi) * Math.cos(cam.theta));
      camera.lookAt(target);
      const sweep = ((t / 2600) % 1) * Math.max(model.height, 2);
      const ring = Math.max(1.5, Math.min(7.2, model.radius * 1.35)) / 7.2; // anneau ajusté à l'objet
      stage.scan.scale.setScalar(ring); stage.scanEdge.scale.setScalar(ring);
      stage.scan.position.y = sweep; stage.scanEdge.position.y = sweep;
      stage.scan.material.opacity = 0.03 + 0.03 * Math.sin(t / 300);
      stage.stage.children[0].rotation.y = t / 20000;
      renderer.render(scene, camera);
    } catch (e) {
      if (window.console) console.error("Maquette 3D :", e);
    }
    st.raf = requestAnimationFrame(loop);
  }

  // ------------------------------------------------------------------ ouverture / fermeture
  function disposeScene() {
    if (!st) return;
    cancelAnimationFrame(st.raf);
    st.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
    });
  }

  function close() {
    disposeScene();
    st = null;
    document.getElementById("m3d").classList.add("hidden");
  }

  function fillInfo(ev) {
    document.getElementById("m3d-title").textContent = String(ev.title || "").slice(0, 80);
    document.getElementById("m3d-desc").textContent = String(ev.description || "");
    const facts = document.getElementById("m3d-facts");
    facts.replaceChildren(...(ev.facts || []).map((f) => el("li", "m3d-fact", String(f))));
    const names = [...new Set(ev.parts.map((p) => p.name).filter(Boolean))].slice(0, 16);
    const legend = document.getElementById("m3d-parts");
    legend.replaceChildren(...names.map((n) => {
      const color = (ev.parts.find((p) => p.name === n) || {}).color || "#38d9ff";
      const li = el("li", "m3d-part");
      const dot = el("span", "m3d-dot");
      dot.style.background = color;
      li.append(dot, el("span", "", n));
      return li;
    }));
    document.getElementById("m3d-parts-head").classList.toggle("hidden", !names.length);
  }

  function show(ev) {
    if (!ev || !Array.isArray(ev.parts) || !ev.parts.length) return;
    const box = document.getElementById("m3d");
    box.classList.remove("hidden");
    fillInfo(ev);
    const canvas = document.getElementById("m3d-canvas");
    const warn = document.getElementById("m3d-nogl");
    if (typeof THREE === "undefined" || !webglOk()) { warn.classList.remove("hidden"); return; }
    warn.classList.add("hidden");
    disposeScene();
    const renderer = (st && st.renderer) || window.SyriusModel._renderer ||
      new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    window.SyriusModel._renderer = renderer;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x02060d, 40, 110);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(8, 14, 10);
    scene.add(sun);
    const rim = new THREE.PointLight(HOLO, 60, 40);
    rim.position.set(-8, 6, -8);
    scene.add(rim);
    const stage = buildStage(scene);
    const model = buildModel(ev);
    model.k = model.holder.scale.x;
    scene.add(model.holder);
    const home = Math.max(16, model.height * 1.7, model.radius * 3.2);
    st = { renderer, scene, camera, canvas, stage, model, mode: "color", auto: true, t0: performance.now(),
      cam: { theta: 0.7, phi: 1.15, dist: home, home }, w: 0, h: 0, raf: 0 };
    if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) { st.auto = false; st.t0 -= 1400; }
    applyMode();
    if (!canvas.dataset.bound) { bindControls(canvas); canvas.dataset.bound = "1"; }
    st.raf = requestAnimationFrame(loop);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("m3d-close").addEventListener("click", close);
    document.getElementById("m3d-mode").addEventListener("click", () => {
      if (!st) return;
      st.mode = st.mode === "holo" ? "color" : "holo";
      applyMode();
    });
  });

  window.SyriusModel = { show, close };
})();
