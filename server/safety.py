"""Garde-fou des contenus : pas de contenu sexuel (NSFW) ni violent dans les schémas et les maquettes 3D.

Vérifié côté serveur, quoi que réponde l'IA : un schéma ou une maquette qui contient un de ces mots est refusé.
"""
from __future__ import annotations

import re
import unicodedata

# Mots entiers (après suppression des accents).
_WORDS = {
    # contenu sexuel / nudité
    "sex", "sexe", "sexes", "sexy", "sexuel", "sexuelle", "sexuels", "sexuelles", "sexual", "nsfw", "nu", "nue",
    "nus", "nues", "nude", "nudes", "naked", "nudite", "nudity", "seins", "boobs", "tits", "penis", "vagin", "vagina",
    "vulve", "vulva", "fellation", "lingerie", "bdsm", "fetish", "fetiche", "xxx", "porn", "porno",
    # violence / armes
    "gore", "gun", "guns", "pistol", "pistols", "bomb", "bombs", "bombe", "bombes", "kill", "killing", "killer",
    "tuer", "viol", "viols", "rape", "attentat", "attentats", "ak47", "weapon", "weapons", "arme", "armes",
    "violence", "violent", "violente", "murder", "meurtre", "meurtres", "torture", "suicide", "cadavre", "cadavres",
    "corpse", "corpses", "massacre", "genocide", "terrorist", "terroriste", "terrorism", "terrorisme",
}
# Débuts de mots.
_PREFIXES = ("pornog", "erotiq", "erotic", "hentai", "masturb", "orgasm", "genital", "prostitu", "striptease",
             "decapit", "behead", "tortur", "mutil", "demembr", "dismember", "kalach", "mitraill", "sanglant",
             "bloody", "explosif", "explosive", "pistolet", "revolver", "fusil", "rifle", "sniper", "munition",
             "ammunition", "grenade launcher", "lance-roquette", "rocket launcher", "gunshot", "stabbing", "poignard")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return " " + re.sub(r"[^a-z0-9]+", " ", t) + " "


def _strings(value, out: list, depth: int = 0) -> list:
    if depth > 6 or len(out) > 2000:
        return out
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            _strings(k, out, depth + 1)
            _strings(v, out, depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _strings(v, out, depth + 1)
    return out


def blocked(*values) -> bool:
    """Vrai si le contenu (texte, liste ou dictionnaire) est sexuel ou violent."""
    text = _norm(" ".join(_strings(list(values), [])))
    if any(f" {w} " in text for w in _WORDS):
        return True
    return any(f" {_norm(p).strip()}" in text for p in _PREFIXES)


MESSAGE = ("Contenu refusé : Syrius ne fait pas de schéma ni de maquette à caractère sexuel ou violent. "
           "Propose poliment autre chose, sans afficher ce contenu.")
