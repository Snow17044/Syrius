"""Référencement Google : pages publiques indexables, parties privées exclues."""
from tests.conftest import H


def test_page_decouvrir_et_accueil(make_client):
    c = make_client()
    c.app.state.cfg.public_url = "https://syrius.example"
    r = c.get("/decouvrir")
    assert r.status_code == 200 and "Syrius, ton assistant IA personnel" in r.text
    assert '<link rel="canonical" href="https://syrius.example/decouvrir">' in r.text and "{{" not in r.text
    assert '"@type": "FAQPage"' in r.text
    home = c.get("/").text
    assert '<meta name="description"' in home and 'href="https://syrius.example/"' in home and "{{" not in home
    assert 'href="/decouvrir"' in home
    assert c.head("/").status_code == 200 and c.head("/decouvrir").status_code == 200
    assert c.get("/static/decouvrir.css").status_code == 200


def test_robots_et_plan_du_site(make_client):
    c = make_client()
    c.app.state.cfg.public_url = "https://testserver"
    robots = c.get("/robots.txt").text
    for private in ("/api/", "/code", "/partenaire", "/atelier/", "/reinitialiser"):
        assert f"Disallow: {private}" in robots
    assert "Sitemap: https://testserver/sitemap.xml" in robots
    sm = c.get("/sitemap.xml")
    assert sm.headers["content-type"].startswith("application/xml")
    assert "<loc>https://testserver/decouvrir</loc>" in sm.text and "/api" not in sm.text
    # une autre adresse (copie de déploiement Vercel) : rien n'est indexé
    c.app.state.cfg.public_url = "https://syrius.example"
    assert c.get("/robots.txt").text == "User-agent: *\nDisallow: /\n"


def test_code_de_verification_google(make_client):
    c = make_client()
    c.app.state.cfg.google_verification = "AbC123_verif-xyz"
    assert '<meta name="google-site-verification" content="AbC123_verif-xyz">' in c.get("/").text
    assert 'google-site-verification' in c.get("/decouvrir").text
    c.app.state.cfg.google_verification = '"><script>alert(1)</script>'
    assert "google-site-verification" not in c.get("/").text and "<script>alert" not in c.get("/").text


def test_syrius_code_jamais_indexe(make_client):
    c = make_client()
    assert '<meta name="robots" content="noindex">' in c.get("/code").text


def test_cle_indexnow(make_client):
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "server/app.py").read_text(encoding="utf-8")
    key = re.search(r'INDEXNOW_KEY = "([0-9a-f]{32})"', src).group(1)
    r = make_client().get(f"/{key}.txt")
    assert r.status_code == 200 and r.text == key
