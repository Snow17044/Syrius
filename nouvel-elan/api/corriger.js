// POST /api/corriger → vérifie l'orthographe et la grammaire de textes (équipe seulement).
// Corps : { textes: { cle: "texte", … } }  →  { corrections: { cle: [{ debut, longueur, original, suggestion, message }] } }
// Utilise le correcteur gratuit LanguageTool (serveurs en Europe). Rien n'est corrigé sans l'accord de l'équipe :
// l'appli montre les propositions, on choisit ce qu'on garde.
import { codeValide, repondre, lireCorps } from "./_outils.js";

const SERVICE = process.env.NE_CORRECTEUR_URL || "https://api.languagetool.org/v2/check";
const MORCEAU = 15000;          // la version gratuite accepte ~20 Ko par demande
const TOTAL_MAX = 150000;       // de quoi vérifier tout un programme

// On garde l'orthographe et la grammaire ; on laisse de côté le style et les espaces typographiques.
const GARDER = new Set(["misspelling", "grammar"]);
const IGNORER = /WHITESPACE|ESPACE|APOS_TYP|GUILLEMETS|TIRET|UPPERCASE_SENTENCE_START|FRENCH_WORD_REPEAT_BEGINNING/i;

// Coupe un long texte en morceaux, de préférence entre deux paragraphes.
function morceaux(texte) {
  const r = [];
  let debut = 0;
  while (debut < texte.length) {
    let fin = Math.min(texte.length, debut + MORCEAU);
    if (fin < texte.length) {
      const coupure = texte.lastIndexOf("\n", fin);
      if (coupure > debut + MORCEAU / 2) fin = coupure + 1;
    }
    r.push([debut, texte.slice(debut, fin)]);
    debut = fin;
  }
  return r;
}

async function verifier(texte) {
  const trouvees = [];
  for (const [decalage, bout] of morceaux(texte)) {
    if (!bout.trim()) continue;
    const r = await fetch(SERVICE, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body: new URLSearchParams({ text: bout, language: "fr" }),
      signal: AbortSignal.timeout(20000),
    });
    if (!r.ok) throw new Error(`correcteur : erreur ${r.status}`);
    for (const m of (await r.json()).matches || []) {
      const type = m.rule?.issueType;
      const suggestion = m.replacements?.[0]?.value;
      if (!GARDER.has(type) || IGNORER.test(m.rule?.id || "") || suggestion == null) continue;
      const original = bout.slice(m.offset, m.offset + m.length);
      if (!original.trim() || original === suggestion) continue;
      trouvees.push({ debut: decalage + m.offset, longueur: m.length, original, suggestion, message: String(m.message || "").slice(0, 200) });
    }
  }
  return trouvees;
}

export default async function handler(req, res) {
  if (req.method !== "POST") return repondre(res, 405, { erreur: "Méthode non prise en charge." });
  if (!codeValide(req.headers["x-code-editeur"])) return repondre(res, 401, { erreur: "Code éditeur incorrect." });
  try {
    const { textes } = await lireCorps(req, 600000);
    const entrees = Object.entries(textes && typeof textes === "object" ? textes : {})
      .filter(([, t]) => typeof t === "string" && t.trim()).slice(0, 500);
    if (entrees.reduce((n, [, t]) => n + t.length, 0) > TOTAL_MAX) return repondre(res, 413, { erreur: "Texte trop long pour être vérifié d'un coup." });
    const corrections = {};
    let partiel = false;
    for (const [cle, texte] of entrees) {
      try {
        const c = await verifier(texte);
        if (c.length) corrections[cle] = c;
      } catch { partiel = true; break; } // limite de la version gratuite atteinte : on rend ce qu'on a
    }
    return repondre(res, 200, { corrections, partiel });
  } catch (e) {
    // Correcteur indisponible : on n'empêche pas de publier.
    return repondre(res, 200, { corrections: {}, indisponible: true, erreur: e.message });
  }
}
