// POST /api/photo        → envoyer une photo (code éditeur requis), renvoie son adresse
// GET  /api/photo?id=…   → afficher la photo (public)
import { randomUUID } from "node:crypto";
import { stockagePret, enregistrerPhoto, lirePhoto, listerPhotos, codeValide, repondre, lireCorps } from "./_outils.js";

const MAX_OCTETS = 3 * 1024 * 1024;

// Reconnaît le format à partir des premiers octets (on ne fait pas confiance à ce que dit le navigateur).
function format(octets) {
  if (octets[0] === 0xff && octets[1] === 0xd8 && octets[2] === 0xff) return "image/jpeg";
  if (octets[0] === 0x89 && octets[1] === 0x50 && octets[2] === 0x4e && octets[3] === 0x47) return "image/png";
  if (octets.subarray(0, 4).toString() === "RIFF" && octets.subarray(8, 12).toString() === "WEBP") return "image/webp";
  return "";
}

export default async function handler(req, res) {
  if (!stockagePret()) return repondre(res, 503, { erreur: "La base de données n'est pas encore branchée." });
  try {
    if (req.method === "GET" && new URL(req.url, "http://x").searchParams.has("liste")) {
      // Galerie des photos déjà envoyées (équipe seulement)
      if (!codeValide(req.headers["x-code-editeur"])) return repondre(res, 401, { erreur: "Code éditeur incorrect." });
      return repondre(res, 200, { photos: (await listerPhotos()).map((p) => ({ url: `/api/photo?id=${p.id}`, cree: p.cree })) });
    }
    if (req.method === "GET") {
      const id = new URL(req.url, "http://x").searchParams.get("id") || "";
      const photo = /^[a-f0-9-]{36}$/.test(id) ? await lirePhoto(id) : null;
      if (!photo) return repondre(res, 404, { erreur: "Photo introuvable." });
      res.statusCode = 200;
      res.setHeader("Content-Type", photo.mime);
      res.setHeader("X-Content-Type-Options", "nosniff");
      res.setHeader("Content-Security-Policy", "default-src 'none'; sandbox");
      res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
      return res.end(Buffer.from(photo.base64, "base64"));
    }
    if (req.method === "POST") {
      if (!codeValide(req.headers["x-code-editeur"])) return repondre(res, 401, { erreur: "Code éditeur incorrect." });
      const { data } = await lireCorps(req, 4_300_000);
      const base64 = String(data || "").replace(/^data:image\/[a-z]+;base64,/, "");
      const octets = Buffer.from(base64, "base64");
      if (!octets.length) return repondre(res, 400, { erreur: "Photo vide." });
      if (octets.length > MAX_OCTETS) return repondre(res, 413, { erreur: "Photo trop lourde (3 Mo maximum)." });
      const mime = format(octets);
      if (!mime) return repondre(res, 415, { erreur: "Format non reconnu (JPEG, PNG ou WebP)." });
      const id = randomUUID();
      await enregistrerPhoto(id, mime, octets.toString("base64"));
      return repondre(res, 201, { url: `/api/photo?id=${id}` });
    }
    return repondre(res, 405, { erreur: "Méthode non prise en charge." });
  } catch (e) {
    return repondre(res, 500, { erreur: e.message || "Erreur inattendue." });
  }
}
