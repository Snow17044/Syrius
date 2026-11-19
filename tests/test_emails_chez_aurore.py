"""Les emails ne sont plus dans Syrius : ils se gèrent dans Syrius Code (Aurore), propriétaire seulement."""
import json
from pathlib import Path

from tests.conftest import H, login, reply
from tests.test_family import member_client

WEB = Path(__file__).resolve().parents[1] / "web"


def test_syrius_refuse_les_outils_d_emails_meme_si_l_ia_les_appelle(make_client):
    c = make_client([reply("", [("list_emails", {})]), reply("Désolé.")], email=True)
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"text": "lis mes mails"}, headers=H)
    sent_tools = [t["function"]["name"] for t in c.fake.requests[0].get("tools", [])]
    assert "list_emails" not in sent_tools and "draft_email" not in sent_tools  # Syrius n'a plus ces outils
    results = [m["content"] for r in c.fake.requests for m in r["messages"] if m["role"] == "tool"]
    assert any("Syrius Code" in x for x in results)  # et un appel forcé est refusé


def test_aurore_a_les_outils_d_emails(make_client):
    c = make_client([reply("Voilà.")], email=True)
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Résume mes mails non lus"}, headers=H)
    assert "list_emails" in [t["function"]["name"] for t in c.fake.requests[0].get("tools", [])]


def test_confirmer_un_envoi_reserve_au_proprietaire(make_client, monkeypatch):
    owner = make_client(email=True)
    sent = []
    monkeypatch.setattr(owner.agent.executor.email, "send_email", lambda *a: sent.append(a))
    login(owner)
    aid = owner.db.add_pending_action("send_email", {"to": "a@b.fr", "subject": "s", "body": "b"})
    lea = member_client(owner)
    assert lea.post(f"/api/actions/{aid}/confirm", headers=H).status_code == 403
    assert lea.post(f"/api/actions/{aid}/cancel", headers=H).status_code == 403
    assert sent == []
    assert owner.post(f"/api/actions/{aid}/confirm", headers=H).status_code == 200 and len(sent) == 1


def test_plus_d_emails_dans_les_ecrans_de_syrius_et_connexion_dans_syrius_code():
    html, js = (WEB / "index.html").read_text(encoding="utf-8"), (WEB / "app.js").read_text(encoding="utf-8")
    for gone in ("google-connect", "outlook-connect", "s-email", "tpl-action", "/api/email/", "actionCard"):
        assert gone not in html and gone not in js, gone
    code, cjs = (WEB / "code.html").read_text(encoding="utf-8"), (WEB / "code.js").read_text(encoding="utf-8")
    assert "c-google-connect" in code and "c-outlook-connect" in code and "/api/email/google/start" in cjs
    assert "/api/actions/" in cjs and "/api/code/email" in cjs
