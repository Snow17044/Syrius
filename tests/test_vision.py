"""Vision par photo : vérification de l'image, choix d'une IA qui voit, photo jamais enregistrée."""
import base64
import json

import pytest

from server import vision
from tests.conftest import FakeLLM, H, PASSWORD, login, reply

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 100).decode()


def test_image_valide():
    assert vision.check_image(JPEG) == JPEG


@pytest.mark.parametrize("bad", [
    None, 5, "", "http://exemple.com/a.jpg", "data:image/svg+xml;base64,PHN2Zz4=",
    "data:image/jpeg;base64,!!!", "data:image/jpeg;base64," + base64.b64encode(b"<html>pas une image").decode(),
    "data:image/png;base64," + base64.b64encode(b"\xff\xd8\xff" + b"0" * 10).decode(),
    "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"0" * 3_000_000).decode(),
])
def test_image_refusee(bad):
    with pytest.raises(vision.ImageError):
        vision.check_image(bad)


def test_photo_vers_ia_qui_voit_et_jamais_enregistree(cfg, make_db):
    from fastapi.testclient import TestClient
    from server import auth
    from server.agent import Agent
    from server.app import create_app
    db = make_db()
    auth.set_password(db, PASSWORD)
    fake = FakeLLM([reply("C'est un chat.")], names=("groq", "groq4"))
    fake.providers[1].vision = True
    c = TestClient(create_app(cfg, Agent(cfg, db, llm=fake), db=db), base_url="https://testserver")
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"text": "C'est quoi ?", "image": JPEG}, headers=H)
    assert "chat" in r.text
    req = fake.requests[0]
    assert req["_provider"] == "groq4"  # l'IA qui ne voit pas est sautée
    last = [m for m in req["messages"] if m["role"] == "user"][-1]
    assert last["content"][1] == {"type": "image_url", "image_url": {"url": JPEG}}
    stored = json.dumps(db.get_messages(cid))
    assert "base64" not in stored and "photo jointe" in stored


def test_photo_refusee_par_le_serveur(make_client):
    c = make_client()
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"text": "x", "image": "data:image/gif;base64,R0lG"},
               headers=H)
    assert r.status_code == 400


def test_aucune_ia_qui_voit(make_client):
    c = make_client([reply("x")])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"text": "x", "image": JPEG}, headers=H)
    assert "photo" in r.text and c.fake.requests == []


def test_vision_des_cerveaux(monkeypatch):
    from server.config import Config
    from server.llm import providers_from_config
    monkeypatch.setenv("GROQ_API_KEY", "k")
    ps = {p.model: p.vision for p in providers_from_config(Config())}
    assert ps["meta-llama/llama-4-scout-17b-16e-instruct"] and not ps["openai/gpt-oss-120b"]
