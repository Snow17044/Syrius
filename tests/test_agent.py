"""Tests du fonctionnement : discussions, mémoire, historique, outils, cerveaux, base de données."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from server.agent import MAX_HISTORY, display_messages, to_openai, trim_history, unanswered_tool_uses
from server.llm import ChatClient, LLMError, Provider, RetryableError
from tests.conftest import H, login, reply


def events_of(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


def new_conv(c) -> str:
    return c.post("/api/conversations", headers=H).json()["id"]


def ask(c, cid, text) -> list[dict]:
    return events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": text}, headers=H).text)


def test_discussion_complete(make_client):
    c = make_client([reply("Bonjour, je suis **Syrius**.")])
    login(c)
    cid = new_conv(c)
    ev = ask(c, cid, "Salut, peux-tu m'aider à organiser ma semaine de travail ?")
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "Bonjour, je suis **Syrius**."
    assert any(e["type"] == "done" for e in ev) and any(e["type"] == "title" for e in ev)

    conv = c.get(f"/api/conversations/{cid}").json()
    assert conv["title"].startswith("Salut, peux-tu") and len(conv["title"]) <= 50
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]

    req = c.fake.requests[0]
    assert req["_provider"] == "groq" and req["reasoning_effort"] == "low"
    assert req["messages"][0]["role"] == "system" and "Syrius" in req["messages"][0]["content"]
    assert req["messages"][-1]["role"] == "user"


def test_historique_renvoye_a_l_ia(make_client):
    c = make_client([reply("Réponse 1"), reply("Réponse 2")])
    login(c)
    cid = new_conv(c)
    ask(c, cid, "Question 1")
    ask(c, cid, "Question 2")
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
    ev = ask(c, cid, "Je m'appelle Alex")
    assert any(e["type"] == "memory" for e in ev)
    assert c.get("/api/memories").json()[0]["content"] == "S'appelle Alex et adore le café"

    second = c.fake.requests[1]["messages"]
    call = second[-2]["tool_calls"][0]
    assert call["function"]["name"] == "remember"
    assert json.loads(call["function"]["arguments"]) == {"fact": "S'appelle Alex et adore le café"}
    assert second[-1] == {"role": "tool", "tool_call_id": call["id"], "content": "Souvenir n°1 enregistré."}

    cid2 = new_conv(c)  # une NOUVELLE discussion connaît le souvenir
    ask(c, cid2, "Comment je m'appelle ?")
    assert "Alex" in c.fake.requests[-1]["messages"][0]["content"]

    mid = c.get("/api/memories").json()[0]["id"]
    assert c.delete(f"/api/memories/{mid}", headers=H).status_code == 200
    assert c.get("/api/memories").json() == []


def test_bascule_automatique_si_limite_atteinte(make_client):
    c = make_client([reply("Réponse de Gemini")])
    c.fake.fail["groq"] = RetryableError("Groq : limite gratuite atteinte pour le moment.")
    login(c)
    cid = new_conv(c)
    ev = ask(c, cid, "Salut")
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "Réponse de Gemini"
    assert any(e["type"] == "tool" and "Gemini" in e["label"] for e in ev)
    assert [r["_provider"] for r in c.fake.requests] == ["groq", "gemini"]


def test_tous_les_cerveaux_satures(make_client):
    c = make_client()
    c.fake.fail = {n: RetryableError(f"{n} : limite atteinte") for n in ("groq", "gemini")}
    login(c)
    cid = new_conv(c)
    ev = ask(c, cid, "Salut")
    assert ev[-1]["type"] == "error"
    assert c.get(f"/api/conversations/{cid}").json()["messages"] == []


def test_erreur_definitive_pas_de_bascule(make_client):
    c = make_client()
    c.fake.fail["groq"] = LLMError("Groq : clé API invalide")
    login(c)
    cid = new_conv(c)
    ev = ask(c, cid, "Salut")
    assert ev[-1] == {"type": "error", "message": "Groq : clé API invalide"}
    assert [r["_provider"] for r in c.fake.requests] == ["groq"]


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
    login(c)
    r = c.put("/api/settings", json={"effort": "high", "brain": "gemini", "web_search": False}, headers=H)
    assert r.status_code == 200
    ask(c, new_conv(c), "test")
    req = c.fake.requests[0]
    assert req["_provider"] == "gemini" and req["reasoning_effort"] == "high"
    assert not any(t["function"]["name"] == "web_search" for t in req["tools"])
    assert c.put("/api/settings", json={"brain": "inconnu"}, headers=H).status_code == 400
    assert [b["name"] for b in c.get("/api/brains").json()] == ["groq", "gemini"]


def test_outils_email_absents_si_non_configures(make_client):
    c = make_client([reply("ok")])
    login(c)
    ask(c, new_conv(c), "test")
    names = {t["function"]["name"] for t in c.fake.requests[0]["tools"]}
    assert "read_email" not in names and "remember" in names and "web_search" not in names


def test_aucun_cerveau_configure(make_client):
    c = make_client()
    c.fake.providers = []
    login(c)
    ev = ask(c, new_conv(c), "allo")
    assert ev[0]["type"] == "error" and "GROQ_API_KEY" in ev[0]["message"]


def test_premier_lancement_avec_code(make_client, cfg):
    cfg.setup_code = "code-secret-vercel"
    c = make_client(password=False)
    s = c.get("/api/session").json()
    assert s["setup_available"] and not s["password_set"]
    assert c.post("/api/setup", json={"code": "faux", "password": "nouveau-mdp-123"}, headers=H).status_code == 401
    assert c.post("/api/setup", json={"code": "code-secret-vercel", "password": "nouveau-mdp-123"},
                  headers=H).status_code == 200
    # Une fois fait, impossible de recommencer (personne ne peut écraser le mot de passe)
    assert c.post("/api/setup", json={"code": "code-secret-vercel", "password": "pirate-pirate-1"},
                  headers=H).status_code == 403
    assert c.post("/api/login", json={"password": "nouveau-mdp-123"}, headers=H).status_code == 200


def test_premier_lancement_sans_code_impossible(make_client):
    c = make_client(password=False)
    assert not c.get("/api/session").json()["setup_available"]
    assert c.post("/api/setup", json={"code": "", "password": "nouveau-mdp-123"}, headers=H).status_code == 403


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
    msgs = to_openai(stored, "SYS")
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "assistant"]
    assert msgs[3]["tool_call_id"] == "t"


# ---------------------------------------------------------------- vraie connexion HTTP
class _FakeAPI(BaseHTTPRequestHandler):
    """Mini serveur qui répond comme Groq/Gemini (format « chat completions » en flux SSE)."""

    def log_message(self, *a):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != "Bearer bonne-cle":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": {"message": "invalid key"}}')
            return
        if req["model"] == "sature":
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error": {"message": "rate limit"}}')
            return
        assert req["stream"] is True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in reply("Bonjour Alex", [("get_current_time", {})]):
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture
def api_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAPI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()


@pytest.mark.anyio
async def test_client_http_reel(api_url):
    ok = Provider("groq", "Groq", api_url, "m", "bonne-cle")
    client = ChatClient([ok])
    chunks = [c async for c in client.stream_chat(ok, {"messages": []})]
    text = "".join((c["choices"][0]["delta"].get("content") or "") for c in chunks)
    assert text == "Bonjour Alex"
    with pytest.raises(RetryableError, match="limite"):
        _ = [c async for c in client.stream_chat(Provider("groq", "Groq", api_url, "sature", "bonne-cle"), {})]
    with pytest.raises(LLMError, match="clé API"):
        _ = [c async for c in client.stream_chat(Provider("groq", "Groq", api_url, "m", "mauvaise"), {})]


@pytest.mark.anyio
async def test_cerveau_injoignable():
    p = Provider("groq", "Groq", "http://127.0.0.1:9/v1", "m", "k")
    with pytest.raises(RetryableError, match="ne répond pas"):
        _ = [c async for c in ChatClient([p]).stream_chat(p, {})]


def test_url_invalide():
    with pytest.raises(ValueError):
        Provider("x", "X", "file:///etc/passwd", "m")


def test_cle_groq_nom_court(monkeypatch):
    from server.config import Config
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("groq", "gsk_test")
    assert Config().groq_api_key == "gsk_test"


def test_valeurs_collees_nettoyees(monkeypatch):
    from server.config import Config
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", 'UPSTASH_REDIS_REST_URL="https://abc.upstash.io"')
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "  'jeton'  ")
    c = Config()
    assert c.redis_url == "https://abc.upstash.io" and c.redis_token == "jeton"


@pytest.mark.parametrize("url,token", [
    ('UPSTASH_REDIS_REST_URL="https://abc.upstash.io"\nUPSTASH_REDIS_REST_TOKEN="AbCdEfGhIjKlMnOpQrStUvWx123="', ""),
    ("https://abc.upstash.io\n", "\n  AbCdEfGhIjKlMnOpQrStUvWx123=\n"),
    ("", 'export UPSTASH_REDIS_REST_URL="https://abc.upstash.io"\nexport UPSTASH_REDIS_REST_TOKEN="AbCdEfGhIjKlMnOpQrStUvWx123="'),
])
def test_upstash_bloc_colle_en_vrac(url, token):
    from server.app import upstash_settings
    assert upstash_settings(url, token) == ("https://abc.upstash.io", "AbCdEfGhIjKlMnOpQrStUvWx123=")


def test_adresse_upstash_invalide_ne_fait_pas_planter(cfg):
    from fastapi.testclient import TestClient
    from server.app import create_app
    cfg.redis_url, cfg.redis_token = "pas-une-adresse", "x"
    r = TestClient(create_app(cfg), base_url="https://testserver").get("/health")
    assert r.status_code == 200 and r.json()["stockage"] == "temporaire"


@pytest.mark.parametrize("url,token", [("jeton-secret-tres-long-1234567", "https://abc.upstash.io"),
                                       ("abc.upstash.io", "jeton-secret-tres-long-1234567")])
def test_upstash_valeurs_inversees_ou_sans_https(cfg, url, token):
    from server.app import open_database
    from server.store_redis import RedisDatabase
    cfg.redis_url, cfg.redis_token = url, token
    db = open_database(cfg)
    assert isinstance(db, RedisDatabase)
    assert db.r.url == "https://abc.upstash.io" and db.r.token == "jeton-secret-tres-long-1234567"
