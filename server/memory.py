"""Mémoire long terme de Syrius : ajout contrôlé (pas de doublon, pas de secret, taille limitée).

Utilisé par l'outil « remember » de l'IA et par l'ajout à la main dans les réglages.
"""
from __future__ import annotations

import re

from . import safety

MAX_MEMORIES = 80
MAX_LEN = 300
_SECRET = re.compile(
    r"(mot de passe|mdp|password|passcode|code (pin|secret|de carte|bancaire)|\bpin\b|\bcvv\b|\biban\b|\bcvc\b|"
    r"(?<!\d)(?:\d[ -]?){13,19}(?!\d))", re.I)


class MemoryError_(ValueError):
    """Souvenir refusé (message affichable)."""


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def add(db, fact: str) -> tuple[int, bool]:
    """Enregistre un souvenir. Renvoie (numéro, nouveau). Un doublon renvoie le souvenir existant."""
    fact = " ".join(str(fact or "").split())
    if len(fact) < 3:
        raise MemoryError_("Souvenir vide ou trop court.")
    if len(fact) > MAX_LEN:
        raise MemoryError_(f"Souvenir trop long ({MAX_LEN} caractères au plus) : résume-le en une phrase.")
    if _SECRET.search(fact):
        raise MemoryError_("Je ne retiens jamais de mots de passe, codes ni numéros de carte ou de compte.")
    if safety.blocked(fact):
        raise MemoryError_("Souvenir refusé : pas de contenu sexuel ni violent.")
    existing = db.list_memories()
    key = _norm(fact)
    for m in existing:
        if _norm(m["content"]) == key:
            return m["id"], False
    if len(existing) >= MAX_MEMORIES:
        raise MemoryError_(f"Mémoire pleine ({MAX_MEMORIES} souvenirs) : supprime les moins utiles dans les réglages.")
    return db.add_memory(fact), True
