"""Identifiant pour parler à ton Syrius depuis GitHub Actions.

Priorité à la signature officielle GitHub (OIDC, aucun secret à configurer) ; sinon l'ancienne clé
d'entraînement si elle existe. Le jeton GitHub ne dure que quelques minutes : il est redemandé au besoin.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

_cache = {"token": "", "at": 0.0}


def token() -> str:
    url, req_tok = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if url and req_tok:
        if time.time() - _cache["at"] > 240 or not _cache["token"]:
            sep = "&" if "?" in url else "?"
            req = urllib.request.Request(url + sep + urllib.parse.urlencode({"audience": "syrius"}),
                                         headers={"Authorization": f"bearer {req_tok}"})
            with urllib.request.urlopen(req, timeout=20) as r:  # nosec B310 (service officiel de GitHub)
                _cache["token"] = json.loads(r.read())["value"]
            _cache["at"] = time.time()
        return _cache["token"]
    return os.environ.get("SYRIUS_TRAINING_TOKEN", "")


if __name__ == "__main__":  # python training/syrius_auth.py should-train  → « true » ou « false »
    import sys
    base = os.environ.get("SYRIUS_URL", "").rstrip("/")
    if sys.argv[1:] == ["should-train"]:
        try:
            req = urllib.request.Request(base + "/api/training/worker/should-train", headers={
                "Authorization": f"Bearer {token()}", "User-Agent": "SyriusTraining/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310
                print("true" if json.loads(r.read()).get("train") else "false")
        except Exception as e:  # noqa: BLE001
            print(f"false  # {e}", file=sys.stderr)
            print("false")
