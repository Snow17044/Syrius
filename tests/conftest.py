"""Outils de test : un faux cerveau local qui rejoue des réponses prévues à l'avance."""
import copy

import pytest
from fastapi.testclient import TestClient

from server import auth
from server.agent import Agent
from server.app import create_app
from server.config import Config
from server.db import Database

PASSWORD = "motdepasse-tres-solide"


def reply(text: str = "", tool_calls: list | None = None) -> list[dict]:
    """Une réponse du modèle, découpée en morceaux comme le fait Ollama."""
    chunks = []
    words = text.split(" ") if text else []
    for i, w in enumerate(words):
        chunks.append({"message": {"role": "assistant", "content": w + (" " if i < len(words) - 1 else "")},
                       "done": False})
    if tool_calls:
        chunks.append({"message": {"role": "assistant", "content": "",
                                   "tool_calls": [{"function": {"name": n, "arguments": a}} for n, a in tool_calls]},
                       "done": False})
    chunks.append({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"})
    return chunks


class FakeLLM:
    def __init__(self, responses: list[list[dict]] | None = None, models=("qwen3:30b",)):
        self.responses = list(responses or [])
        self.requests: list[dict] = []
        self.models = list(models)

    async def stream_chat(self, payload):
        self.requests.append(copy.deepcopy(payload))
        for chunk in self.responses.pop(0):
            yield chunk

    async def chat(self, payload):
        return {"message": {"role": "assistant", "content": "Titre de test"}, "done": True}

    async def list_models(self):
        return self.models


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.data_dir = tmp_path
    c.cookie_secure = True
    c.imap_host = ""
    c.email_user = ""
    c.email_password = ""
    return c


@pytest.fixture
def make_client(cfg):
    def _make(responses=None, email=False):
        if email:
            cfg.imap_host = "imap.example.com"
            cfg.smtp_host = "smtp.example.com"
            cfg.email_user = "moi@example.com"
            cfg.email_password = "x"
        db = Database(cfg.db_path)
        auth.set_password(db, PASSWORD)
        fake = FakeLLM(responses or [])
        agent = Agent(cfg, db, llm=fake)
        app = create_app(cfg, agent)
        client = TestClient(app, base_url="https://testserver")
        client.fake = fake
        client.db = app.state.db
        client.agent = agent
        return client
    return _make


def login(client) -> None:
    r = client.post("/api/login", json={"password": PASSWORD}, headers={"X-Syrius": "1"})
    assert r.status_code == 200, r.text


H = {"X-Syrius": "1"}
