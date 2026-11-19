"""Lire tout le code d'un site (pages HTML, scripts, styles, sources) pour qu'Aurore l'analyse.

Mêmes garde-fous que le scanner de sécurité (server/sitescan.py) :
- uniquement les sites que le propriétaire a ajoutés ET dont il a prouvé la propriété (revérifiée à chaque appel) ;
- lecture seule (GET), jamais hors du domaine, même pare-feu que le web, 60 requêtes au plus par appel ;
- les secrets trouvés dans le code (clés, jetons, mots de passe écrits) sont MASQUÉS avant d'être donnés à l'IA :
  ils ne quittent pas le site. Seul leur emplacement est signalé.
Le code d'un site est une donnée non fiable : l'IA ne doit jamais le prendre pour des ordres.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from . import sitescan

MAX_PAGES, MAX_ASSETS, CHUNK, FETCH_LIMIT = 25, 60, 12_000, 400_000
TEXT_EXT = (".html", ".htm", ".js", ".mjs", ".css", ".json", ".xml", ".txt", ".svg", ".map", ".webmanifest", ".md")
_BINARY_EXT = re.compile(r"\.(png|jpe?g|gif|webp|avif|ico|bmp|woff2?|ttf|otf|eot|mp[34]|webm|ogg|wav|pdf|zip|gz|wasm)$", re.I)


class CodeError(ValueError):
    """Refus ou erreur affichable."""


def redact(text: str) -> tuple[str, list[str]]:
    """Masque les secrets : renvoie (texte propre, liste des types trouvés)."""
    found: list[str] = []
    for rx, label in sitescan.SECRET_PATTERNS:
        def sub(m, label=label):
            found.append(label)
            return f"[SECRET MASQUÉ : {label}]"
        text = rx.sub(sub, text)
    return text, found


def _clean_path(path: str) -> str:
    p = str(path or "").strip()
    if not p.startswith("/") or p.startswith("//") or len(p) > 300 or any(c in p for c in "\r\n\t\x00 \\") or ".." in p.split("?")[0].split("/"):
        raise CodeError("Chemin invalide : donne un chemin du site qui commence par / (ex. /app.js).")
    return p


def _kind(path: str, ctype: str = "") -> str:
    p = path.split("?")[0].lower()
    if p.endswith(".map"):
        return "sourcemap"
    if p.endswith((".js", ".mjs")) or "javascript" in ctype:
        return "script"
    if p.endswith(".css") or "css" in ctype:
        return "style"
    if p.endswith((".html", ".htm")) or p.endswith("/") or "html" in ctype:
        return "page"
    if p.endswith(".json") or p.endswith(".webmanifest"):
        return "données"
    return "texte"


def _text(r) -> str:
    return r.body.decode("utf-8", errors="replace")


def _links(base_url: str, html: str, hosts: set[str]) -> tuple[list[str], list[str], list[str]]:
    """(pages, scripts, styles) du même site, sans doublon."""
    pages, scripts, styles = [], [], []

    def keep(u: str):
        p = urlparse(urljoin(base_url, u.strip()))
        if p.scheme not in ("http", "https") or (p.hostname or "").lower() not in hosts:
            return None
        return p._replace(fragment="").geturl()
    for m in re.finditer(r"""<script\b[^>]*\bsrc\s*=\s*["']([^"']+)""", html, re.I):
        if (u := keep(m.group(1))) and u not in scripts:
            scripts.append(u)
    for m in re.finditer(r"""<link\b[^>]*\brel\s*=\s*["'][^"']*stylesheet[^"']*["'][^>]*\bhref\s*=\s*["']([^"']+)""", html, re.I):
        if (u := keep(m.group(1))) and u not in styles:
            styles.append(u)
    for m in re.finditer(r"""<link\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*\brel\s*=\s*["'][^"']*stylesheet""", html, re.I):
        if (u := keep(m.group(1))) and u not in styles:
            styles.append(u)
    for m in re.finditer(r"""<a\b[^>]*\bhref\s*=\s*["']([^"'#]+)""", html, re.I):
        u = keep(m.group(1))
        if u and not _BINARY_EXT.search(urlparse(u).path) and u not in pages:
            pages.append(u)
    return pages, scripts, styles


def _path(url: str) -> str:
    p = urlparse(url)
    return (p.path or "/") + (("?" + p.query) if p.query else "")


def list_files(base, raw: str, fetcher=None) -> dict:
    """Parcourt le site (pages liées + scripts et styles qu'elles chargent) et renvoie l'index des fichiers."""
    dom, f = sitescan.ensure_access(base, raw, fetcher)
    start = f"https://{dom}/"
    home = f.get(start, FETCH_LIMIT)
    if home.error or home.status != 200:
        alt = f.get(f"https://www.{dom}/", FETCH_LIMIT)
        if alt.status == 200 and not alt.error:
            start, home = f"https://www.{dom}/", alt
    if home.error or home.status != 200:
        raise CodeError("La page d'accueil du site ne répond pas : impossible de lire son code.")
    files, seen = [], set()
    secrets_found: list[str] = []

    def add(url: str, r, kind: str = ""):
        if url in seen:
            return
        seen.add(url)
        body = _text(r)
        _, hit = redact(body)
        secrets_found.extend(f"{_path(url)} : {h}" for h in hit)
        files.append({"path": _path(url), "kind": kind or _kind(_path(url), r.h("content-type").lower()),
                      "size": len(r.body), "parts": max(1, -(-len(body) // CHUNK)), "secrets": len(hit)})
    add(start, home, "page")
    queue = [start]
    assets: list[str] = []
    inline = 0
    html_cache = {start: _text(home)}
    while queue and len([x for x in files if x["kind"] == "page"]) < MAX_PAGES:
        url = queue.pop(0)
        html = html_cache.get(url)
        if html is None:
            r = f.get(url, FETCH_LIMIT)
            if r.error or r.status != 200 or "html" not in r.h("content-type").lower():
                continue
            html = _text(r)
            add(url, r, "page")
        inline += len(re.findall(r"<script\b(?![^>]*\bsrc=)[^>]*>", html, re.I))
        pages, scripts, styles = _links(url, html, f.hosts)
        assets += [a for a in scripts + styles if a not in assets]
        queue += [p for p in pages if p not in seen and p not in queue][: MAX_PAGES]
    for a in assets[:MAX_ASSETS]:
        if a in seen:
            continue
        r = f.get(a, FETCH_LIMIT)
        if r.status == 200 and not r.error:
            add(a, r)
            m = re.search(r"//[#@]\s*sourceMappingURL=([^\s]+)\s*$", _text(r)[-400:])
            if m and not m.group(1).startswith("data:"):
                mp = urljoin(a, m.group(1))
                if (urlparse(mp).hostname or "").lower() in f.hosts and mp not in seen:
                    mr = f.get(mp, FETCH_LIMIT)
                    if mr.status == 200 and not mr.error:
                        add(mp, mr, "sourcemap")
    return {"domain": dom, "files": files, "inline_scripts": inline, "requests": f.count,
            "secrets": sorted(set(secrets_found))[:20],
            "note": "Lis un fichier avec read_site_file(domain, path, part). Pour un sourcemap, donne path « /x.js.map » "
                    "pour voir les sources originales, puis « /x.js.map::src/app.js »."}


def read_file(base, raw: str, path: str, part: int = 1, fetcher=None) -> dict:
    """Lit un fichier du site (par morceaux de ~12 000 caractères), secrets masqués."""
    dom, f = sitescan.ensure_access(base, raw, fetcher)
    spec = str(path or "")
    inner = ""
    if "::" in spec:
        spec, inner = spec.split("::", 1)
    spec = _clean_path(spec)
    if _BINARY_EXT.search(spec.split("?")[0]):
        raise CodeError("Fichier binaire (image, police, archive…) : je ne lis que du texte.")
    if not isinstance(part, int) or isinstance(part, bool) or part < 1:
        part = 1
    r = f.get(f"https://{dom}{spec}", FETCH_LIMIT)
    if r.error == "refus":
        raise CodeError("Fichier hors du site : refusé.")
    if r.error or r.status != 200:
        raise CodeError(f"Impossible de lire {spec} (réponse {r.status or 'aucune'}).")
    ctype = r.h("content-type").lower()
    if ctype and not any(k in ctype for k in ("text", "json", "javascript", "xml", "svg", "css")):
        raise CodeError("Ce fichier n'est pas du texte : je ne le lis pas.")
    body = _text(r)
    note = ""
    if spec.split("?")[0].lower().endswith(".map"):
        try:
            sm = json.loads(body)
            sources, contents = sm.get("sources") or [], sm.get("sourcesContent") or []
        except ValueError:
            raise CodeError("Sourcemap illisible.") from None
        if not inner:
            note = "Sources originales de ce sourcemap (donne path « %s::<nom> » pour en lire une) :" % spec
            body = "\n".join(f"{i}: {s}" for i, s in enumerate(sources[:300]))
        else:
            idx = next((i for i, s in enumerate(sources) if s == inner or str(s).endswith("/" + inner)), None)
            if idx is None or idx >= len(contents) or not isinstance(contents[idx], str):
                raise CodeError("Source introuvable dans ce sourcemap (ou son contenu n'est pas publié).")
            body = contents[idx]
    clean, hit = redact(body)
    total = max(1, -(-len(clean) // CHUNK))
    part = min(part, total)
    chunk = clean[(part - 1) * CHUNK: part * CHUNK]
    return {"domain": dom, "path": spec + (("::" + inner) if inner else ""), "part": part, "parts": total, "size": len(r.body),
            "secrets_masked": sorted(set(hit)), "note": note, "content": chunk}


def to_text(res: dict) -> str:
    """Forme lisible par l'IA."""
    if "files" in res:
        lines = [f"Site {res['domain']} : {len(res['files'])} fichier(s), {res['inline_scripts']} script(s) dans les pages."]
        lines += [f"- {x['path']}  [{x['kind']}, {x['size']} o, {x['parts']} morceau(x)]" + (f"  ⚠ {x['secrets']} secret(s) masqué(s)" if x["secrets"] else "")
                  for x in res["files"]]
        if res["secrets"]:
            lines.append("Secrets masqués (à révoquer par le propriétaire) : " + " ; ".join(res["secrets"]))
        lines.append(res["note"])
        return "\n".join(lines)
    head = f"{res['domain']}{res['path']} — morceau {res['part']}/{res['parts']}"
    if res["secrets_masked"]:
        head += " — secrets masqués : " + ", ".join(res["secrets_masked"])
    return head + ("\n" + res["note"] if res["note"] else "") + "\n```\n" + res["content"] + "\n```"
