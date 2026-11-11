"""Outils de test : un faux Claude qui rejoue des réponses prévues à l'avance."""
from types import SimpleNamespace

import pytest
from anthropic.types.beta import BetaMessage
from fastapi.testclient import TestClient

from server import auth
from server.agent import Agent
from server.app import create_app
from server.config import Config
from server.db import Database

PASSWORD = "motdepasse-tres-solide"


def make_message(content: list[dict], stop_reason: str = "end_turn") -> BetaMessage:
    return BetaMessage.model_validate({
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    })


class FakeStream:
    def __init__(self, message: BetaMessage):
        self.message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for block in self.message.content:
                if block.type == "text":
                    yield SimpleNamespace(type="text", text=block.text)
                elif block.type in ("tool_use", "server_tool_use"):
                    yield SimpleNamespace(type="content_block_start", content_block=block)
        return gen()

    async def get_final_message(self):
        return self.message


class FakeClient:
    """Imite `client.beta.messages.stream(...)` et `client.messages.create(...)`."""

    def __init__(self, responses: list[BetaMessage]):
        self.responses = list(responses)
        self.requests: list[dict] = []
        outer = self

        class _Messages:
            def stream(self, **kwargs):
                import copy
                outer.requests.append(copy.deepcopy(kwargs))
                return FakeStream(outer.responses.pop(0))

            async def create(self, **kwargs):
                return make_message([{"type": "text", "text": "Titre de test"}])

        self.beta = SimpleNamespace(messages=_Messages())
        self.messages = _Messages()


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
        fake = FakeClient(responses or [])
        agent = Agent(cfg, db, client=fake)
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
