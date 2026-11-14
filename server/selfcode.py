"""« Améliorer Syrius » : le propriétaire demande un changement, une IA programmeuse gratuite le propose.

Règles (les mêmes que pour un développeur humain) :
- seul le propriétaire peut faire une demande ;
- l'IA travaille sur le serveur gratuit de GitHub et PROPOSE le changement (une « pull request ») ;
- tous les tests doivent passer, certaines parties sont interdites de modification (sécurité, comptes,
  filtre de contenu, automatisations) ;
- rien n'est jamais publié sans l'accord du propriétaire.
Le serveur de GitHub utilise la clé d'entraînement : elle ne lui permet que de prendre la demande suivante
et d'en donner le résultat.
"""
from __future__ import annotations

import json
import re
import secrets
import time

from . import safety

KEY = "family_selfcode_v1"
SETTINGS_KEY = "family_selfcode_settings_v1"
MAX_LESSONS = 40
# IA programmeuses gratuites proposées (OpenRouter, modèles « :free »).
CODER_MODELS = ["qwen/qwen3-coder:free", "nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free",
                "inclusionai/ling-3.2-flash:free"]
MAX_ITEMS = 30
STATUSES = ("pending", "running", "proposed", "failed", "refused")
_PR = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/pull/\d+$")


class SelfCodeError(ValueError):
    pass


def _load(base) -> list[dict]:
    try:
        data = json.loads(base.get_secret(KEY) or "[]")
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _save(base, items: list[dict]) -> None:
    base.set_secret(KEY, json.dumps(items[-MAX_ITEMS:], ensure_ascii=False))


def items(base) -> list[dict]:
    now = time.time()
    out = _load(base)
    for it in out:  # une demande prise depuis plus de 2 h sans nouvelles : considérée comme échouée
        if it.get("status") == "running" and now - it.get("updated", 0) > 7200:
            it["status"], it["summary"] = "failed", "Pas de réponse du serveur de GitHub (interrompu)."
    return out[::-1]


def add(base, text: str) -> dict:
    t = " ".join(str(text).split())
    if not 10 <= len(t) <= 1500:
        raise SelfCodeError("Décris le changement en 10 à 1500 caractères.")
    if safety.blocked(t):
        raise SelfCodeError("Demande refusée : pas de contenu sexuel ni violent.")
    data = _load(base)
    if sum(1 for d in data if d.get("status") in ("pending", "running")) >= 3:
        raise SelfCodeError("3 demandes sont déjà en attente : patiente qu'elles soient traitées.")
    now = int(time.time())
    item = {"id": secrets.token_hex(4), "text": t, "status": "pending", "created": now, "updated": now,
            "summary": "", "pr": "", "tests": ""}
    data.append(item)
    _save(base, data)
    return item


def cancel(base, iid: str) -> bool:
    data = _load(base)
    for d in data:
        if d.get("id") == iid and d.get("status") == "pending":
            d["status"], d["summary"], d["updated"] = "refused", "Annulée par toi.", int(time.time())
            _save(base, data)
            return True
    return False


# ------------------------------------------------------------------ rendre l'IA programmeuse meilleure
def settings(base) -> dict:
    try:
        s = json.loads(base.get_secret(SETTINGS_KEY) or "{}")
    except ValueError:
        s = {}
    s = s if isinstance(s, dict) else {}
    lessons = [x for x in s.get("lessons", []) if isinstance(x, dict)]
    model = s.get("model") if s.get("model") in CODER_MODELS else ""
    return {"lessons": lessons, "model": model, "models": CODER_MODELS}


def _save_settings(base, s: dict) -> None:
    base.set_secret(SETTINGS_KEY, json.dumps({"lessons": s["lessons"][-MAX_LESSONS:], "model": s["model"]},
                                             ensure_ascii=False))


def add_lesson(base, text: str) -> dict:
    t = " ".join(str(text).split())
    if not 5 <= len(t) <= 400:
        raise SelfCodeError("Un conseil fait 5 à 400 caractères.")
    if safety.blocked(t):
        raise SelfCodeError("Conseil refusé : pas de contenu sexuel ni violent.")
    s = settings(base)
    item = {"id": secrets.token_hex(4), "text": t, "at": int(time.time())}
    s["lessons"].append(item)
    _save_settings(base, s)
    return item


def delete_lesson(base, lid: str) -> bool:
    s = settings(base)
    keep = [x for x in s["lessons"] if x.get("id") != lid]
    if len(keep) == len(s["lessons"]):
        return False
    s["lessons"] = keep
    _save_settings(base, s)
    return True


def set_model(base, model: str) -> None:
    if model and model not in CODER_MODELS:
        raise SelfCodeError("IA programmeuse inconnue.")
    s = settings(base)
    s["model"] = model
    _save_settings(base, s)


def retry(base, iid: str, feedback: str) -> dict:
    """Proposition pas satisfaisante : l'avis devient un conseil durable et la demande est relancée."""
    fb = " ".join(str(feedback).split())
    if not 5 <= len(fb) <= 400:
        raise SelfCodeError("Explique en quelques mots ce qui ne va pas (5 à 400 caractères).")
    old = next((d for d in _load(base) if d.get("id") == iid), None)
    if not old or old.get("status") not in ("proposed", "failed"):
        raise SelfCodeError("Demande introuvable.")
    add_lesson(base, fb)
    return add(base, f"{old['text']} (Nouvel essai. Remarque du propriétaire sur l'essai précédent : {fb})"[:1500])


def take_next(base) -> dict | None:
    """Pour le serveur de GitHub : la plus ancienne demande en attente (marquée « en cours »)."""
    data = _load(base)
    for d in data:
        if d.get("status") == "pending":
            d["status"], d["updated"] = "running", int(time.time())
            _save(base, data)
            s = settings(base)
            return {"id": d["id"], "text": d["text"], "lessons": [x["text"] for x in s["lessons"]],
                    "model": s["model"]}
    return None


def report(base, body: dict) -> None:
    if not isinstance(body, dict):
        raise SelfCodeError("résultat invalide")
    iid, status = str(body.get("id", "")), body.get("status")
    if not re.fullmatch(r"[0-9a-f]{8}", iid) or status not in ("running", "proposed", "failed"):
        raise SelfCodeError("résultat invalide")
    pr = str(body.get("pr") or "")
    if pr and not _PR.match(pr):
        raise SelfCodeError("lien invalide")
    data = _load(base)
    for d in data:
        if d.get("id") == iid:
            d["status"] = status
            d["summary"] = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(body.get("summary") or ""))[:1500]
            d["tests"] = str(body.get("tests") or "")[:200]
            d["pr"] = pr
            d["updated"] = int(time.time())
            _save(base, data)
            return
    raise SelfCodeError("demande inconnue")
