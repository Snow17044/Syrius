"""Demande à ton Syrius de trier les nouveaux emails (appelé par le workflow « Tri des emails »).

Seul le nombre d'emails triés revient ici : le contenu des emails ne quitte jamais ton Syrius.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import syrius_auth  # noqa: E402


def main() -> None:
    url = os.environ["SYRIUS_URL"].rstrip("/") + "/api/training/worker/mail-sort"
    req = urllib.request.Request(url, data=b"{}", method="POST", headers={
        "Authorization": f"Bearer {syrius_auth.token()}", "Content-Type": "application/json",
        "X-Syrius": "1", "User-Agent": "SyriusMailSort/1.0"})
    with urllib.request.urlopen(req, timeout=280) as r:  # nosec B310 (adresse de ton Syrius)
        res = json.loads(r.read(10_000) or b"{}")
    if res.get("disabled"):
        print("Tri automatique désactivé dans Syrius Code.")
    elif res.get("error"):  # le journal de GitHub est public : la raison détaillée reste dans Syrius Code
        print("::warning::Le tri n'a pas pu se faire cette fois : la raison est affichée dans Syrius Code (Emails).")
    else:
        print(f"{res.get('new', 0)} nouvel(s) email(s) trié(s).")


if __name__ == "__main__":
    main()
