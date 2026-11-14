"""Mot de passe (scrypt) et sessions par cookie."""
import base64
import hashlib
import hmac
import secrets
import time

from .db import Database

# Nom de la clé en base (ce n'est pas un mot de passe)
PASSWORD_KEY = "password_hash"  # nosec B105
COOKIE_NAME = "syrius_session"
MIN_PASSWORD_LEN = 10
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 15 * 60

_SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, digest_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return hmac.compare_digest(digest, expected)


def set_password(db: Database, password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Le mot de passe doit faire au moins {MIN_PASSWORD_LEN} caractères.")
    db.set_secret(PASSWORD_KEY, hash_password(password))
    db.delete_all_sessions()  # un changement de mot de passe déconnecte tous les appareils


def password_is_set(db: Database) -> bool:
    return db.get_secret(PASSWORD_KEY) is not None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_locked_out(db: Database, ip: str) -> bool:
    return db.failed_logins_since(ip, time.time() - LOCKOUT_SECONDS) >= MAX_FAILED_LOGINS


def login(db: Database, ip: str, password: str, session_days: int, name: str = "") -> str | None:
    """Renvoie un jeton de session, ou None si refusé. Sans prénom : le propriétaire ; avec : un membre."""
    from . import family
    if is_locked_out(db, ip):
        return None
    uid = ""
    if name and name.strip():
        found = family.find_member(getattr(db, "base", db), name, password)
        if not found:
            db.record_failed_login(ip)
            return None
        uid = found
    else:
        stored = db.get_secret(PASSWORD_KEY)
        if stored is None or not verify_password(password, stored):
            db.record_failed_login(ip)
            return None
    db.clear_failed_logins(ip)
    return new_session(db, uid, session_days)


def new_session(db: Database, uid: str, session_days: int) -> str:
    # Le compte est inscrit dans le jeton ; tout le jeton est vérifié (empreinte) côté serveur.
    token = (uid + "." if uid else "") + secrets.token_urlsafe(32)
    db.add_session(_token_hash(token), session_days * 86400)
    return token


def check_session(db: Database, token: str | None) -> bool:
    return session_user(db, token) is not None


def session_user(db: Database, token: str | None) -> str | None:
    """Compte de la session : "" pour le propriétaire, identifiant pour un membre, None si invalide."""
    from . import family
    if not token or not db.session_valid(_token_hash(token)):
        return None
    uid = token.split(".", 1)[0] if "." in token else ""
    return uid if family.member_exists(getattr(db, "base", db), uid) else None


def logout(db: Database, token: str | None) -> None:
    if token:
        db.delete_session(_token_hash(token))
