"""Recherche de lieux (restaurants, pharmacies, adresses…) pour l'affichage sur la carte.

Données OpenStreetMap via Nominatim (gratuit, sans clé), en passant par le pare-feu Internet.
La position de l'utilisateur, si elle est fournie, est arrondie (~100 m) et n'est jamais enregistrée.
"""
import json
import math
from urllib.parse import urlencode

from . import web

NOMINATIM = "https://nominatim.openstreetmap.org/search"
MAX_PLACES = 8


def round_location(loc) -> dict | None:
    """Valide et arrondit une position {lat, lon} (environ 100 m de précision)."""
    if not isinstance(loc, dict):
        return None
    lat, lon = loc.get("lat"), loc.get("lon")
    if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)) \
            or not isinstance(lon, (int, float)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return {"lat": round(float(lat), 3), "lon": round(float(lon), 3)}


def distance_m(a: dict, b: dict) -> int:
    r = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(h)))


def search(query: str, near: dict | None, radius_km: float = 3.0) -> list[dict]:
    q = " ".join(str(query).split())[:120]
    if not q:
        raise web.WebError("Recherche de lieu vide.")
    params = {"format": "jsonv2", "q": q, "limit": MAX_PLACES, "accept-language": "fr"}
    if near:
        d = radius_km / 111.0
        params.update({"viewbox": f"{near['lon'] - d},{near['lat'] + d},{near['lon'] + d},{near['lat'] - d}",
                       "bounded": 1})
    _, _, raw = web.fetch(NOMINATIM + "?" + urlencode(params), allowed_types=("application/json",))
    try:
        items = json.loads(raw)
    except ValueError:
        raise web.WebError("Réponse illisible du service de cartes.") from None
    places = []
    for it in items if isinstance(items, list) else []:
        try:
            lat, lon = float(it["lat"]), float(it["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        label = str(it.get("display_name", ""))
        name = str(it.get("name") or label.split(",")[0]).strip()[:80]
        place = {"name": name or "Lieu", "lat": round(lat, 6), "lon": round(lon, 6),
                 "address": ", ".join(p.strip() for p in label.split(",")[1:4])[:160],
                 "kind": str(it.get("type", ""))[:40]}
        if near:
            place["distance_m"] = distance_m(near, place)
        places.append(place)
    if near:
        places.sort(key=lambda p: p["distance_m"])
    return places[:MAX_PLACES]
