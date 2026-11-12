"""Météo (Open-Meteo) : géocodage, prévisions, sécurité."""
import json

import pytest

from server.tools import weather, web
from server.tools.registry import ToolExecutor, build_tools

GEO = {"results": [{"name": "Lyon", "admin1": "Auvergne-Rhône-Alpes", "country": "France",
                    "latitude": 45.7578, "longitude": 4.832}]}
FC = {
    "current": {"time": "2026-11-12T14:00", "temperature_2m": 11.4, "apparent_temperature": 9.1,
                "relative_humidity_2m": 80, "weather_code": 61, "wind_speed_10m": 14.2, "is_day": 1},
    "hourly": {"time": [f"2026-11-12T{h:02d}:00" for h in range(24)], "temperature_2m": [10.0] * 24,
               "weather_code": [3] * 24, "precipitation_probability": [40] * 24, "is_day": [1] * 24},
    "daily": {"time": ["2026-11-12", "2026-11-13"], "weather_code": [61, 0], "temperature_2m_max": [12, 14],
              "temperature_2m_min": [6, 4], "precipitation_probability_max": [70, 5],
              "sunrise": ["", ""], "sunset": ["", ""]},
}


@pytest.fixture
def fake_fetch(monkeypatch):
    calls = []

    def fetch(url, allowed_types=web.ALLOWED_TYPES):
        calls.append((url, allowed_types))
        body = GEO if "geocoding-api" in url else FC
        return url, "application/json", json.dumps(body)
    monkeypatch.setattr(web, "fetch", fetch)
    return calls


def test_prevision_complete(fake_fetch):
    where = weather.geocode("Lyon")
    assert where == {"lat": 45.758, "lon": 4.832, "name": "Lyon, Auvergne-Rhône-Alpes, France"}
    w = weather.forecast(where)
    assert w["type"] == "weather" and w["now"]["temp"] == 11.4 and w["now"]["label"] == "Pluie faible"
    assert len(w["hours"]) == 10 and w["hours"][0]["h"] == "14h"  # à partir de l'heure actuelle
    assert w["days"][0]["day"] == "Aujourd'hui" and w["days"][1]["day"] == "ven." and w["days"][1]["icon"] == "☀️"
    assert all(t == ("application/json",) for _, t in fake_fetch)
    assert all(u.startswith(("https://geocoding-api.open-meteo.com/", "https://api.open-meteo.com/")) for u, _ in fake_fetch)


def test_valeurs_bizarres_ignorees(fake_fetch, monkeypatch):
    bad = {"current": {"temperature_2m": "chaud", "weather_code": "x"}, "hourly": {}, "daily": {}}
    monkeypatch.setattr(web, "fetch", lambda url, allowed_types=None: (url, "application/json", json.dumps(bad)))
    w = weather.forecast({"lat": 1, "lon": 2})
    assert w["now"]["temp"] is None and w["now"]["label"] == "Inconnu" and w["hours"] == [] and w["days"] == []


def test_outil_disponible_avec_internet(cfg):
    assert "get_weather" in {t["function"]["name"] for t in build_tools(cfg, {"internet": True})}
    assert "get_weather" not in {t["function"]["name"] for t in build_tools(cfg, {"internet": False})}


@pytest.mark.anyio
async def test_outil_ville_et_position(cfg, make_db, fake_fetch):
    ex = ToolExecutor(cfg, make_db())
    result, err, ev = await ex.run("get_weather", {"place": "Lyon"})
    assert not err and ev["type"] == "weather" and ev["place"].startswith("Lyon") and "web_non_fiable" in result
    result, err, ev = await ex.run("get_weather", {"near_me": True}, {"location": {"lat": 48.85, "lon": 2.35}})
    assert not err and ev["place"] == "Ma position"
    result, err, ev = await ex.run("get_weather", {"near_me": True}, {"location": None})
    assert ev is None and "inconnue" in result


@pytest.mark.anyio
async def test_lieu_introuvable(cfg, make_db, monkeypatch):
    monkeypatch.setattr(web, "fetch", lambda url, allowed_types=None: (url, "application/json", "{}"))
    result, err, ev = await ToolExecutor(cfg, make_db()).run("get_weather", {"place": "Zzzz"})
    assert ev is None and "introuvable" in result
