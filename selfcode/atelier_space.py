"""L'atelier rapide d'Aurora, sur un serveur Hugging Face toujours allumé (Space « syrius-atelier »).

Ton Syrius le réveille dès qu'Aurora lance un projet (POST /wake) : le travail démarre en quelques secondes, sans
attendre GitHub. Par sécurité, il regarde aussi lui-même toutes les 5 minutes s'il reste un projet.

Protection de la clé de l'atelier (le seul secret du serveur) :
- au démarrage, la clé est retirée de l'environnement : le programme se relance (execve) SANS elle et la relit par
  un tube, si bien qu'aucun processus ne la porte dans son environnement ;
- le programme se rend « non inspectable » (PR_SET_DUMPABLE) : le code de l'IA ne peut pas lire sa mémoire ;
- le code de l'IA tourne dans des processus séparés à l'environnement vidé (voir atelier.run_local).
Cette clé ne permet de toute façon que de prendre les projets de l'atelier et d'en rendre le résultat.
"""
from __future__ import annotations

import hmac
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("ATELIER_RUNNER", "local")
import atelier  # noqa: E402

POLL_EVERY = 300
wake = threading.Event()
state = {"busy": False, "last": "", "done": 0}


def hide_token() -> str:
    """Relance le programme sans la clé dans l'environnement ; la clé passe par un tube."""
    if "--fd" in sys.argv:
        fd = int(sys.argv[sys.argv.index("--fd") + 1])
        with os.fdopen(fd, "r") as f:
            return f.read().strip()
    token = os.environ.get("ATELIER_TOKEN", "")
    if not token:
        return ""
    r, w = os.pipe()
    os.write(w, token.encode())
    os.close(w)
    os.set_inheritable(r, True)
    env = {k: v for k, v in os.environ.items() if k != "ATELIER_TOKEN"}
    os.execve(sys.executable, [sys.executable, __file__, "--fd", str(r)], env)
    return ""  # jamais atteint


def not_dumpable() -> None:
    try:
        import ctypes
        ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)  # PR_SET_DUMPABLE = 4 : mémoire et environnement illisibles
    except (OSError, AttributeError):
        pass


def take_all() -> None:
    """Prend et traite les projets en attente, un par un."""
    while True:
        try:
            item = atelier.api("/api/training/worker/atelier-next", {}).get("project")
        except Exception as e:  # noqa: BLE001 — ton Syrius injoignable : on réessaiera
            state["last"] = f"Syrius injoignable : {str(e)[:80]}"
            return
        if not item:
            return
        state["busy"], state["last"] = True, f"projet {item['id']}"
        try:
            atelier.work(item)
            state["done"] += 1
        except Exception as e:  # noqa: BLE001
            atelier.report(item["id"], "failed", 0, {}, f"L'atelier rapide a rencontré une erreur ({str(e)[:120]}).", "")
        finally:
            state["busy"] = False


def worker() -> None:
    while True:
        wake.wait(POLL_EVERY)
        wake.clear()
        take_all()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, text: str) -> None:
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        self._send(200, "Atelier d'Aurora : prêt." + (" Au travail." if state["busy"] else ""))

    def do_POST(self):  # noqa: N802
        if self.path != "/wake":
            return self._send(404, "")
        given = self.headers.get("X-Atelier-Key", "")
        if not (atelier.TOKEN and hmac.compare_digest(given.encode(), atelier.TOKEN.encode())):
            return self._send(403, "")
        wake.set()
        self._send(202, "ok")

    def log_message(self, *args):  # pas de journal des requêtes
        pass


def main() -> None:
    atelier.TOKEN = hide_token()
    not_dumpable()
    if not atelier.TOKEN:
        print("ATELIER_TOKEN absent : configure l'atelier depuis Syrius Code.", flush=True)
    atelier.WORK.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    wake.set()  # au démarrage : on regarde tout de suite s'il y a un projet
    print("Atelier d'Aurora prêt sur le port 7860.", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "7860"))), Handler).serve_forever()  # nosec B104


if __name__ == "__main__":
    main()
