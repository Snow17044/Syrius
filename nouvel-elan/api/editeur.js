// GET /api/editeur → vérifie un code ou un lien d'accès et dit qui est connecté.
import { codeValide, estBureau, repondre } from "./_outils.js";

export default function handler(req, res) {
  const code = req.headers["x-code-editeur"];
  const nom = codeValide(code);
  if (!nom) return repondre(res, 401, { erreur: "Ce lien d'accès n'est pas valide (ou il a été désactivé)." });
  return repondre(res, 200, { nom, programme: estBureau(code) });
}
