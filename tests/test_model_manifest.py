"""Nouvelle version de notre IA : annoncée par la conversion (GitHub), lue par l'application."""
from fastapi.testclient import TestClient

from server import github_oidc
from tests.conftest import H, login
from tests.test_github_oidc import KEYS, REPO, token

GOOD = {"file": "syrius-1.5b-43700000000-dynamic_wi8_afp32.litertlm", "sha256": "a" * 64, "size": 1_567_653_904,
        "run_id": "43700000000"}


def test_annonce_puis_lecture(make_client, monkeypatch):
    owner = make_client()
    login(owner)
    monkeypatch.setattr(github_oidc, "_jwks", lambda: KEYS)
    monkeypatch.setattr(github_oidc.time, "time", lambda: 1500)
    gh = TestClient(owner.app, base_url="https://testserver")
    W = {**H, "Authorization": "Bearer " + token(
        event_name="workflow_run", job_workflow_ref=f"{REPO}/.github/workflows/convert-syrius.yml@refs/heads/main")}
    assert owner.get("/api/model/manifest").json() == {}
    assert gh.post("/api/model/manifest", headers=H, json=GOOD).status_code == 401  # sans signature GitHub
    for bad in ({"file": "../../evil.litertlm"}, {"file": "syrius-1.5b-1-x.apk"}, {"sha256": "zz"}, {"size": 5}):
        assert gh.post("/api/model/manifest", headers=W, json={**GOOD, **bad}).status_code == 422
    r = gh.post("/api/model/manifest", headers=W, json=GOOD)
    assert r.status_code == 200
    m = owner.get("/api/model/manifest").json()
    assert m["file"] == GOOD["file"] and m["sha256"] == GOOD["sha256"] and m["at"] > 0
    assert TestClient(owner.app, base_url="https://testserver").get("/api/model/manifest").status_code == 401
