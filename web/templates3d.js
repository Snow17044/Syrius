// Maquettes 3D soignées pour les objets les plus demandés (dessinées à la main, pas par l'IA).
// Chaque modèle renvoie une liste de pièces au même format que celles validées par le serveur.
"use strict";

(function () {
  const P = (shape, pos, size, color, extra) => Object.assign({ shape, pos, size, color, rot: [0, 0, 0] }, extra || {});
  const range = (n) => Array.from({ length: n }, (_, i) => i);

  function arcPoints(x0, x1, z, peak, base) { // arche (demi-ellipse) dans un plan z = constante
    return range(13).map((i) => {
      const t = i / 12, a = Math.PI * t;
      return [x0 + (x1 - x0) * t, base + Math.sin(a) * peak, z];
    });
  }

  const T = {
    tour_eiffel() {
      const bronze = "#9a6b45", dark = "#6e4a2f";
      // silhouette à 4 faces (tour à 4 segments) en treillis métallique
      const profile = [[62, 0], [52, 20], [44, 40], [36, 57], [30, 70], [22, 95], [17, 115], [13, 140],
        [10, 170], [7.5, 205], [5.5, 240], [4, 270], [2.5, 285], [1.2, 300]];
      const parts = [
        P("lathe", [0, 0, 0], [1, 1, 1], bronze, { points: profile, segments: 4, wire: true, rot: [0, 45, 0] }),
        P("lathe", [0, 0, 0], [1, 1, 1], dark, { points: profile.map(([r, y]) => [r * 0.92, y]), segments: 4, rot: [0, 45, 0] }),
        P("box", [0, 57, 0], [74, 5, 74], "#b0855c"),
        P("box", [0, 115, 0], [40, 4, 40], "#b0855c"),
        P("box", [0, 276, 0], [10, 7, 10], "#c49a6c"),
        P("cylinder", [0, 312, 0], [0.4, 26, 0.8], "#c0c7d0"),
      ];
      // grandes arches entre les piliers, sur les 4 faces
      [[-1, 0], [1, 0], [0, -1], [0, 1]].forEach(([fx, fz]) => {
        const pts = arcPoints(-40, 40, 0, 34, 0).map(([x, y]) => (fx ? [fx * 46, y, x] : [x, y, fz * 46]));
        parts.push(P("tube", [0, 0, 0], [1.6], bronze, { points: pts }));
      });
      return parts;
    },

    pyramide() {
      return [
        P("box", [40, -1, 0], [330, 2, 300], "#e2c98f"),
        P("pyramid", [0, 73, 0], [230, 146, 230], "#d8b46a", { name: "Grande pyramide" }),
        P("pyramid", [170, 20, -120], [56, 40, 56], "#cfa95f", { name: "Pyramide de reine" }),
        P("pyramid", [170, 20, -40], [52, 38, 52], "#cfa95f"),
        P("pyramid", [170, 20, 40], [48, 36, 48], "#cfa95f"),
        P("pyramid", [0, 141, 0], [12, 10, 12], "#f2dfa8", { name: "Pyramidion" }),
      ];
    },

    fusee() {
      const body = [[0, 0], [3.2, 0], [3.4, 4], [3.4, 40], [3.2, 46], [2.6, 52], [1.6, 57], [0.6, 60], [0, 61]];
      const parts = [
        P("lathe", [0, 6, 0], [1, 1, 1], "#f1f5f9", { points: body, segments: 40, name: "Corps" }),
        P("lathe", [0, 52, 0], [1, 1, 1], "#e63946", { points: [[2.62, 0], [1.6, 5], [0.6, 8], [0, 9]], segments: 40, name: "Coiffe" }),
        P("lathe", [0, 0, 0], [1, 1, 1], "#94a3b8", { points: [[1.6, 6], [2.2, 3], [2.8, 0], [0, 0]], segments: 32, name: "Tuyère" }),
        P("cylinder", [0, 30, 3.35], [1, 0.2, 1], "#3a86ff", { rot: [90, 0, 0], name: "Hublot" }),
        P("cylinder", [0, 36, 3.35], [1, 0.2, 1], "#3a86ff", { rot: [90, 0, 0] }),
        P("torus", [0, 46, 0], [3.25, 0.25], "#e63946"),
        P("torus", [0, 12, 0], [3.45, 0.25], "#e63946"),
      ];
      [0, 90, 180, 270].forEach((deg) => parts.push(P("extrude", [0, 6, 0], [1, 1, 0.4], "#e63946",
        { points: [[3.2, 0], [7.5, -6], [7.5, -2], [3.2, 9]], axis: "z", rot: [0, deg, 0], name: "Aileron" })));
      return parts;
    },

    voiture() {
      const profile = [[-2.2, 0.35], [2.25, 0.35], [2.3, 0.75], [2.15, 0.95], [1.1, 1.05], [0.55, 1.5], [-0.9, 1.55],
        [-1.6, 1.1], [-2.25, 1.0], [-2.3, 0.6]];
      const parts = [
        P("extrude", [0, 0, 0], [1, 1, 1.8], "#d62839", { points: profile, axis: "z", name: "Carrosserie" }),
        P("extrude", [0.02, 0.02, 0], [1, 1, 1.82], "#9fd8ff", { points: [[0.5, 1.1], [1.0, 1.1], [0.52, 1.45], [-0.8, 1.5], [-1.45, 1.12]], axis: "z", name: "Vitres" }),
        P("box", [2.28, 0.8, 0.55], [0.06, 0.15, 0.35], "#ffd166", { name: "Phares", sym: "z" }),
        P("box", [2.28, 0.8, -0.55], [0.06, 0.15, 0.35], "#ffd166"),
        P("box", [-2.28, 0.85, 0.6], [0.06, 0.12, 0.3], "#ff4d6d"),
        P("box", [-2.28, 0.85, -0.6], [0.06, 0.12, 0.3], "#ff4d6d"),
      ];
      [[1.45, 0.92], [1.45, -0.92], [-1.4, 0.92], [-1.4, -0.92]].forEach(([x, z]) => {
        parts.push(P("cylinder", [x, 0.36, z], [0.36, 0.26, 0.36], "#1f2937", { rot: [90, 0, 0], name: "Roue" }));
        parts.push(P("cylinder", [x, 0.36, z + Math.sign(z) * 0.135], [0.2, 0.02, 0.2], "#c0c7d0", { rot: [90, 0, 0] }));
      });
      return parts;
    },

    maison() {
      return [
        P("box", [0, 3, 0], [10, 6, 8], "#f1e3c6", { name: "Murs" }),
        P("extrude", [0, 6, 0], [1, 1, 8.6], "#b5442f", { points: [[-5.6, 0], [5.6, 0], [0, 4]], axis: "z", name: "Toit" }),
        P("box", [0, 1.4, 4.02], [1.6, 2.8, 0.1], "#7a4b2a", { name: "Porte" }),
        P("box", [-3, 3.4, 4.02], [1.6, 1.4, 0.08], "#9fd8ff", { name: "Fenêtres" }),
        P("box", [3, 3.4, 4.02], [1.6, 1.4, 0.08], "#9fd8ff"),
        P("box", [3, 8.3, -1.5], [1, 3, 1], "#8d5524", { name: "Cheminée" }),
        P("box", [0, -0.05, 2], [18, 0.1, 16], "#6fbf73", { name: "Jardin" }),
      ];
    },

    avion() {
      return [
        P("capsule", [0, 3, 0], [1.6, 26, 1], "#f1f5f9", { rot: [0, 0, 90], name: "Fuselage" }),
        P("extrude", [0, 2.6, 0], [1, 0.5, 1], "#cbd5e1", { points: [[2, -1.4], [-3, -15], [-5.5, -15], [-3, -1.4], [-3, 1.4], [-5.5, 15], [-3, 15], [2, 1.4]], name: "Ailes" }),
        P("extrude", [0, 3.4, 0], [1, 0.3, 1], "#cbd5e1", { points: [[-11, -0.6], [-14.5, -5], [-15.5, -5], [-14, -0.6], [-14, 0.6], [-15.5, 5], [-14.5, 5], [-11, 0.6]], name: "Empennage" }),
        P("extrude", [0, 4, 0], [1, 1, 0.3], "#3a86ff", { points: [[-10.5, 0], [-15.5, 5.5], [-14, 5.5], [-12.5, 0]], axis: "z", name: "Dérive" }),
        P("cylinder", [-1, 1.9, -5.5], [0.8, 3, 0.8], "#94a3b8", { rot: [0, 0, 90], name: "Réacteurs" }),
        P("cylinder", [-1, 1.9, 5.5], [0.8, 3, 0.8], "#94a3b8", { rot: [0, 0, 90] }),
        P("sphere", [12.6, 3.3, 0], [0.9], "#1e3a5f", { name: "Cockpit" }),
      ];
    },

    arbre() {
      const parts = [P("cylinder", [0, 3, 0], [0.6, 6, 0.9], "#7a4b2a", { name: "Tronc" })];
      [[0, 8, 0, 3.6], [2.2, 6.6, 0.8, 2.6], [-2, 6.8, -0.6, 2.7], [0.6, 6.4, -2.2, 2.4], [-0.8, 6.3, 2.1, 2.4],
        [0.3, 10.2, 0.2, 2.4]].forEach(([x, y, z, r], i) =>
        parts.push(P("sphere", [x, y, z], [r], i % 2 ? "#3f8f4a" : "#2e7d3a", { name: i ? undefined : "Feuillage" })));
      parts.push(P("cylinder", [0, 0.02, 0], [5, 0.04, 5], "#6fbf73"));
      return parts;
    },

    atome() {
      const parts = [];
      [[0, 0, 0], [0.9, 0.3, 0.2], [-0.6, 0.7, -0.4], [0.3, -0.8, 0.5], [-0.5, -0.4, 0.8], [0.6, 0.5, -0.8],
        [-0.9, -0.2, -0.3]].forEach((p, i) => parts.push(P("sphere", p, [0.65], i % 2 ? "#e63946" : "#3a86ff", { name: i < 2 ? (i ? "Neutrons" : "Protons") : undefined })));
      [[90, 0, 0], [30, 60, 0], [-30, -60, 0]].forEach((rot, i) => {
        parts.push(P("torus", [0, 0, 0], [6, 0.05], "#38d9ff", { rot, name: i ? undefined : "Orbites" }));
      });
      parts.push(P("sphere", [6, 0, 0], [0.35], "#ffd166", { name: "Électrons" }));
      parts.push(P("sphere", [-3, 2.6, 4.2], [0.35], "#ffd166"));
      parts.push(P("sphere", [-3, -2.6, -4.2], [0.35], "#ffd166"));
      return parts;
    },

    systeme_solaire() {
      // échelle « lisible » (les vraies distances rendraient les planètes invisibles)
      const planets = [["Mercure", 4.2, 0.45, "#a8a29e"], ["Vénus", 5.6, 0.7, "#e9c46a"], ["Terre", 7.1, 0.75, "#3a86ff"],
        ["Mars", 8.5, 0.6, "#e76f51"], ["Jupiter", 10.6, 1.5, "#d4a373"], ["Saturne", 13, 1.25, "#e9d8a6"],
        ["Uranus", 15, 0.95, "#8ecae6"], ["Neptune", 16.8, 0.9, "#4361ee"]];
      const parts = [P("sphere", [0, 2, 0], [2.6], "#ffb703", { name: "Soleil" })];
      planets.forEach(([name, d, r, c], i) => {
        const a = i * 0.8;
        parts.push(P("torus", [0, 2, 0], [d, 0.03], "#38d9ff", { rot: [90, 0, 0] }));
        parts.push(P("sphere", [Math.cos(a) * d, 2, Math.sin(a) * d], [r], c, { name }));
        if (name === "Saturne") parts.push(P("torus", [Math.cos(a) * d, 2, Math.sin(a) * d], [2.1, 0.25], "#d6c38f", { rot: [70, 0, 20] }));
      });
      return parts;
    },

    molecule_eau() {
      return [
        // angle H-O-H réel : 104,5°
        P("sphere", [0, 3, 0], [0.9], "#e63946", { name: "Oxygène" }),
        P("sphere", [2.3, 1.2, 0], [0.55], "#f1f5f9", { name: "Hydrogène" }),
        P("sphere", [-2.3, 1.2, 0], [0.55], "#f1f5f9"),
        P("tube", [0, 0, 0], [0.16], "#cbd5e1", { points: [[0, 3, 0], [2.3, 1.2, 0]], name: "Liaisons" }),
        P("tube", [0, 0, 0], [0.16], "#cbd5e1", { points: [[0, 3, 0], [-2.3, 1.2, 0]] }),
      ];
    },

    adn() {
      const a = [], b = [], parts = [];
      range(41).forEach((i) => {
        const t = i * 0.32, y = i * 0.5;
        a.push([Math.cos(t) * 2, y, Math.sin(t) * 2]);
        b.push([Math.cos(t + Math.PI) * 2, y, Math.sin(t + Math.PI) * 2]);
      });
      parts.push(P("tube", [0, 0, 0], [0.22], "#38d9ff", { points: a, name: "Brin 1" }));
      parts.push(P("tube", [0, 0, 0], [0.22], "#9b5de5", { points: b, name: "Brin 2" }));
      const bases = ["#e63946", "#ffd166", "#2a9d8f", "#f4a261"];
      for (let i = 0; i < 41; i += 2) parts.push(P("tube", [0, 0, 0], [0.12], bases[(i / 2) % 4], { points: [a[i], b[i]], name: i ? undefined : "Bases" }));
      return parts;
    },

    phare() {
      const parts = [P("cylinder", [0, 0.5, 0], [6, 1, 6.5], "#94a3b8", { name: "Rocher" })];
      range(6).forEach((i) => {
        const y = 1 + i * 4, r0 = 3.2 - i * 0.28, r1 = 3.2 - (i + 1) * 0.28;
        parts.push(P("lathe", [0, y, 0], [1, 1, 1], i % 2 ? "#f1f5f9" : "#e63946", { points: [[r0, 0], [r1, 4]], segments: 40, name: i ? undefined : "Tour" }));
      });
      parts.push(P("cylinder", [0, 25.4, 0], [2.4, 0.4, 2.4], "#1f2937", { name: "Galerie" }));
      parts.push(P("torus", [0, 26.2, 0], [2.3, 0.06], "#1f2937"));
      parts.push(P("cylinder", [0, 27.4, 0], [1.4, 2.6, 1.4], "#ffe08a", { name: "Lanterne" }));
      parts.push(P("sphere", [0, 28.9, 0], [1.4], "#1f2937", { name: "Dôme" }));
      return parts;
    },
  };

  window.SyriusTemplates3D = T;
})();
