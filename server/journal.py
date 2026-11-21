"""Journal intime : le soir, Syrius pose quelques questions puis range un court résumé de la journée.

Une entrée par jour (refaire son journal le même jour remplace l'entrée). Chaque membre de la famille a son
propre journal (rangé dans son espace privé, comme les rappels). Rien n'est envoyé ailleurs.
"""
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Paris")

KEY = "journal_v1"
MAX_ENTRIES = 400      # un peu plus d'un an
MAX_TEXT = 2000
MAX_MOOD = 40
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class JournalError(Exception):
    pass


def today() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def _load(db) -> list[dict]:
    try:
        data = json.loads(db.get_secret(KEY) or "[]")
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and _DAY.match(str(e.get("day", ""))) and isinstance(e.get("text"), str)]


def _save(db, items: list[dict]) -> None:
    items = sorted(items, key=lambda e: e["day"])[-MAX_ENTRIES:]
    db.set_secret(KEY, json.dumps(items, ensure_ascii=False))


def save(db, text: str, mood: str = "", day: str | None = None) -> dict:
    text = "\n".join(" ".join(line.split()) for line in str(text or "").strip().splitlines()).strip()
    if len(text) < 5:
        raise JournalError("résumé trop court")
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT - 1].rstrip() + "…"
    day = day or today()
    if not _DAY.match(day):
        raise JournalError("date invalide")
    mood = " ".join(str(mood or "").split())[:MAX_MOOD]
    entry = {"day": day, "text": text, "mood": mood}
    items = [e for e in _load(db) if e["day"] != day] + [entry]
    _save(db, items)
    return entry


def entries(db) -> list[dict]:
    """Toutes les entrées, la plus récente d'abord."""
    return sorted(_load(db), key=lambda e: e["day"], reverse=True)


def recent(db, days: int = 7) -> list[dict]:
    days = max(1, min(int(days), 62))
    since = (datetime.now(TIMEZONE) - timedelta(days=days)).strftime("%Y-%m-%d")
    return [e for e in entries(db) if e["day"] >= since]


def delete(db, day: str) -> bool:
    if not _DAY.match(day or ""):
        return False
    items = _load(db)
    left = [e for e in items if e["day"] != day]
    if len(left) == len(items):
        return False
    _save(db, left)
    return True
