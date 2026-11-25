"""Connexion aux cerveaux IA (format compatible OpenAI) : Groq, Gemini, ou Ollama en local.

Bibliothèque standard uniquement. Si un cerveau est saturé (limite gratuite atteinte)
ou en panne, Syrius passe automatiquement au suivant.
"""
import asyncio
import json
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlparse


class LLMError(Exception):
    """Erreur affichable telle quelle à l'utilisateur."""


class RetryableError(LLMError):
    """Limite atteinte ou panne passagère : on peut essayer un autre cerveau."""


class TooLargeError(RetryableError):
    """Demande trop lourde pour la limite par minute : on peut réessayer en plus léger."""


@dataclass
class Provider:
    name: str        # identifiant court : groq, gemini, local
    label: str       # nom affiché
    base_url: str
    model: str
    api_key: str = ""
    reasoning: bool = True  # accepte le paramètre reasoning_effort
    vision: bool = False     # sait regarder une photo
    photos_only: bool = False  # cerveau de relais réservé aux photos
    coding_only: bool = False  # cerveau spécialisé code, utilisé seulement pour programmer

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
    if code == 404:  # modèle retiré : on passe au suivant
        return RetryableError(f"{provider.label} : modèle « {provider.model} » introuvable.")
    if code == 413:  # demande trop grosse pour la limite par minute de ce modèle
        return TooLargeError(f"{provider.label} : demande trop lourde pour sa limite gratuite.")
    low = detail.lower()
    if code == 400 and "model" in low and any(k in low for k in ("decommission", "not found", "does not exist",
                                                                   "not supported", "deprecated")):
        return RetryableError(f"{provider.label} : modèle indisponible.")
    if code >= 500:
        return RetryableError(f"{provider.label} est momentanément indisponible.")
    return LLMError(f"{provider.label} a refusé la demande ({code}) : {detail[:150]}")


SLOW_TTFT = 8.0      # secondes avant le premier mot : au-delà, l'IA passe derrière les plus rapides
FAIL_MEMORY = 300    # une IA en échec est mise derrière les autres pendant 5 minutes


# Les IA gratuites les plus capables d'abord quand il faut de l'intelligence (Aurora, atelier) ;
# les plus petites ne servent qu'en secours.
STRONG_FIRST = ("nemotron-3-ultra", "gpt-oss-120b", "codestral", "gemini", "gpt-4.1", "gemma-4-31b", "glm-4.7",
                "mistral", "llama-3.3-70b", "gpt-oss-20b", "gemma-4-26b")


def strength(provider) -> int:
    m = f"{provider.name} {provider.model}".lower()
    return next((i for i, k in enumerate(STRONG_FIRST) if k in m), len(STRONG_FIRST))


class ChatClient:
    # 25 s sans un seul octet = l'IA est bloquée : on passe tout de suite à la suivante (avant : 120 s d'attente).
    def __init__(self, providers: list[Provider], timeout: float = 25):
        self.providers = providers
        self.timeout = timeout
        self.stats: dict[str, dict] = {}  # nom -> {"ttft": délai moyen avant le premier mot, "fail_at": dernier échec}

    GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
    GROQ_CHECK_EVERY, GROQ_RETRY_AFTER = 3600, 600

    def prune_groq(self, now: float | None = None) -> list[str]:
        """Retire les modèles Groq qui n'existent plus (Groq en retire régulièrement). Liste officielle lue au
        plus une fois par heure ; si elle est illisible ou vide, on ne touche à rien."""
        now = time.time() if now is None else now
        groq = [p for p in self.providers if "api.groq.com" in p.base_url and p.api_key]
        if not groq or now < getattr(self, "_groq_next", 0):
            return []
        self._groq_next = now + self.GROQ_RETRY_AFTER
        req = urllib.request.Request(self.GROQ_MODELS_URL, headers={
            "Authorization": f"Bearer {groq[0].api_key}", "User-Agent": "Syrius/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=6) as r:  # nosec B310 (adresse officielle fixe)
                ids = {m.get("id") for m in json.loads(r.read(500_000)).get("data", []) if isinstance(m, dict)}
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return []
        ids.discard(None)
        if not ids:
            return []
        self._groq_next = now + self.GROQ_CHECK_EVERY
        gone = [p for p in groq if p.model not in ids]
        if gone and len(gone) < len(self.providers):  # on ne vide jamais toute la liste
            self.providers = [p for p in self.providers if p not in gone]
            return [p.model for p in gone]
        return []

    def _record(self, name: str, ttft: float) -> None:
        st = self.stats.setdefault(name, {})
        st["ttft"] = ttft if "ttft" not in st else 0.6 * st["ttft"] + 0.4 * ttft

    def _fail(self, name: str) -> None:
        self.stats.setdefault(name, {})["fail_at"] = time.time()

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

    def _rank(self, p: Provider, fast: bool) -> int:
        st = self.stats.get(p.name, {})
        rank = 0
        if fast and p.name.startswith("openrouter"):
            rank += 1  # les IA gratuites d'OpenRouter sont puissantes mais souvent lentes : après les rapides
        if st.get("ttft", 0) > SLOW_TTFT:
            rank += 1
        if time.time() - st.get("fail_at", 0) < FAIL_MEMORY:
            rank += 2
        return rank

    def ordered(self, preferred: str = "", photo: bool = False, fast: bool = True) -> list[Provider]:
        """Ordre d'essai. fast=True : les IA rapides d'abord ; fast=False (« réflexion poussée ») : les plus
        puissantes d'abord. Dans les deux cas, une IA récemment en échec ou lente passe derrière les autres."""
        self.prune_groq()
        pool = sorted((p for p in self.providers if photo or not p.photos_only), key=lambda p: self._rank(p, fast))
        special = [p for p in pool if p.coding_only]
        pool = [p for p in pool if not p.coding_only]
        if preferred and any(p.name == preferred for p in special):
            return special + pool  # cerveau spécialisé demandé en premier, les autres en secours
        return pool

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
            t0 = time.monotonic()
            first = True
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
                        if first:
                            first = False
                            self._record(provider.name, time.monotonic() - t0)
                        put(json.loads(data))
            except LLMError as e:
                if isinstance(e, RetryableError):
                    self._fail(provider.name)
                put(e)
            except (ValueError, OSError):
                self._fail(provider.name)
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


def groq_label(model: str) -> str:
    name = model.split("/")[-1]
    for key, label in (("gpt-oss-120b", "GPT-OSS 120B"), ("gpt-oss-20b", "GPT-OSS 20B"), ("llama-3.3", "Llama 3.3"),
                       ("llama-4", "Llama 4"), ("qwen", "Qwen 3"), ("kimi", "Kimi K2")):
        if key in name:
            return f"Groq · {label}"
    return f"Groq · {name[:30]}"


def openrouter_label(model: str) -> str:
    name = model.split("/")[-1].replace(":free", "")
    if "nemotron-3-ultra" in name:
        return "NVIDIA Nemotron 3 Ultra"
    if name.startswith("gemma-4"):
        return "Google Gemma 4"
    if "nemotron-3.5-super-vl" in name:
        return "NVIDIA Nemotron Vision"
    if "nemotron-3-nano-omni" in name:
        return "NVIDIA Nemotron Omni"
    if "inkling" in name:
        return "Inkling 2"
    return "OpenRouter · " + name[:24]


def _cf_vision(model: str) -> bool:
    """Modèles de Cloudflare Workers AI qui savent regarder une photo."""
    return any(k in model for k in ("gemma-4", "gemma-3", "llama-4", "vision"))


def providers_from_config(cfg) -> list[Provider]:
    out = []
    if cfg.openrouter_api_key:  # IA gratuites les plus puissantes d'abord (limite ~50 messages/jour)
        for i, model in enumerate(cfg.openrouter_models):
            out.append(Provider("openrouter" if i == 0 else f"openrouter{i + 1}", openrouter_label(model),
                                "https://openrouter.ai/api/v1", model, cfg.openrouter_api_key, reasoning=False,
                                vision=any(k in model for k in ("gemma-4", "-vl", "omni", "vision"))))
    if cfg.mistral_api_key:  # en premier : limites gratuites bien plus larges que Groq
        out.append(Provider("mistral", "Mistral", "https://api.mistral.ai/v1", cfg.mistral_model,
                            cfg.mistral_api_key, reasoning=False, vision="small" in cfg.mistral_model))
        # Mistral Code (Codestral) : le modèle spécialisé programmation, réservé aux demandes de code.
        out.append(Provider("codestral", "Mistral · Codestral", "https://api.mistral.ai/v1",
                            cfg.mistral_code_model, cfg.mistral_api_key, reasoning=False, coding_only=True))
    if cfg.groq_api_key:
        # Plusieurs modèles open source sur Groq : chacun a sa propre limite gratuite.
        # Quand l'un est à court, Syrius passe automatiquement au suivant.
        models = [cfg.groq_model] + [m for m in cfg.groq_backup_models if m != cfg.groq_model]
        for i, model in enumerate(models):
            out.append(Provider("groq" if i == 0 else f"groq{i + 1}", groq_label(model),
                                "https://api.groq.com/openai/v1", model, cfg.groq_api_key,
                                reasoning=model.startswith("openai/gpt-oss"),
                                vision="llama-4" in model or "vision" in model))
    if cfg.github_models_token:
        for i, model in enumerate(cfg.github_models):
            out.append(Provider("github" if i == 0 else f"github{i + 1}", f"GitHub · {model.split('/')[-1][:24]}",
                                "https://models.github.ai/inference", model, cfg.github_models_token,
                                reasoning=False, vision="gpt-4" in model))
    if cfg.gemini_api_key:
        out.append(Provider("gemini", "Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                            cfg.gemini_model, cfg.gemini_api_key, vision=True))
    if cfg.cloudflare_api_key and re.fullmatch(r"[0-9a-f]{32}", cfg.cloudflare_account_id or ""):
        # Cloudflare Workers AI (adresse compatible OpenAI) : modèles gratuits dans la limite de 10 000 neurones par jour
        for i, model in enumerate(cfg.cloudflare_models):
            out.append(Provider("cloudflare" if i == 0 else f"cloudflare{i + 1}", f"Cloudflare · {model.split('/')[-1][:24]}",
                                f"https://api.cloudflare.com/client/v4/accounts/{cfg.cloudflare_account_id}/ai/v1", model,
                                cfg.cloudflare_api_key, reasoning=False, vision=_cf_vision(model)))
        # IA de Cloudflare qui « voient », réservées aux photos : fiables (quota quotidien large), en relais
        known = set(cfg.cloudflare_models)
        for i, model in enumerate(m for m in getattr(cfg, "cloudflare_vision_models", []) if m not in known):
            out.append(Provider(f"cloudflare-vue{i + 1}", f"Cloudflare · {model.split('/')[-1][:24]}",
                                f"https://api.cloudflare.com/client/v4/accounts/{cfg.cloudflare_account_id}/ai/v1", model,
                                cfg.cloudflare_api_key, reasoning=False, vision=True, photos_only=True))
    if cfg.openrouter_api_key:  # relais réservés aux photos, en dernier
        known = set(cfg.openrouter_models)
        for i, model in enumerate(m for m in getattr(cfg, "openrouter_vision_models", []) if m not in known):
            out.append(Provider(f"openrouter-vue{i + 1}", openrouter_label(model), "https://openrouter.ai/api/v1",
                                model, cfg.openrouter_api_key, reasoning=False, vision=True, photos_only=True))
    if cfg.ollama_url:
        out.append(Provider("local", "IA locale", cfg.ollama_url.rstrip("/") + "/v1", cfg.ollama_model,
                            reasoning=False))
    return out
