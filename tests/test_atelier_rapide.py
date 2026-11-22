"""Atelier rapide d'Aurora : serveur Hugging Face toujours allumé, réveillé par Syrius, avec SA clé limitée."""
import io
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from server import atelier, hfspace, training
from tests.conftest import H, login, reply
from tests.test_agent import events_of

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "selfcode"))
import atelier as worker  # noqa: E402


@pytest.fixture(autouse=True)
def _mode_atelier(monkeypatch):
    """Ces tests portent sur l'atelier : Aurora est en mode « toute seule »."""
    from server import atelier as _a
    monkeypatch.setattr(_a, "get_mode", lambda base: "atelier")



def test_cle_de_l_atelier_limitee_a_ses_routes(make_client):
    c = make_client()
    login(c)
    key = atelier.worker_token(c.db)
    auth = {"Authorization": f"Bearer {key}", **H}
    assert key.startswith("atl_")
    assert c.post("/api/training/worker/atelier-next", headers=auth).status_code == 200
    assert c.get("/api/training/worker/examples", headers=auth).status_code == 401  # tes exemples privés : non
    assert c.post("/api/training/worker/mail-sort", headers=auth).status_code == 401  # tes emails : non
    assert c.post("/api/training/worker/atelier-next", headers={"Authorization": "Bearer atl_faux", **H}).status_code == 401
    # la clé d'entraînement de GitHub marche toujours (secours)
    assert c.post("/api/training/worker/atelier-next",
                  headers={"Authorization": f"Bearer {training.token(c.db)}", **H}).status_code == 200


class _Resp(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_reveil(make_db, monkeypatch):
    base = make_db()
    assert not atelier.wake(base)  # pas d'atelier rapide installé
    atelier.set_space(base, {"space": "moi/syrius-atelier", "url": "https://evil.example.com"})
    assert not atelier.wake(base)  # jamais une autre adresse qu'un Space Hugging Face
    atelier.set_space(base, {"space": "moi/syrius-atelier", "url": "https://moi-syrius-atelier.hf.space"})
    seen = {}

    def fake(req, timeout=0):
        seen["url"], seen["key"] = req.full_url, req.headers.get("X-atelier-key")
        return _Resp(202, b"ok")
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert atelier.wake(base) and seen["url"] == "https://moi-syrius-atelier.hf.space/wake"
    assert seen["key"] == atelier.worker_token(base)
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: _Resp(200, b"<html>Space en sommeil</html>"))
    assert not atelier.wake(base)  # la page d'attente d'un Space endormi n'est pas l'atelier


def test_projet_reveille_l_atelier_sans_github(make_client, monkeypatch):
    from server import selfcode
    calls = []
    monkeypatch.setattr(atelier, "wake", lambda base: calls.append("wake") or True)
    monkeypatch.setattr(selfcode, "dispatch", lambda *a: calls.append("github") or True)
    c = make_client([reply("", [("run_code_project", {"request": "Un site vitrine pour un café, testé."})]), reply("Lancé.")])
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    events_of(c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Fais un site"}, headers=H).text)
    assert calls == ["wake"]  # GitHub n'est pas dérangé
    res = [b["content"] for m in c.db.get_messages(cid) for b in m["content"] if b.get("tool_name") == "run_code_project"]
    assert "démarre maintenant" in res[0]


def test_installation_du_serveur(make_client, monkeypatch):
    got = {}

    def fake_setup(hf, key, url, repo):
        got.update(hf=hf, key=key, url=url)
        return {"space": "moi/syrius-atelier", "url": "https://moi-syrius-atelier.hf.space",
                "page": "https://huggingface.co/spaces/moi/syrius-atelier"}
    monkeypatch.setattr(hfspace, "setup_atelier", fake_setup)
    c = make_client()
    c.app.state.cfg.hf_token = "hf_x"
    login(c)
    r = c.post("/api/code/atelier/fast", headers=H)
    assert r.status_code == 200 and got["key"] == atelier.worker_token(c.db) and got["key"] != "hf_x"
    assert atelier.space(c.db)["url"] == "https://moi-syrius-atelier.hf.space"


def test_dockerfile_et_adresse():
    assert hfspace.ATELIER_DOCKERFILE == (ROOT / "selfcode/Dockerfile.atelier").read_text(encoding="utf-8")
    assert "playwright:v1.49.1-noble" in hfspace.ATELIER_DOCKERFILE and "USER 1000" in hfspace.ATELIER_DOCKERFILE
    assert "HF_TOKEN" not in hfspace.ATELIER_DOCKERFILE
    assert hfspace.space_host("Snow17044", "syrius-atelier") == "https://snow17044-syrius-atelier.hf.space"


def test_execution_locale_sans_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "WORK", tmp_path)
    monkeypatch.setattr(worker, "PROJ", tmp_path / "p")
    (tmp_path / "p").mkdir()
    monkeypatch.setenv("ATELIER_TOKEN", "atl_secret")
    monkeypatch.setenv("SYRIUS_URL", "https://secret.example")
    ok, out = worker.run_local("env; echo FIN")
    assert ok and "FIN" in out and "atl_secret" not in out and "secret.example" not in out
    monkeypatch.setattr(worker, "RUN_TIMEOUT", 2)
    t0 = time.time()
    ok, out = worker.run_local("sleep 30 & sleep 30")
    assert not ok and "TROP LONG" in out and time.time() - t0 < 15


@pytest.mark.skipif(not Path("/proc/self/environ").exists(), reason="Linux seulement")
def test_la_cle_ne_reste_pas_dans_l_environnement(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "ATELIER_TOKEN": "atl_test_secret", "SYRIUS_URL": "http://127.0.0.1:9", "PORT": str(port),
           "RUNNER_TEMP": str(tmp_path)}
    p = subprocess.Popen([sys.executable, str(ROOT / "selfcode/atelier_space.py")], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        assert b"atl_test_secret" not in Path(f"/proc/{p.pid}/environ").read_bytes()
    finally:
        p.kill()
