"""Schémas d'idées en 3D : l'IA décrit un graphe (idées + liens), l'app le dessine en hologramme.

Le contenu vient du modèle : tout est validé strictement (types, tailles, références, boucles)
et l'app ne l'affiche que comme du texte (jamais comme du HTML).
"""
from __future__ import annotations

import json
import re

STYLES = ("carte", "etapes", "arbre")
KINDS = ("objectif", "phase", "etape", "action", "outil", "budget", "delai", "risque", "idee", "ressource", "personne")
MAX_NODES = 30
MAX_LINKS = 40
MAX_TITLE = 80
MAX_LABEL = 48
MAX_NOTE = 300
MAX_ID = 24


class DiagramError(ValueError):
    pass


def _text(value, limit: int, what: str, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise DiagramError(f"{what} doit être un texte")
    clean = " ".join(value.split())[:limit]
    if required and not clean:
        raise DiagramError(f"{what} vide")
    return clean


def validate(args) -> dict:
    if not isinstance(args, dict):
        raise DiagramError("entrée non valide")
    unknown = set(args) - {"title", "style", "nodes", "links"}
    if unknown:
        raise DiagramError(f"paramètre inconnu : {sorted(unknown)[0]}")
    title = _text(args.get("title"), MAX_TITLE, "title")
    style = args.get("style", "carte")
    if style not in STYLES:
        style = "carte"
    raw_nodes = args.get("nodes")
    if not isinstance(raw_nodes, list) or not 2 <= len(raw_nodes) <= MAX_NODES:
        raise DiagramError(f"nodes : entre 2 et {MAX_NODES} idées")

    nodes, ids = [], set()
    for n in raw_nodes:
        if not isinstance(n, dict) or set(n) - {"id", "label", "parent", "note", "kind"}:
            raise DiagramError("chaque idée : id, label, parent, note, kind (facultatifs sauf id et label)")
        nid = _text(n.get("id"), MAX_ID, "id")
        if nid in ids:
            raise DiagramError(f"id en double : {nid}")
        ids.add(nid)
        parent = n.get("parent")
        parent = _text(parent, MAX_ID, "parent", required=False) if parent not in (None, "") else ""
        kind = n.get("kind") if n.get("kind") in KINDS else ""
        nodes.append({"id": nid, "label": _text(n.get("label"), MAX_LABEL, "label"), "parent": parent,
                      "note": _text(n.get("note"), MAX_NOTE, "note", required=False), "kind": kind})

    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        if n["parent"] and (n["parent"] not in by_id or n["parent"] == n["id"]):
            n["parent"] = ""  # parent inconnu : l'idée sera rattachée à la racine
    roots = [n for n in nodes if not n["parent"]]
    root = roots[0]
    for n in roots[1:]:
        n["parent"] = root["id"]
    for n in nodes:  # casse les boucles éventuelles (a → b → a)
        seen, cur = set(), n
        while cur["parent"]:
            if cur["id"] in seen:
                cur["parent"] = root["id"] if cur is not root else ""
                break
            seen.add(cur["id"])
            cur = by_id[cur["parent"]]

    links = []
    raw_links = args.get("links") or []
    if not isinstance(raw_links, list):
        raise DiagramError("links doit être une liste")
    for link in raw_links[:MAX_LINKS]:
        if not isinstance(link, dict) or set(link) - {"from", "to", "label"}:
            raise DiagramError("chaque lien : from, to, label (facultatif)")
        a, b = link.get("from"), link.get("to")
        if a in by_id and b in by_id and a != b:
            links.append({"from": a, "to": b, "label": _text(link.get("label"), 30, "label", required=False)})

    return {"type": "diagram", "title": title, "style": style, "nodes": nodes, "links": links}


# ---------------------------------------------------------------- filet de sécurité
# Certains modèles écrivent le schéma en texte (bloc de code JSON) au lieu d'appeler l'outil.
# On le repère, on le retire du message et on l'affiche quand même.
_FENCE = re.compile(r"```[a-zA-Z]*\s*(.*?)```", re.S)
MAX_SCAN = 60_000


def _unwrap(obj):
    for _ in range(3):  # {"name": "show_diagram", "arguments": {...}} et variantes
        if not isinstance(obj, dict) or "nodes" in obj:
            break
        inner = obj.get("arguments") or obj.get("parameters") or obj.get("input") or obj.get("diagram")
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                return None
        obj = inner
    return obj if isinstance(obj, dict) and isinstance(obj.get("nodes"), list) else None


def extract_from_text(text: str) -> tuple[str, dict | None]:
    """Renvoie (texte sans le code du schéma, schéma validé) ou (texte inchangé, None)."""
    if "nodes" not in text or len(text) > MAX_SCAN:
        return text, None
    decoder = json.JSONDecoder()
    spans = [(m.start(), m.end(), m.group(1)) for m in _FENCE.finditer(text)]
    for start, end, body in spans:  # d'abord les blocs de code ```json … ```
        body = body.strip()
        try:
            obj, _ = decoder.raw_decode(body[body.find("{"):]) if "{" in body else (None, 0)
        except ValueError:
            continue
        found = _unwrap(obj)
        if found:
            try:
                event = validate({k: v for k, v in found.items() if k in ("title", "style", "nodes", "links")}
                                 | {"title": found.get("title") or "Schéma"})
            except DiagramError:
                continue
            return (text[:start] + text[end:]).strip(), event
    i = text.find("{")
    while i != -1:  # puis un objet JSON écrit directement dans le texte
        try:
            obj, length = decoder.raw_decode(text[i:])
        except ValueError:
            i = text.find("{", i + 1)
            continue
        found = _unwrap(obj)
        if found:
            try:
                event = validate({k: v for k, v in found.items() if k in ("title", "style", "nodes", "links")}
                                 | {"title": found.get("title") or "Schéma"})
            except DiagramError:
                return text, None
            before = re.sub(r"show_diagram\s*\(?\s*$", "", text[:i])
            after = re.sub(r"^\s*\)", "", text[i + length:])
            return (before + after).strip(), event
        i = text.find("{", i + length)
    return text, None
