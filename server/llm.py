"""Connexion aux cerveaux IA (format compatible OpenAI) : Groq, Gemini, ou Ollama en local.

Bibliothèque standard uniquement. Si un cerveau est saturé (limite gratuite atteinte)
ou en panne, Syrius passe automatiquement au suivant.
"""
import asyncio
import json
import threading
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlparse


class LLMError(Exception):
    """Erreur affichable telle quelle à l'utilisateur."""


class RetryableError(LLMError):
    """Limite atteinte ou panne passagère : on peut essayer un autre cerveau."""


@dataclass
class Provider:
    name: str        # identifiant court : groq, gemini, local
    label: str       # nom affiché
    base_url: str
    model: str
    api_key: str = ""
    reasoning: bool = True  # accepte le paramètre reasoning_effort

    def __post_init__(self):
        p = urlparse(self.base_url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise ValueError(f"URL invalide pour {self.name}")
        self.base_url = self.base_url.rstrip("/")


def _http_error_message(provider: Provider, code: int, detail: str) -> LLMError:
    if code == 429:
        return RetryableError(f"{provider.label} : limite gratuite atteinte pour le moment.")
    if code in (401, 403):
        return LLMError(f"{provider.label} : clé API invalide ou refusée (voir README).")
    if code == 404:
        return LLMError(f"{provider.label} : modèle « {provider.model} » introuvable.")
    if code >= 500:
        return RetryableError(f"{provider.label} est momentanément indisponible.")
    return LLMError(f"{provider.label} a refusé la demande ({code}) : {detail[:150]}")


class ChatClient:
    def __init__(self, providers: list[Provider], timeout: float = 120):
        self.providers = providers
        self.timeout = timeout

    def _open(self, provider: Provider, path: str, body: dict | None):
        headers = {"Content-Type": "application/json", "User-Agent": "Syrius/1.0"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(provider.base_url + path, data=data, headers=headers,
                                     method="POST" if data else "GET")
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)  # nosec B310
        except urllib.error.HTTPError as e:
            try:
                raw = json.loads(e.read().decode() or "{}")
                err = raw[0] if isinstance(raw, list) and raw else raw
                detail = str((err.get("error") or {}).get("message", "")) if isinstance(err, dict) else ""
            except (ValueError, AttributeError):
                detail = ""
            raise _http_error_message(provider, e.code, detail) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise RetryableError(f"{provider.label} ne répond pas.") from None

    def ordered(self, preferred: str = "") -> list[Provider]:
        if not preferred:
            return list(self.providers)
        return sorted(self.providers, key=lambda p: p.name != preferred)

    async def stream_chat(self, provider: Provider, body: dict) -> AsyncIterator[dict]:
        """Requête /chat/completions en streaming ; renvoie chaque morceau JSON."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        stop = threading.Event()
        done = object()
        payload = {**body, "model": provider.model, "stream": True}

        def put(item):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, item)
            except RuntimeError:  # requête abandonnée
                stop.set()

        def worker():
            try:
                with self._open(provider, "/chat/completions", payload) as resp:
                    for raw in resp:
                        if stop.is_set():
                            return
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        put(json.loads(data))
            except LLMError as e:
                put(e)
            except (ValueError, OSError):
                put(RetryableError(f"Réponse illisible de {provider.label}."))
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
                if isinstance(item, dict) and item.get("error"):
                    msg = item["error"].get("message", "") if isinstance(item["error"], dict) else item["error"]
                    raise RetryableError(f"{provider.label} : {str(msg)[:150]}")
                yield item
        finally:
            stop.set()


def providers_from_config(cfg) -> list[Provider]:
    out = []
    if cfg.mistral_api_key:  # en premier : limites gratuites bien plus larges que Groq
        out.append(Provider("mistral", "Mistral", "https://api.mistral.ai/v1", cfg.mistral_model,
                            cfg.mistral_api_key, reasoning=False))
    if cfg.groq_api_key:
        out.append(Provider("groq", "Groq", "https://api.groq.com/openai/v1", cfg.groq_model, cfg.groq_api_key))
    if cfg.gemini_api_key:
        out.append(Provider("gemini", "Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                            cfg.gemini_model, cfg.gemini_api_key))
    if cfg.ollama_url:
        out.append(Provider("local", "IA locale", cfg.ollama_url.rstrip("/") + "/v1", cfg.ollama_model,
                            reasoning=False))
    return out
