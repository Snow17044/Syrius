// Pour essayer l'application sur un ordinateur : `npm run dev` puis http://localhost:3000
// (articles gardés en mémoire, code éditeur « elan »).
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import articles from "./api/articles.js";
import apercu from "./api/apercu.js";
import programme from "./api/programme.js";
import photo from "./api/photo.js";
import editeur from "./api/editeur.js";
import adhesion from "./api/adhesion.js";
import espace from "./api/espace.js";

const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".png": "image/png", ".webmanifest": "application/manifest+json" };
const racine = new URL("./public/", import.meta.url).pathname;

createServer(async (req, res) => {
  const { pathname } = new URL(req.url, "http://x");
  if (pathname === "/api/articles") return articles(req, res);
  if (pathname === "/api/apercu") return apercu(req, res);
  if (pathname === "/api/programme") return programme(req, res);
  if (pathname === "/api/photo") return photo(req, res);
  if (pathname === "/api/editeur") return editeur(req, res);
  if (pathname === "/api/adhesion") return adhesion(req, res);
  if (pathname === "/api/espace") return espace(req, res);
  const chemin = normalize(join(racine, pathname === "/" ? "index.html" : pathname === "/installer" ? "installer.html" : pathname === "/reparer" ? "reparer.html" : pathname));
  if (!chemin.startsWith(racine)) { res.statusCode = 403; return res.end(); }
  try {
    const contenu = await readFile(chemin);
    res.setHeader("Content-Type", TYPES[extname(chemin)] || "application/octet-stream");
    res.end(contenu);
  } catch { res.statusCode = 404; res.end("Introuvable"); }
}).listen(process.env.PORT || 3000, () => console.log(`Nouvel Élan : http://localhost:${process.env.PORT || 3000}`));
