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
    assert "script-src 'self';" in csp and "img-src 'self' data: blob:;" in csp
    script_part = csp.split("script-src")[1].split(";")[0]
    assert "openstreetmap" not in script_part and "unsafe" not in csp


def test_hud_n_insere_jamais_de_html():
    src = open("web/hud.js", encoding="utf-8").read()
    for danger in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval("):
        assert danger not in src
    assert src.count("html:") == 1 and "html: pt.n" in src  # seule donnée HTML : le numéro du repère


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


# ---------------------------------------------------------------- carte 3D
def _fake_3d(calls, planet=None, tile=(200, b"PBF")):
    planet = planet if planet is not None else \
        b'{"tiles":["https://tiles.openfreemap.org/planet/20251105_001001_pt/{z}/{x}/{y}.pbf"]}'
    def _open(scheme, host, ip, port, path, headers=None):
        calls.append((host, path))
        if path == "/planet":
            return 200, {"content-type": "application/json"}, planet
        if path.startswith("/fonts/"):
            return 200, {"content-type": "application/x-protobuf"}, b"GLYPHS"
        return tile[0], {"content-type": "application/x-protobuf"}, tile[1]
    return _open


@pytest.fixture
def fake3d(monkeypatch):
    from server.tools import tiles, web
    calls = []
    monkeypatch.setattr(web, "resolve_public", lambda h, p: "203.0.113.9")
    monkeypatch.setattr(web, "_open", _fake_3d(calls))
    monkeypatch.setitem(tiles._version, "value", "")
    return calls


def test_carte3d_exige_une_connexion(make_client):
    c = make_client()
    assert c.get("/map3d/t/14/8297/5634.pbf").status_code == 401
    assert c.get("/map3d/fonts/Noto Sans Regular/0-255.pbf").status_code == 401


def test_carte3d_relaie_tuile_et_police(make_client, fake3d):
    from tests.conftest import login
    c = make_client()
    login(c)
    r = c.get("/map3d/t/14/8297/5634.pbf")
    assert r.status_code == 200 and r.content == b"PBF"
    assert ("tiles.openfreemap.org", "/planet/20251105_001001_pt/14/8297/5634.pbf") in fake3d
    r = c.get("/map3d/fonts/Noto%20Sans%20Regular/256-511.pbf")
    assert r.status_code == 200 and r.content == b"GLYPHS"
    assert ("tiles.openfreemap.org", "/fonts/Noto%20Sans%20Regular/256-511.pbf") in fake3d
    assert {h for h, _ in fake3d} == {"tiles.openfreemap.org"}


def test_carte3d_refuse_les_demandes_suspectes(make_client, fake3d):
    from tests.conftest import login
    c = make_client()
    login(c)
    for bad in ("/map3d/t/15/0/0.pbf", "/map3d/t/2/9/0.pbf", "/map3d/fonts/Arial/0-255.pbf",
                "/map3d/fonts/Noto%20Sans%20Regular/0-999.pbf", "/map3d/fonts/Noto%20Sans%20Regular/1-256.pbf",
                "/map3d/fonts/..%2F..%2Fetc/0-255.pbf"):
        assert c.get(bad).status_code in (404, 422), bad
    assert fake3d == []


def test_carte3d_version_douteuse_refusee(monkeypatch):
    from server.tools import tiles, web
    monkeypatch.setattr(web, "resolve_public", lambda h, p: "203.0.113.9")
    monkeypatch.setitem(tiles._version, "value", "")
    for planet in (b'{"tiles":["https://evil.example/planet/x/{z}/{x}/{y}.pbf"]}',
                   b'{"tiles":["https://tiles.openfreemap.org/planet/../../x/{z}/{x}/{y}.pbf"]}', b"pas du json"):
        monkeypatch.setattr(web, "_open", _fake_3d([], planet=planet))
        with pytest.raises(tiles.TileError):
            tiles.fetch_vector(1, 0, 0)


def test_carte3d_tuile_vide_et_gzip(monkeypatch):
    import gzip
    from server.tools import tiles, web
    monkeypatch.setattr(web, "resolve_public", lambda h, p: "203.0.113.9")
    monkeypatch.setitem(tiles._version, "value", "")
    monkeypatch.setattr(web, "_open", _fake_3d([], tile=(204, b"")))
    assert tiles.fetch_vector(1, 0, 0) == b""
    def gz(scheme, host, ip, port, path, headers=None):
        if path == "/planet":
            return 200, {}, b'{"tiles":["https://tiles.openfreemap.org/planet/v1/{z}/{x}/{y}.pbf"]}'
        return 200, {"content-encoding": "gzip"}, gzip.compress(b"DATA")
    monkeypatch.setitem(tiles._version, "value", "")
    monkeypatch.setattr(web, "_open", gz)
    assert tiles.fetch_vector(1, 0, 0) == b"DATA"


def test_maplibre_intact():
    expected = {
        "web/maplibre-gl.js": "55557346a86db282433469a8ca1ff0b4889bfc2809547c809c780171bd4553cf",
        "web/maplibre-gl-worker.js": "86f6a52cae3b4dfb7141480ec8ed66a8cd6b763cd16d48a2dd7342d245094f98",
        "web/maplibre-gl.css": "576b085fdd9487a65a19215328c1e086c07ce5bf6da09b666b3806d3d008dae9",
    }
    for path, digest in expected.items():
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == digest, path
