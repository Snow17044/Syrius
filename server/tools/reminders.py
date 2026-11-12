"""Liste des rappels connus du serveur (pour que Syrius puisse les citer ou les annuler).

Les notifications elles-mêmes sont programmées et déclenchées par l'application Android.
"""
import json
import time

KEY = "reminders_v1"
MAX = 100


def _load(db) -> list[dict]:
    try:
        data = json.loads(db.get_secret(KEY) or "[]")
    except ValueError:
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def _save(db, items: list[dict]) -> None:
    db.set_secret(KEY, json.dumps(items[-MAX:], ensure_ascii=False))


def add(db, r: dict) -> None:
    items = _load(db)
    items.append({k: r[k] for k in ("id", "text", "at", "repeat", "label")})
    _save(db, items)


def remove(db, rid: str) -> bool:
    items = _load(db)
    left = [r for r in items if r.get("id") != rid]
    _save(db, left)
    return len(left) != len(items)


def upcoming(db) -> list[dict]:
    """Rappels à venir (les rappels ponctuels passés sont oubliés)."""
    now = time.time() * 1000
    items = [r for r in _load(db) if r.get("repeat") in ("daily", "weekly") or r.get("at", 0) > now]
    return sorted(items, key=lambda r: r.get("at", 0))
