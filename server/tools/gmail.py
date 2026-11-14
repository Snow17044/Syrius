"""Gmail par la connexion officielle Google (OAuth), via l'API Gmail.

- Droits demandés : lecture seule des emails + envoi. Syrius ne peut ni supprimer,
  ni modifier, ni marquer comme lu.
- L'envoi ne se fait que sur confirmation de l'utilisateur (comme pour IMAP).
- Bibliothèque standard uniquement.
"""
import base64
import email
import email.policy
import hmac
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from ..config import Config
from ..db import Database
from .email_tool import (MAX_LIST, EmailError, clean_header, extract_body, list_attachments, validate_draft,
                         wrap_untrusted)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # nosec B105 - URL publique
API = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"
REFRESH_KEY = "google_refresh_token"
STATE_KEY = "google_oauth_state"
STATE_TTL = 15 * 60
_ID = re.compile(r"^[0-9a-f]{6,32}$")
FOLDERS = {"INBOX": "in:inbox", "Sent": "in:sent", "Junk": "in:spam", "Spam": "in:spam",
           "Archive": "-in:inbox -in:sent -in:drafts", "Drafts": "in:drafts"}


def _http(method: str, url: str, data: dict | None = None, token: str | None = None, form: bool = False):
    headers = {"User-Agent": "Syrius/1.0"}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310 - URL https fixe
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except ValueError:
            detail = {}
        err = detail.get("error")
        if isinstance(err, dict):
            err = err.get("status") or err.get("message")
        raise EmailError(f"Google a refusé la demande ({e.code} {str(err or '')[:60]})") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise EmailError("Google ne répond pas.") from None


# ---------------------------------------------------------------------------
# Connexion (OAuth)
# ---------------------------------------------------------------------------
def start_url(cfg: Config, db: Database, redirect_uri: str, owner_prefix: str = "") -> str:
    if not (cfg.google_client_id and cfg.google_client_secret):
        raise EmailError("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET manquants dans Vercel (voir le guide).")
    # Préfixe = compte famille concerné (pour retrouver son espace au retour de Google).
    state = owner_prefix + secrets.token_urlsafe(24)
    db.set_secret(STATE_KEY, json.dumps({"state": state, "exp": time.time() + STATE_TTL}))
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cfg.google_client_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent", "state": state,
        "include_granted_scopes": "true"})


def finish(cfg: Config, db: Database, code: str, state: str, redirect_uri: str) -> None:
    raw = db.get_secret(STATE_KEY)
    db.set_secret(STATE_KEY, "")  # usage unique
    try:
        saved = json.loads(raw) if raw else None
    except ValueError:
        saved = None
    if not saved or time.time() > saved.get("exp", 0) or \
            not hmac.compare_digest(str(state).encode(), str(saved.get("state", "")).encode()):
        raise EmailError("Lien de connexion expiré ou invalide : recommence depuis les réglages de Syrius.")
    if not code or len(code) > 1000:
        raise EmailError("Réponse de Google invalide.")
    tok = _http("POST", TOKEN_URL, {"code": code, "client_id": cfg.google_client_id,
                                    "client_secret": cfg.google_client_secret,
                                    "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, form=True)
    if not tok.get("refresh_token"):
        raise EmailError("Google n'a pas donné d'accès durable : recommence la connexion.")
    db.set_secret(REFRESH_KEY, tok["refresh_token"])


def is_connected(db: Database) -> bool:
    return bool(db.get_secret(REFRESH_KEY))


def disconnect(db: Database) -> None:
    db.set_secret(REFRESH_KEY, "")


# ---------------------------------------------------------------------------
# Client Gmail
# ---------------------------------------------------------------------------
class GmailClient:
    def __init__(self, cfg: Config, db: Database):
        self.cfg = cfg
        self.db = db
        self._token: tuple[str, float] | None = None

    def _access_token(self) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        refresh = self.db.get_secret(REFRESH_KEY)
        if not refresh:
            raise EmailError("Gmail n'est pas encore connecté : Réglages → Emails → Connecter Gmail.")
        tok = _http("POST", TOKEN_URL, {"client_id": self.cfg.google_client_id,
                                        "client_secret": self.cfg.google_client_secret,
                                        "refresh_token": refresh, "grant_type": "refresh_token"}, form=True)
        if "access_token" not in tok:
            raise EmailError("Connexion Gmail expirée : reconnecte Gmail dans les réglages.")
        self._token = (tok["access_token"], time.time() + int(tok.get("expires_in", 3000)))
        return self._token[0]

    def _get(self, path: str, **params) -> dict:
        url = API + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        return _http("GET", url, token=self._access_token())

    def _list(self, query: str, limit: int) -> list[dict]:
        limit = max(1, min(int(limit), MAX_LIST))
        ids = [m["id"] for m in self._get("/messages", q=query, maxResults=limit).get("messages", [])]
        out = []
        for mid in ids:
            m = self._get(f"/messages/{mid}", format="metadata", metadataHeaders=["From", "Subject", "Date"])
            hdr = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
            out.append({"uid": m.get("id", ""), "de": clean_header(hdr.get("from")),
                        "sujet": clean_header(hdr.get("subject")), "date": clean_header(hdr.get("date"), 60),
                        "lu": "UNREAD" not in m.get("labelIds", []),
                        "apercu": clean_header(m.get("snippet"), 200)})
        return out

    @staticmethod
    def _folder(folder: str) -> str:
        if folder not in FOLDERS:
            raise EmailError(f"Dossier non autorisé. Choix : {', '.join(sorted(FOLDERS))}")
        return FOLDERS[folder]

    def list_emails(self, folder: str = "INBOX", limit: int = 10, unread_only: bool = False) -> list[dict]:
        q = self._folder(folder) + (" is:unread" if unread_only else "")
        return self._list(q, limit)

    def search_emails(self, query: str, folder: str = "INBOX", limit: int = 10) -> list[dict]:
        q = re.sub(r"[\r\n\"\\{}]", " ", query).strip()[:100]
        if not q:
            raise EmailError("Recherche vide.")
        return self._list(f"{self._folder(folder)} {q}", limit)

    def read_email(self, uid: str, folder: str = "INBOX") -> dict:
        if not _ID.match(str(uid)):
            raise EmailError("Identifiant d'email invalide.")
        raw = self._get(f"/messages/{uid}", format="raw").get("raw", "")
        msg = email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)),
                                       policy=email.policy.default)
        return {"uid": uid, "de": clean_header(msg.get("From")), "a": clean_header(msg.get("To")),
                "sujet": clean_header(msg.get("Subject")), "date": clean_header(msg.get("Date"), 60),
                "pieces_jointes": list_attachments(msg), "contenu": wrap_untrusted(extract_body(msg))}

    def send_email(self, to: str, subject: str, body: str) -> None:
        """Appelé UNIQUEMENT après confirmation explicite de l'utilisateur."""
        validate_draft(to, subject, body)
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        _http("POST", API + "/messages/send", {"raw": raw}, token=self._access_token())
