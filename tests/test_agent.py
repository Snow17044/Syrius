"""Tests du fonctionnement : discussions, mémoire, historique, outils."""
import json

from server.agent import build_history, display_messages, sanitize_assistant, unanswered_tool_uses
from tests.conftest import H, login, make_message


def events_of(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


def test_discussion_complete(make_client):
    c = make_client([make_message([{"type": "text", "text": "Bonjour, je suis **Syrius**."}])])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": "Salut"}, headers=H).text)
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "Bonjour, je suis **Syrius**."
    assert any(e["type"] == "title" for e in ev)
    assert ev[-1]["type"] == "title" or any(e["type"] == "done" for e in ev)

    conv = c.get(f"/api/conversations/{cid}").json()
    assert conv["title"] == "Titre de test"
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]

    req = c.fake.requests[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["fallbacks"] == "default"
    assert req["output_config"] == {"effort": "low"}
    assert "speed" not in req


def test_historique_renvoye_a_l_ia(make_client):
    c = make_client([make_message([{"type": "text", "text": "Réponse 1"}]),
                     make_message([{"type": "text", "text": "Réponse 2"}])])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"text": "Question 1"}, headers=H)
    c.post(f"/api/conversations/{cid}/messages", json={"text": "Question 2"}, headers=H)
    msgs = c.fake.requests[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"][0]["text"] == "Réponse 1"


def test_memoire_long_terme(make_client):
    c = make_client([
        make_message([{"type": "tool_use", "id": "toolu_1", "name": "remember",
                       "input": {"fact": "S'appelle Alex et adore le café"}}], stop_reason="tool_use"),
        make_message([{"type": "text", "text": "C'est noté."}]),
        make_message([{"type": "text", "text": "Tu t'appelles Alex."}]),
    ])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": "Je m'appelle Alex"}, headers=H).text)
    assert any(e["type"] == "memory" for e in ev)
    assert c.get("/api/memories").json()[0]["content"] == "S'appelle Alex et adore le café"

    # Une NOUVELLE discussion connaît le souvenir (via le prompt système).
    cid2 = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid2}/messages", json={"text": "Comment je m'appelle ?"}, headers=H)
    system_text = " ".join(b["text"] for b in c.fake.requests[-1]["system"])
    assert "Alex" in system_text

    # Suppression depuis les réglages
    mid = c.get("/api/memories").json()[0]["id"]
    assert c.delete(f"/api/memories/{mid}", headers=H).status_code == 200
    assert c.get("/api/memories").json() == []


def test_menu_des_discussions(make_client):
    c = make_client()
    login(c)
    a = c.post("/api/conversations", headers=H).json()["id"]
    b = c.post("/api/conversations", headers=H).json()["id"]
    c.patch(f"/api/conversations/{a}", json={"title": "Vacances Italie"}, headers=H)
    c.patch(f"/api/conversations/{b}", json={"pinned": True}, headers=H)
    lst = c.get("/api/conversations").json()
    assert lst[0]["id"] == b  # épinglée en premier
    assert [x["id"] for x in c.get("/api/conversations?q=italie").json()] == [a]
    assert c.delete(f"/api/conversations/{a}", headers=H).status_code == 200
    assert c.get(f"/api/conversations/{a}").status_code == 404


def test_reglages_appliques(make_client):
    c = make_client([make_message([{"type": "text", "text": "ok"}])])
    login(c)
    c.put("/api/settings", json={"effort": "high", "fast_mode": True, "web_search": False}, headers=H)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"text": "test"}, headers=H)
    req = c.fake.requests[0]
    assert req["output_config"]["effort"] == "high"
    assert req["speed"] == "fast"
    assert not any(t.get("name") == "web_search" for t in req["tools"])


def test_outils_email_absents_si_non_configures(make_client):
    c = make_client([make_message([{"type": "text", "text": "ok"}])])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"text": "test"}, headers=H)
    names = {t["name"] for t in c.fake.requests[0]["tools"]}
    assert "read_email" not in names and "remember" in names


def test_appel_d_outil_interrompu_repare():
    hist = [{"role": "user", "content": [{"type": "text", "text": "x"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_9", "name": "list_emails", "input": {}}]}]
    assert unanswered_tool_uses(hist) == ["toolu_9"]
    assert unanswered_tool_uses(hist[:1]) == []


def test_regle_du_modele_de_secours():
    content = [{"type": "thinking", "thinking": "", "signature": "s"},
               {"type": "text", "text": "Début"},
               {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
               {"type": "thinking", "thinking": "", "signature": "t"},
               {"type": "text", "text": "Fin"}]
    out = sanitize_assistant(content)
    assert [b["type"] for b in out] == ["text", "fallback", "thinking", "text"]
    plain = [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "text", "text": "x"}]
    assert sanitize_assistant(plain) == plain  # réflexions conservées telles quelles


def test_affichage_simplifie():
    stored = [
        {"role": "user", "content": [{"type": "text", "text": "Mes mails ?"}]},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                                          {"type": "tool_use", "id": "t", "name": "list_emails", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "..."}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Tu as 2 mails."}]},
    ]
    view = display_messages(stored)
    assert len(view) == 2
    assert view[1]["text"] == "Tu as 2 mails." and view[1]["tools"] == ["Je consulte tes emails"]
    assert build_history(stored)[1]["content"][0]["type"] == "thinking"
