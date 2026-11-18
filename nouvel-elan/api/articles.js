// GET    /api/articles            → liste publique des articles
// POST   /api/articles            → ajouter un article   (code éditeur requis)
// PATCH  /api/articles            → épingler / modifier   (code éditeur requis)
// DELETE /api/articles?id=...     → supprimer             (code éditeur requis)
import { randomUUID } from "node:crypto";
import {
  stockagePret, lireArticles, enregistrerArticle, lireArticle, supprimerArticle,
  codeValide, repondre, lireCorps, lienPropre, textePropre, paragraphe, imagePropre, supprimerPhoto,
} from "./_outils.js";

export const CATEGORIES = ["Communiqués", "Événements", "Actions de terrain", "Idées & tribunes", "Presse", "Vidéos"];

export default async function handler(req, res) {
  if (!stockagePret()) {
    return repondre(res, 503, { erreur: "La base de données n'est pas encore branchée (voir le guide d'installation)." });
  }
  try {
    if (req.method === "GET") {
      return repondre(res, 200, { articles: await lireArticles(), categories: CATEGORIES });
    }

    const code = req.headers["x-code-editeur"];
    const auteur = codeValide(code);
    if (!auteur) return repondre(res, 401, { erreur: "Code éditeur incorrect." });

    if (req.method === "POST") {
      const c = await lireCorps(req, 1_000_000);
      // Deux sortes de publications : un lien vers un article, ou une publication de l'asso (photo + texte).
      const url = c.url ? lienPropre(c.url) : "";
      if (c.url && !url) return repondre(res, 400, { erreur: "Ce lien n'est pas valide." });
      const texte = paragraphe(c.texte, 200000);
      const image = c.image ? imagePropre(c.image) : "";
      if (!url && !texte && !image) return repondre(res, 400, { erreur: "Ajoute un lien, une photo ou un texte." });
      const titre = textePropre(c.titre, 300) || (url ? new URL(url).hostname : "");
      if (!titre) return repondre(res, 400, { erreur: "Donne un titre à la publication." });
      if (url && (await lireArticles()).some((a) => a.url === url)) return repondre(res, 409, { erreur: "Cet article est déjà dans l'application." });
      const article = {
        id: randomUUID(),
        url,
        titre,
        resume: textePropre(c.resume, 600) || textePropre(texte, 220),
        texte,
        image,
        source: url ? (textePropre(c.source, 80) || new URL(url).hostname.replace(/^www\./, "")) : "Nouvel Élan",
        categorie: CATEGORIES.includes(c.categorie) ? c.categorie : CATEGORIES[0],
        date: new Date().toISOString(),
        epingle: false,
        auteur, // qui a publié (Bureau, Président…), pour s'y retrouver
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
      const a = await lireArticle(id);
      await supprimerArticle(id);
      // La photo envoyée avec la publication est supprimée avec elle.
      const photo = a?.image?.match(/^\/api\/photo\?id=([a-f0-9-]{36})$/);
      if (photo) await supprimerPhoto(photo[1]).catch(() => {});
      return repondre(res, 200, { ok: true });
    }

    return repondre(res, 405, { erreur: "Méthode non prise en charge." });
  } catch (e) {
    return repondre(res, 500, { erreur: e.message || "Erreur inattendue." });
  }
}
