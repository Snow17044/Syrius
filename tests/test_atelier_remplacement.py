"""Dans une même discussion, un nouveau projet remplace l'ancien : l'ancien est annulé, le nouveau démarre tout de suite."""
import json
import sys
from pathlib import Path

from server import atelier, coderask
from tests.conftest import H, login, reply
from tests.test_agent import events_of

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "selfcode"))
import atelier as worker  # noqa: E402


def test_meme_discussion_remplace_autre_discussion_non(make_db):
    base = make_db()
    a = atelier.add(base, "Premier projet de la discussion A", "conv-a")
    b = atelier.add(base, "Projet de la discussion B", "conv-b")
    c = atelier.add(base, "Nouveau projet de la discussion A", "conv-a")  # avant : refusé (2 projets en cours)
    assert c["replaced"] == [a["id"]]
    assert atelier.get(base, a["id"])["status"] == "cancelled"
    assert atelier.get(base, b["id"])["status"] == "pending"  # l'autre discussion n'est pas touchée
    assert "remplacé" in atelier.get(base, a["id"])["summary"]


def test_l_atelier_s_arrete_sur_un_projet_annule(make_db):
    base = make_db()
    a = atelier.add(base, "Un programme Python de test", "conv")
    atelier.take_next(base)
    atelier.add(base, "Un autre programme, finalement", "conv")
    assert atelier.report(base, {"id": a["id"], "status": "done", "summary": "fini"}) is True
    assert atelier.get(base, a["id"])["status"] == "cancelled"  # pas écrasé par le résultat de l'ancien


def test_le_travail_s_arrete_net(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "WORK", tmp_path)
    monkeypatch.setattr(worker, "PROJ", tmp_path / "p")
    asked = []
    monkeypatch.setattr(worker, "api", lambda path, body: asked.append(path) or ({"text": "x"} if path.endswith("coder-ask")
                                                                                 else {"ok": True, "cancelled": True}))
    worker.work({"id": "abcd1234", "text": "Un programme"})
    assert not any(p.endswith("coder-ask") for p in asked)  # annulé dès le 1er avancement : pas de travail inutile


def test_aurora_remplace_le_site_en_cours(make_client, monkeypatch):
    monkeypatch.setattr(coderask, "ask", lambda *a, **k: {"text": "RÉSUMÉ: x\n### FICHIER: index.html\n```\n<p>x</p>\n```"})
    c = make_client([reply("", [("build_web_page", {"request": "Un site pour mon club de foot"})]), reply("Lancé."),
                     reply("", [("build_web_page", {"request": "Finalement un site pour ma boulangerie"})]), reply("Lancé.")])
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    first = next(e for e in events_of(c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Un site foot"},
                                             headers=H).text) if e["type"] == "atelier")["id"]
    c.post(f"/api/code/atelier/{first}/ask", json={}, headers=H)  # le premier est en cours
    second = next(e for e in events_of(c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Non, boulangerie"},
                                              headers=H).text) if e["type"] == "atelier")["id"]
    assert atelier.get(c.db, first)["status"] == "cancelled" and atelier.get(c.db, second)["status"] == "pending"
    assert c.post(f"/api/code/atelier/{first}/ask", json={}, headers=H).status_code == 404  # l'appli arrête l'ancien
    res = [b["content"] for m in c.db.get_messages(cid) for b in m["content"] if b.get("tool_name") == "build_web_page"]
    assert "est annulé" in res[-1]
