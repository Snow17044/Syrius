// GET /api/espace → place occupée dans la base de données (équipe seulement),
// pour rester dans l'offre gratuite de l'hébergeur.
import { neon } from "@neondatabase/serverless";
import { codeValide, repondre } from "./_outils.js";

const URL_PG = process.env.DATABASE_URL || process.env.POSTGRES_URL;
const sql = URL_PG ? neon(URL_PG) : null;

export default async function handler(req, res) {
  if (!codeValide(req.headers["x-code-editeur"])) return repondre(res, 401, { erreur: "Code éditeur incorrect." });
  if (!sql) return repondre(res, 200, { octets: 0, photos: 0, essai: true });
  try {
    const [r] = await sql`SELECT pg_database_size(current_database())::bigint AS octets,
      (SELECT count(*) FROM pg_class WHERE relname = 'ne_photos') AS existe`;
    const photos = Number(r.existe) ? Number((await sql`SELECT count(*)::int AS n FROM ne_photos`)[0].n) : 0;
    return repondre(res, 200, { octets: Number(r.octets), photos });
  } catch (e) {
    return repondre(res, 500, { erreur: e.message || "Erreur inattendue." });
  }
}
