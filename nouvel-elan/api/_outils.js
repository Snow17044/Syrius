// Outils communs aux fonctions serveur de Nouvel Élan (stockage + réponses).
import { timingSafeEqual, createHash } from "node:crypto";

const URL_REDIS = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const JETON_REDIS = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
const CLE = "nouvel-elan:articles";

// Stockage en mémoire, uniquement pour les essais sur ordinateur (NE_DEV=1).
const memoire = new Map();

export function stockagePret() {
  return Boolean((URL_REDIS && JETON_REDIS) || process.env.NE_DEV === "1");
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
  if (URL_REDIS && JETON_REDIS) {
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
  if (URL_REDIS && JETON_REDIS) await redis(["HSET", CLE, a.id, v]);
  else memoire.set(a.id, v);
}

export async function lireArticle(id) {
  const v = URL_REDIS && JETON_REDIS ? await redis(["HGET", CLE, id]) : memoire.get(id);
  return v ? JSON.parse(v) : null;
}

export async function supprimerArticle(id) {
  if (URL_REDIS && JETON_REDIS) await redis(["HDEL", CLE, id]);
  else memoire.delete(id);
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

export async function lireCorps(req) {
  if (req.body !== undefined && req.body !== null) {
    return typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body;
  }
  let brut = "";
  for await (const morceau of req) {
    brut += morceau;
    if (brut.length > 20000) throw new Error("Requête trop grosse");
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

export function textePropre(t, max) {
  return String(t ?? "").replace(/[\u0000-\u001f\u007f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}
