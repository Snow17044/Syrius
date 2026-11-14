"""Tableau de bord de l'entraînement de l'IA Syrius (propriétaire uniquement).

- Le propriétaire ajoute ses propres exemples (question → réponse idéale) : ils sont appris au prochain
  entraînement.
- Le serveur d'entraînement (GitHub) envoie sa progression en direct (étapes, perte, réponses de test)
  avec une clé d'entraînement générée ici. Cette clé ne donne accès qu'à ces deux choses : déposer la
  progression et lire les exemples. Jamais aux discussions ni aux comptes.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time

from . import safety

TOKEN_KEY = "family_training_token_v1"  # préfixe « family_ » : espace commun
EXAMPLES_KEY = "family_training_examples_v1"
RUNS_KEY = "family_training_runs_v1"
MAX_EXAMPLES = 500
MAX_RUNS = 6
MAX_POINTS = 400
_RUN_ID = re.compile(r"^[0-9]{1,20}$")


class TrainingError(ValueError):
    pass


def _load(base, key: str, default):
    try:
        data = json.loads(base.get_secret(key) or "null")
    except ValueError:
        data = None
    return data if isinstance(data, type(default)) else default


def _save(base, key: str, value) -> None:
    base.set_secret(key, json.dumps(value, ensure_ascii=False))


# ------------------------------------------------------------------ clé du serveur d'entraînement
def token(base, renew: bool = False) -> str:
    t = base.get_secret(TOKEN_KEY)
    if renew or not t:
        t = "syr_" + secrets.token_urlsafe(32)
        base.set_secret(TOKEN_KEY, t)
    return t


def check_token(base, given: str) -> bool:
    t = base.get_secret(TOKEN_KEY) or ""
    return bool(t) and bool(given) and hmac.compare_digest(
        hashlib.sha256(given.encode()).digest(), hashlib.sha256(t.encode()).digest())


# ------------------------------------------------------------------ exemples donnés par le propriétaire
def examples(base) -> list[dict]:
    return [e for e in _load(base, EXAMPLES_KEY, []) if isinstance(e, dict)]


def add_example(base, question: str, answer: str) -> dict:
    q, a = " ".join(str(question).split()), str(answer).strip()
    if not 2 <= len(q) <= 500 or not 1 <= len(a) <= 2000:
        raise TrainingError("Question (2 à 500 caractères) et réponse (1 à 2000) obligatoires.")
    if safety.blocked(q, a):
        raise TrainingError("Exemple refusé : pas de contenu sexuel ni violent.")
    items = examples(base)
    if len(items) >= MAX_EXAMPLES:
        raise TrainingError(f"Maximum {MAX_EXAMPLES} exemples : supprime-en avant d'en ajouter.")
    item = {"id": secrets.token_hex(4), "q": q, "a": a, "at": int(time.time())}
    items.append(item)
    _save(base, EXAMPLES_KEY, items)
    return item


def delete_example(base, eid: str) -> bool:
    items = examples(base)
    keep = [e for e in items if e.get("id") != eid]
    if len(keep) == len(items):
        return False
    _save(base, EXAMPLES_KEY, keep)
    return True


# ------------------------------------------------------------------ suivi des entraînements
def runs(base) -> list[dict]:
    return [r for r in _load(base, RUNS_KEY, []) if isinstance(r, dict)]


def _num(v, lo: float, hi: float) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if lo <= x <= hi else None


def _txt(v, n: int) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(v or ""))[:n]


def report(base, event: dict) -> None:
    """Événement envoyé par le serveur d'entraînement : start, step, test, done ou error."""
    if not isinstance(event, dict):
        raise TrainingError("événement invalide")
    rid = str(event.get("run", ""))
    kind = event.get("type")
    if not _RUN_ID.match(rid) or kind not in ("start", "step", "test", "done", "error"):
        raise TrainingError("événement invalide")
    items = runs(base)
    run = next((r for r in items if r.get("id") == rid), None)
    now = int(time.time())
    if run is None:
        run = {"id": rid, "status": "running", "started": now, "updated": now, "points": [], "tests": [],
               "steps_total": 0, "examples": 0, "model": "", "phase": "Préparation"}
        items.append(run)
    run["updated"] = now
    if kind == "start":
        run["model"] = _txt(event.get("model"), 80)
        run["examples"] = int(_num(event.get("examples"), 0, 100000) or 0)
        run["steps_total"] = int(_num(event.get("steps_total"), 0, 1e6) or 0)
        run["minutes"] = _num(event.get("minutes"), 0, 1e4)
        run["phase"] = "Entraînement"
    elif kind == "step":
        step, loss = _num(event.get("step"), 0, 1e6), _num(event.get("loss"), 0, 1e4)
        if step is not None and loss is not None:
            run["points"].append([int(step), round(loss, 4), now - run["started"]])
            run["points"] = run["points"][-MAX_POINTS:]
        run["phase"] = "Entraînement"
    elif kind == "test":
        phase = "avant" if event.get("phase") == "avant" else "après"
        run["tests"].append({"phase": phase, "q": _txt(event.get("q"), 300), "a": _txt(event.get("a"), 900)})
        run["tests"] = run["tests"][-24:]
        run["phase"] = "Essais " + ("avant" if phase == "avant" else "après") + " entraînement"
    elif kind == "done":
        run["status"] = "done"
        run["examples_hash"] = examples_hash(base)
        run["phase"] = "Terminé"
        run["finished"] = now
    else:
        run["status"] = "error"
        run["phase"] = "Erreur : " + _txt(event.get("message"), 200)
        run["finished"] = now
    items = sorted(items, key=lambda r: r.get("started", 0))[-MAX_RUNS:]
    _save(base, RUNS_KEY, items)


def examples_hash(base) -> str:
    return hashlib.sha256(json.dumps([[e.get("q"), e.get("a")] for e in examples(base)]).encode()).hexdigest()[:16]


def should_train(base) -> bool:
    """Entraînement de nuit : seulement si tes exemples ont changé depuis le dernier entraînement réussi."""
    done = [r for r in runs(base) if r.get("status") == "done"]
    return not done or done[-1].get("examples_hash") != examples_hash(base)


def state(base) -> dict:
    items = runs(base)
    for r in items:  # un entraînement silencieux depuis 30 min est considéré comme interrompu
        if r.get("status") == "running" and time.time() - r.get("updated", 0) > 1800:
            r["status"] = "stale"
            r["phase"] = "Sans nouvelles (interrompu ?)"
    return {"runs": items[::-1], "examples": examples(base)[::-1], "connected": bool(items)}
