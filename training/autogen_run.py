"""Demande à ton Syrius de créer N lots d'exemples d'entraînement (étape de la nuit)."""
import json
import os
import sys
import urllib.request

import syrius_auth

base = os.environ.get("SYRIUS_URL", "").rstrip("/")
n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
total_added = 0
why_total: dict = {}
for i in range(n):
    try:  # chaque lot prend le thème suivant : tous les thèmes sont couverts chaque nuit
        req = urllib.request.Request(base + f"/api/training/worker/generate?theme={i}", data=b"{}", method="POST", headers={
            "Authorization": f"Bearer {syrius_auth.token()}", "Content-Type": "application/json", "X-Syrius": "1",
            "User-Agent": "SyriusTraining/1.0"})
        with urllib.request.urlopen(req, timeout=290) as r:  # nosec B310 (adresse de ton Syrius)
            res = json.loads(r.read())
    except Exception as e:  # noqa: BLE001 — on continue avec ce qui existe déjà
        print(f"Lot {i + 1} : indisponible ({e})")
        continue
    total_added += res.get("added", 0)
    print(f"Lot {i + 1} « {res.get('theme', '')[:50]} » : {res.get('added', 0)} gardés, "
          f"{res.get('rejected', 0)} refusés {res.get('provider', '')} {res.get('error', '')}")
    for why, k in (res.get("reasons") or {}).items():
        print(f"    refusé ×{k} : {why}")
        why_total[why] = why_total.get(why, 0) + k
print(f"Nouveaux exemples créés par Syrius cette nuit : {total_added}")
if why_total:
    print("Raisons des refus : " + " ; ".join(f"{w} ×{k}" for w, k in sorted(why_total.items(), key=lambda x: -x[1])))
