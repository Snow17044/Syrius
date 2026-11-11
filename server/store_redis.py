"""Stockage sur Upstash Redis (gratuit, sans carte bancaire), via son API REST.

Même interface que `db.Database` (SQLite), pour pouvoir passer de l'un à l'autre.
Bibliothèque standard uniquement.
"""
import json
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from .db import ALLOWED_EFFORTS, DEFAULT_SETTINGS, validate_settings

P = "syrius:"  # préfixe de toutes les clés


class RedisError(Exception):
    pass


class UpstashREST:
    def __init__(self, url: str, token: str, timeout: float = 15):
        if not url.startswith("https://"):
            raise ValueError("L'URL Upstash doit commencer par https://")
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def __call__(self, *args) -> Any:
        body = json.dumps([str(a) for a in args]).encode()
        req = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                out = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RedisError(f"Base de données : erreur {e.code}") from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise RedisError("Base de données injoignable") from None
        if "error" in out:
            raise RedisError("Base de données : " + str(out["error"])[:120])
        return out.get("result")


class RedisDatabase:
    def __init__(self, cmd: Callable[..., Any]):
        self.r = cmd

    # --- utilitaires ---------------------------------------------------
    def _hgetall(self, key: str) -> dict:
        flat = self.r("HGETALL", P + key) or []
        if isinstance(flat, dict):
            return flat
        return dict(zip(flat[0::2], flat[1::2]))

    # --- Conversations -------------------------------------------------
    def create_conversation(self, title: str = "Nouvelle discussion") -> dict:
        now = time.time()
        conv = {"id": uuid.uuid4().hex, "title": title, "created_at": now, "updated_at": now, "pinned": 0}
        self.r("SET", P + "conv:" + conv["id"], json.dumps(conv, ensure_ascii=False))
        self.r("ZADD", P + "convs", now, conv["id"])
        return conv

    def get_conversation(self, cid: str) -> dict | None:
        if not cid.isalnum() or len(cid) > 64:
            return None
        raw = self.r("GET", P + "conv:" + cid)
        return json.loads(raw) if raw else None

    def _save_conv(self, conv: dict) -> None:
        self.r("SET", P + "conv:" + conv["id"], json.dumps(conv, ensure_ascii=False))

    def list_conversations(self, query: str = "") -> list[dict]:
        ids = self.r("ZREVRANGE", P + "convs", 0, 199) or []
        convs = [c for c in (self.get_conversation(i) for i in ids) if c]
        if query:
            q = query.lower()
            convs = [c for c in convs if q in c["title"].lower()]
        convs.sort(key=lambda c: (-int(c.get("pinned", 0)), -c["updated_at"]))
        return convs

    def update_conversation(self, cid: str, title: str | None = None, pinned: bool | None = None) -> None:
        conv = self.get_conversation(cid)
        if not conv:
            return
        if title is not None:
            conv["title"] = title[:120]
        if pinned is not None:
            conv["pinned"] = 1 if pinned else 0
        self._save_conv(conv)

    def touch_conversation(self, cid: str) -> None:
        conv = self.get_conversation(cid)
        if conv:
            conv["updated_at"] = time.time()
            self._save_conv(conv)
            self.r("ZADD", P + "convs", conv["updated_at"], cid)

    def delete_conversation(self, cid: str) -> bool:
        if not self.get_conversation(cid):
            return False
        self.r("DEL", P + "conv:" + cid)
        self.r("DEL", P + "msgs:" + cid)
        self.r("ZREM", P + "convs", cid)
        return True

    # --- Messages ------------------------------------------------------
    def add_messages(self, cid: str, messages: list[dict]) -> None:
        now = time.time()
        if messages:
            self.r("RPUSH", P + "msgs:" + cid, *[json.dumps({"role": m["role"], "content": m["content"],
                                                             "created_at": now}, ensure_ascii=False)
                                                 for m in messages])
        self.touch_conversation(cid)

    def get_messages(self, cid: str) -> list[dict]:
        return [json.loads(x) for x in (self.r("LRANGE", P + "msgs:" + cid, 0, -1) or [])]

    # --- Mémoire long terme -------------------------------------------
    def add_memory(self, content: str) -> int:
        mid = int(self.r("INCR", P + "memory_seq"))
        self.r("HSET", P + "memories", mid, json.dumps({"id": mid, "content": content[:500],
                                                        "created_at": time.time()}, ensure_ascii=False))
        return mid

    def list_memories(self) -> list[dict]:
        items = [json.loads(v) for v in self._hgetall("memories").values()]
        return sorted(items, key=lambda m: m["id"])

    def delete_memory(self, mid: int) -> bool:
        return int(self.r("HDEL", P + "memories", mid) or 0) > 0

    # --- Réglages ------------------------------------------------------
    def get_settings(self) -> dict:
        out = dict(DEFAULT_SETTINGS)
        for k, v in self._hgetall("settings").items():
            if k in out:
                out[k] = json.loads(v)
        return out

    def update_settings(self, values: dict) -> dict:
        for key, val in validate_settings(values).items():
            self.r("HSET", P + "settings", key, json.dumps(val))
        return self.get_settings()

    # --- Secrets -------------------------------------------------------
    def get_secret(self, key: str) -> str | None:
        return self.r("HGET", P + "secrets", key)

    def set_secret(self, key: str, value: str) -> None:
        self.r("HSET", P + "secrets", key, value)

    # --- Sessions & connexion -----------------------------------------
    def add_session(self, token_hash: str, ttl: float) -> None:
        self.r("SET", P + "session:" + token_hash, "1", "EX", int(ttl))
        self.r("SADD", P + "sessions", token_hash)

    def session_valid(self, token_hash: str) -> bool:
        return self.r("GET", P + "session:" + token_hash) is not None

    def delete_session(self, token_hash: str) -> None:
        self.r("DEL", P + "session:" + token_hash)
        self.r("SREM", P + "sessions", token_hash)

    def delete_all_sessions(self) -> None:
        for h in self.r("SMEMBERS", P + "sessions") or []:
            self.r("DEL", P + "session:" + h)
        self.r("DEL", P + "sessions")

    def record_failed_login(self, ip: str) -> None:
        key = P + "fails:" + ip[:64]
        self.r("INCR", key)
        self.r("EXPIRE", key, 15 * 60)

    def failed_logins_since(self, ip: str, since: float) -> int:
        return int(self.r("GET", P + "fails:" + ip[:64]) or 0)

    def clear_failed_logins(self, ip: str) -> None:
        self.r("DEL", P + "fails:" + ip[:64])

    # --- Actions en attente de confirmation ----------------------------
    def add_pending_action(self, kind: str, payload: dict) -> str:
        aid = uuid.uuid4().hex
        self.r("SET", P + "action:" + aid, json.dumps({"id": aid, "kind": kind, "payload": payload,
                                                       "status": "pending", "created_at": time.time()},
                                                      ensure_ascii=False), "EX", 7 * 86400)
        return aid

    def get_pending_action(self, aid: str) -> dict | None:
        if not aid.isalnum() or len(aid) > 64:
            return None
        raw = self.r("GET", P + "action:" + aid)
        return json.loads(raw) if raw else None

    def set_action_status(self, aid: str, status: str, expected: str = "pending") -> bool:
        action = self.get_pending_action(aid)
        if not action or action["status"] != expected:
            return False
        if expected == "pending":
            # Verrou atomique : une seule transition possible depuis « pending » (anti double envoi).
            if self.r("SET", P + "action_lock:" + aid, status, "NX", "EX", 7 * 86400) is None:
                return False
        action["status"] = status
        self.r("SET", P + "action:" + aid, json.dumps(action, ensure_ascii=False), "EX", 7 * 86400)
        return True


__all__ = ["RedisDatabase", "UpstashREST", "RedisError", "ALLOWED_EFFORTS"]
