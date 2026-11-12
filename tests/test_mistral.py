"""Mistral : cerveau principal (modèles open source), Groq en secours."""
from server.config import Config
from server.llm import providers_from_config
from tests.conftest import FakeLLM, H, login, reply
from server.agent import Agent
from server.app import create_app
from fastapi.testclient import TestClient

TOUR = {"title": "Tour", "parts": [{"shape": "box", "pos": [0, 5, 0], "size": [2, 10, 2]}]}


def test_mistral_en_premier_groq_en_secours(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", " 'cle-mistral' ")
    monkeypatch.setenv("GROQ_API_KEY", "cle-groq")
    names = [(p.name, p.base_url, p.model, p.reasoning) for p in providers_from_config(Config())]
    assert names[0] == ("mistral", "https://api.mistral.ai/v1", "mistral-small-latest", False)
    assert names[1][0] == "groq"
    assert providers_from_config(Config())[0].api_key == "cle-mistral"


def test_sans_cle_mistral_rien_ne_change(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "cle-groq")
    assert [p.name for p in providers_from_config(Config())][0] == "groq"


def test_mistral_outil_impose_compatible(cfg, make_db):
    db = make_db()
    from server import auth
    from tests.conftest import PASSWORD
    auth.set_password(db, PASSWORD)
    fake = FakeLLM([reply(tool_calls=[("show_model", TOUR)]), reply("La voilà.")], names=("mistral", "groq"))
    c = TestClient(create_app(cfg, Agent(cfg, db, llm=fake), db=db), base_url="https://testserver")
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"text": "montre la tour Eiffel en 3D"}, headers=H)
    assert '"type": "model"' in r.text
    first = fake.requests[0]
    assert first["_provider"] == "mistral" and first["tool_choice"] == "any"
    assert [t["function"]["name"] for t in first["tools"]] == ["show_model"]
    assert len(fake.requests[1]["tools"]) > 1  # ensuite, tous les outils reviennent
