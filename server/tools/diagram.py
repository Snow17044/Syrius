"""Schémas d'idées en 3D : l'IA décrit un graphe (idées + liens), l'app le dessine en hologramme.

Le contenu vient du modèle : tout est validé strictement (types, tailles, références, boucles)
et l'app ne l'affiche que comme du texte (jamais comme du HTML).
"""
from __future__ import annotations

STYLES = ("carte", "etapes", "arbre")
MAX_NODES = 30
MAX_LINKS = 40
MAX_TITLE = 80
MAX_LABEL = 48
MAX_NOTE = 220
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
        if not isinstance(n, dict) or set(n) - {"id", "label", "parent", "note"}:
            raise DiagramError("chaque idée : id, label, parent (facultatif), note (facultative)")
        nid = _text(n.get("id"), MAX_ID, "id")
        if nid in ids:
            raise DiagramError(f"id en double : {nid}")
        ids.add(nid)
        parent = n.get("parent")
        parent = _text(parent, MAX_ID, "parent", required=False) if parent not in (None, "") else ""
        nodes.append({"id": nid, "label": _text(n.get("label"), MAX_LABEL, "label"),
                      "parent": parent, "note": _text(n.get("note"), MAX_NOTE, "note", required=False)})

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
