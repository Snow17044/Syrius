"""Discussions à plusieurs : Nova et Aurora réunies dans une même discussion."""
import json

from server import debate, group
from server.agent import display_messages, to_openai
from server.llm import RetryableError
from tests.conftest import H, login, reply


def events_of(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


def new_conv(c, aurora=True) -> str:
    cid = c.post("/api/conversations", headers=H).json()["id"]
    if aurora:
        assert c.put(f"/api/conversations/{cid}/members", json={"aurora": True}, headers=H).json() == {"members": ["aurora"]}
    return cid


def ask(c, cid, text):
    return events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": text}, headers=H).text)


def texts(ev):
    """Texte de chaque intervenant, dans l'ordre : [("nova", …), ("aurora", …)]."""
    out, who = [], "nova"
    for e in ev:
        if e["type"] == "speaker":
            who = e["who"]
        elif e["type"] == "text":
            if not out or out[-1][0] != who:
                out.append((who, ""))
            out[-1] = (who, out[-1][1] + e["text"])
    return out


def test_qui_parle():
    assert group.addressed("Aurora, ton avis ?") == "aurora"
    assert group.addressed("@nova mets un minuteur") == "nova"
    assert group.addressed("  NOVA : salut") == "nova"
    assert group.addressed("Que pensez-vous d'Aurora ?") == ""
    assert group.addressed("Novateur, ce projet") == ""


def test_nova_puis_aurora(make_client):
    c = make_client([reply("Bonne idée, je te fais un plan."), reply("Attention au budget : prévois 20 % de marge.")])
    login(c)
    cid = new_conv(c)
    ev = ask(c, cid, "Je veux ouvrir un café")
    assert texts(ev) == [("nova", "Bonne idée, je te fais un plan."), ("aurora", "Attention au budget : prévois 20 % de marge.")]
    assert ev[-1]["type"] == "title" and sum(e["type"] == "done" for e in ev) == 1
    nova_req, aurora_req = c.fake.requests
    assert group.NOVA_NOTE in nova_req["messages"][0]["content"]  # Nova sait qu'Aurora est là
    assert "tools" not in aurora_req and "Aurora" in aurora_req["messages"][0]["content"]
    assert aurora_req["messages"][-1]["content"].startswith("[Utilisateur] Je veux ouvrir un café")
    assert "[Nova] Bonne idée" in aurora_req["messages"][-1]["content"]
    # Affichage : deux bulles distinctes ; Aurora est marquée
    conv = c.get(f"/api/conversations/{cid}").json()
    assert conv["members"] == ["aurora"]
    assert [(m["role"], m.get("speaker", "")) for m in conv["messages"]] == [("user", ""), ("assistant", ""), ("assistant", "aurora")]


def test_nova_voit_aurora_comme_une_autre_ia(make_client):
    c = make_client([reply("A"), reply("Avis d'Aurora."), reply("Merci Aurora !"), reply("Avec plaisir.")])
    login(c)
    cid = new_conv(c)
    ask(c, cid, "Salut")
    ask(c, cid, "Et maintenant ?")
    msgs = c.fake.requests[2]["messages"]  # 2e réponse de Nova
    assert {"role": "user", "content": "[Aurora] Avis d'Aurora."} in msgs
    assert not any(m["role"] == "assistant" and "Avis d'Aurora" in (m.get("content") or "") for m in msgs)
    aurora_msgs = c.fake.requests[3]["messages"]  # 2e réponse d'Aurora : sa 1re réponse est la sienne
    assert {"role": "assistant", "content": "Avis d'Aurora."} in aurora_msgs


def test_ne_parler_qu_a_l_une(make_client):
    c = make_client([reply("Voilà le code."), reply("Minuteur lancé.")])
    login(c)
    cid = new_conv(c)
    ev = ask(c, cid, "Aurora, écris-moi une fonction qui trie une liste")
    assert texts(ev) == [("aurora", "Voilà le code.")] and len(c.fake.requests) == 1
    ev = ask(c, cid, "Nova, mets un minuteur de 5 minutes")
    assert texts(ev) == [("nova", "Minuteur lancé.")] and not any(e["type"] == "speaker" for e in ev)
    roles = [(m["role"], m.get("speaker", "")) for m in c.get(f"/api/conversations/{cid}").json()["messages"]]
    assert roles == [("user", ""), ("assistant", "aurora"), ("user", ""), ("assistant", "")]


def test_sans_aurora_rien_ne_change(make_client):
    c = make_client([reply("Bonjour !")])
    login(c)
    cid = new_conv(c, aurora=False)
    ev = ask(c, cid, "Aurora, tu es là ?")  # elle n'est pas dans la discussion : Nova répond
    assert texts(ev) == [("nova", "Bonjour !")] and len(c.fake.requests) == 1
    assert group.NOVA_NOTE not in c.fake.requests[0]["messages"][0]["content"]
    assert c.get(f"/api/conversations/{cid}").json()["members"] == []


def test_retirer_aurora_et_suppression(make_client):
    c = make_client()
    login(c)
    cid = new_conv(c)
    assert c.put(f"/api/conversations/{cid}/members", json={"aurora": False}, headers=H).json() == {"members": []}
    new_conv(c)
    other = new_conv(c)
    assert c.delete(f"/api/conversations/{other}", headers=H).status_code == 200
    assert group.members(c.db, other) == []
    assert c.put("/api/conversations/inconnue/members", json={"aurora": True}, headers=H).status_code == 404


def test_aurora_passe_a_une_autre_ia_si_limite(make_client):
    c = make_client([reply("Nova répond."), reply("Aurora répond quand même.")])
    login(c)
    cid = new_conv(c)
    # Nova utilise la 1re IA (groq) ; pour Aurora, groq est saturée : gemini prend le relais.
    orig = c.fake.stream_chat
    calls = {"n": 0}

    async def flaky(provider, body):
        calls["n"] += 1
        if calls["n"] == 2 and provider.name == "groq":
            raise RetryableError("Groq : limite gratuite atteinte.")
        async for ch in orig(provider, body):
            yield ch
    c.fake.stream_chat = flaky
    ev = ask(c, cid, "Salut")
    assert texts(ev)[-1] == ("aurora", "Aurora répond quand même.")


def test_affichage_et_conversion():
    stored = [{"role": "user", "content": [{"type": "text", "text": "Q"}]},
              {"role": "assistant", "content": [{"type": "text", "text": "N1"}]},
              group.aurora_message("A1"),
              {"role": "assistant", "content": [{"type": "text", "text": "N2"}]}]
    shown = display_messages(stored)
    assert [(m.get("speaker", ""), m["text"]) for m in shown[1:]] == [("", "N1"), ("aurora", "A1"), ("", "N2")]
    conv = to_openai(stored, "sys")
    assert conv[3] == {"role": "user", "content": "[Aurora] A1"}


def test_pouce_sur_aurora_entraine_aurora(make_client):
    c = make_client()
    login(c)
    r = c.post("/api/training/aurora", json={"question": "Comment trier une liste ?", "answer": "sorted(liste)"}, headers=H)
    assert r.status_code == 200
    assert debate.trained(c.db)["aurora"][-1]["a"] == "sorted(liste)"
    assert c.post("/api/training/aurora", json={"question": "x", "answer": "y"}, headers=H).status_code == 422
