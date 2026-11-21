"""python -m coder.compare avant.json apres.json [gain_minimum] : le modèle entraîné est-il meilleur que l'autre ?"""
from __future__ import annotations

import json
import sys

MIN_GAIN = 0.05  # il faut gagner au moins 5 points pour parler d'amélioration


def verdict(before: dict, after: dict, min_gain: float = MIN_GAIN) -> tuple[bool, str]:
    if before.get("version") != after.get("version"):
        return False, "banc d'essai différent : comparaison impossible"
    b, a = float(before.get("score", 0)), float(after.get("score", 0))
    if a >= b + min_gain:
        return True, f"Amélioration : {b:.0%} → {a:.0%} ({after.get('passed')}/{after.get('n')} bugs réparés)."
    if a >= b:
        return False, f"Pas d'amélioration nette : {b:.0%} → {a:.0%} (il faut au moins +{max(min_gain, 0.01):.0%})."
    return False, f"Moins bon qu'avant : {b:.0%} → {a:.0%}. Ce modèle ne sera pas utilisé."


if __name__ == "__main__":
    gain = float(sys.argv[3]) if len(sys.argv) > 3 else MIN_GAIN
    ok, msg = verdict(json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), gain)
    print(msg)
    sys.exit(0 if ok else 1)
