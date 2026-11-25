"""Aurora (Syrius Code) : la plus capable des IA d'abord, raisonnement poussé, place pour du vrai code. Nova reste rapide."""
from pathlib import Path

from server.llm import Provider
from tests.conftest import H, login, reply

ROOT = Path(__file__).resolve().parents[1]


def _providers():
    return [Provider("groq", "Groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "k"),
            Provider("groq2", "Groq 2", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "k"),
            Provider("cloudflare", "CF", "https://cf.example/v1", "@cf/google/gemma-4-26b-a4b-it", "k", reasoning=False),
            Provider("openrouter", "OR", "https://openrouter.ai/api/v1", "nvidia/nemotron-3-ultra-550b-a55b:free", "k",
                     reasoning=False)]


def test_aurora_prend_la_plus_capable_et_reflechit(make_client):
    c = make_client([reply("Voici une réponse soignée.")])
    c.fake.providers = _providers()
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Explique-moi les closures en JS"}, headers=H)
    req = c.fake.requests[0]
    assert req["_provider"] == "openrouter" and req["max_tokens"] == 6000  # Nemotron Ultra d'abord, réponse longue


def test_aurora_raisonnement_pousse_sur_groq(make_client):
    from server.llm import RetryableError
    c = make_client([reply("Réponse.")])
    c.fake.providers = _providers()
    c.fake.fail["openrouter"] = RetryableError("limite")
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Bonjour"}, headers=H)
    groq = next(r for r in c.fake.requests if r["_provider"] == "groq")
    assert groq["reasoning_effort"] == "high"  # avant : « low », d'où des réponses superficielles


def test_nova_reste_rapide(make_client):
    c = make_client([reply("Salut !")])
    c.fake.providers = _providers()
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"text": "Salut"}, headers=H)
    req = c.fake.requests[0]
    assert req["max_tokens"] == 3000 and req.get("reasoning_effort") in (None, "low")


def test_methode_de_developpeuse_senior():
    text = (ROOT / "server/aurore.md").read_text(encoding="utf-8")
    assert "Ta méthode" in text and "relis-toi" in text and "n'invente jamais une fonction" in text
