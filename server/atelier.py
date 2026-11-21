"""L'Atelier d'Aurora : elle écrit un programme, le LANCE et le TESTE elle-même, puis le corrige jusqu'à ce qu'il marche.

Comme un développeur sur son ordinateur : Aurora travaille sur un serveur Linux gratuit de GitHub (workflow
« Atelier d'Aurora »). Elle écrit les fichiers, installe ce qu'il faut, lance les tests, lit les erreurs et corrige
(jusqu'à 5 essais). Le code qui tourne est enfermé dans un conteneur sans aucun secret. Le résultat (fichiers, sortie
des tests) revient ici et s'affiche dans Syrius Code.

Réservé au propriétaire. Le serveur de GitHub ne peut que prendre le projet suivant et en donner l'avancement.
"""
from __future__ import annotations

import json
import re
import secrets
import time

from . import safety

KEY = "family_atelier_v1"
WORKFLOW = "atelier.yml"
MAX_ITEMS = 20
MAX_FILES = 40
MAX_FILE_CHARS = 60_000
MAX_TOTAL_CHARS = 200_000
STATUSES = ("pending", "running", "done", "failed")
_ID = re.compile(r"^[0-9a-f]{8}$")
_PATH = re.compile(r"^(?!/)(?!.*\.\.)[\w.\-/ ]{1,120}$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class AtelierError(ValueError):
    pass


def _load(base) -> list[dict]:
    try:
        data = json.loads(base.get_secret(KEY) or "[]")
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _save(base, items: list[dict]) -> None:
    base.set_secret(KEY, json.dumps(items[-MAX_ITEMS:], ensure_ascii=False))


def _fresh(item: dict, now: float) -> dict:
    if item.get("status") == "running" and now - item.get("updated", 0) > 3600:
        item = {**item, "status": "failed", "summary": "Pas de nouvelles du serveur de GitHub (interrompu)."}
    if item.get("status") == "pending" and now - item.get("created", 0) > 3 * 3600:
        item = {**item, "status": "failed", "summary": "Le serveur de GitHub n'a pas pris le projet (atelier pas lancé ?)."}
    return item


def items(base) -> list[dict]:
    now = time.time()
    return [_fresh(d, now) for d in _load(base)][::-1]


def get(base, pid: str) -> dict | None:
    return next((d for d in items(base) if d.get("id") == pid), None)


def add(base, text: str) -> dict:
    t = str(text).strip()
    if not 10 <= len(t) <= 4000:
        raise AtelierError("Décris le programme en 10 à 4000 caractères.")
    if safety.blocked(t):
        raise AtelierError("Projet refusé : pas de contenu sexuel ni violent.")
    data = _load(base)
    if sum(1 for d in data if _fresh(d, time.time()).get("status") in ("pending", "running")) >= 2:
        raise AtelierError("2 projets sont déjà en cours dans l'atelier : attends qu'ils soient finis.")
    now = int(time.time())
    item = {"id": secrets.token_hex(4), "text": t, "status": "pending", "created": now, "updated": now,
            "summary": "", "attempt": 0, "files": {}, "log": "", "setup": "", "test": "", "env": ""}
    data.append(item)
    _save(base, data)
    return item


def take_next(base) -> dict | None:
    """Pour le serveur de GitHub : le plus ancien projet en attente (marqué « en cours »)."""
    data = _load(base)
    for d in data:
        if d.get("status") == "pending":
            d["status"], d["updated"], d["summary"] = "running", int(time.time()), "L'atelier démarre…"
            _save(base, data)
            return {"id": d["id"], "text": d["text"]}
    return None


def _files(raw) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out, total = {}, 0
    for path, content in list(raw.items())[:MAX_FILES]:
        if not isinstance(path, str) or not isinstance(content, str) or not _PATH.match(path):
            continue
        content = content[:MAX_FILE_CHARS]
        if total + len(content) > MAX_TOTAL_CHARS:
            break
        total += len(content)
        out[path] = content
    return out


def report(base, body: dict) -> None:
    """Avancement envoyé par le serveur de GitHub (à chaque essai, puis le résultat final)."""
    if not isinstance(body, dict):
        raise AtelierError("résultat invalide")
    pid, status = str(body.get("id", "")), body.get("status")
    if not _ID.match(pid) or status not in ("running", "done", "failed"):
        raise AtelierError("résultat invalide")
    data = _load(base)
    for d in data:
        if d.get("id") != pid:
            continue
        d["status"] = status
        d["updated"] = int(time.time())
        d["summary"] = _CTRL.sub("", str(body.get("summary") or ""))[:1500]
        try:
            d["attempt"] = max(0, min(int(body.get("attempt") or 0), 20))
        except (TypeError, ValueError):
            pass
        d["log"] = str(body.get("log") or "")[-6000:]
        for k in ("setup", "test"):
            d[k] = _CTRL.sub("", str(body.get(k) or ""))[:300]
        d["env"] = body.get("env") if body.get("env") in ("python", "node") else ""
        files = _files(body.get("files"))
        if files:
            d["files"] = files
        _save(base, data)
        return
    raise AtelierError("projet inconnu")


def for_aurora(item: dict) -> str:
    """Résultat lisible par Aurora (outil check_code_project)."""
    st = {"pending": "en attente", "running": "en cours", "done": "TERMINÉ : les tests passent",
          "failed": "ÉCHEC"}[item["status"]]
    parts = [f"Projet {item['id']} : {st} (essai {item.get('attempt', 0)}/5).", f"Résumé : {item.get('summary') or '—'}"]
    if item.get("setup") or item.get("test"):
        parts.append(f"Environnement : {item.get('env') or '?'} ; installation : {item.get('setup') or 'aucune'} ; "
                     f"test : {item.get('test') or '?'}")
    for path, content in (item.get("files") or {}).items():
        parts.append(f"### {path}\n```\n{content[:6000]}\n```")
    if item.get("log"):
        parts.append("Dernière sortie des tests :\n```\n" + item["log"][-1500:] + "\n```")
    return "\n\n".join(parts)[:20000]
