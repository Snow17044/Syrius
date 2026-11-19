// Demandes d'adhésion.
// POST   /api/adhesion          → envoyer une demande (public, avec consentement)
// GET    /api/adhesion          → liste des demandes (équipe seulement)
// PATCH  /api/adhesion          → changer le statut d'une demande (équipe)
// DELETE /api/adhesion?id=…     → supprimer une demande (équipe) — droit à l'effacement
//
// Données sensibles (opinions politiques, RGPD art. 9) : le minimum est demandé, rien n'est
// public, et les demandes restées sans suite sont effacées au bout de 12 mois.
import { randomUUID, createHash } from "node:crypto";
import { neon } from "@neondatabase/serverless";
import { codeValide, repondre, lireCorps, textePropre, paragraphe } from "./_outils.js";

const URL_PG = process.env.DATABASE_URL || process.env.POSTGRES_URL;
const sql = URL_PG ? neon(URL_PG) : null;
const memoire = new Map(); // essais sur ordinateur uniquement (NE_DEV=1)
const STATUTS = ["nouvelle", "contactee", "membre", "refusee"];
const AGES = ["moins16", "16-17", "18plus"];

let table = null;
function pg() {
  table ??= sql`CREATE TABLE IF NOT EXISTS ne_adhesions (id text PRIMARY KEY, donnees jsonb NOT NULL, empreinte text, cree timestamptz DEFAULT now())`
    .catch((e) => { table = null; throw e; });
  return table;
}

// Empreinte de l'adresse IP (jamais l'IP elle-même), uniquement pour limiter les envois en rafale.
function empreinte(req) {
  const ip = String(req.headers["x-forwarded-for"] || req.socket?.remoteAddress || "").split(",")[0].trim();
  return createHash("sha256").update(`${ip}|${new Date().toISOString().slice(0, 10)}|nouvel-elan`).digest("hex").slice(0, 32);
}

async function enregistrer(a, emp) {
  if (sql) { await pg(); await sql`INSERT INTO ne_adhesions (id, donnees, empreinte) VALUES (${a.id}, ${JSON.stringify(a)}::jsonb, ${emp})`; }
  else memoire.set(a.id, { a, emp, cree: Date.now() });
}
async function envoisRecents(emp) {
  if (sql) { await pg(); return Number((await sql`SELECT count(*)::int AS n FROM ne_adhesions WHERE empreinte = ${emp} AND cree > now() - interval '1 hour'`)[0].n); }
  return [...memoire.values()].filter((x) => x.emp === emp && Date.now() - x.cree < 3600000).length;
}
async function lister() {
  if (sql) {
    await pg();
    // Effacement automatique : demandes sans suite de plus de 12 mois
    await sql`DELETE FROM ne_adhesions WHERE cree < now() - interval '12 months' AND donnees->>'statut' IN ('nouvelle', 'contactee', 'refusee')`;
    return (await sql`SELECT donnees FROM ne_adhesions ORDER BY cree DESC`).map((r) => r.donnees);
  }
  return [...memoire.values()].map((x) => x.a).reverse();
}
async function lire(id) {
  if (sql) { await pg(); return (await sql`SELECT donnees FROM ne_adhesions WHERE id = ${id}`)[0]?.donnees || null; }
  return memoire.get(id)?.a || null;
}
async function maj(a) {
  if (sql) { await pg(); await sql`UPDATE ne_adhesions SET donnees = ${JSON.stringify(a)}::jsonb WHERE id = ${a.id}`; }
  else if (memoire.has(a.id)) memoire.get(a.id).a = a;
}
async function supprimer(id) {
  if (sql) { await pg(); await sql`DELETE FROM ne_adhesions WHERE id = ${id}`; }
  else memoire.delete(id);
}

export default async function handler(req, res) {
  if (!sql && process.env.NE_DEV !== "1") return repondre(res, 503, { erreur: "La base de données n'est pas encore branchée." });
  try {
    if (req.method === "POST") {
      const c = await lireCorps(req, 20000);
      // Pièges à robots : champ caché rempli, ou formulaire envoyé trop vite
      if (c.site || (Number(c.ouvertDepuis) || 0) < 3000) return repondre(res, 400, { erreur: "Envoi refusé. Réessaie dans quelques secondes." });
      const prenom = textePropre(c.prenom, 60), nom = textePropre(c.nom, 60), ville = textePropre(c.ville, 80);
      const email = textePropre(c.email, 120).toLowerCase();
      const telephone = textePropre(c.telephone, 25).replace(/[^\d+ .-]/g, "");
      const age = AGES.includes(c.age) ? c.age : "";
      if (!prenom || !nom || !ville || !age) return repondre(res, 400, { erreur: "Remplis tous les champs obligatoires." });
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return repondre(res, 400, { erreur: "Cette adresse e-mail n'est pas valide." });
      if (c.consentement !== true) return repondre(res, 400, { erreur: "Il faut cocher la case d'accord pour envoyer ta demande." });
      if (age === "moins16" && c.accordParent !== true) return repondre(res, 400, { erreur: "Avant 16 ans, il faut l'accord d'un parent." });
      const emp = empreinte(req);
      if ((await envoisRecents(emp)) >= 5) return repondre(res, 429, { erreur: "Trop de demandes envoyées. Réessaie plus tard." });
      await enregistrer({
        id: randomUUID(), prenom, nom, email, telephone, ville, age,
        accordParent: age === "moins16" ? true : undefined,
        message: paragraphe(c.message, 1500),
        consentement: new Date().toISOString(),
        statut: "nouvelle", date: new Date().toISOString(),
      }, emp);
      return repondre(res, 201, { ok: true });
    }

    // Tout le reste est réservé à l'équipe
    if (!codeValide(req.headers["x-code-editeur"])) return repondre(res, 401, { erreur: "Code éditeur incorrect." });
    if (req.method === "GET") return repondre(res, 200, { demandes: await lister() });
    if (req.method === "PATCH") {
      const c = await lireCorps(req, 2000);
      const a = await lire(String(c.id || ""));
      if (!a) return repondre(res, 404, { erreur: "Demande introuvable." });
      if (STATUTS.includes(c.statut)) a.statut = c.statut;
      await maj(a);
      return repondre(res, 200, { demande: a });
    }
    if (req.method === "DELETE") {
      await supprimer(new URL(req.url, "http://x").searchParams.get("id") || "");
      return repondre(res, 200, { ok: true });
    }
    return repondre(res, 405, { erreur: "Méthode non prise en charge." });
  } catch (e) {
    return repondre(res, 500, { erreur: e.message || "Erreur inattendue." });
  }
}
