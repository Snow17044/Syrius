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
# Budget À PART pour les sites de l'atelier instantané : ils ne mangent plus celui des exemples de code ni de GitHub.
SITE_KEY = "family_coderask_site_v1"
SITE_BUDGET = 400
MAX_PROMPT = 30000  # l'atelier d'Aurora renvoie le projet entier et la sortie des tests


class CoderAskError(Exception):
    pass


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def used(base, key: str = KEY) -> int:
    try:
        d = json.loads(base.get_secret(key) or "{}")
    except ValueError:
        return 0
    return int(d.get("n", 0)) if d.get("day") == _today() else 0


def ask(base, providers: list, system: str, prompt: str, max_tokens: int = 2500, kind: str = "code") -> dict:
    key, budget = (SITE_KEY, SITE_BUDGET) if kind == "site" else (KEY, DAILY_BUDGET)
    if not isinstance(prompt, str) or not 10 <= len(prompt) <= MAX_PROMPT:
        raise CoderAskError("demande invalide")
    n = used(base, key)
    if n >= budget:
        raise CoderAskError("budget du jour atteint" + (" pour les sites" if kind == "site" else ""))
    from .llm import strength  # la plus capable d'abord (Codestral en tête s'il existe)
    pool = sorted((p for p in providers if not getattr(p, "photos_only", False)),
                  key=lambda p: (0 if getattr(p, "coding_only", False) else 1, strength(p)))
    last = ""
    for p in pool:
        try:
            text = autogen._ask(p, (str(system)[:8000] + "\n\n" if system else "") + prompt, 0.3,
                                max(500, min(int(max_tokens), 6000)))
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = str(e)[:100]
            continue
        if text.strip():
            base.set_secret(key, json.dumps({"day": _today(), "n": n + 1}))
            return {"text": text, "provider": p.label, "used": n + 1}
    raise CoderAskError("aucune IA disponible" + (f" ({last})" if last else ""))
