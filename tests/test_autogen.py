"""Syrius crée ses exemples : seuls les exemples propres et aux actions valides sont gardés."""
import json

from fastapi.testclient import TestClient

from server import autogen, github_oidc
from tests.conftest import H, login
from tests.test_github_oidc import KEYS, token


def call(name, args):
    return "C'est parti.\n<tool_call>\n" + json.dumps({"name": name, "arguments": args}) + "\n</tool_call>"


def test_verification_des_exemples():
    assert autogen.check("Combien font 2+2 ?", "4, tout simplement.")
    assert autogen.check("Mets un minuteur de 5 minutes", call("phone_timer", {"seconds": 300}))
    assert not autogen.check("Minuteur", call("phone_timer", {"seconds": -3}))  # action invalide
    assert not autogen.check("Ouvre", call("outil_inconnu", {}))
    assert not autogen.check("Dessine", "Ok.\n<tool_call>\n{pas du json}\n</tool_call>")
    assert autogen.check("Dessine une femme nue", "Désolé, je ne crée pas de contenu sexuel. Autre chose ?")
    assert not autogen.check("Dessine une femme nue", call("phone_image", {"prompt": "a naked woman"}))
    assert not autogen.check("x", "y")  # trop court
    assert autogen.check("Schéma pour réviser", call("show_diagram", {"title": "Réviser", "nodes": [
        {"id": "o", "label": "Réussir"}, {"id": "p1", "label": "Planifier", "parent": "o"}]}))


def test_lot_cree_et_stocke(make_client, monkeypatch):
    owner = make_client()
    login(owner)
    lot = [{"q": "Capitale de l'Italie ?", "a": "Rome !"}, {"q": "capitale de l'italie", "a": "Rome."},
           {"q": "Mets un minuteur de 2 minutes", "a": call("phone_timer", {"seconds": 120})},
           {"q": "Lampe", "a": call("phone_flashlight", {"on": "oui"})}]
    monkeypatch.setattr(autogen, "_ask", lambda p, prompt: json.dumps(lot))
    owner.fake.providers[0].name = "groq"
    monkeypatch.setattr(github_oidc, "_jwks", lambda: KEYS)
    monkeypatch.setattr(github_oidc.time, "time", lambda: 1500)
    worker = TestClient(owner.app, base_url="https://testserver")
    W = {**H, "Authorization": f"Bearer {token()}"}
    r = worker.post("/api/training/worker/generate", headers=W).json()
    assert r["added"] == 2 and r["total"] == 2  # doublon et action invalide écartés
    ex = worker.get("/api/training/worker/examples", headers=W).json()
    assert sum(1 for e in ex if e.get("auto")) == 2
    st = owner.get("/api/training").json()
    assert st["auto"]["total"] == 2
    assert owner.delete("/api/training/auto/0", headers=H).status_code == 200
    assert owner.get("/api/training").json()["auto"]["total"] == 1


def _call(name, args):
    return "Voilà.\n<tool_call>\n" + json.dumps({"name": name, "arguments": args}, ensure_ascii=False) + "\n</tool_call>"


def test_champs_inventes_retires_au_lieu_de_tout_jeter():
    a = _call("show_diagram", {"title": "Guitare", "style": "flowchart", "couleur": "bleu", "nodes": [
        {"id": "o", "label": "Jouer", "children": ["p1"]},
        {"id": "p1", "label": "Accords", "parent": "o", "description": "x"}]})
    fixed, why = autogen.review("Fais un schéma pour apprendre la guitare", a)
    assert why == "" and fixed
    args = json.loads(fixed.split("<tool_call>")[1].split("</tool_call>")[0])["arguments"]
    assert set(args) == {"title", "nodes"} and all(set(n) <= {"id", "label", "parent"} for n in args["nodes"])
    assert fixed.startswith("Voilà.")
    assert autogen.check("Minuteur de 5 minutes", _call("phone_timer", {"seconds": 300, "unit": "s"}))


def test_raison_du_refus_donnee():
    assert autogen.review("Salut", "<tool_call>{pas du json}</tool_call>") == (None, "action illisible")
    assert autogen.review("Salut", _call("pirater", {}))[1] == "outil inconnu"
    assert autogen.review("x", "ok")[1].startswith("question")


def test_theme_choisi_et_raisons_comptees(monkeypatch):
    items = [{"q": "Un poème sur la mer", "a": "La mer chante, la mer danse."},
             {"q": "Mauvais", "a": "<tool_call>{oops}</tool_call>"}]
    monkeypatch.setattr(autogen, "_ask", lambda p, prompt: json.dumps(items))

    class P:
        label, model, base_url, api_key = "Test", "m", "http://x", ""
    res = autogen.generate([P()], theme_index=3)
    assert res["theme"] == autogen.THEMES[3][0]
    assert len(res["kept"]) == 1 and res["reasons"] == {"action illisible": 1}
