"""Tests du fonctionnement : discussions, mémoire, historique, outils, connexion à Ollama."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from server.agent import (MAX_HISTORY, display_messages, to_ollama, trim_history,
                          unanswered_tool_uses)
from server.llm import LLMError, OllamaClient
from tests.conftest import H, login, reply


def events_of(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


def new_conv(c) -> str:
    return c.post("/api/conversations", headers=H).json()["id"]


def test_discussion_complete(make_client):
    c = make_client([reply("Bonjour, je suis **Syrius**.")])
    login(c)
    cid = new_conv(c)
    ev = events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": "Salut"}, headers=H).text)
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "Bonjour, je suis **Syrius**."
    assert any(e["type"] == "done" for e in ev) and any(e["type"] == "title" for e in ev)

    conv = c.get(f"/api/conversations/{cid}").json()
    assert conv["title"] == "Titre de test"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]

    req = c.fake.requests[0]
    assert req["model"] == "qwen3:8b"
    assert req["keep_alive"] == -1          # reste chargé : pas d'attente
    assert req["think"] is False            # mode rapide par défaut
    assert req["messages"][0]["role"] == "system" and "Syrius" in req["messages"][0]["content"]
    assert req["messages"][-1] == {"role": "user", "content": "Salut"}


def test_historique_renvoye_a_l_ia(make_client):
    c = make_client([reply("Réponse 1"), reply("Réponse 2")])
    login(c)
    cid = new_conv(c)
    c.post(f"/api/conversations/{cid}/messages", json={"text": "Question 1"}, headers=H)
    c.post(f"/api/conversations/{cid}/messages", json={"text": "Question 2"}, headers=H)
    msgs = c.fake.requests[1]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[2]["content"] == "Réponse 1"


def test_memoire_long_terme(make_client):
    c = make_client([
        reply("", [("remember", {"fact": "S'appelle Alex et adore le café"})]),
        reply("C'est noté."),
        reply("Tu t'appelles Alex."),
    ])
    login(c)
    cid = new_conv(c)
    ev = events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": "Je m'appelle Alex"}, headers=H).text)
    assert any(e["type"] == "memory" for e in ev)
    assert c.get("/api/memories").json()[0]["content"] == "S'appelle Alex et adore le café"

    # Le résultat de l'outil est bien renvoyé au modèle
    second = c.fake.requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "remember"
    assert second[-1]["role"] == "tool" and second[-1]["tool_name"] == "remember"

    # Une NOUVELLE discussion connaît le souvenir
    cid2 = new_conv(c)
    c.post(f"/api/conversations/{cid2}/messages", json={"text": "Comment je m'appelle ?"}, headers=H)
    assert "Alex" in c.fake.requests[-1]["messages"][0]["content"]

    mid = c.get("/api/memories").json()[0]["id"]
    assert c.delete(f"/api/memories/{mid}", headers=H).status_code == 200
    assert c.get("/api/memories").json() == []


def test_menu_des_discussions(make_client):
    c = make_client()
    login(c)
    a, b = new_conv(c), new_conv(c)
    c.patch(f"/api/conversations/{a}", json={"title": "Vacances Italie"}, headers=H)
    c.patch(f"/api/conversations/{b}", json={"pinned": True}, headers=H)
    assert c.get("/api/conversations").json()[0]["id"] == b  # épinglée en premier
    assert [x["id"] for x in c.get("/api/conversations?q=italie").json()] == [a]
    assert c.delete(f"/api/conversations/{a}", headers=H).status_code == 200
    assert c.get(f"/api/conversations/{a}").status_code == 404


def test_reglages_appliques(make_client):
    c = make_client([reply("ok")])
    c.fake.models = ["qwen3:8b", "qwen3:4b"]
    login(c)
    r = c.put("/api/settings", json={"effort": "high", "model": "qwen3:4b", "web_search": False}, headers=H)
    assert r.status_code == 200
    cid = new_conv(c)
    c.post(f"/api/conversations/{cid}/messages", json={"text": "test"}, headers=H)
    req = c.fake.requests[0]
    assert req["think"] is True and req["model"] == "qwen3:4b"
    assert not any(t["function"]["name"] == "web_search" for t in req["tools"])


def test_modele_non_installe_refuse(make_client):
    c = make_client()
    login(c)
    r = c.put("/api/settings", json={"model": "modele-pirate"}, headers=H)
    assert r.status_code == 400


def test_outils_email_absents_si_non_configures(make_client):
    c = make_client([reply("ok")])
    login(c)
    cid = new_conv(c)
    c.post(f"/api/conversations/{cid}/messages", json={"text": "test"}, headers=H)
    names = {t["function"]["name"] for t in c.fake.requests[0]["tools"]}
    assert "read_email" not in names and "remember" in names and "web_search" not in names


def test_cerveau_eteint_message_clair(make_client):
    c = make_client()
    login(c)

    async def broken(payload):
        raise LLMError("Le cerveau local (Ollama) ne répond pas. Est-il démarré ?")
        yield  # pragma: no cover
    c.fake.stream_chat = broken
    cid = new_conv(c)
    ev = events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": "allo"}, headers=H).text)
    assert ev[0]["type"] == "error" and "Ollama" in ev[0]["message"]


def test_appel_d_outil_interrompu_repare():
    stored = [{"role": "user", "content": [{"type": "text", "text": "x"}]},
              {"role": "assistant", "content": [{"type": "tool_use", "id": "c1", "name": "list_emails", "input": {}}]}]
    assert unanswered_tool_uses(stored) == [("c1", "list_emails")]
    assert unanswered_tool_uses(stored[:1]) == []


def test_historique_long_raccourci():
    stored = []
    for i in range(60):
        stored.append({"role": "user", "content": [{"type": "text", "text": f"q{i}"}]})
        stored.append({"role": "assistant", "content": [{"type": "text", "text": f"r{i}"}]})
    out = trim_history(stored)
    assert len(out) <= MAX_HISTORY and out[0]["role"] == "user"


def test_conversion_et_affichage():
    stored = [
        {"role": "user", "content": [{"type": "text", "text": "Mes mails ?"}]},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": "list_emails", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "tool_name": "list_emails",
                                      "content": "..."}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Tu as 2 mails."}]},
    ]
    view = display_messages(stored)
    assert len(view) == 2
    assert view[1]["text"] == "Tu as 2 mails." and view[1]["tools"] == ["Je consulte tes emails"]
    msgs = to_ollama(stored, "SYS")
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "assistant"]


# ---------------------------------------------------------------- vraie connexion HTTP
class _FakeOllama(BaseHTTPRequestHandler):
    """Mini serveur qui répond comme Ollama (format de sa documentation officielle)."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"models": [{"name": "qwen3:8b"}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if req["model"] == "absent":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(json.dumps({"error": "model 'absent' not found"}).encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for chunk in reply("Bonjour Alex", [("get_current_time", {})]):
            self.wfile.write((json.dumps(chunk) + "\n").encode())
            self.wfile.flush()


@pytest.fixture
def ollama_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.mark.anyio
async def test_client_ollama_reel(ollama_url):
    client = OllamaClient(ollama_url)
    chunks = [c async for c in client.stream_chat({"model": "qwen3:8b", "messages": []})]
    text = "".join((c.get("message") or {}).get("content", "") for c in chunks)
    calls = [tc for c in chunks for tc in (c.get("message") or {}).get("tool_calls", [])]
    assert text == "Bonjour Alex" and calls[0]["function"]["name"] == "get_current_time"
    assert await client.list_models() == ["qwen3:8b"]
    with pytest.raises(LLMError, match="pas installé"):
        _ = [c async for c in client.stream_chat({"model": "absent", "messages": []})]


@pytest.mark.anyio
async def test_client_ollama_eteint():
    with pytest.raises(LLMError, match="ne répond pas"):
        _ = [c async for c in OllamaClient("http://127.0.0.1:9").stream_chat({"model": "x", "messages": []})]


def test_url_ollama_invalide():
    with pytest.raises(ValueError):
        OllamaClient("file:///etc/passwd")
