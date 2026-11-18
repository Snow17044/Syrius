// GET    /api/articles            → liste publique des articles
// POST   /api/articles            → ajouter un article   (code éditeur requis)
// PATCH  /api/articles            → épingler / modifier   (code éditeur requis)
// DELETE /api/articles?id=...     → supprimer             (code éditeur requis)
import { randomUUID } from "node:crypto";
import {
  stockagePret, lireArticles, enregistrerArticle, lireArticle, supprimerArticle,
  codeValide, repondre, lireCorps, lienPropre, textePropre,
} from "./_outils.js";

export const CATEGORIES = ["Actualités", "Événements", "Idées & tribunes", "Presse", "Vidéos"];

export default async function handler(req, res) {
  if (!stockagePret()) {
    return repondre(res, 503, { erreur: "La base de données n'est pas encore branchée (voir le guide d'installation)." });
  }
  try {
    if (req.method === "GET") {
      return repondre(res, 200, { articles: await lireArticles(), categories: CATEGORIES });
    }

    const code = req.headers["x-code-editeur"];
    if (!codeValide(code)) return repondre(res, 401, { erreur: "Code éditeur incorrect." });

    if (req.method === "POST") {
      const c = await lireCorps(req);
      const url = lienPropre(c.url);
      if (!url) return repondre(res, 400, { erreur: "Ce lien n'est pas valide." });
      const existants = await lireArticles();
      if (existants.some((a) => a.url === url)) return repondre(res, 409, { erreur: "Cet article est déjà dans l'application." });
      const article = {
        id: randomUUID(),
        url,
        titre: textePropre(c.titre, 200) || new URL(url).hostname,
        resume: textePropre(c.resume, 400),
        image: c.image ? lienPropre(c.image) : "",
        source: textePropre(c.source, 80) || new URL(url).hostname.replace(/^www\./, ""),
        categorie: CATEGORIES.includes(c.categorie) ? c.categorie : CATEGORIES[0],
        date: new Date().toISOString(),
        epingle: false,
      };
      await enregistrerArticle(article);
      return repondre(res, 201, { article });
    }

    if (req.method === "PATCH") {
      const c = await lireCorps(req);
      const a = await lireArticle(String(c.id || ""));
      if (!a) return repondre(res, 404, { erreur: "Article introuvable." });
      if (typeof c.epingle === "boolean") a.epingle = c.epingle;
      if (c.titre !== undefined) a.titre = textePropre(c.titre, 200) || a.titre;
      if (CATEGORIES.includes(c.categorie)) a.categorie = c.categorie;
      await enregistrerArticle(a);
      return repondre(res, 200, { article: a });
    }

    if (req.method === "DELETE") {
      const id = new URL(req.url, "http://x").searchParams.get("id") || "";
      await supprimerArticle(id);
      return repondre(res, 200, { ok: true });
    }

    return repondre(res, 405, { erreur: "Méthode non prise en charge." });
  } catch (e) {
    return repondre(res, 500, { erreur: e.message || "Erreur inattendue." });
  }
}
