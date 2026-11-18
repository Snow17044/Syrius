// GET /api/programme → le programme de l'association (public)
// PUT /api/programme → le remplacer (code éditeur requis)
import { stockagePret, lireContenu, ecrireContenu, codeValide, repondre, lireCorps, textePropre, lienPropre, paragraphe, imagePropre } from "./_outils.js";

const VIDE = { slogan: "", intro: "", photo: "", lienAdhesion: "", axes: [], maj: null };

// Pas de limite pratique sur les textes : on peut coller tout un programme d'un coup.
function nettoyer(c) {
  const axes = (Array.isArray(c.axes) ? c.axes : []).slice(0, 200).map((a, i) => ({
    id: textePropre(a?.id, 60) || `axe-${i + 1}`,
    icone: textePropre(a?.icone, 16),
    titre: textePropre(a?.titre, 500),
    photo: a?.photo ? imagePropre(a.photo) : "",
    resume: paragraphe(a?.resume, 200000),
    propositions: (Array.isArray(a?.propositions) ? a.propositions : [])
      .map((p) => textePropre(p, 20000)).filter(Boolean).slice(0, 2000),
  })).filter((a) => a.titre);
  return {
    slogan: textePropre(c.slogan, 500),
    intro: paragraphe(c.intro, 200000),
    photo: c.photo ? imagePropre(c.photo) : "",
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
      const programme = nettoyer(await lireCorps(req, 4_000_000));
      await ecrireContenu("programme", programme);
      return repondre(res, 200, { programme });
    }
    return repondre(res, 405, { erreur: "Méthode non prise en charge." });
  } catch (e) {
    return repondre(res, 500, { erreur: e.message || "Erreur inattendue." });
  }
}
