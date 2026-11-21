"""L'Atelier d'Aurora : elle écrit un programme, le lance et le corrige elle-même jusqu'à ce que les tests passent."""
import json
import sys
from pathlib import Path

import yaml

from server import atelier, github_oidc, training
from server.config import Config
from server.tools.registry import build_tools
from tests.conftest import H, login, reply
from tests.test_agent import events_of
from tests.test_family import member_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "selfcode"))
import atelier as worker  # noqa: E402  (selfcode/atelier.py : le côté serveur de GitHub)


def names(tools):
    return {t["function"]["name"] for t in tools}


# --------------------------------------------------------------- file d'attente
def test_projet_de_bout_en_bout(make_db):
    base = make_db()
    item = atelier.add(base, "Un script Python qui compte les mots d'un fichier, avec des tests.")
    assert item["status"] == "pending" and atelier.take_next(base)["id"] == item["id"]
    assert atelier.take_next(base) is None  # déjà pris
    atelier.report(base, {"id": item["id"], "status": "running", "attempt": 1, "summary": "Essai 1/5…"})
    atelier.report(base, {"id": item["id"], "status": "done", "attempt": 2, "summary": "Ça marche.", "env": "python",
                          "setup": "pip install pytest", "test": "python -m pytest -q", "log": "1 passed",
                          "files": {"mots.py": "def compte(t):\n    return len(t.split())\n", "../evil.py": "x",
                                    "/etc/passwd": "x", "ok/test_mots.py": "from mots import compte\n"}})
    got = atelier.get(base, item["id"])
    assert got["status"] == "done" and got["attempt"] == 2 and set(got["files"]) == {"mots.py", "ok/test_mots.py"}
    text = atelier.for_aurora(got)
    assert "TERMINÉ" in text and "### mots.py" in text and "1 passed" in text


def test_limites_et_refus(make_db):
    base = make_db()
    for bad in ("court", "x" * 5000):
        try:
            atelier.add(base, bad)
            raise AssertionError(bad)
        except atelier.AtelierError:
            pass
    atelier.add(base, "Premier projet assez long pour être accepté")
    atelier.add(base, "Deuxième projet assez long pour être accepté")
    try:
        atelier.add(base, "Troisième projet en même temps : refusé")
        raise AssertionError("3 projets à la fois")
    except atelier.AtelierError:
        pass
    for bad in ({"id": "zz", "status": "done"}, {"id": "abcdef12", "status": "done"},
                {"id": atelier.items(base)[0]["id"], "status": "publié"}):
        try:
            atelier.report(base, bad)
            raise AssertionError(bad)
        except atelier.AtelierError:
            pass


# --------------------------------------------------------------- Aurora et ses outils
def test_outils_reserves_a_aurora():
    cfg = Config()
    assert {"run_code_project", "check_code_project"} <= names(build_tools(cfg, {}, "aurore"))
    assert not {"run_code_project", "check_code_project"} & names(build_tools(cfg, {}))  # pas chez Nova
    aurore = (ROOT / "server" / "aurore.md").read_text(encoding="utf-8")
    assert "run_code_project" in aurore and "Termux" in aurore


def test_aurora_lance_un_projet(make_client):
    c = make_client([reply("", [("run_code_project", {"request": "Un serveur Express qui affiche un minuteur, testé."})]),
                     reply("C'est lancé dans mon atelier : je l'écris, le teste et le corrige.")])
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Fais-moi un minuteur en Express"},
                          headers=H).text)
    card = next(e for e in ev if e["type"] == "atelier")
    projects = c.get("/api/code/atelier").json()
    assert projects[0]["id"] == card["id"] and projects[0]["status"] == "pending" and "Express" in projects[0]["text"]
    assert c.get(f"/api/code/atelier/{card['id']}").json()["id"] == card["id"]
    # la carte reste dans l'historique de la discussion
    hist = c.get(f"/api/code/conversations/{cid}").json()["messages"]
    assert {"type": "atelier", "id": card["id"]} in hist[-1]["diagrams"]


def test_le_serveur_de_github_prend_et_rend_le_projet(make_client):
    c = make_client()
    login(c)
    item = atelier.add(c.db, "Un script qui inverse une chaîne, avec tests")
    auth = {"Authorization": f"Bearer {training.token(c.db)}", **H}
    got = c.post("/api/training/worker/atelier-next", headers=auth).json()["project"]
    assert got == {"id": item["id"], "text": item["text"]}
    r = c.post("/api/training/worker/atelier-report", headers=auth,
               json={"id": item["id"], "status": "done", "attempt": 1, "files": {"inv.py": "x"}})
    assert r.status_code == 200 and c.get(f"/api/code/atelier/{item['id']}").json()["files"] == {"inv.py": "x"}
    assert c.post("/api/training/worker/atelier-next", headers=H).status_code == 401  # sans identité GitHub


def test_atelier_reserve_au_proprietaire(make_client):
    c = make_client()
    login(c)
    lea = member_client(c)
    assert lea.get("/api/code/atelier").status_code == 403


# --------------------------------------------------------------- le travail sur le serveur de GitHub
REPLY = """**RÉSUMÉ:** Une fonction moyenne.
ENVIRONNEMENT: Python
INSTALLATION: aucune
TEST: python -m unittest -v
### FICHIER: calc.py
```python
def moyenne(xs):
    return sum(xs) / len(xs)
```
### FICHIER: ../../etc/passwd
```
pirate
```
#### FICHIER: `node_modules/x.js`
```js
x
```
"""


def test_lecture_de_la_reponse_de_l_ia():
    p = worker.parse(REPLY)
    assert p["summary"] == "Une fonction moyenne." and p["env"] == "python" and p["setup"] == ""
    assert p["test"] == "python -m unittest -v" and list(p["files"]) == ["calc.py"]  # chemins dangereux refusés
    assert worker.parse("ENVIRONNEMENT: Node.js\nINSTALLATION: npm install express\nTEST: node --test")["env"] == "node"


def test_boucle_ecrire_lancer_corriger(tmp_path, monkeypatch):
    """Essai 1 : les tests échouent ; l'erreur réelle est renvoyée à l'IA ; essai 2 : réussi."""
    monkeypatch.setattr(worker, "WORK", tmp_path)
    monkeypatch.setattr(worker, "PROJ", tmp_path / "projet")
    replies = [REPLY.replace("/ len(xs)", "/ (len(xs) + 1)"), REPLY]
    prompts, reports, runs = [], [], []

    def fake_api(path, body):
        if path.endswith("coder-ask"):
            prompts.append(body["prompt"])
            return {"text": replies.pop(0)}
        reports.append(body)
        return {"ok": True}

    def fake_run(env, setup, test):
        code = (tmp_path / "projet" / "calc.py").read_text()
        runs.append(code)
        ok = "+ 1" not in code
        return ok, "1 test OK" if ok else "AssertionError: 2.0 != 3"
    monkeypatch.setattr(worker, "api", fake_api)
    monkeypatch.setattr(worker, "run", fake_run)
    (tmp_path / "project.json").write_text(json.dumps({"id": "abcd1234", "text": "Une moyenne testée"}))
    worker.cmd_work()
    assert len(runs) == 2 and "AssertionError: 2.0 != 3" in prompts[1] and "### FICHIER: calc.py" in prompts[1]
    final = reports[-1]
    assert final["status"] == "done" and final["attempt"] == 2 and "calc.py" in final["files"]
    assert any(r["status"] == "running" and "essai" in r["summary"].lower() for r in reports)  # avancement en direct


def test_echec_apres_5_essais(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "WORK", tmp_path)
    monkeypatch.setattr(worker, "PROJ", tmp_path / "projet")
    reports = []
    monkeypatch.setattr(worker, "api", lambda path, body: {"text": REPLY} if path.endswith("coder-ask") else reports.append(body) or {})
    monkeypatch.setattr(worker, "run", lambda *a: (False, "erreur"))
    (tmp_path / "project.json").write_text(json.dumps({"id": "abcd1234", "text": "Une moyenne testée"}))
    worker.cmd_work()
    assert reports[-1]["status"] == "failed" and "5 essais" in reports[-1]["summary"]


def test_workflow_isole_et_autorise():
    wf = yaml.safe_load((ROOT / ".github/workflows/atelier.yml").read_text())
    assert "atelier.yml" in github_oidc.WORKFLOWS
    job = wf["jobs"]["atelier"]
    assert job["permissions"] == {"contents": "read", "id-token": "write"} and wf["permissions"] == {"contents": "read"}
    text = (ROOT / ".github/workflows/atelier.yml").read_text()
    assert "169.254.169.254 -j DROP" in text and "atelier.py fail" in text
    src = (ROOT / "selfcode/atelier.py").read_text()
    assert '"--pids-limit"' in src and '"--memory"' in src and "--env-file" not in src  # aucun secret dans le conteneur


# --------------------------------------------------------------- sites web : aperçu, capture, téléchargement
SITE = {"site/index.html": "<!doctype html><title>Café</title><link rel=stylesheet href=style.css><p>Salut</p>",
        "site/style.css": "p{color:brown}", "tests/site.test.js": "// test", "package.json": "{}"}


def _done_site(c):
    import base64
    item = atelier.add(c.db, "Un site vitrine pour un café, beau sur téléphone")
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    atelier.report(c.db, {"id": item["id"], "status": "done", "attempt": 1, "env": "web", "files": SITE,
                          "screenshot": base64.b64encode(jpeg).decode()})
    return item, jpeg


def test_apercu_du_site_dans_un_bac_a_sable(make_client):
    c = make_client()
    login(c)
    item, jpeg = _done_site(c)
    p = c.get(f"/api/code/atelier/{item['id']}").json()
    assert "token" not in p and p["has_shot"] and p["env"] == "web"
    assert p["site_url"].endswith("/site/") and p["zip_url"].endswith("/projet.zip")
    anon = type(c)(c.app, base_url="https://testserver")  # sans cookie : comme le site lui-même ou Termux
    page = anon.get(p["site_url"])
    assert page.status_code == 200 and "Salut" in page.text and page.headers["content-type"].startswith("text/html")
    csp = page.headers["content-security-policy"]
    assert csp.startswith("sandbox ") and "allow-same-origin" not in csp  # le site ne peut pas toucher à Syrius
    # bug vu au premier essai : cet en-tête empêchait le bac à sable de charger le CSS et le JavaScript du site
    assert "cross-origin-resource-policy" not in page.headers
    assert anon.get(p["site_url"] + "style.css").headers["content-type"].startswith("text/css")
    for bad in ("../package.json", "tests/site.test.js", "inconnu.html", "%2e%2e/package.json"):
        assert anon.get(p["site_url"] + bad).status_code == 404, bad
    assert anon.get(p["site_url"].replace(item["token"], "mauvais-jeton")).status_code == 404
    assert c.get(f"/api/code/atelier/{item['id']}/capture").content == jpeg
    assert anon.get(f"/api/code/atelier/{item['id']}/capture").status_code == 401


def test_telechargement_zip(make_client):
    import io
    import zipfile
    c = make_client()
    login(c)
    item, _ = _done_site(c)
    p = c.get(f"/api/code/atelier/{item['id']}").json()
    r = type(c)(c.app, base_url="https://testserver").get(p["zip_url"])  # Termux : sans cookie
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert set(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == set(SITE)


def test_capture_refusee_si_ce_n_est_pas_une_image(make_db):
    import base64
    base = make_db()
    item = atelier.add(base, "Un site de test pour la capture d'écran")
    atelier.report(base, {"id": item["id"], "status": "done", "screenshot": base64.b64encode(b"<script>").decode()})
    assert not atelier.get(base, item["id"]).get("has_shot") and atelier.screenshot(base, item["id"]) == b""


def test_l_ia_peut_choisir_un_site():
    assert worker.parse("ENVIRONNEMENT: web\nTEST: node --test")["env"] == "web"
    assert worker.parse("ENVIRONNEMENT: site HTML\nTEST: x")["env"] == "web"
    assert "playwright@1.49.1" in worker.SYSTEM and worker.IMAGES["web"].endswith(f"v{worker.PLAYWRIGHT}-noble")
