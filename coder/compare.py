"""python -m coder.compare avant.json apres.json : le modèle entraîné est-il meilleur que celui de départ ?"""
from __future__ import annotations

import json
import sys

MIN_GAIN = 0.05  # il faut gagner au moins 5 points pour parler d'amélioration


def verdict(before: dict, after: dict) -> tuple[bool, str]:
    if before.get("version") != after.get("version"):
        return False, "banc d'essai différent : comparaison impossible"
    b, a = float(before.get("score", 0)), float(after.get("score", 0))
    if a >= b + MIN_GAIN:
        return True, f"Amélioration : {b:.0%} → {a:.0%} ({after.get('passed')}/{after.get('n')} bugs réparés)."
    if a >= b:
        return False, f"Pas d'amélioration nette : {b:.0%} → {a:.0%} (il faut au moins +{MIN_GAIN:.0%})."
    return False, f"Moins bon qu'avant : {b:.0%} → {a:.0%}. Ce modèle ne sera pas utilisé."


if __name__ == "__main__":
    ok, msg = verdict(json.load(open(sys.argv[1])), json.load(open(sys.argv[2])))
    print(msg)
    sys.exit(0 if ok else 1)
