"""Annonce à ton Syrius la nouvelle version de notre IA (nom du fichier publié, empreinte, taille).

Appelé par la conversion automatique, avec la signature GitHub (OIDC) : aucun secret. Les téléphones
proposent ensuite « Mettre à jour » et vérifient l'empreinte du fichier téléchargé.
"""
import hashlib
import json
import os
import sys
import urllib.request

import syrius_auth

path = sys.argv[1]
h = hashlib.sha256()
with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)
body = {"file": os.path.basename(path), "sha256": h.hexdigest(), "size": os.path.getsize(path),
        "run_id": os.environ.get("RUN_ID", "")}
req = urllib.request.Request(os.environ["SYRIUS_URL"].rstrip("/") + "/api/model/manifest", method="POST",
                             data=json.dumps(body).encode(), headers={
                                 "Authorization": f"Bearer {syrius_auth.token()}", "Content-Type": "application/json",
                                 "X-Syrius": "1", "User-Agent": "SyriusTraining/1.0"})
with urllib.request.urlopen(req, timeout=60) as r:  # nosec B310 (adresse de ton Syrius)
    print("Nouvelle version annoncée :", json.loads(r.read()).get("file"))
