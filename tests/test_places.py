"""Tests de la carte holographique (recherche de lieux + position)."""
import hashlib
import json

import pytest

from server.tools import places, web
from tests.conftest import H, login, reply


def events_of(text):
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


NOMINATIM_ANSWER = json.dumps([
    {"lat": "48.8570", "lon": "2.3530", "name": "Chez Luigi", "type": "restaurant",
     "display_name": "Chez Luigi, 3, Rue de Rivoli, Paris, France"},
    {"lat": "48.8566", "lon": "2.3522", "name": "Le Petit Bistro", "type": "restaurant",
     "display_name": "Le Petit Bistro, 1, Rue du Temple, Paris, France"},
    {"lat": "pas-un-nombre", "lon": "2", "name": "Cassé"},
]).encode()


@pytest.fixture
def fake_nominatim(monkeypatch):
    seen = []

    def fake_fetch(url, allowed_types=web.ALLOWED_TYPES):
        seen.append((url, allowed_types))
        return url, "application/json", NOMINATIM_ANSWER.decode()
    monkeypatch.setattr(web, "fetch", fake_fetch)
    return seen


def test_position_arrondie_et_validee():
    assert places.round_location({"lat": 48.856614, "lon": 2.3522219}) == {"lat": 48.857, "lon": 2.352}
    for bad in (None, "48,2", {"lat": 91, "lon": 0}, {"lat": True, "lon": 2}, {"lat": "48", "lon": "2"},
                {"lat": 0, "lon": 0}, {"lat": 48}):
        assert places.round_location(bad) is None


def test_recherche_triee_par_distance(fake_nominatim):
    me = {"lat": 48.8566, "lon": 2.3522}
    found = places.search("restaurant", me)
    assert [p["name"] for p in found] == ["Le Petit Bistro", "Chez Luigi"]  # le plus proche d'abord
    assert found[0]["distance_m"] < found[1]["distance_m"]
    url, types = fake_nominatim[0]
    assert url.startswith("https://nominatim.openstreetmap.org/search?") and "bounded=1" in url
    assert types == ("application/json",)


def test_passe_par_le_pare_feu():
    # La recherche utilise web.fetch, donc le pare-feu : une adresse interne serait refusée.
    import inspect
    assert "web.fetch(" in inspect.getsource(places.search)


def test_carte_affichee_dans_l_app_sans_enregistrer_la_position(make_client, fake_nominatim):
    c = make_client([reply("", [("show_places", {"query": "restaurant", "near_me": True})]),
                     reply("Le plus proche est Le Petit Bistro.")])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    body = {"text": "Où est le restaurant le plus proche ?", "location": {"lat": 48.856614, "lon": 2.3522219}}
    ev = events_of(c.post(f"/api/conversations/{cid}/messages", json=body, headers=H).text)
    m = [e for e in ev if e["type"] == "map"][0]
    assert m["me"] == {"lat": 48.857, "lon": 2.352} and len(m["places"]) == 2
    # La position n'est jamais enregistrée dans l'historique.
    stored = json.dumps(c.db.get_messages(cid))
    assert "48.85" not in stored.replace("48.8570", "").replace("48.8566", "")
    assert "2.3522219" not in stored and "48.856614" not in stored


def test_position_ignoree_si_partage_desactive(make_client, fake_nominatim):
    c = make_client([reply("", [("show_places", {"query": "pharmacie", "near_me": True})]), reply("ok")])
    login(c)
    c.put("/api/settings", json={"location": False}, headers=H)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/conversations/{cid}/messages",
                          json={"text": "pharmacie ?", "location": {"lat": 48.8, "lon": 2.3}}, headers=H).text)
    m = [e for e in ev if e["type"] == "map"][0]
    assert m["me"] is None and "bounded" not in fake_nominatim[0][0]


def test_resultats_carte_non_fiables():
    from server.agent import UNTRUSTED_TOOLS
    assert "show_places" in UNTRUSTED_TOOLS


def test_leaflet_intact():
    expected = {"web/leaflet.js": "db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a",
                "web/leaflet.css": "a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6"}
    for path, digest in expected.items():
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == digest, path


def test_csp_n_autorise_que_les_images_de_carte(make_client):
    csp = make_client().get("/").headers["content-security-policy"]
    assert "script-src 'self';" in csp and "img-src 'self' data:;" in csp
    script_part = csp.split("script-src")[1].split(";")[0]
    assert "openstreetmap" not in script_part and "unsafe" not in csp


def test_hud_n_insere_jamais_de_html():
    src = open("web/hud.js", encoding="utf-8").read()
    for danger in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval("):
        assert danger not in src
    assert "html: n" in src  # seule donnée HTML : le numéro du repère


def test_android_position_seulement_pour_syrius():
    java = open("android/app/src/main/java/fr/syrius/app/MainActivity.java", encoding="utf-8").read()
    i = java.index("onGeolocationPermissionsShowPrompt")
    assert "allowedHost.equals(o.getHost())" in java[i:i + 600]
    manifest = open("android/app/src/main/AndroidManifest.xml", encoding="utf-8").read()
    assert "ACCESS_COARSE_LOCATION" in manifest and "ACCESS_FINE_LOCATION" not in manifest
    assert "ACCESS_BACKGROUND_LOCATION" not in manifest


# ---------------------------------------------------------------- relais du fond de carte
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50


def _fake_open(calls, status=200, ctype="image/png", body=PNG):
    def _open(scheme, host, ip, port, path, headers=None):
        calls.append((scheme, host, ip, port, path, headers))
        return status, {"content-type": ctype}, body
    return _open


def test_tuile_exige_une_connexion(make_client):
    assert make_client().get("/tiles/3/4/2.png").status_code == 401


def test_tuile_relayee(make_client, monkeypatch):
    from server.tools import tiles, web
    from tests.conftest import login
    calls = []
    monkeypatch.setattr(web, "resolve_public", lambda h, p: "203.0.113.5")
    monkeypatch.setattr(web, "_open", _fake_open(calls))
    c = make_client()
    login(c)
    r = c.get("/tiles/3/4/2.png")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    assert calls[0][:5] == ("https", tiles.HOST, "203.0.113.5", 443, "/3/4/2.png")
    assert "User-Agent" in calls[0][5] and "Cookie" not in calls[0][5]


def test_tuile_coordonnees_invalides(make_client, monkeypatch):
    from server.tools import web
    from tests.conftest import login
    calls = []
    monkeypatch.setattr(web, "resolve_public", lambda h, p: "203.0.113.5")
    monkeypatch.setattr(web, "_open", _fake_open(calls))
    c = make_client()
    login(c)
    for bad in ("/tiles/20/0/0.png", "/tiles/2/4/0.png", "/tiles/2/0/-1.png", "/tiles/a/0/0.png",
                "/tiles/2/0/0.png/../../x", "/tiles/2/0/0%2F..%2F.png"):
        assert c.get(bad).status_code in (404, 422), bad
    assert calls == []


def test_tuile_refuse_autre_chose_qu_une_image(make_client, monkeypatch):
    from server.tools import tiles, web
    from tests.conftest import login
    monkeypatch.setattr(web, "resolve_public", lambda h, p: "203.0.113.5")
    for kw in ({"ctype": "text/html"}, {"status": 403}, {"body": b"x" * (tiles.MAX_TILE_BYTES + 1)}):
        monkeypatch.setattr(web, "_open", _fake_open([], **kw))
        c = make_client()
        login(c)
        assert c.get("/tiles/1/0/0.png").status_code == 404


def test_tuile_hote_interne_refuse(monkeypatch):
    from server.tools import tiles, web
    def deny(h, p):
        raise web.WebError("Adresse interne refusée par le pare-feu.")
    monkeypatch.setattr(web, "resolve_public", deny)
    with pytest.raises(tiles.TileError):
        tiles.fetch_tile(1, 0, 0)
