"""Scanner de sécurité : propriété obligatoire, passif, pare-feu, et détection sur un FAUX site (aucun réseau)."""
import pytest

from server import sitescan
from server.sitescan import Resp
from tests.conftest import H, login


class Mem:  # mini base clé/valeur
    def __init__(self):
        self.d = {}

    def get_secret(self, k):
        return self.d.get(k)

    def set_secret(self, k, v):
        self.d[k] = v


class FakeSite:
    """Remplace le réseau : un dict {url: Resp}. Enregistre chaque requête (toutes doivent être des GET sur le site)."""

    def __init__(self, pages, domain="exemple.fr"):
        self.pages, self.asked, self.hosts, self.count = pages, [], {domain, "www." + domain}, 0

    def get(self, url, limit=300_000):
        self.count += 1
        self.asked.append(url)
        return self.pages.get(url, Resp(status=404, body=b"non"))


def ok(body=b"", headers=None, **kw):
    return Resp(status=200, body=body if isinstance(body, bytes) else body.encode(), headers=headers or [], **kw)


SECURE = [("strict-transport-security", "max-age=63072000"), ("content-security-policy", "default-src 'self'"),
          ("x-frame-options", "DENY"), ("x-content-type-options", "nosniff"), ("referrer-policy", "no-referrer"),
          ("permissions-policy", "camera=()")]


def site(extra=None, home=None, headers=SECURE):
    pages = {
        "https://exemple.fr/": home or ok("<html><body><h1>Bonjour</h1></body></html>", headers, cert_days=80, tls="TLSv1.3"),
        "http://exemple.fr/": Resp(status=301, headers=[("location", "https://exemple.fr/")]),
        "https://exemple.fr/.well-known/security.txt": ok("Contact: a@b.fr"),
    }
    pages.update(extra or {})
    return FakeSite(pages)


def titles(res):
    return [f["title"] for f in res["findings"]]


def test_site_propre_note_maximale():
    res = sitescan.scan("exemple.fr", site())
    assert res["score"] == 100 and res["counts"]["haute"] == 0 and not res["findings"], titles(res)


def test_detecte_les_erreurs_classiques():
    html = ('<html><head><script src="https://cdn.x.fr/jquery-1.12.4.min.js"></script>'
            '<link rel="stylesheet" href="http://exemple.fr/a.css"></head>'
            '<body><form method="post" action="http://exemple.fr/login"><input type="password" name="p"></form>'
            '<script src="/app.js"></script></body></html>')
    bad = site({
        "https://exemple.fr/.env": ok("DB_PASSWORD=abc123\nAPI_KEY=zzz"),
        "https://exemple.fr/.git/HEAD": ok("ref: refs/heads/main"),
        "https://exemple.fr/app.js": ok('const k="AKIAABCDEFGHIJKLMNOP";'),
        "https://exemple.fr/uploads/": ok("<title>Index of /uploads</title>"),
    }, home=ok(html, [("set-cookie", "session=abc; Path=/"), ("server", "Apache/2.4.49"), ("x-powered-by", "PHP/7.4")],
               cert_days=5, tls="TLSv1.3"))
    bad.pages["http://exemple.fr/"] = ok("pas de redirection")
    res = sitescan.scan("exemple.fr", bad)
    t = " | ".join(titles(res))
    for attendu in (".env public", "Dossier .git public", "Secret visible dans le code : clé AWS", "Liste des fichiers visible",
                    "Mot de passe envoyé sans chiffrement", "Contenu mixte", "jQuery ancien", "sans HttpOnly", "sans Secure",
                    "HSTS absent", "Content-Security-Policy".replace("Content-Security-Policy", "politique de sécurité"),
                    "Version du serveur visible", "Technologie visible", "bientôt expiré", "reste accessible sans chiffrement"):
        assert attendu in t, f"manque : {attendu}\n{t}"
    assert res["score"] < 20 and res["counts"]["haute"] >= 4
    assert "AKIAABCDEFGHIJKLMNOP" not in str(res)  # le secret trouvé n'est jamais recopié en entier


def test_pas_de_faux_positif_si_le_site_repond_200_partout():
    # un site qui renvoie sa page d'accueil pour TOUT : les contenus ne ressemblent pas à de vrais fichiers sensibles
    page = ok("<html><body>Accueil</body></html>")
    f = site()
    f.get = lambda url, limit=300_000, _p=f.pages: _p.get(url, page)
    res = sitescan.scan("exemple.fr", f)
    assert not [x for x in res["findings"] if x["sev"] == "haute"], titles(res)


def test_scan_uniquement_en_lecture_et_sur_le_site():
    f = site()
    sitescan.scan("exemple.fr", f)
    assert f.asked and all(u.startswith(("https://exemple.fr/", "http://exemple.fr/", "https://www.exemple.fr/")) for u in f.asked)
    assert f.count <= sitescan.MAX_REQUESTS


def test_domaines_refuses():
    for bad in ("localhost", "127.0.0.1", "192.168.0.1", "serveur.local", "intranet", "exemple.fr:8080", "a b.fr", "", "x"):
        with pytest.raises(sitescan.ScanError):
            sitescan.clean_domain(bad)
    assert sitescan.clean_domain("https://WWW.Exemple.FR/page?x=1") == "exemple.fr"


def test_propriete_obligatoire(monkeypatch):
    base = Mem()
    with pytest.raises(sitescan.ScanError, match="Ajoute d'abord"):
        sitescan.run(base, "exemple.fr", fetcher=site())  # site jamais ajouté
    entry = sitescan.add_domain(base, "exemple.fr")
    f = site()
    with pytest.raises(sitescan.ScanError, match="Preuve de propriété"):
        sitescan.run(base, "exemple.fr", fetcher=f)  # ajouté mais pas prouvé
    assert not any("/.env" in u for u in f.asked)  # aucun scan n'a eu lieu
    # preuve par fichier
    f = site({"https://exemple.fr" + sitescan.WELL_KNOWN: ok(entry["token"])})
    assert sitescan.run(base, "exemple.fr", fetcher=f, now=1000)["score"] == 100
    # preuve par balise
    base2 = Mem()
    e2 = sitescan.add_domain(base2, "exemple.fr")
    meta = f'<html><head><meta name="syrius-verify" content="{e2["token"]}"></head></html>'
    assert sitescan.verify("exemple.fr", e2["token"], site(home=ok(meta)))
    # mauvais code
    assert not sitescan.verify("exemple.fr", "autre-code", site({"https://exemple.fr" + sitescan.WELL_KNOWN: ok(entry["token"])}))


def test_serveur_syrius_reconnu_d_office_et_frequence_limitee():
    base = Mem()
    sitescan.run(base, "syrius.exemple.fr", own_hosts=("syrius.exemple.fr",), fetcher=FakeSite({}, "syrius.exemple.fr"), now=1000)
    with pytest.raises(sitescan.ScanError, match="2 minutes"):
        sitescan.run(base, "syrius.exemple.fr", own_hosts=("syrius.exemple.fr",), fetcher=FakeSite({}, "syrius.exemple.fr"), now=1060)
    sitescan.run(base, "syrius.exemple.fr", own_hosts=("syrius.exemple.fr",), fetcher=FakeSite({}, "syrius.exemple.fr"), now=1200)


def test_limite_de_sites():
    base = Mem()
    for i in range(sitescan.MAX_DOMAINS):
        sitescan.add_domain(base, f"site{i}.fr")
    with pytest.raises(sitescan.ScanError):
        sitescan.add_domain(base, "trop.fr")


def test_pare_feu_du_scanner_refuse_les_adresses_privees(monkeypatch):
    f = sitescan.Fetcher("exemple.fr")
    monkeypatch.setattr(sitescan.web, "resolve_public", lambda h, p: (_ for _ in ()).throw(sitescan.web.WebError("Adresse non publique refusée par le pare-feu.")))
    r = f.get("https://exemple.fr/")
    assert r.error == "refus" and "non publique" in r.detail
    assert f.get("https://autre-site.fr/").error == "refus"  # jamais hors du domaine
    assert f.get("http://169.254.169.254/latest/meta-data/").error == "refus"


def test_routes_reservees_au_proprietaire(make_client):
    c = make_client()
    login(c)
    assert c.get("/api/sitescan").status_code == 200
    r = c.post("/api/sitescan/domains", headers=H, json={"domain": "monsite.fr"})
    assert r.status_code == 200 and len(r.json()["token"]) == 24 and "syrius-verify" in r.json()["instructions"]
    assert c.post("/api/sitescan/domains", headers=H, json={"domain": "localhost"}).status_code == 400
    # site non prouvé : le scan est refusé, sans aucune requête vers le site
    r = c.post("/api/sitescan/run", headers=H, json={"domain": "monsite.fr"})
    assert r.status_code == 400
    assert c.post("/api/sitescan/run", headers=H, json={"domain": "pasajoute.fr"}).status_code == 400
    assert c.delete("/api/sitescan/domains/monsite.fr", headers=H).status_code == 200
    assert c.get("/api/sitescan").json()["sites"] == [] or all(s["own"] for s in c.get("/api/sitescan").json()["sites"])


def test_resume_pour_l_ia():
    res = sitescan.scan("exemple.fr", site({"https://exemple.fr/.env": ok("A_B=1")}))
    txt = sitescan.chat_summary(res)
    assert "exemple.fr" in txt and ".env public" in txt and "ne remplace pas" in txt
