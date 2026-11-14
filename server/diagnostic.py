"""Diagnostic des services (bouton « Tester les services », propriétaire uniquement).

Vérifie depuis le serveur, en direct : création d'images, IA qui voient (petite image de test),
bibliothèque 3D et création 3D. Aucune clé n'est jamais affichée : seulement « OK » ou l'erreur.
"""
from __future__ import annotations

import base64
import json
import re
import struct
import time
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor

from .tools import imagegen, real3d


def _png(w: int = 32, h: int = 32, rgb=(220, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _clean(msg: str) -> str:
    msg = re.sub(r"(sk|hf|pk|gsk|AIza)[\w-]{8,}", "•••", str(msg))  # jamais de clé dans le rapport
    return " ".join(msg.split())[:160]


def _timed(name: str, fn) -> dict:
    t = time.time()
    try:
        detail = fn() or "OK"
        return {"name": name, "ok": True, "detail": _clean(detail), "s": round(time.time() - t, 1)}
    except Exception as e:  # noqa: BLE001 — on rapporte toute erreur
        return {"name": name, "ok": False, "detail": _clean(e) or type(e).__name__, "s": round(time.time() - t, 1)}


def _vision(provider) -> str:
    img = "data:image/png;base64," + base64.b64encode(_png()).decode()
    body = {"model": provider.model, "max_tokens": 30, "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Quelle est la couleur de cette image ? Un seul mot."},
        {"type": "image_url", "image_url": {"url": img}}]}]}
    req = urllib.request.Request(provider.base_url + "/chat/completions", data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "User-Agent": "Syrius/1.0",
        **({"Authorization": f"Bearer {provider.api_key}"} if provider.api_key else {})}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:  # nosec B310 (hôtes des cerveaux configurés)
            data = json.loads(r.read(200_000))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {e.read(300).decode('utf-8', 'replace')}") from None
    text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("réponse vide")
    return "répond : " + text[:40]


def _image_source(src) -> str:
    ctype, data = src("a red apple on a table", 1234)
    return f"image reçue ({len(data) // 1024} Ko)"


def _hf_whoami(token: str) -> str:
    req = urllib.request.Request("https://huggingface.co/api/whoami-v2", headers={
        "Authorization": f"Bearer {token}", "User-Agent": "Syrius/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # nosec B310
            d = json.loads(r.read(100_000))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"clé HF_TOKEN refusée (HTTP {e.code})") from None
    return f"clé valide (compte {'PRO' if d.get('isPro') else 'gratuit'} : quota GPU limité par jour)"


def run(cfg, providers) -> list[dict]:
    checks = []
    names = {imagegen._pollinations_key: "Images · Pollinations (clé)", imagegen._pollinations: "Images · Pollinations",
             imagegen._huggingface: "Images · Hugging Face FLUX"}
    for src in imagegen.sources():
        checks.append((names.get(src, "Images"), lambda s=src: _image_source(s)))
    for p in providers:
        if p.vision:
            checks.append((f"Photos · {p.label}", lambda p=p: _vision(p)))
    if not any(p.vision for p in providers):
        checks.append(("Photos", lambda: (_ for _ in ()).throw(RuntimeError("aucune IA qui voit n'est configurée"))))
    if cfg.polypizza_api_key:
        checks.append(("3D · bibliothèque Poly Pizza",
                       lambda: f"{len(real3d.poly_search(cfg.polypizza_api_key, 'car'))} modèles trouvés pour « car »"))
    else:
        checks.append(("3D · bibliothèque Poly Pizza", lambda: (_ for _ in ()).throw(RuntimeError("clé POLYPIZZA_API_KEY absente"))))
    if cfg.hf_token:
        checks.append(("3D · clé Hugging Face", lambda: _hf_whoami(cfg.hf_token)))
        checks.append(("3D · service TRELLIS.2", lambda: f"en ligne (fonction n°{real3d._fn_index(cfg.hf_token, 'image_to_3d')})"))
    else:
        checks.append(("3D · création sur mesure", lambda: (_ for _ in ()).throw(RuntimeError("clé HF_TOKEN absente"))))
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda c: _timed(*c), checks))
