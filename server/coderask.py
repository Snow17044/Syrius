"""Point d'accès réservé aux automatisations GitHub : une grande IA gratuite écrit du code pour fabriquer les exemples.

Budget quotidien (compteur dans la base) pour ne pas vider les limites gratuites de Syrius.
"""
from __future__ import annotations

import json
import time
import urllib.error

from . import autogen

KEY = "family_coderask_v1"
DAILY_BUDGET = 120
MAX_PROMPT = 14000


class CoderAskError(Exception):
    pass


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def used(base) -> int:
    try:
        d = json.loads(base.get_secret(KEY) or "{}")
    except ValueError:
        return 0
    return int(d.get("n", 0)) if d.get("day") == _today() else 0


def ask(base, providers: list, system: str, prompt: str) -> dict:
    if not isinstance(prompt, str) or not 10 <= len(prompt) <= MAX_PROMPT:
        raise CoderAskError("demande invalide")
    n = used(base)
    if n >= DAILY_BUDGET:
        raise CoderAskError("budget du jour atteint")
    pool = sorted((p for p in providers if not getattr(p, "photos_only", False)),
                  key=lambda p: 0 if getattr(p, "coding_only", False) else 1)
    last = ""
    for p in pool:
        try:
            text = autogen._ask(p, (str(system)[:1200] + "\n\n" if system else "") + prompt, 0.3, 2500)
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = str(e)[:100]
            continue
        if text.strip():
            base.set_secret(KEY, json.dumps({"day": _today(), "n": n + 1}))
            return {"text": text, "provider": p.label, "used": n + 1}
    raise CoderAskError("aucune IA disponible" + (f" ({last})" if last else ""))
