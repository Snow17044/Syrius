"""« Améliorer Syrius » : démarrage immédiat si possible, message honnête sinon (GitHub ne passe qu'environ 1 fois/heure)."""
import io
import json

from server import selfcode
from tests.conftest import H, login


class Resp(io.BytesIO):
    def __init__(self, status=204):
        super().__init__(b"")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_dispatch_appelle_github_avec_le_jeton(monkeypatch):
    seen = {}

    def fake(req, timeout=0):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=json.loads(req.data))
        return Resp(204)
    monkeypatch.setattr(selfcode.urllib.request, "urlopen", fake)
    assert selfcode.dispatch("jeton-de-test", "Snow17044/Syrius")
    assert seen["url"].endswith("/repos/Snow17044/Syrius/actions/workflows/selfcode.yml/dispatches")
    assert seen["auth"] == "Bearer jeton-de-test" and seen["body"] == {"ref": "main"}


def test_dispatch_ne_plante_jamais(monkeypatch):
    assert not selfcode.dispatch("", "Snow17044/Syrius")  # pas de jeton
    assert not selfcode.dispatch("t", "pas un depot ; rm -rf")  # adresse douteuse refusée

    def boom(req, timeout=0):
        raise OSError("réseau")
    monkeypatch.setattr(selfcode.urllib.request, "urlopen", boom)
    assert not selfcode.dispatch("t", "Snow17044/Syrius")


def test_route_indique_si_le_demarrage_est_immediat(make_client, monkeypatch):
    owner = make_client()
    login(owner)
    monkeypatch.setattr(selfcode, "dispatch", lambda token, repo: bool(token))
    r = owner.post("/api/selfcode", json={"text": "Ajoute un bouton pour copier une réponse"}, headers=H).json()
    assert r["status"] == "pending" and r["started"] is False  # pas de jeton configuré
    info = owner.get("/api/selfcode/launch").json()
    assert info["auto"] is False and info["url"].endswith("/actions/workflows/selfcode.yml")
    owner.app.state.cfg.github_dispatch_token = "jeton-de-test"  # le propriétaire a donné un jeton
    r2 = owner.post("/api/selfcode", json={"text": "Change la couleur du bouton d'envoi"}, headers=H).json()
    assert r2["started"] is True and owner.get("/api/selfcode/launch").json()["auto"] is True


def test_interface_honnete_sur_le_delai():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    js, html = (root / "web/code.js").read_text(), (root / "web/code.html").read_text()
    assert "toutes les 15 min" in js and "parfois" in js and "Lancer maintenant" in html  # 15 min, mais sans promettre l'impossible
    assert 'rel="noopener"' in html
