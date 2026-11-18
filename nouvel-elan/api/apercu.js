// GET /api/apercu?url=...  → titre, résumé, image et source d'une page web,
// pour remplir automatiquement la fiche d'un article à partir de son lien.
import { lookup } from "node:dns/promises";
import { isIP } from "node:net";
import { repondre, lienPropre, textePropre } from "./_outils.js";

// Refuse les adresses internes (protection contre l'accès au réseau privé du serveur).
function adressePrivee(ip) {
  if (isIP(ip) === 6) {
    const s = ip.toLowerCase();
    if (s.startsWith("::ffff:")) return adressePrivee(s.slice(7));
    return s === "::1" || s === "::" || s.startsWith("fc") || s.startsWith("fd") || s.startsWith("fe80");
  }
  const [a, b] = ip.split(".").map(Number);
  return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127) || a >= 224;
}

async function hoteAutorise(u) {
  if (u.port && !["80", "443"].includes(u.port)) return false;
  const hote = u.hostname.replace(/^\[|\]$/g, "");
  const adresses = isIP(hote) ? [{ address: hote }] : await lookup(hote, { all: true });
  return adresses.length > 0 && adresses.every((x) => !adressePrivee(x.address));
}

function decoder(t) {
  return t
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&");
}

function meta(html, noms) {
  for (const nom of noms) {
    const re1 = new RegExp(`<meta[^>]+(?:property|name)=["']${nom}["'][^>]*content=["']([^"']*)["']`, "i");
    const re2 = new RegExp(`<meta[^>]+content=["']([^"']*)["'][^>]*(?:property|name)=["']${nom}["']`, "i");
    const m = html.match(re1) || html.match(re2);
    if (m && m[1].trim()) return decoder(m[1]);
  }
  return "";
}

async function telecharger(depart) {
  let u = new URL(depart);
  for (let saut = 0; saut < 5; saut++) {
    if (!(await hoteAutorise(u))) throw new Error("Adresse non autorisée");
    const r = await fetch(u, {
      redirect: "manual",
      signal: AbortSignal.timeout(8000),
      headers: { "User-Agent": "Mozilla/5.0 (compatible; NouvelElanApercu/1.0)", Accept: "text/html" },
    });
    if (r.status >= 300 && r.status < 400 && r.headers.get("location")) {
      u = new URL(r.headers.get("location"), u);
      if (!lienPropre(u.toString())) throw new Error("Redirection refusée");
      continue;
    }
    if (!(r.headers.get("content-type") || "").includes("html")) return { html: "", fin: u };
    // On ne lit que le début de la page : les informations utiles sont dans <head>.
    const lecteur = r.body.getReader();
    let html = "";
    const dec = new TextDecoder();
    while (html.length < 600000) {
      const { done, value } = await lecteur.read();
      if (done) break;
      html += dec.decode(value, { stream: true });
      if (/<\/head>/i.test(html)) break;
    }
    lecteur.cancel().catch(() => {});
    return { html, fin: u };
  }
  throw new Error("Trop de redirections");
}

export default async function handler(req, res) {
  const lien = lienPropre(new URL(req.url, "http://x").searchParams.get("url") || "");
  if (!lien) return repondre(res, 400, { erreur: "Ce lien n'est pas valide." });
  const source = new URL(lien).hostname.replace(/^www\./, "");
  try {
    const { html, fin } = await telecharger(lien);
    const titreBalise = (html.match(/<title[^>]*>([^<]*)<\/title>/i) || [])[1] || "";
    let image = meta(html, ["og:image:secure_url", "og:image", "twitter:image", "twitter:image:src"]);
    if (image) { try { image = lienPropre(new URL(image, fin).toString()); } catch { image = ""; } }
    return repondre(res, 200, {
      url: lien,
      titre: textePropre(meta(html, ["og:title", "twitter:title"]) || decoder(titreBalise), 200),
      resume: textePropre(meta(html, ["og:description", "twitter:description", "description"]), 400),
      image,
      source: textePropre(meta(html, ["og:site_name"]), 80) || source,
    });
  } catch {
    // Site injoignable ou qui bloque les robots : on renvoie le minimum, la personne complète le titre.
    return repondre(res, 200, { url: lien, titre: "", resume: "", image: "", source, partiel: true });
  }
}
