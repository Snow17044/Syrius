"""Syrius sur Discord : clé du bot, personnes autorisées, mot d'éveil « Syrius »."""
from fastapi.testclient import TestClient

from server import transcribe, voicebot
from tests.conftest import H, login, reply
from tests.test_family import member_client

WAV = b"RIFF" + b"\x00" * 4 + b"WAVEfmt " + b"\x00" * 3000
ME = "123456789012345678"


def test_mot_d_eveil():
    assert voicebot.wake("Syrius, quelle heure est-il ?") == "quelle heure est-il ?"
    assert voicebot.wake("hey Sirius quel temps fait-il") == "quel temps fait-il"
    assert voicebot.wake("Syrius.") == ""
    assert voicebot.wake("passe-moi les munitions à gauche") is None
    assert voicebot.wake("le sirius est une étoile") is None


def test_bot_vocal(make_client, monkeypatch):
    owner = make_client(responses=[reply("Il est midi.")])
    login(owner)
    lea = member_client(owner)
    assert lea.get("/api/voicebot/key").status_code == 403
    key = owner.get("/api/voicebot/key").json()["key"]
    assert owner.put("/api/voicebot/ids", json={"ids": ["abc"]}, headers=H).status_code == 400
    assert owner.put("/api/voicebot/ids", json={"ids": [ME]}, headers=H).json() == {"discord_ids": [ME]}
    bot = TestClient(owner.app, base_url="https://testserver")
    B = {**H, "Authorization": f"Bearer {key}", "X-Discord-User": ME, "Content-Type": "audio/wav"}
    assert bot.post("/api/bot/voice", content=WAV, headers={**B, "Authorization": "Bearer faux"}).status_code == 401
    assert bot.get("/api/conversations", headers=B).status_code == 401  # la clé ne sert qu'au bot
    assert bot.post("/api/bot/voice", content=WAV, headers={**B, "X-Discord-User": "999999999999999999"}).status_code == 403
    heard = iter(["passe à gauche", "Syrius, quelle heure est-il ?"])
    monkeypatch.setattr(transcribe, "transcribe", lambda k, d: next(heard))
    r = bot.post("/api/bot/voice", content=WAV, headers=B).json()
    assert r["ignored"] is True  # pas de « Syrius » : ignoré
    r = bot.post("/api/bot/voice", content=WAV, headers=B).json()
    assert r["ignored"] is False and "midi" in r["text"]
    convs = owner.get("/api/conversations").json()
    assert convs[0]["title"] == voicebot.CONV_TITLE
    assert bot.get("/api/bot/config", headers=B).json() == {"discord_ids": [ME]}


def test_createur_du_bot_autorise_automatiquement(make_client):
    owner = make_client()
    login(owner)
    key = owner.get("/api/voicebot/key").json()["key"]
    bot = TestClient(owner.app, base_url="https://testserver")
    B = {**H, "Authorization": f"Bearer {key}"}
    assert bot.post("/api/bot/owner", json={"discord_id": ME}, headers=B).json() == {"discord_ids": [ME]}
    # déjà configuré : un autre identifiant ne remplace pas le premier
    assert bot.post("/api/bot/owner", json={"discord_id": "999999999999999999"}, headers=B).json() == {"discord_ids": [ME]}
    assert bot.post("/api/bot/owner", json={"discord_id": ME}, headers={**H, "Authorization": "Bearer faux"}).status_code == 401
