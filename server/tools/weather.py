"""Météo : Open-Meteo (gratuit, sans clé, données publiques), en passant par le pare-feu Internet.

La position de l'utilisateur, si elle sert, est arrondie (~100 m) et n'est jamais enregistrée.
"""
import json
import math
from urllib.parse import urlencode

from . import web

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

# Codes météo WMO → (description, emoji jour, emoji nuit)
CODES = {
    0: ("Ciel dégagé", "☀️", "🌙"), 1: ("Plutôt dégagé", "🌤", "🌙"), 2: ("Partiellement nuageux", "⛅", "☁️"),
    3: ("Couvert", "☁️", "☁️"), 45: ("Brouillard", "🌫", "🌫"), 48: ("Brouillard givrant", "🌫", "🌫"),
    51: ("Bruine légère", "🌦", "🌧"), 53: ("Bruine", "🌦", "🌧"), 55: ("Bruine forte", "🌧", "🌧"),
    56: ("Bruine verglaçante", "🌧", "🌧"), 57: ("Bruine verglaçante", "🌧", "🌧"),
    61: ("Pluie faible", "🌦", "🌧"), 63: ("Pluie", "🌧", "🌧"), 65: ("Forte pluie", "🌧", "🌧"),
    66: ("Pluie verglaçante", "🌧", "🌧"), 67: ("Pluie verglaçante", "🌧", "🌧"),
    71: ("Neige faible", "🌨", "🌨"), 73: ("Neige", "🌨", "🌨"), 75: ("Forte neige", "❄️", "❄️"),
    77: ("Grains de neige", "🌨", "🌨"), 80: ("Averses", "🌦", "🌧"), 81: ("Averses", "🌧", "🌧"),
    82: ("Fortes averses", "⛈", "⛈"), 85: ("Averses de neige", "🌨", "🌨"), 86: ("Averses de neige", "❄️", "❄️"),
    95: ("Orage", "⛈", "⛈"), 96: ("Orage avec grêle", "⛈", "⛈"), 99: ("Orage avec grêle", "⛈", "⛈"),
}


def describe(code, day: bool = True) -> tuple[str, str]:
    label, d, n = CODES.get(int(code) if isinstance(code, (int, float)) else -1, ("Inconnu", "🌡", "🌡"))
    return label, d if day else n


def _get(url: str) -> dict:
    _, _, raw = web.fetch(url, allowed_types=("application/json",))
    try:
        data = json.loads(raw)
    except ValueError:
        raise web.WebError("Réponse illisible du service météo.") from None
    if not isinstance(data, dict):
        raise web.WebError("Réponse illisible du service météo.")
    return data


def geocode(place: str) -> dict | None:
    q = " ".join(str(place).split())[:80]
    if not q:
        return None
    data = _get(GEOCODE + "?" + urlencode({"name": q, "count": 1, "language": "fr", "format": "json"}))
    res = (data.get("results") or [None])[0]
    if not isinstance(res, dict):
        return None
    try:
        lat, lon = float(res["latitude"]), float(res["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    name = ", ".join(str(x) for x in (res.get("name"), res.get("admin1"), res.get("country")) if x)[:80]
    return {"lat": round(lat, 3), "lon": round(lon, 3), "name": name}


def _num(v, nd=0):
    return round(float(v), nd) if isinstance(v, (int, float)) and math.isfinite(v) else None


def forecast(where: dict) -> dict:
    params = {
        "latitude": where["lat"], "longitude": where["lon"], "timezone": "auto", "forecast_days": 6,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
        "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
    }
    d = _get(FORECAST + "?" + urlencode(params))
    cur = d.get("current") or {}
    day = bool(cur.get("is_day", 1))
    label, icon = describe(cur.get("weather_code"), day)
    out = {
        "type": "weather", "place": where.get("name") or "Ma position",
        "now": {"temp": _num(cur.get("temperature_2m"), 1), "feels": _num(cur.get("apparent_temperature"), 1),
                "humidity": _num(cur.get("relative_humidity_2m")), "wind": _num(cur.get("wind_speed_10m")),
                "label": label, "icon": icon, "time": str(cur.get("time", ""))[:16]},
        "hours": [], "days": [],
    }
    h = d.get("hourly") or {}
    times = h.get("time") or []
    now_t = out["now"]["time"]
    start = next((i for i, t in enumerate(times) if str(t)[:13] >= now_t[:13]), 0)
    for i in range(start, min(start + 12, len(times))):
        lab, ic = describe((h.get("weather_code") or [None] * len(times))[i],
                           bool((h.get("is_day") or [1] * len(times))[i]))
        out["hours"].append({"h": str(times[i])[11:13] + "h", "temp": _num((h.get("temperature_2m") or [None] * len(times))[i]),
                             "icon": ic, "rain": _num((h.get("precipitation_probability") or [None] * len(times))[i])})
    dd = d.get("daily") or {}
    jours = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
    from datetime import date
    for i, t in enumerate((dd.get("time") or [])[:6]):
        try:
            wd = jours[date.fromisoformat(str(t)).weekday()]
        except ValueError:
            wd = str(t)
        lab, ic = describe((dd.get("weather_code") or [None] * 6)[i])
        out["days"].append({"day": "Aujourd'hui" if i == 0 else wd, "icon": ic, "label": lab,
                            "max": _num((dd.get("temperature_2m_max") or [None] * 6)[i]),
                            "min": _num((dd.get("temperature_2m_min") or [None] * 6)[i]),
                            "rain": _num((dd.get("precipitation_probability_max") or [None] * 6)[i])})
    return out


def summary(w: dict) -> dict:
    """Résumé compact pour le modèle (le détail est affiché dans l'app)."""
    return {"lieu": w["place"], "maintenant": w["now"],
            "prochaines_heures": [f"{x['h']} {x['temp']}° pluie {x['rain']}%" for x in w["hours"][:6]],
            "jours": [f"{x['day']} {x['label']} {x['min']}°/{x['max']}° pluie {x['rain']}%" for x in w["days"]]}
