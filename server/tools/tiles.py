"""Fond de carte : les tuiles OpenStreetMap passent par notre serveur.

Pourquoi : l'application (WebView Android) n'envoie pas les en-têtes que le serveur de
tuiles exige, et cela évite aussi de transmettre l'adresse du téléphone à un tiers.
Sécurité : un seul hôte possible (codé en dur), coordonnées entières vérifiées,
connexion épinglée sur une IP publique, uniquement des images PNG de taille limitée.
"""
from __future__ import annotations

import json
import re
import time
import zlib
from urllib.parse import quote

from . import web

HOST = "tile.openstreetmap.org"
MAX_ZOOM = 19
MAX_TILE_BYTES = 300_000
HEADERS = {
    "User-Agent": "SyriusAssistant/1.0 (assistant personnel; carte des lieux)",
    "Referer": "https://syriusprojet1.vercel.app/",
    "Accept": "image/png",
    "Connection": "close",
}


class TileError(Exception):
    pass


def check_tile(z: int, x: int, y: int) -> None:
    if not (0 <= z <= MAX_ZOOM):
        raise TileError("zoom invalide")
    n = 1 << z
    if not (0 <= x < n and 0 <= y < n):
        raise TileError("tuile invalide")


def fetch_tile(z: int, x: int, y: int) -> bytes:
    check_tile(z, x, y)
    try:
        ip = web.resolve_public(HOST, 443)
        status, headers, body = web._open("https", HOST, ip, 443, f"/{z}/{x}/{y}.png", HEADERS)
    except web.WebError as e:
        raise TileError(str(e)) from None
    ctype = headers.get("content-type", "").split(";")[0].strip().lower()
    if status != 200 or ctype != "image/png" or len(body) > MAX_TILE_BYTES:
        raise TileError(f"tuile indisponible ({status})")
    return body


# ---------------------------------------------------------------- carte 3D (tuiles vectorielles)
# OpenFreeMap : gratuit, sans clé, données OpenStreetMap avec hauteur des bâtiments.
HOST_3D = "tiles.openfreemap.org"
MAX_ZOOM_3D = 14
MAX_VECTOR_BYTES = 1_400_000
FONTS = {"Noto Sans Regular", "Noto Sans Bold"}
VERSION_TTL = 3600
_VERSION_RE = re.compile(r"^https://tiles\.openfreemap\.org/planet/([0-9A-Za-z_]{1,64})/\{z\}/\{x\}/\{y\}\.pbf$")
_RANGE_RE = re.compile(r"^(\d{1,5})-(\d{1,5})$")
_version: dict = {"value": "", "at": 0.0}
HEADERS_3D = {"User-Agent": HEADERS["User-Agent"], "Accept": "*/*", "Connection": "close"}


def _get_3d(path: str) -> tuple[int, dict, bytes]:
    try:
        ip = web.resolve_public(HOST_3D, 443)
        status, headers, body = web._open("https", HOST_3D, ip, 443, path, HEADERS_3D)
    except web.WebError as e:
        raise TileError(str(e)) from None
    if headers.get("content-encoding", "").lower() == "gzip":
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            body = d.decompress(body, MAX_VECTOR_BYTES + 1)
        except zlib.error:
            raise TileError("données illisibles") from None
    if len(body) > MAX_VECTOR_BYTES:
        raise TileError("données trop lourdes")
    return status, headers, body


def current_version() -> str:
    """Version actuelle des données OpenFreeMap (gardée une heure)."""
    if _version["value"] and time.time() - _version["at"] < VERSION_TTL:
        return _version["value"]
    status, _, body = _get_3d("/planet")
    try:
        url = json.loads(body)["tiles"][0] if status == 200 else ""
    except (ValueError, KeyError, IndexError, TypeError):
        url = ""
    m = _VERSION_RE.match(url if isinstance(url, str) else "")
    if not m:
        raise TileError("version des cartes introuvable")
    _version.update(value=m.group(1), at=time.time())
    return m.group(1)


def fetch_vector(z: int, x: int, y: int) -> bytes:
    if not (0 <= z <= MAX_ZOOM_3D):
        raise TileError("zoom invalide")
    check_tile(z, x, y)
    status, _, body = _get_3d(f"/planet/{current_version()}/{z}/{x}/{y}.pbf")
    if status == 204 or (status == 200 and not body):
        return b""  # zone vide (mer, désert…)
    if status != 200:
        raise TileError(f"tuile indisponible ({status})")
    return body


def fetch_glyphs(fontstack: str, rng: str) -> bytes:
    if fontstack not in FONTS:
        raise TileError("police inconnue")
    m = _RANGE_RE.match(rng)
    if not m:
        raise TileError("plage invalide")
    start, end = int(m.group(1)), int(m.group(2))
    if start % 256 or end != start + 255 or start > 65280:
        raise TileError("plage invalide")
    status, _, body = _get_3d(f"/fonts/{quote(fontstack)}/{start}-{end}.pbf")
    if status != 200:
        raise TileError(f"police indisponible ({status})")
    return body
