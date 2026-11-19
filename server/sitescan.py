"""Scanner de sécurité PASSIF pour TES sites (pas ceux des autres).

Garde-fous (non négociables) :
- seuls les domaines dont tu as PROUVÉ être le propriétaire sont scannés : un fichier ou une balise secrète que
  seul le propriétaire du site peut placer (vérifié à chaque scan) ; le serveur Syrius lui-même est reconnu d'office ;
- passif : uniquement des requêtes GET comme un navigateur (pages, fichiers connus). Aucune attaque, aucun essai de
  mot de passe, aucune injection, aucun formulaire envoyé ;
- doux : 60 requêtes au plus, 6 en parallèle, 25 s au plus, un scan toutes les 2 minutes par site ;
- même pare-feu que la lecture de pages web (adresses publiques seulement, ports 80/443, certificat vérifié) ;
- ne sort jamais du domaine scanné (les redirections vers un autre site ne sont pas suivies).

Il repère les erreurs courantes (en-têtes de sécurité absents, fichiers sensibles exposés, clés secrètes visibles,
cookies mal protégés, contenu mixte, bibliothèques anciennes…). Il NE remplace PAS un test d'intrusion complet.
"""
from __future__ import annotations

import http.client
import json
import re
import secrets
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from .tools import web

KEY = "site_scan_v1"
MAX_DOMAINS = 5
MAX_REQUESTS = 60
MAX_PAGES = 12
MAX_SCRIPTS = 6
TIME_BUDGET = 25.0
MIN_DELAY = 120  # secondes entre deux scans du même site
UA = "SyriusSecurityCheck/1.0 (scan demandé par le propriétaire du site)"
SEV_ORDER = {"haute": 0, "moyenne": 1, "faible": 2, "info": 3}
_DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
WELL_KNOWN = "/.well-known/syrius-verify.txt"


class ScanError(Exception):
    """Refus ou erreur affichable."""


# --------------------------------------------------------------------------- domaines et preuve de propriété
def clean_domain(raw: str) -> str:
    d = str(raw or "").strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0].split("?")[0].split("#")[0].rstrip(".")
    if d.startswith("www."):
        d = d[4:]
    if ":" in d or not _DOMAIN.match(d) or d.endswith(web.BLOCKED_SUFFIXES):
        raise ScanError("Nom de site invalide. Écris par exemple : monsite.fr")
    return d


def _load(base) -> dict:
    try:
        data = json.loads(base.get_secret(KEY) or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _save(base, data: dict) -> None:
    base.set_secret(KEY, json.dumps(data, ensure_ascii=False))


def instructions(domain: str, token: str) -> str:
    return (f"Pour prouver que le site est à toi, ajoute sur {domain} un fichier accessible à "
            f"https://{domain}{WELL_KNOWN} qui contient exactement ce code : {token}   "
            f"(ou, à la place, une balise <meta name=\"syrius-verify\" content=\"{token}\"> dans l'en-tête de la "
            "page d'accueil). Si tu as créé ton site avec un assistant de code, demande-lui de le faire.")


def public_entries(base, own_host: str = "") -> list[dict]:
    out = []
    own = clean_domain(own_host) if own_host else ""
    data = _load(base)
    if own:
        out.append({"domain": own, "own": True, "token": "", "last": (data.get(own) or {}).get("last"),
                    "history": (data.get(own) or {}).get("history", [])})
    for dom, e in data.items():
        if dom == own or e.get("own"):
            continue
        out.append({"domain": dom, "own": False, "token": e["token"], "instructions": instructions(dom, e["token"]),
                    "last": e.get("last"), "history": e.get("history", [])})
    return out


def add_domain(base, raw: str) -> dict:
    dom = clean_domain(raw)
    data = _load(base)
    if dom not in data or not data[dom].get("token"):
        if len([e for e in data.values() if e.get("token")]) >= MAX_DOMAINS:
            raise ScanError(f"{MAX_DOMAINS} sites au plus : supprime-en un d'abord.")
        data[dom] = {**data.get(dom, {}), "token": secrets.token_hex(12), "added": int(time.time()), "own": False}
        _save(base, data)
    return {"domain": dom, "token": data[dom]["token"], "instructions": instructions(dom, data[dom]["token"])}


def remove_domain(base, raw: str) -> bool:
    dom = clean_domain(raw)
    data = _load(base)
    if dom not in data:
        return False
    del data[dom]
    _save(base, data)
    return True


# --------------------------------------------------------------------------- requêtes (même pare-feu que le web)
@dataclass
class Resp:
    status: int = 0
    headers: list = field(default_factory=list)  # [(nom en minuscules, valeur)] : plusieurs Set-Cookie possibles
    body: bytes = b""
    error: str = ""      # "" | "cert" | "tls" | "net" | "refus"
    detail: str = ""
    cert_days: int | None = None
    tls: str = ""

    def h(self, name: str) -> str:
        return next((v for k, v in self.headers if k == name), "")

    def all(self, name: str) -> list[str]:
        return [v for k, v in self.headers if k == name]


class Fetcher:
    """GET protégés vers UN domaine (et son « www »). Compte les requêtes ; remplaçable dans les tests."""

    def __init__(self, domain: str):
        self.hosts = {domain, "www." + domain}
        self.count = 0
        self._lock = threading.Lock()

    def get(self, url: str, limit: int = 300_000) -> Resp:
        with self._lock:
            if self.count >= MAX_REQUESTS:
                return Resp(error="refus", detail="limite de requêtes atteinte")
            self.count += 1
        try:
            scheme, host, port, path = web.check_url(url)
            if host not in self.hosts:
                return Resp(error="refus", detail="hors du site scanné")
            ip = web.resolve_public(host, port)
        except web.WebError as e:
            return Resp(error="refus", detail=str(e))
        cls = web._PinnedHTTPS if scheme == "https" else web._PinnedHTTP
        conn = cls(host, ip, port, 5)
        out = Resp()
        try:
            conn.request("GET", path, headers={"User-Agent": UA, "Accept": "*/*", "Connection": "close"})
            sock = conn.sock
            if scheme == "https" and sock is not None:
                out.tls = sock.version() or ""
                cert = sock.getpeercert()
                if cert and cert.get("notAfter"):
                    out.cert_days = int((ssl.cert_time_to_seconds(cert["notAfter"]) - time.time()) // 86400)
            resp = conn.getresponse()
            out.status = resp.status
            out.headers = [(k.lower(), v) for k, v in resp.getheaders()]
            out.body = resp.read(limit)
        except ssl.SSLCertVerificationError as e:
            out.error, out.detail = "cert", str(getattr(e, "verify_message", "") or "certificat refusé")[:100]
        except ssl.SSLError as e:
            out.error, out.detail = "tls", str(e)[:100]
        except (OSError, http.client.HTTPException, socket.timeout):
            out.error = "net"
        finally:
            conn.close()
        return out


def _text(r: Resp) -> str:
    return r.body.decode("utf-8", errors="replace")


def verify(domain: str, token: str, fetcher=None) -> bool:
    """Le site contient-il notre code secret (fichier ou balise) ? Seul son propriétaire peut l'y mettre."""
    f = fetcher or Fetcher(domain)
    r = f.get(f"https://{domain}{WELL_KNOWN}", 2000)
    if r.status == 200 and token in _text(r)[:500]:
        return True
    r = f.get(f"https://{domain}/", 200_000)
    return r.status == 200 and bool(re.search(
        r"<meta[^>]+name=[\"']syrius-verify[\"'][^>]+content=[\"']" + re.escape(token) + r"[\"']", _text(r), re.I))


# --------------------------------------------------------------------------- contrôles (fonctions pures)
def F(sev: str, title: str, detail: str, fix: str, where: str = "") -> dict:
    return {"sev": sev, "title": title, "detail": detail, "fix": fix, "where": where}


def check_headers(r: Resp, https: bool = True) -> list[dict]:
    out = []
    csp = r.h("content-security-policy")
    hsts = r.h("strict-transport-security")
    if https and not hsts:
        out.append(F("moyenne", "HSTS absent", "Le navigateur n'est pas obligé d'utiliser HTTPS pour ce site.",
                     "Ajoute l'en-tête Strict-Transport-Security: max-age=31536000; includeSubDomains."))
    elif https:
        m = re.search(r"max-age=(\d+)", hsts)
        if not m or int(m.group(1)) < 15552000:
            out.append(F("faible", "HSTS trop court", "La durée de HSTS est inférieure à 6 mois.",
                         "Mets max-age=31536000 (1 an)."))
    if not csp:
        out.append(F("moyenne", "Pas de politique de sécurité du contenu (CSP)",
                     "Rien ne limite les scripts qui peuvent s'exécuter sur tes pages : une faille XSS ferait plus de dégâts.",
                     "Ajoute un en-tête Content-Security-Policy (commence par : default-src 'self')."))
    if not r.h("x-frame-options") and "frame-ancestors" not in csp:
        out.append(F("moyenne", "Site affichable dans le cadre d'un autre site (clickjacking)",
                     "Un site pirate pourrait afficher le tien invisiblement et piéger les clics.",
                     "Ajoute X-Frame-Options: DENY (ou frame-ancestors 'none' dans la CSP)."))
    if r.h("x-content-type-options").lower() != "nosniff":
        out.append(F("faible", "X-Content-Type-Options absent", "Le navigateur peut mal deviner le type des fichiers.",
                     "Ajoute X-Content-Type-Options: nosniff."))
    if not r.h("referrer-policy"):
        out.append(F("faible", "Referrer-Policy absent", "Les adresses de tes pages sont envoyées aux autres sites.",
                     "Ajoute Referrer-Policy: strict-origin-when-cross-origin."))
    if not r.h("permissions-policy"):
        out.append(F("info", "Permissions-Policy absent", "Rien ne limite l'accès à la caméra, au micro, etc.",
                     "Ajoute Permissions-Policy: camera=(), microphone=(), geolocation=()."))
    server = r.h("server")
    if re.search(r"\d+\.\d+", server):
        out.append(F("faible", "Version du serveur visible", f"L'en-tête Server annonce « {server[:60]} ».",
                     "Masque la version (ServerTokens Prod pour Apache, server_tokens off pour nginx)."))
    if r.h("x-powered-by"):
        out.append(F("faible", "Technologie visible", f"L'en-tête X-Powered-By annonce « {r.h('x-powered-by')[:60]} ».",
                     "Supprime l'en-tête X-Powered-By."))
    if r.h("access-control-allow-origin") == "*" and r.h("access-control-allow-credentials").lower() == "true":
        out.append(F("haute", "CORS dangereux", "Le site accepte les requêtes de n'importe quel site avec les cookies.",
                     "N'autorise que tes propres domaines dans Access-Control-Allow-Origin."))
    return out


def check_cookies(r: Resp, https: bool = True) -> list[dict]:
    out = []
    for c in r.all("set-cookie"):
        name = c.split("=", 1)[0].strip()[:40]
        low = c.lower()
        sensitive = bool(re.search(r"sess|token|auth|sid|jwt|login", name, re.I))
        if https and "secure" not in low:
            out.append(F("moyenne" if sensitive else "faible", f"Cookie « {name} » sans Secure",
                         "Le cookie peut être envoyé sans chiffrement.", "Ajoute l'attribut Secure.", name))
        if "httponly" not in low:
            out.append(F("moyenne" if sensitive else "faible", f"Cookie « {name} » sans HttpOnly",
                         "Un script de la page peut lire ce cookie (vol de session si faille XSS).",
                         "Ajoute l'attribut HttpOnly.", name))
        if "samesite" not in low:
            out.append(F("faible", f"Cookie « {name} » sans SameSite", "Le cookie est envoyé depuis d'autres sites.",
                         "Ajoute SameSite=Lax (ou Strict).", name))
    return out


_ZIP = b"PK\x03\x04"
# (chemin, gravité, titre, validateur(résultat) → vrai si c'est VRAIMENT exposé)
PROBES = [
    ("/.env", "haute", "Fichier .env public (mots de passe et clés !)",
     lambda r: re.search(rb"(?m)^[A-Z][A-Z0-9_]{2,}\s*=", r.body[:4000]) is not None),
    ("/.git/HEAD", "haute", "Dossier .git public (tout ton code peut être téléchargé)",
     lambda r: r.body.startswith(b"ref:")),
    ("/.git/config", "haute", "Configuration .git publique", lambda r: b"[core]" in r.body[:2000]),
    ("/.htpasswd", "haute", "Fichier .htpasswd public", lambda r: re.search(rb"^[\w.-]+:(\$|\{SHA\})", r.body) is not None),
    ("/phpinfo.php", "haute", "phpinfo() public (révèle toute la configuration)",
     lambda r: b"phpinfo()" in r.body or b"PHP Version" in r.body),
    ("/wp-config.php.bak", "haute", "Sauvegarde de configuration WordPress publique", lambda r: b"DB_PASSWORD" in r.body),
    ("/config.php.bak", "haute", "Sauvegarde de configuration publique", lambda r: b"<?php" in r.body or b"password" in r.body.lower()),
    ("/backup.zip", "haute", "Archive de sauvegarde publique", lambda r: r.body.startswith(_ZIP)),
    ("/site.zip", "haute", "Archive du site publique", lambda r: r.body.startswith(_ZIP)),
    ("/backup.sql", "haute", "Sauvegarde de base de données publique", lambda r: re.search(rb"CREATE TABLE|INSERT INTO", r.body) is not None),
    ("/dump.sql", "haute", "Export de base de données public", lambda r: re.search(rb"CREATE TABLE|INSERT INTO", r.body) is not None),
    ("/server-status", "moyenne", "Page d'état du serveur publique", lambda r: b"Apache Server Status" in r.body),
    ("/.DS_Store", "faible", "Fichier .DS_Store public (liste tes dossiers)", lambda r: r.body.startswith(b"\x00\x00\x00\x01Bud1")),
    ("/package.json", "faible", "package.json public (liste tes bibliothèques)",
     lambda r: b'"dependencies"' in r.body or b'"devDependencies"' in r.body),
    ("/composer.json", "faible", "composer.json public", lambda r: b'"require"' in r.body),
    ("/uploads/", "moyenne", "Liste des fichiers visible (/uploads/)", lambda r: b"Index of /" in r.body[:3000]),
    ("/files/", "moyenne", "Liste des fichiers visible (/files/)", lambda r: b"Index of /" in r.body[:3000]),
    ("/backup/", "moyenne", "Liste des fichiers visible (/backup/)", lambda r: b"Index of /" in r.body[:3000]),
    ("/assets/", "faible", "Liste des fichiers visible (/assets/)", lambda r: b"Index of /" in r.body[:3000]),
]
_FIX_PRIVATE = "Retire ce fichier du site public (ou bloque l'accès) et change les mots de passe et clés qu'il contient."

SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "clé AWS"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "clé privée"),
    (re.compile(r"\bsk_live_[0-9A-Za-z]{16,}"), "clé secrète Stripe"),
    (re.compile(r"\bgh[pousr]_[0-9A-Za-z]{30,}"), "jeton GitHub"),
    (re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}"), "jeton Slack"),
    (re.compile(r"\bsk-(?:ant-|proj-)?[0-9A-Za-z_-]{32,}"), "clé d'IA (OpenAI/Anthropic…)"),
    (re.compile(r"\b[0-9]{8,10}:[A-Za-z0-9_-]{35}\b"), "jeton de bot Telegram"),
    (re.compile(r"(?i)\b(?:api[_-]?key|secret|password|passwd)[\"']?\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"), "secret écrit dans le code"),
]
VULN_LIBS = [  # (nom, regex de version, test « trop ancien », conseil)
    ("jQuery", re.compile(r"jquery[-./@]v?(\d+)\.(\d+)\.(\d+)", re.I), lambda v: v < (3, 5, 0),
     "faille XSS connue avant la 3.5.0 (CVE-2020-11022)", "Passe à jQuery 3.7 ou plus."),
    ("Bootstrap", re.compile(r"bootstrap[-./@]v?(\d+)\.(\d+)\.(\d+)", re.I), lambda v: v < (3, 4, 1) or (4, 0, 0) <= v < (4, 3, 1),
     "failles XSS connues (avant 3.4.1 / 4.3.1)", "Passe à Bootstrap 5."),
    ("AngularJS", re.compile(r"angular(?:js)?[-./@]v?(1)\.(\d+)\.(\d+)", re.I), lambda v: True,
     "AngularJS 1.x n'est plus maintenu (plus aucun correctif de sécurité)", "Migre vers une version récente."),
    ("lodash", re.compile(r"lodash[-./@]v?(\d+)\.(\d+)\.(\d+)", re.I), lambda v: v < (4, 17, 21),
     "pollution de prototype avant la 4.17.21", "Passe à lodash 4.17.21 ou plus."),
]


def check_page(url: str, html: str, https: bool = True) -> list[dict]:
    """Contrôles sur le code d'une page."""
    out = []
    path = urlparse(url).path or "/"
    if https:
        # ressources chargées (src, action) ou feuilles de style : pas les simples liens <a href>
        mixed = re.findall(r"""(?:\bsrc|\baction)\s*=\s*["']http://[^"']+""", html, re.I)
        mixed += re.findall(r"""<link\b[^>]*\bhref\s*=\s*["']http://[^"']+""", html, re.I)
        if mixed:
            out.append(F("moyenne", "Contenu mixte (http dans une page https)",
                         f"{len(mixed)} ressource(s) chargée(s) sans chiffrement, par exemple « {mixed[0][-70:]} ».",
                         "Remplace http:// par https:// pour ces adresses.", path))
    for form in re.findall(r"<form\b[^>]*>.*?</form>", html, re.I | re.S):
        tag = re.match(r"<form\b[^>]*>", form, re.I).group(0)
        has_pw = re.search(r"type\s*=\s*[\"']?password", form, re.I) is not None
        action = re.search(r"action\s*=\s*[\"']([^\"']*)", tag, re.I)
        if has_pw and action and action.group(1).lower().startswith("http://"):
            out.append(F("haute", "Mot de passe envoyé sans chiffrement", "Un formulaire de mot de passe envoie vers http://.",
                         "Utilise https:// pour l'action du formulaire.", path))
        if re.search(r"method\s*=\s*[\"']?post", tag, re.I) and not re.search(
                r"name\s*=\s*[\"'][^\"']*(csrf|token|nonce|authenticity)", form, re.I):
            out.append(F("faible", "Formulaire sans jeton anti-CSRF visible (à vérifier)",
                         "Aucun jeton caché n'est visible dans ce formulaire. Si ton site protège autrement (cookies SameSite), c'est bon.",
                         "Ajoute un jeton anti-CSRF aux formulaires qui modifient des données.", path))
    ext = [t for t in re.findall(r"<script\b[^>]*\bsrc\s*=\s*[\"']https?://[^\"']+[\"'][^>]*>", html, re.I)
           if not re.search(r"integrity\s*=", t, re.I)]
    if ext:
        out.append(F("faible", "Script externe sans contrôle d'intégrité (SRI)",
                     f"{len(ext)} script(s) venant d'ailleurs sont chargés sans empreinte : si ce service est piraté, ton site l'est aussi.",
                     "Ajoute l'attribut integrity=… et crossorigin à ces balises <script>.", path))
    for name, rx, old, why, fix in VULN_LIBS:
        m = rx.search(html)
        if m and old(tuple(int(x) for x in m.groups())):
            out.append(F("moyenne", f"{name} ancien : {m.group(0)[:40]}", why.capitalize() + ".", fix, path))
    return out


def check_secrets(where: str, text: str) -> list[dict]:
    out = []
    for rx, label in SECRET_PATTERNS:
        m = rx.search(text)
        if m:
            masked = m.group(0)[:4] + "…" + f" ({len(m.group(0))} caractères)"
            out.append(F("haute", f"Secret visible dans le code : {label}",
                         f"Un {label} est lisible par tous les visiteurs ({masked}).",
                         "Retire-le du code public, puis REVOQUE-le et crée-en un nouveau chez le service concerné.", where))
    return out


def _links(base_url: str, html: str, hosts: set[str]) -> list[str]:
    seen, out = set(), []
    for m in re.finditer(r"""(?:href|src)\s*=\s*["']([^"'#]+)""", html, re.I):
        u = urljoin(base_url, m.group(1).strip())
        p = urlparse(u)
        if p.scheme not in ("http", "https") or (p.hostname or "").lower() not in hosts:
            continue
        u = p._replace(fragment="", query="").geturl()
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def score(findings: list[dict]) -> int:
    pts = {"haute": 20, "moyenne": 8, "faible": 2, "info": 0}
    return max(0, 100 - sum(pts[f["sev"]] for f in findings))


# --------------------------------------------------------------------------- le scan
def scan(domain: str, fetcher=None, budget: float = TIME_BUDGET) -> dict:
    f = fetcher or Fetcher(domain)
    start = time.monotonic()
    findings: list[dict] = []
    pages = 0
    partial = False

    def left() -> bool:
        return time.monotonic() - start < budget

    home_url = f"https://{domain}/"
    home = f.get(home_url)
    # www ? (certains sites n'ont que www)
    if home.error == "net" or (home.status in (301, 302, 307, 308) and "www." in home.h("location")):
        alt = f.get(f"https://www.{domain}/")
        if alt.status and not alt.error:
            home_url, home = f"https://www.{domain}/", alt
    for _ in range(3):  # redirections vers le même site
        if home.status in (301, 302, 303, 307, 308) and home.h("location"):
            nxt = urljoin(home_url, home.h("location"))
            if (urlparse(nxt).hostname or "") in f.hosts and urlparse(nxt).scheme == "https":
                home_url, home = nxt, f.get(nxt)
                continue
        break
    if home.error == "cert":
        findings.append(F("haute", "Certificat HTTPS invalide", f"Les navigateurs afficheront un avertissement ({home.detail}).",
                          "Renouvelle ou corrige le certificat (Let's Encrypt est gratuit)."))
    elif home.error:
        findings.append(F("haute", "Le site ne répond pas en HTTPS", "Impossible d'ouvrir la page d'accueil en HTTPS.",
                          "Active HTTPS sur ton site."))
    else:
        pages += 1
        if home.cert_days is not None:
            if home.cert_days < 0:
                findings.append(F("haute", "Certificat HTTPS expiré", f"Il a expiré il y a {-home.cert_days} jours.", "Renouvelle-le."))
            elif home.cert_days < 15:
                findings.append(F("moyenne", "Certificat HTTPS bientôt expiré", f"Il expire dans {home.cert_days} jours.",
                                  "Vérifie le renouvellement automatique."))
        if home.tls and home.tls < "TLSv1.2":
            findings.append(F("moyenne", "Version de TLS ancienne", f"Le site accepte {home.tls}.", "Exige TLS 1.2 ou plus."))
        findings += check_headers(home) + check_cookies(home)
        # http → https ?
        plain = f.get(f"http://{domain}/")
        loc = plain.h("location")
        if plain.status and not plain.error and not (plain.status in (301, 302, 307, 308) and loc.startswith("https://")):
            findings.append(F("moyenne", "Le site reste accessible sans chiffrement (http)",
                              "La version http:// n'est pas redirigée vers https://.", "Redirige tout le trafic http vers https."))

    # fichiers sensibles et listes de dossiers, en parallèle
    base_url = home_url if home.status and not home.error else f"https://{domain}/"
    if left():
        def probe(p):
            path, sev, title, ok = p
            r = f.get(urljoin(base_url, path), 60_000)
            return (p, r) if r.status == 200 and not r.error and ok(r) else None
        with ThreadPoolExecutor(max_workers=6) as pool:
            for hit in pool.map(probe, PROBES):
                if hit:
                    (path, sev, title, _), _r = hit
                    findings.append(F(sev, title, f"Accessible à {path} pour tout le monde.", _FIX_PRIVATE, path))
        sec = f.get(urljoin(base_url, "/.well-known/security.txt"), 5000)
        if sec.status != 200 or sec.error:
            findings.append(F("info", "Pas de security.txt", "Personne ne sait comment te signaler une faille.",
                              "Ajoute /.well-known/security.txt avec un contact (securitytxt.org)."))

    # petite exploration : pages et scripts du même site
    if home.status == 200 and not home.error and left():
        html = _text(home)
        findings += check_page(home_url, html)
        findings += check_secrets("/", html)
        todo = [u for u in _links(home_url, html, f.hosts) if not re.search(r"\.(png|jpe?g|gif|svg|webp|ico|woff2?|ttf|mp4|pdf|css)$", u, re.I)]
        scripts = [u for u in todo if u.endswith(".js")][:MAX_SCRIPTS]
        pages_to_visit = [u for u in todo if not u.endswith(".js")][:MAX_PAGES - 1]
        sm = f.get(urljoin(base_url, "/sitemap.xml"), 100_000)
        if sm.status == 200 and b"<loc>" in sm.body:
            extra = [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", _text(sm)) if (urlparse(u).hostname or "") in f.hosts]
            pages_to_visit = list(dict.fromkeys(pages_to_visit + extra))[:MAX_PAGES - 1]

        def visit(u):
            r = f.get(u, 250_000)
            ctype = r.h("content-type").lower()
            return u, r, ctype

        with ThreadPoolExecutor(max_workers=6) as pool:
            for u, r, ctype in pool.map(visit, pages_to_visit if left() else []):
                if r.status == 200 and not r.error and "html" in ctype:
                    pages += 1
                    t = _text(r)
                    findings += check_page(u, t) + check_secrets(urlparse(u).path or "/", t)
                    scripts += [s for s in _links(u, t, f.hosts) if s.endswith(".js") and s not in scripts]
            scripts = list(dict.fromkeys(scripts))[:MAX_SCRIPTS]
            for u, r, _ in pool.map(visit, scripts if left() else []):
                if r.status == 200 and not r.error:
                    t = _text(r)
                    findings += check_secrets(urlparse(u).path or u, t)
                    for name, rx, old, why, fix in VULN_LIBS:
                        m = rx.search(u) or rx.search(t[:600])
                        if m and old(tuple(int(x) for x in m.groups())):
                            findings.append(F("moyenne", f"{name} ancien : {m.group(0)[:40]}", why.capitalize() + ".", fix,
                                              urlparse(u).path))
    if not left():
        partial = True
    # sans doublons, du plus grave au moins grave
    uniq, seen = [], set()
    for x in findings:
        k = (x["title"], x["where"])
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    uniq.sort(key=lambda x: SEV_ORDER[x["sev"]])
    counts = {s: sum(1 for x in uniq if x["sev"] == s) for s in SEV_ORDER}
    return {"domain": domain, "at": int(time.time()), "pages": pages, "requests": f.count, "partial": partial,
            "seconds": round(time.monotonic() - start, 1), "score": score(uniq), "counts": counts, "findings": uniq[:60]}


# --------------------------------------------------------------------------- orchestration
def run(base, raw: str, own_hosts: tuple = (), fetcher=None, now: float | None = None) -> dict:
    """Vérifie la propriété, applique la limite de fréquence, scanne, garde le dernier résultat."""
    dom = clean_domain(raw)
    own = dom in {clean_domain(h) for h in own_hosts if h}
    data = _load(base)
    entry = data.get(dom)
    if not own and not entry:
        raise ScanError("Ajoute d'abord ce site à ta liste et prouve qu'il est à toi.")
    t = now if now is not None else time.time()
    last = (entry or {}).get("last") or {}
    if last and t - last.get("at", 0) < MIN_DELAY:
        raise ScanError("Un scan de ce site vient d'avoir lieu : attends 2 minutes.")
    f = fetcher or Fetcher(dom)
    if not own and not verify(dom, entry["token"], f):
        raise ScanError("Preuve de propriété introuvable sur ce site. " + instructions(dom, entry["token"]))
    result = scan(dom, f)
    result["at"] = int(t)
    entry = data.setdefault(dom, {"token": "", "added": int(t), "own": True})
    entry["last"] = {k: result[k] for k in ("at", "pages", "requests", "partial", "seconds", "score", "counts", "findings")}
    entry["history"] = [*entry.get("history", []), {"at": int(t), "score": result["score"], "counts": result["counts"]}][-12:]
    _save(base, data)
    return result


def ensure_access(base, raw: str, fetcher=None):
    """Site ajouté par le propriétaire ET preuve de propriété retrouvée sur le site : renvoie (domaine, accès)."""
    dom = clean_domain(raw)
    entry = _load(base).get(dom)
    if not entry or not entry.get("token"):
        raise ScanError("Ajoute d'abord ce site dans Syrius Code (onglet Sites) et prouve qu'il est à toi.")
    f = fetcher or Fetcher(dom)
    if not verify(dom, entry["token"], f):
        raise ScanError("Preuve de propriété introuvable sur ce site. " + instructions(dom, entry["token"]))
    return dom, f


def chat_summary(res: dict) -> str:
    """Résumé court pour l'IA (qui le reformule pour l'utilisateur)."""
    c = res["counts"]
    lines = [f"Scan de {res['domain']} : note {res['score']}/100, {res['pages']} page(s) vues, "
             f"{c['haute']} grave(s), {c['moyenne']} moyen(s), {c['faible']} léger(s)."
             + (" (scan partiel : trop long)" if res.get("partial") else "")]
    for x in res["findings"][:12]:
        lines.append(f"- [{x['sev']}] {x['title']} — {x['fix']}")
    lines.append("Scan passif : il ne remplace pas un test d'intrusion complet.")
    return "\n".join(lines)
