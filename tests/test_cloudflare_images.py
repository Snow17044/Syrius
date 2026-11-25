"""Images et photos par Cloudflare Workers AI (clés déjà utilisées pour les IA de secours)."""
import base64
import json

import pytest

from server.config import Config
from server.llm import providers_from_config
from server.tools import imagegen
from server import diagnostic

@pytest.fixture(autouse=True)
def _keys_restaurees():
    saved = dict(imagegen.KEYS)
    yield
    imagegen.KEYS.clear()
    imagegen.KEYS.update(saved)


PNG = diagnostic._png(64, 64) + bytes(range(256)) * 8  # assez gros pour passer le contrôle de taille


def _cfg():
    c = Config()
    c.openrouter_api_key = c.groq_api_key = c.mistral_api_key = c.github_models_token = c.gemini_api_key = ""
    c.cloudflare_api_key, c.cloudflare_account_id = "cf_secret", "a" * 32
    c.ollama_url = ""
    return c


def test_cloudflare_en_premier_pour_les_images(monkeypatch):
    imagegen.configure(_cfg())
    assert imagegen.sources()[0] is imagegen._cloudflare
    seen = {}

    def fake(host, method, path, headers, body=None):
        seen.update(host=host, path=path, auth=headers["Authorization"], body=json.loads(body))
        return 200, "application/json", json.dumps({"result": {"image": base64.b64encode(PNG).decode()},
                                                    "success": True}).encode()
    monkeypatch.setattr(imagegen, "_fetch", fake)
    ctype, data = imagegen.generate("une pomme rouge sur une table", seed=7)
    assert ctype == "image/png" and data == PNG
    assert seen["host"] == "api.cloudflare.com" and seen["auth"] == "Bearer cf_secret"
    assert seen["path"] == f"/client/v4/accounts/{'a' * 32}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    assert seen["body"]["prompt"] == "une pomme rouge sur une table" and seen["body"]["seed"] == 7


def test_relais_si_cloudflare_echoue(monkeypatch):
    imagegen.configure(_cfg())
    calls = []

    def fake(host, method, path, headers, body=None):
        calls.append(host)
        if host == "api.cloudflare.com":
            return 429, "application/json", b"{}"
        return 200, "image/png", PNG
    monkeypatch.setattr(imagegen, "_fetch", fake)
    assert imagegen.generate("une pomme rouge", seed=1)[1] == PNG
    assert calls == ["api.cloudflare.com", imagegen.HOST]


def test_cloudflare_refuse_ce_qui_n_est_pas_une_image(monkeypatch):
    imagegen.configure(_cfg())
    monkeypatch.setattr(imagegen, "_fetch", lambda *a, **k: (200, "application/json",
                        json.dumps({"result": {"image": base64.b64encode(b"<html>pas une image</html>" * 50).decode()}}).encode()))
    try:
        imagegen._cloudflare("une pomme", 1)
        raise AssertionError("image invalide acceptée")
    except imagegen.ImageGenError:
        pass


def test_sans_cle_cloudflare_rien_ne_change():
    c = _cfg()
    c.cloudflare_api_key = ""
    imagegen.configure(c)
    assert imagegen._cloudflare not in imagegen.sources()
    c = _cfg()
    c.cloudflare_account_id = "pas-un-identifiant"
    imagegen.configure(c)
    assert imagegen._cloudflare not in imagegen.sources()


def test_ia_cloudflare_qui_voient_les_photos():
    provs = {p.model: p for p in providers_from_config(_cfg())}
    assert provs["@cf/google/gemma-4-26b-a4b-it"].vision  # Gemma 4 voit les photos
    assert not provs["@cf/zai-org/glm-4.7-flash"].vision
    scout = provs["@cf/meta/llama-4-scout-17b-16e-instruct"]
    assert scout.vision and scout.photos_only  # relais réservé aux photos


def test_diagnostic_liste_cloudflare():
    imagegen.configure(_cfg())
    assert any(src is imagegen._cloudflare for src in imagegen.sources())
    import inspect
    assert "Images · Cloudflare FLUX" in inspect.getsource(diagnostic.run)
