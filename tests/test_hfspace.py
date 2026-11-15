"""Lancement du bot Discord sur un Space Hugging Face, depuis les réglages du propriétaire."""
from pathlib import Path

from server import hfspace
from tests.conftest import H, login
from tests.test_family import member_client

DTOKEN = ".".join(["A" * 24, "B" * 6, "C" * 38])  # faux jeton au bon format (pas un vrai)


def test_dockerfile_identique():
    assert hfspace.DOCKERFILE == (Path(__file__).parents[1] / "discord-bot" / "Dockerfile").read_text(encoding="utf-8")


def test_creation_du_space(make_client, monkeypatch):
    owner = make_client()
    login(owner)
    owner.agent.cfg.hf_token = "hf_test"
    calls = []

    def fake(token, method, path, body=None, ctype="application/json", timeout=30):
        calls.append((method, path, body))
        if path == "/api/whoami-v2":
            return 200, {"name": "morgane"}
        return 200, {}
    monkeypatch.setattr(hfspace, "_call", fake)
    lea = member_client(owner)
    assert lea.post("/api/voicebot/space", json={"discord_token": DTOKEN}, headers=H).status_code == 403
    assert owner.post("/api/voicebot/space", json={"discord_token": "x" * 60}, headers=H).status_code == 400
    r = owner.post("/api/voicebot/space", json={"discord_token": DTOKEN}, headers=H)
    assert r.status_code == 200 and r.json()["url"] == "https://huggingface.co/spaces/morgane/syrius-discord"
    paths = [p for _, p, _ in calls]
    assert "/api/repos/create" in paths and "/api/spaces/morgane/syrius-discord/commit/main" in paths
    secrets = [b.decode() for m, p, b in calls if p.endswith("/secrets")]
    assert any("DISCORD_TOKEN" in s and DTOKEN in s for s in secrets)
    assert any("SYRIUS_BOT_KEY" in s and "syb_" in s for s in secrets)
    assert DTOKEN not in str(owner.db.get_secret("family_voicebot_v1"))  # le jeton Discord n'est pas gardé


def test_cle_hf_en_lecture_seule(make_client, monkeypatch):
    owner = make_client()
    login(owner)
    owner.agent.cfg.hf_token = "hf_test"
    monkeypatch.setattr(hfspace, "_call", lambda t, m, p, *a, **k: (200, {"name": "m"}) if "whoami" in p else (403, {}))
    r = owner.post("/api/voicebot/space", json={"discord_token": DTOKEN}, headers=H)
    assert r.status_code == 400 and "Write" in r.json()["detail"]
