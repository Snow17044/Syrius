"""Identité GitHub (OIDC) : seule une automatisation autorisée de TON dépôt est acceptée."""
import base64
import hashlib
import json
import random

from fastapi.testclient import TestClient

from server import github_oidc
from tests.conftest import H, login

REPO = "Snow17044/Syrius"


def _prime(bits, rng):
    while True:
        p = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if all(pow(a, p - 1, p) == 1 for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)):
            return p


def _key():
    rng = random.Random(42)
    e = 65537
    while True:
        p, q = _prime(1024, rng), _prime(1024, rng)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            n = p * q
            return n, e, pow(e, -1, phi)


N, E, D = _key()
B64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
KEYS = {"k1": {"kty": "RSA", "kid": "k1", "n": B64(N.to_bytes(256, "big")), "e": B64(E.to_bytes(3, "big"))}}


def token(**over):
    claims = {"iss": github_oidc.ISSUER, "aud": "syrius", "nbf": 1000, "exp": 2000, "repository": REPO,
              "ref": "refs/heads/main", "event_name": "schedule",
              "job_workflow_ref": f"{REPO}/.github/workflows/train-syrius.yml@refs/heads/main", **over}
    head = B64(json.dumps({"alg": "RS256", "kid": "k1"}).encode())
    body = B64(json.dumps(claims).encode())
    digest = github_oidc._SHA256_PREFIX + hashlib.sha256(f"{head}.{body}".encode()).digest()
    em = b"\x00\x01" + b"\xff" * (256 - len(digest) - 3) + b"\x00" + digest
    sig = pow(int.from_bytes(em, "big"), D, N).to_bytes(256, "big")
    return f"{head}.{body}.{B64(sig)}"


def test_jeton_valide_et_refus():
    ok = lambda t: github_oidc.verify(t, REPO, keys=KEYS, now=1500) is not None  # noqa: E731
    assert ok(token())
    assert ok(token(job_workflow_ref=f"{REPO}/.github/workflows/selfcode.yml@refs/heads/main"))
    assert not ok(token(repository="pirate/Syrius"))  # autre dépôt
    assert not ok(token(ref="refs/heads/dev"))  # autre branche
    assert not ok(token(job_workflow_ref=f"{REPO}/.github/workflows/android.yml@refs/heads/main"))  # autre automatisation
    assert not ok(token(event_name="pull_request"))
    assert not ok(token(aud="autre"))
    assert not ok(token(exp=1100))  # expiré
    t = token()
    head, body, sig = t.split(".")
    forged = json.loads(base64.urlsafe_b64decode(body + "=="))
    forged["repository"] = REPO
    forged["ref"] = "refs/heads/dev"
    assert not ok(f"{head}.{B64(json.dumps(forged).encode())}.{sig}")  # contenu modifié : signature invalide
    assert not ok("pas.un.jeton")


def test_route_accepte_l_identite_github(make_client, monkeypatch):
    owner = make_client()
    login(owner)
    monkeypatch.setattr(github_oidc, "_jwks", lambda: KEYS)
    monkeypatch.setattr(github_oidc.time, "time", lambda: 1500)
    worker = TestClient(owner.app, base_url="https://testserver")
    W = {**H, "Authorization": f"Bearer {token()}"}
    assert worker.get("/api/training/worker/should-train", headers=W).status_code == 200
    bad = {**H, "Authorization": f"Bearer {token(repository='pirate/Syrius')}"}
    assert worker.get("/api/training/worker/should-train", headers=bad).status_code == 401
    assert worker.get("/api/conversations", headers=W).status_code == 401  # ne donne accès à rien d'autre
