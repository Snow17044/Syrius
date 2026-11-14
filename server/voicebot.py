"""Syrius sur Discord (salon vocal) : le bot envoie ce que tu dis, ton Syrius répond.

- Le bot s'identifie avec une clé dédiée (créée par le propriétaire dans ses réglages). Cette clé ne permet
  QUE de poser une question vocale au nom du propriétaire, dans une discussion à part « Syrius sur Discord ».
- Seuls les comptes Discord autorisés par le propriétaire sont écoutés (par défaut : le sien).
- Syrius ne répond que si la phrase commence par son nom (« Syrius, … ») : les bruits du jeu et les
  discussions entre joueurs sont ignorés. Le son n'est jamais enregistré.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets

KEY = "family_voicebot_v1"  # espace commun
WAKE = re.compile(r"^\W*(?:ok\s+|dis\s+|h[ée]\s+|hey\s+)?(syrius|sirius|cyrius|syrus|sirus|sirious|syrious)\b[\s,.:;!?-]*(.*)$",
                  re.I | re.S)
_ID = re.compile(r"^[0-9]{15,21}$")
CONV_TITLE = "Syrius sur Discord"


class VoiceBotError(ValueError):
    pass


def settings(base) -> dict:
    try:
        s = json.loads(base.get_secret(KEY) or "{}")
    except ValueError:
        s = {}
    s = s if isinstance(s, dict) else {}
    ids = [i for i in s.get("discord_ids", []) if isinstance(i, str) and _ID.match(i)]
    return {"key": s.get("key", ""), "discord_ids": ids[:5], "conversation": s.get("conversation", "")}


def _save(base, s: dict) -> None:
    base.set_secret(KEY, json.dumps(s))


def key(base, renew: bool = False) -> str:
    s = settings(base)
    if renew or not s["key"]:
        s["key"] = "syb_" + secrets.token_urlsafe(32)
        _save(base, s)
    return s["key"]


def check_key(base, given: str) -> bool:
    k = settings(base)["key"]
    return bool(k) and bool(given) and hmac.compare_digest(
        hashlib.sha256(given.encode()).digest(), hashlib.sha256(k.encode()).digest())


def set_ids(base, ids: list[str]) -> list[str]:
    clean = []
    for i in ids:
        i = str(i).strip()
        if not _ID.match(i):
            raise VoiceBotError("Identifiant Discord invalide (un nombre de 17 à 20 chiffres).")
        if i not in clean:
            clean.append(i)
    s = settings(base)
    s["discord_ids"] = clean[:5]
    _save(base, s)
    return s["discord_ids"]


def allowed(base, discord_id: str) -> bool:
    return discord_id in settings(base)["discord_ids"]


def remember_conversation(base, cid: str) -> None:
    s = settings(base)
    s["conversation"] = cid
    _save(base, s)


def wake(text: str) -> str | None:
    """Renvoie la demande si la phrase commence par « Syrius », sinon None."""
    m = WAKE.match(text or "")
    if not m:
        return None
    rest = m.group(2).strip()
    return rest or ""
