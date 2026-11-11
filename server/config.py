"""Configuration lue depuis les variables d'environnement (fichier .env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "oui", "on"}


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("SYRIUS_DATA_DIR", "data")))
    model: str = field(default_factory=lambda: os.environ.get("SYRIUS_MODEL", "claude-opus-5-5"))
    title_model: str = field(default_factory=lambda: os.environ.get("SYRIUS_TITLE_MODEL", "claude-haiku-5-5"))
    # Cookies "Secure" : obligatoire en production (HTTPS). Désactivable seulement en local.
    cookie_secure: bool = field(default_factory=lambda: _bool("SYRIUS_COOKIE_SECURE", True))
    session_days: int = field(default_factory=lambda: int(os.environ.get("SYRIUS_SESSION_DAYS", "30")))

    # Emails (IMAP lecture / SMTP envoi)
    imap_host: str = field(default_factory=lambda: os.environ.get("SYRIUS_IMAP_HOST", ""))
    imap_port: int = field(default_factory=lambda: int(os.environ.get("SYRIUS_IMAP_PORT", "993")))
    smtp_host: str = field(default_factory=lambda: os.environ.get("SYRIUS_SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SYRIUS_SMTP_PORT", "587")))
    email_user: str = field(default_factory=lambda: os.environ.get("SYRIUS_EMAIL_USER", ""))
    email_password: str = field(default_factory=lambda: os.environ.get("SYRIUS_EMAIL_PASSWORD", ""))
    # "password" (mot de passe d'application, ex. Gmail) ou "outlook" (OAuth2 Microsoft)
    email_auth: str = field(default_factory=lambda: os.environ.get("SYRIUS_EMAIL_AUTH", "password"))
    ms_client_id: str = field(default_factory=lambda: os.environ.get("SYRIUS_MS_CLIENT_ID", ""))

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
