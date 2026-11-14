"""Création d'images en ligne : relais sécurisé (un seul hôte, vraies images uniquement)."""
import pytest

from server.tools import imagegen
from server.tools.imagegen import ImageGenError


def test_description_nettoyee_et_encodee():
    path = imagegen.build_path("a cat\x00 on /etc/passwd?x=1&y=2#z", 7)
    assert path.startswith("/prompt/a%20cat%20on%20%2Fetc%2Fpasswd%3Fx%3D1%26y%3D2%23z?")
    assert "seed=7" in path and "nologo=true" in path and "private=true" in path
    assert len(imagegen.clean_prompt("x" * 5000)) == imagegen.MAX_PROMPT
    for bad in ("", "  ", "ab", None, 42):
        with pytest.raises(ImageGenError):
            imagegen.clean_prompt(bad)
    with pytest.raises(ImageGenError):
        imagegen.build_path("a cat", -1)


def test_seules_les_vraies_images_sont_acceptees():
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 2000
    assert imagegen.check_image("image/jpeg; charset=x", jpeg) == "image/jpeg"
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 2000
    assert imagegen.check_image("image/png", png) == "image/png"
    webp = b"RIFF1234WEBP" + b"0" * 2000
    assert imagegen.check_image("image/webp", webp) == "image/webp"
    for ctype, body in (("text/html", b"<html>" + b"0" * 2000), ("image/jpeg", b"<html>" + b"0" * 2000),
                        ("image/svg+xml", b"<svg>" + b"0" * 2000), ("image/jpeg", b"\xff\xd8\xff"),
                        ("image/jpeg", b"\xff\xd8\xff" + b"0" * (imagegen.MAX_BYTES + 1)),
                        ("image/webp", b"RIFF1234AVI " + b"0" * 2000)):
        with pytest.raises(ImageGenError):
            imagegen.check_image(ctype, body)


def test_un_seul_hote_et_ip_publique(monkeypatch):
    seen = {}

    def fake_resolve(host, port):
        seen["host"] = host
        raise imagegen.web.WebError("adresse privée refusée")
    monkeypatch.setattr(imagegen.web, "resolve_public", fake_resolve)
    with pytest.raises(ImageGenError):
        imagegen.generate("a red apple", seed=1)
    assert seen["host"] == "image.pollinations.ai"


def test_route_protegee_et_relayee(make_client, monkeypatch):
    from tests.conftest import login
    client = make_client()
    r = client.post("/api/image", json={"prompt": "a red apple"}, headers={"X-Syrius": "1"})
    assert r.status_code == 401  # connexion obligatoire
    login(client)
    r = client.post("/api/image", json={"prompt": "a red apple"})
    assert r.status_code in (400, 403)  # anti-CSRF : en-tête X-Syrius obligatoire
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 2000
    monkeypatch.setattr(imagegen, "generate", lambda prompt: ("image/jpeg", jpeg))
    r = client.post("/api/image", json={"prompt": "a red apple"}, headers={"X-Syrius": "1"})
    assert r.status_code == 200 and r.content == jpeg and r.headers["content-type"] == "image/jpeg"

    def fail(prompt):
        raise ImageGenError("service d'images saturé")
    monkeypatch.setattr(imagegen, "generate", fail)
    r = client.post("/api/image", json={"prompt": "a red apple"}, headers={"X-Syrius": "1"})
    assert r.status_code == 502 and "saturé" in r.json()["detail"]
    r = client.post("/api/image", json={"prompt": "x" * 700}, headers={"X-Syrius": "1"})
    assert r.status_code == 422


def test_plusieurs_services_essayes_tour_a_tour(monkeypatch):
    calls = []
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 2000

    def fake_fetch(host, method, path, headers, body=None):
        calls.append((host, headers.get("Authorization", "")))
        if host == "router.huggingface.co":
            return 200, "image/jpeg", jpeg
        return (429 if host == "image.pollinations.ai" else 401), "application/json", b"{}"
    monkeypatch.setattr(imagegen, "_fetch", fake_fetch)
    monkeypatch.setitem(imagegen.KEYS, "pollinations", "pk_test")
    monkeypatch.setitem(imagegen.KEYS, "hf", "hf_test")
    assert imagegen.generate("a red apple", seed=3) == ("image/jpeg", jpeg)
    assert [h for h, _ in calls] == ["gen.pollinations.ai", "image.pollinations.ai", "router.huggingface.co"]
    assert calls[0][1] == "Bearer pk_test" and calls[1][1] == "" and calls[2][1] == "Bearer hf_test"
    monkeypatch.setitem(imagegen.KEYS, "hf", "")
    with pytest.raises(ImageGenError) as e:
        imagegen.generate("a red apple", seed=3)
    assert "saturé" in str(e.value)
