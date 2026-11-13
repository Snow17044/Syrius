"""Création d'images EN LIGNE (gratuite, sans clé) : le serveur relaie la demande à Pollinations.

Même capacité que le générateur hors ligne du téléphone, mais bien plus rapide (quelques secondes).
Sécurité : un seul hôte possible (codé en dur), connexion épinglée sur une IP publique, description
nettoyée et limitée, réponse acceptée uniquement si c'est une vraie image JPEG/PNG/WebP de taille limitée.
L'adresse du téléphone n'est jamais transmise au service (c'est le serveur qui fait la demande).
"""
from __future__ import annotations

import http.client
import random
import re
import ssl
from urllib.parse import quote

from . import web

HOST = "image.pollinations.ai"
TIMEOUT = 60
MAX_BYTES = 4_000_000
MAX_PROMPT = 400
SIZE = 768
HEADERS = {
    "User-Agent": "SyriusAssistant/1.0 (assistant personnel)",
    "Accept": "image/jpeg,image/png,image/webp",
    "Connection": "close",
}
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_MAGIC = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "image/webp": b"RIFF"}


class ImageGenError(Exception):
    pass


def clean_prompt(prompt) -> str:
    if not isinstance(prompt, str):
        raise ImageGenError("description invalide")
    p = " ".join(_CTRL.sub(" ", prompt).split())
    if len(p) < 3:
        raise ImageGenError("description trop courte")
    return p[:MAX_PROMPT]


def build_path(prompt: str, seed: int) -> str:
    if not (0 <= seed < 2**31):
        raise ImageGenError("graine invalide")
    return (f"/prompt/{quote(clean_prompt(prompt), safe='')}"
            f"?width={SIZE}&height={SIZE}&seed={seed}&nologo=true&private=true&safe=true")


def check_image(ctype: str, body: bytes) -> str:
    ctype = ctype.split(";")[0].strip().lower()
    magic = _MAGIC.get(ctype)
    if not magic or not body.startswith(magic) or len(body) > MAX_BYTES or len(body) < 1000:
        raise ImageGenError("le service n'a pas renvoyé d'image valide")
    if ctype == "image/webp" and body[8:12] != b"WEBP":
        raise ImageGenError("le service n'a pas renvoyé d'image valide")
    return ctype


def generate(prompt: str, seed: int | None = None) -> tuple[str, bytes]:
    """Renvoie (type, octets de l'image)."""
    path = build_path(prompt, random.randrange(2**31) if seed is None else seed)
    try:
        ip = web.resolve_public(HOST, 443)
    except web.WebError as e:
        raise ImageGenError(str(e)) from None
    conn = web._PinnedHTTPS(HOST, ip, 443, TIMEOUT)
    try:
        conn.request("GET", path, headers=HEADERS)
        resp = conn.getresponse()
        ctype = resp.getheader("content-type", "")
        body = resp.read(MAX_BYTES + 1)
        status = resp.status
    except (OSError, http.client.HTTPException, ssl.SSLError):
        raise ImageGenError("le service d'images n'a pas répondu") from None
    finally:
        conn.close()
    if status == 429:
        raise ImageGenError("service d'images saturé, réessaie dans une minute")
    if status != 200:
        raise ImageGenError(f"service d'images indisponible ({status})")
    return check_image(ctype, body), body
