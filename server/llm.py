"""Connexion au cerveau local (Ollama). Aucune dépendance externe : bibliothèque standard uniquement."""
import asyncio
import json
import threading
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from urllib.parse import urlparse


class LLMError(Exception):
    """Erreur affichable telle quelle à l'utilisateur."""


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 600):
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("SYRIUS_OLLAMA_URL invalide")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _open(self, path: str, payload: dict | None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method="POST" if data else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)  # nosec B310
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode()).get("error", "")
            except ValueError:
                detail = ""
            if e.code == 404 and "not found" in detail:
                model = (payload or {}).get("model", "?")
                raise LLMError(f"Le modèle « {model} » n'est pas installé. Sur le serveur : "
                               f"docker compose exec ollama ollama pull {model}") from None
            raise LLMError(f"Le cerveau local a renvoyé une erreur ({e.code}) : {detail[:150]}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise LLMError("Le cerveau local (Ollama) ne répond pas. Est-il démarré ?") from None

    async def stream_chat(self, payload: dict) -> AsyncIterator[dict]:
        """Envoie une requête /api/chat et renvoie les morceaux au fil de l'eau."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        stop = threading.Event()
        done = object()

        def put(item):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, item)
            except RuntimeError:  # la boucle est déjà fermée (requête abandonnée)
                stop.set()

        def worker():
            try:
                with self._open("/api/chat", {**payload, "stream": True}) as resp:
                    for line in resp:
                        if stop.is_set():
                            return
                        line = line.strip()
                        if line:
                            put(json.loads(line))
            except LLMError as e:
                put(e)
            except (ValueError, OSError):
                put(LLMError("Réponse illisible du cerveau local."))
            finally:
                put(done)

        threading.Thread(target=worker, daemon=True).start()
        try:
            while True:
                item = await queue.get()
                if item is done:
                    return
                if isinstance(item, Exception):
                    raise item
                if item.get("error"):
                    raise LLMError(f"Erreur du cerveau local : {str(item['error'])[:200]}")
                yield item
        finally:
            stop.set()  # l'utilisateur a arrêté : on coupe la génération

    async def chat(self, payload: dict) -> dict:
        def run():
            with self._open("/api/chat", {**payload, "stream": False}) as resp:
                return json.loads(resp.read().decode())
        return await asyncio.to_thread(run)

    async def list_models(self) -> list[str]:
        def run():
            with self._open("/api/tags", None) as resp:
                return [m["name"] for m in json.loads(resp.read().decode()).get("models", [])]
        return await asyncio.to_thread(run)
