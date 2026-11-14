"""Outils de test : faux cerveaux IA et fausse base Upstash, en mémoire."""
import copy
import fnmatch
import time

import pytest
from fastapi.testclient import TestClient

from server import auth
from server.agent import Agent
from server.app import create_app
from server.config import Config
from server.db import Database
from server.llm import Provider
from server.store_redis import RedisDatabase

PASSWORD = "motdepasse-tres-solide"


# ----------------------------------------------------------------- faux cerveau
def reply(text: str = "", tool_calls: list | None = None) -> list[dict]:
    """Une réponse du modèle, découpée en morceaux comme les API « chat completions »."""
    chunks = []
    words = text.split(" ") if text else []
    for i, w in enumerate(words):
        chunks.append({"choices": [{"index": 0, "delta": {"content": w + (" " if i < len(words) - 1 else "")}}]})
    for i, (name, args) in enumerate(tool_calls or []):
        import json
        raw = json.dumps(args, ensure_ascii=False)
        # Les arguments arrivent en plusieurs morceaux, comme en vrai.
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": i, "id": f"call_{i}_{name}", "type": "function", "function": {"name": name, "arguments": raw[:5]}}]}}]})
        chunks.append({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": i, "function": {"arguments": raw[5:]}}]}}]})
    chunks.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if tool_calls else "stop"}]})
    return chunks


class FakeLLM:
    def __init__(self, responses=None, names=("groq", "gemini")):
        self.responses = list(responses or [])
        self.requests: list[dict] = []
        self.providers = [Provider(n, n.capitalize(), f"https://{n}.example.com/v1", f"{n}-model", "k")
                          for n in names]
        self.fail: dict[str, Exception] = {}  # nom du cerveau -> erreur à lever

    def ordered(self, preferred="", photo=False):
        return sorted(self.providers, key=lambda p: p.name != preferred) if preferred else list(self.providers)

    async def stream_chat(self, provider, body):
        self.requests.append({**copy.deepcopy(body), "_provider": provider.name})
        if provider.name in self.fail:
            raise self.fail[provider.name]
        for chunk in self.responses.pop(0):
            yield chunk


# ----------------------------------------------------------------- fausse base Upstash
class FakeRedis:
    """Implémente en mémoire les commandes Redis utilisées par Syrius."""

    def __init__(self):
        self.data: dict = {}
        self.exp: dict = {}

    def _live(self, k):
        if k in self.exp and self.exp[k] < time.time():
            self.data.pop(k, None)
            self.exp.pop(k, None)
        return k in self.data

    def __call__(self, *args):
        cmd, *a = [str(x) for x in args]
        cmd = cmd.upper()
        d = self.data
        if cmd == "GET":
            return d[a[0]] if self._live(a[0]) else None
        if cmd == "SET":
            k, v, opts = a[0], a[1], [o.upper() for o in a[2:]]
            if "NX" in opts and self._live(k):
                return None
            d[k] = v
            self.exp.pop(k, None)
            if "EX" in opts:
                self.exp[k] = time.time() + int(a[2 + opts.index("EX") + 1])
            return "OK"
        if cmd == "DEL":
            return sum(1 for k in a if d.pop(k, None) is not None)
        if cmd == "INCR":
            d[a[0]] = str(int(d.get(a[0], 0) if self._live(a[0]) else 0) + 1)
            return int(d[a[0]])
        if cmd == "EXPIRE":
            self.exp[a[0]] = time.time() + int(a[1])
            return 1
        if cmd == "HSET":
            h = d.setdefault(a[0], {})
            for k, v in zip(a[1::2], a[2::2]):
                h[k] = v
            return 1
        if cmd == "HGET":
            return d.get(a[0], {}).get(a[1])
        if cmd == "HGETALL":
            return [x for kv in d.get(a[0], {}).items() for x in kv]
        if cmd == "HDEL":
            return 1 if d.get(a[0], {}).pop(a[1], None) is not None else 0
        if cmd in ("SADD", "SREM"):
            s = d.setdefault(a[0], set())
            (s.update if cmd == "SADD" else s.difference_update)(a[1:])
            return 1
        if cmd == "SMEMBERS":
            return list(d.get(a[0], set()))
        if cmd == "ZADD":
            d.setdefault(a[0], {})[a[2]] = float(a[1])
            return 1
        if cmd == "ZREM":
            return 1 if d.get(a[0], {}).pop(a[1], None) is not None else 0
        if cmd == "ZREVRANGE":
            items = sorted(d.get(a[0], {}).items(), key=lambda kv: -kv[1])
            stop = int(a[2])
            return [k for k, _ in items[int(a[1]): None if stop == -1 else stop + 1]]
        if cmd == "RPUSH":
            d.setdefault(a[0], []).extend(a[1:])
            return len(d[a[0]])
        if cmd == "LRANGE":
            lst = d.get(a[0], [])
            stop = int(a[2])
            return lst[int(a[1]): None if stop == -1 else stop + 1]
        if cmd == "KEYS":
            return [k for k in d if fnmatch.fnmatch(k, a[0])]
        raise NotImplementedError(cmd)


# ----------------------------------------------------------------- fixtures
@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.data_dir = tmp_path
    c.cookie_secure = True
    c.redis_url = c.redis_token = ""
    c.imap_host = c.email_user = c.email_password = ""
    c.web_search_key = ""
    c.setup_code = ""
    c.behind_vercel = False
    return c


@pytest.fixture(params=["sqlite", "upstash"])
def backend(request):
    return request.param


@pytest.fixture
def make_db(cfg, backend):
    def _make():
        return Database(cfg.db_path) if backend == "sqlite" else RedisDatabase(FakeRedis())
    return _make


@pytest.fixture
def make_client(cfg, make_db):
    def _make(responses=None, email=False, password=True):
        if email:
            cfg.imap_host = "imap.example.com"
            cfg.smtp_host = "smtp.example.com"
            cfg.email_user = "moi@example.com"
            cfg.email_password = "x"
        db = make_db()
        if password:
            auth.set_password(db, PASSWORD)
        fake = FakeLLM(responses or [])
        agent = Agent(cfg, db, llm=fake)
        app = create_app(cfg, agent, db=db)
        client = TestClient(app, base_url="https://testserver")
        client.fake = fake
        client.db = db
        client.agent = agent
        return client
    return _make


def login(client) -> None:
    r = client.post("/api/login", json={"password": PASSWORD}, headers={"X-Syrius": "1"})
    assert r.status_code == 200, r.text


H = {"X-Syrius": "1"}
