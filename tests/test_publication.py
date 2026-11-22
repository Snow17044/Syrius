"""Bouton « Publier sur Internet » : un site terminé d'Aurora, mis en ligne sur Vercel, seulement sur demande."""
from server import atelier, publish
from tests.conftest import H, login

FILES = {"index.html": "<!doctype html><title>x</title><p>Salut</p>", "style.css": "p{}", "tests.js": "window.__tests=[]",
         "tests/site.test.js": "//", "package.json": "{}", ".env": "SECRET=1"}


def _done(base, files=FILES):
    item = atelier.add_instant(base, "Un site pour mon club de foot, joli sur téléphone")
    atelier.instant_update(base, item["id"], files=files, status="done")
    return atelier.get(base, item["id"])


def test_seuls_les_fichiers_du_site_partent(make_db):
    item = _done(make_db())
    assert sorted(publish.site_files(item)) == ["index.html", "style.css"]  # ni tests, ni package.json, ni fichier caché
    assert publish.project_name(item).startswith("aurora-un-site-pour-mon-")


def test_publication(make_client, monkeypatch):
    calls = []

    def fake(token, method, path, team, body=None):
        calls.append((method, path, team, body))
        if path.startswith("/v13/deployments"):
            return 200, {"id": "dpl_1", "projectId": "prj_1"}
        if path.endswith("/domains"):
            return 200, {"domains": [{"name": "aurora-club-1234.vercel.app"}]}
        return 200, {}
    monkeypatch.setattr(publish, "_call", fake)
    c = make_client()
    c.app.state.cfg.vercel_token, c.app.state.cfg.vercel_team_id = "vk", "team_1"
    login(c)
    item = _done(c.db)
    assert c.get(f"/api/code/atelier/{item['id']}").json()["can_publish"] is True
    r = c.post(f"/api/code/atelier/{item['id']}/publish", headers=H).json()
    assert r["url"] == "https://aurora-club-1234.vercel.app"
    assert c.get(f"/api/code/atelier/{item['id']}").json()["published"] == r["url"]
    deploy = calls[0][3]
    assert {f["file"] for f in deploy["files"]} == {"index.html", "style.css"} and calls[0][2] == "team_1"
    assert any(m == "PATCH" and b == {"ssoProtection": None} for m, _, _, b in calls)  # visible sans compte Vercel


def test_refus(make_client):
    c = make_client()
    login(c)
    unfinished = atelier.add_instant(c.db, "Un site pas encore terminé, en cours")
    assert c.post(f"/api/code/atelier/{unfinished['id']}/publish", headers=H).status_code == 400  # pas de clé Vercel
    c.app.state.cfg.vercel_token = "vk"
    assert "terminé" in c.post(f"/api/code/atelier/{unfinished['id']}/publish", headers=H).json()["detail"]
    bad = _done(c.db, {"index.html": "<p>porno</p>"})
    assert "refusée" in c.post(f"/api/code/atelier/{bad['id']}/publish", headers=H).json()["detail"]


def test_reserve_au_proprietaire(make_client):
    from tests.test_family import member_client
    c = make_client()
    login(c)
    item = _done(c.db)
    assert member_client(c).post(f"/api/code/atelier/{item['id']}/publish", headers=H).status_code == 403


def test_aurora_ne_peut_pas_publier_toute_seule():
    from server.config import Config
    from server.tools.registry import build_tools
    names = {t["function"]["name"] for t in build_tools(Config(), {}, "aurore")}
    assert not any("publi" in n or "deploy" in n for n in names)
