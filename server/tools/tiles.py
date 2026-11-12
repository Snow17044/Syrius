"""Fond de carte : les tuiles OpenStreetMap passent par notre serveur.

Pourquoi : l'application (WebView Android) n'envoie pas les en-têtes que le serveur de
tuiles exige, et cela évite aussi de transmettre l'adresse du téléphone à un tiers.
Sécurité : un seul hôte possible (codé en dur), coordonnées entières vérifiées,
connexion épinglée sur une IP publique, uniquement des images PNG de taille limitée.
"""
from __future__ import annotations

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
