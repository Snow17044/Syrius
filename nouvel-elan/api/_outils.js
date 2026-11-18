// Outils communs aux fonctions serveur de Nouvel Élan (stockage + réponses).
import { timingSafeEqual, createHash } from "node:crypto";
import { neon } from "@neondatabase/serverless";

const URL_REDIS = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const JETON_REDIS = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
const CLE = "nouvel-elan:articles";
// Base Postgres (Neon), branchée depuis l'onglet Storage de Vercel.
const URL_PG = process.env.DATABASE_URL || process.env.POSTGRES_URL;
const sql = URL_PG ? neon(URL_PG) : null;
let tablePrete = null;
function pg() {
  tablePrete ??= sql`CREATE TABLE IF NOT EXISTS ne_articles (id text PRIMARY KEY, donnees jsonb NOT NULL)`
    .catch((e) => { tablePrete = null; throw e; });
  return tablePrete;
}

// Stockage en mémoire, uniquement pour les essais sur ordinateur (NE_DEV=1).
const memoire = new Map();

export function stockagePret() {
  return Boolean(sql || (URL_REDIS && JETON_REDIS) || process.env.NE_DEV === "1");
}

async function redis(commande) {
  const r = await fetch(URL_REDIS, {
    method: "POST",
    headers: { Authorization: `Bearer ${JETON_REDIS}`, "Content-Type": "application/json" },
    body: JSON.stringify(commande),
  });
  if (!r.ok) throw new Error(`Base de données : erreur ${r.status}`);
  const d = await r.json();
  if (d.error) throw new Error(`Base de données : ${d.error}`);
  return d.result;
}

export async function lireArticles() {
  let valeurs;
  if (sql) {
    await pg();
    valeurs = (await sql`SELECT donnees::text AS v FROM ne_articles`).map((r) => r.v);
  } else if (URL_REDIS && JETON_REDIS) {
    const plat = (await redis(["HGETALL", CLE])) || [];
    valeurs = plat.filter((_, i) => i % 2 === 1);
  } else {
    valeurs = [...memoire.values()];
  }
  return valeurs
    .map((v) => { try { return JSON.parse(v); } catch { return null; } })
    .filter(Boolean)
    .sort((a, b) => (b.epingle - a.epingle) || b.date.localeCompare(a.date));
}

export async function enregistrerArticle(a) {
  const v = JSON.stringify(a);
  if (sql) { await pg(); await sql`INSERT INTO ne_articles (id, donnees) VALUES (${a.id}, ${v}::jsonb) ON CONFLICT (id) DO UPDATE SET donnees = EXCLUDED.donnees`; return; }
  if (URL_REDIS && JETON_REDIS) await redis(["HSET", CLE, a.id, v]);
  else memoire.set(a.id, v);
}

export async function lireArticle(id) {
  if (sql) { await pg(); const r = await sql`SELECT donnees::text AS v FROM ne_articles WHERE id = ${id}`; return r[0] ? JSON.parse(r[0].v) : null; }
  const v = URL_REDIS && JETON_REDIS ? await redis(["HGET", CLE, id]) : memoire.get(id);
  return v ? JSON.parse(v) : null;
}

export async function supprimerArticle(id) {
  if (sql) { await pg(); await sql`DELETE FROM ne_articles WHERE id = ${id}`; return; }
  if (URL_REDIS && JETON_REDIS) await redis(["HDEL", CLE, id]);
  else memoire.delete(id);
}

// Contenus uniques (le programme) : une valeur JSON par nom.
const memoireContenu = new Map();
let tableContenu = null;
function pgContenu() {
  tableContenu ??= sql`CREATE TABLE IF NOT EXISTS ne_contenu (cle text PRIMARY KEY, donnees jsonb NOT NULL)`
    .catch((e) => { tableContenu = null; throw e; });
  return tableContenu;
}

export async function lireContenu(nom) {
  let v;
  if (sql) { await pgContenu(); v = (await sql`SELECT donnees::text AS v FROM ne_contenu WHERE cle = ${nom}`)[0]?.v; }
  else if (URL_REDIS && JETON_REDIS) v = await redis(["GET", `nouvel-elan:${nom}`]);
  else v = memoireContenu.get(nom);
  return v ? JSON.parse(v) : null;
}

export async function ecrireContenu(nom, valeur) {
  const v = JSON.stringify(valeur);
  if (sql) { await pgContenu(); await sql`INSERT INTO ne_contenu (cle, donnees) VALUES (${nom}, ${v}::jsonb) ON CONFLICT (cle) DO UPDATE SET donnees = EXCLUDED.donnees`; }
  else if (URL_REDIS && JETON_REDIS) await redis(["SET", `nouvel-elan:${nom}`, v]);
  else memoireContenu.set(nom, v);
}

// Photos : rangées dans la base (texte base64), servies par /api/photo?id=…
const memoirePhotos = new Map();
let tablePhotos = null;
function pgPhotos() {
  tablePhotos ??= sql`CREATE TABLE IF NOT EXISTS ne_photos (id text PRIMARY KEY, mime text NOT NULL, donnees text NOT NULL, cree timestamptz DEFAULT now())`
    .catch((e) => { tablePhotos = null; throw e; });
  return tablePhotos;
}

export async function enregistrerPhoto(id, mime, base64) {
  if (sql) { await pgPhotos(); await sql`INSERT INTO ne_photos (id, mime, donnees) VALUES (${id}, ${mime}, ${base64})`; }
  else if (URL_REDIS && JETON_REDIS) await redis(["SET", `nouvel-elan:photo:${id}`, JSON.stringify({ mime, base64 })]);
  else memoirePhotos.set(id, { mime, base64 });
}

export async function lirePhoto(id) {
  if (sql) { await pgPhotos(); const r = await sql`SELECT mime, donnees FROM ne_photos WHERE id = ${id}`; return r[0] ? { mime: r[0].mime, base64: r[0].donnees } : null; }
  if (URL_REDIS && JETON_REDIS) { const v = await redis(["GET", `nouvel-elan:photo:${id}`]); return v ? JSON.parse(v) : null; }
  return memoirePhotos.get(id) || null;
}

export async function supprimerPhoto(id) {
  if (sql) { await pgPhotos(); await sql`DELETE FROM ne_photos WHERE id = ${id}`; }
  else if (URL_REDIS && JETON_REDIS) await redis(["DEL", `nouvel-elan:photo:${id}`]);
  else memoirePhotos.delete(id);
}

// Adresse d'une photo : lien web classique, ou photo envoyée dans l'appli.
export function imagePropre(t) {
  const s = String(t ?? "").trim();
  if (/^\/api\/photo\?id=[a-f0-9-]{36}$/.test(s)) return s;
  return lienPropre(s);
}

// Vérifie le code éditeur sans révéler d'indice par le temps de réponse.
export function codeValide(code) {
  const attendu = process.env.NE_CODE_EDITEUR || (process.env.NE_DEV === "1" ? "elan" : "");
  if (!attendu || typeof code !== "string" || !code) return false;
  const h = (s) => createHash("sha256").update(s).digest();
  return timingSafeEqual(h(code), h(attendu));
}

export function repondre(res, statut, donnees) {
  res.statusCode = statut;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(donnees));
}

export async function lireCorps(req, max = 100000) {
  if (req.body !== undefined && req.body !== null) {
    return typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body;
  }
  let brut = "";
  for await (const morceau of req) {
    brut += morceau;
    if (brut.length > max) throw new Error("Envoi trop gros");
  }
  return brut ? JSON.parse(brut) : {};
}

// N'accepte que des liens web classiques (http/https).
export function lienPropre(texte, max = 2000) {
  try {
    const u = new URL(String(texte).trim());
    if (u.protocol !== "http:" && u.protocol !== "https:") return "";
    const s = u.toString();
    return s.length <= max ? s : "";
  } catch {
    return "";
  }
}

export function paragraphe(t, max) {
  return String(t ?? "").replace(/\r/g, "").replace(/[\u0000-\u0009\u000b-\u001f\u007f]+/g, " ")
    .replace(/\n{3,}/g, "\n\n").trim().slice(0, max);
}

export function textePropre(t, max) {
  return String(t ?? "").replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}
