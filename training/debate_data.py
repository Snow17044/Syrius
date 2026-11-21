"""Ajoute les répliques de débat d'Aurora à ses exemples d'entraînement (IA programmeuse de Syrius Code).

Les débats du propriétaire (Nova contre Aurora) sont joués par les grandes IA gratuites ; leurs répliques
« Aurora » sont rangées par ton Syrius. Ici, on les récupère et on les ajoute au fichier d'entraînement
d'Aurora, en petite quantité (10 % au plus) : le code reste sa priorité, et le banc d'essai décide
toujours si le nouveau modèle est gardé.

Usage : python training/debate_data.py training/data/coder.jsonl
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import syrius_auth  # noqa: E402

SHARE = 0.10  # part maximale des exemples de débat dans l'entraînement d'Aurora
SYSTEM = ("Tu es Aurora, l'IA de Syrius Code : rigoureuse, analytique, pragmatique, avec un humour sec. Dans un débat, "
          "tu réponds en français en 2 à 4 phrases : d'abord à l'argument précédent, puis un argument nouveau et concret. "
          "Pas de Markdown, pas d'emoji.")


def fetch() -> list[dict]:
    url = os.environ.get("SYRIUS_URL", "").rstrip("/")
    try:
        tok = syrius_auth.token() if url else ""
    except Exception as e:  # noqa: BLE001
        print(f"Identité GitHub indisponible : {e}")
        return []
    if not url or not tok:
        return []
    try:
        req = urllib.request.Request(url + "/api/training/worker/debates?who=aurora", headers={
            "Authorization": f"Bearer {tok}", "User-Agent": "SyriusTraining/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310 (adresse de ton Syrius)
            items = json.loads(r.read(5_000_000))
    except Exception as e:  # noqa: BLE001 — l'entraînement continue sans
        print(f"Débats indisponibles : {e}")
        return []
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def rows(items: list[dict], limit: int) -> list[dict]:
    out = []
    for it in items[-limit:] if limit > 0 else []:
        q, a = str(it.get("q", ""))[:500], str(it.get("a", ""))[:900]
        if q and a:
            out.append({"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": q},
                                     {"role": "assistant", "content": a}]})
    return out


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "training/data/coder.jsonl")
    n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()) if path.exists() else 0
    if not n:
        print("Pas d'exemples de code : rien à compléter.")
        return
    extra = rows(fetch(), int(n * SHARE))
    if extra:
        with path.open("a", encoding="utf-8") as f:  # ajoutés à la fin : la 1re ligne (consigne de code) ne change pas
            for r in extra:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(extra)} répliques de débat d'Aurora ajoutées à {n} exemples de code")


if __name__ == "__main__":
    main()
