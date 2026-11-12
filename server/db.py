"""Stockage SQLite : conversations, messages, mémoire, réglages, sessions."""
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Nouvelle discussion',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (
    ip TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_actions (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS secrets (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "user_name": "",
    "effort": "low",          # low = réponse directe (rapide) ; high = réfléchit avant de répondre
    "brain": "",              # cerveau préféré (groq, gemini, local) ; vide = automatique
    "internet": True,         # recherche web + lecture de pages (pare-feu)
    "voice_reply": False,     # lecture vocale des réponses (dans le téléphone)
    "custom_instructions": "",
}
ALLOWED_EFFORTS = {"low", "high"}


def validate_settings(values: dict) -> dict:
    """Ne garde que les réglages connus, avec le bon type. Lève ValueError sinon."""
    clean: dict[str, Any] = {}
    for key, val in values.items():
        if key not in DEFAULT_SETTINGS:
            continue
        default = DEFAULT_SETTINGS[key]
        if isinstance(default, bool):
            if not isinstance(val, bool):
                raise ValueError(f"{key} doit être vrai/faux")
        elif isinstance(default, str):
            if not isinstance(val, str):
                raise ValueError(f"{key} doit être un texte")
            val = val[:2000]
        if key == "effort" and val not in ALLOWED_EFFORTS:
            raise ValueError("effort invalide")
        clean[key] = val
    return clean


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        try:  # base lisible uniquement par l'utilisateur du serveur
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _q(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _x(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.rowcount

    # --- Conversations -------------------------------------------------
    def create_conversation(self, title: str = "Nouvelle discussion") -> dict:
        now = time.time()
        cid = uuid.uuid4().hex
        self._x("INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?,?,?,?)",
                (cid, title, now, now))
        return self.get_conversation(cid)

    def get_conversation(self, cid: str) -> dict | None:
        rows = self._q("SELECT * FROM conversations WHERE id = ?", (cid,))
        return dict(rows[0]) if rows else None

    def list_conversations(self, query: str = "") -> list[dict]:
        if query:
            like = "%" + query.replace("%", "").replace("_", "") + "%"
            rows = self._q("SELECT * FROM conversations WHERE title LIKE ? "
                           "ORDER BY pinned DESC, updated_at DESC LIMIT 200", (like,))
        else:
            rows = self._q("SELECT * FROM conversations ORDER BY pinned DESC, updated_at DESC LIMIT 200")
        return [dict(r) for r in rows]

    def update_conversation(self, cid: str, title: str | None = None, pinned: bool | None = None) -> None:
        if title is not None:
            self._x("UPDATE conversations SET title = ? WHERE id = ?", (title[:120], cid))
        if pinned is not None:
            self._x("UPDATE conversations SET pinned = ? WHERE id = ?", (1 if pinned else 0, cid))

    def touch_conversation(self, cid: str) -> None:
        self._x("UPDATE conversations SET updated_at = ? WHERE id = ?", (time.time(), cid))

    def delete_conversation(self, cid: str) -> bool:
        return self._x("DELETE FROM conversations WHERE id = ?", (cid,)) > 0

    # --- Messages ------------------------------------------------------
    def add_messages(self, cid: str, messages: list[dict]) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                for m in messages:
                    self._conn.execute(
                        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                        (cid, m["role"], json.dumps(m["content"], ensure_ascii=False), now))
                self._conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def get_messages(self, cid: str) -> list[dict]:
        rows = self._q("SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
                       (cid,))
        return [{"role": r["role"], "content": json.loads(r["content"]), "created_at": r["created_at"]}
                for r in rows]

    # --- Mémoire long terme -------------------------------------------
    def add_memory(self, content: str) -> int:
        with self._lock:
            cur = self._conn.execute("INSERT INTO memories (content, created_at) VALUES (?,?)",
                                     (content[:500], time.time()))
            return cur.lastrowid

    def list_memories(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT id, content, created_at FROM memories ORDER BY id")]

    def delete_memory(self, mid: int) -> bool:
        return self._x("DELETE FROM memories WHERE id = ?", (mid,)) > 0

    # --- Réglages ------------------------------------------------------
    def get_settings(self) -> dict:
        out = dict(DEFAULT_SETTINGS)
        for r in self._q("SELECT key, value FROM settings"):
            if r["key"] in out:
                out[r["key"]] = json.loads(r["value"])
        return out

    def update_settings(self, values: dict) -> dict:
        for key, val in validate_settings(values).items():
            self._x("INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(val)))
        return self.get_settings()

    # --- Secrets (mot de passe, jetons OAuth) ---------------------------
    def get_secret(self, key: str) -> str | None:
        rows = self._q("SELECT value FROM secrets WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_secret(self, key: str, value: str) -> None:
        self._x("INSERT INTO secrets (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # --- Sessions & connexion -----------------------------------------
    def add_session(self, token_hash: str, ttl: float) -> None:
        now = time.time()
        self._x("INSERT INTO sessions (token_hash, created_at, expires_at) VALUES (?,?,?)",
                (token_hash, now, now + ttl))

    def session_valid(self, token_hash: str) -> bool:
        rows = self._q("SELECT expires_at FROM sessions WHERE token_hash = ?", (token_hash,))
        return bool(rows) and rows[0]["expires_at"] > time.time()

    def delete_session(self, token_hash: str) -> None:
        self._x("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def delete_all_sessions(self) -> None:
        self._x("DELETE FROM sessions")

    def record_failed_login(self, ip: str) -> None:
        self._x("INSERT INTO login_attempts (ip, at) VALUES (?, ?)", (ip, time.time()))

    def failed_logins_since(self, ip: str, since: float) -> int:
        self._x("DELETE FROM login_attempts WHERE at < ?", (time.time() - 86400,))
        return self._q("SELECT COUNT(*) AS n FROM login_attempts WHERE ip = ? AND at > ?", (ip, since))[0]["n"]

    def clear_failed_logins(self, ip: str) -> None:
        self._x("DELETE FROM login_attempts WHERE ip = ?", (ip,))

    # --- Actions en attente de confirmation (ex. envoi d'email) ---------
    def add_pending_action(self, kind: str, payload: dict) -> str:
        aid = uuid.uuid4().hex
        self._x("INSERT INTO pending_actions (id, kind, payload, created_at) VALUES (?,?,?,?)",
                (aid, kind, json.dumps(payload, ensure_ascii=False), time.time()))
        return aid

    def get_pending_action(self, aid: str) -> dict | None:
        rows = self._q("SELECT * FROM pending_actions WHERE id = ?", (aid,))
        if not rows:
            return None
        d = dict(rows[0])
        d["payload"] = json.loads(d["payload"])
        return d

    def set_action_status(self, aid: str, status: str, expected: str = "pending") -> bool:
        """Change le statut seulement s'il vaut `expected` (évite un double envoi)."""
        return self._x("UPDATE pending_actions SET status = ? WHERE id = ? AND status = ?",
                       (status, aid, expected)) > 0
