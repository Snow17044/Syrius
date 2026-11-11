"""Configuration lue depuis les variables d'environnement (Vercel ou fichier .env)."""
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _clean(value: str) -> str:
    """Nettoie une valeur collée à la main : espaces, guillemets, « NOM=valeur »."""
    v = value.strip()
    if "=" in v and v.split("=", 1)[0].strip().isupper() and " " not in v.split("=", 1)[0].strip():
        v = v.split("=", 1)[1].strip()  # ex. UPSTASH_REDIS_REST_URL="https://..."
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    return v


def _env(name: str, default: str = "") -> str:
    return _clean(os.environ.get(name, default))


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "oui", "on"}


def _default_data_dir() -> str:
    # Sur Vercel, seul /tmp est inscriptible (et il est effacé) : il faut Upstash.
    return os.path.join(tempfile.gettempdir(), "syrius") if os.environ.get("VERCEL") else "data"


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(_env("SYRIUS_DATA_DIR", _default_data_dir())))
    # Base de données Upstash Redis (gratuite). Vercel crée ces variables automatiquement.
    redis_url: str = field(default_factory=lambda: _env("UPSTASH_REDIS_REST_URL") or _env("KV_REST_API_URL"))
    redis_token: str = field(default_factory=lambda: _env("UPSTASH_REDIS_REST_TOKEN") or _env("KV_REST_API_TOKEN"))

    # Cerveaux IA gratuits (au moins un des trois)
    # Accepte aussi les noms courts (ex. « groq ») si la variable a été nommée autrement dans Vercel.
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY") or _env("GROQ_KEY") or _env("groq")
                              or _env("GROQ"))
    groq_model: str = field(default_factory=lambda: _env("SYRIUS_GROQ_MODEL", "openai/gpt-oss-120b"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY") or _env("gemini") or _env("GEMINI"))
    gemini_model: str = field(default_factory=lambda: _env("SYRIUS_GEMINI_MODEL", "gemini-flash-latest"))
    ollama_url: str = field(default_factory=lambda: _env("SYRIUS_OLLAMA_URL"))
    ollama_model: str = field(default_factory=lambda: _env("SYRIUS_OLLAMA_MODEL", "qwen3:8b"))

    # Recherche web gratuite (compte Ollama gratuit). Vide = recherche web désactivée.
    web_search_key: str = field(default_factory=lambda: _env("OLLAMA_API_KEY"))

    # Premier mot de passe : code choisi dans Vercel, demandé une seule fois au premier lancement.
    setup_code: str = field(default_factory=lambda: _env("SYRIUS_SETUP_CODE"))
    # Cookies "Secure" : obligatoire en production (HTTPS). Désactivable seulement en local.
    cookie_secure: bool = field(default_factory=lambda: _bool("SYRIUS_COOKIE_SECURE", True))
    session_days: int = field(default_factory=lambda: int(_env("SYRIUS_SESSION_DAYS", "30")))
    behind_vercel: bool = field(default_factory=lambda: bool(os.environ.get("VERCEL")))

    # Emails (IMAP lecture / SMTP envoi)
    imap_host: str = field(default_factory=lambda: _env("SYRIUS_IMAP_HOST"))
    imap_port: int = field(default_factory=lambda: int(_env("SYRIUS_IMAP_PORT", "993")))
    smtp_host: str = field(default_factory=lambda: _env("SYRIUS_SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SYRIUS_SMTP_PORT", "587")))
    email_user: str = field(default_factory=lambda: _env("SYRIUS_EMAIL_USER"))
    email_password: str = field(default_factory=lambda: _env("SYRIUS_EMAIL_PASSWORD"))
    # "password" (mot de passe d'application, ex. Gmail) ou "outlook" (OAuth2 Microsoft)
    email_auth: str = field(default_factory=lambda: _env("SYRIUS_EMAIL_AUTH", "password"))
    ms_client_id: str = field(default_factory=lambda: _env("SYRIUS_MS_CLIENT_ID"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "syrius.db"

    @property
    def email_enabled(self) -> bool:
        if not (self.imap_host and self.email_user):
            return False
        if self.email_auth == "outlook":
            return bool(self.ms_client_id)
        return bool(self.email_password)


config = Config()
