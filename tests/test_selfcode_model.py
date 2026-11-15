"""IA programmeuse : Mistral (Devstral) en priorité si sa clé existe, sinon OpenRouter."""
import importlib.util
import io
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("sc_agent", Path(__file__).resolve().parents[1] / "selfcode" / "agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


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


def test_mistral_prioritaire(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-de-test")
    monkeypatch.setattr(agent.urllib.request, "urlopen", fake({
        "mistral.ai": ["mistral-large-latest", "codestral-latest", "devstral-medium-latest"],
        "openrouter.ai": agent.MODELS}))
    assert agent.pick_model() == "mistral/devstral-medium-latest"
    monkeypatch.setattr(agent.urllib.request, "urlopen", fake({"mistral.ai": None, "openrouter.ai": agent.MODELS}))
    assert agent.pick_model() == f"openrouter/{agent.MODELS[0]}"  # Mistral injoignable : OpenRouter


def test_sans_cle_mistral(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(agent.urllib.request, "urlopen", fake({"openrouter.ai": agent.MODELS}))
    assert agent.pick_model() == f"openrouter/{agent.MODELS[0]}"
    assert agent.pick_model(agent.MODELS[1]) == f"openrouter/{agent.MODELS[1]}"
