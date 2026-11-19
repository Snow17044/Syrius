"""Syrius n'a plus de fonction Syrius Code : plus de routage vers l'IA de code, plus de scanner, plus de « améliorer »."""
from pathlib import Path

from server.agent import Agent
from server.llm import ChatClient, Provider
from tests.conftest import H, login, reply

WEB = Path(__file__).resolve().parents[1] / "web"


def test_le_choix_des_cerveaux_de_syrius_exclut_l_ia_de_code(make_db):
    llm = ChatClient([Provider("mistral", "Mistral", "http://x", "m", "k"),
                      Provider("codestral", "Mistral · Codestral", "http://x", "c", "k", coding_only=True)])
    from server.config import Config
    brains = Agent(Config(), make_db(), llm=llm).brains()
    assert [b["name"] for b in brains] == ["mistral"]


def test_syrius_n_envoie_plus_les_demandes_de_code_a_codestral(make_client):
    c = make_client([reply("Je te renvoie vers Syrius Code."), reply("ok")])
    login(c)
    asked = []
    real = c.fake.ordered
    c.fake.ordered = lambda preferred="", photo=False, fast=True: (asked.append(preferred), real(preferred, photo, fast))[1]
    cid = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"text": "Écris-moi une fonction Python qui trie une liste"}, headers=H)
    assert asked == [""]  # Syrius : aucune IA de code demandée
    c.patch("/api/settings", headers=H, json={"brain": "codestral"})  # même un ancien réglage est ignoré
    cid2 = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid2}/messages", json={"text": "Salut"}, headers=H)
    assert asked[-1] == ""
    # Aurora, elle, passe bien par l'IA de code
    code_cid = c.post("/api/code/conversations", headers=H).json()["id"]
    c.fake.responses.append(reply("Voici."))
    c.post(f"/api/code/conversations/{code_cid}/messages", json={"text": "Écris une fonction Python qui trie une liste"}, headers=H)
    assert asked[-1] == "codestral"


def test_la_consigne_de_syrius_renvoie_le_code_vers_syrius_code(make_client):
    c = make_client([reply("ok")])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"text": "Salut"}, headers=H)
    system = c.fake.requests[0]["messages"][0]["content"]
    assert "Syrius Code" in system and "ne rédiges pas de programmes" in system


def test_aucune_trace_de_syrius_code_dans_les_ecrans_de_syrius():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = (WEB / "app.js").read_text(encoding="utf-8")
    for gone in ("sc-add", "scan-box", "Sécurité de mes sites", "Pour les demandes de code", "MISTRAL_API_KEY", "/api/selfcode",
                 "/api/sitescan", "/api/code/"):
        assert gone not in html and gone not in js, gone
