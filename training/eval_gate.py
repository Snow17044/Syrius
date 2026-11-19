"""Décide si le nouveau modèle peut être publié (appelé par la conversion automatique).

Usage : python training/eval_gate.py build/syrius/eval.json [eval-latest.json de la version publiée] [--require]
Code de sortie 0 = on publie, 1 = on ne publie pas. Sans contrôle qualité (ancien modèle) : on laisse passer.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_set import MAX_REGRESSION, MIN_SCORE  # noqa: E402


def decide(new: dict | None, old: dict | None, require: bool = False) -> tuple[bool, str]:
    if not new and require:
        return False, "Contrôle qualité absent alors qu'il est obligatoire : mise à jour NON publiée."
    if not new:
        return True, "Pas de contrôle qualité pour ce modèle (ancien entraînement) : publication autorisée."
    s = float(new.get("score", 0))
    if s < MIN_SCORE:
        return False, f"Qualité trop basse : {s:.0%} (minimum {MIN_SCORE:.0%}). Mise à jour NON publiée."
    if old and s < float(old.get("score", 0)) - MAX_REGRESSION:
        return False, (f"Moins bon que la version publiée : {s:.0%} contre {float(old['score']):.0%}. "
                       "Mise à jour NON publiée.")
    return True, f"Qualité {s:.0%} : OK."


def _load(p: str | None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8")) if p and Path(p).exists() else None
    except ValueError:
        return None


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--require"]
    ok, msg = decide(_load(args[0] if args else None), _load(args[1] if len(args) > 1 else None),
                     require="--require" in sys.argv)
    print(msg)
    sys.exit(0 if ok else 1)
