// GET /api/programme → le programme de l'association (public)
// PUT /api/programme → le remplacer (code éditeur requis)
import { stockagePret, lireContenu, ecrireContenu, codeValide, repondre, lireCorps, textePropre, lienPropre } from "./_outils.js";

const VIDE = { slogan: "", intro: "", lienAdhesion: "", axes: [], maj: null };

// Garde un texte de plusieurs lignes lisible (paragraphes), sans caractères de contrôle.
function paragraphe(t, max) {
  return String(t ?? "").replace(/\r/g, "").replace(/[\u0000-\u0009\u000b-\u001f\u007f]+/g, " ")
    .replace(/\n{3,}/g, "\n\n").trim().slice(0, max);
}

function nettoyer(c) {
  const axes = (Array.isArray(c.axes) ? c.axes : []).slice(0, 20).map((a, i) => ({
    id: textePropre(a?.id, 40) || `axe-${i + 1}`,
    icone: textePropre(a?.icone, 8),
    titre: textePropre(a?.titre, 120),
    resume: paragraphe(a?.resume, 1500),
    propositions: (Array.isArray(a?.propositions) ? a.propositions : [])
      .map((p) => textePropre(p, 400)).filter(Boolean).slice(0, 40),
  })).filter((a) => a.titre);
  return {
    slogan: textePropre(c.slogan, 140),
    intro: paragraphe(c.intro, 3000),
    lienAdhesion: c.lienAdhesion ? lienPropre(c.lienAdhesion) : "",
    axes,
    maj: new Date().toISOString(),
  };
}

export default async function handler(req, res) {
  if (!stockagePret()) return repondre(res, 503, { erreur: "La base de données n'est pas encore branchée." });
  try {
    if (req.method === "GET") return repondre(res, 200, { programme: (await lireContenu("programme")) || VIDE });
    if (req.method === "PUT") {
      if (!codeValide(req.headers["x-code-editeur"])) return repondre(res, 401, { erreur: "Code éditeur incorrect." });
      const programme = nettoyer(await lireCorps(req));
      await ecrireContenu("programme", programme);
      return repondre(res, 200, { programme });
    }
    return repondre(res, 405, { erreur: "Méthode non prise en charge." });
  } catch (e) {
    return repondre(res, 500, { erreur: e.message || "Erreur inattendue." });
  }
}
