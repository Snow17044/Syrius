"""Vraies maquettes 3D : bibliothèque Poly Pizza et création TRELLIS.2 (hôtes fixes, GLB vérifiés)."""
import json

import pytest

from server.tools import real3d
from server.tools.real3d import Real3DError

GLB = b"glTF" + b"\x02\x00\x00\x00" + b"0" * 200


def test_glb_verifie():
    assert real3d.check_glb(GLB) == GLB
    for bad in (b"<html>" + b"0" * 200, b"glTF", b"glTF" + b"0" * real3d.MAX_GLB):
        with pytest.raises(Real3DError):
            real3d.check_glb(bad)


def test_recherche_bibliotheque(monkeypatch):
    seen = {}

    def fake(host, method, path, headers, body=None, timeout=30, limit=0):
        seen.update(host=host, path=path, headers=headers)
        return 200, {}, json.dumps({"results": [
            {"ID": "abc123", "Title": "Eiffel Tower", "Download": "https://static.poly.pizza/abc123.glb",
             "Creator": {"Username": "Artiste"}, "Licence": "CC0", "Tri Count": 5000},
            {"ID": "evil1", "Title": "Piège", "Download": "https://evil.example/x.glb"},          # hôte refusé
            {"ID": "../x", "Title": "Piège", "Download": "https://static.poly.pizza/x.glb"},    # identifiant refusé
            {"ID": "big123", "Title": "Lourd", "Download": "https://static.poly.pizza/big123.glb", "Tri Count": 900000},
        ]}).encode()
    monkeypatch.setattr(real3d, "_request", fake)
    res = real3d.poly_search("cle", "eiffel tower")
    assert res == [{"id": "abc123", "title": "Eiffel Tower", "creator": "Artiste", "licence": "CC0", "path": "/abc123.glb"}]
    assert seen["host"] == "api.poly.pizza" and seen["headers"]["x-auth-token"] == "cle"
    assert seen["path"].startswith("/v1.1/search/eiffel%20tower")
    with pytest.raises(Real3DError, match="POLYPIZZA"):
        real3d.poly_search("", "car")


def test_telechargement_bibliotheque(monkeypatch):
    monkeypatch.setattr(real3d, "_request", lambda host, *a, **k: (200, {}, GLB) if host == "static.poly.pizza" else 1 / 0)
    assert real3d.poly_glb("/abc123.glb") == GLB
    for bad in ("/../etc/passwd.glb", "https://evil/x.glb", "/x.exe", "//evil.com/a.glb/../b"):
        with pytest.raises(Real3DError):
            real3d.poly_glb(bad)


def _fake_space(calls, quota=False):
    deps = [{"id": i, "api_name": n} for i, n in enumerate(
        ["load_example_input", "load_example", "start_session", "end_session", "preprocess_image", "get_seed",
         "lambda", "image_to_3d", "lambda_1", "extract_glb"])]
    names = {d["id"]: d["api_name"] for d in deps}
    state = {}

    def fake(host, method, path, headers, body=None, timeout=30, limit=0):
        assert host == real3d.TRELLIS and headers.get("Authorization") == "Bearer hf_x"
        if path == "/config":
            return 200, {}, json.dumps({"dependencies": deps}).encode()
        if path == "/gradio_api/upload":
            return 200, {}, b'["/tmp/gradio/abc/objet.jpg"]'
        if path == "/gradio_api/queue/join":
            req = json.loads(body)
            state["api"] = names[req["fn_index"]]
            calls.append(state["api"])
            return 200, {}, b'{"event_id": "ev123456"}'
        if path.startswith("/gradio_api/queue/data"):
            if quota and state["api"] == "image_to_3d":
                msg = {"msg": "process_completed", "event_id": "ev123456", "success": False,
                       "output": {"error": "You have exceeded your ZeroGPU quota"}}
            else:
                data = {"preprocess_image": [{"path": "/tmp/gradio/abc/image.png"}],
                        "extract_glb": [{"path": "/tmp/gradio/abc/m.glb"}, {"path": "/tmp/gradio/abc/m.glb"}]}
                msg = {"msg": "process_completed", "event_id": "ev123456", "success": True,
                       "output": {"data": data.get(state["api"], [None])}}
            return 200, {}, ('data: {"msg": "estimation", "event_id": "ev123456"}\n\n'
                             "data: " + json.dumps(msg) + "\n\n").encode()
        if path.startswith("/gradio_api/file="):
            return 200, {}, GLB
        raise AssertionError(path)
    return fake


def test_creation_sur_mesure(monkeypatch):
    calls = []
    real3d._FN.clear()
    monkeypatch.setattr(real3d.imagegen, "generate", lambda p: ("image/jpeg", b"\xff\xd8\xff" + b"0" * 2000))
    monkeypatch.setattr(real3d, "_request", _fake_space(calls))
    assert real3d.trellis_generate("hf_x", "a red car") == GLB
    assert calls == ["start_session", "preprocess_image", "image_to_3d", "extract_glb"]


def test_quota_et_reponses_piegees(monkeypatch):
    real3d._FN.clear()
    monkeypatch.setattr(real3d.imagegen, "generate", lambda p: ("image/jpeg", b"\xff\xd8\xff" + b"0" * 2000))
    monkeypatch.setattr(real3d, "_request", _fake_space([], quota=True))
    with pytest.raises(Real3DError, match="quota"):
        real3d.trellis_generate("hf_x", "a red car")
    with pytest.raises(Real3DError):
        real3d._file_path([{"path": "/etc/passwd"}])  # seulement des fichiers temporaires du service


def test_routes_protegees(make_client, monkeypatch):
    from tests.conftest import login
    client = make_client()
    h = {"X-Syrius": "1"}
    assert client.post("/api/model3d/search", json={"query": "car"}, headers=h).status_code == 401
    login(client)
    monkeypatch.setattr(real3d, "poly_search", lambda key, q: [{"id": "a1b2", "path": "/a1b2.glb"}])
    assert client.post("/api/model3d/search", json={"query": "car"}, headers=h).json()["results"][0]["id"] == "a1b2"
    monkeypatch.setattr(real3d, "poly_glb", lambda p: GLB)
    r = client.get("/api/model3d/poly", params={"path": "/a1b2.glb"})
    assert r.status_code == 200 and r.content == GLB and r.headers["content-type"] == "model/gltf-binary"
    r = client.post("/api/model3d/generate", json={"prompt": "a red car"}, headers=h)
    assert r.status_code == 503  # pas de clé HF_TOKEN dans les tests
    assert client.post("/api/model3d/search", json={"query": "car"}).status_code in (400, 403)  # anti-CSRF
