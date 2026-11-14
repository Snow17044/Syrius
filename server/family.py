"""Syrius en famille : le propriétaire + jusqu'à 10 proches, chacun avec son espace privé.

- Le propriétaire n'a rien à gérer : il partage un code d'invitation, chacun crée son compte (prénom + mot
  de passe) et le gère lui-même.
- Chaque personne a ses propres discussions, mémoire, réglages, rappels et connexion email : la base est
  « aiguillée » vers l'espace de la personne connectée (contexte de la requête). Les comptes, les sessions,
  l'invitation, les quotas et le cache des maquettes 3D restent dans l'espace commun.
- Quotas équitables : chacun a sa part par jour des ressources gratuites limitées (IA la plus puissante,
  création de maquettes 3D), pour qu'une seule personne ne prive pas les autres.
"""
from __future__ import annotations

import base64
import contextvars
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import auth

MAX_MEMBERS = 10
USERS_KEY = "family_users_v1"
INVITE_KEY = "family_invite_v1"
OWNER = ""  # identifiant du propriétaire (ses données restent à leur place d'origine)
_UID = re.compile(r"^[0-9a-f]{12}$")
_NAME = re.compile(r"^[\w][\w '\-]{0,29}$", re.UNICODE)
TZ = ZoneInfo("Europe/Paris")

CURRENT = contextvars.ContextVar("syrius_user", default=OWNER)
TEST_SECONDS = 24 * 3600  # durée d'un compte de test

# Méthodes toujours servies par l'espace commun.
GLOBAL_METHODS = {"add_session", "session_valid", "delete_session", "delete_all_sessions",
                  "record_failed_login", "failed_logins_since", "clear_failed_logins"}
GLOBAL_SECRETS = (auth.PASSWORD_KEY, "family_", "quota:", "m3d:")


class FamilyError(Exception):
    pass


class ScopedDB:
    """Même interface que la base, aiguillée vers l'espace de la personne connectée."""

    def __init__(self, base, factory):
        self._base = base
        self._factory = factory
        self._spaces: dict[str, object] = {}

    @property
    def base(self):
        return self._base

    def for_user(self, uid: str):
        if not uid:
            return self._base
        if not _UID.match(uid):
            raise FamilyError("compte invalide")
        if uid not in self._spaces:
            self._spaces[uid] = self._factory(uid)
        return self._spaces[uid]

    def current(self):
        return self.for_user(CURRENT.get())

    def _space_for_secret(self, key: str):
        return self._base if str(key).startswith(GLOBAL_SECRETS) else self.current()

    def get_secret(self, key: str):
        return self._space_for_secret(key).get_secret(key)

    def set_secret(self, key: str, value: str) -> None:
        self._space_for_secret(key).set_secret(key, value)

    def wipe(self, uid: str) -> None:
        """Efface toutes les données d'un compte retiré ou expiré."""
        from .store_redis import RedisDatabase
        if not _UID.match(uid or ""):
            return
        space = self._spaces.pop(uid, None) or self._factory(uid)
        if isinstance(space, RedisDatabase):
            keys = space.r("KEYS", space.p + "*") or []
            for i in range(0, len(keys), 100):
                space.r("DEL", *keys[i:i + 100])
            return
        path = getattr(space, "path", None)
        conn = getattr(space, "_conn", None)
        if conn is not None:
            conn.close()
        if path:
            for p in (Path(path), Path(str(path) + "-wal"), Path(str(path) + "-shm")):
                p.unlink(missing_ok=True)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._base if name in GLOBAL_METHODS else self.current(), name)


def space_factory(base, data_dir: Path):
    """Crée l'espace privé d'un membre : clés préfixées (Upstash) ou fichier à part (SQLite)."""
    from .db import Database
    from .store_redis import RedisDatabase

    def make(uid: str):
        if isinstance(base, RedisDatabase):
            return RedisDatabase(base.r, prefix=f"syrius:u:{uid}:")
        folder = Path(data_dir) / "membres"
        folder.mkdir(parents=True, exist_ok=True)
        return Database(folder / f"{uid}.db")
    return make


# ------------------------------------------------------------------ comptes
def _users(base) -> dict:
    try:
        data = json.loads(base.get_secret(USERS_KEY) or "{}")
    except ValueError:
        data = {}
    return {k: v for k, v in data.items() if _UID.match(k) and isinstance(v, dict)}


def _save_users(base, users: dict) -> None:
    base.set_secret(USERS_KEY, json.dumps(users, ensure_ascii=False))


def _alive(u: dict, now: float | None = None) -> bool:
    exp = u.get("expires")
    return not exp or float(exp) > (now or time.time())


def _active(base) -> dict:
    return {k: v for k, v in _users(base).items() if _alive(v)}


def purge_expired(base, wipe=None) -> None:
    """Retire les comptes de test arrivés à échéance (et efface leurs données)."""
    users = _users(base)
    dead = [uid for uid, u in users.items() if not _alive(u)]
    if not dead:
        return
    for uid in dead:
        del users[uid]
    _save_users(base, users)
    for uid in dead:
        if wipe:
            wipe(uid)


def is_full(base) -> bool:
    """10 comptes en tout (famille + tests en cours) : plus aucun lien ne peut être créé."""
    return len(_active(base)) >= MAX_MEMBERS


def is_guest(base, uid: str) -> bool:
    return bool(uid) and bool(_users(base).get(uid, {}).get("guest"))


def account(base, uid: str) -> dict:
    u = _users(base).get(uid, {}) if uid else {}
    return {"owner": not uid, "name": u.get("name", ""), "guest": bool(u.get("guest")),
            **({"expires": int(u["expires"])} if u.get("expires") else {})}


def members(base) -> list[dict]:
    return [{"id": uid, "name": u.get("name", ""), "created": u.get("created", 0), "guest": bool(u.get("guest")),
             **({"expires": int(u["expires"])} if u.get("expires") else {})}
            for uid, u in sorted(_active(base).items(), key=lambda kv: kv[1].get("created", 0))]


def member_name(base, uid: str) -> str:
    return _users(base).get(uid, {}).get("name", "") if uid else ""


def clean_name(name: str) -> str:
    n = " ".join(str(name or "").split())
    if not _NAME.match(n):
        raise FamilyError("Prénom invalide (lettres, espaces, tirets ; 30 caractères au plus).")
    return n


def invite_code(base, renew: bool = False) -> str:
    """Code à partager avec la famille (le propriétaire peut le changer à tout moment).
    Famille complète : plus de code du tout."""
    if is_full(base):
        if base.get_secret(INVITE_KEY):
            base.set_secret(INVITE_KEY, "")
        if renew:
            raise FamilyError(f"La famille est complète ({MAX_MEMBERS} comptes) : impossible de créer un lien.")
        return ""
    code = base.get_secret(INVITE_KEY)
    if renew or not code:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans caractères ambigus (O/0, I/1)
        code = "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))
        base.set_secret(INVITE_KEY, code)
    return code


def _same_code(given: str, code: str) -> bool:
    norm = lambda c: re.sub(r"[^A-Z0-9]", "", str(c).upper())  # noqa: E731
    return bool(code) and hmac.compare_digest(norm(given).encode(), norm(code).encode())


def join(base, code: str, name: str, password: str) -> str:
    """Création d'un compte avec le code d'invitation. Renvoie l'identifiant du nouveau membre."""
    if is_full(base):
        raise FamilyError(f"La famille est complète ({MAX_MEMBERS} comptes).")
    if not _same_code(code, base.get_secret(INVITE_KEY) or ""):
        raise FamilyError("Code d'invitation incorrect.")
    name = clean_name(name)
    if len(password) < auth.MIN_PASSWORD_LEN:
        raise FamilyError(f"Le mot de passe doit faire au moins {auth.MIN_PASSWORD_LEN} caractères.")
    users = _users(base)
    if len(_active(base)) >= MAX_MEMBERS:
        raise FamilyError(f"La famille est complète ({MAX_MEMBERS} comptes).")
    if any(u.get("name", "").casefold() == name.casefold() for u in users.values()):
        raise FamilyError("Ce prénom est déjà utilisé : ajoute une initiale (ex. « Léa B »).")
    uid = secrets.token_hex(6)
    users[uid] = {"name": name, "pw": auth.hash_password(password), "created": time.time()}
    _save_users(base, users)
    return uid


def create_test(base) -> str:
    """Lien de test : compte temporaire (24 h), sans mot de passe. Renvoie le secret du lien."""
    if is_full(base):
        raise FamilyError(f"La famille est complète ({MAX_MEMBERS} comptes en tout) : impossible de créer un lien.")
    users = _users(base)
    used = {u.get("name", "") for u in users.values()}
    n = next(i for i in range(1, 100) if f"Testeur {i}" not in used)
    uid, secret, now = secrets.token_hex(6), secrets.token_urlsafe(24), time.time()
    users[uid] = {"name": f"Testeur {n}", "guest": True, "created": now, "expires": now + TEST_SECONDS,
                  "link": hashlib.sha256(secret.encode()).hexdigest()}
    _save_users(base, users)
    return f"{uid}-{secret}"


def claim_test(base, link: str) -> tuple[str, float] | None:
    """Vérifie un lien de test. Renvoie (identifiant, secondes restantes) ou None."""
    uid, _, secret = str(link or "").partition("-")
    u = _users(base).get(uid) if _UID.match(uid) else None
    want = (u or {}).get("link", "")
    given = hashlib.sha256(secret.encode()).hexdigest()
    if not u or not u.get("guest") or not want or not hmac.compare_digest(given, want) or not _alive(u):
        return None
    return uid, float(u["expires"]) - time.time()


def find_member(base, name: str, password: str) -> str | None:
    """Vérifie prénom + mot de passe d'un membre (temps constant sur le mot de passe)."""
    want = " ".join(str(name or "").split()).casefold()
    for uid, u in _active(base).items():
        if u.get("guest"):
            continue
        if u.get("name", "").casefold() == want:
            return uid if auth.verify_password(password, u.get("pw", "")) else None
    auth.verify_password(password, auth.hash_password("x" * 12))  # même durée si le prénom n'existe pas
    return None


def set_member_password(base, uid: str, current: str, new: str) -> None:
    users = _users(base)
    u = users.get(uid)
    if not u or not auth.verify_password(current, u.get("pw", "")):
        raise FamilyError("Mot de passe actuel incorrect")
    if len(new) < auth.MIN_PASSWORD_LEN:
        raise FamilyError(f"Le mot de passe doit faire au moins {auth.MIN_PASSWORD_LEN} caractères.")
    u["pw"] = auth.hash_password(new)
    _save_users(base, users)


def check_member_password(base, uid: str, password: str) -> bool:
    u = _users(base).get(uid)
    if not u:
        return False
    if u.get("guest"):
        return True  # compte de test : pas de mot de passe
    return auth.verify_password(password, u.get("pw", ""))


REPORTS_KEY = "family_reports_v1"


def add_report(base, who: str, text: str, reason: str) -> None:
    """Contenu de l'IA signalé par un utilisateur (visible par le propriétaire)."""
    try:
        reports = json.loads(base.get_secret(REPORTS_KEY) or "[]")
    except ValueError:
        reports = []
    reports.append({"at": int(time.time()), "who": who[:40], "reason": reason[:300], "text": text[:1500]})
    base.set_secret(REPORTS_KEY, json.dumps(reports[-50:], ensure_ascii=False))


def reports(base) -> list[dict]:
    try:
        data = json.loads(base.get_secret(REPORTS_KEY) or "[]")
    except ValueError:
        return []
    return [r for r in data if isinstance(r, dict)][::-1]


def clear_reports(base) -> None:
    base.set_secret(REPORTS_KEY, "[]")


def remove_member(base, uid: str) -> bool:
    users = _users(base)
    if uid not in users:
        return False
    del users[uid]
    _save_users(base, users)
    return True


def member_exists(base, uid: str) -> bool:
    return not uid or uid in _active(base)


GUEST = contextvars.ContextVar("syrius_guest", default=False)


def email_allowed(cfg) -> bool:
    """Les proches n'ont accès qu'à LEUR boîte (Gmail connecté par chacun) ; une boîte configurée sur le
    serveur (IMAP / Outlook) est celle du propriétaire et lui reste réservée. Pas d'emails pour les tests."""
    if GUEST.get():
        return False
    return bool(cfg.email_enabled) and (cfg.email_mode == "google" or not CURRENT.get())


# ------------------------------------------------------------------ quotas équitables
LIMITS = {  # par personne et par jour
    "power": {"owner": 25, "member": 10, "guest": 5},  # IA la plus puissante (OpenRouter, ~50 messages/jour)
    "m3d": {"owner": 2, "member": 1, "guest": 1},      # créations de maquettes 3D sur mesure (quota Hugging Face)
}


def _quota_key(kind: str, uid: str) -> str:
    return f"quota:{datetime.now(TZ):%Y-%m-%d}:{kind}:{uid or 'owner'}"


def quota_left(base, kind: str, uid: str) -> int:
    limit = LIMITS[kind]["owner" if not uid else "guest" if is_guest(base, uid) else "member"]
    try:
        used = int(base.get_secret(_quota_key(kind, uid)) or 0)
    except ValueError:
        used = 0
    return max(0, limit - used)


def quota_use(base, kind: str, uid: str) -> None:
    key = _quota_key(kind, uid)
    try:
        used = int(base.get_secret(key) or 0)
    except ValueError:
        used = 0
    base.set_secret(key, str(used + 1))


# ------------------------------------------------------------------ maquettes 3D déjà créées (partagées)
CACHE_MAX = 30
CHUNK = 600_000


def _cache_id(key: str) -> str:
    norm = " ".join(re.sub(r"[^\w\s]", " ", str(key).lower()).split())
    return hashlib.sha256(norm.encode()).hexdigest()[:24]


def cache_get(base, key: str) -> bytes | None:
    cid = _cache_id(key)
    try:
        n = int(base.get_secret(f"m3d:{cid}:n") or 0)
    except ValueError:
        n = 0
    if not 0 < n <= 12:
        return None
    parts = [base.get_secret(f"m3d:{cid}:{i}") or "" for i in range(n)]
    if not all(parts):
        return None
    try:
        data = b"".join(base64.b64decode(p) for p in parts)
    except ValueError:
        return None
    return data if data[:4] == b"glTF" else None


def cache_put(base, key: str, data: bytes) -> None:
    cid = _cache_id(key)
    chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
    if not chunks or len(chunks) > 12:
        return
    for i, c in enumerate(chunks):
        base.set_secret(f"m3d:{cid}:{i}", base64.b64encode(c).decode())
    base.set_secret(f"m3d:{cid}:n", str(len(chunks)))
    try:
        index = [x for x in json.loads(base.get_secret("m3d:index") or "[]") if x != cid]
    except ValueError:
        index = []
    index.append(cid)
    for old in index[:-CACHE_MAX]:  # les plus anciennes sont oubliées
        base.set_secret(f"m3d:{old}:n", "0")
        for i in range(12):
            base.set_secret(f"m3d:{old}:{i}", "")
    base.set_secret("m3d:index", json.dumps(index[-CACHE_MAX:]))
