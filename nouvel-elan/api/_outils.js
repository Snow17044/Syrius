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
  else memoirePhotos.set(id, { mime, base64, cree: new Date().toISOString() });
}

export async function lirePhoto(id) {
  if (sql) { await pgPhotos(); const r = await sql`SELECT mime, donnees FROM ne_photos WHERE id = ${id}`; return r[0] ? { mime: r[0].mime, base64: r[0].donnees } : null; }
  if (URL_REDIS && JETON_REDIS) { const v = await redis(["GET", `nouvel-elan:photo:${id}`]); return v ? JSON.parse(v) : null; }
  return memoirePhotos.get(id) || null;
}

// Liste des photos envoyées (les plus récentes d'abord), pour pouvoir les réutiliser.
export async function listerPhotos() {
  if (sql) { await pgPhotos(); return (await sql`SELECT id, cree FROM ne_photos ORDER BY cree DESC LIMIT 300`).map((r) => ({ id: r.id, cree: r.cree })); }
  if (URL_REDIS && JETON_REDIS) return []; // non disponible avec Redis
  return [...memoirePhotos.entries()].map(([id, p]) => ({ id, cree: p.cree })).reverse();
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

// Point de cadrage d'une photo, ex. "40% 25%".
export function positionPropre(t) {
  const m = String(t ?? "").match(/^(\d{1,3})% (\d{1,3})%$/);
  return m && +m[1] <= 100 && +m[2] <= 100 ? `${+m[1]}% ${+m[2]}%` : "";
}

// Codes d'accès, comparés sans révéler d'indice par le temps de réponse.
const empreinte = (s) => createHash("sha256").update(String(s)).digest();
const egal = (a, b) => timingSafeEqual(empreinte(a), empreinte(b));

// Code principal (bureau) : tous les droits, y compris le programme.
function codeBureau() {
  return process.env.NE_CODE_EDITEUR || (process.env.NE_DEV === "1" ? "elan" : "");
}

// Liens personnels de l'équipe : NE_CODES_EQUIPE = "Président:jeton1,Secrétaire:jeton2"
// Chaque personne a son propre lien ; on en coupe un en retirant sa ligne, sans toucher aux autres.
function codesEquipe() {
  const brut = process.env.NE_CODES_EQUIPE || (process.env.NE_DEV === "1" ? "Président:essai-president,Secrétaire:essai-secretaire" : "");
  return brut.split(",").map((x) => x.trim()).filter(Boolean).map((x) => {
    const i = x.lastIndexOf(":");
    return { nom: x.slice(0, i).trim(), jeton: x.slice(i + 1).trim() };
  }).filter((x) => x.nom && (x.jeton.length >= 16 || process.env.NE_DEV === "1"));
}

// Renvoie qui publie (« Bureau », « Président »…) ou "" si le code est faux.
export function codeValide(code) {
  if (typeof code !== "string" || !code) return "";
  if (codeBureau() && egal(code, codeBureau())) return "Bureau";
  let nom = "";
  for (const x of codesEquipe()) if (egal(code, x.jeton)) nom = x.nom; // pas d'arrêt anticipé
  return nom;
}

export function estBureau(code) {
  return Boolean(typeof code === "string" && code && codeBureau() && egal(code, codeBureau()));
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
