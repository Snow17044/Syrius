"""Atelier instantané : sites web écrits par Aurora, testés tout de suite dans l'appli (boîte fermée), sans serveur."""
from server import atelier, coderask, hfspace
from tests.conftest import H, login, reply
from tests.test_agent import events_of

SITE = """RÉSUMÉ: Un compteur.
### FICHIER: index.html
```html
<!doctype html><html><head><title>x</title></head><body><button id="plus">+</button><script src="script.js"></script></body></html>
```
### FICHIER: script.js
```js
document.getElementById("plus").onclick = () => {};
```
### FICHIER: tests.js
```js
window.__tests = [{ nom: "ok", test: async (t) => t.assert(true) }];
```
"""


def _launch(c):
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Fais-moi un site"}, headers=H).text)
    return next(e for e in ev if e["type"] == "atelier")["id"]


def test_aurora_lance_un_site_instantane(make_client, monkeypatch):
    c = make_client([reply("", [("build_web_page", {"request": "Un compteur de cafés joli sur téléphone"})]), reply("C'est parti.")])
    login(c)
    pid = _launch(c)
    item = atelier.get(c.db, pid)
    assert item["mode"] == "instant" and item["status"] == "pending"
    assert atelier.take_next(c.db) is None  # jamais envoyé à GitHub : il se fait dans l'appli


def test_boucle_ecrire_tester_corriger(make_client, monkeypatch):
    prompts = []
    monkeypatch.setattr(coderask, "ask", lambda base, prov, system, prompt, max_tokens=0: prompts.append((system, prompt)) or {"text": SITE})
    c = make_client([reply("", [("build_web_page", {"request": "Un compteur de cafés joli sur téléphone"})]), reply("C'est parti.")])
    login(c)
    pid = _launch(c)
    p = c.post(f"/api/code/atelier/{pid}/ask", json={}, headers=H).json()
    assert p["attempt"] == 1 and p["status"] == "running" and p["site_url"].endswith("/site/")
    assert "tests.js est OBLIGATOIRE" in prompts[0][0]
    # mode test : banc d'essai au début, tests d'Aurora à la fin, scripts en « crossorigin » (vrais messages d'erreur)
    page = c.get(p["site_url"] + "?test=1").text
    assert page.index("/static/atelier-test.js") < page.index("script.js") and '<script src="tests.js"></script>' in page
    assert 'crossorigin="anonymous"' in page
    assert "atelier-test.js" not in c.get(p["site_url"]).text  # l'aperçu normal reste intact
    # erreurs réelles → Aurora corrige avec ce retour
    c.post(f"/api/code/atelier/{pid}/result", json={"ok": False, "final": False, "log": "✘ le bouton compte"}, headers=H)
    c.post(f"/api/code/atelier/{pid}/ask", json={"feedback": "✘ le bouton compte → le compteur reste à 0"}, headers=H)
    assert "le compteur reste à 0" in prompts[1][1] and "Fichiers actuels" in prompts[1][1]
    r = c.post(f"/api/code/atelier/{pid}/result", json={"ok": True, "final": True, "log": "Tests : 2/2 réussis"}, headers=H).json()
    assert r["status"] == "done" and r["log"] == "Tests : 2/2 réussis"
    assert c.post(f"/api/code/atelier/{pid}/ask", json={}, headers=H).status_code == 404  # terminé


def test_quatre_essais_au_plus(make_client, monkeypatch):
    monkeypatch.setattr(coderask, "ask", lambda *a, **k: {"text": SITE})
    c = make_client([reply("", [("build_web_page", {"request": "Un compteur de cafés joli sur téléphone"})]), reply("Ok.")])
    login(c)
    pid = _launch(c)
    for _ in range(atelier.MAX_INSTANT_ATTEMPTS):
        assert c.post(f"/api/code/atelier/{pid}/ask", json={}, headers=H).status_code == 200
    assert c.post(f"/api/code/atelier/{pid}/ask", json={}, headers=H).status_code == 409


def test_apercu_dans_l_appli_mais_nulle_part_ailleurs(make_client, monkeypatch):
    monkeypatch.setattr(coderask, "ask", lambda *a, **k: {"text": SITE})
    c = make_client([reply("", [("build_web_page", {"request": "Un compteur de cafés joli sur téléphone"})]), reply("Ok.")])
    login(c)
    pid = _launch(c)
    url = c.post(f"/api/code/atelier/{pid}/ask", json={}, headers=H).json()["site_url"]
    r = c.get(url)
    assert r.headers["x-frame-options"] == "SAMEORIGIN" and "frame-ancestors 'self'" in r.headers["content-security-policy"]
    assert "allow-same-origin" not in r.headers["content-security-policy"]  # toujours une boîte fermée
    assert c.get("/code").headers["x-frame-options"] == "DENY"  # Syrius lui-même : jamais dans un cadre
    assert c.get("/static/atelier-test.js").status_code == 200


def test_tester_le_demarrage_github(make_client):
    c = make_client()
    login(c)
    r = c.post("/api/code/atelier/test-start", headers=H).json()
    assert r["ok"] is False and "pas configurée" in r["reason"]


def test_message_clair_si_hugging_face_demande_pro(monkeypatch):
    monkeypatch.setattr(hfspace, "owner", lambda t: "moi")
    monkeypatch.setattr(hfspace, "_call", lambda *a, **k: (402, {}))
    try:
        hfspace.setup_atelier("hf_x", "atl_x", "https://x", "a/b")
        raise AssertionError("402 attendu")
    except hfspace.SpaceError as e:
        assert "PRO" in str(e) and "atelier instantané" in str(e)
