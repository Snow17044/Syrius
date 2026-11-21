"""Épreuve de confirmation inédite, fabriquée chaque nuit par une grande IA gratuite.

Le banc d'essai fixe a une petite part de hasard : un modèle « chanceux » pourrait y gagner quelques points
sans être vraiment meilleur. Chaque nuit, la grande IA écrit donc de NOUVEAUX petits projets (jamais utilisés
pour l'entraînement), on y fabrique de vrais bugs, et le nouveau modèle d'Aurora doit faire au moins aussi bien
que le modèle actuel sur cette épreuve. Les tests sont exécutés : c'est un résultat vérifié, pas un avis.

python -m coder.confirm make confirm.json            (grande IA, via ton Syrius)
python -m coder.confirm run DOSSIER_MODELE confirm.json
python -m coder.confirm verdict nouveau.json reference.json
"""
from __future__ import annotations

import json
import random
import sys
import time

from . import bench, make_data

# Thèmes différents de ceux des exemples d'entraînement (make_data.TOPICS) : l'épreuve reste inédite.
TOPICS = ["bibliothèque et emprunts", "météo et températures", "panier d'achat et réductions",
          "agenda et rendez-vous", "playlist et durées", "budget mensuel", "jeu de cartes",
          "horaires de train", "parking et tarifs", "classement sportif", "cuisine et temps de cuisson",
          "location de vélos"]
MIN_TASKS = 4  # en dessous, l'épreuve ne prouve rien


def make(ask, n_projects: int = 3, seed: int | None = None, log=print) -> list[dict]:
    seed = int(time.time() // 86400) if seed is None else seed
    rng = random.Random(seed)
    projects: dict[str, dict] = {}
    for topic in rng.sample(TOPICS, len(TOPICS)):
        if len(projects) >= n_projects:
            break
        try:
            files = make_data.new_project(ask, topic)
        except Exception as e:  # noqa: BLE001
            log(f"épreuve « {topic} » : indisponible ({str(e)[:80]})")
            continue
        if files:
            projects[f"epreuve_{len(projects)}"] = files
        else:
            log(f"épreuve « {topic} » : refusée (tests ne passent pas)")
    return bench.build(projects, per_project=3, seed=seed, implement=1) if projects else []


def verdict(new: dict, ref: dict) -> tuple[bool, str]:
    n = int(new.get("n", 0))
    if n < MIN_TASKS or n != int(ref.get("n", -1)):
        return False, "Épreuve de confirmation indisponible cette nuit : le modèle attend la prochaine."
    a, b = int(new.get("passed", 0)), int(ref.get("passed", 0))
    if a >= b:
        return True, f"Confirmé sur l'épreuve inédite de la nuit : {a}/{n} bugs réparés (modèle actuel : {b}/{n})."
    return False, f"Non confirmé sur l'épreuve inédite : {a}/{n} contre {b}/{n} pour le modèle actuel. On garde l'actuel."


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "make":
        ts = make(make_data.http_ask())
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            json.dump(ts, f, ensure_ascii=False)
        print(json.dumps({"tasks": len(ts)}))
    elif cmd == "run":
        from .bench_run import local_ask
        with open(sys.argv[3], encoding="utf-8") as f:
            ts = json.load(f)
        print(json.dumps(bench.run(local_ask(sys.argv[2]), ts), ensure_ascii=False))
    elif cmd == "verdict":
        ok, msg = verdict(json.load(open(sys.argv[2], encoding="utf-8")), json.load(open(sys.argv[3], encoding="utf-8")))
        print(msg)
        sys.exit(0 if ok else 1)
    else:
        print(__doc__)
        sys.exit(2)
