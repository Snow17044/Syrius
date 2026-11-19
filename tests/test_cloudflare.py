"""Cloudflare Workers AI : IA de secours gratuite (10 000 neurones par jour) pour Syrius, Aurora et l'IA programmeuse."""
import importlib.util
import io
import json
from pathlib import Path

from server.config import Config
from server.llm import ChatClient, providers_from_config

ACC = "0123456789abcdef0123456789abcdef"
spec = importlib.util.spec_from_file_location("sc_agent_cf", Path(__file__).resolve().parents[1] / "selfcode" / "agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def names(**env):
    return [(p.name, p.base_url, p.model) for p in providers_from_config(Config()) if p.name.startswith("cloudflare")]


def test_branche_seulement_avec_cle_et_identifiant_valide(monkeypatch):
    for k in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(k, raising=False)
    assert names() == []
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cle-de-test")
    assert names() == []  # sans identifiant de compte
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "pas-un-identifiant")
    assert names() == []  # identifiant invalide : jamais intégré dans une adresse
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACC)
    got = names()
    assert [g[0] for g in got] == ["cloudflare", "cloudflare2"]
    assert got[0][1] == f"https://api.cloudflare.com/client/v4/accounts/{ACC}/ai/v1" and got[0][2] == "@cf/zai-org/glm-4.7-flash"


def test_cloudflare_passe_apres_les_ia_rapides(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cle-de-test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACC)
    monkeypatch.setenv("GROQ_API_KEY", "cle-groq")
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-mistral")
    order = [p.name for p in ChatClient(providers_from_config(Config())).ordered()]
    assert order.index("cloudflare") > order.index("mistral") and order.index("cloudflare") > order.index("groq")


def fake(models_by_host):
    def urlopen(req, timeout=0):
        url = req if isinstance(req, str) else req.full_url
        for host, ids in models_by_host.items():
            if host in url:
                if ids is None:
                    raise OSError("injoignable")
                return io.BytesIO(json.dumps({"data": [{"id": i} for i in ids]}).encode())
        raise OSError(url)
    return urlopen


def test_ia_programmeuse_prefere_cloudflare_a_openrouter(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "cle-de-test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACC)
    monkeypatch.setattr(agent.urllib.request, "urlopen", fake({"openrouter.ai": agent.MODELS}))
    assert agent.pick_model() == "openai/@cf/zai-org/glm-4.7-flash"
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "invalide")
    assert agent.pick_model() == f"openrouter/{agent.MODELS[0]}"  # identifiant invalide : on retombe sur OpenRouter
    monkeypatch.delenv("CLOUDFLARE_API_KEY")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACC)
    assert agent.pick_model() == f"openrouter/{agent.MODELS[0]}"


def test_mistral_reste_prioritaire(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-mistral")
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "cle-de-test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACC)
    monkeypatch.setattr(agent.urllib.request, "urlopen", fake({"mistral.ai": ["devstral-latest"], "openrouter.ai": agent.MODELS}))
    assert agent.pick_model() == "mistral/devstral-latest"


def test_aider_recoit_l_adresse_cloudflare(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(agent, "WORK", tmp_path)
    monkeypatch.setattr(agent.subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd, env=kw.get("env")))
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "cle-de-test")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACC)
    agent.aider("openai/@cf/zai-org/glm-4.7-flash", "Fais ceci")
    assert seen["env"]["OPENAI_API_BASE"] == f"https://api.cloudflare.com/client/v4/accounts/{ACC}/ai/v1"
    assert seen["env"]["OPENAI_API_KEY"] == "cle-de-test" and "openai/@cf/zai-org/glm-4.7-flash" in seen["cmd"]
