"""Création d'images EN LIGNE (gratuite, sans clé) : le serveur relaie la demande à Pollinations.

Même capacité que le générateur hors ligne du téléphone, mais bien plus rapide (quelques secondes).
Sécurité : un seul hôte possible (codé en dur), connexion épinglée sur une IP publique, description
nettoyée et limitée, réponse acceptée uniquement si c'est une vraie image JPEG/PNG/WebP de taille limitée.
L'adresse du téléphone n'est jamais transmise au service (c'est le serveur qui fait la demande).
"""
from __future__ import annotations

import base64
import http.client
import json
import random
import re
import ssl
import time
from urllib.parse import quote, urlsplit

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
HF_PATH = "/fal-ai/fal-ai/flux/schnell"  # FLUX.1 schnell via Hugging Face (fournisseur fal-ai)
GEN_HOST = "gen.pollinations.ai"
HORDE_HOST = "aihorde.net"  # AI Horde : réseau collaboratif gratuit, sans compte
HORDE_WAIT = 100  # secondes au plus dans la file d'attente
_DATA_IMG = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")


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


def _download(url: str, allowed: tuple, name: str) -> tuple[str, bytes]:
    """Télécharge l'image finale (https, hôte attendu uniquement)."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https" or not any(host == h or host.endswith("." + h) for h in allowed):
        raise ImageGenError(f"{name} : adresse d'image inattendue")
    status, ctype, body = _fetch(host, "GET", (parts.path or "/") + (f"?{parts.query}" if parts.query else ""),
                                 {**HEADERS, "Accept": "image/*"})
    if status != 200:
        raise _status_error(name, status)
    return check_image(ctype or "image/webp", body), body


def _json(name: str, status: int, body: bytes) -> dict:
    if status not in (200, 201, 202):
        raise _status_error(name, status)
    try:
        data = json.loads(body)
    except ValueError:
        raise ImageGenError(f"{name} : réponse illisible") from None
    if not isinstance(data, dict):
        raise ImageGenError(f"{name} : réponse illisible")
    return data


def _huggingface(prompt: str, seed: int) -> tuple[str, bytes]:
    payload = json.dumps({"prompt": clean_prompt(prompt), "image_size": {"width": SIZE, "height": SIZE},
                          "num_inference_steps": 4, "seed": seed, "sync_mode": True, "enable_safety_checker": True})
    status, _, body = _fetch(HF_HOST, "POST", HF_PATH, {
        **HEADERS, "Accept": "application/json", "Content-Type": "application/json",
        "Authorization": f"Bearer {KEYS['hf']}"}, payload.encode())
    data = _json("Hugging Face", status, body)
    images = data.get("images") or []
    url = images[0].get("url", "") if images and isinstance(images[0], dict) else ""
    m = _DATA_IMG.match(url or "")
    if m:
        raw = base64.b64decode(m.group(2))
        return check_image(m.group(1), raw), raw
    return _download(url, ("fal.media", "fal.run"), "Hugging Face")


def _horde(prompt: str, seed: int) -> tuple[str, bytes]:
    head = {**HEADERS, "Accept": "application/json", "Content-Type": "application/json",
            "apikey": "0000000000", "Client-Agent": "Syrius:1.0:anonymous"}
    payload = {"prompt": clean_prompt(prompt) + " ### blurry, deformed, text, watermark",
               "params": {"width": 512, "height": 512, "steps": 20, "n": 1, "seed": str(seed),
                          "sampler_name": "k_euler_a", "cfg_scale": 7},
               "models": ["AbsoluteReality", "Deliberate", "stable_diffusion"],
               "nsfw": False, "censor_nsfw": True, "r2": True, "shared": False, "trusted_workers": False}
    status, _, body = _fetch(HORDE_HOST, "POST", "/api/v2/generate/async", head, json.dumps(payload).encode())
    job = str(_json("AI Horde", status, body).get("id") or "")
    if not re.fullmatch(r"[0-9a-f-]{8,64}", job):
        raise ImageGenError("AI Horde : demande refusée")
    end = time.time() + HORDE_WAIT
    while True:
        time.sleep(2)
        status, _, body = _fetch(HORDE_HOST, "GET", f"/api/v2/generate/check/{job}", head)
        check = _json("AI Horde", status, body)
        if check.get("done"):
            break
        if check.get("faulted") or not check.get("is_possible", True):
            raise ImageGenError("AI Horde : création impossible")
        if time.time() > end:
            _fetch(HORDE_HOST, "DELETE", f"/api/v2/generate/status/{job}", head)
            raise ImageGenError("AI Horde : file d'attente trop longue")
    status, _, body = _fetch(HORDE_HOST, "GET", f"/api/v2/generate/status/{job}", head)
    gens = _json("AI Horde", status, body).get("generations") or []
    if not gens or not isinstance(gens[0], dict) or gens[0].get("censored"):
        raise ImageGenError("AI Horde : image refusée")
    img = str(gens[0].get("img") or "")
    if not img.startswith("https://"):
        try:
            raw = base64.b64decode(img, validate=True)
        except ValueError:
            raise ImageGenError("AI Horde : image illisible") from None
        return check_image("image/webp", raw), raw
    return _download(img, ("r2.cloudflarestorage.com", "aihorde.net"), "AI Horde")


def sources() -> list:
    out = []
    if KEYS["pollinations"]:
        out.append(_pollinations_key)
    out.append(_pollinations)
    if KEYS["hf"]:
        out.append(_huggingface)
    out.append(_horde)  # gratuit et sans clé, un peu plus lent (file d'attente)
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
