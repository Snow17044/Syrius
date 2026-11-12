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


# ---------------------------------------------------------------- plan B : plusieurs modèles Groq
def test_plusieurs_modeles_groq(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "cle-groq")
    ps = providers_from_config(Config())
    assert [p.name for p in ps][:3] == ["groq", "groq2", "groq3"] and len(ps) == 5
    assert ps[0].model == "openai/gpt-oss-120b" and ps[0].reasoning
    assert ps[1].model == "llama-3.3-70b-versatile" and not ps[1].reasoning and ps[1].label == "Groq · Llama 3.3"
    assert all(p.api_key == "cle-groq" for p in ps)


def test_liste_de_modeles_personnalisable(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("SYRIUS_GROQ_MODELS", "openai/gpt-oss-120b, moonshotai/kimi-k2-instruct ,")
    ps = providers_from_config(Config())
    assert [p.model for p in ps if p.name.startswith("groq")] == ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct"]


def test_erreurs_qui_font_passer_au_modele_suivant():
    from server.llm import Provider, RetryableError, _http_error_message
    p = Provider("groq", "Groq", "https://api.groq.com/openai/v1", "m", "k")
    for code, detail in ((429, ""), (404, ""), (413, ""), (500, ""),
                         (400, '{"error":{"message":"The model `x` has been decommissioned"}}')):
        assert isinstance(_http_error_message(p, code, detail), RetryableError), code
    assert not isinstance(_http_error_message(p, 401, ""), RetryableError)
    assert not isinstance(_http_error_message(p, 400, "bad request"), RetryableError)


def test_limite_atteinte_bascule_sur_le_modele_suivant(cfg, make_db):
    from server import auth
    from server.llm import RetryableError
    from tests.conftest import PASSWORD
    db = make_db()
    auth.set_password(db, PASSWORD)
    fake = FakeLLM([reply("Réponse de secours.")], names=("groq", "groq2"))
    fake.fail["groq"] = RetryableError("Groq : limite gratuite atteinte pour le moment.")
    c = TestClient(create_app(cfg, Agent(cfg, db, llm=fake), db=db), base_url="https://testserver")
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"text": "salut"}, headers=H)
    assert "Je passe sur" in r.text and "secours." in r.text
    assert [q["_provider"] for q in fake.requests] == ["groq", "groq2"]
