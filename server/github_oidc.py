"""Reconnaître les automatisations GitHub de TON dépôt, sans aucun secret à copier.

GitHub Actions peut fournir un « jeton d'identité » (OIDC) signé par GitHub. Ton Syrius vérifie :
- la signature (RS256, clés publiques officielles de GitHub, téléchargées en HTTPS) ;
- l'émetteur, le destinataire (« syrius »), les dates de validité ;
- que le dépôt est bien le tien, sur la branche principale, et que c'est l'une des automatisations autorisées
  (entraînement, Améliorer Syrius).
Bibliothèque standard uniquement (vérification RSA PKCS#1 v1.5 écrite ici, avec comparaison en temps constant).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
import urllib.request

ISSUER = "https://token.actions.githubusercontent.com"
JWKS_URL = ISSUER + "/.well-known/jwks"
AUDIENCE = "syrius"
WORKFLOWS = ("train-syrius.yml", "selfcode.yml", "convert-syrius.yml")
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
_cache: dict = {"keys": {}, "at": 0.0}


def _b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _jwks() -> dict:
    if time.time() - _cache["at"] > 3600 or not _cache["keys"]:
        req = urllib.request.Request(JWKS_URL, headers={"User-Agent": "Syrius/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:  # nosec B310 (adresse officielle fixe)
            data = json.loads(r.read(200_000))
        _cache["keys"] = {k["kid"]: k for k in data.get("keys", []) if k.get("kty") == "RSA" and k.get("kid")}
        _cache["at"] = time.time()
    return _cache["keys"]


def _rsa_verify(key: dict, signed: bytes, sig: bytes) -> bool:
    n = int.from_bytes(_b64(key["n"]), "big")
    e = int.from_bytes(_b64(key["e"]), "big")
    k = (n.bit_length() + 7) // 8
    if len(sig) != k or n.bit_length() < 2048:
        return False
    em = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    digest = _SHA256_PREFIX + hashlib.sha256(signed).digest()
    expected = b"\x00\x01" + b"\xff" * (k - len(digest) - 3) + b"\x00" + digest
    return hmac.compare_digest(em, expected)


def verify(token: str, repository: str, keys: dict | None = None, now: float | None = None) -> dict | None:
    """Renvoie les informations du jeton s'il vient bien d'une automatisation autorisée de `repository`."""
    try:
        head_b64, body_b64, sig_b64 = token.split(".")
        header = json.loads(_b64(head_b64))
        claims = json.loads(_b64(body_b64))
        sig = _b64(sig_b64)
    except (ValueError, TypeError):
        return None
    if header.get("alg") != "RS256" or not isinstance(claims, dict):
        return None
    try:
        key = (keys if keys is not None else _jwks()).get(header.get("kid"))
    except Exception:  # noqa: BLE001 — GitHub injoignable : refusé
        return None
    if not key or not _rsa_verify(key, f"{head_b64}.{body_b64}".encode(), sig):
        return None
    t = now if now is not None else time.time()
    aud = claims.get("aud")
    if claims.get("iss") != ISSUER or (aud != AUDIENCE and not (isinstance(aud, list) and AUDIENCE in aud)):
        return None
    if not (claims.get("nbf", 0) - 60 <= t <= claims.get("exp", 0) + 60):
        return None
    if claims.get("repository") != repository or claims.get("ref") != "refs/heads/main":
        return None
    wf = str(claims.get("job_workflow_ref", ""))
    m = re.fullmatch(re.escape(repository) + r"/\.github/workflows/([\w.-]+)@refs/heads/main", wf)
    if not m or m.group(1) not in WORKFLOWS or claims.get("event_name") in ("pull_request", "pull_request_target"):
        return None
    return claims
