"""Mot de passe oublié : désactivé par défaut, protégé par un code de secours, déconnecte tout le monde."""
from fastapi.testclient import TestClient

from tests.conftest import H, PASSWORD, login

CODE = "quatre mots au hasard"


def anon(c):
    return TestClient(c.app, base_url="https://testserver")


def test_desactive_par_defaut(make_client):
    c = make_client()
    assert c.get("/api/reset/state").json() == {"available": False}
    r = anon(c).post("/api/reset", headers=H, json={"code": CODE, "password": "nouveau-mot-de-passe"})
    assert r.status_code == 403
    login(c)  # l'ancien mot de passe marche toujours


def test_code_trop_court_ne_compte_pas(make_client, cfg):
    cfg.reset_code = "court"
    c = make_client()
    assert c.get("/api/reset/state").json() == {"available": False}
    assert anon(c).post("/api/reset", headers=H, json={"code": "court", "password": "nouveau-mot-de-passe"}).status_code == 403


def test_reinitialisation_complete(make_client, cfg):
    cfg.reset_code = CODE
    c = make_client()
    login(c)
    assert c.get("/api/conversations").status_code == 200  # connecté avec l'ancien mot de passe
    a = anon(c)
    assert a.get("/api/reset/state").json() == {"available": True}
    bad = a.post("/api/reset", headers=H, json={"code": "mauvais code de secours", "password": "nouveau-mot-de-passe"})
    assert bad.status_code == 401
    short = a.post("/api/reset", headers=H, json={"code": CODE, "password": "court"})
    assert short.status_code == 422  # mot de passe trop court
    ok = a.post("/api/reset", headers=H, json={"code": CODE, "password": "nouveau-mot-de-passe"})
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    assert c.get("/api/conversations").status_code == 401  # tous les appareils sont déconnectés
    old = a.post("/api/login", headers=H, json={"password": PASSWORD})
    assert old.status_code == 401  # l'ancien mot de passe ne marche plus
    new = a.post("/api/login", headers=H, json={"password": "nouveau-mot-de-passe"})
    assert new.status_code == 200
    assert a.get("/api/conversations").status_code == 200


def test_blocage_apres_plusieurs_essais(make_client, cfg):
    cfg.reset_code = CODE
    c = make_client()
    a = anon(c)
    codes = [a.post("/api/reset", headers=H, json={"code": f"mauvais code numéro {i}", "password": "nouveau-mot-de-passe"}).status_code
             for i in range(7)]
    assert codes[:5] == [401] * 5 and codes[5] == 429  # bloqué comme à la connexion
    assert a.post("/api/reset", headers=H, json={"code": CODE, "password": "nouveau-mot-de-passe"}).status_code == 429


def test_protege_contre_les_requetes_d_autres_sites(make_client, cfg):
    cfg.reset_code = CODE
    c = make_client()
    r = anon(c).post("/api/reset", json={"code": CODE, "password": "nouveau-mot-de-passe"})  # sans l'en-tête X-Syrius
    assert r.status_code == 403
    login(c)


def test_pages_et_liens(make_client):
    c = make_client()
    page = c.get("/reinitialiser")
    assert page.status_code == 200 and b"Mot de passe oubli" in page.content and "no-store" in page.headers["cache-control"]
    assert c.get("/static/reset.js").status_code == 200
    for path in ("/", "/code"):
        assert b"/reinitialiser" in c.get(path).content  # lien « Mot de passe oublié ? » sur les deux écrans de connexion
