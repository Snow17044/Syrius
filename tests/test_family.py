"""Syrius en famille : invitation, espaces privés, retrait d'un compte, quotas équitables, maquettes en cache."""
import pytest
from fastapi.testclient import TestClient

from server import family
from server.app import create_app
from tests.conftest import PASSWORD, login, reply

H = {"X-Syrius": "1"}
MEMBER_PW = "motdepasse-de-lea-42"


def member_client(owner_client, name="Léa", password=MEMBER_PW):
    """Un deuxième téléphone (autres cookies) qui rejoint la famille avec le code d'invitation."""
    code = owner_client.get("/api/family").json()["code"]
    other = TestClient(owner_client.app, base_url="https://testserver")
    r = other.post("/api/family/join", json={"code": code, "name": name, "password": password}, headers=H)
    assert r.status_code == 200, r.text
    return other


def test_invitation_et_espaces_prives(make_client):
    owner = make_client(responses=[reply("Bonjour Léa !"), reply("Salut !")])
    login(owner)
    lea = member_client(owner)
    # Léa a son propre espace : ses discussions n'apparaissent pas chez le propriétaire, et inversement.
    cid = lea.post("/api/conversations", headers=H).json()["id"]
    lea.post(f"/api/conversations/{cid}/messages", json={"text": "Coucou"}, headers=H)
    assert [c["id"] for c in lea.get("/api/conversations").json()] == [cid]
    assert lea.get(f"/api/conversations/{cid}").json()["messages"]
    assert owner.get("/api/conversations").json() == []
    assert owner.get(f"/api/conversations/{cid}").status_code == 404
    own = owner.post("/api/conversations", headers=H).json()["id"]
    assert lea.get(f"/api/conversations/{own}").status_code == 404
    # Réglages et mémoire séparés
    lea.put("/api/settings", json={"user_name": "Léa"}, headers=H)
    assert owner.get("/api/settings").json().get("user_name", "") != "Léa"
    s = lea.get("/api/settings").json()
    assert s["user_name"] == "Léa" and s["account"] == {"owner": False, "name": "Léa", "guest": False}
    assert owner.get("/api/settings").json()["account"]["owner"] is True


def test_connexion_membre_et_erreurs(make_client):
    owner = make_client()
    login(owner)
    member_client(owner)
    other = TestClient(owner.app, base_url="https://testserver")
    assert other.post("/api/login", json={"name": "léa", "password": MEMBER_PW}, headers=H).status_code == 200
    assert other.get("/api/session").json()["member_name"] == "Léa"
    bad = TestClient(owner.app, base_url="https://testserver")
    assert bad.post("/api/login", json={"name": "Léa", "password": "mauvais-mot-de-passe"}, headers=H).status_code == 401
    assert bad.post("/api/login", json={"name": "Inconnu", "password": MEMBER_PW}, headers=H).status_code == 401
    # Le mot de passe du propriétaire ne donne pas accès au compte de Léa, et inversement.
    assert bad.post("/api/login", json={"name": "Léa", "password": PASSWORD}, headers=H).status_code == 401
    assert bad.post("/api/login", json={"password": MEMBER_PW}, headers=H).status_code == 401


def test_code_invitation_obligatoire_et_famille_limitee(make_client):
    owner = make_client()
    login(owner)
    code = owner.get("/api/family").json()["code"]
    anon = TestClient(owner.app, base_url="https://testserver")
    r = anon.post("/api/family/join", json={"code": "AAAA-BBBB-CCCC", "name": "Pirate", "password": "x" * 12}, headers=H)
    assert r.status_code == 400
    for i in range(family.MAX_MEMBERS):
        c = TestClient(owner.app, base_url="https://testserver")
        assert c.post("/api/family/join", json={"code": code.lower(), "name": f"Membre {i}", "password": "x" * 12},
                      headers=H).status_code == 200
    c = TestClient(owner.app, base_url="https://testserver")
    r = c.post("/api/family/join", json={"code": code, "name": "En trop", "password": "x" * 12}, headers=H)
    assert r.status_code == 400 and "complète" in r.json()["detail"]
    r = c.post("/api/family/join", json={"code": code, "name": "Membre 1", "password": "x" * 12}, headers=H)
    assert r.status_code == 400


def test_outils_famille_reserves_au_proprietaire(make_client):
    owner = make_client()
    login(owner)
    lea = member_client(owner)
    assert lea.get("/api/family").status_code == 403
    assert lea.post("/api/family/code", headers=H).status_code == 403
    old = owner.get("/api/family").json()["code"]
    new = owner.post("/api/family/code", headers=H).json()["code"]
    assert new != old
    anon = TestClient(owner.app, base_url="https://testserver")
    assert anon.post("/api/family/join", json={"code": old, "name": "Zoé", "password": "x" * 12}, headers=H).status_code == 400
    # Retrait d'un compte : sa session ne fonctionne plus.
    uid = owner.get("/api/family").json()["members"][0]["id"]
    assert lea.get("/api/conversations").status_code == 200
    assert owner.delete(f"/api/family/{uid}", headers=H).status_code == 200
    assert lea.get("/api/conversations").status_code == 401


def test_jeton_falsifie_refuse(make_client):
    owner = make_client()
    login(owner)
    lea = member_client(owner)
    token = lea.cookies.get("syrius_session")
    uid = token.split(".")[0]
    forged = TestClient(owner.app, base_url="https://testserver")
    forged.cookies.set("syrius_session", uid + ".fauxjeton")  # identifiant correct, jeton inventé
    assert forged.get("/api/conversations").status_code == 401
    owner_token = owner.cookies.get("syrius_session")
    forged.cookies.set("syrius_session", uid + "." + owner_token)  # jeton du propriétaire « relabellisé »
    assert forged.get("/api/conversations").status_code == 401


def test_mot_de_passe_membre(make_client):
    owner = make_client()
    login(owner)
    lea = member_client(owner)
    r = lea.post("/api/password", json={"current": MEMBER_PW, "new": "nouveau-mdp-lea-123"}, headers=H)
    assert r.status_code == 200
    other = TestClient(owner.app, base_url="https://testserver")
    assert other.post("/api/login", json={"name": "Léa", "password": "nouveau-mdp-lea-123"}, headers=H).status_code == 200
    # Le mot de passe du propriétaire n'a pas changé
    third = TestClient(owner.app, base_url="https://testserver")
    assert third.post("/api/login", json={"password": PASSWORD}, headers=H).status_code == 200


def test_quotas_equitables(make_client):
    owner = make_client()
    base = owner.db
    assert family.quota_left(base, "m3d", "") == family.LIMITS["m3d"]["owner"]
    family.quota_use(base, "m3d", "abcdefabcdef")
    assert family.quota_left(base, "m3d", "abcdefabcdef") == family.LIMITS["m3d"]["member"] - 1
    assert family.quota_left(base, "m3d", "") == family.LIMITS["m3d"]["owner"]  # parts indépendantes


def test_ia_puissante_par_personne(make_client):
    owner = make_client(responses=[reply("ok")])
    owner.agent.llm.providers[0].name = "openrouter"  # la plus puissante en premier
    login(owner)
    base = owner.db
    for _ in range(family.LIMITS["power"]["owner"]):
        family.quota_use(base, "power", "")
    cid = owner.post("/api/conversations", headers=H).json()["id"]
    owner.post(f"/api/conversations/{cid}/messages", json={"text": "Salut"}, headers=H)
    assert owner.fake.requests[-1]["_provider"] != "openrouter"  # part du jour utilisée : relais


def test_maquette_en_cache(make_client, monkeypatch):
    from server.tools import real3d
    owner = make_client()
    login(owner)
    owner.agent.cfg.hf_token = "hf_x"
    glb = b"glTF" + b"\x02\x00\x00\x00" + bytes(range(256)) * 5000  # ~1,3 Mo : plusieurs morceaux
    calls = []
    monkeypatch.setattr(real3d, "trellis_generate", lambda token, prompt: calls.append(prompt) or glb)
    r1 = owner.post("/api/model3d/generate", json={"prompt": "a red car", "key": "red car"}, headers=H)
    assert r1.status_code == 200 and r1.content == glb
    r2 = owner.post("/api/model3d/generate", json={"prompt": "a shiny red car", "key": "Red  car!"}, headers=H)
    assert r2.status_code == 200 and r2.content == glb and r2.headers.get("X-Syrius-Cache") == "1"
    assert calls == ["a red car"]  # créée une seule fois
    assert family.quota_left(owner.db, "m3d", "") == family.LIMITS["m3d"]["owner"] - 1


def test_portee_des_donnees(make_client):
    owner = make_client()
    db = family.ScopedDB(owner.db, family.space_factory(owner.db, owner.agent.cfg.data_dir))
    with pytest.raises(family.FamilyError):
        db.for_user("../../etc")
    assert db.for_user("") is owner.db
    # les clés communes (mot de passe, comptes, quotas, cache) restent dans l'espace commun
    family.CURRENT.set("abcdefabcdef")
    try:
        db.set_secret("quota:test", "1")
        db.set_secret("perso", "x")
        assert owner.db.get_secret("quota:test") == "1" and owner.db.get_secret("perso") is None
        assert db.for_user("abcdefabcdef").get_secret("perso") == "x"
    finally:
        family.CURRENT.set("")


def test_boite_mail_du_proprietaire_reservee(make_client):
    owner = make_client()
    cfg = owner.agent.cfg
    cfg.imap_host, cfg.email_user, cfg.email_password = "imap.example.com", "moi@example.com", "x"
    cfg.email_auth = "password"
    login(owner)
    assert owner.get("/api/settings").json()["email_enabled"] is True
    lea = member_client(owner)
    assert lea.get("/api/settings").json()["email_enabled"] is False
    from server.tools.registry import build_tools
    family.CURRENT.set("abcdefabcdef")
    try:
        assert not any(t.get("name") == "list_emails" or t.get("function", {}).get("name") == "list_emails"
                       for t in build_tools(cfg, {}))
    finally:
        family.CURRENT.set("")
    assert lea.post("/api/email/outlook/start", headers=H).status_code == 403


def test_lien_de_test_24h(make_client, monkeypatch):
    owner = make_client(responses=[reply("Bienvenue")])
    login(owner)
    link = owner.post("/api/family/test-link", headers=H).json()["link"]
    tester = TestClient(owner.app, base_url="https://testserver")
    assert tester.post("/api/family/test", json={"link": link}, headers=H).status_code == 200
    acc = tester.get("/api/settings").json()["account"]
    assert acc["guest"] is True and acc["name"] == "Testeur 1" and acc["expires"] > 0
    cid = tester.post("/api/conversations", headers=H).json()["id"]
    assert tester.get(f"/api/conversations/{cid}").status_code == 200
    assert owner.get("/api/conversations").json() == []  # espace séparé
    assert tester.get("/api/family").status_code == 403
    assert tester.post("/api/email/google/start", headers=H).status_code == 403
    # mauvais lien refusé
    other = TestClient(owner.app, base_url="https://testserver")
    uid = link.split("-")[0]
    assert other.post("/api/family/test", json={"link": uid + "-" + "x" * 32}, headers=H).status_code == 400
    # 24 h plus tard : plus d'accès, compte et données effacés
    real = family.time.time
    monkeypatch.setattr(family.time, "time", lambda: real() + family.TEST_SECONDS + 5)
    assert tester.get("/api/conversations").status_code == 401
    assert other.post("/api/family/test", json={"link": link}, headers=H).status_code == 400
    assert owner.get("/api/family").json()["members"] == []
    assert family.ScopedDB(owner.db, family.space_factory(owner.db, owner.agent.cfg.data_dir)) \
        .for_user(uid).list_conversations() == []


def test_dix_comptes_en_tout_plus_de_lien(make_client):
    owner = make_client()
    login(owner)
    code = owner.get("/api/family").json()["code"]
    for _ in range(3):
        assert owner.post("/api/family/test-link", headers=H).status_code == 200
    for i in range(family.MAX_MEMBERS - 3):
        c = TestClient(owner.app, base_url="https://testserver")
        assert c.post("/api/family/join", json={"code": code, "name": f"Membre {i}", "password": "x" * 12},
                      headers=H).status_code == 200
    f = owner.get("/api/family").json()
    assert f["full"] is True and f["code"] is None and len(f["members"]) == family.MAX_MEMBERS
    assert owner.post("/api/family/code", headers=H).status_code == 409
    assert owner.post("/api/family/test-link", headers=H).status_code == 409
    c = TestClient(owner.app, base_url="https://testserver")
    assert c.post("/api/family/join", json={"code": code, "name": "En trop", "password": "x" * 12},
                  headers=H).status_code == 400
    # un compte retiré libère une place : un nouveau code est créé
    owner.delete(f"/api/family/{f['members'][0]['id']}", headers=H)
    f = owner.get("/api/family").json()
    assert f["full"] is False and f["code"] and f["code"] != code


def test_retrait_efface_les_donnees(make_client):
    owner = make_client(responses=[reply("ok")])
    login(owner)
    lea = member_client(owner)
    cid = lea.post("/api/conversations", headers=H).json()["id"]
    uid = owner.get("/api/family").json()["members"][0]["id"]
    owner.delete(f"/api/family/{uid}", headers=H)
    db = family.ScopedDB(owner.db, family.space_factory(owner.db, owner.agent.cfg.data_dir))
    assert db.for_user(uid).get_conversation(cid) is None


def test_seul_le_proprietaire_cree_des_liens(make_client):
    owner = make_client()
    login(owner)
    lea = member_client(owner)
    link = owner.post("/api/family/test-link", headers=H).json()["link"]
    tester = TestClient(owner.app, base_url="https://testserver")
    tester.post("/api/family/test", json={"link": link}, headers=H)
    anon = TestClient(owner.app, base_url="https://testserver")
    for c in (lea, tester, anon):
        assert c.post("/api/family/test-link", headers=H).status_code in (401, 403)
        assert c.post("/api/family/code", headers=H).status_code in (401, 403)
        assert c.get("/api/family").status_code in (401, 403)
        assert "code" not in c.get("/api/settings").json()
