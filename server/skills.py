"""Compétences d'Aurora : des fiches de méthode qu'elle charge à la demande (revue de code, rapport client…).

- fiches intégrées : server/skills/*.md (début « --- name: … description: … --- », puis les consignes) ;
- fiches du propriétaire : ajoutées dans Syrius Code (20 au plus, 4 000 caractères chacune).
Seul le nom et la description sont dans la consigne d'Aurora ; le contenu n'est chargé que quand elle s'en sert
(l'outil `use_skill`), ce qui garde chaque question légère.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import safety
from .memory import _SECRET

DIR = Path(__file__).with_name("skills")
KEY = "aurore_skills_v1"
MAX_CUSTOM, MAX_BODY = 20, 4000
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")


class SkillError(ValueError):
    pass


def _builtin() -> dict[str, dict]:
    out = {}
    for f in sorted(DIR.glob("*.md")):
        m = re.match(r"^---\s*\nname:\s*([\w-]+)\s*\ndescription:\s*(.+?)\s*\n---\s*\n(.*)$", f.read_text(encoding="utf-8"), re.S)
        if m:
            out[m.group(1)] = {"name": m.group(1), "description": m.group(2), "body": m.group(3).strip(), "builtin": True}
    return out


def _custom(base) -> list[dict]:
    try:
        data = json.loads(base.get_secret(KEY) or "[]")
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict) and _NAME.match(str(d.get("name", "")))] if isinstance(data, list) else []


def catalog(base) -> list[dict]:
    """Toutes les compétences (nom, description, intégrée ou non), sans le contenu."""
    mine = _custom(base)
    out = [{"name": s["name"], "description": s["description"], "builtin": True} for s in _builtin().values()]
    out += [{"name": d["name"], "description": str(d.get("description", ""))[:160], "builtin": False} for d in mine]
    return out


def get(base, name: str) -> dict | None:
    name = str(name or "").strip().lower()
    if name in (b := _builtin()):
        return b[name]
    d = next((x for x in _custom(base) if x["name"] == name), None)
    return {"name": d["name"], "description": d.get("description", ""), "body": str(d.get("body", "")), "builtin": False} if d else None


def add(base, name: str, description: str, body: str) -> dict:
    name = " ".join(str(name or "").lower().split()).replace(" ", "-")
    description, body = " ".join(str(description or "").split()), str(body or "").strip()
    if not _NAME.match(name):
        raise SkillError("Nom : 2 à 40 caractères, lettres, chiffres et tirets (ex. relecture-contrat).")
    if not 10 <= len(description) <= 160:
        raise SkillError("Description : 10 à 160 caractères (elle dit QUAND utiliser la compétence).")
    if not 20 <= len(body) <= MAX_BODY:
        raise SkillError(f"Consignes : 20 à {MAX_BODY} caractères.")
    if _SECRET.search(body) or _SECRET.search(description):
        raise SkillError("Ne mets ni mot de passe, ni code, ni numéro de carte dans une compétence.")
    if safety.blocked(description, body):
        raise SkillError("Compétence refusée : pas de contenu sexuel ni violent.")
    if name in _builtin():
        raise SkillError("Ce nom est déjà pris par une compétence d'Aurora.")
    mine = [d for d in _custom(base) if d["name"] != name]
    if len(mine) >= MAX_CUSTOM:
        raise SkillError(f"{MAX_CUSTOM} compétences au plus : supprime-en une.")
    item = {"name": name, "description": description, "body": body, "at": int(time.time())}
    base.set_secret(KEY, json.dumps([*mine, item], ensure_ascii=False))
    return {"name": name, "description": description, "builtin": False}


def delete(base, name: str) -> bool:
    mine = _custom(base)
    if not any(d["name"] == name for d in mine):
        return False
    base.set_secret(KEY, json.dumps([d for d in mine if d["name"] != name], ensure_ascii=False))
    return True


def prompt_list(base) -> str:
    """Les lignes ajoutées à la consigne d'Aurora."""
    lines = [f"- {s['name']} : {s['description']}" for s in catalog(base)]
    return ("Compétences (fiches de méthode) : quand la demande correspond, appelle d'abord `use_skill` avec le nom, "
            "puis applique la fiche.\n" + "\n".join(lines)) if lines else ""
