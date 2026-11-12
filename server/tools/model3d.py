"""Maquettes 3D : l'IA décrit un objet (tour Eiffel, voiture, molécule…) comme un assemblage
de formes simples ; l'app le dessine en hologramme avec Three.js.

Le contenu vient du modèle : tout est validé strictement (formes connues, nombres bornés,
couleurs au format #rrggbb, textes courts) et n'est jamais inséré comme du HTML.
"""
from __future__ import annotations

import math
import re

from .diagram import find_json_object

SHAPES = ("box", "cylinder", "cone", "sphere", "torus", "pyramid", "capsule")
MAX_PARTS = 220
MAX_COORD = 1000.0
MAX_SIZE = 1000.0
MAX_FACTS = 8
_HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
NAMED_COLORS = {
    "rouge": "#e63946", "red": "#e63946", "bleu": "#3a86ff", "blue": "#3a86ff", "vert": "#2a9d8f",
    "green": "#2a9d8f", "jaune": "#ffd166", "yellow": "#ffd166", "orange": "#f4a261", "violet": "#9b5de5",
    "purple": "#9b5de5", "rose": "#ff8fab", "pink": "#ff8fab", "blanc": "#f1f5f9", "white": "#f1f5f9",
    "noir": "#1f2937", "black": "#1f2937", "gris": "#94a3b8", "grey": "#94a3b8", "gray": "#94a3b8",
    "marron": "#8d5524", "brun": "#8d5524", "brown": "#8d5524", "or": "#d4a017", "gold": "#d4a017",
    "argent": "#c0c7d0", "silver": "#c0c7d0", "bronze": "#a97142", "cyan": "#38d9ff", "beige": "#e9d8a6",
}


class ModelError(ValueError):
    pass


def _num(v, lo: float, hi: float, default: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return default
    return float(min(hi, max(lo, v)))


def _vec(v, lo: float, hi: float, default: float) -> list[float]:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        v = [v, v, v]
    if not isinstance(v, list):
        return [default] * 3
    out = [_num(x, lo, hi, default) for x in v[:3]]
    return out + [default] * (3 - len(out))


def _color(v) -> str:
    if isinstance(v, str):
        c = v.strip().lower()
        if c in NAMED_COLORS:
            return NAMED_COLORS[c]
        m = _HEX.match(c)
        if m:
            h = m.group(1)
            if len(h) == 3:
                h = "".join(ch * 2 for ch in h)
            return "#" + h.lower()
    return "#38d9ff"


def _text(v, limit: int) -> str:
    return " ".join(v.split())[:limit] if isinstance(v, str) else ""


def validate(args) -> dict:
    if not isinstance(args, dict):
        raise ModelError("entrée non valide")
    title = _text(args.get("title"), 80)
    if not title:
        raise ModelError("title manquant")
    raw = args.get("parts")
    if not isinstance(raw, list) or not raw:
        raise ModelError("parts : au moins une forme")
    parts = []
    for p in raw[:MAX_PARTS]:
        if not isinstance(p, dict):
            continue
        shape = p.get("shape") if p.get("shape") in SHAPES else None
        if not shape:
            continue
        parts.append({
            "shape": shape,
            "pos": _vec(p.get("pos"), -MAX_COORD, MAX_COORD, 0.0),
            "size": _vec(p.get("size"), 0.001, MAX_SIZE, 1.0),
            "rot": _vec(p.get("rot"), -360.0, 360.0, 0.0),
            "color": _color(p.get("color")),
            "name": _text(p.get("name"), 40),
        })
    if not parts:
        raise ModelError("aucune forme valide (box, cylinder, cone, sphere, torus, pyramid, capsule)")
    facts = [f for f in (_text(x, 80) for x in (args.get("facts") or [])[:MAX_FACTS]
                         if isinstance(args.get("facts"), list)) if f]
    return {"type": "model", "title": title, "description": _text(args.get("description"), 300),
            "parts": parts, "facts": facts}


def _check(found: dict) -> dict:
    return validate({k: v for k, v in found.items() if k in ("title", "description", "parts", "facts")}
                    | {"title": found.get("title") or "Maquette 3D"})


def extract_from_text(text: str) -> tuple[str, dict | None]:
    return find_json_object(text, "parts", _check)
