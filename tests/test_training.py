"""Tableau de bord de l'entraînement : exemples du propriétaire, suivi en direct protégé par une clé."""
from fastapi.testclient import TestClient

from tests.conftest import H, login
from tests.test_family import member_client


def test_exemples_du_proprietaire(make_client):
    owner = make_client()
    login(owner)
    r = owner.post("/api/training/examples", json={"question": "C'est qui ma meilleure amie ?",
                                                  "answer": "C'est Julie !"}, headers=H)
    assert r.status_code == 200
    eid = r.json()["id"]
    assert owner.get("/api/training").json()["examples"][0]["q"] == "C'est qui ma meilleure amie ?"
    bad = owner.post("/api/training/examples", json={"question": "Dessine une femme nue", "answer": "ok"}, headers=H)
    assert bad.status_code == 400
    assert owner.delete(f"/api/training/examples/{eid}", headers=H).status_code == 200
    assert owner.get("/api/training").json()["examples"] == []


def test_reserve_au_proprietaire(make_client):
    owner = make_client()
    login(owner)
    lea = member_client(owner)
    for c in (lea, TestClient(owner.app, base_url="https://testserver")):
        assert c.get("/api/training").status_code in (401, 403)
        assert c.get("/api/training/token").status_code in (401, 403)
        assert c.post("/api/training/examples", json={"question": "ab", "answer": "c"}, headers=H).status_code in (401, 403)


def test_suivi_en_direct_avec_cle(make_client):
    owner = make_client()
    login(owner)
    owner.post("/api/training/examples", json={"question": "Ma couleur préférée ?", "answer": "Le bleu."}, headers=H)
    tok = owner.get("/api/training/token").json()["token"]
    worker = TestClient(owner.app, base_url="https://testserver")
    W = {**H, "Authorization": f"Bearer {tok}"}
    # sans clé ou avec une fausse clé : refusé
    assert worker.get("/api/training/worker/examples").status_code == 401
    assert worker.post("/api/training/worker/report", json={"run": "1", "type": "start"},
                       headers={**H, "Authorization": "Bearer faux"}).status_code == 401
    # la clé ne donne pas accès au reste
    assert worker.get("/api/conversations", headers=W).status_code == 401
    assert worker.get("/api/training/worker/examples", headers=W).json() == [{"q": "Ma couleur préférée ?", "a": "Le bleu."}]
    assert worker.get("/api/training/worker/should-train", headers=W).json() == {"train": True}
    for ev in ({"type": "start", "model": "Qwen", "examples": 450, "steps_total": 100},
               {"type": "step", "step": 1, "loss": 2.5}, {"type": "step", "step": 2, "loss": 1.9},
               {"type": "test", "phase": "après", "q": "Qui es-tu ?", "a": "Je suis Syrius."}):
        assert worker.post("/api/training/worker/report", json={"run": "42", **ev}, headers=W).status_code == 200
    run = owner.get("/api/training").json()["runs"][0]
    assert run["status"] == "running" and run["steps_total"] == 100 and [p[1] for p in run["points"]] == [2.5, 1.9]
    assert run["tests"][0]["a"] == "Je suis Syrius."
    worker.post("/api/training/worker/report", json={"run": "42", "type": "done"}, headers=W)
    assert owner.get("/api/training").json()["runs"][0]["status"] == "done"
    # rien de nouveau depuis : pas d'entraînement cette nuit ; un nouvel exemple → entraînement
    assert worker.get("/api/training/worker/should-train", headers=W).json() == {"train": False}
    owner.post("/api/training/examples", json={"question": "Mon plat préféré ?", "answer": "Les lasagnes."}, headers=H)
    assert worker.get("/api/training/worker/should-train", headers=W).json() == {"train": True}
    # événement invalide refusé ; nouvelle clé : l'ancienne ne marche plus
    assert worker.post("/api/training/worker/report", json={"run": "../x", "type": "step"}, headers=W).status_code == 400
    owner.post("/api/training/token", headers=H)
    assert worker.get("/api/training/worker/examples", headers=W).status_code == 401


def test_ameliorer_syrius(make_client):
    owner = make_client()
    login(owner)
    lea = member_client(owner)
    assert lea.post("/api/selfcode", json={"text": "Ajoute un bouton rouge partout"}, headers=H).status_code == 403
    r = owner.post("/api/selfcode", json={"text": "Ajoute un bouton pour copier une réponse"}, headers=H)
    assert r.status_code == 200 and owner.get("/api/selfcode").json()[0]["status"] == "pending"
    assert owner.post("/api/selfcode", json={"text": "Fais une page avec des armes à feu"}, headers=H).status_code == 400
    tok = owner.get("/api/training/token").json()["token"]
    worker = TestClient(owner.app, base_url="https://testserver")
    W = {**H, "Authorization": f"Bearer {tok}"}
    assert worker.post("/api/training/worker/code-next", headers=H).status_code == 401
    item = worker.post("/api/training/worker/code-next", headers=W).json()["request"]
    assert item["text"] == "Ajoute un bouton pour copier une réponse"
    assert worker.post("/api/training/worker/code-next", headers=W).json()["request"] is None  # déjà prise
    bad = {"id": item["id"], "status": "proposed", "pr": "https://evil.example.com/x"}
    assert worker.post("/api/training/worker/code-report", json=bad, headers=W).status_code == 400
    ok = {"id": item["id"], "status": "proposed", "pr": "https://github.com/Snow17044/Syrius/pull/99",
          "summary": "1 fichier modifié", "tests": "505 passed"}
    assert worker.post("/api/training/worker/code-report", json=ok, headers=W).status_code == 200
    it = owner.get("/api/selfcode").json()[0]
    assert it["status"] == "proposed" and it["pr"].endswith("/pull/99")


def test_garde_fous_de_l_ia_programmeuse(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[1] / "selfcode"))
    import agent
    monkeypatch.setattr(agent, "changed", lambda: [("M", "server/auth.py"), ("M", "tests/test_agent.py"),
                                                    ("??", "tests/test_nouveau.py"), ("M", "web/app.js"),
                                                    ("M", ".github/workflows/x.yml")])
    bad = agent.violations()
    assert any("server/auth.py" in b for b in bad) and any("tests/test_agent.py" in b for b in bad)
    assert any(".github" in b for b in bad)
    assert not any("web/app.js" in b or "test_nouveau" in b for b in bad)
