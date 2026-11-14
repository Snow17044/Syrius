"""Création d'images EN LIGNE (gratuite, sans clé) : le serveur relaie la demande à Pollinations.

Même capacité que le générateur hors ligne du téléphone, mais bien plus rapide (quelques secondes).
Sécurité : un seul hôte possible (codé en dur), connexion épinglée sur une IP publique, description
nettoyée et limitée, réponse acceptée uniquement si c'est une vraie image JPEG/PNG/WebP de taille limitée.
L'adresse du téléphone n'est jamais transmise au service (c'est le serveur qui fait la demande).
"""
from __future__ import annotations

import http.client
import json
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


KEYS = {"pollinations": "", "hf": ""}  # renseignées au démarrage (variables Vercel), jamais envoyées ailleurs
HF_HOST = "router.huggingface.co"
HF_PATH = "/hf-inference/models/black-forest-labs/FLUX.1-schnell"
GEN_HOST = "gen.pollinations.ai"


def configure(cfg) -> None:
    KEYS["pollinations"] = getattr(cfg, "pollinations_api_key", "") or ""
    KEYS["hf"] = getattr(cfg, "hf_token", "") or ""


def _fetch(host: str, method: str, path: str, headers: dict, body: bytes | None = None) -> tuple[int, str, bytes]:
    try:
        ip = web.resolve_public(host, 443)
    except web.WebError as e:
        raise ImageGenError(str(e)) from None
    conn = web._PinnedHTTPS(host, ip, 443, TIMEOUT)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.getheader("content-type", ""), resp.read(MAX_BYTES + 1)
    except (OSError, http.client.HTTPException, ssl.SSLError):
        raise ImageGenError("le service d'images n'a pas répondu") from None
    finally:
        conn.close()


def _status_error(name: str, status: int) -> ImageGenError:
    if status == 429:
        return ImageGenError(f"{name} : service saturé, réessaie dans une minute")
    if status in (401, 402, 403):
        return ImageGenError(f"{name} : accès refusé ({status})")
    return ImageGenError(f"{name} : service indisponible ({status})")


def _pollinations(prompt: str, seed: int) -> tuple[str, bytes]:
    status, ctype, body = _fetch(HOST, "GET", build_path(prompt, seed), HEADERS)
    if status != 200:
        raise _status_error("Pollinations", status)
    return check_image(ctype, body), body


def _pollinations_key(prompt: str, seed: int) -> tuple[str, bytes]:
    path = build_path(prompt, seed).replace("/prompt/", "/image/", 1)
    status, ctype, body = _fetch(GEN_HOST, "GET", path, {**HEADERS, "Authorization": f"Bearer {KEYS['pollinations']}"})
    if status != 200:
        raise _status_error("Pollinations (clé)", status)
    return check_image(ctype, body), body


def _huggingface(prompt: str, seed: int) -> tuple[str, bytes]:
    payload = json.dumps({"inputs": clean_prompt(prompt),
                          "parameters": {"width": SIZE, "height": SIZE, "num_inference_steps": 4, "seed": seed}})
    status, ctype, body = _fetch(HF_HOST, "POST", HF_PATH, {
        **HEADERS, "Accept": "image/jpeg", "Content-Type": "application/json",
        "Authorization": f"Bearer {KEYS['hf']}"}, payload.encode())
    if status != 200:
        raise _status_error("Hugging Face", status)
    return check_image(ctype, body), body


def sources() -> list:
    out = []
    if KEYS["pollinations"]:
        out.append(_pollinations_key)
    out.append(_pollinations)
    if KEYS["hf"]:
        out.append(_huggingface)
    return out


def generate(prompt: str, seed: int | None = None) -> tuple[str, bytes]:
    """Renvoie (type, octets de l'image). Plusieurs services gratuits essayés tour à tour."""
    seed = random.randrange(2**31) if seed is None else seed
    clean_prompt(prompt)
    errors = []
    for src in sources():
        try:
            return src(prompt, seed)
        except ImageGenError as e:
            errors.append(str(e))
    raise ImageGenError(" ; ".join(errors) or "aucun service d'images disponible")
